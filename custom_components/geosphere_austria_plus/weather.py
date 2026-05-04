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


# Mapping from GeoSphere symbol codes (sy, 1–32) to HA weather conditions.
# Source: https://github.com/Geosphere-Austria/dataset-api-docs/issues/30#issuecomment-2042539848
_SY_CONDITION_MAP: dict[int, str] = {
    # Codes 1–2: Cloudless / Fair
    1: "sunny",
    # Codes 3–5: Cloudy variations
    2: "partlycloudy",
    3: "partlycloudy",
    4: "cloudy",
    5: "cloudy",
    # Codes 6–7: Fog types
    6: "fog",
    7: "fog",
    # Codes 8–10: Rain (increasing intensity)
    8: "rainy",
    9: "rainy",
    10: "pouring",
    # Codes 11–13: Rain-snow mix (continuous)
    11: "snowy-rainy",
    12: "snowy-rainy",
    13: "snowy-rainy",
    # Codes 14–16: Snow (increasing intensity)
    14: "snowy",
    15: "snowy",
    16: "snowy",
    # Codes 17–19: Showers (rain)
    17: "rainy",
    18: "rainy",
    19: "pouring",
    # Codes 20–22: Snow-rain showers
    20: "snowy-rainy",
    21: "snowy-rainy",
    22: "snowy-rainy",
    # Codes 23–25: Snow showers
    23: "snowy",
    24: "snowy",
    25: "snowy",
    # Codes 26–32: Thunderstorms (all variants)
    26: "lightning-rainy",
    27: "lightning-rainy",
    28: "lightning-rainy",
    29: "lightning-rainy",
    30: "lightning-rainy",
    31: "lightning-rainy",
    32: "lightning-rainy",
}


def _coerce_sy(sy: Any) -> int | None:
    """Wandelt einen rohen sy-Wert robust in int um. Liefert None bei ungültigen Werten."""
    if sy is None:
        return None
    try:
        return int(round(float(sy)))
    except (TypeError, ValueError):
        return None


def _base_condition_from_sy(sy: int | float | None) -> str | None:
    """Rohe Bedingung aus GeoSphere-Symbolcode — ohne Wind- oder Nacht-Logik."""
    code = _coerce_sy(sy)
    if code is None:
        return None
    return _SY_CONDITION_MAP.get(code)


def _base_condition_from_tcc(tcc: float | None, rain_mm: float, snow_mm: float) -> str:
    """Rohe Bedingung aus tcc/Niederschlag — ohne Wind- oder Nacht-Logik."""
    if snow_mm > 0.1 and rain_mm > 0.1:
        return "snowy-rainy"
    if snow_mm > 0.1:
        return "snowy"
    if rain_mm > 5.0:
        return "pouring"
    if rain_mm > 0.1:
        return "rainy"
    if tcc is None or tcc <= 0.5:
        return "sunny"
    if tcc <= 0.875:
        return "partlycloudy"
    return "cloudy"


def nwp_to_condition(
    tcc: float | None,
    rain_mm: float,
    snow_mm: float,
    wind_ms: float,
    is_day: bool,
    sy: int | float | None = None,
) -> str | None:
    """Leite HA-Wetterbedingung aus NWP-Parametern ab."""
    base = _base_condition_from_sy(sy) if sy is not None else None
    if base is None:
        base = _base_condition_from_tcc(tcc, rain_mm, snow_mm)

    if wind_ms > _WIND_STRONG_MS:
        if base == "sunny":
            return "windy"
        if base in ("partlycloudy", "cloudy"):
            return "windy-variant"

    if base == "sunny" and not is_day:
        return "clear-night"

    return base


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

    @property
    def _first_forecast_entry(self) -> dict[str, Any] | None:
        """Erster gültiger Vorhersagepunkt (max. 1 h in der Vergangenheit)."""
        now = datetime.now(timezone.utc)
        for entry in self._forecast_raw:
            ts_str = entry.get("datetime")
            if not ts_str:
                continue
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt >= now - timedelta(hours=1):
                return entry
        return None

    # ------------------------------------------------------------------
    # Aktuelle Werte – aus TAWES wenn vorhanden, sonst aus erstem
    # Vorhersagepunkt (Fallback ohne konfigurierte Station).
    # Kein Forecast-Äquivalent: Taupunkt, Luftdruck, Böen.
    # ------------------------------------------------------------------

    @property
    def native_temperature(self) -> float | None:
        v = self._current.get("TL")
        if v is not None:
            return v
        entry = self._first_forecast_entry
        return entry.get("t2m") if entry else None

    @property
    def native_dew_point(self) -> float | None:
        return self._current.get("TP")

    @property
    def humidity(self) -> float | None:
        v = self._current.get("RF")
        if v is not None:
            return v
        entry = self._first_forecast_entry
        return entry.get("rh2m") if entry else None

    @property
    def native_pressure(self) -> float | None:
        return self._current.get("PRED") or self._current.get("P")

    @property
    def wind_bearing(self) -> float | None:
        v = self._current.get("DD")
        if v is not None:
            return v
        entry = self._first_forecast_entry
        if entry is None:
            return None
        # Nowcast liefert dd direkt; NWP/Ensemble: aus u10m/v10m berechnen
        if entry.get("dd") is not None:
            return float(entry["dd"])
        u10 = entry.get("u10m") or 0.0
        v10 = entry.get("v10m") or 0.0
        if u10 or v10:
            return (math.degrees(math.atan2(u10, v10)) + 180) % 360
        return None

    @property
    def native_wind_speed(self) -> float | None:
        v = self._current.get("FF")
        if v is not None:
            return v
        entry = self._first_forecast_entry
        if entry is None:
            return None
        # Nowcast liefert ff direkt; NWP/Ensemble: aus u10m/v10m berechnen
        if entry.get("ff") is not None:
            return float(entry["ff"])
        u10 = entry.get("u10m") or 0.0
        v10 = entry.get("v10m") or 0.0
        if u10 or v10:
            return math.sqrt(u10**2 + v10**2)
        return None

    @property
    def native_wind_gust_speed(self) -> float | None:
        return self._current.get("FX")

    @property
    def native_precipitation(self) -> float | None:
        v = self._current.get("RR")
        if v is not None:
            return v
        entry = self._first_forecast_entry
        if entry is None:
            return None
        # Nach Normalisierung in api.py liefern alle Modelle rain_acc/snow_acc als mm/Zeitschritt:
        #   - Nowcast: aus rr+pt abgeleitet (_normalize_nowcast_params)
        #   - Ensemble: rain_p50/snow_p50 als Periodensummen (_normalize_ensemble_params)
        #   - NWP: nach _deaccumulate_precip de-akkumuliert
        rain = entry.get("rain_acc") or 0.0
        snow = entry.get("snow_acc") or 0.0
        if rain == 0.0 and snow == 0.0:
            return None
        return rain + snow

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
        # sy (symbol code) is only available in NWP model output; Ensemble and
        # Nowcast do not provide it, so we only pass it for NWP entries.
        is_nwp = "nwp" in self._model
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
            sy = entry.get("sy") if is_nwp else None
            return nwp_to_condition(tcc, rain, snow, wind_speed, is_day, sy)
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
            ugust = entry.get("ugust")
            vgust = entry.get("vgust")
            tcc = entry.get("tcc")
            wind_speed = math.sqrt(u10**2 + v10**2)
            wind_bearing = (math.degrees(math.atan2(u10, v10)) + 180) % 360
            if ugust is not None and vgust is not None:
                # NWP/Ensemble: Böe aus Windvektorkomponenten berechnen
                wind_gust: float | None = math.sqrt(ugust**2 + vgust**2)
            else:
                # Nowcast: fx ist bereits eine skalare Böengeschwindigkeit
                wind_gust = entry.get("wind_gust_speed")

            is_day = self._is_dt_daytime(dt)
            # sy (symbol code) is only present in NWP model output.
            sy = entry.get("sy") if "nwp" in self._model else None
            cond = nwp_to_condition(tcc, rain, snow, wind_speed, is_day, sy)
            if cond is None:
                cond = self.condition

            forecast_entry = Forecast(
                datetime=dt.isoformat(),
                condition=cond,
                native_temperature=t2m,
                native_precipitation=rain + snow,
                humidity=rh,
                native_wind_speed=wind_speed,
                wind_bearing=wind_bearing,
                native_wind_gust_speed=wind_gust,
                is_daytime=is_day,
            )
            grad = entry.get("grad")
            if grad is not None:
                forecast_entry["solar_irradiance"] = round(grad, 1)  # type: ignore[typeddict-unknown-key]
            # Schneefallgrenze (m) — hochrelevant für österreichisches Bergland
            snowlmt = entry.get("snowlmt")
            if snowlmt is not None:
                forecast_entry["snow_altitude"] = round(snowlmt)  # type: ignore[typeddict-unknown-key]
            # CAPE (m²/s²) — quantitatives Gewitterpotenzial
            cape = entry.get("cape")
            if cape is not None:
                forecast_entry["cape"] = round(cape)  # type: ignore[typeddict-unknown-key]
            forecasts.append(forecast_entry)

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

            # Tagesextreme: native mxt2m/mnt2m vom Modell bevorzugen, sonst aus stündlichen
            # t2m-Werten ableiten. Das Modell kennt Peaks auch zwischen vollen Stunden.
            mxt2m_list = [e["mxt2m"] for e in entries if e.get("mxt2m") is not None]
            mnt2m_list = [e["mnt2m"] for e in entries if e.get("mnt2m") is not None]
            t_max = max(mxt2m_list) if mxt2m_list else (max(temps) if temps else None)
            t_min = min(mnt2m_list) if mnt2m_list else (min(temps) if temps else None)
            # rain_acc/snow_acc sind immer Intervallwerte (mm/Zeitschritt):
            # NWP: nach _deaccumulate_precip in api.py de-akkumuliert.
            # Ensemble: rain_p50/snow_p50 sind Periodensummen (mm/Periode, kein Delta nötig).
            # Direkte Summe ergibt in beiden Fällen die korrekte Tagessumme.
            rain_total = sum(max(0.0, r) for r in rain_list)
            snow_total = sum(max(0.0, s) for s in snow_list)
            tcc_avg = sum(tcc_list) / len(tcc_list) if tcc_list else None
            wind_speeds = [
                math.sqrt((e.get("u10m") or 0.0)**2 + (e.get("v10m") or 0.0)**2)
                for e in entries
                if e.get("u10m") is not None or e.get("v10m") is not None
            ]
            wind_max: float | None = max(wind_speeds) if wind_speeds else None
            gust_speeds = [
                math.sqrt(e["ugust"] ** 2 + e["vgust"] ** 2)
                for e in entries
                if e.get("ugust") is not None and e.get("vgust") is not None
            ]
            # For Nowcast entries that carry wind_gust_speed directly
            gust_speeds += [
                e["wind_gust_speed"]
                for e in entries
                if e.get("wind_gust_speed") is not None
            ]
            gust_max = max(gust_speeds) if gust_speeds else None

            # For NWP: use the worst-case sy code among daytime entries. Daytime-only
            # filtering prevents clear-night hours (sy 1–2) from suppressing significant
            # daytime conditions. Falls back to tcc/precip aggregate for Ensemble/Nowcast.
            daytime_sy: list[int] = []
            if "nwp" in self._model:
                for e in entries:
                    if self._entry_is_daytime(e):
                        if (sy_val := _coerce_sy(e.get("sy"))) is not None:
                            daytime_sy.append(sy_val)

            if daytime_sy:
                cond = nwp_to_condition(
                    tcc_avg, 0.0, 0.0, wind_max or 0.0, True, max(daytime_sy)
                )
            else:
                # wind_max kann None sein (kein Wind-Vektor verfügbar) → 0.0 als Fallback
                cond = nwp_to_condition(
                    tcc_avg,
                    rain_total / max(len(entries), 1),
                    snow_total / max(len(entries), 1),
                    wind_max or 0.0,
                    True,
                )
            # Accumulated precipitation overrides the symbol-code condition, but must
            # not downgrade lightning-rainy (already the highest-priority outcome).
            # Reihenfolge ist beabsichtigt: bei gleichzeitigem Regen UND Schnee jeweils
            # über 2 mm wird "snowy-rainy" bevorzugt — auch wenn rain_total > 10 mm wäre.
            if cond != "lightning-rainy":
                if rain_total > 2.0 and snow_total > 2.0:
                    cond = "snowy-rainy"
                elif rain_total > 10.0:
                    cond = "pouring"
                elif rain_total > 2.0:
                    cond = "rainy"
                elif snow_total > 2.0:
                    cond = "snowy"

            # Schneefallgrenze: Tagesminimum (= tiefster Punkt an dem Schneefall möglich ist)
            snowlmt_list = [e["snowlmt"] for e in entries if e.get("snowlmt") is not None]
            snowlmt_min = min(snowlmt_list) if snowlmt_list else None
            # CAPE: Tagesmaximum (höchstes Gewitterpotenzial im Tagesverlauf)
            cape_list = [e["cape"] for e in entries if e.get("cape") is not None]
            cape_max = max(cape_list) if cape_list else None

            dt_day = datetime.strptime(day_key, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            daily_entry = Forecast(
                datetime=dt_day.isoformat(),
                condition=cond,
                native_temperature=t_max,
                native_templow=t_min,
                native_precipitation=rain_total + snow_total,
                humidity=sum(rh_list) / len(rh_list) if rh_list else None,
                native_wind_speed=wind_max,
                native_wind_gust_speed=gust_max,
                is_daytime=True,
            )
            if snowlmt_min is not None:
                daily_entry["snow_altitude"] = round(snowlmt_min)  # type: ignore[typeddict-unknown-key]
            if cape_max is not None:
                daily_entry["cape"] = round(cape_max)  # type: ignore[typeddict-unknown-key]
            forecasts.append(daily_entry)

        return forecasts

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _is_dt_daytime(self, dt: datetime) -> bool:
        local_hour = (dt.hour + self._lon / 15.0) % 24
        return 6.0 <= local_hour < 21.0

    def _entry_is_daytime(self, entry: dict) -> bool:
        """Return True if the entry's datetime timestamp falls in daytime hours."""
        ts = entry.get("datetime")
        if not ts:
            return False
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return False
        return self._is_dt_daytime(dt)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._current_coordinator is not None:
            self.async_on_remove(
                self._current_coordinator.async_add_listener(self.async_write_ha_state)
            )
