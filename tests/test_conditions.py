"""Tests for nwp_to_condition – pure function, no HA dependencies."""
import pytest

from custom_components.geosphere_austria_plus.weather import nwp_to_condition


class TestNwpToCondition:
    # ------------------------------------------------------------------
    # Precipitation takes priority over cloud cover
    # ------------------------------------------------------------------

    def test_snowy_rainy_when_both_exceed_threshold(self):
        assert nwp_to_condition(0.9, 0.5, 0.5, 5.0, True) == "snowy-rainy"

    def test_snowy_when_only_snow(self):
        assert nwp_to_condition(0.9, 0.0, 0.5, 5.0, True) == "snowy"

    def test_pouring_when_rain_exceeds_5mm(self):
        assert nwp_to_condition(0.9, 5.1, 0.0, 5.0, True) == "pouring"

    def test_rainy_when_rain_between_01_and_5mm(self):
        assert nwp_to_condition(0.9, 0.5, 0.0, 5.0, True) == "rainy"

    # ------------------------------------------------------------------
    # Cloud cover thresholds
    # ------------------------------------------------------------------

    def test_cloudy_when_tcc_above_875(self):
        assert nwp_to_condition(0.9, 0.0, 0.0, 5.0, True) == "cloudy"

    def test_partlycloudy_when_tcc_between_05_and_875_calm(self):
        assert nwp_to_condition(0.6, 0.0, 0.0, 5.0, True) == "partlycloudy"

    def test_windy_variant_when_tcc_above_05_and_wind_strong(self):
        assert nwp_to_condition(0.6, 0.0, 0.0, 11.0, True) == "windy-variant"

    # ------------------------------------------------------------------
    # Wind / clear sky
    # ------------------------------------------------------------------

    def test_windy_when_low_tcc_and_strong_wind(self):
        assert nwp_to_condition(0.3, 0.0, 0.0, 11.0, True) == "windy"

    def test_sunny_during_day(self):
        assert nwp_to_condition(0.3, 0.0, 0.0, 5.0, True) == "sunny"

    def test_clear_night_at_night(self):
        assert nwp_to_condition(0.3, 0.0, 0.0, 5.0, False) == "clear-night"

    # ------------------------------------------------------------------
    # Exact boundary values
    # ------------------------------------------------------------------

    def test_snow_threshold_not_exceeded(self):
        # snow_mm must be > 0.1; exactly 0.1 does not trigger snowy
        assert nwp_to_condition(0.0, 0.0, 0.1, 0.0, True) != "snowy"

    def test_snow_threshold_just_exceeded(self):
        assert nwp_to_condition(0.0, 0.0, 0.11, 0.0, True) == "snowy"

    def test_rain_pouring_boundary_not_exceeded(self):
        # rain_mm > 5.0 required; exactly 5.0 → rainy not pouring
        assert nwp_to_condition(0.0, 5.0, 0.0, 0.0, True) == "rainy"

    def test_rain_pouring_boundary_exceeded(self):
        assert nwp_to_condition(0.0, 5.01, 0.0, 0.0, True) == "pouring"

    def test_rain_rainy_boundary_not_exceeded(self):
        # rain_mm must be > 0.1; exactly 0.1 → not rainy
        result = nwp_to_condition(0.0, 0.1, 0.0, 0.0, True)
        assert result != "rainy"

    def test_tcc_cloudy_boundary_not_exceeded(self):
        # tcc must be > 0.875; exactly 0.875 → partlycloudy (or windy)
        result = nwp_to_condition(0.875, 0.0, 0.0, 5.0, True)
        assert result != "cloudy"

    def test_wind_threshold_exact(self):
        # wind > 10 required; exactly 10 → not windy
        assert nwp_to_condition(0.3, 0.0, 0.0, 10.0, True) != "windy"

    # ------------------------------------------------------------------
    # tcc=None (Nowcast: no cloud cover available)
    # ------------------------------------------------------------------

    def test_none_tcc_windy_when_strong_wind(self):
        assert nwp_to_condition(None, 0.0, 0.0, 11.0, True) == "windy"

    def test_none_tcc_sunny_when_calm_day(self):
        assert nwp_to_condition(None, 0.0, 0.0, 5.0, True) == "sunny"

    def test_none_tcc_clear_night_when_calm_night(self):
        assert nwp_to_condition(None, 0.0, 0.0, 5.0, False) == "clear-night"

    def test_none_tcc_precipitation_still_takes_priority(self):
        assert nwp_to_condition(None, 2.0, 0.0, 5.0, True) == "rainy"

    def test_none_tcc_snow_takes_priority(self):
        assert nwp_to_condition(None, 0.0, 0.5, 5.0, True) == "snowy"
