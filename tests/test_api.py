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

def _make_forecast_payload(timestamps, **param_data):
    """Erstellt eine realistische API-Antwort im tatsächlichen GeoJSON-Format."""
    return {
        "timestamps": timestamps,
        "features": [
            {
                "properties": {
                    "parameters": {
                        name: {"name": name, "unit": "", "data": values}
                        for name, values in param_data.items()
                    }
                }
            }
        ],
    }


class TestParseForecastGeoJSON:
    def test_basic_parsing(self):
        api = _make_api()
        data = _make_forecast_payload(
            ["2024-06-01T00:00:00Z", "2024-06-01T01:00:00Z", "2024-06-01T02:00:00Z"],
            t2m=[10.0, 11.0, 12.0],
            rain_acc=[0.0, 0.5, 1.0],
        )
        result = api._parse_forecast_geojson(data)
        assert len(result) == 3
        assert result[0]["datetime"] == "2024-06-01T00:00:00Z"
        assert result[0]["t2m"] == 10.0
        assert result[1]["rain_acc"] == 0.5
        assert result[2]["t2m"] == 12.0

    def test_empty_features_returns_empty_list(self):
        api = _make_api()
        assert api._parse_forecast_geojson({"timestamps": ["2024-06-01T00:00:00Z"], "features": []}) == []

    def test_missing_features_returns_empty_list(self):
        api = _make_api()
        assert api._parse_forecast_geojson({}) == []

    def test_no_timestamps_returns_empty_list(self):
        api = _make_api()
        data = {
            "features": [{"properties": {"parameters": {"t2m": {"data": [10.0]}}}}]
        }
        assert api._parse_forecast_geojson(data) == []

    def test_short_data_array_fills_none(self):
        api = _make_api()
        data = _make_forecast_payload(
            ["2024-06-01T00:00:00Z", "2024-06-01T01:00:00Z", "2024-06-01T02:00:00Z"],
            t2m=[10.0, 11.0, 12.0],
            rain_acc=[0.5],  # kürzer als timestamps
        )
        result = api._parse_forecast_geojson(data)
        assert result[0]["rain_acc"] == 0.5
        assert result[1]["rain_acc"] is None
        assert result[2]["rain_acc"] is None

    def test_multiple_params_all_mapped(self):
        api = _make_api()
        data = _make_forecast_payload(
            ["2024-06-01T00:00:00Z", "2024-06-01T01:00:00Z"],
            t2m=[5.0, 6.0],
            u10m=[1.0, 2.0],
        )
        result = api._parse_forecast_geojson(data)
        assert len(result) == 2
        assert result[0]["t2m"] == 5.0
        assert result[0]["u10m"] == 1.0
        assert result[1]["u10m"] == 2.0


# ---------------------------------------------------------------------------
# Async HTTP methods
# ---------------------------------------------------------------------------

class TestExtractMissingParams:
    def test_extracts_single_param(self):
        from custom_components.geosphere_austria_plus.api import GeoSphereApi
        result = GeoSphereApi._extract_missing_params("Parameters {'SH'} do not exist or access is denied")
        assert result == {"SH"}

    def test_extracts_multiple_params(self):
        from custom_components.geosphere_austria_plus.api import GeoSphereApi
        result = GeoSphereApi._extract_missing_params("Parameters {'SH', 'FX'} do not exist or access is denied")
        assert result == {"SH", "FX"}

    def test_no_braces_returns_empty(self):
        from custom_components.geosphere_austria_plus.api import GeoSphereApi
        assert GeoSphereApi._extract_missing_params("some other error") == set()


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

    async def test_retries_without_unsupported_params_on_400(self):
        """Station ohne FX/SH liefert beim ersten Versuch HTTP 400, beim zweiten 200."""
        success_payload = {
            "features": [
                {
                    "geometry": {"coordinates": [14.0, 47.5]},
                    "properties": {"parameters": {"TL": {"data": [12.0]}}},
                }
            ]
        }

        resp_400 = AsyncMock()
        resp_400.status = 400
        resp_400.json = AsyncMock(return_value={"detail": "Parameters {'SH', 'FX'} do not exist or access is denied"})
        resp_400.raise_for_status = MagicMock()
        resp_400.__aenter__ = AsyncMock(return_value=resp_400)
        resp_400.__aexit__ = AsyncMock(return_value=False)

        resp_200 = AsyncMock()
        resp_200.status = 200
        resp_200.json = AsyncMock(return_value=success_payload)
        resp_200.raise_for_status = MagicMock()
        resp_200.__aenter__ = AsyncMock(return_value=resp_200)
        resp_200.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.get = MagicMock(side_effect=[resp_400, resp_200])
        api = GeoSphereApi(session)

        result = await api.get_current("11389")
        assert result["TL"] == 12.0
        assert session.get.call_count == 2
        # Zweiter Aufruf darf SH und FX nicht enthalten
        second_url = session.get.call_args_list[1][0][0]
        assert "SH" not in second_url
        assert "FX" not in second_url


class TestGetForecast:
    async def test_success_returns_list(self):
        payload = _make_forecast_payload(
            ["2024-06-01T12:00:00Z"],
            t2m=[10.0],
        )
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

    async def test_ensemble_model_uses_percentile_params(self):
        """Ensemble model uses p50 percentile parameter names."""
        payload = _make_forecast_payload(
            ["2024-06-01T12:00:00Z"],
            t2m_p50=[12.0],
            rain_p50=[0.5],
            snow_p50=[0.0],
            rr_p50=[0.5],
            sundur_p50=[1800.0],
            cape_p50=[100.0],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        result = await api.get_forecast(48.21, 16.37, "ensemble-v1-1h-2500m")

        url_called = session.get.call_args[0][0]
        assert "t2m_p50" in url_called
        assert "t2m" not in url_called.split("parameters=")[1].split("&")[0].replace("t2m_p50", "")

        # Normalized names
        assert result[0]["t2m"] == 12.0
        assert result[0]["rain_acc"] == 0.5
        assert result[0]["snow_acc"] == 0.0
        # tcc derived from sundur: 1 - 1800/3600 = 0.5
        assert abs(result[0]["tcc"] - 0.5) < 1e-6

    async def test_ensemble_full_sunshine_gives_zero_cloud_cover(self):
        """sundur_p50 = 3600 s → tcc = 0.0 (clear sky)."""
        payload = _make_forecast_payload(
            ["2024-06-01T12:00:00Z"],
            t2m_p50=[15.0], rain_p50=[0.0], snow_p50=[0.0],
            rr_p50=[0.0], sundur_p50=[3600.0], cape_p50=[0.0],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "ensemble-v1-1h-2500m")
        assert result[0]["tcc"] == 0.0

    async def test_ensemble_no_sunshine_gives_full_cloud_cover(self):
        """sundur_p50 = 0 s → tcc = 1.0 (overcast)."""
        payload = _make_forecast_payload(
            ["2024-06-01T12:00:00Z"],
            t2m_p50=[8.0], rain_p50=[0.0], snow_p50=[0.0],
            rr_p50=[0.0], sundur_p50=[0.0], cape_p50=[0.0],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "ensemble-v1-1h-2500m")
        assert result[0]["tcc"] == 1.0


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


