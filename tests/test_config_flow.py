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
)


class _FakeOptionsFlow:
    """Test-Double: liefert die Interface-Methoden, die async_step_init nutzt."""

    def __init__(self, options=None, data=None):
        self.config_entry = MagicMock()
        self.config_entry.options = options or {}
        self.config_entry.data = data or {}

    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, step_id, data_schema=None, errors=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}}


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
            _FakeOptionsFlow(), user_input={"forecast_models": models}
        )
        assert result["type"] == "create_entry"
        assert result["data"]["forecast_models"] == models

    async def test_defaults_to_nwp_when_no_models_selected(self):
        result = await _call(
            _FakeOptionsFlow(), user_input={"forecast_models": []}
        )
        assert result["type"] == "create_entry"
        assert result["data"]["forecast_models"] == [DEFAULT_FORECAST_MODEL]

    async def test_reads_current_models_from_options(self):
        fake = _FakeOptionsFlow(options={"forecast_models": ["ensemble-v1-1h-2500m"]})
        result = await _call(fake, user_input=None)
        assert result["type"] == "form"

    async def test_falls_back_to_data_when_options_empty(self):
        fake = _FakeOptionsFlow(
            options={},
            data={"forecast_models": ["nowcast-v1-15min-1km"]},
        )
        result = await _call(fake, user_input=None)
        assert result["type"] == "form"

    async def test_invalid_models_filtered_out(self):
        """Unbekannte Modell-IDs im OptionsFlow werden ignoriert."""
        result = await _call(
            _FakeOptionsFlow(), user_input={"forecast_models": ["invalid-model"]}
        )
        assert result["type"] == "create_entry"
        assert result["data"]["forecast_models"] == [DEFAULT_FORECAST_MODEL]

    async def test_mix_of_valid_and_invalid_models(self):
        """Nur gültige Modelle werden übernommen; ungültige werden gefiltert."""
        result = await _call(
            _FakeOptionsFlow(),
            user_input={"forecast_models": ["nwp-v1-1h-2500m", "invalid-model"]},
        )
        assert result["type"] == "create_entry"
        assert result["data"]["forecast_models"] == ["nwp-v1-1h-2500m"]


# ---------------------------------------------------------------------------
# GeoSphereAustriaPlusConfigFlow – async_step_user
# ---------------------------------------------------------------------------


class _FakeConfigFlow:
    """Test-Double für GeoSphereAustriaPlusConfigFlow (enthält die benötigten Interface-Methoden)."""

    _stations: list[dict] | None = None

    def __init__(self, stations: list[dict] | None = None):
        self.hass = MagicMock()
        if stations is not None:
            self._stations = stations

    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, step_id, data_schema=None, errors=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}}

    def _abort_if_unique_id_configured(self):
        pass

    async def async_set_unique_id(self, unique_id):
        pass


async def _call_user(fake, user_input):
    return await GeoSphereAustriaPlusConfigFlow.async_step_user(fake, user_input)


_VALID_STATION = {"id": "11035", "name": "Wien", "lat": 48.21, "lon": 16.37}


class TestConfigFlowUserStep:
    async def test_shows_form_when_no_input(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(fake, user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    async def test_creates_entry_with_valid_input(self):
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake,
            user_input={"station_id": "11035", "forecast_models": ["nwp-v1-1h-2500m"]},
        )
        assert result["type"] == "create_entry"
        assert result["data"]["station_id"] == "11035"
        assert result["data"]["forecast_models"] == ["nwp-v1-1h-2500m"]

    async def test_invalid_models_are_filtered_out(self):
        """Unbekannte Modell-IDs werden gefiltert und durch den Default ersetzt."""
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake,
            user_input={"station_id": "11035", "forecast_models": ["invalid-model"]},
        )
        assert result["type"] == "create_entry"
        assert result["data"]["forecast_models"] == [DEFAULT_FORECAST_MODEL]

    async def test_empty_models_falls_back_to_default(self):
        """Leere Modell-Liste → Default-Modell wird verwendet."""
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake,
            user_input={"station_id": "11035", "forecast_models": []},
        )
        assert result["type"] == "create_entry"
        assert result["data"]["forecast_models"] == [DEFAULT_FORECAST_MODEL]

    async def test_mix_valid_and_invalid_models(self):
        """Nur gültige Modelle werden übernommen."""
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake,
            user_input={
                "station_id": "11035",
                "forecast_models": ["nwp-v1-1h-2500m", "bad-model"],
            },
        )
        assert result["type"] == "create_entry"
        assert result["data"]["forecast_models"] == ["nwp-v1-1h-2500m"]

    async def test_station_id_is_stripped(self):
        """Führende/nachfolgende Leerzeichen in der Station-ID werden entfernt."""
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake,
            user_input={"station_id": "  11035  ", "forecast_models": []},
        )
        assert result["type"] == "create_entry"
        assert result["data"]["station_id"] == "11035"

    async def test_stations_not_reloaded_when_already_set(self):
        """Stationsliste wird nur einmal geladen (kein zweiter API-Call)."""
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        # _stations ist bereits gesetzt → kein API-Aufruf erwartet
        await _call_user(fake, user_input=None)
        fake.hass.helpers.aiohttp_client.async_get_clientsession.assert_not_called()

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

    async def test_station_coords_stored_in_entry(self):
        """lat/lon aus der Stationsliste werden in den Config-Entry-Daten gespeichert."""
        fake = _FakeConfigFlow(stations=[_VALID_STATION])
        result = await _call_user(
            fake,
            user_input={"station_id": "11035", "forecast_models": []},
        )
        assert result["data"]["lat"] == 48.21
        assert result["data"]["lon"] == 16.37
