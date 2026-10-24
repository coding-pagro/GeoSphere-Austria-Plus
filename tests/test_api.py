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

    def test_empty_param_data_skips_key(self):
        """Station liefert den Parameter-Slot ohne Messwerte (z.B. TB1 an
        Stationen ohne Bodensonde) → Key wird gar nicht gesetzt, damit der
        Sensor 'unavailable' zeigt statt 'unknown'."""
        api = _make_api()
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 48.21]},
                    "properties": {
                        "parameters": {
                            "TL": {"data": [12.0]},
                            "TB1": {"data": []},  # no soil probe at this station
                        }
                    },
                }
            ]
        }
        result = api._parse_station_geojson(data, "11035")
        assert result["TL"] == 12.0
        assert "TB1" not in result

    def test_explicit_none_value_kept(self):
        """values[-1] == None (transient measurement gap, array non-empty)
        → Key is set with value None → Sensor shows 'unknown' rather than
        flipping to 'unavailable'."""
        api = _make_api()
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [16.37, 48.21]},
                    "properties": {"parameters": {"TL": {"data": [12.0, None]}}},
                }
            ]
        }
        result = api._parse_station_geojson(data, "11035")
        assert "TL" in result
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

    def test_logs_warning_when_parameter_message_but_no_brace_set(self, caplog):
        """API-Änderung erkennen: 'Parameter' im Detail aber kein {…}-Set."""
        from custom_components.geosphere_austria_plus.api import GeoSphereApi
        import logging
        caplog.set_level(logging.WARNING, logger="custom_components.geosphere_austria_plus.api")
        result = GeoSphereApi._extract_missing_params(
            "Parameter SH is not available (new API error format!)"
        )
        assert result == set()
        # Eine Warnung muss aufgetaucht sein, die den Detail-String enthält.
        assert any(
            "parameter" in r.message.lower() and "new api error format" in r.message.lower()
            for r in caplog.records
        )

    def test_no_log_when_detail_is_unrelated(self, caplog):
        """Allgemeine 400er ohne Parameter-Bezug dürfen NICHT als Regex-Bruch geloggt werden."""
        from custom_components.geosphere_austria_plus.api import GeoSphereApi
        import logging
        caplog.set_level(logging.WARNING, logger="custom_components.geosphere_austria_plus.api")
        result = GeoSphereApi._extract_missing_params("Invalid station id")
        assert result == set()
        assert caplog.records == []


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
            **{"2t": [10.0]},
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        result = await api.get_forecast(48.21, 16.37, "nwp-v2-1h-1km")
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
            await api.get_forecast(48.21, 16.37, "nwp-v2-1h-1km")

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

    async def test_nwp_model_uses_v2_params(self):
        """NWP v2 requests the GRIB short names incl. sy, snowlmt, cape and msl."""
        payload = {"features": [{"properties": {"parameters": {}}}]}
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        await api.get_forecast(48.21, 16.37, "nwp-v2-1h-1km")

        url_called = session.get.call_args[0][0]
        assert "/timeseries/forecast/nwp-v2-1h-1km?" in url_called
        params = url_called.split("parameters=")[1].split("&")[0].split(",")
        assert params == [
            "2t", "2r", "10u", "10v", "10fg", "rain", "sf", "tcc",
            "ssrd", "sy", "snowlmt", "cape", "msl",
        ]

    async def test_nwp_model_normalizes_names_and_units(self):
        """v2-Namen → interne Namen; tcc % → 0–1, msl Pa → hPa, Rest unverändert."""
        payload = _make_forecast_payload(
            ["2024-06-01T12:00:00Z"],
            **{
                "2t": [12.5], "2r": [51.5], "10u": [5.3], "10v": [-1.8],
                "10fg": [11.5], "rain": [0.4], "sf": [0.1], "tcc": [91.5],
                "ssrd": [395.5], "sy": [5.0], "snowlmt": [1271.1],
                "cape": [0.8], "msl": [101793.85],
            },
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))

        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "nwp-v2-1h-1km")

        assert result[0] == {
            "datetime": "2024-06-01T12:00:00Z",
            "t2m": 12.5,
            "rh2m": 51.5,
            "u10m": 5.3,
            "v10m": -1.8,
            "wind_gust_speed": 11.5,
            "rain_acc": 0.4,
            "snow_acc": 0.1,
            "tcc": pytest.approx(0.915),
            "grad": 395.5,
            "sy": 5.0,
            "snowlmt": 1271.1,
            "cape": 0.8,
            "pressure": 1017.9,
        }

    async def test_nwp_precip_and_radiation_not_deaccumulated(self):
        """v2 liefert rain/sf/ssrd als Intervallwerte — sie werden unverändert übernommen.

        Würde noch wie bei v1 de-akkumuliert, ergäbe entry[2] ein geklemmtes
        Delta (0.3 - 1.2 → 0.0) statt 0.3.
        """
        payload = _make_forecast_payload(
            ["2024-06-01T00:00:00Z", "2024-06-01T01:00:00Z", "2024-06-01T02:00:00Z"],
            rain=[0.5, 1.2, 0.3],
            sf=[2.0, 0.5, 1.8],
            ssrd=[100.0, 300.0, 50.0],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))

        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "nwp-v2-1h-1km")

        assert [e["rain_acc"] for e in result] == [0.5, 1.2, 0.3]
        assert [e["snow_acc"] for e in result] == [2.0, 0.5, 1.8]
        assert [e["grad"] for e in result] == [100.0, 300.0, 50.0]

    async def test_ensemble_model_uses_percentile_params(self):
        """Ensemble v2 requests the _p50 variants of all NWP params except sy."""
        payload = {"features": [{"properties": {"parameters": {}}}]}
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))

        await GeoSphereApi(session).get_forecast(48.21, 16.37, "ensemble-v2-1h-1km")

        url_called = session.get.call_args[0][0]
        params = url_called.split("parameters=")[1].split("&")[0].split(",")
        assert all(p.endswith("_p50") for p in params)
        assert "sy_p50" not in params
        assert {"2t_p50", "2r_p50", "10u_p50", "10fg_p50", "tcc_p50", "ssrd_p50", "msl_p50"} <= set(params)

    async def test_ensemble_model_normalizes_names_and_units(self):
        """Ensemble _p50-Namen werden auf dieselben internen Namen wie NWP abgebildet."""
        payload = _make_forecast_payload(
            ["2024-06-01T12:00:00Z"],
            **{
                "2t_p50": [12.2], "2r_p50": [53.2], "10u_p50": [5.0], "10v_p50": [-1.4],
                "10fg_p50": [11.5], "rain_p50": [0.5], "sf_p50": [0.0], "tcc_p50": [52.5],
                "ssrd_p50": [345.2], "snowlmt_p50": [1128.0], "cape_p50": [0.6],
                "msl_p50": [101834.03],
            },
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))

        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "ensemble-v2-1h-1km")

        assert result[0]["t2m"] == 12.2
        assert result[0]["rh2m"] == 53.2
        assert result[0]["u10m"] == 5.0
        assert result[0]["v10m"] == -1.4
        assert result[0]["wind_gust_speed"] == 11.5
        assert result[0]["rain_acc"] == 0.5
        assert result[0]["snow_acc"] == 0.0
        assert result[0]["tcc"] == pytest.approx(0.525)
        assert result[0]["grad"] == 345.2
        assert result[0]["snowlmt"] == 1128.0
        assert result[0]["cape"] == 0.6
        assert result[0]["pressure"] == 1018.3
        assert "sy" not in result[0]

    async def test_ensemble_precip_not_deaccumulated(self):
        """rain_p50/sf_p50 sind Intervallwerte und werden unverändert übernommen."""
        payload = _make_forecast_payload(
            ["2024-06-01T00:00:00Z", "2024-06-01T01:00:00Z", "2024-06-01T02:00:00Z"],
            rain_p50=[0.5, 1.2, 0.3],
            sf_p50=[2.0, 0.5, 1.8],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "ensemble-v2-1h-1km")

        assert [e["rain_acc"] for e in result] == [0.5, 1.2, 0.3]
        assert [e["snow_acc"] for e in result] == [2.0, 0.5, 1.8]

    async def test_missing_values_stay_none(self):
        """Fehlende tcc/msl-Werte bleiben None statt einen Fehler auszulösen."""
        payload = _make_forecast_payload(
            ["2024-06-01T00:00:00Z"],
            tcc=[None],
            msl=[None],
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "nwp-v2-1h-1km")

        assert result[0]["tcc"] is None
        assert result[0]["pressure"] is None
        assert result[0]["t2m"] is None

    async def test_retries_without_unknown_param_on_400(self):
        """400 mit unbekanntem Parameter → zweiter Versuch ohne diesen Parameter."""
        bad = AsyncMock()
        bad.status = 400
        bad.json = AsyncMock(
            return_value={"detail": "Parameters {'cape'} do not exist or access is denied"}
        )
        bad.__aenter__ = AsyncMock(return_value=bad)
        bad.__aexit__ = AsyncMock(return_value=False)
        good = _make_mock_response(_make_forecast_payload(["2024-06-01T00:00:00Z"], **{"2t": [5.0]}))
        good.status = 200

        session = MagicMock()
        session.get = MagicMock(side_effect=[bad, good])
        result = await GeoSphereApi(session).get_forecast(48.21, 16.37, "nwp-v2-1h-1km")

        second_url = session.get.call_args_list[1][0][0]
        assert "cape" not in second_url.split("parameters=")[1].split("&")[0].split(",")
        assert result[0]["t2m"] == 5.0
        assert result[0]["cape"] is None


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
