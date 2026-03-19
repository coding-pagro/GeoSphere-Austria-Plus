"""Mock Home Assistant modules before any integration code is imported."""
import sys
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Lightweight stand-ins for Home Assistant classes
# ---------------------------------------------------------------------------

class _MockForecast:
    """Accepts the same keyword arguments as the real HA Forecast TypedDict."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _MockWeatherEntityFeature:
    FORECAST_HOURLY = 1
    FORECAST_DAILY = 2


class _MockWeatherEntity:
    pass


class _MockCoordinatorEntity:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, coordinator):
        self.coordinator = coordinator

    async def async_added_to_hass(self):
        pass

    def async_on_remove(self, func):
        pass

    def async_write_ha_state(self):
        pass


class _MockDataUpdateCoordinator:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass=None, logger=None, name=None, update_interval=None):
        self.data = None
        self.hass = hass

    async def async_request_refresh(self):
        pass

    def async_add_listener(self, func):
        return lambda: None


class _MockUpdateFailed(Exception):
    pass


# ---------------------------------------------------------------------------
# Build mock modules and inject into sys.modules
# ---------------------------------------------------------------------------

_weather_mod = MagicMock()
_weather_mod.Forecast = _MockForecast
_weather_mod.WeatherEntity = _MockWeatherEntity
_weather_mod.WeatherEntityFeature = _MockWeatherEntityFeature

_coordinator_mod = MagicMock()
_coordinator_mod.DataUpdateCoordinator = _MockDataUpdateCoordinator
_coordinator_mod.UpdateFailed = _MockUpdateFailed
_coordinator_mod.CoordinatorEntity = _MockCoordinatorEntity

_const_mod = MagicMock()
_const_mod.UnitOfTemperature.CELSIUS = "°C"
_const_mod.UnitOfPressure.HPA = "hPa"
_const_mod.UnitOfSpeed.METERS_PER_SECOND = "m/s"
_const_mod.UnitOfLength.MILLIMETERS = "mm"

sys.modules.update(
    {
        "homeassistant": MagicMock(),
        "homeassistant.components": MagicMock(),
        "homeassistant.components.weather": _weather_mod,
        "homeassistant.config_entries": MagicMock(),
        "homeassistant.const": _const_mod,
        "homeassistant.core": MagicMock(),
        "homeassistant.helpers": MagicMock(),
        "homeassistant.helpers.aiohttp_client": MagicMock(),
        "homeassistant.helpers.entity_platform": MagicMock(),
        "homeassistant.helpers.update_coordinator": _coordinator_mod,
        "voluptuous": MagicMock(),
    }
)
