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
TAWES_PARAMS = "TL,TP,RF,DD,FF,FX,P,PRED,RR,SO,SH,GLOW,TB1"

# Vorhersagemodelle (gültige IDs – Bezeichnungen in den Übersetzungsdateien)
# NWP und Ensemble basieren seit v2 auf C-LAEF AlpeAdria (1 km, Läufe alle 3 h).
FORECAST_MODELS = [
    "nwp-v2-1h-1km",
    "ensemble-v2-1h-1km",
    "nowcast-v1-15min-1km",
]
DEFAULT_FORECAST_MODEL = "nwp-v2-1h-1km"

FORECAST_MODEL_LABELS = {
    "nwp-v2-1h-1km":         "NWP",
    "ensemble-v2-1h-1km":    "Ensemble",
    "nowcast-v1-15min-1km":  "Nowcast",
}

# Von GeoSphere am 04.11.2026 eingestellte Modelle → Nachfolger.
# Wird von async_migrate_entry für bestehende Config-Einträge und
# Weather-Entity-Unique-IDs verwendet.
LEGACY_FORECAST_MODEL_MAP = {
    "nwp-v1-1h-2500m":       "nwp-v2-1h-1km",
    "ensemble-v1-1h-2500m":  "ensemble-v2-1h-1km",
}

# Normalisierung: v2-Parameternamen → interne Namen
# Ermöglicht identische Verarbeitung aller Modelle in weather.py.
# Alle v2-Werte gelten für das zurückliegende Intervall bzw. den Zeitpunkt —
# es gibt keine Akkumulation seit Modellstart mehr, daher keine De-Akkumulation.
# - 10fg: skalare Max-Böe im Intervall (m/s)
# - rain/sf: Niederschlag im Intervall (kg/m² ≈ mm)
# - tcc: Wolkenbedeckung in % → api.py rechnet auf Anteil 0–1 um
# - ssrd: Globalstrahlung als Intervallmittel (W/m²)
# - msl: Luftdruck auf Meeresniveau in Pa → api.py rechnet auf hPa um
# - snowlmt: Schneefallgrenze (m) — hochrelevant für österreichisches Bergland
# - cape: Convective Available Potential Energy (m²/s²) — quantitatives Gewitterpotenzial
NWP_PARAM_MAP = {
    "2t":      "t2m",
    "2r":      "rh2m",
    "10u":     "u10m",
    "10v":     "v10m",
    "10fg":    "wind_gust_speed",
    "rain":    "rain_acc",
    "sf":      "snow_acc",
    "tcc":     "tcc",
    "ssrd":    "grad",
    "sy":      "sy",
    "snowlmt": "snowlmt",
    "cape":    "cape",
    "msl":     "pressure",
}
NWP_PARAMS = ",".join(NWP_PARAM_MAP)

# Ensemble: Median-Perzentil (_p50) derselben Größen. Das Ensemble liefert
# kein Wettersymbol (sy).
ENSEMBLE_PARAM_MAP = {
    f"{name}_p50": internal
    for name, internal in NWP_PARAM_MAP.items()
    if name != "sy"
}
ENSEMBLE_PARAMS = ",".join(ENSEMBLE_PARAM_MAP)

# Vorhersageparameter (Nowcast)
NOWCAST_PARAMS = "t2m,rh2m,ff,dd,fx,rr,pt"

# Open-Meteo (daily forecast tail extension)
CONF_ENABLE_OPEN_METEO = "enable_open_meteo"
CONF_OPEN_METEO_FORECAST_DAYS = "open_meteo_forecast_days"
DATA_OPEN_METEO_DAILY = "open_meteo_daily"
OPEN_METEO_API_BASE = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_UPDATE_INTERVAL = 60   # minutes
OPEN_METEO_FORECAST_DAYS = 16     # API buffer — always request 16 days regardless of display setting
OPEN_METEO_FORECAST_DAYS_MIN = 3
OPEN_METEO_FORECAST_DAYS_MAX = 14
OPEN_METEO_FORECAST_DAYS_DEFAULT = 7
OPEN_METEO_MODEL = "geosphere_seamless"
OPEN_METEO_DAY_COVERAGE_HOUR = 17  # local hour; GeoSphere days reaching this threshold are considered complete
OPEN_METEO_ATTRIBUTION = "Daily forecast extension by Open-Meteo (CC-BY 4.0)"

OPEN_METEO_DAILY_PARAMS = (
    "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,"
    "precipitation_sum,precipitation_probability_max,wind_speed_10m_max,"
    "wind_gusts_10m_max,wind_direction_10m_dominant,relative_humidity_2m_mean,"
    "cloud_cover_mean,pressure_msl_mean,dew_point_2m_mean,uv_index_max,"
    "cape_max,shortwave_radiation_sum,sunshine_duration,sunrise,sunset,"
    "precipitation_hours"
)

# WMO code → HA weather condition (copied from homeassistant/components/open_meteo/const.py)
WMO_TO_HA_CONDITION_MAP: dict[int, str] = {
    0: "sunny",
    1: "sunny",
    2: "partlycloudy",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "rainy",
    53: "rainy",
    55: "pouring",
    56: "rainy",
    57: "rainy",
    61: "rainy",
    63: "rainy",
    65: "pouring",
    66: "rainy",
    67: "pouring",
    71: "snowy",
    73: "snowy",
    75: "snowy",
    77: "snowy",
    80: "rainy",
    81: "rainy",
    82: "pouring",
    85: "snowy",
    86: "snowy",
    # WMO 95/96/99 all imply precipitation by definition (rain, snow, or hail).
    # Using "lightning-rainy" matches GeoSphere sy codes 26–32 and avoids an
    # icon jump at the GeoSphere→Open-Meteo boundary. Intentional deviation
    # from the official HA open_meteo integration which uses "lightning".
    95: "lightning-rainy",
    96: "lightning-rainy",
    99: "lightning-rainy",
}

