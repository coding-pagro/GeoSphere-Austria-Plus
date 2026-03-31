"""GeoSphere Austria Plus – TAWES-Sensoren und Wetterwarnungen."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

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

from .const import (
    ATTRIBUTION,
    DOMAIN,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DATA_CURRENT,
    DATA_WARNINGS,
    WARNING_TYPES,
)
from .coordinator import GeoSphereCurrentCoordinator, GeoSphereWarningsCoordinator


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
    """TAWES-Sensoren und Warnungs-Sensor registrieren."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    station_id = entry.data[CONF_STATION_ID]
    station_name = entry.data.get(CONF_STATION_NAME, station_id)

    entities: list[SensorEntity] = [
        TawesSensor(coordinators[DATA_CURRENT], description, station_id, station_name)
        for description in SENSORS
    ]

    warnings_coordinator = coordinators.get(DATA_WARNINGS)
    if warnings_coordinator is not None:
        entities.append(
            GeoSphereWarningSensor(warnings_coordinator, station_id, station_name)
        )

    async_add_entities(entities)


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


class GeoSphereWarningSensor(
    CoordinatorEntity[GeoSphereWarningsCoordinator], SensorEntity
):
    """Höchste aktive Warnstufe für eine Station (0 = keine, 1–3 = gelb/orange/rot)."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_translation_key = "warning_level"

    def __init__(
        self,
        coordinator: GeoSphereWarningsCoordinator,
        station_id: str,
        station_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"geosphere_plus_{station_id}_warning_level"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, station_id)},
            name=station_name,
            manufacturer="Data provided by GeoSphere Austria",
            model=station_name,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://dataset.api.hub.geosphere.at/v1",
        )

    @property
    def native_value(self) -> int:
        """Höchste aktive Warnstufe (0 wenn keine Warnungen)."""
        warnings = self.coordinator.data or []
        if not warnings:
            return 0
        return max(w["level"] for w in warnings)

    @property
    def icon(self) -> str:
        level = self.native_value
        if level == 0:
            return "mdi:alert-outline"
        if level == 1:
            return "mdi:alert"
        return "mdi:alert-circle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Alle aktiven Warnungen als strukturierte Attribute."""
        warnings = self.coordinator.data or []
        result = []
        for w in warnings:
            entry: dict[str, Any] = {
                "type": WARNING_TYPES.get(w["type_id"], str(w["type_id"])),
                "level": w["level"],
                "text": w["text"],
            }
            if w.get("begin") is not None:
                entry["begin"] = datetime.fromtimestamp(
                    w["begin"], tz=timezone.utc
                ).isoformat()
            if w.get("end") is not None:
                entry["end"] = datetime.fromtimestamp(
                    w["end"], tz=timezone.utc
                ).isoformat()
            if w.get("effects"):
                entry["effects"] = w["effects"]
            if w.get("recommendations"):
                entry["recommendations"] = w["recommendations"]
            result.append(entry)
        return {"warnings": result}
