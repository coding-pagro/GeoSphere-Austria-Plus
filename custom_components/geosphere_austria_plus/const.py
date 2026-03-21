"""Konstanten für GeoSphere Austria Plus."""
from __future__ import annotations

DOMAIN = "geosphere_austria_plus"
DEFAULT_NAME = "GeoSphere Austria Plus"
CONF_STATION_ID = "station_id"
CONF_FORECAST_MODEL = "forecast_model"    # veraltet, nur noch für Rückwärtskompatibilität
CONF_FORECAST_MODELS = "forecast_models"  # Liste der gewählten Modelle
CONF_STATION_NAME = "station_name"
CONF_LATITUDE = "lat"
CONF_LONGITUDE = "lon"

# Keys für hass.data
DATA_CURRENT = "current"
DATA_FORECASTS = "forecasts"

# Attribution
ATTRIBUTION = "Data provided by GeoSphere Austria"

# Update-Intervalle
CURRENT_UPDATE_INTERVAL = 10   # Minuten
FORECAST_UPDATE_INTERVAL = 60  # Minuten

# GeoSphere API
API_BASE = "https://dataset.api.hub.geosphere.at/v1"

# Aktuelle Messwerte (TAWES – 10-Minuten-Auflösung)
TAWES_RESOURCE = "tawes-v1-10min"
TAWES_PARAMS = "TL,TP,RF,DD,FF,FX,P,PRED,RR,RRM,SO,SH"

# Vorhersagemodelle (gültige IDs – Bezeichnungen in den Übersetzungsdateien)
FORECAST_MODELS = [
    "nwp-v1-1h-2500m",
    "ensemble-v1-1h-2500m",
    "nowcast-v1-15min-1km",
]
DEFAULT_FORECAST_MODEL = "nwp-v1-1h-2500m"

FORECAST_MODEL_LABELS = {
    "nwp-v1-1h-2500m":       "NWP",
    "ensemble-v1-1h-2500m":  "Ensemble",
    "nowcast-v1-15min-1km":  "Nowcast",
}

# Vorhersageparameter (NWP / Nowcast)
NWP_PARAMS = "t2m,rh2m,u10m,v10m,rain_acc,snow_acc,cape,tcc,msl"

# Vorhersageparameter (Ensemble – Median-Perzentile, andere Namenskonvention)
ENSEMBLE_PARAMS = "t2m_p50,rain_p50,snow_p50,rr_p50,sundur_p50,cape_p50"

# Normalisierung: Ensemble-Parameternamen → NWP-Parameternamen
# Ermöglicht identische Verarbeitung in weather.py
ENSEMBLE_PARAM_MAP = {
    "t2m_p50":    "t2m",
    "rain_p50":   "rain_acc",
    "snow_p50":   "snow_acc",
    "sundur_p50": "sundur",
    "cape_p50":   "cape",
}

# NWP → HA-Condition Mapping (über Wolkenbedeckung + Niederschlag)
# tcc = total cloud cover [0–1], rain_acc [mm], snow_acc [mm]
def nwp_to_condition(tcc: float | None, rain_mm: float, snow_mm: float, wind_ms: float, is_day: bool) -> str | None:
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
        # Wolkenbedeckung nicht verfügbar (z. B. Nowcast) – kein Sonnenschein annehmen
        if wind_ms > 10:
            return "windy"
        return None
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
