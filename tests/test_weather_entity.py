"""Tests for GeoSphereWeatherEntity – condition derivation and forecast building."""
import math
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.geosphere_austria_plus.weather import GeoSphereWeatherEntity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def current_coord():
    coord = MagicMock()
    coord.data = {}
    return coord


@pytest.fixture
def forecast_coord():
    coord = MagicMock()
    coord.data = []
    coord.async_request_refresh = AsyncMock()
    return coord


@pytest.fixture
def entity(current_coord, forecast_coord):
    return GeoSphereWeatherEntity(
        current_coordinator=current_coord,
        forecast_coordinator=forecast_coord,
        station_id="11035",
        model="nwp-v1-1h-2500m",
        entry_id="test_entry",
        station_name="WIEN HOHE WARTE",
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _future_entry(hours_ahead: int = 2, **overrides) -> dict:
    """Return a forecast dict for a point in the future."""
    dt = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    base = {
        "datetime": dt.isoformat(),
        "t2m": 15.0,
        "rain_acc": 0.0,
        "snow_acc": 0.0,
        "rh2m": 60.0,
        "u10m": 0.0,
        "v10m": 0.0,
        "tcc": 0.3,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Entity metadata
# ---------------------------------------------------------------------------

class TestEntityMetadata:
    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "geosphere_plus_11035_nwp-v1-1h-2500m"

    def test_name(self, entity):
        assert entity._attr_name == "NWP"  # Modell-Label als Entitätsname unter Gerät

    def test_device_info_set(self, entity):
        di = entity._attr_device_info
        assert di is not None
        assert di["identifiers"] == {("geosphere_austria_plus", "11035")}
        assert di["name"] == "WIEN HOHE WARTE"
        assert di["manufacturer"] == "GeoSphere Austria"
        assert di["entry_type"] == "service"


# ---------------------------------------------------------------------------
# Current weather properties
# ---------------------------------------------------------------------------

class TestCurrentProperties:
    def test_native_temperature(self, entity, current_coord):
        current_coord.data = {"TL": 18.5}
        assert entity.native_temperature == 18.5

    def test_native_temperature_missing(self, entity, current_coord):
        current_coord.data = {}
        assert entity.native_temperature is None

    def test_humidity(self, entity, current_coord):
        current_coord.data = {"RF": 72.0}
        assert entity.humidity == 72.0

    def test_pressure_prefers_pred(self, entity, current_coord):
        current_coord.data = {"PRED": 1013.0, "P": 1010.0}
        assert entity.native_pressure == 1013.0

    def test_pressure_falls_back_to_p(self, entity, current_coord):
        current_coord.data = {"P": 1010.0}
        assert entity.native_pressure == 1010.0

    def test_wind_speed(self, entity, current_coord):
        current_coord.data = {"FF": 3.5}
        assert entity.native_wind_speed == 3.5

    def test_wind_gust(self, entity, current_coord):
        current_coord.data = {"FX": 8.0}
        assert entity.native_wind_gust_speed == 8.0

    def test_wind_bearing(self, entity, current_coord):
        current_coord.data = {"DD": 270.0}
        assert entity.wind_bearing == 270.0

    def test_dew_point(self, entity, current_coord):
        current_coord.data = {"TP": 5.0}
        assert entity.native_dew_point == 5.0

    def test_precipitation(self, entity, current_coord):
        current_coord.data = {"RR": 0.4}
        assert entity.native_precipitation == 0.4


# ---------------------------------------------------------------------------
# Condition derivation from TAWES data
# ---------------------------------------------------------------------------

class TestConditionDerivation:
    def _set(self, coord, **kwargs):
        defaults = {"RR": 0.0, "RF": 50.0, "FF": 2.0, "FX": 3.0, "SH": 0.0, "SO": 600}
        defaults.update(kwargs)
        coord.data = defaults

    def test_pouring_when_rr_above_heavy_threshold(self, entity, current_coord):
        self._set(current_coord, RR=1.5)
        assert entity.condition == "pouring"

    def test_rainy_when_rr_between_thresholds(self, entity, current_coord):
        self._set(current_coord, RR=0.5)
        assert entity.condition == "rainy"

    def test_rainy_boundary_just_met(self, entity, current_coord):
        # RR == 0.2 → "rainy"
        self._set(current_coord, RR=0.2)
        assert entity.condition == "rainy"

    def test_snow_and_rain_gives_snowy_rainy(self, entity, current_coord):
        # Snow+rain mix is checked before pure rain thresholds
        self._set(current_coord, RR=0.5, SH=5.0)
        assert entity.condition == "snowy-rainy"

    def test_heavy_rain_with_snow_gives_snowy_rainy_not_pouring(self, entity, current_coord):
        # Even with heavy rain, snow presence → snowy-rainy takes priority
        self._set(current_coord, RR=2.0, SH=10.0)
        assert entity.condition == "snowy-rainy"

    def test_snowy_when_snow_present(self, entity, current_coord):
        self._set(current_coord, RR=0.0, SH=5.0)
        assert entity.condition == "snowy"

    def test_snowy_boundary_just_not_met(self, entity, current_coord):
        # SH == 0.1 is NOT > threshold; no snow condition
        self._set(current_coord, RR=0.0, SH=0.1)
        cond = entity.condition
        assert cond not in ("snowy", "snowy-rainy")

    def test_fog_when_high_humidity_low_wind(self, entity, current_coord):
        self._set(current_coord, RR=0.0, RF=98.0, FF=1.0, SH=0.0)
        assert entity.condition == "fog"

    def test_no_fog_when_wind_too_high(self, entity, current_coord):
        self._set(current_coord, RR=0.0, RF=98.0, FF=3.0, SH=0.0, SO=400)
        assert entity.condition != "fog"

    def test_cloudy_when_no_sunshine(self, entity, current_coord):
        # SO = 0 → cloud_fraction = 1.0 ≥ 0.875
        self._set(current_coord, RR=0.0, RF=50.0, FF=5.0, SH=0.0, SO=0)
        assert entity.condition == "cloudy"

    def test_windy_variant_when_overcast_and_windy(self, entity, current_coord):
        self._set(current_coord, RR=0.0, RF=50.0, FF=11.0, SH=0.0, SO=0)
        assert entity.condition == "windy-variant"

    def test_partlycloudy_when_moderate_cloud_cover(self, entity, current_coord):
        # SO = 200 → cloud_fraction = 1 - 200/600 ≈ 0.667 (between 0.5 and 0.875)
        self._set(current_coord, RR=0.0, RF=50.0, FF=2.0, SH=0.0, SO=200)
        assert entity.condition == "partlycloudy"

    def test_windy_when_clear_and_strong_wind(self, entity, current_coord):
        # SO = 400 → cloud_fraction ≈ 0.333 < 0.5; no cloud condition; strong wind
        self._set(current_coord, RR=0.0, RF=50.0, FF=11.0, SH=0.0, SO=400)
        assert entity.condition == "windy"

    def test_day_night_returned_for_clear_sky(self, entity, current_coord):
        self._set(current_coord, RR=0.0, RF=50.0, FF=2.0, SH=0.0, SO=400)
        cond = entity.condition
        assert cond in ("sunny", "clear-night")

    def test_empty_data_returns_day_or_night(self, entity, current_coord):
        current_coord.data = {}
        cond = entity.condition
        assert cond in ("sunny", "clear-night")


# ---------------------------------------------------------------------------
# _is_daytime (sun.sun integration)
# ---------------------------------------------------------------------------

class TestIsDaytime:
    def test_uses_sun_entity_above_horizon(self, entity, current_coord):
        entity.hass = MagicMock()
        sun_state = MagicMock()
        sun_state.state = "above_horizon"
        entity.hass.states.get.return_value = sun_state
        assert entity._is_daytime() is True

    def test_uses_sun_entity_below_horizon(self, entity, current_coord):
        entity.hass = MagicMock()
        sun_state = MagicMock()
        sun_state.state = "below_horizon"
        entity.hass.states.get.return_value = sun_state
        assert entity._is_daytime() is False

    def test_falls_back_to_longitude_when_sun_entity_unavailable(
        self, entity, current_coord
    ):
        entity.hass = MagicMock()
        entity.hass.states.get.return_value = None
        current_coord.data = {"_lon": 15.0}
        # 12:00 UTC + 1h offset → 13:00 local → daytime
        with patch(
            "custom_components.geosphere_austria_plus.weather.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
            assert entity._is_daytime() is True

    def test_falls_back_to_longitude_when_hass_not_set(self, entity, current_coord):
        # hass not set at all (before async_added_to_hass)
        if hasattr(entity, "hass"):
            del entity.hass
        current_coord.data = {"_lon": 15.0}
        with patch(
            "custom_components.geosphere_austria_plus.weather.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
            assert entity._is_daytime() is True


# ---------------------------------------------------------------------------
# _is_dt_daytime
# ---------------------------------------------------------------------------

class TestIsDtDaytime:
    def test_noon_utc_is_daytime_for_austria(self, entity, current_coord):
        current_coord.data = {"_lon": 15.0}  # lon=15 → local offset +1h
        dt = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
        assert entity._is_dt_daytime(dt) is True

    def test_midnight_utc_is_nighttime_for_austria(self, entity, current_coord):
        current_coord.data = {"_lon": 15.0}
        dt = datetime(2024, 6, 15, 0, 0, tzinfo=timezone.utc)
        assert entity._is_dt_daytime(dt) is False

    def test_defaults_to_austria_longitude_when_no_data(self, entity, current_coord):
        current_coord.data = {}
        dt = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
        # lon default = 14.0 → local ≈ 12.93 → daytime
        assert entity._is_dt_daytime(dt) is True


# ---------------------------------------------------------------------------
# _build_hourly_forecasts
# ---------------------------------------------------------------------------

class TestBuildHourlyForecasts:
    def test_basic_entry_is_included(self, entity, current_coord, forecast_coord):
        current_coord.data = {"_lon": 14.0}
        forecast_coord.data = [_future_entry(hours_ahead=2, t2m=20.0, rh2m=55.0, rain_acc=0.3)]

        forecasts = entity._build_hourly_forecasts()
        assert len(forecasts) == 1
        f = forecasts[0]
        assert f.native_temperature == 20.0
        assert f.native_precipitation == 0.3
        assert f.humidity == 55.0

    def test_wind_speed_calculated_as_vector_magnitude(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        forecast_coord.data = [_future_entry(u10m=3.0, v10m=4.0)]

        forecasts = entity._build_hourly_forecasts()
        assert abs(forecasts[0].native_wind_speed - 5.0) < 1e-6  # sqrt(9+16)

    def test_wind_bearing_calculation(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        # u10m=0, v10m=5 → atan2(0,5)=0 → bearing = (0+180)%360 = 180
        forecast_coord.data = [_future_entry(u10m=0.0, v10m=5.0)]

        forecasts = entity._build_hourly_forecasts()
        assert abs(forecasts[0].wind_bearing - 180.0) < 1e-6

    def test_past_entries_are_skipped(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        past_dt = datetime.now(timezone.utc) - timedelta(hours=3)
        forecast_coord.data = [{"datetime": past_dt.isoformat(), "t2m": 10.0}]

        assert entity._build_hourly_forecasts() == []

    def test_recent_entry_within_1h_is_included(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        recent_dt = datetime.now(timezone.utc) - timedelta(minutes=30)
        entry = _future_entry()
        entry["datetime"] = recent_dt.isoformat()
        forecast_coord.data = [entry]

        assert len(entity._build_hourly_forecasts()) == 1

    def test_invalid_datetime_is_skipped(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        forecast_coord.data = [{"datetime": "not-a-date", "t2m": 10.0}]
        assert entity._build_hourly_forecasts() == []

    def test_missing_datetime_is_skipped(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        forecast_coord.data = [{"t2m": 10.0}]
        assert entity._build_hourly_forecasts() == []

    def test_capped_at_48_entries(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        forecast_coord.data = [
            _future_entry(hours_ahead=i + 1) for i in range(60)
        ]
        assert len(entity._build_hourly_forecasts()) == 48

    def test_condition_assigned_from_nwp(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        forecast_coord.data = [_future_entry(tcc=0.9, rain_acc=0.0, snow_acc=0.0)]

        forecasts = entity._build_hourly_forecasts()
        assert forecasts[0].condition == "cloudy"

    def test_none_values_default_to_zero_for_precip_and_wind(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        entry = _future_entry()
        entry["rain_acc"] = None
        entry["snow_acc"] = None
        entry["u10m"] = None
        entry["v10m"] = None
        forecast_coord.data = [entry]

        forecasts = entity._build_hourly_forecasts()
        assert len(forecasts) == 1
        assert forecasts[0].native_precipitation == 0.0
        assert forecasts[0].native_wind_speed == 0.0

    def test_z_suffix_in_datetime_handled(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        future_dt = datetime.now(timezone.utc) + timedelta(hours=2)
        ts = future_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        forecast_coord.data = [_future_entry() | {"datetime": ts}]

        assert len(entity._build_hourly_forecasts()) == 1


# ---------------------------------------------------------------------------
# _build_daily_forecasts
# ---------------------------------------------------------------------------

class TestBuildDailyForecasts:
    def _acc_entries(
        self,
        day_offset: int,
        rain_total: float = 0.0,
        snow_total: float = 0.0,
        count: int = 4,
    ) -> list:
        """Entries where rain_acc/snow_acc increase monotonically (accumulated style).

        max(rain_acc) - min(rain_acc) == rain_total after the fix.
        """
        base_dt = (
            datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=day_offset)
        )
        return [
            {
                "datetime": (base_dt + timedelta(hours=i)).isoformat(),
                "t2m": 10.0,
                "rain_acc": rain_total * i / max(count - 1, 1),
                "snow_acc": snow_total * i / max(count - 1, 1),
                "rh2m": 65.0,
                "u10m": 2.0,
                "v10m": 2.0,
                "tcc": 0.3,
            }
            for i in range(count)
        ]

    def _day_entries(self, day_offset: int = 1, count: int = 24, **overrides) -> list:
        """Generate `count` hourly entries starting at midnight UTC on day+offset."""
        base_dt = (
            datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=day_offset)
        )
        entries = []
        for i in range(count):
            dt = base_dt + timedelta(hours=i)
            row = {
                "datetime": dt.isoformat(),
                "t2m": 10.0 + i * 0.5,
                "rain_acc": 0.0,
                "snow_acc": 0.0,
                "rh2m": 65.0,
                "u10m": 2.0,
                "v10m": 2.0,
                "tcc": 0.3,
            }
            row.update(overrides)
            entries.append(row)
        return entries

    def test_returns_one_entry_per_day(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        forecast_coord.data = self._day_entries(day_offset=1)

        forecasts = entity._build_daily_forecasts()
        assert len(forecasts) == 1

    def test_temp_max_and_min_aggregated(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        entries = self._day_entries(day_offset=1, count=4)
        # t2m: 10.0, 10.5, 11.0, 11.5
        forecast_coord.data = entries

        forecasts = entity._build_daily_forecasts()
        assert forecasts[0].native_temperature == pytest.approx(11.5)
        assert forecasts[0].native_templow == pytest.approx(10.0)

    def test_rain_above_2mm_gives_rainy(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        # Accumulated: 0.0 → 4.8 mm, range = 4.8 mm → rainy
        forecast_coord.data = self._acc_entries(day_offset=1, rain_total=4.8)
        forecasts = entity._build_daily_forecasts()
        assert forecasts[0].condition == "rainy"

    def test_rain_above_10mm_gives_pouring(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        # Accumulated: 0.0 → 12.0 mm, range = 12.0 mm → pouring
        forecast_coord.data = self._acc_entries(day_offset=1, rain_total=12.0)
        forecasts = entity._build_daily_forecasts()
        assert forecasts[0].condition == "pouring"

    def test_snow_above_2mm_gives_snowy(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        # Accumulated: 0.0 → 4.8 mm snow, range = 4.8 mm → snowy
        forecast_coord.data = self._acc_entries(day_offset=1, snow_total=4.8)
        forecasts = entity._build_daily_forecasts()
        assert forecasts[0].condition == "snowy"

    def test_precipitation_is_range_not_sum(self, entity, current_coord, forecast_coord):
        """native_precipitation muss max-min sein, nicht die Summe der akkumulierten Werte."""
        current_coord.data = {}
        # Accumulated: [0.0, 3.0, 6.0, 9.0] → range = 9.0, sum = 18.0
        forecast_coord.data = self._acc_entries(day_offset=1, rain_total=9.0, count=4)
        forecasts = entity._build_daily_forecasts()
        assert forecasts[0].native_precipitation == pytest.approx(9.0)

    def test_capped_at_7_days(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        all_entries = []
        for day in range(1, 11):
            all_entries.extend(self._day_entries(day_offset=day))
        forecast_coord.data = all_entries

        forecasts = entity._build_daily_forecasts()
        assert len(forecasts) <= 7

    def test_humidity_averaged(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        forecast_coord.data = self._day_entries(day_offset=1, count=2, rh2m=80.0)
        forecasts = entity._build_daily_forecasts()
        assert forecasts[0].humidity == pytest.approx(80.0)

    def test_is_daytime_always_true_for_daily(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        forecast_coord.data = self._day_entries(day_offset=1)
        forecasts = entity._build_daily_forecasts()
        assert forecasts[0].is_daytime is True

    def test_empty_forecast_data_returns_empty(self, entity, current_coord, forecast_coord):
        current_coord.data = {}
        forecast_coord.data = []
        assert entity._build_daily_forecasts() == []


# ---------------------------------------------------------------------------
# async_forecast_hourly / async_forecast_daily (integration of async path)
# ---------------------------------------------------------------------------

class TestAsyncForecastMethods:
    async def test_async_forecast_hourly_does_not_refresh(
        self, entity, current_coord, forecast_coord
    ):
        """Coordinator-Refresh darf nicht bei jedem Frontend-Aufruf ausgelöst werden."""
        current_coord.data = {}
        forecast_coord.data = []

        await entity.async_forecast_hourly()
        forecast_coord.async_request_refresh.assert_not_called()

    async def test_async_forecast_daily_does_not_refresh(
        self, entity, current_coord, forecast_coord
    ):
        """Coordinator-Refresh darf nicht bei jedem Frontend-Aufruf ausgelöst werden."""
        current_coord.data = {}
        forecast_coord.data = []

        await entity.async_forecast_daily()
        forecast_coord.async_request_refresh.assert_not_called()

    async def test_async_forecast_hourly_returns_list(
        self, entity, current_coord, forecast_coord
    ):
        current_coord.data = {}
        forecast_coord.data = [_future_entry()]

        result = await entity.async_forecast_hourly()
        assert isinstance(result, list)
        assert len(result) == 1

    async def test_async_forecast_daily_returns_list(
        self, entity, current_coord, forecast_coord
    ):
        current_coord.data = {}
        # Use entries far in the future so they form a full future day
        base = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        entries = []
        for i in range(24):
            dt = base + timedelta(hours=i)
            entries.append(
                {
                    "datetime": dt.isoformat(),
                    "t2m": 15.0,
                    "rain_acc": 0.0,
                    "snow_acc": 0.0,
                    "rh2m": 60.0,
                    "u10m": 0.0,
                    "v10m": 0.0,
                    "tcc": 0.3,
                }
            )
        forecast_coord.data = entries

        result = await entity.async_forecast_daily()
        assert isinstance(result, list)
        assert len(result) >= 1
