"""Live integration test against the real GeoSphere Austria API.

Run with: python tests/live_integration_test.py
Requires internet access. Not part of the regular pytest suite.
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mock HA modules before importing our code
from unittest.mock import MagicMock
import types

_coordinator_mod = MagicMock()

class _MockDataUpdateCoordinator:
    def __class_getitem__(cls, item):
        return cls
    def __init__(self, *a, **kw):
        self.data = None

_coordinator_mod.DataUpdateCoordinator = _MockDataUpdateCoordinator
_coordinator_mod.CoordinatorEntity = type("CoordinatorEntity", (), {"__class_getitem__": classmethod(lambda cls, item: cls), "__init__": lambda self, c: setattr(self, "coordinator", c)})
_coordinator_mod.UpdateFailed = Exception

_const_mod = MagicMock()
_const_mod.UnitOfTemperature.CELSIUS = "°C"
_const_mod.UnitOfPressure.HPA = "hPa"
_const_mod.UnitOfSpeed.METERS_PER_SECOND = "m/s"
_const_mod.UnitOfLength.MILLIMETERS = "mm"

# Only install mocks when running as a standalone script.  When pytest
# imports this file during collection (it matches *_test.py) the HA stubs
# are already in sys.modules via tests/conftest.py; overwriting them would
# replace _MockDataUpdateCoordinator with this file's leaner version (which
# omits self.hass) and corrupt every coordinator test that runs afterwards.
if "homeassistant.helpers.update_coordinator" not in sys.modules:
    sys.modules.update({
        "homeassistant": MagicMock(),
        "homeassistant.components": MagicMock(),
        "homeassistant.components.diagnostics": MagicMock(),
        "homeassistant.components.sensor": MagicMock(),
        "homeassistant.components.system_health": MagicMock(),
        "homeassistant.components.weather": MagicMock(),
        "homeassistant.components.weather.const": MagicMock(),
        "homeassistant.config_entries": MagicMock(),
        "homeassistant.const": _const_mod,
        "homeassistant.core": MagicMock(),
        "homeassistant.exceptions": MagicMock(),
        "homeassistant.helpers": MagicMock(),
        "homeassistant.helpers.aiohttp_client": MagicMock(),
        "homeassistant.helpers.device_registry": MagicMock(),
        "homeassistant.helpers.entity_platform": MagicMock(),
        "homeassistant.helpers.entity_registry": MagicMock(),
        "homeassistant.helpers.event": MagicMock(),
        "homeassistant.helpers.issue_registry": MagicMock(),
        "homeassistant.helpers.selector": MagicMock(),
        "homeassistant.helpers.update_coordinator": _coordinator_mod,
        "voluptuous": MagicMock(),
    })

import aiohttp
import ssl


STATION_ID = "11389"
MODELS = ["nwp-v1-1h-2500m", "ensemble-v1-1h-2500m", "nowcast-v1-15min-1km"]

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

# Failure counter — script exits with this value so CI / wrappers see
# a non-zero status when any probe failed.
_FAILURES = 0


def ok(msg):
    print(f"  {GREEN}OK{RESET} {msg}")


def fail(msg):
    global _FAILURES
    _FAILURES += 1
    print(f"  {RED}FAIL{RESET} {msg}")


async def run_tests():
    from custom_components.geosphere_austria_plus.api import GeoSphereApi

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        api = GeoSphereApi(session)

        # --- Current data ---
        print(f"\nStation {STATION_ID} – Current data:")
        try:
            data = await api.get_current(STATION_ID)
            tl = data.get("TL")
            ff = data.get("FF")
            ok(f"TL={tl}°C  FF={ff} m/s  keys={list(data.keys())[:8]}")
        except Exception as e:
            fail(f"get_current: {e}")
            return

        lat = data.get("_lat", 47.5)
        lon = data.get("_lon", 14.0)

        # --- Forecast per model ---
        for model in MODELS:
            print(f"\nModel {model}:")
            try:
                forecasts = await api.get_forecast(lat, lon, model)
                if not forecasts:
                    fail("Returned 0 timesteps")
                else:
                    first = forecasts[0]
                    rain = first.get("rain_acc", 0.0)
                    ok(f"{len(forecasts)} timesteps, first: {first.get('datetime')}  t2m={first.get('t2m')}  rain_acc={rain}")
            except Exception as e:
                fail(f"get_forecast: {e}")

        # --- Open-Meteo daily extension ---
        print(f"\nOpen-Meteo daily (lat={lat:.3f}, lon={lon:.3f}):")
        try:
            from custom_components.geosphere_austria_plus.open_meteo_api import fetch_open_meteo_daily
            om_days = await fetch_open_meteo_daily(session, lat, lon)
            if not om_days:
                fail("Returned 0 days")
            else:
                first = om_days[0]
                last = om_days[-1]
                ok(f"{len(om_days)} days  [{first['datetime'][:10]} … {last['datetime'][:10]}]")
                ok(f"first day: condition={first.get('condition')}  t_max={first.get('native_temperature')}°C  t_min={first.get('native_templow')}°C")
                om_only_keys = [k for k in ("uv_index", "solar_radiation", "precipitation_probability") if k in first]
                ok(f"Open-Meteo-specific keys present: {om_only_keys}")
        except Exception as e:
            fail(f"fetch_open_meteo_daily: {e}")

    print()


if __name__ == "__main__":
    asyncio.run(run_tests())
    sys.exit(_FAILURES)
