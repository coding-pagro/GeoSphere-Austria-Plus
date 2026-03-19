"""GeoSphere Austria Plus – Custom Integration mit Conditions & Forecast."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_STATION_ID, CONF_FORECAST_MODEL, DEFAULT_FORECAST_MODEL
from .coordinator import GeoSphereCurrentCoordinator, GeoSphereForecastCoordinator

PLATFORMS = ["weather"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Eintrag einrichten."""
    station_id = entry.data[CONF_STATION_ID]
    model = entry.data.get(CONF_FORECAST_MODEL, DEFAULT_FORECAST_MODEL)
    lat = entry.data.get("lat")
    lon = entry.data.get("lon")

    current_coordinator = GeoSphereCurrentCoordinator(hass, station_id)
    forecast_coordinator = GeoSphereForecastCoordinator(hass, lat, lon, model)

    await current_coordinator.async_config_entry_first_refresh()
    await forecast_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "current": current_coordinator,
        "forecast": forecast_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Eintrag entladen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
