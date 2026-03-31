"""Tests für GeoSphereWarningSensor und get_warnings() API-Parsing."""
from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import aiohttp

from custom_components.geosphere_austria_plus.api import GeoSphereApi, GeoSphereApiError
from custom_components.geosphere_austria_plus.sensor import GeoSphereWarningSensor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_coordinator(warnings: list | None = None):
    coord = MagicMock()
    coord.data = warnings
    return coord


def _make_sensor(warnings: list | None = None) -> GeoSphereWarningSensor:
    return GeoSphereWarningSensor(
        coordinator=_make_coordinator(warnings),
        station_id="11035",
        station_name="WIEN HOHE WARTE",
    )


def _make_mock_response(json_data, *, status: int = 200):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


_SAMPLE_WARNING = {
    "warnid": 4149,
    "warntypid": 1,        # Sturm
    "warnstufeid": 2,      # orange
    "text": "Orangene Sturmwarnung",
    "auswirkungen": "* Äste können brechen",
    "empfehlungen": "* Seien Sie vorsichtig",
    "rawinfo": {"start": "1679896800", "end": "1679932800"},
}

_SAMPLE_RESPONSE = {
    "type": "Feature",
    "properties": {
        "location": {"type": "Municipal", "properties": {"name": "Wien"}},
        "warnings": [_SAMPLE_WARNING],
    },
}

_EMPTY_RESPONSE = {
    "type": "Feature",
    "properties": {
        "location": {"type": "Municipal", "properties": {"name": "Wien"}},
        "warnings": [],
    },
}


# ---------------------------------------------------------------------------
# GeoSphereApi.get_warnings – Parsing
# ---------------------------------------------------------------------------

class TestGetWarnings:
    async def test_parses_warning_fields(self):
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(_SAMPLE_RESPONSE))
        api = GeoSphereApi(session)

        result = await api.get_warnings(48.21, 16.37)

        assert len(result) == 1
        w = result[0]
        assert w["id"] == 4149
        assert w["type_id"] == 1
        assert w["level"] == 2
        assert w["text"] == "Orangene Sturmwarnung"
        assert w["effects"] == "* Äste können brechen"
        assert w["recommendations"] == "* Seien Sie vorsichtig"
        assert w["begin"] == 1679896800
        assert w["end"] == 1679932800

    async def test_empty_warnings_list(self):
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(_EMPTY_RESPONSE))
        api = GeoSphereApi(session)

        result = await api.get_warnings(48.21, 16.37)
        assert result == []

    async def test_multiple_warnings(self):
        payload = {
            "type": "Feature",
            "properties": {
                "warnings": [
                    {**_SAMPLE_WARNING, "warnid": 1, "warnstufeid": 1},
                    {**_SAMPLE_WARNING, "warnid": 2, "warntypid": 5, "warnstufeid": 3},
                ]
            },
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        result = await api.get_warnings(48.21, 16.37)
        assert len(result) == 2
        assert result[0]["level"] == 1
        assert result[1]["level"] == 3

    async def test_http_error_raises_api_error(self):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("connection refused"))
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=resp)
        api = GeoSphereApi(session)

        with pytest.raises(GeoSphereApiError, match="Fehler beim Abrufen der Warnungen"):
            await api.get_warnings(48.21, 16.37)

    async def test_timeout_raises_api_error(self):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
        resp.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=resp)

        with pytest.raises(GeoSphereApiError):
            await GeoSphereApi(session).get_warnings(48.21, 16.37)

    async def test_url_contains_lon_lat_and_lang(self):
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(_EMPTY_RESPONSE))
        api = GeoSphereApi(session)

        await api.get_warnings(48.21, 16.37, lang="de")

        url = session.get.call_args[0][0]
        assert "lat=48.21" in url
        assert "lon=16.37" in url
        assert "lang=de" in url

    async def test_missing_rawinfo_timestamps_are_none(self):
        payload = {
            "type": "Feature",
            "properties": {
                "warnings": [{
                    "warnid": 1, "warntypid": 2, "warnstufeid": 1,
                    "text": "Regen", "auswirkungen": "", "empfehlungen": "",
                    "rawinfo": {},  # keine start/end
                }]
            },
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_make_mock_response(payload))
        api = GeoSphereApi(session)

        result = await api.get_warnings(48.21, 16.37)
        assert result[0]["begin"] is None
        assert result[0]["end"] is None


# ---------------------------------------------------------------------------
# GeoSphereWarningSensor – native_value
# ---------------------------------------------------------------------------

class TestWarningSensorNativeValue:
    def test_returns_0_when_no_data(self):
        sensor = _make_sensor(warnings=None)
        assert sensor.native_value == 0

    def test_returns_0_when_empty_list(self):
        sensor = _make_sensor(warnings=[])
        assert sensor.native_value == 0

    def test_returns_max_level_of_single_warning(self):
        sensor = _make_sensor(warnings=[{"type_id": 1, "level": 2, "text": "", "effects": "", "recommendations": "", "begin": None, "end": None}])
        assert sensor.native_value == 2

    def test_returns_max_level_of_multiple_warnings(self):
        sensor = _make_sensor(warnings=[
            {"type_id": 1, "level": 1, "text": "", "effects": "", "recommendations": "", "begin": None, "end": None},
            {"type_id": 5, "level": 3, "text": "", "effects": "", "recommendations": "", "begin": None, "end": None},
            {"type_id": 2, "level": 2, "text": "", "effects": "", "recommendations": "", "begin": None, "end": None},
        ])
        assert sensor.native_value == 3

    def test_level_1_yellow(self):
        sensor = _make_sensor(warnings=[{"type_id": 1, "level": 1, "text": "", "effects": "", "recommendations": "", "begin": None, "end": None}])
        assert sensor.native_value == 1

    def test_level_3_red(self):
        sensor = _make_sensor(warnings=[{"type_id": 1, "level": 3, "text": "", "effects": "", "recommendations": "", "begin": None, "end": None}])
        assert sensor.native_value == 3


# ---------------------------------------------------------------------------
# GeoSphereWarningSensor – icon
# ---------------------------------------------------------------------------

class TestWarningSensorIcon:
    def test_icon_outline_when_no_warnings(self):
        sensor = _make_sensor(warnings=[])
        assert sensor.icon == "mdi:alert-outline"

    def test_icon_alert_for_level_1(self):
        sensor = _make_sensor(warnings=[{"type_id": 1, "level": 1, "text": "", "effects": "", "recommendations": "", "begin": None, "end": None}])
        assert sensor.icon == "mdi:alert"

    def test_icon_alert_circle_for_level_2(self):
        sensor = _make_sensor(warnings=[{"type_id": 1, "level": 2, "text": "", "effects": "", "recommendations": "", "begin": None, "end": None}])
        assert sensor.icon == "mdi:alert-circle"

    def test_icon_alert_circle_for_level_3(self):
        sensor = _make_sensor(warnings=[{"type_id": 1, "level": 3, "text": "", "effects": "", "recommendations": "", "begin": None, "end": None}])
        assert sensor.icon == "mdi:alert-circle"


# ---------------------------------------------------------------------------
# GeoSphereWarningSensor – extra_state_attributes
# ---------------------------------------------------------------------------

def _warning(type_id=1, level=2, begin=1679896800, end=1679932800,
             text="Sturmwarnung", effects="Äste", recommendations="Vorsicht"):
    return {
        "type_id": type_id, "level": level,
        "begin": begin, "end": end,
        "text": text, "effects": effects, "recommendations": recommendations,
    }


class TestWarningSensorAttributes:
    def test_empty_warnings_list_in_attributes(self):
        sensor = _make_sensor(warnings=[])
        assert sensor.extra_state_attributes == {"warnings": []}

    def test_none_data_gives_empty_list(self):
        sensor = _make_sensor(warnings=None)
        assert sensor.extra_state_attributes == {"warnings": []}

    def test_type_name_resolved(self):
        sensor = _make_sensor(warnings=[_warning(type_id=1)])
        attrs = sensor.extra_state_attributes["warnings"][0]
        assert attrs["type"] == "Sturm"

    def test_unknown_type_id_falls_back_to_string(self):
        sensor = _make_sensor(warnings=[_warning(type_id=99)])
        attrs = sensor.extra_state_attributes["warnings"][0]
        assert attrs["type"] == "99"

    def test_all_warning_types_known(self):
        from custom_components.geosphere_austria_plus.const import WARNING_TYPES
        for type_id in range(1, 8):
            sensor = _make_sensor(warnings=[_warning(type_id=type_id)])
            attrs = sensor.extra_state_attributes["warnings"][0]
            assert attrs["type"] == WARNING_TYPES[type_id]

    def test_begin_end_converted_to_iso(self):
        sensor = _make_sensor(warnings=[_warning(begin=1679896800, end=1679932800)])
        attrs = sensor.extra_state_attributes["warnings"][0]
        expected_begin = datetime.fromtimestamp(1679896800, tz=timezone.utc).isoformat()
        expected_end = datetime.fromtimestamp(1679932800, tz=timezone.utc).isoformat()
        assert attrs["begin"] == expected_begin
        assert attrs["end"] == expected_end

    def test_none_timestamps_omitted(self):
        sensor = _make_sensor(warnings=[_warning(begin=None, end=None)])
        attrs = sensor.extra_state_attributes["warnings"][0]
        assert "begin" not in attrs
        assert "end" not in attrs

    def test_empty_effects_omitted(self):
        sensor = _make_sensor(warnings=[_warning(effects="", recommendations="")])
        attrs = sensor.extra_state_attributes["warnings"][0]
        assert "effects" not in attrs
        assert "recommendations" not in attrs

    def test_text_always_present(self):
        sensor = _make_sensor(warnings=[_warning(text="Achtung Sturm")])
        attrs = sensor.extra_state_attributes["warnings"][0]
        assert attrs["text"] == "Achtung Sturm"

    def test_level_present_in_attributes(self):
        sensor = _make_sensor(warnings=[_warning(level=3)])
        attrs = sensor.extra_state_attributes["warnings"][0]
        assert attrs["level"] == 3

    def test_multiple_warnings_all_in_attributes(self):
        sensor = _make_sensor(warnings=[_warning(type_id=1), _warning(type_id=5)])
        result = sensor.extra_state_attributes["warnings"]
        assert len(result) == 2
        assert result[0]["type"] == "Sturm"
        assert result[1]["type"] == "Gewitter"


# ---------------------------------------------------------------------------
# GeoSphereWarningSensor – Metadaten
# ---------------------------------------------------------------------------

class TestWarningSensorMetadata:
    def test_unique_id(self):
        sensor = _make_sensor()
        assert sensor._attr_unique_id == "geosphere_plus_11035_warning_level"

    def test_translation_key(self):
        sensor = _make_sensor()
        assert sensor._attr_translation_key == "warning_level"

    def test_device_info_identifiers(self):
        sensor = _make_sensor()
        assert sensor._attr_device_info["identifiers"] == {("geosphere_austria_plus", "11035")}

    def test_device_info_name(self):
        sensor = _make_sensor()
        assert sensor._attr_device_info["name"] == "WIEN HOHE WARTE"
