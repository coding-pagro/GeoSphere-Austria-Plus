"""Open-Meteo API client – daily forecast extension."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import aiohttp
from aiohttp import ClientTimeout

from .const import (
    OPEN_METEO_API_BASE,
    OPEN_METEO_DAILY_PARAMS,
    OPEN_METEO_FORECAST_DAYS,
    OPEN_METEO_MODEL,
    WMO_TO_HA_CONDITION_MAP,
)


async def fetch_open_meteo_daily(
    session: aiohttp.ClientSession,
    lat: float,
    lon: float,
) -> list[dict[str, Any]]:
    """Return a list of per-day HA-Forecast-shaped dicts for up to 16 days."""
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "models": OPEN_METEO_MODEL,
        "forecast_days": OPEN_METEO_FORECAST_DAYS,
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
        "wind_speed_unit": "ms",
        "daily": OPEN_METEO_DAILY_PARAMS,
    }

    async with session.get(
        OPEN_METEO_API_BASE,
        params=params,
        timeout=ClientTimeout(total=30),
    ) as response:
        response.raise_for_status()
        data: dict[str, Any] = await response.json()

    today = date.today()
    daily = data["daily"]
    times: list[str] = daily["time"]
    result: list[dict[str, Any]] = []

    for i, day_str in enumerate(times):
        entry_date = date.fromisoformat(day_str)
        if entry_date < today:
            continue

        dt_utc = datetime(entry_date.year, entry_date.month, entry_date.day, tzinfo=timezone.utc)

        def _v(key: str, idx: int = i) -> Any:
            arr = daily.get(key)
            if arr is None or idx >= len(arr):
                return None
            return arr[idx]

        weather_code = _v("weather_code")
        if weather_code is not None:
            condition = WMO_TO_HA_CONDITION_MAP.get(int(weather_code), "partlycloudy")
        else:
            condition = "partlycloudy"

        entry: dict[str, Any] = {
            "datetime": dt_utc.isoformat(),
            "condition": condition,
            "is_daytime": True,
        }

        _put(entry, "native_temperature", _v("temperature_2m_max"))
        _put(entry, "native_templow", _v("temperature_2m_min"))
        _put(entry, "native_apparent_temperature", _v("apparent_temperature_max"))
        _put(entry, "native_precipitation", _v("precipitation_sum"))
        _put(entry, "precipitation_probability", _v("precipitation_probability_max"))
        _put(entry, "native_wind_speed", _v("wind_speed_10m_max"))
        _put(entry, "native_wind_gust_speed", _v("wind_gusts_10m_max"))
        _put(entry, "wind_bearing", _v("wind_direction_10m_dominant"))
        _put(entry, "humidity", _v("relative_humidity_2m_mean"))
        _put(entry, "cloud_coverage", _v("cloud_cover_mean"))
        _put(entry, "native_pressure", _v("pressure_msl_mean"))
        _put(entry, "native_dew_point", _v("dew_point_2m_mean"))
        _put(entry, "uv_index", _v("uv_index_max"))
        _put(entry, "cape", _v("cape_max"))
        _put(entry, "solar_radiation", _v("shortwave_radiation_sum"))
        _put(entry, "sunshine_duration", _v("sunshine_duration"))
        _put(entry, "sunrise", _v("sunrise"))
        _put(entry, "sunset", _v("sunset"))
        _put(entry, "precipitation_hours", _v("precipitation_hours"))

        result.append(entry)

    return result


def _put(entry: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        entry[key] = value
