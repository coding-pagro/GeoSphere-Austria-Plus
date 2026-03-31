"""Tests für Luftqualitäts-API-Parsing, AirQualitySensor und AirQualityIndexSensor."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

import aiohttp

from custom_components.geosphere_austria_plus.api import GeoSphereApi, GeoSphereApiError
from custom_components.geosphere_austria_plus.sensor import (
    AirQualitySensor,
    AirQualityIndexSensor,
    AirQualitySensorDescription,
    AIR_QUALITY_SENSORS,
    _compute_aqi_level,
)
from custom_components.geosphere_austria_plus.const import AQI_BREAKPOINTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIMESTAMPS = [
    f"2026-03-31T{h:02d}:00:00+00:00" for h in range(8, 8 + 30)
]

_SAMPLE_RESPONSE = {
    "timestamps": _TIMESTAMPS,
    "features": [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [16.37, 48.21]},
        "properties": {
            "parameters": {
                "no2surf":  {"name": "NO2",  "unit": "ug m-3", "data": [i * 1.0 for i in range(30)]},
                "o3surf":   {"name": "O3",   "unit": "ug m-3", "data": [50.0 + i for i in range(30)]},
                "pm10surf": {"name": "PM10", "unit": "ug m-3", "data": [5.0 + i * 0.5 for i in range(30)]},
                "pm25surf": {"name": "PM25", "unit": "ug m-3", "data": [3.0 + i * 0.3 for i in range(30)]},
            }
        },
    }],
}


def _make_mock_response(json_data, *, status: int = 200):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data
    return coord


def _make_aq_sensor(param: str, data=None) -> AirQualitySensor:
    description = next(d for d in AIR_QUALITY_SENSORS if d.param == param)
    return AirQualitySensor(
        coordinator=_make_coordinator(data),
        description=description,
        entry_id="test_entry_id",
        location_name="WIEN HOHE WARTE",
    )


def _make_aqi_sensor(data=None) -> AirQualityIndexSensor:
    return AirQualityIndexSensor(
        coordinator=_make_coordinator(data),
        entry_id="test_entry_id",
        location_name="WIEN HOHE WARTE",
    )


def _make_aq_data(no2=1.0, o3=50.0, pm10=5.0, pm25=3.0):
    return {
        "timestamps": _TIMESTAMPS,
        "no2surf":  [no2],
        "o3surf":   [o3],
        "pm10surf": [pm10],
        "pm25surf": [pm25],
    }


# ---------------------------------------------------------------------------
# GeoSphereApi.get_air_quality – Parsing
# ---------------------------------------------------------------------------

class TestGetAirQuality:
    async def test_parses_all_parameters(self):
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(_SAMPLE_RESPONSE))
        api = GeoSphereApi(session)

        result = await api.get_air_quality(48.21, 16.37)

        assert "no2surf" in result
        assert "o3surf" in result
        assert "pm10surf" in result
        assert "pm25surf" in result

    async def test_timestamps_preserved(self):
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(_SAMPLE_RESPONSE))
        api = GeoSphereApi(session)

        result = await api.get_air_quality(48.21, 16.37)

        assert result["timestamps"] == _TIMESTAMPS

    async def test_data_arrays_aligned_with_timestamps(self):
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(_SAMPLE_RESPONSE))
        api = GeoSphereApi(session)

        result = await api.get_air_quality(48.21, 16.37)

        assert len(result["no2surf"]) == len(_TIMESTAMPS)
        assert result["no2surf"][0] == 0.0
        assert result["o3surf"][0] == 50.0

    async def test_empty_features_returns_timestamps_only(self):
        payload = {"timestamps": _TIMESTAMPS, "features": []}
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        result = await api.get_air_quality(48.21, 16.37)

        assert result == {"timestamps": _TIMESTAMPS}

    async def test_http_error_raises_api_error(self):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("timeout"))
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=resp)
        api = GeoSphereApi(session)

        with pytest.raises(GeoSphereApiError, match="Schadstoffvorhersage"):
            await api.get_air_quality(48.21, 16.37)

    async def test_timeout_raises_api_error(self):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=resp)

        with pytest.raises(GeoSphereApiError):
            await GeoSphereApi(session).get_air_quality(48.21, 16.37)

    async def test_url_uses_lat_lon_format(self):
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(_SAMPLE_RESPONSE))
        api = GeoSphereApi(session)

        await api.get_air_quality(48.21, 16.37)

        url = session.get.call_args[0][0]
        assert "lat_lon=48.21,16.37" in url

    async def test_url_contains_chem_resource(self):
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(_SAMPLE_RESPONSE))
        api = GeoSphereApi(session)

        await api.get_air_quality(48.21, 16.37)

        url = session.get.call_args[0][0]
        assert "chem-v2-1h-3km" in url

    async def test_url_contains_all_parameters(self):
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(_SAMPLE_RESPONSE))
        api = GeoSphereApi(session)

        await api.get_air_quality(48.21, 16.37)

        url = session.get.call_args[0][0]
        for param in ("no2surf", "o3surf", "pm10surf", "pm25surf"):
            assert param in url


# ---------------------------------------------------------------------------
# _compute_aqi_level helper
# ---------------------------------------------------------------------------

class TestComputeAqiLevel:
    def test_below_first_threshold_is_level_1(self):
        assert _compute_aqi_level(10.0, "no2surf") == 1   # <40

    def test_at_first_threshold_is_level_2(self):
        assert _compute_aqi_level(40.0, "no2surf") == 2   # >=40, <90

    def test_at_last_threshold_is_level_6(self):
        assert _compute_aqi_level(340.0, "no2surf") == 6  # >=340

    def test_above_last_threshold_is_level_6(self):
        assert _compute_aqi_level(999.0, "no2surf") == 6

    def test_pm25_level_boundaries(self):
        assert _compute_aqi_level(5.0,  "pm25surf") == 1   # <10
        assert _compute_aqi_level(10.0, "pm25surf") == 2   # >=10, <20
        assert _compute_aqi_level(20.0, "pm25surf") == 3   # >=20, <25
        assert _compute_aqi_level(25.0, "pm25surf") == 4   # >=25, <50
        assert _compute_aqi_level(50.0, "pm25surf") == 5   # >=50, <75
        assert _compute_aqi_level(75.0, "pm25surf") == 6   # >=75

    def test_all_four_params_accepted(self):
        for param in AQI_BREAKPOINTS:
            assert _compute_aqi_level(0.0, param) == 1


# ---------------------------------------------------------------------------
# AirQualitySensor – native_value
# ---------------------------------------------------------------------------

class TestAirQualitySensorNativeValue:
    def test_returns_none_when_no_data(self):
        sensor = _make_aq_sensor("no2surf", data=None)
        assert sensor.native_value is None

    def test_returns_none_when_empty_values(self):
        sensor = _make_aq_sensor("no2surf", data={"timestamps": [], "no2surf": []})
        assert sensor.native_value is None

    def test_returns_first_value_rounded(self):
        sensor = _make_aq_sensor("no2surf", data={"timestamps": _TIMESTAMPS, "no2surf": [1.8765, 2.0]})
        assert sensor.native_value == 1.9

    def test_returns_exact_one_decimal(self):
        sensor = _make_aq_sensor("o3surf", data={"timestamps": _TIMESTAMPS, "o3surf": [55.0]})
        assert sensor.native_value == 55.0

    def test_missing_param_key_returns_none(self):
        # If param key is absent from data dict
        sensor = _make_aq_sensor("pm10surf", data={"timestamps": _TIMESTAMPS})
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# AirQualitySensor – extra_state_attributes
# ---------------------------------------------------------------------------

class TestAirQualitySensorAttributes:
    def test_empty_data_gives_empty_forecast(self):
        sensor = _make_aq_sensor("no2surf", data=None)
        assert sensor.extra_state_attributes == {"forecast": []}

    def test_forecast_contains_time_and_value_keys(self):
        sensor = _make_aq_sensor("no2surf", data={
            "timestamps": ["2026-03-31T08:00:00+00:00"],
            "no2surf": [1.8],
        })
        fc = sensor.extra_state_attributes["forecast"]
        assert len(fc) == 1
        assert fc[0]["time"] == "2026-03-31T08:00:00+00:00"
        assert fc[0]["value"] == 1.8

    def test_forecast_limited_to_24_entries(self):
        data = {
            "timestamps": [f"ts_{i}" for i in range(30)],
            "no2surf": [float(i) for i in range(30)],
        }
        sensor = _make_aq_sensor("no2surf", data=data)
        fc = sensor.extra_state_attributes["forecast"]
        assert len(fc) == 24

    def test_none_values_skipped(self):
        data = {
            "timestamps": ["t1", "t2", "t3"],
            "no2surf": [1.0, None, 3.0],
        }
        sensor = _make_aq_sensor("no2surf", data=data)
        fc = sensor.extra_state_attributes["forecast"]
        assert len(fc) == 2
        assert fc[0]["value"] == 1.0
        assert fc[1]["value"] == 3.0


# ---------------------------------------------------------------------------
# AirQualityIndexSensor – native_value
# ---------------------------------------------------------------------------

class TestAirQualityIndexSensorNativeValue:
    def test_returns_none_when_no_data(self):
        sensor = _make_aqi_sensor(data=None)
        assert sensor.native_value is None

    def test_good_air_quality_returns_level_1(self):
        sensor = _make_aqi_sensor(data=_make_aq_data(no2=1.0, o3=10.0, pm10=5.0, pm25=2.0))
        assert sensor.native_value == 1

    def test_max_of_all_parameters(self):
        # NO2 at level 3 (90–119), others at level 1
        sensor = _make_aqi_sensor(data=_make_aq_data(no2=95.0, o3=10.0, pm10=5.0, pm25=2.0))
        assert sensor.native_value == 3

    def test_pm25_drives_high_aqi(self):
        # PM2.5 at level 6 (>=75)
        sensor = _make_aqi_sensor(data=_make_aq_data(no2=1.0, o3=10.0, pm10=5.0, pm25=80.0))
        assert sensor.native_value == 6

    def test_returns_none_when_all_params_missing(self):
        sensor = _make_aqi_sensor(data={"timestamps": []})
        assert sensor.native_value is None

    def test_level_2_fair(self):
        # NO2=50 (level 2), rest good
        sensor = _make_aqi_sensor(data=_make_aq_data(no2=50.0, o3=10.0, pm10=5.0, pm25=2.0))
        assert sensor.native_value == 2


# ---------------------------------------------------------------------------
# AirQualityIndexSensor – icon
# ---------------------------------------------------------------------------

class TestAirQualityIndexSensorIcon:
    def test_icon_level_1_leaf(self):
        sensor = _make_aqi_sensor(data=_make_aq_data())
        assert sensor.icon == "mdi:leaf"

    def test_icon_level_2_leaf(self):
        sensor = _make_aqi_sensor(data=_make_aq_data(no2=50.0))
        assert sensor.icon == "mdi:leaf"

    def test_icon_level_3_alert_outline(self):
        # NO2=95 → level 3 (range 90–119)
        sensor = _make_aqi_sensor(data=_make_aq_data(no2=95.0))
        assert sensor.icon == "mdi:alert-circle-outline"

    def test_icon_level_4_alert_circle(self):
        # NO2=125 → level 4 (range 120–229)
        sensor = _make_aqi_sensor(data=_make_aq_data(no2=125.0))
        assert sensor.icon == "mdi:alert-circle"

    def test_icon_level_5_biohazard(self):
        sensor = _make_aqi_sensor(data=_make_aq_data(no2=341.0))
        assert sensor.icon == "mdi:biohazard"

    def test_icon_level_6_biohazard(self):
        sensor = _make_aqi_sensor(data=_make_aq_data(pm25=80.0))
        assert sensor.icon == "mdi:biohazard"

    def test_icon_no_data_defaults_leaf(self):
        sensor = _make_aqi_sensor(data=None)
        # native_value is None → or 1 → mdi:leaf
        assert sensor.icon == "mdi:leaf"


# ---------------------------------------------------------------------------
# AirQualityIndexSensor – extra_state_attributes
# ---------------------------------------------------------------------------

class TestAirQualityIndexSensorAttributes:
    def test_all_four_indices_in_attributes(self):
        sensor = _make_aqi_sensor(data=_make_aq_data())
        attrs = sensor.extra_state_attributes
        assert "no2_index" in attrs
        assert "o3_index" in attrs
        assert "pm10_index" in attrs
        assert "pm25_index" in attrs

    def test_per_param_index_correct(self):
        # NO2=50 → level 2, rest at level 1
        sensor = _make_aqi_sensor(data=_make_aq_data(no2=50.0, o3=10.0, pm10=5.0, pm25=2.0))
        attrs = sensor.extra_state_attributes
        assert attrs["no2_index"] == 2
        assert attrs["o3_index"] == 1
        assert attrs["pm10_index"] == 1
        assert attrs["pm25_index"] == 1

    def test_empty_data_returns_empty_attrs(self):
        sensor = _make_aqi_sensor(data=None)
        assert sensor.extra_state_attributes == {}

    def test_missing_param_not_in_attrs(self):
        # Only o3 available
        sensor = _make_aqi_sensor(data={"timestamps": _TIMESTAMPS, "o3surf": [10.0]})
        attrs = sensor.extra_state_attributes
        assert "o3_index" in attrs
        assert "no2_index" not in attrs


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

class TestAirQualitySensorMetadata:
    def test_unique_id_no2(self):
        sensor = _make_aq_sensor("no2surf")
        assert sensor._attr_unique_id == "geosphere_plus_test_entry_id_aq_no2surf"

    def test_unique_id_pm25(self):
        sensor = _make_aq_sensor("pm25surf")
        assert sensor._attr_unique_id == "geosphere_plus_test_entry_id_aq_pm25surf"

    def test_translation_key_no2(self):
        sensor = _make_aq_sensor("no2surf")
        assert sensor.entity_description.translation_key == "no2"

    def test_translation_key_aqi(self):
        sensor = _make_aqi_sensor()
        assert sensor._attr_translation_key == "aqi"

    def test_aqi_unique_id(self):
        sensor = _make_aqi_sensor()
        assert sensor._attr_unique_id == "geosphere_plus_test_entry_id_aqi"

    def test_device_info_identifiers(self):
        sensor = _make_aq_sensor("no2surf")
        assert sensor._attr_device_info["identifiers"] == {("geosphere_austria_plus", "test_entry_id")}

    def test_device_info_name(self):
        sensor = _make_aqi_sensor()
        assert sensor._attr_device_info["name"] == "WIEN HOHE WARTE"

    def test_four_aq_sensor_descriptions(self):
        params = {d.param for d in AIR_QUALITY_SENSORS}
        assert params == {"no2surf", "o3surf", "pm10surf", "pm25surf"}
