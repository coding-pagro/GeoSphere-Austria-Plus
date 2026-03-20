"""GeoSphere Austria Plus – TAWES-Sensoren."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, CONF_STATION_ID, CONF_STATION_NAME, DATA_CURRENT
from .coordinator import GeoSphereCurrentCoordinator


@dataclass(frozen=True)
class TawesSensorDescription(SensorEntityDescription):
    """SensorEntityDescription mit TAWES-Parameternamen."""
    param: str = ""


SENSORS: tuple[TawesSensorDescription, ...] = (
    TawesSensorDescription(
        key="temperature",        translation_key="temperature",
        param="TL",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    TawesSensorDescription(
        key="dew_point",          translation_key="dew_point",
        param="TP",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    TawesSensorDescription(
        key="humidity",           translation_key="humidity",
        param="RF",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    TawesSensorDescription(
        key="wind_direction",     translation_key="wind_direction",
        param="DD",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:compass-rose",
    ),
    TawesSensorDescription(
        key="wind_speed",         translation_key="wind_speed",
        param="FF",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    TawesSensorDescription(
        key="wind_gust",          translation_key="wind_gust",
        param="FX",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    TawesSensorDescription(
        key="pressure",           translation_key="pressure",
        param="P",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    TawesSensorDescription(
        key="pressure_reduced",   translation_key="pressure_reduced",
        param="PRED",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    TawesSensorDescription(
        key="precipitation",      translation_key="precipitation",
        param="RR",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    TawesSensorDescription(
        key="sunshine_duration",  translation_key="sunshine_duration",
        param="SO",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    TawesSensorDescription(
        key="snow_height",        translation_key="snow_height",
        param="SH",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:snowflake",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """TAWES-Sensoren registrieren."""
    station_id = entry.data[CONF_STATION_ID]
    station_name = entry.data.get(CONF_STATION_NAME, station_id)
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_CURRENT]

    async_add_entities(
        TawesSensor(coordinator, description, station_id, station_name)
        for description in SENSORS
    )


class TawesSensor(CoordinatorEntity[GeoSphereCurrentCoordinator], SensorEntity):
    """Einzelner TAWES-Messwert als HA-Sensor."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: GeoSphereCurrentCoordinator,
        description: TawesSensorDescription,
        station_id: str,
        station_name: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"geosphere_plus_{station_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, station_id)},
            name=station_name,
            manufacturer="Data provided by GeoSphere Austria",
            model=station_name,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://dataset.api.hub.geosphere.at/v1",
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.param)
