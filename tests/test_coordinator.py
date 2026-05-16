"""Tests für Coordinator-Fallback und Fibonacci-Retry bei API-Fehlern."""
from __future__ import annotations

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, call

# conftest already populated sys.modules with HA stubs.
# Import from the mocked module so isinstance checks match.
from homeassistant.helpers.update_coordinator import UpdateFailed as _UpdateFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator as _BaseCoordinator

from custom_components.geosphere_austria_plus.coordinator import (
    GeoSphereCurrentCoordinator,
    GeoSphereForecastCoordinator,
    GeoSphereWarningsCoordinator,
    GeoSphereAirQualityCoordinator,
    _RETRY_INTERVALS,
)
from custom_components.geosphere_austria_plus.api import GeoSphereApiError


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def _make_coordinator(cls, **kwargs):
    """Erstellt einen Koordinator mit gemocktem hass und API."""
    hass = MagicMock()
    coord = cls.__new__(cls)
    _BaseCoordinator.__init__(coord, hass=hass)
    coord._last_good_data = None
    coord._retry_step = 0
    coord._cancel_retry = None
    coord._pending_retry_task = None
    coord._api = MagicMock()
    for k, v in kwargs.items():
        setattr(coord, k, v)
    return coord


# ---------------------------------------------------------------------------
# GeoSphereCurrentCoordinator – Basis-Fallback
# ---------------------------------------------------------------------------

class TestCurrentCoordinatorFallback:
    @pytest.mark.asyncio
    async def test_returns_fresh_data_on_success(self):
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        fresh = {"TL": 20.0}
        coord._api.get_current = AsyncMock(return_value=fresh)

        result = await coord._async_update_data()

        assert result == fresh
        assert coord._last_good_data == fresh

    @pytest.mark.asyncio
    async def test_returns_cached_data_on_api_error(self):
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        cached = {"TL": 18.5}
        coord._last_good_data = cached
        coord._api.get_current = AsyncMock(side_effect=GeoSphereApiError("timeout"))

        result = await coord._async_update_data()

        assert result == cached

    @pytest.mark.asyncio
    async def test_raises_update_failed_without_cache(self):
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        coord._api.get_current = AsyncMock(side_effect=GeoSphereApiError("timeout"))

        with pytest.raises(_UpdateFailed):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_cache_is_updated_after_recovery(self):
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        coord._last_good_data = {"TL": 18.5}
        new_data = {"TL": 22.0}
        coord._api.get_current = AsyncMock(return_value=new_data)

        result = await coord._async_update_data()

        assert result == new_data
        assert coord._last_good_data == new_data


# ---------------------------------------------------------------------------
# Retry-Mechanismus (_RetryMixin)
# ---------------------------------------------------------------------------

class TestRetryMechanism:
    @pytest.mark.asyncio
    async def test_first_failure_schedules_retry_after_1_min(self):
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        coord._last_good_data = {"TL": 18.5}
        coord._api.get_current = AsyncMock(side_effect=GeoSphereApiError("timeout"))

        await coord._async_update_data()

        coord.hass.async_call_later.assert_called_once()
        delay = coord.hass.async_call_later.call_args[0][0]
        assert delay == _RETRY_INTERVALS[0] * 60  # 1 Minute

    @pytest.mark.asyncio
    async def test_retry_step_increments_on_each_failure(self):
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        coord._last_good_data = {"TL": 18.5}
        coord._api.get_current = AsyncMock(side_effect=GeoSphereApiError("timeout"))

        for expected_step in range(len(_RETRY_INTERVALS)):
            coord._retry_step = expected_step
            await coord._async_update_data()
            expected_delay = _RETRY_INTERVALS[min(expected_step, len(_RETRY_INTERVALS) - 1)] * 60
            delay = coord.hass.async_call_later.call_args[0][0]
            assert delay == expected_delay

    @pytest.mark.asyncio
    async def test_retry_step_caps_at_max(self):
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        coord._last_good_data = {"TL": 18.5}
        coord._retry_step = len(_RETRY_INTERVALS) - 1  # schon am Maximum
        coord._api.get_current = AsyncMock(side_effect=GeoSphereApiError("timeout"))

        await coord._async_update_data()

        assert coord._retry_step == len(_RETRY_INTERVALS) - 1  # bleibt am Maximum
        delay = coord.hass.async_call_later.call_args[0][0]
        assert delay == _RETRY_INTERVALS[-1] * 60  # 30 Minuten

    @pytest.mark.asyncio
    async def test_success_resets_retry_step(self):
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        coord._last_good_data = {"TL": 18.5}
        coord._retry_step = 4
        coord._api.get_current = AsyncMock(return_value={"TL": 20.0})

        await coord._async_update_data()

        assert coord._retry_step == 0

    @pytest.mark.asyncio
    async def test_success_cancels_pending_retry(self):
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        coord._last_good_data = {"TL": 18.5}
        cancel_mock = MagicMock()
        coord._cancel_retry = cancel_mock
        coord._api.get_current = AsyncMock(return_value={"TL": 20.0})

        await coord._async_update_data()

        cancel_mock.assert_called_once()
        assert coord._cancel_retry is None

    @pytest.mark.asyncio
    async def test_new_failure_cancels_previous_scheduled_retry(self):
        """Wenn ein Refresh (z.B. reguläres Intervall) feuert bevor der Retry feuert,
        soll der geplante Retry zuerst abgebrochen werden."""
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        coord._last_good_data = {"TL": 18.5}
        old_cancel = MagicMock()
        coord._cancel_retry = old_cancel
        coord._api.get_current = AsyncMock(side_effect=GeoSphereApiError("timeout"))

        await coord._async_update_data()

        old_cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_fibonacci_sequence_matches_expected(self):
        """Vollständige Fibonacci-Sequenz: 1,2,3,5,8,13,21,30 Minuten."""
        assert _RETRY_INTERVALS == (1, 2, 3, 5, 8, 13, 21, 30)


# ---------------------------------------------------------------------------
# Retry-Lifecycle (H2): Task-Tracking und Cancel auf Shutdown
# ---------------------------------------------------------------------------

class TestRetryLifecycle:
    @pytest.mark.asyncio
    async def test_cancel_pending_retry_cancels_timer_and_task(self):
        """_cancel_pending_retry bricht sowohl den Timer als auch einen
        bereits gestarteten Refresh-Task ab."""
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        timer_cancel = MagicMock()
        task = MagicMock()
        task.done.return_value = False
        coord._cancel_retry = timer_cancel
        coord._pending_retry_task = task

        coord._cancel_pending_retry()

        timer_cancel.assert_called_once()
        task.cancel.assert_called_once()
        assert coord._cancel_retry is None
        assert coord._pending_retry_task is None

    @pytest.mark.asyncio
    async def test_cancel_pending_retry_skips_finished_task(self):
        """Wenn der Refresh-Task bereits fertig ist, wird cancel() nicht gerufen."""
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        task = MagicMock()
        task.done.return_value = True
        coord._pending_retry_task = task

        coord._cancel_pending_retry()

        task.cancel.assert_not_called()
        assert coord._pending_retry_task is None

    @pytest.mark.asyncio
    async def test_retry_not_scheduled_during_ha_shutdown(self):
        """Während HA-Shutdown (CoreState.stopping) darf kein neuer Retry
        geplant werden — sonst läuft der Refresh auf einem zerstörten Coordinator."""
        from homeassistant.core import CoreState
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        coord._last_good_data = {"TL": 18.5}
        coord.hass.state = CoreState.stopping
        coord._api.get_current = AsyncMock(side_effect=GeoSphereApiError("timeout"))

        result = await coord._async_update_data()

        # Cache wird trotzdem zurückgegeben, aber kein Timer geplant.
        assert result == {"TL": 18.5}
        coord.hass.async_call_later.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_callback_tracks_created_task(self):
        """Der Timer-Callback weist den erzeugten Refresh-Task an
        _pending_retry_task zu, damit er später abgebrochen werden kann."""
        coord = _make_coordinator(GeoSphereCurrentCoordinator, station_id="11035")
        coord._last_good_data = {"TL": 18.5}
        coord._api.get_current = AsyncMock(side_effect=GeoSphereApiError("timeout"))

        fake_task = MagicMock()
        coord.hass.async_create_task = MagicMock(return_value=fake_task)
        # async_call_later soll den Callback nicht sofort feuern; wir simulieren
        # das manuell unten.
        captured_cb = {}
        def _capture(delay, cb):
            captured_cb["cb"] = cb
            return MagicMock()
        coord.hass.async_call_later.side_effect = _capture

        await coord._async_update_data()

        # Simuliere Timer-Firing:
        captured_cb["cb"](None)

        coord.hass.async_create_task.assert_called_once()
        assert coord._pending_retry_task is fake_task
        assert coord._cancel_retry is None  # Timer-Handle wurde geleert


# ---------------------------------------------------------------------------
# Andere Koordinatoren – Stichproben für Fallback + Retry
# ---------------------------------------------------------------------------

class TestForecastCoordinatorFallback:
    @pytest.mark.asyncio
    async def test_returns_cached_data_on_api_error(self):
        coord = _make_coordinator(GeoSphereForecastCoordinator, lat=48.2, lon=16.37, model="nwp-v1-1h-2500m")
        cached = [{"t2m": 15.0}]
        coord._last_good_data = cached
        coord._api.get_forecast = AsyncMock(side_effect=GeoSphereApiError("500"))

        assert await coord._async_update_data() == cached

    @pytest.mark.asyncio
    async def test_schedules_retry_on_failure(self):
        coord = _make_coordinator(GeoSphereForecastCoordinator, lat=48.2, lon=16.37, model="nwp-v1-1h-2500m")
        coord._last_good_data = [{"t2m": 15.0}]
        coord._api.get_forecast = AsyncMock(side_effect=GeoSphereApiError("500"))

        await coord._async_update_data()

        coord.hass.async_call_later.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_update_failed_without_cache(self):
        coord = _make_coordinator(GeoSphereForecastCoordinator, lat=48.2, lon=16.37, model="nwp-v1-1h-2500m")
        coord._api.get_forecast = AsyncMock(side_effect=GeoSphereApiError("500"))

        with pytest.raises(_UpdateFailed):
            await coord._async_update_data()


class TestWarningsCoordinatorFallback:
    @pytest.mark.asyncio
    async def test_returns_cached_data_on_api_error(self):
        coord = _make_coordinator(GeoSphereWarningsCoordinator, lat=48.2, lon=16.37)
        cached = [{"warnstufeid": 2}]
        coord._last_good_data = cached
        coord._api.get_warnings = AsyncMock(side_effect=GeoSphereApiError("503"))

        assert await coord._async_update_data() == cached

    @pytest.mark.asyncio
    async def test_raises_update_failed_without_cache(self):
        coord = _make_coordinator(GeoSphereWarningsCoordinator, lat=48.2, lon=16.37)
        coord._api.get_warnings = AsyncMock(side_effect=GeoSphereApiError("503"))

        with pytest.raises(_UpdateFailed):
            await coord._async_update_data()


class TestAirQualityCoordinatorFallback:
    @pytest.mark.asyncio
    async def test_returns_cached_data_on_api_error(self):
        coord = _make_coordinator(GeoSphereAirQualityCoordinator, lat=48.2, lon=16.37)
        cached = {"no2surf": 35.0}
        coord._last_good_data = cached
        coord._api.get_air_quality = AsyncMock(side_effect=GeoSphereApiError("404"))

        assert await coord._async_update_data() == cached

    @pytest.mark.asyncio
    async def test_raises_update_failed_without_cache(self):
        coord = _make_coordinator(GeoSphereAirQualityCoordinator, lat=48.2, lon=16.37)
        coord._api.get_air_quality = AsyncMock(side_effect=GeoSphereApiError("404"))

        with pytest.raises(_UpdateFailed):
            await coord._async_update_data()
