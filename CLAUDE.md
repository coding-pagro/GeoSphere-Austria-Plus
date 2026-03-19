# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**GeoSphere Austria Plus** is a Home Assistant custom integration that fetches weather data from the Austrian [GeoSphere DataHub API](https://dataset.api.hub.geosphere.at/v1) (no API key required). It exposes current conditions, hourly (48h), and daily (7-day) forecasts via the Home Assistant `WeatherEntity` platform.

Installation is via HACS. There are no build steps, no external Python dependencies beyond Home Assistant's built-in libraries, and no test suite.

## Architecture

All integration code lives in `custom_components/geosphere_austria_plus/`.

### Data Flow

1. User configures a **TAWES station ID** (e.g. `11035` for Vienna) and a **forecast model** in `config_flow.py`
2. `__init__.py` creates two coordinators and registers the weather entity
3. **`GeoSphereCurrentCoordinator`** (`coordinator.py`) — fetches real-time TAWES station data every **10 minutes**
4. **`GeoSphereForecastCoordinator`** (`coordinator.py`) — fetches NWP forecast for the station's coordinates every **60 minutes**
5. **`GeoSphereWeatherEntity`** (`weather.py`) — derives HA weather conditions from TAWES data and builds forecast objects

### Key Files

| File | Responsibility |
|------|---------------|
| `api.py` | Async aiohttp client for GeoSphere DataHub API |
| `coordinator.py` | Two `DataUpdateCoordinator` subclasses |
| `weather.py` | `WeatherEntity` — condition logic, forecast building |
| `config_flow.py` | Config UI, station validation |
| `const.py` | API endpoints, parameter names, condition thresholds |

### Weather Condition Derivation

**Current conditions** (from TAWES parameters, priority order):
- Heavy rain: RR > 1.0 mm/10 min → `pouring`
- Rain: RR > 0.2 mm/10 min → `rainy`
- Snow+rain mix → `snowy-rainy`
- Snow: SH > 0 → `snowy`
- Fog: RF > 97% AND FF < 2 m/s → `fog`
- Overcast: based on SO (sunshine duration)
- Windy: FX above threshold
- Default: `sunny` / `clear-night`

**Forecast conditions** (from NWP model output): derived from `tcc` (cloud cover), `rain_acc`/`snow_acc` (precipitation), and `u10m`/`v10m` (wind components).

### API Endpoints

- **TAWES (current):** `GET /station/current/tawes-v1-10min?station_ids=<id>&parameters=...`
- **NWP forecast:** `GET /forecast/nwp/nowcast-v1-15min?lat=...&lon=...&parameters=...` (endpoint varies by model)
- Station metadata (coordinates) is retrieved from TAWES response and used for forecast queries.

### Forecast Models

| Model | Resolution | Update |
|-------|-----------|--------|
| NWP (default) | 1h / 2.5 km | Hourly |
| Ensemble | 1h / 2.5 km | Hourly |
| Nowcast | 15 min / 1 km | Sub-hourly |

## Translations

UI strings are in `strings.json` (German source) and mirrored in `translations/de.json` and `translations/en.json`. All three files must be kept in sync when adding new config fields or error keys.
