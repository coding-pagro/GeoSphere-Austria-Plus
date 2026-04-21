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
    WARNINGS_UPDATE_INTERVAL,
    AIR_QUALITY_UPDATE_INTERVAL,
    DEFAULT_FORECAST_MODEL,
)

_LOGGER = logging.getLogger(__name__)

# Fibonacci-artige Retry-Abstände in Minuten (letzter Wert = Maximum)
_RETRY_INTERVALS = (1, 2, 3, 5, 8, 13, 21, 30)


class _RetryMixin:
    """Fibonacci-Backoff-Retry für DataUpdateCoordinator-Subklassen.

    Erwartet, dass die Subklasse folgende Attribute setzt, bevor _retry_init()
    aufgerufen wird:
        self._last_good_data  – wird hier nicht initialisiert (Typ variiert)
        self.hass             – gesetzt durch DataUpdateCoordinator.__init__
    """

    def _retry_init(self) -> None:
        self._retry_step: int = 0
        self._cancel_retry: Any = None

    def _retry_on_success(self, data: Any) -> Any:
        """Daten cachen, Retry-Zähler zurücksetzen, geplante Retries abbrechen."""
        if self._cancel_retry is not None:
            self._cancel_retry()
            self._cancel_retry = None
        self._retry_step = 0
        self._last_good_data = data
        return data

    def _retry_on_failure(self, label: str, err: Exception) -> Any | None:
        """Nächsten Retry planen und gecachte Daten zurückgeben (oder None wenn kein Cache).

        Gibt None zurück wenn kein Cache vorhanden → Aufrufer soll UpdateFailed werfen.
        """
        if self._cancel_retry is not None:
            self._cancel_retry()
            self._cancel_retry = None

        if self._last_good_data is None:
            return None

        delay = _RETRY_INTERVALS[self._retry_step]
        self._retry_step = min(self._retry_step + 1, len(_RETRY_INTERVALS) - 1)
        _LOGGER.warning(
            "%s nicht erreichbar, verwende letzte bekannte Daten (Retry in %d min): %s",
            label, delay, err,
        )
        self._cancel_retry = self.hass.async_call_later(
            delay * 60,
            lambda _: self.hass.async_create_task(self.async_refresh()),
        )
        return self._last_good_data


class GeoSphereCurrentCoordinator(_RetryMixin, DataUpdateCoordinator[dict[str, Any]]):
    """Koordinator für aktuelle TAWES-Messwerte."""

    def __init__(self, hass: HomeAssistant, station_id: str) -> None:
        self.station_id = station_id
        self._api = GeoSphereApi(async_get_clientsession(hass))
        self._last_good_data: dict[str, Any] | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_current_{station_id}",
            update_interval=timedelta(minutes=CURRENT_UPDATE_INTERVAL),
        )
        self._retry_init()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return self._retry_on_success(await self._api.get_current(self.station_id))
        except GeoSphereApiError as err:
            cached = self._retry_on_failure("GeoSphere TAWES", err)
            if cached is not None:
                return cached
            raise UpdateFailed(f"GeoSphere API Fehler: {err}") from err


class GeoSphereForecastCoordinator(_RetryMixin, DataUpdateCoordinator[list[dict[str, Any]]]):
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
        self._last_good_data: list[dict[str, Any]] | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_forecast_{model}_{lat}_{lon}",
            update_interval=timedelta(minutes=FORECAST_UPDATE_INTERVAL),
        )
        self._retry_init()

    async def _async_update_data(self) -> list[dict[str, Any]]:
        try:
            return self._retry_on_success(
                await self._api.get_forecast(self.lat, self.lon, self.model)
            )
        except GeoSphereApiError as err:
            cached = self._retry_on_failure(f"GeoSphere Vorhersage ({self.model})", err)
            if cached is not None:
                return cached
            raise UpdateFailed(f"GeoSphere Vorhersage Fehler: {err}") from err


class GeoSphereWarningsCoordinator(_RetryMixin, DataUpdateCoordinator[list[dict[str, Any]]]):
    """Koordinator für Wetterwarnungen (warnungen.zamg.at)."""

    def __init__(self, hass: HomeAssistant, lat: float, lon: float) -> None:
        self.lat = lat
        self.lon = lon
        self._api = GeoSphereApi(async_get_clientsession(hass))
        self._last_good_data: list[dict[str, Any]] | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_warnings_{lat}_{lon}",
            update_interval=timedelta(minutes=WARNINGS_UPDATE_INTERVAL),
        )
        self._retry_init()

    async def _async_update_data(self) -> list[dict[str, Any]]:
        try:
            return self._retry_on_success(
                await self._api.get_warnings(self.lat, self.lon)
            )
        except GeoSphereApiError as err:
            cached = self._retry_on_failure("Warnungs-API", err)
            if cached is not None:
                return cached
            raise UpdateFailed(f"Warnungs-API Fehler: {err}") from err


class GeoSphereAirQualityCoordinator(_RetryMixin, DataUpdateCoordinator[dict[str, Any]]):
    """Koordinator für die stündliche Schadstoffvorhersage (chem-v2-1h-3km)."""

    def __init__(self, hass: HomeAssistant, lat: float, lon: float) -> None:
        self.lat = lat
        self.lon = lon
        self._api = GeoSphereApi(async_get_clientsession(hass))
        self._last_good_data: dict[str, Any] | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_air_quality_{lat}_{lon}",
            update_interval=timedelta(minutes=AIR_QUALITY_UPDATE_INTERVAL),
        )
        self._retry_init()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return self._retry_on_success(
                await self._api.get_air_quality(self.lat, self.lon)
            )
        except GeoSphereApiError as err:
            cached = self._retry_on_failure("Luftqualitäts-API", err)
            if cached is not None:
                return cached
            raise UpdateFailed(f"Schadstoff-API Fehler: {err}") from err
