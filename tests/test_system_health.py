"""Tests for system_health module."""
from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# system_health.py importiert via `from homeassistant.components import system_health`.
# Diese Form holt das Attribut vom Parent-Module — also patchen wir das
# Attribut direkt am im conftest hinterlegten MagicMock, BEVOR die
# Integrations-Datei importiert wird.
_sh_mod = types.ModuleType("homeassistant.components.system_health")


class _MockSystemHealthRegistration:
    """Mock für die HA SystemHealthRegistration-Klasse."""
    def __init__(self):
        self.info_callback = None
        self.url = None

    def async_register_info(self, callback, url=None):
        self.info_callback = callback
        self.url = url


def _async_check_can_reach_url(hass, url):
    return f"_check:{url}"


_sh_mod.SystemHealthRegistration = _MockSystemHealthRegistration
_sh_mod.async_check_can_reach_url = _async_check_can_reach_url
sys.modules["homeassistant.components.system_health"] = _sh_mod
# Auch am Parent-MagicMock anhängen, damit `from homeassistant.components import system_health`
# unsere Stub-Implementierung liefert.
sys.modules["homeassistant.components"].system_health = _sh_mod

from custom_components.geosphere_austria_plus import system_health  # noqa: E402
from custom_components.geosphere_austria_plus.const import (  # noqa: E402
    API_BASE,
    OPEN_METEO_API_BASE,
    WARNINGS_API_BASE,
)


class TestSystemHealthRegistration:
    def test_async_register_attaches_info_callback(self):
        hass = MagicMock()
        register = _MockSystemHealthRegistration()
        system_health.async_register(hass, register)
        assert register.info_callback is system_health.system_health_info

    @pytest.mark.asyncio
    async def test_info_returns_all_three_endpoints(self):
        hass = MagicMock()
        result = await system_health.system_health_info(hass)
        assert set(result.keys()) == {
            "can_reach_datahub", "can_reach_warnings", "can_reach_open_meteo"
        }

    @pytest.mark.asyncio
    async def test_info_uses_correct_urls(self):
        hass = MagicMock()
        result = await system_health.system_health_info(hass)
        assert result["can_reach_datahub"] == f"_check:{API_BASE}"
        assert result["can_reach_warnings"] == f"_check:{WARNINGS_API_BASE}"
        assert result["can_reach_open_meteo"] == f"_check:{OPEN_METEO_API_BASE}"
