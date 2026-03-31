"""GeoSphere Austria Plus – Custom Integration mit Conditions & Forecast."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

from .const import (
    DOMAIN,
    CONF_STATION_ID,
    CONF_FORECAST_MODEL,
    CONF_FORECAST_MODELS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    DATA_CURRENT,
    DATA_FORECASTS,
    DATA_WARNINGS,
    DATA_AIR_QUALITY,
    DEFAULT_FORECAST_MODEL,
)
from .coordinator import (
    GeoSphereCurrentCoordinator,
    GeoSphereForecastCoordinator,
    GeoSphereWarningsCoordinator,
    GeoSphereAirQualityCoordinator,
)

PLATFORMS = ["weather", "sensor"]


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Eintrag bei Optionsänderung neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Eintrag einrichten."""
    station_id = entry.data[CONF_STATION_ID]

    # Options haben Vorrang (OptionsFlow), dann Data, dann Rückwärtskompatibilität
    models: list[str] = (
        entry.options.get(CONF_FORECAST_MODELS)
        or entry.data.get(CONF_FORECAST_MODELS)
        or [entry.data.get(CONF_FORECAST_MODEL, DEFAULT_FORECAST_MODEL)]
    )

    current_coordinator = GeoSphereCurrentCoordinator(hass, station_id)
    await current_coordinator.async_config_entry_first_refresh()

    # Koordinaten aus Config-Entry lesen; Fallback auf frisch abgerufene Stationsdaten
    lat = entry.data.get(CONF_LATITUDE)
    lon = entry.data.get(CONF_LONGITUDE)
    if lat is None or lon is None:
        station_data = current_coordinator.data or {}
        lat = station_data.get("_lat")
        lon = station_data.get("_lon")
    if lat is None or lon is None:
        raise ConfigEntryNotReady(
            f"Koordinaten für Station {station_id} nicht verfügbar – "
            "bitte Integration neu einrichten."
        )

    forecast_coordinators: dict[str, GeoSphereForecastCoordinator] = {}
    for model in models:
        fc = GeoSphereForecastCoordinator(hass, lat, lon, model)
        await fc.async_config_entry_first_refresh()
        forecast_coordinators[model] = fc

    warnings_coordinator = GeoSphereWarningsCoordinator(hass, lat, lon)
    try:
        await warnings_coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady as err:
        # Warnungs-API ist optional – Integration läuft auch ohne Warnungen
        _LOGGER.warning(
            "Warnungs-API nicht erreichbar: %s – Integration läuft ohne Warnungen weiter",
            err,
        )

    aq_coordinator = GeoSphereAirQualityCoordinator(hass, lat, lon)
    try:
        await aq_coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady as err:
        # Schadstoff-API ist optional – Integration läuft auch ohne Luftqualitätsdaten
        _LOGGER.warning(
            "Schadstoff-API nicht erreichbar: %s – Integration läuft ohne Luftqualitätsdaten weiter",
            err,
        )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_CURRENT: current_coordinator,
        DATA_FORECASTS: forecast_coordinators,
        DATA_WARNINGS: warnings_coordinator,
        DATA_AIR_QUALITY: aq_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Eintrag entladen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
