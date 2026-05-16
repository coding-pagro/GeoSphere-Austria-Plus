"""Mock Home Assistant modules before any integration code is imported."""
import sys
import types
from dataclasses import dataclass as _dataclass
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Lightweight stand-ins for Home Assistant classes
# ---------------------------------------------------------------------------

class _MockForecast(dict):
    """Dict-basierter Stub für HA Forecast TypedDict.

    Das echte HA Forecast ist ein TypedDict (= dict zur Laufzeit).
    Beide Zugriffsarten müssen funktionieren:
      forecast.native_temperature  (Attributzugriff – bestehende Tests)
      forecast["solar_irradiance"] (Dict-Zugriff – für Extra-Felder)
    """

    def __init__(self, **kwargs):
        super().__init__(kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        setattr(self, key, value)


class _MockWeatherEntityFeature:
    FORECAST_HOURLY = 1
    FORECAST_DAILY = 2


class _MockWeatherEntity:
    @property
    def supported_features(self):
        """Mirror HA: derive from _attr_supported_features class/instance attribute."""
        return getattr(self, "_attr_supported_features", 0)


class _MockCoordinatorEntity:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def available(self) -> bool:
        """Mirror real CoordinatorEntity: unavailable when coordinator has no data.

        Real HA: returns ``self.coordinator.last_update_success and super().available``.
        For tests, the closest pragmatic stand-in is "data is populated" — most
        tests set coordinator.data = None to mean unavailable.
        """
        return self.coordinator.data is not None

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

    async def async_refresh(self):
        pass

    def async_add_listener(self, func):
        return lambda: None


class _MockUpdateFailed(Exception):
    """Mirror HA's UpdateFailed: accepts translation_domain/key/placeholders kwargs."""
    def __init__(self, message: str = "", *, translation_domain: str | None = None,
                 translation_key: str | None = None,
                 translation_placeholders: dict | None = None) -> None:
        super().__init__(message)
        self.translation_domain = translation_domain
        self.translation_key = translation_key
        self.translation_placeholders = translation_placeholders or {}


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
    IRRADIANCE = "irradiance"
    NITROGEN_DIOXIDE = "nitrogen_dioxide"
    OZONE = "ozone"
    PM10 = "pm10"
    PM25 = "pm25"


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

# Production code imports WeatherEntityFeature from the .const submodule
# (correct path per mypy strict reexport rules). Mirror it.
_weather_const_mod = MagicMock()
_weather_const_mod.WeatherEntityFeature = _MockWeatherEntityFeature

_coordinator_mod = MagicMock()
_coordinator_mod.DataUpdateCoordinator = _MockDataUpdateCoordinator
_coordinator_mod.UpdateFailed = _MockUpdateFailed
_coordinator_mod.CoordinatorEntity = _MockCoordinatorEntity

_const_mod = MagicMock()
_const_mod.UnitOfTemperature.CELSIUS = "°C"
_const_mod.UnitOfPressure.HPA = "hPa"
_const_mod.UnitOfSpeed.METERS_PER_SECOND = "m/s"
_const_mod.UnitOfLength.MILLIMETERS = "mm"
_const_mod.UnitOfLength.CENTIMETERS = "cm"
_const_mod.UnitOfIrradiance.WATTS_PER_SQUARE_METER = "W/m²"
_const_mod.UnitOfTime.SECONDS = "s"
_const_mod.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER = "µg/m³"
_const_mod.DEGREE = "°"
_const_mod.PERCENTAGE = "%"

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
# Production code now imports DeviceInfo from device_registry (canonical location
# per HA 2024.10+ deprecation of homeassistant.helpers.entity.DeviceInfo).
_device_registry_mod.DeviceInfo = _MockDeviceInfo

# Selector module: SelectOptionDict is a TypedDict (dict at runtime). Mock it
# as a callable that returns a real dict so test asserts on result[i]["value"]
# work — otherwise MagicMock() returns yet another MagicMock.
_selector_mod = MagicMock()
_selector_mod.SelectOptionDict = lambda **kwargs: dict(kwargs)

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
        self.hass = MagicMock()
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

# Production code now imports ConfigEntryNotReady from homeassistant.exceptions
# (the canonical location per mypy strict reexport rules). Mirror the symbol
# in our mock so both import paths resolve.
_exceptions_mod = MagicMock()
_exceptions_mod.ConfigEntryNotReady = _config_entries_mod.ConfigEntryNotReady
_exceptions_mod.HomeAssistantError = Exception

# Echtes Modulobjekt für homeassistant, damit `from homeassistant import config_entries`
# das richtige Mock-Objekt liefert (MagicMock.__getattr__ überschreibt sonst den Wert).
_ha_mod = types.ModuleType("homeassistant")
_ha_mod.config_entries = _config_entries_mod

_core_mod = MagicMock()
# @callback ist in HA ein no-op-Decorator → durchreichen, sonst werden
# dekorierte Funktionen durch MagicMocks ersetzt.
_core_mod.callback = lambda f: f

sys.modules.update(
    {
        "homeassistant": _ha_mod,
        "homeassistant.components": MagicMock(),
        "homeassistant.components.sensor": _sensor_mod,
        "homeassistant.components.weather": _weather_mod,
        "homeassistant.components.weather.const": _weather_const_mod,
        "homeassistant.config_entries": _config_entries_mod,
        "homeassistant.exceptions": _exceptions_mod,
        "homeassistant.const": _const_mod,
        "homeassistant.core": _core_mod,
        "homeassistant.helpers": MagicMock(),
        "homeassistant.helpers.aiohttp_client": MagicMock(),
        "homeassistant.helpers.device_registry": _device_registry_mod,
        "homeassistant.helpers.entity": _entity_mod,
        "homeassistant.helpers.entity_platform": MagicMock(),
        "homeassistant.helpers.event": MagicMock(),
        "homeassistant.helpers.update_coordinator": _coordinator_mod,
        "homeassistant.helpers.selector": _selector_mod,
        "homeassistant.helpers.entity_registry": MagicMock(),
        "voluptuous": MagicMock(),
    }
)

# Pre-import integration modules so class definitions run with the correct
# sys.modules state, before test files trigger their own imports.
from custom_components.geosphere_austria_plus import weather as _weather_module  # noqa: E402
from custom_components.geosphere_austria_plus import config_flow as _config_flow_module  # noqa: E402
from custom_components.geosphere_austria_plus import coordinator as _coordinator_module  # noqa: E402

# Production code uses module-level `async_call_later(hass, delay, cb)` from
# homeassistant.helpers.event (the correct HA API; hass.async_call_later
# doesn't exist). Existing tests still assert on `coord.hass.async_call_later`
# for ergonomics, so we forward calls through the hass mock here.
def _forward_async_call_later(hass, delay, callback):  # type: ignore[no-untyped-def]
    return hass.async_call_later(delay, callback)


_coordinator_module.async_call_later = _forward_async_call_later
