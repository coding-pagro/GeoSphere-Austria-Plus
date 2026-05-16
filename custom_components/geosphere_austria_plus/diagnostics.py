"""Diagnostics-Support für GeoSphere Austria Plus."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    DATA_AIR_QUALITY,
    DATA_CURRENT,
    DATA_FORECASTS,
    DATA_OPEN_METEO_DAILY,
    DATA_WARNINGS,
    DOMAIN,
)

# Vollredaktion für Felder, die nicht für Diagnose nötig sind.
TO_REDACT = {"station_id"}


def _round_coords(data: dict[str, Any]) -> dict[str, Any]:
    """Lat/Lon auf 2 Dezimalen runden (~1 km Auflösung) — Privacy-Kompromiss."""
    result = dict(data)
    for key in (CONF_LATITUDE, CONF_LONGITUDE):
        if key in result and isinstance(result[key], (int, float)):
            result[key] = round(float(result[key]), 2)
    return result


def _coordinator_snapshot(coord: Any) -> dict[str, Any]:
    """Minimaler Coordinator-State ohne Rohdaten (die enthalten ggf. Stationskoords)."""
    data = getattr(coord, "data", None)
    snapshot: dict[str, Any] = {
        "name": getattr(coord, "name", None),
        "last_update_success": getattr(coord, "last_update_success", None),
        "update_interval_seconds": (
            coord.update_interval.total_seconds()
            if getattr(coord, "update_interval", None) is not None
            else None
        ),
        "retry_step": getattr(coord, "_retry_step", None),
        "has_cached_data": getattr(coord, "_last_good_data", None) is not None,
        "data_present": data is not None,
    }
    # Typ-abhängige Größenangabe (Sensoren sind ggf. an exakter Datenform interessiert)
    if isinstance(data, dict):
        snapshot["data_keys"] = sorted(data.keys())
    elif isinstance(data, list):
        snapshot["data_entries"] = len(data)
    return snapshot


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Diagnose-Daten für einen Config-Entry liefern.

    Enthält redaktierte Config-Daten und einen Coordinator-Statusüberblick —
    aber **keine** Rohdaten der GeoSphere-/Open-Meteo-Antworten, weil dort
    teils präzise Stationskoordinaten enthalten sind.
    """
    coordinators: dict[str, Any] = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})

    coord_diagnostics: dict[str, Any] = {}

    current = coordinators.get(DATA_CURRENT)
    if current is not None:
        coord_diagnostics[DATA_CURRENT] = _coordinator_snapshot(current)

    forecasts = coordinators.get(DATA_FORECASTS, {})
    if forecasts:
        coord_diagnostics[DATA_FORECASTS] = {
            model: _coordinator_snapshot(coord) for model, coord in forecasts.items()
        }

    for key in (DATA_WARNINGS, DATA_AIR_QUALITY, DATA_OPEN_METEO_DAILY):
        coord = coordinators.get(key)
        if coord is not None:
            coord_diagnostics[key] = _coordinator_snapshot(coord)

    return {
        "config_entry": {
            "title": entry.title,
            "version": entry.version,
            "data": async_redact_data(_round_coords(dict(entry.data)), TO_REDACT),
            "options": async_redact_data(_round_coords(dict(entry.options)), TO_REDACT),
        },
        "coordinators": coord_diagnostics,
    }
