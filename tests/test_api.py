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
        """NWP model should include tcc, rain_acc, wind and grad params in URL."""
        payload = {"features": [{"properties": {"parameters": {}}}]}
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        await api.get_forecast(48.21, 16.37, "nwp-v1-1h-2500m")

        url_called = session.get.call_args[0][0]
        assert "tcc" in url_called
        assert "rain_acc" in url_called
        assert "u10m" in url_called
        assert "grad" in url_called
        assert "cape" not in url_called
        assert "msl" not in url_called

    async def test_ensemble_model_uses_percentile_params(self):
        """Ensemble model uses p50 percentile parameter names including grad_p50."""
        payload = _make_forecast_payload(
            ["2024-06-01T12:00:00Z"],
            t2m_p50=[12.0],
            rain_p50=[0.5],
            snow_p50=[0.0],
            sundur_p50=[1800.0],
            grad_p50=[250.0],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        result = await api.get_forecast(48.21, 16.37, "ensemble-v1-1h-2500m")

        url_called = session.get.call_args[0][0]
        assert "t2m_p50" in url_called
        assert "grad_p50" in url_called
        assert "rr_p50" not in url_called
        assert "cape_p50" not in url_called
        # Normalized names
        assert result[0]["t2m"] == 12.0
        assert result[0]["rain_acc"] == 0.5
        assert result[0]["snow_acc"] == 0.0
        # grad_p50 (W/m², direkt) → grad
        assert result[0]["grad"] == 250.0
        # tcc derived from sundur: 1 - 1800/3600 = 0.5
        assert abs(result[0]["tcc"] - 0.5) < 1e-6

    async def test_ensemble_full_sunshine_gives_zero_cloud_cover(self):
        """sundur_p50 = 3600 s → tcc = 0.0 (clear sky)."""
        payload = _make_forecast_payload(
            ["2024-06-01T12:00:00Z"],
            t2m_p50=[15.0], rain_p50=[0.0], snow_p50=[0.0], sundur_p50=[3600.0],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "ensemble-v1-1h-2500m")
        assert result[0]["tcc"] == 0.0

    async def test_ensemble_no_sunshine_gives_full_cloud_cover(self):
        """sundur_p50 = 0 s → tcc = 1.0 (overcast)."""
        payload = _make_forecast_payload(
            ["2024-06-01T12:00:00Z"],
            t2m_p50=[8.0], rain_p50=[0.0], snow_p50=[0.0], sundur_p50=[0.0],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "ensemble-v1-1h-2500m")
        assert result[0]["tcc"] == 1.0

    async def test_ensemble_precip_not_deaccumulated(self):
        """Bug 3.3: rain_p50/snow_p50 are per-period accumulations, not cumulative totals.

        _deaccumulate_precip must NOT be applied to ensemble output.
        Verify that per-period values are returned as-is, not delta-computed.
        """
        # Simulate three hourly values with non-monotonic per-period rainfall.
        # If de-accumulation were applied, entry[1] would give delta(1.2-0.5)=0.7
        # and entry[2] would clamp delta(0.3-1.2)=-0.9 → 0.0. Both are wrong.
        payload = _make_forecast_payload(
            ["2024-06-01T00:00:00Z", "2024-06-01T01:00:00Z", "2024-06-01T02:00:00Z"],
            t2m_p50=[10.0, 11.0, 12.0],
            rain_p50=[0.5, 1.2, 0.3],
            snow_p50=[0.0, 0.0, 0.0],
            sundur_p50=[0.0, 0.0, 0.0],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "ensemble-v1-1h-2500m")

        assert result[0]["rain_acc"] == pytest.approx(0.5)
        assert result[1]["rain_acc"] == pytest.approx(1.2)
        assert result[2]["rain_acc"] == pytest.approx(0.3)

    async def test_ensemble_snow_not_deaccumulated(self):
        """Bug 3.3: snow_p50 per-period accumulations are preserved without delta computation."""
        payload = _make_forecast_payload(
            ["2024-06-01T00:00:00Z", "2024-06-01T01:00:00Z", "2024-06-01T02:00:00Z"],
            t2m_p50=[0.0, -1.0, -2.0],
            rain_p50=[0.0, 0.0, 0.0],
            snow_p50=[2.0, 0.5, 1.8],
            sundur_p50=[0.0, 0.0, 0.0],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "ensemble-v1-1h-2500m")

        assert result[0]["snow_acc"] == pytest.approx(2.0)
        assert result[1]["snow_acc"] == pytest.approx(0.5)
        assert result[2]["snow_acc"] == pytest.approx(1.8)


class TestStationIdUrlEncoding:
    async def test_special_chars_in_station_id_are_encoded(self):
        """Leerzeichen und Sonderzeichen in der Station-ID werden URL-kodiert."""
        payload = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 48.21]},
                    "properties": {"parameters": {"TL": {"data": [15.0]}}},
                }
            ]
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        await api.get_current("11035 extra")
        url_called = session.get.call_args[0][0]
        assert "11035 extra" not in url_called
        assert "11035%20extra" in url_called

    async def test_ampersand_in_station_id_is_encoded(self):
        """& in der Station-ID darf den Query-String nicht aufbrechen."""
        payload = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 48.21]},
                    "properties": {"parameters": {}},
                }
            ]
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        await api.get_current("11035&evil=1")
        url_called = session.get.call_args[0][0]
        assert "11035%26evil%3D1" in url_called
        # der injizierte Parameter darf nicht als echter Query-Parameter auftauchen
        assert "evil=1" not in url_called.split("station_ids=")[1]

    async def test_plain_numeric_station_id_unchanged(self):
        """Reine Ziffern-IDs werden unverändert übergeben (kein unnötiges Encoding)."""
        payload = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 48.21]},
                    "properties": {"parameters": {}},
                }
            ]
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        await api.get_current("11035")
        url_called = session.get.call_args[0][0]
        assert "station_ids=11035" in url_called


class TestCoordinateValidation:
    def test_valid_coordinates_are_stored(self):
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

    def test_longitude_above_180_not_stored(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [999.0, 48.21]},
                    "properties": {"parameters": {}},
                }
            ]
        }
        result = api._parse_station_geojson(data, "11035")
        assert "_lon" not in result
        assert "_lat" not in result

    def test_latitude_above_90_not_stored(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 999.0]},
                    "properties": {"parameters": {}},
                }
            ]
        }
        result = api._parse_station_geojson(data, "11035")
        assert "_lon" not in result
        assert "_lat" not in result

    def test_negative_out_of_range_not_stored(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [-181.0, -91.0]},
                    "properties": {"parameters": {}},
                }
            ]
        }
        result = api._parse_station_geojson(data, "11035")
        assert "_lon" not in result
        assert "_lat" not in result

    def test_non_numeric_longitude_not_stored(self):
        api = _make_api()
        data = {
            "features": [
                {
                    "geometry": {"coordinates": ["not-a-number", 48.21]},
                    "properties": {"parameters": {}},
                }
            ]
        }
        result = api._parse_station_geojson(data, "11035")
        assert "_lon" not in result
        assert "_lat" not in result

    def test_altitude_still_extracted_with_valid_coords(self):
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

    def test_boundary_values_are_valid(self):
        """Grenzwerte ±180 lon und ±90 lat sind gültig."""
        api = _make_api()
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [180.0, 90.0]},
                    "properties": {"parameters": {}},
                }
            ]
        }
        result = api._parse_station_geojson(data, "test")
        assert result["_lon"] == 180.0
        assert result["_lat"] == 90.0


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



class TestNormalizeNowcastParams:
    def test_rain_type_1_goes_to_rain_acc(self):
        entries = [{"datetime": "2026-01-01T00:00:00Z", "rr": 2.0, "pt": 1,
                    "ff": 0.0, "dd": 0.0, "t2m": 5.0, "rh2m": 80.0}]
        result = GeoSphereApi._normalize_nowcast_params(entries)
        assert result[0]["rain_acc"] == 2.0
        assert result[0]["snow_acc"] == 0.0

    def test_snow_type_2_goes_to_snow_acc(self):
        entries = [{"datetime": "2026-01-01T00:00:00Z", "rr": 3.0, "pt": 2,
                    "ff": 0.0, "dd": 0.0, "t2m": -2.0, "rh2m": 90.0}]
        result = GeoSphereApi._normalize_nowcast_params(entries)
        assert result[0]["rain_acc"] == 0.0
        assert result[0]["snow_acc"] == 3.0

    def test_mixed_type_3_splits_50_50(self):
        entries = [{"datetime": "2026-01-01T00:00:00Z", "rr": 4.0, "pt": 3,
                    "ff": 0.0, "dd": 0.0, "t2m": 0.0, "rh2m": 95.0}]
        result = GeoSphereApi._normalize_nowcast_params(entries)
        assert result[0]["rain_acc"] == pytest.approx(2.0)
        assert result[0]["snow_acc"] == pytest.approx(2.0)

    def test_no_precip_type_0_gives_zeros(self):
        entries = [{"datetime": "2026-01-01T00:00:00Z", "rr": 0.0, "pt": 0,
                    "ff": 0.0, "dd": 0.0, "t2m": 10.0, "rh2m": 60.0}]
        result = GeoSphereApi._normalize_nowcast_params(entries)
        assert result[0]["rain_acc"] == 0.0
        assert result[0]["snow_acc"] == 0.0

    def test_type_255_no_precip(self):
        entries = [{"datetime": "2026-01-01T00:00:00Z", "rr": 1.0, "pt": 255,
                    "ff": 0.0, "dd": 0.0, "t2m": 10.0, "rh2m": 60.0}]
        result = GeoSphereApi._normalize_nowcast_params(entries)
        assert result[0]["rain_acc"] == 0.0
        assert result[0]["snow_acc"] == 0.0

    def test_wind_vector_reconstructed_from_speed_and_direction(self):
        import math
        # ff=10, dd=90° (East): u=-ff*sin(90°)=-10, v=-ff*cos(90°)=0
        entries = [{"datetime": "2026-01-01T00:00:00Z", "rr": 0.0, "pt": 255,
                    "ff": 10.0, "dd": 90.0, "t2m": 10.0, "rh2m": 60.0}]
        result = GeoSphereApi._normalize_nowcast_params(entries)
        assert result[0]["u10m"] == pytest.approx(-10.0, abs=1e-6)
        assert result[0]["v10m"] == pytest.approx(0.0, abs=1e-6)

    def test_tcc_is_always_none(self):
        entries = [{"datetime": "2026-01-01T00:00:00Z", "rr": 0.0, "pt": 0,
                    "ff": 0.0, "dd": 0.0, "t2m": 10.0, "rh2m": 60.0}]
        result = GeoSphereApi._normalize_nowcast_params(entries)
        assert result[0]["tcc"] is None

    def test_datetime_preserved(self):
        entries = [{"datetime": "2026-04-07T12:00:00Z", "rr": 0.0, "pt": 0,
                    "ff": 0.0, "dd": 0.0, "t2m": 10.0, "rh2m": 60.0}]
        result = GeoSphereApi._normalize_nowcast_params(entries)
        assert result[0]["datetime"] == "2026-04-07T12:00:00Z"

    def test_fx_mapped_to_wind_gust_speed(self):
        """fx (scalar gust speed) is mapped to wind_gust_speed in the normalized entry."""
        entries = [{"datetime": "2026-01-01T00:00:00Z", "rr": 0.0, "pt": 0,
                    "ff": 5.0, "dd": 0.0, "fx": 12.5, "t2m": 10.0, "rh2m": 60.0}]
        result = GeoSphereApi._normalize_nowcast_params(entries)
        assert result[0]["wind_gust_speed"] == pytest.approx(12.5)

    def test_wind_gust_speed_none_when_fx_absent(self):
        """Entries without fx produce wind_gust_speed=None."""
        entries = [{"datetime": "2026-01-01T00:00:00Z", "rr": 0.0, "pt": 0,
                    "ff": 5.0, "dd": 0.0, "t2m": 10.0, "rh2m": 60.0}]
        result = GeoSphereApi._normalize_nowcast_params(entries)
        assert result[0]["wind_gust_speed"] is None


class TestDeaccumulateGrad:
    """Tests für die NWP-Globalstrahlungs-Deakkumulation (Ws/m² → W/m²)."""

    def _entries(self, grad_values: list) -> list[dict]:
        return [{"datetime": f"2024-06-01T{i:02d}:00:00Z", "grad": v}
                for i, v in enumerate(grad_values)]

    def test_first_entry_divided_by_3600(self):
        """Erster Eintrag: akkumulierter Wert / 3600 = mittlere W/m²."""
        entries = self._entries([3600.0])
        GeoSphereApi._deaccumulate_grad(entries)
        assert entries[0]["grad"] == pytest.approx(1.0)

    def test_subsequent_entries_use_delta(self):
        """Folgeeinträge: (current - previous) / 3600."""
        entries = self._entries([0.0, 3600.0, 10800.0])
        GeoSphereApi._deaccumulate_grad(entries)
        assert entries[0]["grad"] == pytest.approx(0.0)
        assert entries[1]["grad"] == pytest.approx(1.0)   # (3600-0)/3600
        assert entries[2]["grad"] == pytest.approx(2.0)   # (10800-3600)/3600

    def test_negative_delta_clamped_to_zero(self):
        """Modell-Reset: negatives Delta wird auf 0 geklemmt."""
        entries = self._entries([7200.0, 3600.0])
        GeoSphereApi._deaccumulate_grad(entries)
        assert entries[0]["grad"] == pytest.approx(2.0)
        assert entries[1]["grad"] == pytest.approx(0.0)

    def test_none_grad_is_left_unchanged_and_resets_accumulator(self):
        """None-Einträge bleiben None; danach wird der Akkumulator zurückgesetzt."""
        entries = [
            {"datetime": "2024-06-01T00:00:00Z", "grad": 3600.0},
            {"datetime": "2024-06-01T01:00:00Z", "grad": None},
            {"datetime": "2024-06-01T02:00:00Z", "grad": 7200.0},
        ]
        GeoSphereApi._deaccumulate_grad(entries)
        assert entries[0]["grad"] == pytest.approx(1.0)
        assert entries[1]["grad"] is None
        # Nach dem Reset wird der dritte Eintrag wie ein Ersteintrag behandelt
        assert entries[2]["grad"] == pytest.approx(2.0)   # 7200/3600

    def test_modifies_entries_in_place(self):
        """_deaccumulate_grad gibt None zurück und ändert die Liste direkt."""
        entries = self._entries([3600.0])
        result = GeoSphereApi._deaccumulate_grad(entries)
        assert result is None
        assert entries[0]["grad"] == pytest.approx(1.0)

    def test_nwp_forecast_applies_deaccumulation(self):
        """get_forecast ruft _deaccumulate_grad für NWP-Modelle auf."""
        payload = _make_forecast_payload(
            ["2024-06-01T06:00:00Z", "2024-06-01T07:00:00Z"],
            t2m=[15.0, 16.0],
            grad=[0.0, 720000.0],   # 0 Ws/m² → 200 W/m² (720000/3600=200)
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            api.get_forecast(48.21, 16.37, "nwp-v1-1h-2500m")
        )
        assert result[0]["grad"] == pytest.approx(0.0)    # 0/3600
        assert result[1]["grad"] == pytest.approx(200.0)  # (720000-0)/3600


class TestDeaccumulatePrecip:
    """Tests für die NWP/Ensemble-Niederschlags-Deakkumulation (mm akkumuliert → mm/Zeitschritt)."""

    def _entries(self, rain_values: list, snow_values: list | None = None) -> list[dict]:
        if snow_values is None:
            snow_values = [0.0] * len(rain_values)
        return [
            {"datetime": f"2024-06-01T{i:02d}:00:00Z", "rain_acc": r, "snow_acc": s}
            for i, (r, s) in enumerate(zip(rain_values, snow_values))
        ]

    def test_first_entry_is_used_as_is(self):
        """Erster Eintrag: Akkumulationswert direkt übernehmen (kein Vorgänger bekannt)."""
        entries = self._entries([2.5])
        GeoSphereApi._deaccumulate_precip(entries)
        assert entries[0]["rain_acc"] == pytest.approx(2.5)

    def test_subsequent_entries_use_delta(self):
        """Folgeeinträge: Delta zum Vorgänger."""
        entries = self._entries([0.0, 2.0, 5.0, 5.5])
        GeoSphereApi._deaccumulate_precip(entries)
        assert entries[0]["rain_acc"] == pytest.approx(0.0)
        assert entries[1]["rain_acc"] == pytest.approx(2.0)   # 2.0 - 0.0
        assert entries[2]["rain_acc"] == pytest.approx(3.0)   # 5.0 - 2.0
        assert entries[3]["rain_acc"] == pytest.approx(0.5)   # 5.5 - 5.0

    def test_negative_delta_clamped_to_zero(self):
        """Modell-Reset: negatives Delta (Akkumulator-Reset) wird auf 0 geklemmt."""
        entries = self._entries([5.0, 2.0])
        GeoSphereApi._deaccumulate_precip(entries)
        assert entries[0]["rain_acc"] == pytest.approx(5.0)
        assert entries[1]["rain_acc"] == pytest.approx(0.0)

    def test_rain_and_snow_tracked_independently(self):
        """rain_acc und snow_acc werden unabhängig voneinander de-akkumuliert."""
        entries = self._entries([0.0, 3.0], snow_values=[0.0, 1.5])
        GeoSphereApi._deaccumulate_precip(entries)
        assert entries[1]["rain_acc"] == pytest.approx(3.0)
        assert entries[1]["snow_acc"] == pytest.approx(1.5)

    def test_none_rain_acc_resets_accumulator(self):
        """None-Einträge bleiben None; Akkumulator wird danach zurückgesetzt."""
        entries = [
            {"datetime": "2024-06-01T00:00:00Z", "rain_acc": 2.0, "snow_acc": 0.0},
            {"datetime": "2024-06-01T01:00:00Z", "rain_acc": None, "snow_acc": 0.0},
            {"datetime": "2024-06-01T02:00:00Z", "rain_acc": 4.0, "snow_acc": 0.0},
        ]
        GeoSphereApi._deaccumulate_precip(entries)
        assert entries[0]["rain_acc"] == pytest.approx(2.0)
        assert entries[1]["rain_acc"] is None
        assert entries[2]["rain_acc"] == pytest.approx(4.0)   # wie Ersteintrag nach Reset

    def test_modifies_entries_in_place(self):
        """_deaccumulate_precip gibt None zurück und ändert die Liste direkt."""
        entries = self._entries([1.0, 3.0])
        result = GeoSphereApi._deaccumulate_precip(entries)
        assert result is None
        assert entries[1]["rain_acc"] == pytest.approx(2.0)

    def test_nwp_forecast_deaccumulates_precipitation(self):
        """get_forecast de-akkumuliert rain_acc/snow_acc für NWP-Modelle."""
        payload = _make_forecast_payload(
            ["2024-06-01T06:00:00Z", "2024-06-01T07:00:00Z", "2024-06-01T08:00:00Z"],
            t2m=[15.0, 15.0, 15.0],
            rain_acc=[0.0, 2.0, 5.0],
            snow_acc=[0.0, 0.0, 1.0],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            api.get_forecast(48.21, 16.37, "nwp-v1-1h-2500m")
        )
        assert result[0]["rain_acc"] == pytest.approx(0.0)
        assert result[1]["rain_acc"] == pytest.approx(2.0)   # 2.0 - 0.0
        assert result[2]["rain_acc"] == pytest.approx(3.0)   # 5.0 - 2.0
        assert result[2]["snow_acc"] == pytest.approx(1.0)   # 1.0 - 0.0

