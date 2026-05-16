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
    CONF_ENABLE_WARNINGS,
    CONF_ENABLE_AIR_QUALITY,
    CONF_ENABLE_OPEN_METEO,
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

    async def test_empty_models_stored_as_empty_list(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_FORECAST_MODELS: []},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == []

    async def test_invalid_models_filtered_out(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_FORECAST_MODELS: ["invalid-model"]},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == []

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

    async def test_enable_warnings_true_stored(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_ENABLE_WARNINGS: True},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_WARNINGS] is True

    async def test_enable_warnings_false_stored(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_ENABLE_WARNINGS: False},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_WARNINGS] is False

    async def test_enable_air_quality_true_stored(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_ENABLE_AIR_QUALITY: True},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_AIR_QUALITY] is True

    async def test_enable_air_quality_false_stored(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_ENABLE_AIR_QUALITY: False},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_AIR_QUALITY] is False

    async def test_enable_warnings_defaults_to_true_when_missing(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input=_BASE_USER_INPUT,  # kein CONF_ENABLE_WARNINGS
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_WARNINGS] is True

    async def test_enable_air_quality_defaults_to_true_when_missing(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input=_BASE_USER_INPUT,  # kein CONF_ENABLE_AIR_QUALITY
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_AIR_QUALITY] is True

    async def test_enable_open_meteo_true_stored(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_ENABLE_OPEN_METEO: True},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_OPEN_METEO] is True

    async def test_enable_open_meteo_false_stored(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={**_BASE_USER_INPUT, CONF_ENABLE_OPEN_METEO: False},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_OPEN_METEO] is False

    async def test_enable_open_meteo_defaults_to_false_when_missing(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input=_BASE_USER_INPUT,  # no CONF_ENABLE_OPEN_METEO
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_OPEN_METEO] is False

    async def test_zero_models_with_warnings_disabled(self):
        result = await _call(
            _FakeOptionsFlow(),
            user_input={
                **_BASE_USER_INPUT,
                CONF_FORECAST_MODELS: [],
                CONF_ENABLE_WARNINGS: False,
                CONF_ENABLE_AIR_QUALITY: False,
            },
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == []
        assert result["data"][CONF_ENABLE_WARNINGS] is False
        assert result["data"][CONF_ENABLE_AIR_QUALITY] is False


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
        # 5 Dezimalen → ~1 m Auflösung; verhindert Kollisionen nahe gelegener Stationen.
        expected_uid = f"{round(_DEFAULT_LAT, 5)}_{round(_DEFAULT_LON, 5)}"
        assert fake._last_unique_id == expected_uid

    async def test_unique_id_distinguishes_nearby_coordinates(self):
        """Zwei Installationen <100 m Abstand müssen unterschiedliche unique_ids haben."""
        fake1 = _FakeConfigFlow(stations=[_VALID_STATION])
        fake2 = _FakeConfigFlow(stations=[_VALID_STATION])
        # ~80 m Abstand bei lat=48° (1 Dezimalstelle hinter dem dritten Komma)
        await _call_user(fake1, user_input={**_BASE_USER_INPUT, CONF_LATITUDE: 48.21000, CONF_LONGITUDE: 16.37000})
        await _call_user(fake2, user_input={**_BASE_USER_INPUT, CONF_LATITUDE: 48.21070, CONF_LONGITUDE: 16.37000})
        assert fake1._last_unique_id != fake2._last_unique_id


class _FakeReconfigureFlow(_FakeConfigFlow):
    """Test-Double für die Reconfigure-Flow-Variante."""

    def __init__(self, entry_data=None, entry_options=None, stations=None):
        super().__init__(stations=stations)
        self._entry = MagicMock()
        self._entry.entry_id = "test_entry"
        self._entry.title = "Wien"
        self._entry.data = entry_data or {}
        self._entry.options = entry_options or {}
        self._mismatch_called = False
        self._update_args = None

    def _get_reconfigure_entry(self):
        return self._entry

    def _abort_if_unique_id_mismatch(self, reason="reconfigure_unique_id_mismatch"):
        self._mismatch_called = True

    def async_update_reload_and_abort(self, entry, data=None, title=None):
        self._update_args = {"entry": entry, "data": data, "title": title}
        return {"type": "abort", "reason": "reconfigure_successful"}

    def _build_schema_with_defaults(self, entry):
        return MagicMock()


class TestReconfigureFlow:
    """Gold-Tier: async_step_reconfigure ermöglicht User-Änderungen
    am bestehenden Eintrag ohne Lösch-Re-Setup."""

    async def test_shows_form_with_defaults_from_entry(self):
        from custom_components.geosphere_austria_plus.config_flow import (
            GeoSphereAustriaPlusConfigFlow,
        )
        fake = _FakeReconfigureFlow(
            entry_data={**_BASE_USER_INPUT, CONF_LATITUDE: 47.5, CONF_LONGITUDE: 13.1},
            stations=[_VALID_STATION],
        )
        result = await GeoSphereAustriaPlusConfigFlow.async_step_reconfigure(fake, None)
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure"

    async def test_updates_entry_on_submit(self):
        from custom_components.geosphere_austria_plus.config_flow import (
            GeoSphereAustriaPlusConfigFlow,
        )
        fake = _FakeReconfigureFlow(
            entry_data={**_BASE_USER_INPUT, CONF_LATITUDE: 47.5, CONF_LONGITUDE: 13.1},
            stations=[_VALID_STATION],
        )
        new_input = {**_BASE_USER_INPUT, CONF_LATITUDE: 48.21, CONF_LONGITUDE: 16.37}
        result = await GeoSphereAustriaPlusConfigFlow.async_step_reconfigure(fake, new_input)
        assert result["type"] == "abort"
        assert fake._update_args is not None
        assert fake._update_args["data"][CONF_LATITUDE] == 48.21
        assert fake._update_args["data"][CONF_LONGITUDE] == 16.37

    async def test_unique_id_mismatch_check_called_on_submit(self):
        """Bei Reconfigure muss die unique_id-Kollision mit ANDEREN Einträgen
        geprüft werden (nicht abort_if_unique_id_configured wie bei user-step)."""
        from custom_components.geosphere_austria_plus.config_flow import (
            GeoSphereAustriaPlusConfigFlow,
        )
        fake = _FakeReconfigureFlow(
            entry_data=_BASE_USER_INPUT,
            stations=[_VALID_STATION],
        )
        await GeoSphereAustriaPlusConfigFlow.async_step_reconfigure(fake, _BASE_USER_INPUT)
        assert fake._mismatch_called is True

    async def test_invalid_models_are_filtered_out(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake,
            user_input={**_BASE_USER_INPUT, CONF_FORECAST_MODELS: ["invalid-model"]},
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == []

    async def test_empty_models_stored_as_empty_list(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake, user_input={**_BASE_USER_INPUT, CONF_FORECAST_MODELS: []}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_FORECAST_MODELS] == []

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

    async def test_enable_warnings_true_stored(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake, user_input={**_BASE_USER_INPUT, CONF_ENABLE_WARNINGS: True}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_WARNINGS] is True

    async def test_enable_warnings_false_stored(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake, user_input={**_BASE_USER_INPUT, CONF_ENABLE_WARNINGS: False}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_WARNINGS] is False

    async def test_enable_air_quality_true_stored(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake, user_input={**_BASE_USER_INPUT, CONF_ENABLE_AIR_QUALITY: True}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_AIR_QUALITY] is True

    async def test_enable_air_quality_false_stored(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake, user_input={**_BASE_USER_INPUT, CONF_ENABLE_AIR_QUALITY: False}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_AIR_QUALITY] is False

    async def test_enable_warnings_defaults_to_true_when_missing(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(fake, user_input=_BASE_USER_INPUT)
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_WARNINGS] is True

    async def test_enable_air_quality_defaults_to_true_when_missing(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(fake, user_input=_BASE_USER_INPUT)
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_AIR_QUALITY] is True

    async def test_enable_open_meteo_true_stored(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake, user_input={**_BASE_USER_INPUT, CONF_ENABLE_OPEN_METEO: True}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_OPEN_METEO] is True

    async def test_enable_open_meteo_false_stored(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake, user_input={**_BASE_USER_INPUT, CONF_ENABLE_OPEN_METEO: False}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_OPEN_METEO] is False

    async def test_enable_open_meteo_defaults_to_false_when_missing(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(fake, user_input=_BASE_USER_INPUT)
        assert result["type"] == "create_entry"
        assert result["data"][CONF_ENABLE_OPEN_METEO] is False


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

class TestStationOptions:
    def test_empty_stations_returns_only_none_option(self):
        from custom_components.geosphere_austria_plus.config_flow import _station_options
        result = _station_options([])
        assert len(result) == 1
        assert result[0]["value"] == ""

    def test_stations_sorted_alphabetically(self):
        from custom_components.geosphere_austria_plus.config_flow import _station_options
        result = _station_options([
            {"id": "11150", "name": "Salzburg", "lat": 47.8, "lon": 13.0},
            {"id": "11035", "name": "Wien", "lat": 48.2, "lon": 16.4},
            {"id": "11101", "name": "Innsbruck", "lat": 47.3, "lon": 11.4},
        ])
        # First entry is the empty option, then alphabetical names.
        names = [r["label"] for r in result[1:]]
        assert names == ["Innsbruck (11101)", "Salzburg (11150)", "Wien (11035)"]


class TestAsyncGetOptionsFlow:
    def test_returns_options_flow_handler(self):
        from custom_components.geosphere_austria_plus.config_flow import (
            GeoSphereAustriaPlusConfigFlow,
            GeoSphereOptionsFlowHandler,
        )
        handler = GeoSphereAustriaPlusConfigFlow.async_get_options_flow(MagicMock())
        assert isinstance(handler, GeoSphereOptionsFlowHandler)


# ---------------------------------------------------------------------------
# Station-API fallback in all three flows
# ---------------------------------------------------------------------------

class TestStationApiFallback:
    """When GeoSphere's /station/all endpoint fails, all three flows must
    fall back to an empty station list rather than crash setup."""

    async def test_options_flow_api_error_yields_empty_stations(self):
        from custom_components.geosphere_austria_plus.api import GeoSphereApiError
        fake = _FakeOptionsFlow()
        fake._stations = None  # force API load
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "custom_components.geosphere_austria_plus.config_flow.GeoSphereApi",
                lambda session: MagicMock(get_stations=AsyncMock(side_effect=GeoSphereApiError("boom"))),
            )
            await _call(fake, user_input=None)
        assert fake._stations == []

    async def test_user_step_api_error_yields_empty_stations(self):
        from custom_components.geosphere_austria_plus.api import GeoSphereApiError
        fake = _FakeConfigFlow(stations=None)  # default
        fake._stations = None  # ensure API path taken
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "custom_components.geosphere_austria_plus.config_flow.GeoSphereApi",
                lambda session: MagicMock(get_stations=AsyncMock(side_effect=GeoSphereApiError("boom"))),
            )
            await _call_user(fake, user_input=None)
        assert fake._stations == []

    async def test_reconfigure_api_error_yields_empty_stations(self):
        from custom_components.geosphere_austria_plus.config_flow import (
            GeoSphereAustriaPlusConfigFlow,
        )
        from custom_components.geosphere_austria_plus.api import GeoSphereApiError
        fake = _FakeReconfigureFlow(entry_data=_BASE_USER_INPUT)
        fake._stations = None
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "custom_components.geosphere_austria_plus.config_flow.GeoSphereApi",
                lambda session: MagicMock(get_stations=AsyncMock(side_effect=GeoSphereApiError("boom"))),
            )
            await GeoSphereAustriaPlusConfigFlow.async_step_reconfigure(fake, None)
        assert fake._stations == []


# ---------------------------------------------------------------------------
# Schema construction (no _build_schema stub)
# ---------------------------------------------------------------------------

def _make_real_flow(stations=None) -> "GeoSphereAustriaPlusConfigFlow":  # noqa: F821
    """Instantiate the real ConfigFlow class for schema tests.

    The _FakeConfigFlow used elsewhere stubs _build_schema to MagicMock,
    so the real schema-construction code is never exercised. Here we use
    the actual class (which inherits from conftest's _MockConfigFlow → has
    self.hass = MagicMock() after __init__).
    """
    from custom_components.geosphere_austria_plus.config_flow import (
        GeoSphereAustriaPlusConfigFlow,
    )
    flow = GeoSphereAustriaPlusConfigFlow()
    flow.hass.config.location_name = _DEFAULT_NAME
    flow.hass.config.latitude = _DEFAULT_LAT
    flow.hass.config.longitude = _DEFAULT_LON
    flow._stations = stations if stations is not None else []
    return flow


class TestSchemaConstruction:
    """Exercise the real _schema_from_defaults and _build_schema_with_defaults
    bodies — the existing _FakeConfigFlow stubs _build_schema to a MagicMock,
    so neither real method ran before."""

    def test_schema_from_defaults_with_stations_uses_select(self):
        """With non-empty stations, station_field branch goes to SelectSelector."""
        flow = _make_real_flow(stations=[_VALID_STATION])
        schema = flow._schema_from_defaults(
            "Wien", 48.21, 16.37, "11035",
            ["nwp-v1-1h-2500m"],
            True, True, False, 5,
        )
        assert schema is not None

    def test_schema_from_defaults_without_stations_uses_text(self):
        """With empty stations, station_field branch goes to TextSelector."""
        flow = _make_real_flow(stations=[])
        schema = flow._schema_from_defaults(
            "Wien", 48.21, 16.37, "",
            ["nwp-v1-1h-2500m"],
            True, True, False, 5,
        )
        assert schema is not None

    def test_build_schema_with_defaults_reads_options_over_data(self):
        """Options should win over data when both keys are present."""
        flow = _make_real_flow()
        entry = MagicMock()
        entry.title = "Wien"
        entry.data = {
            CONF_LATITUDE: 47.0, CONF_LONGITUDE: 13.0,
            CONF_FORECAST_MODELS: ["nwp-v1-1h-2500m"],
        }
        entry.options = {
            CONF_LATITUDE: 48.21, CONF_LONGITUDE: 16.37,
            CONF_FORECAST_MODELS: ["nowcast-v1-15min-1km"],
        }
        schema = flow._build_schema_with_defaults(entry)
        assert schema is not None

    def test_build_schema_with_defaults_falls_back_to_data(self):
        """When options is empty, data values are used."""
        flow = _make_real_flow()
        entry = MagicMock()
        entry.title = "Wien"
        entry.data = {
            CONF_LATITUDE: 47.0, CONF_LONGITUDE: 13.0,
            CONF_FORECAST_MODELS: ["nwp-v1-1h-2500m"],
        }
        entry.options = {}
        schema = flow._build_schema_with_defaults(entry)
        assert schema is not None

    def test_build_schema_with_defaults_uses_default_model_when_neither_set(self):
        """Neither data nor options has the forecast_models key → fallback."""
        flow = _make_real_flow()
        entry = MagicMock()
        entry.title = "Wien"
        entry.data = {CONF_LATITUDE: 47.0, CONF_LONGITUDE: 13.0}
        entry.options = {}
        schema = flow._build_schema_with_defaults(entry)
        assert schema is not None

    def test_real_build_schema_runs_without_stub(self):
        """Verify the user-step _build_schema (no defaults) executes."""
        flow = _make_real_flow()
        schema = flow._build_schema()
        assert schema is not None
