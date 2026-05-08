"""Tests for open_meteo_api.fetch_open_meteo_daily."""
from __future__ import annotations

import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from custom_components.geosphere_austria_plus.open_meteo_api import fetch_open_meteo_daily
from custom_components.geosphere_austria_plus.const import (
    OPEN_METEO_API_BASE,
    OPEN_METEO_MODEL,
    OPEN_METEO_FORECAST_DAYS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(json_data: dict) -> aiohttp.ClientSession:
    """Return a mock aiohttp session that yields json_data from a GET."""
    response = AsyncMock()
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value=json_data)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock(spec=aiohttp.ClientSession)
    session.get = MagicMock(return_value=response)
    return session


def _make_daily_response(days: list[str], **vars: list) -> dict:
    """Build a minimal Open-Meteo response with the given per-day arrays."""
    return {
        "daily": {
            "time": days,
            **vars,
        }
    }


def _today_plus(offset: int) -> str:
    from datetime import timedelta
    return (date.today() + timedelta(days=offset)).isoformat()


# ---------------------------------------------------------------------------
# URL / query building
# ---------------------------------------------------------------------------

class TestRequestParameters:
    async def test_correct_base_url_called(self):
        session = _make_session(_make_daily_response([], weather_code=[]))
        session.get = MagicMock(return_value=session.get.return_value)

        await fetch_open_meteo_daily(session, 48.21, 16.37)

        url, *_ = session.get.call_args.args
        assert url == OPEN_METEO_API_BASE

    async def test_geosphere_seamless_model_in_params(self):
        session = _make_session(_make_daily_response([], weather_code=[]))

        await fetch_open_meteo_daily(session, 48.21, 16.37)

        params = session.get.call_args.kwargs["params"]
        assert params["models"] == OPEN_METEO_MODEL

    async def test_forecast_days_16_in_params(self):
        session = _make_session(_make_daily_response([], weather_code=[]))

        await fetch_open_meteo_daily(session, 48.21, 16.37)

        params = session.get.call_args.kwargs["params"]
        assert params["forecast_days"] == OPEN_METEO_FORECAST_DAYS

    async def test_unit_params(self):
        session = _make_session(_make_daily_response([], weather_code=[]))

        await fetch_open_meteo_daily(session, 48.21, 16.37)

        params = session.get.call_args.kwargs["params"]
        assert params["temperature_unit"] == "celsius"
        assert params["precipitation_unit"] == "mm"
        assert params["wind_speed_unit"] == "ms"

    async def test_lat_lon_passed(self):
        session = _make_session(_make_daily_response([], weather_code=[]))

        await fetch_open_meteo_daily(session, 47.5, 13.0)

        params = session.get.call_args.kwargs["params"]
        assert params["latitude"] == 47.5
        assert params["longitude"] == 13.0


# ---------------------------------------------------------------------------
# JSON parsing and field mapping
# ---------------------------------------------------------------------------

class TestJsonParsing:
    async def test_basic_entry_returned(self):
        days = [_today_plus(0)]
        session = _make_session(_make_daily_response(
            days,
            weather_code=[0],
            temperature_2m_max=[20.0],
            temperature_2m_min=[10.0],
        ))

        result = await fetch_open_meteo_daily(session, 48.21, 16.37)

        assert len(result) == 1
        assert result[0]["native_temperature"] == 20.0
        assert result[0]["native_templow"] == 10.0

    async def test_datetime_is_utc_midnight(self):
        days = [_today_plus(0)]
        session = _make_session(_make_daily_response(days, weather_code=[0]))

        result = await fetch_open_meteo_daily(session, 48.21, 16.37)

        dt = datetime.fromisoformat(result[0]["datetime"])
        assert dt.tzinfo == timezone.utc
        assert dt.hour == 0
        assert dt.minute == 0

    async def test_all_mapped_fields_present(self):
        days = [_today_plus(0)]
        session = _make_session(_make_daily_response(
            days,
            weather_code=[2],
            temperature_2m_max=[22.0],
            temperature_2m_min=[12.0],
            apparent_temperature_max=[21.0],
            precipitation_sum=[1.5],
            precipitation_probability_max=[40],
            wind_speed_10m_max=[5.0],
            wind_gusts_10m_max=[8.0],
            wind_direction_10m_dominant=[270],
            relative_humidity_2m_mean=[60.0],
            cloud_cover_mean=[50.0],
            pressure_msl_mean=[1013.0],
            dew_point_2m_mean=[8.0],
            uv_index_max=[4.0],
            cape_max=[200.0],
            shortwave_radiation_sum=[15.0],
            sunshine_duration=[28800.0],
            sunrise=["2025-01-01T07:45"],
            sunset=["2025-01-01T16:30"],
            precipitation_hours=[3.0],
        ))

        result = await fetch_open_meteo_daily(session, 48.21, 16.37)
        entry = result[0]

        assert entry["condition"] == "partlycloudy"
        assert entry["native_temperature"] == 22.0
        assert entry["native_templow"] == 12.0
        assert entry["native_apparent_temperature"] == 21.0
        assert entry["native_precipitation"] == 1.5
        assert entry["precipitation_probability"] == 40
        assert entry["native_wind_speed"] == 5.0
        assert entry["native_wind_gust_speed"] == 8.0
        assert entry["wind_bearing"] == 270
        assert entry["humidity"] == 60.0
        assert entry["cloud_coverage"] == 50.0
        assert entry["native_pressure"] == 1013.0
        assert entry["native_dew_point"] == 8.0
        assert entry["uv_index"] == 4.0
        assert entry["cape"] == 200.0
        assert entry["solar_radiation"] == 15.0
        assert entry["sunshine_duration"] == 28800.0
        assert entry["sunrise"] == "2025-01-01T07:45"
        assert entry["sunset"] == "2025-01-01T16:30"
        assert entry["precipitation_hours"] == 3.0
        assert entry["is_daytime"] is True

    async def test_missing_optional_fields_absent_from_entry(self):
        """Fields missing from the response are not set on the entry (no KeyError)."""
        days = [_today_plus(0)]
        session = _make_session(_make_daily_response(days, weather_code=[0]))

        result = await fetch_open_meteo_daily(session, 48.21, 16.37)

        for field in ("native_temperature", "native_precipitation", "uv_index"):
            assert field not in result[0]

    async def test_null_field_values_are_absent(self):
        """Array values of None must not be added to the entry."""
        days = [_today_plus(0)]
        session = _make_session(_make_daily_response(
            days,
            weather_code=[0],
            temperature_2m_max=[None],
        ))

        result = await fetch_open_meteo_daily(session, 48.21, 16.37)

        assert "native_temperature" not in result[0]

    async def test_multiple_days_all_returned(self):
        days = [_today_plus(i) for i in range(5)]
        session = _make_session(_make_daily_response(days, weather_code=[0] * 5))

        result = await fetch_open_meteo_daily(session, 48.21, 16.37)

        assert len(result) == 5


# ---------------------------------------------------------------------------
# WMO code mapping
# ---------------------------------------------------------------------------

class TestWmoMapping:
    @pytest.mark.parametrize("code,expected", [
        (0, "sunny"),
        (1, "sunny"),
        (2, "partlycloudy"),
        (3, "cloudy"),
        (45, "fog"),
        (48, "fog"),
        (51, "rainy"),
        (55, "pouring"),
        (56, "rainy"),
        (57, "rainy"),
        (61, "rainy"),
        (65, "pouring"),
        (66, "rainy"),
        (67, "pouring"),
        (71, "snowy"),
        (75, "snowy"),
        (77, "snowy"),
        (80, "rainy"),
        (82, "pouring"),
        (85, "snowy"),
        (86, "snowy"),
        (95, "lightning"),
        (96, "lightning"),
        (99, "lightning"),
    ])
    async def test_wmo_code_maps_correctly(self, code: int, expected: str):
        days = [_today_plus(0)]
        session = _make_session(_make_daily_response(days, weather_code=[code]))

        result = await fetch_open_meteo_daily(session, 48.21, 16.37)

        assert result[0]["condition"] == expected

    async def test_unknown_wmo_code_falls_back_to_partlycloudy(self):
        days = [_today_plus(0)]
        session = _make_session(_make_daily_response(days, weather_code=[9999]))

        result = await fetch_open_meteo_daily(session, 48.21, 16.37)

        assert result[0]["condition"] == "partlycloudy"

    async def test_null_weather_code_falls_back_to_partlycloudy(self):
        days = [_today_plus(0)]
        session = _make_session(_make_daily_response(days, weather_code=[None]))

        result = await fetch_open_meteo_daily(session, 48.21, 16.37)

        assert result[0]["condition"] == "partlycloudy"


# ---------------------------------------------------------------------------
# Past-date filter
# ---------------------------------------------------------------------------

class TestPastDateFilter:
    async def test_past_dates_excluded(self):
        from datetime import timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        days = [yesterday, _today_plus(0)]
        session = _make_session(_make_daily_response(days, weather_code=[0, 0]))

        result = await fetch_open_meteo_daily(session, 48.21, 16.37)

        assert len(result) == 1
        assert datetime.fromisoformat(result[0]["datetime"]).date() == date.today()

    async def test_all_past_returns_empty(self):
        from datetime import timedelta
        days = [(date.today() - timedelta(days=i)).isoformat() for i in range(1, 4)]
        session = _make_session(_make_daily_response(days, weather_code=[0] * 3))

        result = await fetch_open_meteo_daily(session, 48.21, 16.37)

        assert result == []


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------

class TestErrorPropagation:
    async def test_client_error_propagates(self):
        session = MagicMock(spec=aiohttp.ClientSession)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("network error"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        session.get = MagicMock(return_value=ctx)

        with pytest.raises(aiohttp.ClientError):
            await fetch_open_meteo_daily(session, 48.21, 16.37)

    async def test_raise_for_status_propagates(self):
        response = AsyncMock()
        response.raise_for_status = MagicMock(side_effect=aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=429
        ))
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock(spec=aiohttp.ClientSession)
        session.get = MagicMock(return_value=response)

        with pytest.raises(aiohttp.ClientResponseError):
            await fetch_open_meteo_daily(session, 48.21, 16.37)

    async def test_missing_daily_key_raises_key_error(self):
        """Response without 'daily' key propagates KeyError to the coordinator."""
        session = _make_session({"latitude": 48.21})  # no 'daily' key

        with pytest.raises(KeyError):
            await fetch_open_meteo_daily(session, 48.21, 16.37)
