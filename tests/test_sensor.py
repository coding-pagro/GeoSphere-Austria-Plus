"""Tests für TawesSensor – Metadaten und native_value."""
import pytest
from unittest.mock import MagicMock

from custom_components.geosphere_austria_plus.sensor import TawesSensor, SENSORS


ENTRY_ID = "abc123entryid"
LOCATION_NAME = "WIEN HOHE WARTE"


@pytest.fixture
def coordinator():
    coord = MagicMock()
    coord.data = {
        "TL": 18.5,
        "TP": 10.2,
        "RF": 63.0,
        "DD": 270.0,
        "FF": 3.5,
        "FX": 7.1,
        "P": 1013.2,
        "PRED": 1018.4,
        "RR": 0.0,
        "SO": 480.0,
        "SH": 0.0,
        "GLOW": 350.0,
    }
    return coord


def _make_sensor(coordinator, description):
    return TawesSensor(coordinator, description, ENTRY_ID, LOCATION_NAME)


# ---------------------------------------------------------------------------
# Beschreibungen
# ---------------------------------------------------------------------------

class TestSensorDescriptions:
    def test_sensor_count(self):
        assert len(SENSORS) == 12

    def test_all_have_param(self):
        for desc in SENSORS:
            assert desc.param, f"{desc.key} hat keinen TAWES-Parameter"

    def test_all_have_unit(self):
        for desc in SENSORS:
            assert desc.native_unit_of_measurement is not None, f"{desc.key} hat keine Einheit"

    def test_unique_keys(self):
        keys = [d.key for d in SENSORS]
        assert len(keys) == len(set(keys))

    def test_unique_params(self):
        params = [d.param for d in SENSORS]
        assert len(params) == len(set(params))


# ---------------------------------------------------------------------------
# Metadaten
# ---------------------------------------------------------------------------

class TestSensorMetadata:
    def test_unique_id(self, coordinator):
        desc = next(d for d in SENSORS if d.key == "temperature")
        sensor = _make_sensor(coordinator, desc)
        assert sensor._attr_unique_id == f"geosphere_plus_{ENTRY_ID}_temperature"

    def test_device_info_identifiers(self, coordinator):
        sensor = _make_sensor(coordinator, SENSORS[0])
        di = sensor._attr_device_info
        assert di["identifiers"] == {("geosphere_austria_plus", ENTRY_ID)}

    def test_device_info_name(self, coordinator):
        sensor = _make_sensor(coordinator, SENSORS[0])
        assert sensor._attr_device_info["name"] == LOCATION_NAME

    def test_has_entity_name(self, coordinator):
        sensor = _make_sensor(coordinator, SENSORS[0])
        assert sensor._attr_has_entity_name is True

    def test_attribution(self, coordinator):
        sensor = _make_sensor(coordinator, SENSORS[0])
        assert sensor._attr_attribution == "Data provided by GeoSphere Austria"


# ---------------------------------------------------------------------------
# native_value
# ---------------------------------------------------------------------------

class TestNativeValue:
    @pytest.mark.parametrize("key,param,expected", [
        ("temperature",     "TL",   18.5),
        ("dew_point",       "TP",   10.2),
        ("humidity",        "RF",   63.0),
        ("wind_direction",  "DD",   270.0),
        ("wind_speed",      "FF",   3.5),
        ("wind_gust",       "FX",   7.1),
        ("pressure",        "P",    1013.2),
        ("pressure_reduced","PRED", 1018.4),
        ("precipitation",   "RR",   0.0),
        ("sunshine_duration","SO",  480.0),
        ("snow_height",     "SH",   0.0),
        ("global_radiation","GLOW", 350.0),
    ])
    def test_value(self, coordinator, key, param, expected):
        desc = next(d for d in SENSORS if d.key == key)
        sensor = _make_sensor(coordinator, desc)
        assert sensor.native_value == expected

    def test_none_when_no_data(self, coordinator):
        coordinator.data = None
        sensor = _make_sensor(coordinator, SENSORS[0])
        assert sensor.native_value is None

    def test_none_when_param_missing(self, coordinator):
        coordinator.data = {}
        sensor = _make_sensor(coordinator, SENSORS[0])
        assert sensor.native_value is None
