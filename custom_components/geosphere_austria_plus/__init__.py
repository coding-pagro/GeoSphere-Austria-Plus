"""GeoSphere Austria Plus – Custom Integration mit Conditions & Forecast."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    CONF_STATION_ID,
    CONF_FORECAST_MODEL,
    CONF_FORECAST_MODELS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_ENABLE_WARNINGS,
    CONF_ENABLE_AIR_QUALITY,
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

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.WEATHER, Platform.SENSOR]


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Eintrag bei Optionsänderung neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Eintrag einrichten."""
    # Koordinaten: Options haben Vorrang vor Data
    lat: float = (
        entry.options[CONF_LATITUDE]
        if CONF_LATITUDE in entry.options
        else entry.data[CONF_LATITUDE]
    )
    lon: float = (
        entry.options[CONF_LONGITUDE]
        if CONF_LONGITUDE in entry.options
        else entry.data[CONF_LONGITUDE]
    )

    # Station ist optional
    if CONF_STATION_ID in entry.options:
        station_id: str | None = entry.options[CONF_STATION_ID] or None
    else:
        station_id = entry.data.get(CONF_STATION_ID) or None

    # Vorhersagemodelle: Options → Data → Rückwärtskompatibilität (leere Liste = kein Forecast)
    if CONF_FORECAST_MODELS in entry.options:
        models: list[str] = entry.options[CONF_FORECAST_MODELS]
    elif CONF_FORECAST_MODELS in entry.data:
        models = entry.data[CONF_FORECAST_MODELS]
    else:
        models = [entry.data.get(CONF_FORECAST_MODEL, DEFAULT_FORECAST_MODEL)]

    # Optionale Features: Options haben Vorrang vor Data, Default = aktiviert
    enable_warnings: bool = entry.options.get(
        CONF_ENABLE_WARNINGS,
        entry.data.get(CONF_ENABLE_WARNINGS, True),
    )
    enable_air_quality: bool = entry.options.get(
        CONF_ENABLE_AIR_QUALITY,
        entry.data.get(CONF_ENABLE_AIR_QUALITY, True),
    )

    coordinators: dict = {DATA_FORECASTS: {}}

    # TAWES-Koordinator nur wenn Station konfiguriert
    if station_id:
        current_coordinator = GeoSphereCurrentCoordinator(hass, station_id)
        try:
            await current_coordinator.async_config_entry_first_refresh()
            coordinators[DATA_CURRENT] = current_coordinator
        except ConfigEntryNotReady as err:
            _LOGGER.warning(
                "TAWES-Station %s nicht erreichbar: %s – Integration läuft ohne Stationsdaten",
                station_id,
                err,
            )

    # Vorhersage-Koordinatoren (immer, basierend auf konfigurierten Koordinaten)
    # ConfigEntryNotReady propagiert hier bewusst – Forecasts sind Kernfunktionalität
    for model in models:
        fc = GeoSphereForecastCoordinator(hass, lat, lon, model)
        await fc.async_config_entry_first_refresh()
        coordinators[DATA_FORECASTS][model] = fc

    # Warnungs-Koordinator (optional, konfigurierbar)
    if enable_warnings:
        warnings_coordinator = GeoSphereWarningsCoordinator(hass, lat, lon)
        try:
            await warnings_coordinator.async_config_entry_first_refresh()
            coordinators[DATA_WARNINGS] = warnings_coordinator
        except ConfigEntryNotReady as err:
            _LOGGER.warning(
                "Warnungs-API nicht erreichbar: %s – Integration läuft ohne Warnungen weiter",
                err,
            )

    # Luftqualitäts-Koordinator (optional, konfigurierbar)
    if enable_air_quality:
        aq_coordinator = GeoSphereAirQualityCoordinator(hass, lat, lon)
        try:
            await aq_coordinator.async_config_entry_first_refresh()
            coordinators[DATA_AIR_QUALITY] = aq_coordinator
        except ConfigEntryNotReady as err:
            _LOGGER.warning(
                "Schadstoff-API nicht erreichbar: %s – Integration läuft ohne Luftqualitätsdaten weiter",
                err,
            )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Veraltete Entities entfernen (z.B. nach Modell-Deaktivierung oder Station-Entfernung).
    # Beide Plattformen befüllen _active_unique_ids immer (auch bei 0 Entities),
    # sodass dieser Schlüssel nach async_forward_entry_setups immer vorhanden ist.
    # Bei 0 aktiven Entities wird der Set leer → alle veralteten Entities werden entfernt.
    if "_active_unique_ids" in coordinators:
        active_ids: set[str] = coordinators.pop("_active_unique_ids")
        ent_reg = er.async_get(hass)
        for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            if reg_entry.unique_id not in active_ids:
                _LOGGER.debug("Veraltete Entity entfernen: %s", reg_entry.entity_id)
                ent_reg.async_remove(reg_entry.entity_id)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Eintrag entladen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
