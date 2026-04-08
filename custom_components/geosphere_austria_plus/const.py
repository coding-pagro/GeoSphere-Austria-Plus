"""Konstanten für GeoSphere Austria Plus."""
from __future__ import annotations

DOMAIN = "geosphere_austria_plus"
CONF_NAME = "name"
CONF_STATION_ID = "station_id"
CONF_FORECAST_MODEL = "forecast_model"    # veraltet, nur noch für Rückwärtskompatibilität
CONF_FORECAST_MODELS = "forecast_models"  # Liste der gewählten Modelle
CONF_LATITUDE = "lat"
CONF_LONGITUDE = "lon"
CONF_ENABLE_WARNINGS = "enable_warnings"
CONF_ENABLE_AIR_QUALITY = "enable_air_quality"

# Keys für hass.data
DATA_CURRENT = "current"
DATA_FORECASTS = "forecasts"
DATA_WARNINGS = "warnings"
DATA_AIR_QUALITY = "air_quality"

# Warnungstypen (warntypid → Name)
WARNING_TYPES: dict[int, str] = {
    1: "Sturm",
    2: "Regen",
    3: "Schnee",
    4: "Glatteeis",
    5: "Gewitter",
    6: "Hitze",
    7: "Kälte",
}

# Warnstufen (warnstufeid → Name)
WARNING_LEVELS: dict[int, str] = {
    0: "keine",
    1: "gelb",
    2: "orange",
    3: "rot",
}

# Attribution
ATTRIBUTION = "Data provided by GeoSphere Austria"

# Update-Intervalle
CURRENT_UPDATE_INTERVAL = 10    # Minuten
FORECAST_UPDATE_INTERVAL = 60   # Minuten
WARNINGS_UPDATE_INTERVAL = 15   # Minuten
AIR_QUALITY_UPDATE_INTERVAL = 60  # Minuten (Modell aktualisiert stündlich)

# GeoSphere API
API_BASE = "https://dataset.api.hub.geosphere.at/v1"
WARNINGS_API_BASE = "https://warnungen.zamg.at/wsapp/api"

# Schadstoffvorhersage (chem-v2-1h-3km)
CHEM_RESOURCE = "chem-v2-1h-3km"
CHEM_PARAMS = "no2surf,o3surf,pm10surf,pm25surf"

# EU-Luftqualitätsindex-Grenzwerte: 5 Schwellenwerte für 6 Stufen (1=Gut … 6=Extrem schlecht)
# Einheit: µg/m³. Stufe i wird vergeben, wenn Wert < breakpoints[i-1].
AQI_BREAKPOINTS: dict[str, list[float]] = {
    "no2surf":  [40.0, 90.0, 120.0, 230.0, 340.0],
    "o3surf":   [50.0, 100.0, 130.0, 240.0, 380.0],
    "pm10surf": [20.0, 40.0, 50.0, 100.0, 150.0],
    "pm25surf": [10.0, 20.0, 25.0, 50.0, 75.0],
}

# Aktuelle Messwerte (TAWES – 10-Minuten-Auflösung)
TAWES_RESOURCE = "tawes-v1-10min"
TAWES_PARAMS = "TL,TP,RF,DD,FF,FX,P,PRED,RR,SO,SH,GLOW"

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
NWP_PARAMS = "t2m,rh2m,u10m,v10m,rain_acc,snow_acc,tcc,grad"
NOWCAST_PARAMS = "t2m,rh2m,ff,dd,rr,pt"

# Vorhersageparameter (Ensemble – Median-Perzentile, andere Namenskonvention)
# Hinweis: rh2m ist im Ensemble-Modell nicht verfügbar → humidity immer None.
ENSEMBLE_PARAMS = "t2m_p50,rain_p50,snow_p50,sundur_p50,grad_p50"

# Normalisierung: Ensemble-Parameternamen → NWP-Parameternamen
# Ermöglicht identische Verarbeitung in weather.py
# Hinweis: grad_p50 (W/m²) ist ein Momentanwert, NWP grad (Ws/m²) wird in
# api.py per Delta/3600 in W/m² umgerechnet – danach identisches Format.
ENSEMBLE_PARAM_MAP = {
    "t2m_p50":    "t2m",
    "rain_p50":   "rain_acc",
    "snow_p50":   "snow_acc",
    "sundur_p50": "sundur",
    "grad_p50":   "grad",
}

