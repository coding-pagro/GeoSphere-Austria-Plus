"""Konstanten für GeoSphere Austria Plus."""
from __future__ import annotations

DOMAIN = "geosphere_austria_plus"
DEFAULT_NAME = "GeoSphere Austria Plus"
CONF_STATION_ID = "station_id"
CONF_FORECAST_MODEL = "forecast_model"

# Update-Intervalle
CURRENT_UPDATE_INTERVAL = 10   # Minuten
FORECAST_UPDATE_INTERVAL = 60  # Minuten

# GeoSphere API
API_BASE = "https://dataset.api.hub.geosphere.at/v1"

# Aktuelle Messwerte (TAWES – 10-Minuten-Auflösung)
TAWES_RESOURCE = "tawes-v1-10min"
TAWES_PARAMS = "TL,TP,RF,DD,FF,FX,P,PRED,RR,RRM,SO,SH"

# Vorhersagemodelle
FORECAST_MODELS = {
    "nwp-v1-1h-2500m": "NWP – Numerische Wettervorhersage (1h, 2.5 km)",
    "ensemble-v1-1h-2500m": "Ensemble-Vorhersage (1h, 2.5 km)",
    "nowcast-v1-15min-1km": "Nowcast (15 min, 1 km)",
}
DEFAULT_FORECAST_MODEL = "nwp-v1-1h-2500m"

# Vorhersageparameter (NWP)
NWP_PARAMS = "t2m,rh2m,u10m,v10m,rain_acc,snow_acc,cape,tcc,msl"

# Mapping: Stationsmesswerte → HA-Wetterbedingungen
# Logik: Rang-basiert – höchster zutreffender Rang gewinnt
# Bedingungsreihenfolge nach Priorität
CONDITION_MAP = [
    # (Bedingung, Beschreibung)
    # Wird durch _derive_condition() ausgewertet
    ("lightning-rainy", "Gewitter mit Regen"),
    ("snowy-rainy",     "Schneeregen"),
    ("snowy",           "Schneefall"),
    ("rainy",           "Regen"),
    ("pouring",         "Starkregen"),
    ("fog",             "Nebel"),
    ("cloudy",          "Bewölkt"),
    ("partlycloudy",    "Teilweise bewölkt"),
    ("windy-variant",   "Windig und bewölkt"),
    ("windy",           "Windig"),
    ("sunny",           "Sonnig"),
    ("clear-night",     "Klare Nacht"),
    ("exceptional",     "Außergewöhnlich"),
]

# NWP → HA-Condition Mapping (über Wolkenbedeckung + Niederschlag)
# tcc = total cloud cover [0–1], rain_acc [mm], snow_acc [mm]
def nwp_to_condition(tcc: float, rain_mm: float, snow_mm: float, wind_ms: float, is_day: bool) -> str:
    """Leite HA-Wetterbedingung aus NWP-Parametern ab."""
    if snow_mm > 0.1 and rain_mm > 0.1:
        return "snowy-rainy"
    if snow_mm > 0.1:
        return "snowy"
    if rain_mm > 5.0:
        return "pouring"
    if rain_mm > 0.1:
        return "rainy"
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
