"""Mock Home Assistant modules before any integration code is imported."""
import sys
import types
from dataclasses import dataclass as _dataclass
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

class _MockSensorEntity:
    pass


class _MockSensorDeviceClass:
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    PRESSURE = "pressure"
    WIND_SPEED = "wind_speed"
    PRECIPITATION = "precipitation"
    DURATION = "duration"


class _MockSensorStateClass:
    MEASUREMENT = "measurement"


@_dataclass(frozen=True)
class _MockSensorEntityDescription:
    """Minimaler Stub für SensorEntityDescription (frozen dataclass wie das Original)."""
    key: str = ""
    name: str | None = None
    icon: str | None = None
    device_class: object = None
    native_unit_of_measurement: str | None = None
    state_class: object = None
    entity_category: object = None
    translation_key: str | None = None
    entity_registry_enabled_default: bool = True


_sensor_mod = MagicMock()
_sensor_mod.SensorEntity = _MockSensorEntity
_sensor_mod.SensorDeviceClass = _MockSensorDeviceClass
_sensor_mod.SensorStateClass = _MockSensorStateClass
_sensor_mod.SensorEntityDescription = _MockSensorEntityDescription

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

class _MockDeviceInfo(dict):
    """Minimal stand-in for DeviceInfo (TypedDict subclass in HA)."""
    def __init__(self, **kwargs):
        super().__init__(kwargs)
        for k, v in kwargs.items():
            setattr(self, k, v)


class _MockDeviceEntryType:
    SERVICE = "service"


_entity_mod = MagicMock()
_entity_mod.DeviceInfo = _MockDeviceInfo

_device_registry_mod = MagicMock()
_device_registry_mod.DeviceEntryType = _MockDeviceEntryType

class _MockConfigFlow:
    """Minimal stand-in for config_entries.ConfigFlow."""

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    def __init__(self):
        self.hass = MagicMock()

    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, step_id, data_schema=None, errors=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}}

    def _abort_if_unique_id_configured(self):
        pass

    async def async_set_unique_id(self, unique_id):
        pass


class _MockOptionsFlow:
    """Minimal stand-in for config_entries.OptionsFlow."""

    def __init__(self):
        self.config_entry = MagicMock()
        self.config_entry.options = {}
        self.config_entry.data = {}

    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, step_id, data_schema=None, errors=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}}


_config_entries_mod = MagicMock()
_config_entries_mod.ConfigFlow = _MockConfigFlow
_config_entries_mod.OptionsFlow = _MockOptionsFlow
_config_entries_mod.ConfigEntryNotReady = Exception
_config_entries_mod.callback = lambda f: f

# Echtes Modulobjekt für homeassistant, damit `from homeassistant import config_entries`
# das richtige Mock-Objekt liefert (MagicMock.__getattr__ überschreibt sonst den Wert).
_ha_mod = types.ModuleType("homeassistant")
_ha_mod.config_entries = _config_entries_mod

sys.modules.update(
    {
        "homeassistant": _ha_mod,
        "homeassistant.components": MagicMock(),
        "homeassistant.components.sensor": _sensor_mod,
        "homeassistant.components.weather": _weather_mod,
        "homeassistant.config_entries": _config_entries_mod,
        "homeassistant.const": _const_mod,
        "homeassistant.core": MagicMock(),
        "homeassistant.helpers": MagicMock(),
        "homeassistant.helpers.aiohttp_client": MagicMock(),
        "homeassistant.helpers.device_registry": _device_registry_mod,
        "homeassistant.helpers.entity": _entity_mod,
        "homeassistant.helpers.entity_platform": MagicMock(),
        "homeassistant.helpers.update_coordinator": _coordinator_mod,
        "homeassistant.helpers.selector": MagicMock(),
        "voluptuous": MagicMock(),
    }
)

# Pre-import integration modules so class definitions run with the correct
# sys.modules state, before test files trigger their own imports.
from custom_components.geosphere_austria_plus import weather as _weather_module  # noqa: E402
from custom_components.geosphere_austria_plus import config_flow as _config_flow_module  # noqa: E402
