# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**GeoSphere Austria Plus** is a Home Assistant custom integration that fetches weather data from the Austrian [GeoSphere DataHub API](https://dataset.api.hub.geosphere.at/v1) (no API key required). It exposes current conditions, hourly (48h), and daily (7-day) forecasts via the Home Assistant `WeatherEntity` platform.

Installation is via HACS. There are no build steps and no external Python dependencies beyond Home Assistant's built-in libraries. Tests live in `tests/` and run with `pytest`.

## Architecture

All integration code lives in `custom_components/geosphere_austria_plus/`.

### Data Flow

1. User configures location (lat/lon), an optional **TAWES station ID**, **0–3 forecast models**, and toggles for warnings and air quality in `config_flow.py`
2. `__init__.py` creates up to four coordinators (current, forecast×N, warnings, air quality) and registers the weather entity plus sensors
3. **`GeoSphereCurrentCoordinator`** (`coordinator.py`) — fetches real-time TAWES station data every **10 minutes**. Optional; only created if a station is configured.
4. **`GeoSphereForecastCoordinator`** (`coordinator.py`) — fetches forecast data for the configured coordinates every **60 minutes**. One instance per selected model (NWP / Ensemble / Nowcast).
5. **`GeoSphereWarningsCoordinator`** (`coordinator.py`) — fetches active weather warnings every **15 minutes** from `warnungen.zamg.at`.
6. **`GeoSphereAirQualityCoordinator`** (`coordinator.py`) — fetches the chemical-forecast model (`chem-v2-1h-3km`) every **60 minutes** for NO₂, O₃, PM10, PM2.5.
7. **`GeoSphereWeatherEntity`** (`weather.py`) — derives HA weather conditions from TAWES data (or first forecast point as fallback) and builds hourly/daily forecast objects.
8. **`TawesSensor`** / **`AirQualitySensor`** / **`AirQualityIndexSensor`** / **`GeoSphereWarningSensor`** (`sensor.py`) — register one HA sensor entity per relevant data point.

### Resilience layer

All four coordinators inherit a `_RetryMixin` that:
- caches the last-known-good response (`_last_good_data`) so sensors stay at their previous values instead of going `unavailable` on transient API errors
- on failure, schedules an accelerated retry on a Fibonacci backoff: **1 → 2 → 3 → 5 → 8 → 13 → 21 → 30 min** (capped at 30 min)
- on success, cancels any pending retry and resets the backoff counter

### Key Files

| File | Responsibility |
|------|---------------|
| `api.py` | Async aiohttp client. Handles three forecast models (NWP, Ensemble, Nowcast), parameter normalisation, de-accumulation of `grad`/`rain_acc`/`snow_acc` for NWP, and 400-error retry with parameter-removal fallback when an API model rejects an unknown parameter. |
| `coordinator.py` | Four `DataUpdateCoordinator` subclasses + `_RetryMixin` (Fibonacci-backoff retry on transient failures). |
| `weather.py` | `WeatherEntity`, condition logic (TAWES + symbol-code `sy`), hourly/daily forecast building, snowlmt/cape/solar_irradiance forecast attributes. |
| `sensor.py` | TAWES sensors (13 of them, including `soil_temperature_10cm`), air-quality sensors, AQI aggregation, warning-level sensor with all-warnings attributes. |
| `config_flow.py` | Config UI, options flow, station validation. |
| `const.py` | API endpoints, parameter lists for each model, ensemble→NWP normalisation map, AQI breakpoints, condition thresholds, polling intervals. |

### Weather Condition Derivation

**Current conditions** (from TAWES parameters, priority order):
- Snow+rain mix: SH > 0 AND RR ≥ 0.2 mm/10 min → `snowy-rainy`
- Heavy rain: RR ≥ 1.0 mm/10 min → `pouring`
- Rain: RR ≥ 0.2 mm/10 min → `rainy`
- Snow: SH > 0.1 cm → `snowy`
- Fog: RF ≥ 97% AND FF < 2 m/s → `fog`
- Overcast / partly cloudy: based on SO (sunshine duration)
- Windy: FF ≥ 10 m/s
- Default: `sunny` / `clear-night`

**Forecast conditions** (from NWP/Ensemble model output): the GeoSphere symbol code `sy` is preferred when present (32 codes covering thunderstorms, fog, all rain/snow/mix variants). Falls back to a derived chain over `tcc` (cloud cover), `rain_acc`/`snow_acc` (precipitation, already de-accumulated by `api.py`), and `u10m`/`v10m` (wind vector). Daily forecasts upgrade to `lightning-rainy` if any hourly entry carries a thunderstorm `sy` code (26–32).

### Forecast model parameter conventions

The three forecast models use different parameter naming and value semantics. `api.py` normalises everything so `weather.py` can treat them uniformly:

- **NWP (`nwp-v1-1h-2500m`)**: requests `t2m,mxt2m,mnt2m,rh2m,u10m,v10m,ugust,vgust,rain_acc,snow_acc,tcc,grad,sy,snowlmt,cape`. Both `grad` (Ws/m²) and `rain_acc`/`snow_acc` (mm) are cumulative since model start; `_deaccumulate_grad` and `_deaccumulate_precip` convert them to per-interval values.
- **Ensemble (`ensemble-v1-1h-2500m`)**: requests p50-percentile variants. Mapped to NWP names via `ENSEMBLE_PARAM_MAP`. Crucially, ensemble `rain_p50`/`snow_p50` are **per-period values** (mm/h), not cumulative — therefore **NOT** de-accumulated. `sundur_p50` (s/h sunshine) is converted to approximate `tcc` via `1 - sundur/3600`.
- **Nowcast (`nowcast-v1-15min-1km`)**: requests `t2m,rh2m,ff,dd,fx,rr,pt`. Wind components are reconstructed from scalar `ff`/`dd`. Precipitation type `pt` (WMO codes) splits the `rr` rate into the `rain_acc`/`snow_acc` slots that downstream code expects. `tcc` is unavailable (set to `None`).

### API Endpoints

- **TAWES (current):** `GET /station/current/tawes-v1-10min?station_ids=<id>&parameters=...`
- **NWP / Ensemble / Nowcast forecast:** `GET /timeseries/forecast/<model-id>?lat=...&lon=...&parameters=...`
- **Air quality:** `GET /timeseries/forecast/chem-v2-1h-3km?lat=...&lon=...&parameters=no2surf,o3surf,pm10surf,pm25surf`
- **Warnings:** `GET https://warnungen.zamg.at/wsapp/api/getWarningsForCoords?lon=...&lat=...&lang=de` (separate base URL, not the DataHub).
- Station metadata (coordinates) is retrieved from the TAWES response and used for forecast queries.

### Forecast Models

| Model | Resolution | Update | Use case |
|-------|-----------|--------|----------|
| NWP (default) | 1h / 2.5 km | Hourly | General-purpose forecast, 48–72h |
| Ensemble | 1h / 2.5 km | Hourly | Smoother averaged forecast (median percentile) |
| Nowcast | 15 min / 1 km | Sub-hourly | Radar-extrapolation precipitation, 2–3h horizon, no daily forecast |

### Forecast attributes

Beyond standard HA Forecast fields (`native_temperature`, `native_precipitation`, etc.), the integration adds these typed extras to each hourly/daily entry:

| Attribute | Unit | Hourly | Daily aggregation |
|-----------|------|--------|-------------------|
| `solar_irradiance` | W/m² | from `grad` (NWP/Ensemble) | — |
| `snow_altitude` | m | from `snowlmt` | day-minimum |
| `cape` | m²/s² | from `cape` | day-maximum |

## Testing

414+ unit tests in `tests/`, run with `pytest`. Test infrastructure mocks Home Assistant modules in `tests/conftest.py` (no real HA installation required). Key test files:

- `test_api.py` — HTTP client, parameter URL building, GeoJSON parsing, ensemble normalisation, deaccumulation.
- `test_coordinator.py` — Fibonacci-backoff retry, last-known-good caching.
- `test_weather_entity.py` — condition derivation, hourly/daily forecast building, all forecast attributes (snow_altitude, cape, solar_irradiance, wind gust).
- `test_sensor.py` — sensor descriptions, native_value extraction.
- `test_conditions.py` — pure `nwp_to_condition` and `sy_to_condition` logic.
- `test_air_quality.py` — AQI aggregation, EU-index breakpoints.
- `test_warnings.py` — warnings parser, level aggregation.
- `test_init.py` — entry setup, options-flow data flow.
- `test_config_flow.py` — config UI, station validation.

## Translations

UI strings are in `strings.json` (English source, HA convention) and mirrored in `translations/de.json` and `translations/en.json`. All three files must be kept in sync when adding new config/options fields, sensor translation keys, or error keys.
