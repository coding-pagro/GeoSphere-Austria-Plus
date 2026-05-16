"""GeoSphere Austria Plus – Custom Integration mit Conditions & Forecast."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .const import (
    DOMAIN,
    CONF_STATION_ID,
    CONF_FORECAST_MODEL,
    CONF_FORECAST_MODELS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_ENABLE_WARNINGS,
    CONF_ENABLE_AIR_QUALITY,
    CONF_ENABLE_OPEN_METEO,
    DATA_CURRENT,
    DATA_FORECASTS,
    DATA_WARNINGS,
    DATA_AIR_QUALITY,
    DATA_OPEN_METEO_DAILY,
    DEFAULT_FORECAST_MODEL,
)
from .coordinator import (
    GeoSphereCurrentCoordinator,
    GeoSphereForecastCoordinator,
    GeoSphereWarningsCoordinator,
    GeoSphereAirQualityCoordinator,
    GeoSphereOpenMeteoDailyCoordinator,
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
    using_legacy_model_key = False
    if CONF_FORECAST_MODELS in entry.options:
        models: list[str] = entry.options[CONF_FORECAST_MODELS]
    elif CONF_FORECAST_MODELS in entry.data:
        models = entry.data[CONF_FORECAST_MODELS]
    else:
        models = [entry.data.get(CONF_FORECAST_MODEL, DEFAULT_FORECAST_MODEL)]
        using_legacy_model_key = CONF_FORECAST_MODEL in entry.data

    # Deprecation-Issue (sichtbar in HA Repairs) für veraltete forecast_model-Konfig.
    # Issue wird beim nächsten Reload nach Migration automatisch wieder entfernt.
    issue_id = f"deprecated_forecast_model_{entry.entry_id}"
    if using_legacy_model_key:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="deprecated_forecast_model",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)

    # Optionale Features: Options haben Vorrang vor Data, Default = aktiviert
    enable_warnings: bool = entry.options.get(
        CONF_ENABLE_WARNINGS,
        entry.data.get(CONF_ENABLE_WARNINGS, True),
    )
    enable_air_quality: bool = entry.options.get(
        CONF_ENABLE_AIR_QUALITY,
        entry.data.get(CONF_ENABLE_AIR_QUALITY, True),
    )
    enable_open_meteo: bool = entry.options.get(
        CONF_ENABLE_OPEN_METEO,
        entry.data.get(CONF_ENABLE_OPEN_METEO, False),
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

    # Open-Meteo daily tail extension (optional, configurable)
    if enable_open_meteo:
        om_coordinator = GeoSphereOpenMeteoDailyCoordinator(hass, lat, lon)
        try:
            await om_coordinator.async_config_entry_first_refresh()
            coordinators[DATA_OPEN_METEO_DAILY] = om_coordinator
        except ConfigEntryNotReady as err:
            _LOGGER.warning(
                "Open-Meteo nicht erreichbar: %s – Integration läuft ohne Tagesverlängerung weiter",
                err,
            )

    # Set für aktive Entity-Unique-IDs upfront initialisieren, damit Cleanup
    # auch dann robust läuft, wenn eine Plattform mid-setup eine Exception wirft.
    coordinators["_active_unique_ids"] = set()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Veraltete Entities entfernen (z.B. nach Modell-Deaktivierung oder Station-Entfernung).
    # Bei 0 aktiven Entities wird der Set leer → alle veralteten Entities werden entfernt.
    active_ids: set[str] = coordinators.pop("_active_unique_ids")
    ent_reg = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if reg_entry.unique_id not in active_ids:
            _LOGGER.debug("Veraltete Entity entfernen: %s", reg_entry.entity_id)
            ent_reg.async_remove(reg_entry.entity_id)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _iter_coordinators(coordinators: dict):
    """Alle Coordinator-Instanzen aus dem coordinators-Dict liefern.

    Liefert sowohl Top-Level-Coordinator-Werte als auch verschachtelte
    Coordinatoren (z.B. coordinators[DATA_FORECASTS][model]).
    """
    for value in coordinators.values():
        if hasattr(value, "_cancel_pending_retry"):
            yield value
        elif isinstance(value, dict):
            for inner in value.values():
                if hasattr(inner, "_cancel_pending_retry"):
                    yield inner


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Eintrag entladen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinators = hass.data[DOMAIN].pop(entry.entry_id, {})
        # Geplante Retry-Timer/Tasks aller Coordinatoren abbrechen,
        # damit kein Refresh auf einem zerstörten Coordinator läuft.
        for coord in _iter_coordinators(coordinators):
            coord._cancel_pending_retry()
    return unload_ok
