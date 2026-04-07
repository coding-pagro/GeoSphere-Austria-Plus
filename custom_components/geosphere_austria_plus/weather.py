"""GeoSphere Austria Plus – WeatherEntity mit Conditions & Forecast."""
from __future__ import annotations

import logging
import math
from collections import defaultdict
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
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTRIBUTION,
    DOMAIN,
    CONF_NAME,
    CONF_FORECAST_MODEL,
    CONF_FORECAST_MODELS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    DATA_CURRENT,
    DATA_FORECASTS,
    DEFAULT_FORECAST_MODEL,
    FORECAST_MODEL_LABELS,
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
_SUN_SECONDS_MAX = 600         # SO max. 600 s Sonnenschein je 10-Minuten-Intervall


def nwp_to_condition(
    tcc: float | None,
    rain_mm: float,
    snow_mm: float,
    wind_ms: float,
    is_day: bool,
) -> str | None:
    """Leite HA-Wetterbedingung aus NWP-Parametern ab."""
    if snow_mm > 0.1 and rain_mm > 0.1:
        return "snowy-rainy"
    if snow_mm > 0.1:
        return "snowy"
    if rain_mm > 5.0:
        return "pouring"
    if rain_mm > 0.1:
        return "rainy"
    if tcc is None:
        # Wolkenbedeckung nicht verfügbar (z. B. Nowcast)
        if wind_ms > 10:
            return "windy"
        return "sunny" if is_day else "clear-night"
    if tcc > 0.875:
        return "cloudy"
    if tcc > 0.5:
        if wind_ms > 10:
            return "windy-variant"
        return "partlycloudy"
    if wind_ms > 10:
        return "windy"
    if is_day:
        return "sunny"
    return "clear-night"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Eine Wetterentität pro gewähltem Modell registrieren."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    entry_id = entry.entry_id
    location_name = (
        entry.options.get(CONF_NAME)
        or entry.data.get(CONF_NAME)
        or entry.title
    )
    lon: float = (
        entry.options[CONF_LONGITUDE]
        if CONF_LONGITUDE in entry.options
        else entry.data.get(CONF_LONGITUDE, 14.0)
    )

    # Options haben Vorrang (OptionsFlow), dann Data, dann Rückwärtskompatibilität
    # Explizite Schlüsselprüfung, damit eine leere Liste (0 Modelle) nicht übergangen wird
    if CONF_FORECAST_MODELS in entry.options:
        models: list[str] = entry.options[CONF_FORECAST_MODELS]
    elif CONF_FORECAST_MODELS in entry.data:
        models = entry.data[CONF_FORECAST_MODELS]
    else:
        models = [entry.data.get(CONF_FORECAST_MODEL, DEFAULT_FORECAST_MODEL)]

    current_coordinator: GeoSphereCurrentCoordinator | None = coordinators.get(DATA_CURRENT)

    entities = [
        GeoSphereWeatherEntity(
            current_coordinator=current_coordinator,
            forecast_coordinator=coordinators[DATA_FORECASTS][model],
            entry_id=entry_id,
            model=model,
            location_name=location_name,
            lon=lon,
        )
        for model in models
    ]

    # Aktive unique_ids für spätere Cleanup-Logik registrieren
    coordinators.setdefault("_active_unique_ids", set()).update(
        e.unique_id for e in entities
    )

    async_add_entities(entities)


class GeoSphereWeatherEntity(
    CoordinatorEntity[GeoSphereForecastCoordinator], WeatherEntity
):
    """Wetter-Entität mit Conditions und stündlicher/täglicher Vorhersage.

    Der Forecast-Koordinator ist immer verfügbar (primär).
    Der Current-Koordinator (TAWES-Station) ist optional — ohne ihn wird
    der aktuelle Zustand aus dem ersten Vorhersagepunkt abgeleitet.
    """

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS

    def __init__(
        self,
        current_coordinator: GeoSphereCurrentCoordinator | None,
        forecast_coordinator: GeoSphereForecastCoordinator,
        entry_id: str,
        model: str,
        location_name: str,
        lon: float = 14.0,
    ) -> None:
        super().__init__(forecast_coordinator)
        self._current_coordinator = current_coordinator
        self._model = model
        self._lon = lon
        self._attr_unique_id = f"geosphere_plus_{entry_id}_{model}"

        self._attr_name = FORECAST_MODEL_LABELS.get(model, model)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=location_name,
            manufacturer="GeoSphere Austria",
            model="DataHub API v1",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://dataset.api.hub.geosphere.at/v1",
        )

    @property
    def supported_features(self) -> WeatherEntityFeature:
        """Nowcast liefert nur kurzfristige Stundendaten – kein Daily-Forecast."""
        if "nowcast" in self._model:
            return WeatherEntityFeature.FORECAST_HOURLY
        return WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY

    # ------------------------------------------------------------------
    # Koordinator-Daten
    # ------------------------------------------------------------------

    @property
    def _current(self) -> dict[str, Any]:
        if self._current_coordinator is None:
            return {}
        return self._current_coordinator.data or {}

    @property
    def _forecast_raw(self) -> list[dict[str, Any]]:
        return self.coordinator.data or []

    # ------------------------------------------------------------------
    # Aktuelle Werte (aus TAWES wenn vorhanden, sonst None)
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
    # Condition – aus TAWES abgeleitet wenn vorhanden, sonst aus Forecast
    # ------------------------------------------------------------------

    @property
    def condition(self) -> str | None:
        if self._current_coordinator is not None and self._current_coordinator.data:
            return self._condition_from_tawes()
        return self._condition_from_forecast()

    def _condition_from_tawes(self) -> str | None:
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
        rr = d.get("RR") or 0.0
        rf = d.get("RF") or 0.0
        ff = d.get("FF") or 0.0
        so = d.get("SO")
        sh = d.get("SH") or 0.0

        if sh > _SNOW_THRESHOLD_CM and rr >= _RAIN_THRESHOLD_MM:
            return "snowy-rainy"
        if rr >= _HEAVY_RAIN_MM:
            return "pouring"
        if rr >= _RAIN_THRESHOLD_MM:
            return "rainy"
        if sh > _SNOW_THRESHOLD_CM:
            return "snowy"
        if rf >= _FOG_VISIBILITY_HUM and ff < 2.0:
            return "fog"
        if so is not None:
            cloud_fraction = 1.0 - (so / _SUN_SECONDS_MAX)
            if cloud_fraction >= _CLOUD_FULL:
                if ff >= _WIND_STRONG_MS:
                    return "windy-variant"
                return "cloudy"
            if cloud_fraction >= 0.5:
                return "partlycloudy"
        if ff >= _WIND_STRONG_MS:
            return "windy"
        is_day = self._is_daytime()
        if is_day:
            return "sunny"
        return "clear-night"

    def _condition_from_forecast(self) -> str | None:
        """Aktuellen Zustand aus dem ersten verfügbaren Vorhersagepunkt ableiten."""
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
            rain = entry.get("rain_acc") or 0.0
            snow = entry.get("snow_acc") or 0.0
            tcc = entry.get("tcc")
            u10 = entry.get("u10m") or 0.0
            v10 = entry.get("v10m") or 0.0
            wind_speed = math.sqrt(u10**2 + v10**2)
            is_day = self._is_daytime()
            return nwp_to_condition(tcc, rain, snow, wind_speed, is_day)
        return None

    def _is_daytime(self) -> bool:
        """Tag/Nacht aus sun.sun-Entity ableiten; Fallback auf Längengrad-Schätzung."""
        hass = getattr(self, "hass", None)
        if hass is not None:
            sun_state = hass.states.get("sun.sun")
            if sun_state is not None:
                return sun_state.state == "above_horizon"
        now_utc = datetime.now(timezone.utc)
        local_hour = (now_utc.hour + self._lon / 15.0) % 24
        return 6.0 <= local_hour < 21.0

    # ------------------------------------------------------------------
    # Stündliche Vorhersage
    # ------------------------------------------------------------------

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Stündliche Vorhersage aus NWP-Daten."""
        return self._build_hourly_forecasts()

    def _build_hourly_forecasts(self) -> list[Forecast]:
        forecasts: list[Forecast] = []
        now = datetime.now(timezone.utc)

        for entry in self._forecast_raw:
            ts_str = entry.get("datetime")
            if not ts_str:
                continue

            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                _LOGGER.debug("Ungültiger Zeitstempel: %s", ts_str)
                continue

            if dt < now - timedelta(hours=1):
                continue

            t2m = entry.get("t2m")
            rain = entry.get("rain_acc") or 0.0
            snow = entry.get("snow_acc") or 0.0
            rh = entry.get("rh2m")
            u10 = entry.get("u10m") or 0.0
            v10 = entry.get("v10m") or 0.0
            tcc = entry.get("tcc")
            wind_speed = math.sqrt(u10**2 + v10**2)
            wind_bearing = (math.degrees(math.atan2(u10, v10)) + 180) % 360

            is_day = self._is_dt_daytime(dt)
            cond = nwp_to_condition(tcc, rain, snow, wind_speed, is_day)
            if cond is None:
                cond = self.condition

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

        return forecasts[:48]

    # ------------------------------------------------------------------
    # Tägliche Vorhersage
    # ------------------------------------------------------------------

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Tägliche Zusammenfassung aus stündlichen NWP-Daten."""
        return self._build_daily_forecasts()

    def _build_daily_forecasts(self) -> list[Forecast]:
        """Stündliche Daten auf Tage aggregieren."""
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
            tcc_list = [e["tcc"] for e in entries if e.get("tcc") is not None]

            t_max = max(temps) if temps else None
            t_min = min(temps) if temps else None
            # rain_acc/snow_acc sind Akkumulationswerte. Summe der positiven Deltas
            # ergibt die Tagessumme – robust gegen Modell-Lauf-Resets (negatives
            # Delta = Reset → wird als 0 gezählt).
            rain_total = sum(
                max(0.0, rain_list[i + 1] - rain_list[i])
                for i in range(len(rain_list) - 1)
            ) if len(rain_list) > 1 else 0.0
            snow_total = sum(
                max(0.0, snow_list[i + 1] - snow_list[i])
                for i in range(len(snow_list) - 1)
            ) if len(snow_list) > 1 else 0.0
            tcc_avg = sum(tcc_list) / len(tcc_list) if tcc_list else None
            wind_speeds = [
                math.sqrt((e.get("u10m") or 0.0)**2 + (e.get("v10m") or 0.0)**2)
                for e in entries
            ]
            wind_max = max(wind_speeds) if wind_speeds else 0.0

            cond = nwp_to_condition(
                tcc_avg,
                rain_total / max(len(entries), 1),
                snow_total / max(len(entries), 1),
                wind_max,
                True,
            )
            if rain_total > 2.0:
                cond = "rainy"
            if rain_total > 10.0:
                cond = "pouring"
            if snow_total > 2.0:
                cond = "snowy"

            dt_day = datetime.strptime(day_key, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            forecasts.append(
                Forecast(
                    datetime=dt_day.isoformat(),
                    condition=cond,
                    native_temperature=t_max,
                    native_templow=t_min,
                    native_precipitation=rain_total,
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
        local_hour = (dt.hour + self._lon / 15.0) % 24
        return 6.0 <= local_hour < 21.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._current_coordinator is not None:
            self.async_on_remove(
                self._current_coordinator.async_add_listener(self.async_write_ha_state)
            )
