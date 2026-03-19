"""DataUpdateCoordinator für GeoSphere Austria Plus."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GeoSphereApi, GeoSphereApiError
from .const import (
    DOMAIN,
    CURRENT_UPDATE_INTERVAL,
    FORECAST_UPDATE_INTERVAL,
    DEFAULT_FORECAST_MODEL,
)

_LOGGER = logging.getLogger(__name__)


class GeoSphereCurrentCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Koordinator für aktuelle TAWES-Messwerte."""

    def __init__(
        self,
        hass: HomeAssistant,
        station_id: str,
    ) -> None:
        self.station_id = station_id
        self._api = GeoSphereApi(async_get_clientsession(hass))

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_current_{station_id}",
            update_interval=timedelta(minutes=CURRENT_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self._api.get_current(self.station_id)
        except GeoSphereApiError as err:
            raise UpdateFailed(f"GeoSphere API Fehler: {err}") from err


class GeoSphereForecastCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Koordinator für NWP/Ensemble-Vorhersagen."""

    def __init__(
        self,
        hass: HomeAssistant,
        lat: float,
        lon: float,
        model: str = DEFAULT_FORECAST_MODEL,
    ) -> None:
        self.lat = lat
        self.lon = lon
        self.model = model
        self._api = GeoSphereApi(async_get_clientsession(hass))

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_forecast_{model}",
            update_interval=timedelta(minutes=FORECAST_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> list[dict[str, Any]]:
        try:
            return await self._api.get_forecast(self.lat, self.lon, self.model)
        except GeoSphereApiError as err:
            raise UpdateFailed(f"GeoSphere Vorhersage Fehler: {err}") from err
