"""Tests für async_get_config_entry_diagnostics."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

# diagnostics.py importiert `homeassistant.components.diagnostics.async_redact_data`.
# Im conftest wird der Helpers-Block gestubbt; den Diagnostics-Submodul-Stub
# erzeugen wir hier in-place, damit die Tests ohne echte HA-Installation laufen.
_diagnostics_mod = types.ModuleType("homeassistant.components.diagnostics")
def _async_redact_data(data: dict, redact_keys: set) -> dict:
    return {k: ("**REDACTED**" if k in redact_keys else v) for k, v in data.items()}
_diagnostics_mod.async_redact_data = _async_redact_data
sys.modules["homeassistant.components.diagnostics"] = _diagnostics_mod

from custom_components.geosphere_austria_plus.const import (  # noqa: E402
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STATION_ID,
    DATA_AIR_QUALITY,
    DATA_CURRENT,
    DATA_FORECASTS,
    DATA_WARNINGS,
    DOMAIN,
)
from custom_components.geosphere_austria_plus.diagnostics import (  # noqa: E402
    async_get_config_entry_diagnostics,
)


def _make_coordinator_stub(name: str, data, last_success: bool = True, retry_step: int = 0):
    coord = MagicMock()
    coord.name = name
    coord.data = data
    coord.last_update_success = last_success
    interval = MagicMock()
    interval.total_seconds.return_value = 600.0
    coord.update_interval = interval
    coord._retry_step = retry_step
    coord._last_good_data = data
    return coord


def _make_entry(data=None, options=None):
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.title = "Wien Test"
    entry.version = 2
    entry.data = data or {}
    entry.options = options or {}
    return entry


def _make_hass(coordinators: dict) -> MagicMock:
    hass = MagicMock()
    hass.data = {DOMAIN: {"test_entry_id": coordinators}}
    return hass


class TestDiagnosticsRedaction:
    @pytest.mark.asyncio
    async def test_lat_lon_rounded_to_2_decimals_in_data(self):
        """Lat/Lon werden auf 2 Dezimalen gerundet (~1 km Auflösung, Privacy)."""
        entry = _make_entry(data={
            CONF_LATITUDE: 48.21345,
            CONF_LONGITUDE: 16.37891,
            CONF_STATION_ID: "11035",
        })
        hass = _make_hass({})

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["config_entry"]["data"][CONF_LATITUDE] == 48.21
        assert result["config_entry"]["data"][CONF_LONGITUDE] == 16.38

    @pytest.mark.asyncio
    async def test_station_id_is_redacted(self):
        """station_id ist in TO_REDACT → vollredaktion."""
        entry = _make_entry(data={
            CONF_LATITUDE: 48.21,
            CONF_LONGITUDE: 16.37,
            CONF_STATION_ID: "11035",
        })
        hass = _make_hass({})

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["config_entry"]["data"][CONF_STATION_ID] == "**REDACTED**"

    @pytest.mark.asyncio
    async def test_lat_lon_also_redacted_in_options(self):
        entry = _make_entry(
            data={},
            options={CONF_LATITUDE: 48.99999, CONF_LONGITUDE: 16.99999},
        )
        hass = _make_hass({})

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["config_entry"]["options"][CONF_LATITUDE] == 49.0
        assert result["config_entry"]["options"][CONF_LONGITUDE] == 17.0


class TestDiagnosticsCoordinatorSnapshot:
    @pytest.mark.asyncio
    async def test_current_coordinator_snapshot(self):
        entry = _make_entry(data={CONF_LATITUDE: 48.21, CONF_LONGITUDE: 16.37})
        coord = _make_coordinator_stub("current", {"TL": 20.0, "RF": 50})
        hass = _make_hass({DATA_CURRENT: coord})

        result = await async_get_config_entry_diagnostics(hass, entry)

        snap = result["coordinators"][DATA_CURRENT]
        assert snap["last_update_success"] is True
        assert snap["update_interval_seconds"] == 600.0
        assert snap["retry_step"] == 0
        assert snap["has_cached_data"] is True
        assert snap["data_present"] is True
        # Sortierte Keys, aber keine Werte
        assert snap["data_keys"] == ["RF", "TL"]

    @pytest.mark.asyncio
    async def test_forecast_coordinators_keyed_by_model(self):
        entry = _make_entry(data={CONF_LATITUDE: 48.21, CONF_LONGITUDE: 16.37})
        coords = {
            DATA_FORECASTS: {
                "nwp-v1-1h-2500m": _make_coordinator_stub("nwp", [{"t2m": 15}]),
                "nowcast-v1-15min-1km": _make_coordinator_stub("nc", [{"t2m": 14}]),
            },
        }
        hass = _make_hass(coords)

        result = await async_get_config_entry_diagnostics(hass, entry)

        forecasts = result["coordinators"][DATA_FORECASTS]
        assert set(forecasts.keys()) == {"nwp-v1-1h-2500m", "nowcast-v1-15min-1km"}
        for snap in forecasts.values():
            assert snap["data_entries"] == 1

    @pytest.mark.asyncio
    async def test_no_raw_data_values_in_output(self):
        """Hot Path: Roh-Forecast-Werte dürfen nicht in den Diagnostics landen
        (enthalten u.U. präzise Stationskoordinaten). Key-Namen sind ok."""
        entry = _make_entry(data={CONF_LATITUDE: 48.21, CONF_LONGITUDE: 16.37})
        sensitive = {"_lat": 48.21345, "_lon": 16.37891, "TL": 20.0}
        coord = _make_coordinator_stub("current", sensitive)
        hass = _make_hass({DATA_CURRENT: coord})

        result = await async_get_config_entry_diagnostics(hass, entry)

        # Werte (48.21345, 16.37891, 20.0) dürfen nirgendwo auftauchen
        flat = str(result)
        assert "48.21345" not in flat
        assert "16.37891" not in flat
        # Aber: die Key-Liste IST exportiert (Diagnose-Wert)
        snap = result["coordinators"][DATA_CURRENT]
        assert "TL" in snap["data_keys"]

    @pytest.mark.asyncio
    async def test_missing_coordinators_not_in_output(self):
        """Optionale Coordinatoren erscheinen nur, wenn sie konfiguriert sind."""
        entry = _make_entry(data={CONF_LATITUDE: 48.21, CONF_LONGITUDE: 16.37})
        hass = _make_hass({})  # nichts konfiguriert

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert DATA_CURRENT not in result["coordinators"]
        assert DATA_WARNINGS not in result["coordinators"]
        assert DATA_AIR_QUALITY not in result["coordinators"]
