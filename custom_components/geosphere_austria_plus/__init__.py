"""GeoSphere Austria Plus – Custom Integration mit Conditions & Forecast."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_STATION_ID,
    CONF_FORECAST_MODEL,
    CONF_FORECAST_MODELS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    DATA_CURRENT,
    DATA_FORECASTS,
    DEFAULT_FORECAST_MODEL,
)
from .coordinator import GeoSphereCurrentCoordinator, GeoSphereForecastCoordinator

PLATFORMS = ["weather", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Eintrag einrichten."""
    station_id = entry.data[CONF_STATION_ID]
    lat = entry.data.get(CONF_LATITUDE)
    lon = entry.data.get(CONF_LONGITUDE)

    # Rückwärtskompatibilität: alter Eintrag hat einzelnes Modell (String)
    models: list[str] = entry.data.get(CONF_FORECAST_MODELS) or [
        entry.data.get(CONF_FORECAST_MODEL, DEFAULT_FORECAST_MODEL)
    ]

    current_coordinator = GeoSphereCurrentCoordinator(hass, station_id)
    await current_coordinator.async_config_entry_first_refresh()

    forecast_coordinators: dict[str, GeoSphereForecastCoordinator] = {}
    for model in models:
        fc = GeoSphereForecastCoordinator(hass, lat, lon, model)
        await fc.async_config_entry_first_refresh()
        forecast_coordinators[model] = fc

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_CURRENT: current_coordinator,
        DATA_FORECASTS: forecast_coordinators,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Eintrag entladen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
