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
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
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
    CONF_NAME,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DATA_CURRENT,
    DATA_WARNINGS,
    DATA_AIR_QUALITY,
    WARNING_TYPES,
    AQI_BREAKPOINTS,
)
from .coordinator import (
    GeoSphereCurrentCoordinator,
    GeoSphereWarningsCoordinator,
    GeoSphereAirQualityCoordinator,
)


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


@dataclass(frozen=True)
class AirQualitySensorDescription(SensorEntityDescription):
    """SensorEntityDescription für Schadstoff-Sensoren."""
    param: str = ""


AIR_QUALITY_SENSORS: tuple[AirQualitySensorDescription, ...] = (
    AirQualitySensorDescription(
        key="no2",            translation_key="no2",
        param="no2surf",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        device_class=SensorDeviceClass.NITROGEN_DIOXIDE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:molecule",
    ),
    AirQualitySensorDescription(
        key="o3",             translation_key="o3",
        param="o3surf",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        device_class=SensorDeviceClass.OZONE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sun-wireless",
    ),
    AirQualitySensorDescription(
        key="pm10",           translation_key="pm10",
        param="pm10surf",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        device_class=SensorDeviceClass.PM10,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:air-filter",
    ),
    AirQualitySensorDescription(
        key="pm25",           translation_key="pm25",
        param="pm25surf",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:air-filter",
    ),
)

_AQI_ATTR_KEY: dict[str, str] = {
    "no2surf":  "no2_index",
    "o3surf":   "o3_index",
    "pm10surf": "pm10_index",
    "pm25surf": "pm25_index",
}


def _compute_aqi_level(value: float, param: str) -> int:
    """EU-Luftqualitätsstufe (1–6) für einen einzelnen Schadstoff berechnen."""
    for i, threshold in enumerate(AQI_BREAKPOINTS[param]):
        if value < threshold:
            return i + 1
    return 6


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """TAWES-Sensoren, Warnungs-Sensor und Luftqualitäts-Sensoren registrieren."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    entry_id = entry.entry_id
    location_name = (
        entry.options.get(CONF_NAME)
        or entry.data.get(CONF_NAME)
        or entry.title
    )

    entities: list[SensorEntity] = []

    # TAWES-Sensoren nur wenn Station konfiguriert und erreichbar
    current_coordinator = coordinators.get(DATA_CURRENT)
    if current_coordinator is not None:
        entities += [
            TawesSensor(current_coordinator, description, entry_id, location_name)
            for description in SENSORS
        ]

    warnings_coordinator = coordinators.get(DATA_WARNINGS)
    if warnings_coordinator is not None:
        entities.append(
            GeoSphereWarningSensor(warnings_coordinator, entry_id, location_name)
        )

    aq_coordinator = coordinators.get(DATA_AIR_QUALITY)
    if aq_coordinator is not None:
        for description in AIR_QUALITY_SENSORS:
            entities.append(
                AirQualitySensor(aq_coordinator, description, entry_id, location_name)
            )
        entities.append(
            AirQualityIndexSensor(aq_coordinator, entry_id, location_name)
        )

    # Aktive unique_ids für spätere Cleanup-Logik registrieren
    coordinators.setdefault("_active_unique_ids", set()).update(
        e._attr_unique_id for e in entities
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
        entry_id: str,
        location_name: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"geosphere_plus_{entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=location_name,
            manufacturer="Data provided by GeoSphere Austria",
            model=location_name,
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
        entry_id: str,
        location_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"geosphere_plus_{entry_id}_warning_level"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=location_name,
            manufacturer="Data provided by GeoSphere Austria",
            model=location_name,
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


class AirQualitySensor(
    CoordinatorEntity[GeoSphereAirQualityCoordinator], SensorEntity
):
    """Stündlicher Schadstoffwert (erste Vorhersagestunde) als HA-Sensor."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: GeoSphereAirQualityCoordinator,
        description: AirQualitySensorDescription,
        entry_id: str,
        location_name: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"geosphere_plus_{entry_id}_aq_{description.param}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=location_name,
            manufacturer="Data provided by GeoSphere Austria",
            model=location_name,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://dataset.api.hub.geosphere.at/v1",
        )

    @property
    def native_value(self) -> float | None:
        """Wert der ersten Vorhersagestunde (gerundet auf 1 Dezimalstelle)."""
        data = self.coordinator.data
        if not data:
            return None
        values = data.get(self.entity_description.param)
        if not values:
            return None
        return round(values[0], 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """24-Stunden-Vorhersage als Liste von {time, value}-Dicts."""
        data = self.coordinator.data or {}
        timestamps: list[str] = data.get("timestamps", [])
        values: list = data.get(self.entity_description.param, [])
        forecast = [
            {"time": ts, "value": round(v, 1)}
            for ts, v in zip(timestamps[:24], values[:24])
            if v is not None
        ]
        return {"forecast": forecast}


class AirQualityIndexSensor(
    CoordinatorEntity[GeoSphereAirQualityCoordinator], SensorEntity
):
    """EU-Luftqualitätsindex (1–6) aggregiert aus NO₂, O₃, PM10 und PM2.5."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_translation_key = "aqi"

    def __init__(
        self,
        coordinator: GeoSphereAirQualityCoordinator,
        entry_id: str,
        location_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"geosphere_plus_{entry_id}_aqi"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=location_name,
            manufacturer="Data provided by GeoSphere Austria",
            model=location_name,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://dataset.api.hub.geosphere.at/v1",
        )

    @property
    def native_value(self) -> int | None:
        """Höchster EU-Luftqualitätsindex aller Schadstoffe (1=Gut, 6=Extrem schlecht)."""
        data = self.coordinator.data
        if not data:
            return None
        indices = []
        for param in AQI_BREAKPOINTS:
            values = data.get(param)
            if values:
                indices.append(_compute_aqi_level(values[0], param))
        return max(indices) if indices else None

    @property
    def icon(self) -> str:
        level = self.native_value or 1
        if level <= 2:
            return "mdi:leaf"
        if level == 3:
            return "mdi:alert-circle-outline"
        if level == 4:
            return "mdi:alert-circle"
        return "mdi:biohazard"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """EU-Luftqualitätsstufe je Schadstoff."""
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {}
        for param, attr_key in _AQI_ATTR_KEY.items():
            values = data.get(param)
            if values:
                attrs[attr_key] = _compute_aqi_level(values[0], param)
        return attrs
