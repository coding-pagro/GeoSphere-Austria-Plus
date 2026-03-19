"""GeoSphere Austria Plus – WeatherEntity mit Conditions & Forecast."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_STATION_ID,
    CONF_FORECAST_MODEL,
    DEFAULT_FORECAST_MODEL,
    FORECAST_MODEL_LABELS,
    nwp_to_condition,
)
from .coordinator import GeoSphereCurrentCoordinator, GeoSphereForecastCoordinator

_LOGGER = logging.getLogger(__name__)

# Schwellenwerte für Conditions aus Stationsdaten
_RAIN_THRESHOLD_MM = 0.2      # RR > 0.2 mm/10min → Regen
_HEAVY_RAIN_MM = 1.0           # > 1.0 mm/10min → Starkregen
_SNOW_THRESHOLD_CM = 0.1       # SH > 0 cm Schneehöhe
_FOG_VISIBILITY_HUM = 97       # RF > 97 % → potentiell Nebel
_WIND_STRONG_MS = 10.0         # FF > 10 m/s → windig
_CLOUD_FULL = 0.875            # Als bewölkt gilt > 87.5 % SO-Ausfall
_SUN_MINUTES_MAX = 10          # SO in Sekunden je 10 min


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Wetterentität registrieren."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    station_id = entry.data[CONF_STATION_ID]
    model = entry.data.get(CONF_FORECAST_MODEL, DEFAULT_FORECAST_MODEL)

    async_add_entities(
        [
            GeoSphereWeatherEntity(
                current_coordinator=coordinators["current"],
                forecast_coordinator=coordinators["forecast"],
                station_id=station_id,
                model=model,
                entry_id=entry.entry_id,
            )
        ]
    )


class GeoSphereWeatherEntity(
    CoordinatorEntity[GeoSphereCurrentCoordinator], WeatherEntity
):
    """Wetter-Entität mit Conditions und stündlicher/täglicher Vorhersage."""

    _attr_has_entity_name = True
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY
    )

    def __init__(
        self,
        current_coordinator: GeoSphereCurrentCoordinator,
        forecast_coordinator: GeoSphereForecastCoordinator,
        station_id: str,
        model: str,
        entry_id: str,
    ) -> None:
        super().__init__(current_coordinator)
        self._forecast_coordinator = forecast_coordinator
        self._station_id = station_id
        self._model = model
        self._attr_unique_id = f"geosphere_plus_{station_id}_{model}"
        model_label = FORECAST_MODEL_LABELS.get(model, model)
        self._attr_name = f"GeoSphere {station_id} {model_label}"

    # ------------------------------------------------------------------
    # Koordinator-Daten
    # ------------------------------------------------------------------

    @property
    def _current(self) -> dict[str, Any]:
        return self.coordinator.data or {}

    @property
    def _forecast_raw(self) -> list[dict[str, Any]]:
        return self._forecast_coordinator.data or []

    # ------------------------------------------------------------------
    # Aktuelle Werte
    # ------------------------------------------------------------------

    @property
    def native_temperature(self) -> float | None:
        return self._current.get("TL")

    @property
    def native_dew_point(self) -> float | None:
        return self._current.get("TP")

    @property
    def humidity(self) -> float | None:
        return self._current.get("RF")

    @property
    def native_pressure(self) -> float | None:
        return self._current.get("PRED") or self._current.get("P")

    @property
    def wind_bearing(self) -> float | None:
        return self._current.get("DD")

    @property
    def native_wind_speed(self) -> float | None:
        return self._current.get("FF")

    @property
    def native_wind_gust_speed(self) -> float | None:
        return self._current.get("FX")

    @property
    def native_precipitation(self) -> float | None:
        """Niederschlag der letzten 10 Minuten in mm."""
        return self._current.get("RR")

    # ------------------------------------------------------------------
    # Condition – aus Stationsmesswerten abgeleitet
    # ------------------------------------------------------------------

    @property
    def condition(self) -> str | None:
        """
        Ableitung der HA-Wetterbedingung aus TAWES-Messwerten.

        Priorität (höchste zuerst):
          1. Starkregen (RR > Schwellenwert)
          2. Normaler Regen (RR > minimaler Schwellenwert)
          3. Schnee (SH vorhanden)
          4. Nebel (RF sehr hoch)
          5. Bewölkt / Teilweise bewölkt (über Sonnenscheindauer SO)
          6. Windig
          7. Sonnig / Klare Nacht
        """
        d = self._current
        rr = d.get("RR") or 0.0       # Niederschlag mm/10min
        rf = d.get("RF") or 0.0       # Relative Luftfeuchtigkeit %
        ff = d.get("FF") or 0.0       # Windgeschwindigkeit m/s
        so = d.get("SO")              # Sonnenscheindauer Sekunden/10min (None = keine Daten)
        sh = d.get("SH") or 0.0       # Schneehöhe cm

        # Regen-Pegel
        if rr >= _HEAVY_RAIN_MM:
            return "pouring"
        if rr >= _RAIN_THRESHOLD_MM:
            return "rainy"

        # Schnee
        if sh > _SNOW_THRESHOLD_CM:
            if rr >= _RAIN_THRESHOLD_MM:
                return "snowy-rainy"
            return "snowy"

        # Nebel: sehr hohe Luftfeuchtigkeit ohne Wind
        if rf >= _FOG_VISIBILITY_HUM and ff < 2.0:
            return "fog"

        # Bewölkung aus Sonnenscheindauer ableiten
        # SO = Sekunden Sonnenschein in den letzten 10 Min (max 600 s)
        if so is not None:
            cloud_fraction = 1.0 - (so / 600.0)
            if cloud_fraction >= _CLOUD_FULL:
                if ff >= _WIND_STRONG_MS:
                    return "windy-variant"
                return "cloudy"
            if cloud_fraction >= 0.5:
                return "partlycloudy"

        # Windig
        if ff >= _WIND_STRONG_MS:
            return "windy"

        # Tag/Nacht ermitteln
        is_day = self._is_daytime()
        if is_day:
            return "sunny"
        return "clear-night"

    def _is_daytime(self) -> bool:
        """Grobe Tag/Nacht-Schätzung über UTC-Stunde + Längengrad-Offset."""
        now_utc = datetime.now(timezone.utc)
        lon = self._current.get("_lon") or 14.0  # Österreich default
        local_hour = (now_utc.hour + lon / 15.0) % 24
        return 6.0 <= local_hour < 21.0

    # ------------------------------------------------------------------
    # Stündliche Vorhersage
    # ------------------------------------------------------------------

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Stündliche Vorhersage aus NWP-Daten."""
        await self._forecast_coordinator.async_request_refresh()
        return self._build_hourly_forecasts()

    def _build_hourly_forecasts(self) -> list[Forecast]:
        forecasts: list[Forecast] = []
        now = datetime.now(timezone.utc)

        for entry in self._forecast_raw:
            ts_str = entry.get("datetime")
            if not ts_str:
                continue

            try:
                # ISO 8601 mit Zeitzone
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                _LOGGER.debug("Ungültiger Zeitstempel: %s", ts_str)
                continue

            if dt < now - timedelta(hours=1):
                continue  # Vergangenheit überspringen

            t2m = entry.get("t2m")
            rain = entry.get("rain_acc") or 0.0
            snow = entry.get("snow_acc") or 0.0
            rh = entry.get("rh2m")
            u10 = entry.get("u10m") or 0.0
            v10 = entry.get("v10m") or 0.0
            tcc = entry.get("tcc") or 0.0
            wind_speed = math.sqrt(u10**2 + v10**2)
            wind_bearing = (math.degrees(math.atan2(u10, v10)) + 180) % 360

            is_day = self._is_dt_daytime(dt)
            cond = nwp_to_condition(tcc, rain, snow, wind_speed, is_day)

            forecasts.append(
                Forecast(
                    datetime=dt.isoformat(),
                    condition=cond,
                    native_temperature=t2m,
                    native_precipitation=rain,
                    humidity=rh,
                    native_wind_speed=wind_speed,
                    wind_bearing=wind_bearing,
                    is_daytime=is_day,
                )
            )

        return forecasts[:48]  # max 48 Stunden

    # ------------------------------------------------------------------
    # Tägliche Vorhersage
    # ------------------------------------------------------------------

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Tägliche Zusammenfassung aus stündlichen NWP-Daten."""
        await self._forecast_coordinator.async_request_refresh()
        return self._build_daily_forecasts()

    def _build_daily_forecasts(self) -> list[Forecast]:
        """Stündliche Daten auf Tage aggregieren."""
        from collections import defaultdict

        days: dict[str, list[dict]] = defaultdict(list)
        now = datetime.now(timezone.utc)

        for entry in self._forecast_raw:
            ts_str = entry.get("datetime")
            if not ts_str:
                continue
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt < now - timedelta(hours=1):
                continue
            day_key = dt.strftime("%Y-%m-%d")
            days[day_key].append(entry)

        forecasts: list[Forecast] = []
        for day_key in sorted(days.keys())[:7]:
            entries = days[day_key]
            temps = [e["t2m"] for e in entries if e.get("t2m") is not None]
            rain_list = [e.get("rain_acc") or 0.0 for e in entries]
            snow_list = [e.get("snow_acc") or 0.0 for e in entries]
            rh_list = [e.get("rh2m") for e in entries if e.get("rh2m") is not None]
            tcc_list = [e.get("tcc") or 0.0 for e in entries]

            t_max = max(temps) if temps else None
            t_min = min(temps) if temps else None
            rain_sum = sum(rain_list)
            snow_sum = sum(snow_list)
            tcc_avg = sum(tcc_list) / len(tcc_list) if tcc_list else 0.0
            wind_speeds = [
                math.sqrt((e.get("u10m") or 0.0)**2 + (e.get("v10m") or 0.0)**2)
                for e in entries
            ]
            wind_max = max(wind_speeds) if wind_speeds else 0.0

            # Dominante Bedingung: schlechteste Stunde des Tages
            cond = nwp_to_condition(tcc_avg, rain_sum / max(len(entries), 1), snow_sum / max(len(entries), 1), wind_max, True)
            if rain_sum > 2.0:
                cond = "rainy"
            if rain_sum > 10.0:
                cond = "pouring"
            if snow_sum > 2.0:
                cond = "snowy"

            dt_day = datetime.strptime(day_key, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            forecasts.append(
                Forecast(
                    datetime=dt_day.isoformat(),
                    condition=cond,
                    native_temperature=t_max,
                    native_templow=t_min,
                    native_precipitation=rain_sum,
                    humidity=sum(rh_list) / len(rh_list) if rh_list else None,
                    native_wind_speed=wind_max,
                    is_daytime=True,
                )
            )

        return forecasts

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _is_dt_daytime(self, dt: datetime) -> bool:
        lon = self._current.get("_lon") or 14.0
        local_hour = (dt.hour + lon / 15.0) % 24
        return 6.0 <= local_hour < 21.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._forecast_coordinator.async_add_listener(self.async_write_ha_state)
        )
