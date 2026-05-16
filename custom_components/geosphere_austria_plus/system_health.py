"""System-Health-Integration für GeoSphere Austria Plus.

Zeigt auf der "System Health"-Seite in HA die Erreichbarkeit der drei
Backend-Endpunkte (GeoSphere DataHub, Warnungs-API, Open-Meteo).
"""
from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import API_BASE, OPEN_METEO_API_BASE, WARNINGS_API_BASE


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """System-Health-Callback registrieren."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Endpunkt-Erreichbarkeit für die System-Health-Karte."""
    return {
        "can_reach_datahub": system_health.async_check_can_reach_url(hass, API_BASE),
        "can_reach_warnings": system_health.async_check_can_reach_url(
            hass, WARNINGS_API_BASE
        ),
        "can_reach_open_meteo": system_health.async_check_can_reach_url(
            hass, OPEN_METEO_API_BASE
        ),
    }
