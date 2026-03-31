"""Tests für GeoSphereOptionsFlowHandler und GeoSphereAustriaPlusConfigFlow."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.geosphere_austria_plus.config_flow import (
    GeoSphereOptionsFlowHandler,
    GeoSphereAustriaPlusConfigFlow,
)
from custom_components.geosphere_austria_plus.const import (
    DEFAULT_FORECAST_MODEL,
    FORECAST_MODELS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_STATION_ID,
    CONF_FORECAST_MODELS,
)

_DEFAULT_LAT = 48.21
_DEFAULT_LON = 16.37
_DEFAULT_NAME = "Zuhause"
_VALID_STATION = {"id": "11035", "name": "Wien", "lat": 48.21, "lon": 16.37}

_BASE_USER_INPUT = {
    CONF_NAME: _DEFAULT_NAME,
    CONF_LATITUDE: _DEFAULT_LAT,
    CONF_LONGITUDE: _DEFAULT_LON,
    CONF_STATION_ID: "",
    CONF_FORECAST_MODELS: ["nwp-v1-1h-2500m"],
}


class _FakeOptionsFlow:
    """Test-Double: liefert die Interface-Methoden, die async_step_init nutzt."""

    _stations: list[dict] = []  # Leer → kein API-Call

    def __init__(self, options=None, data=None, title="Test"):
        self.hass = MagicMock()
        self.hass.config.latitude = _DEFAULT_LAT
        self.hass.config.longitude = _DEFAULT_LON
        self.config_entry = MagicMock()
        self.config_entry.title = title
        self.config_entry.options = options or {}
        self.config_entry.data = data or {}

    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, step_id, data_schema=None, errors=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}}

    def _build_schema(self, *args, **kwargs):
        return MagicMock()


async def _call(fake, user_input):
    """Ruft async_step_init als ungebundene Methode mit fake als self auf."""
    return await GeoSphereOptionsFlowHandler.async_step_init(fake, user_input)


class TestOptionsFlowInit:
    async def test_shows_form_when_no_input(self):
        result = await _call(_FakeOptionsFlow(), user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "init"

    async def test_creates_entry_with_selected_models(self):
        models = ["nwp-v1-1h-2500m", "ensemble-v1-1h-2500m"]
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_FORECAST_MODELS: models},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == models

    async def test_defaults_to_nwp_when_no_models_selected(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_FORECAST_MODELS: []},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == [DEFAULT_FORECAST_MODEL]

    async def test_invalid_models_filtered_out(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_FORECAST_MODELS: ["invalid-model"]},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == [DEFAULT_FORECAST_MODEL]

    async def test_mix_of_valid_and_invalid_models(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={
                **_BASE_USER_INPUT,
                CONF_FORECAST_MODELS: ["nwp-v1-1h-2500m", "invalid-model"],
            },
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == ["nwp-v1-1h-2500m"]

    async def test_coordinates_stored_in_options(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_LATITUDE: 47.5, CONF_LONGITUDE: 13.1},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_LATITUDE] == 47.5
        assert result["data"][CONF_LONGITUDE] == 13.1

    async def test_name_stored_in_options(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_NAME: "Ferienhaus"},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_NAME] == "Ferienhaus"

    async def test_station_optional_empty_stored_as_none(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_STATION_ID: ""},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_STATION_ID] is None

    async def test_station_with_value_stored(self):
        fake = _FakeOptionsFlow()
        fake._stations = [_VALID_STATION]
        result = await _call(
            fake,
            user_input={**_BASE_USER_INPUT, CONF_STATION_ID: "11035"},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_STATION_ID] == "11035"

    async def test_reads_current_values_from_options(self):
        fake = _FakeOptionsFlow(
            options={CONF_FORECAST_MODELS: ["ensemble-v1-1h-2500m"], CONF_LATITUDE: 47.0, CONF_LONGITUDE: 15.0}
        )
        result = await _call(fake, user_input=None)
        assert result["type"] == "form"

    async def test_falls_back_to_data_when_options_empty(self):
        fake = _FakeOptionsFlow(
            options={},
            data={CONF_FORECAST_MODELS: ["nowcast-v1-15min-1km"], CONF_LATITUDE: 47.0, CONF_LONGITUDE: 15.0},
        )
        result = await _call(fake, user_input=None)
        assert result["type"] == "form"


# ---------------------------------------------------------------------------
# GeoSphereAustriaPlusConfigFlow – async_step_user
# ---------------------------------------------------------------------------


class _FakeConfigFlow:
    """Test-Double für GeoSphereAustriaPlusConfigFlow."""

    _stations: list[dict] | None = None

    def __init__(self, stations: list[dict] | None = None):
        self.hass = MagicMock()
        self.hass.config.latitude = _DEFAULT_LAT
        self.hass.config.longitude = _DEFAULT_LON
        self.hass.config.location_name = _DEFAULT_NAME
        if stations is not None:
            self._stations = stations

    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, step_id, data_schema=None, errors=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}}

    def _abort_if_unique_id_configured(self):
        pass

    async def async_set_unique_id(self, unique_id):
        self._last_unique_id = unique_id

    def _build_schema(self, *args, **kwargs):
        return MagicMock()


async def _call_user(fake, user_input):
    return await GeoSphereAustriaPlusConfigFlow.async_step_user(fake, user_input)


class TestConfigFlowUserStep:
    async def test_shows_form_when_no_input(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(fake, user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    async def test_creates_entry_with_valid_input(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(fake, user_input=_BASE_USER_INPUT)
        assert result["type"] == "create_entry"
        assert result["title"] == _DEFAULT_NAME
        assert result["data"][CONF_LATITUDE] == _DEFAULT_LAT
        assert result["data"][CONF_LONGITUDE] == _DEFAULT_LON
        assert result["data"][CONF_FORECAST_MODELS] == ["nwp-v1-1h-2500m"]

    async def test_station_optional_empty_means_none(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake, user_input={**_BASE_USER_INPUT, CONF_STATION_ID: ""}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_STATION_ID] is None

    async def test_station_with_value_stored(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake, user_input={**_BASE_USER_INPUT, CONF_STATION_ID: "11035"}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_STATION_ID] == "11035"

    async def test_station_id_is_stripped(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake, user_input={**_BASE_USER_INPUT, CONF_STATION_ID: "  11035  "}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_STATION_ID] == "11035"

    async def test_unique_id_based_on_coordinates(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        await _call_user(fake, user_input=_BASE_USER_INPUT)
        expected_uid = f"{round(_DEFAULT_LAT, 3)}_{round(_DEFAULT_LON, 3)}"
        assert fake._last_unique_id == expected_uid

    async def test_invalid_models_are_filtered_out(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake,
            user_input={**_BASE_USER_INPUT, CONF_FORECAST_MODELS: ["invalid-model"]},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == [DEFAULT_FORECAST_MODEL]

    async def test_empty_models_falls_back_to_default(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake, user_input={**_BASE_USER_INPUT, CONF_FORECAST_MODELS: []}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == [DEFAULT_FORECAST_MODEL]

    async def test_mix_valid_and_invalid_models(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake,
            user_input={
                **_BASE_USER_INPUT,
                CONF_FORECAST_MODELS: ["nwp-v1-1h-2500m", "bad-model"],
            },
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == ["nwp-v1-1h-2500m"]

    async def test_user_coordinates_stored(self):
        """Koordinaten kommen aus der Nutzereingabe, nicht aus der Station."""
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake,
            user_input={**_BASE_USER_INPUT, CONF_LATITUDE: 47.5, CONF_LONGITUDE: 13.1},
        )
        assert result["data"][CONF_LATITUDE] == 47.5
        assert result["data"][CONF_LONGITUDE] == 13.1

    async def test_stations_none_triggers_api_load(self):
        """Wenn _stations None ist, wird die API aufgerufen."""
        from unittest.mock import patch, AsyncMock as AM

        fake = _FakeConfigFlow()  # _stations = None
        mock_stations = [_VALID_STATION]

        with patch(
            "custom_components.geosphere_austria_plus.config_flow.GeoSphereApi"
        ) as MockApi:
            MockApi.return_value.get_stations = AM(return_value=mock_stations)
            await _call_user(fake, user_input=None)

        assert fake._stations == mock_stations

    async def test_stations_not_reloaded_when_already_set(self):
        """Stationsliste wird nur einmal geladen."""
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        await _call_user(fake, user_input=None)
        fake.hass.helpers.aiohttp_client.async_get_clientsession.assert_not_called()
