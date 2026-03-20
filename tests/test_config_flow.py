"""Tests für GeoSphereOptionsFlowHandler."""
import pytest
from unittest.mock import MagicMock

from custom_components.geosphere_austria_plus.config_flow import (
    GeoSphereOptionsFlowHandler,
)
from custom_components.geosphere_austria_plus.const import DEFAULT_FORECAST_MODEL


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
