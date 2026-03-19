"""Tests for GeoSphereApi – parsing methods (sync) and HTTP methods (async)."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

import aiohttp

from custom_components.geosphere_austria_plus.api import GeoSphereApi, GeoSphereApiError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api() -> GeoSphereApi:
    return GeoSphereApi(session=MagicMock())


def _make_mock_response(json_data: dict, *, raise_for_status=None):
    """Return an async context manager mock that yields a response."""
    resp = AsyncMock()
    resp.json = AsyncMock(return_value=json_data)
    if raise_for_status:
        resp.raise_for_status = MagicMock(side_effect=raise_for_status)
    else:
        resp.raise_for_status = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# _parse_station_geojson
# ---------------------------------------------------------------------------

class TestParseStationGeoJSON:
    def test_returns_last_value_for_each_param(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 48.21, 200.0]},
                    "properties": {
                        "parameters": {
                            "TL": {"data": [11.0, 12.5]},
                            "RF": {"data": [75.0]},
                        }
                    },
                }
            ]
        }
        result = api._parse_station_geojson(data, "11035")
        assert result["TL"] == 12.5  # last value
        assert result["RF"] == 75.0

    def test_extracts_coordinates(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 48.21, 200.0]},
                    "properties": {"parameters": {}},
                }
            ]
        }
        result = api._parse_station_geojson(data, "11035")
        assert result["_lon"] == 16.37
        assert result["_lat"] == 48.21
        assert result["_alt"] == 200.0

    def test_no_altitude_in_coords(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 48.21]},
                    "properties": {"parameters": {}},
                }
            ]
        }
        result = api._parse_station_geojson(data, "11035")
        assert result["_lon"] == 16.37
        assert result["_lat"] == 48.21
        assert "_alt" not in result

    def test_empty_param_data_returns_none(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 48.21]},
                    "properties": {"parameters": {"TL": {"data": []}}},
                }
            ]
        }
        result = api._parse_station_geojson(data, "11035")
        assert result["TL"] is None

    def test_empty_features_raises(self):
        api = _make_api()
        with pytest.raises(GeoSphereApiError):
            api._parse_station_geojson({"features": []}, "11035")

    def test_missing_features_key_raises(self):
        api = _make_api()
        with pytest.raises(GeoSphereApiError):
            api._parse_station_geojson({}, "11035")


# ---------------------------------------------------------------------------
# _parse_forecast_geojson
# ---------------------------------------------------------------------------

class TestParseForecastGeoJSON:
    def test_basic_parsing(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "properties": {
                        "parameters": {
                            "t2m": {
                                "data": [10.0, 11.0, 12.0],
                                "datetimes": [
                                    "2024-06-01T00:00:00Z",
                                    "2024-06-01T01:00:00Z",
                                    "2024-06-01T02:00:00Z",
                                ],
                            },
                            "rain_acc": {"data": [0.0, 0.5, 1.0]},
                        }
                    }
                }
            ]
        }
        result = api._parse_forecast_geojson(data)
        assert len(result) == 3
        assert result[0]["datetime"] == "2024-06-01T00:00:00Z"
        assert result[0]["t2m"] == 10.0
        assert result[1]["rain_acc"] == 0.5
        assert result[2]["t2m"] == 12.0

    def test_empty_features_returns_empty_list(self):
        api = _make_api()
        assert api._parse_forecast_geojson({"features": []}) == []

    def test_missing_features_returns_empty_list(self):
        api = _make_api()
        assert api._parse_forecast_geojson({}) == []

    def test_param_without_datetimes_returns_empty_list(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "properties": {
                        "parameters": {
                            "t2m": {"data": [10.0]}
                            # no "datetimes" key
                        }
                    }
                }
            ]
        }
        assert api._parse_forecast_geojson(data) == []

    def test_short_data_array_fills_none(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "properties": {
                        "parameters": {
                            "t2m": {
                                "data": [10.0, 11.0, 12.0],
                                "datetimes": [
                                    "2024-06-01T00:00:00Z",
                                    "2024-06-01T01:00:00Z",
                                    "2024-06-01T02:00:00Z",
                                ],
                            },
                            "rain_acc": {"data": [0.5]},  # shorter than timestamps
                        }
                    }
                }
            ]
        }
        result = api._parse_forecast_geojson(data)
        assert result[0]["rain_acc"] == 0.5
        assert result[1]["rain_acc"] is None
        assert result[2]["rain_acc"] is None

    def test_timestamps_from_first_param_with_datetimes(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "properties": {
                        "parameters": {
                            "u10m": {"data": [1.0, 2.0]},  # no datetimes
                            "t2m": {
                                "data": [5.0, 6.0],
                                "datetimes": [
                                    "2024-06-01T00:00:00Z",
                                    "2024-06-01T01:00:00Z",
                                ],
                            },
                        }
                    }
                }
            ]
        }
        result = api._parse_forecast_geojson(data)
        assert len(result) == 2
        assert result[0]["datetime"] == "2024-06-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Async HTTP methods
# ---------------------------------------------------------------------------

class TestGetCurrent:
    async def test_success_calls_parse(self):
        payload = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 48.21, 200.0]},
                    "properties": {
                        "parameters": {"TL": {"data": [15.0]}}
                    },
                }
            ]
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        result = await api.get_current("11035")
        assert result["TL"] == 15.0
        assert result["_lat"] == 48.21

    async def test_http_error_raises_api_error(self):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(
            side_effect=aiohttp.ClientError("network failure")
        )
        resp.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.get = MagicMock(return_value=resp)
        api = GeoSphereApi(session)

        with pytest.raises(GeoSphereApiError, match="Fehler beim Abrufen aktueller"):
            await api.get_current("11035")

    async def test_timeout_raises_api_error(self):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
        resp.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.get = MagicMock(return_value=resp)
        api = GeoSphereApi(session)

        with pytest.raises(GeoSphereApiError):
            await api.get_current("11035")


class TestGetForecast:
    async def test_success_returns_list(self):
        payload = {
            "features": [
                {
                    "properties": {
                        "parameters": {
                            "t2m": {
                                "data": [10.0],
                                "datetimes": ["2024-06-01T12:00:00Z"],
                            }
                        }
                    }
                }
            ]
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        result = await api.get_forecast(48.21, 16.37, "nwp-v1-1h-2500m")
        assert isinstance(result, list)
        assert result[0]["t2m"] == 10.0

    async def test_http_error_raises_api_error(self):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(
            side_effect=aiohttp.ClientError("connection refused")
        )
        resp.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.get = MagicMock(return_value=resp)
        api = GeoSphereApi(session)

        with pytest.raises(GeoSphereApiError, match="Fehler beim Abrufen der Vorhersage"):
            await api.get_forecast(48.21, 16.37, "nwp-v1-1h-2500m")

    async def test_nowcast_model_uses_different_params(self):
        """Nowcast model should NOT include cape/msl in the URL params."""
        payload = {"features": [{"properties": {"parameters": {}}}]}
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        await api.get_forecast(48.21, 16.37, "nowcast-v1-15min-1km")

        url_called = session.get.call_args[0][0]
        assert "cape" not in url_called
        assert "msl" not in url_called

    async def test_nwp_model_uses_full_params(self):
        """NWP model should include cape in URL params."""
        payload = {"features": [{"properties": {"parameters": {}}}]}
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        await api.get_forecast(48.21, 16.37, "nwp-v1-1h-2500m")

        url_called = session.get.call_args[0][0]
        assert "cape" in url_called


class TestGetStations:
    async def test_parses_station_list(self):
        payload = {
            "stations": [
                {"id": 11035, "name": "Wien-Innere Stadt", "lat": 48.21, "lon": 16.37, "altitude": 171},
                {"id": 11036, "name": "Wien-Mariabrunn", "lat": 48.18, "lon": 16.26},
            ]
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        stations = await api.get_stations()
        assert len(stations) == 2
        assert stations[0]["id"] == "11035"
        assert stations[0]["name"] == "Wien-Innere Stadt"
        assert stations[0]["lat"] == 48.21
        assert stations[1]["altitude"] is None  # missing key defaults to None

    async def test_empty_station_list(self):
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response({"stations": []}))
        api = GeoSphereApi(session)

        assert await api.get_stations() == []


class TestValidateStation:
    async def test_valid_station_returns_true(self):
        payload = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 48.21]},
                    "properties": {"parameters": {"TL": {"data": [10.0]}}},
                }
            ]
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        assert await api.validate_station("11035") is True

    async def test_invalid_station_returns_false(self):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("404"))
        resp.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.get = MagicMock(return_value=resp)
        api = GeoSphereApi(session)

        assert await api.validate_station("99999") is False
