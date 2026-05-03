"""Tests for nwp_to_condition and sy_to_condition – pure functions, no HA dependencies."""
import pytest

from custom_components.geosphere_austria_plus.weather import nwp_to_condition, sy_to_condition


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


class TestSyToCondition:
    # ------------------------------------------------------------------
    # Thunderstorm codes (26–32) → lightning-rainy
    # ------------------------------------------------------------------

    def test_thunderstorm_code_26(self):
        assert sy_to_condition(26, True) == "lightning-rainy"

    def test_thunderstorm_code_27(self):
        assert sy_to_condition(27, True) == "lightning-rainy"

    def test_thunderstorm_code_28(self):
        assert sy_to_condition(28, True) == "lightning-rainy"

    def test_thunderstorm_code_29(self):
        assert sy_to_condition(29, True) == "lightning-rainy"

    def test_thunderstorm_code_30(self):
        assert sy_to_condition(30, True) == "lightning-rainy"

    def test_thunderstorm_code_31(self):
        assert sy_to_condition(31, True) == "lightning-rainy"

    def test_thunderstorm_code_32(self):
        assert sy_to_condition(32, True) == "lightning-rainy"

    def test_thunderstorm_at_night_still_lightning_rainy(self):
        assert sy_to_condition(26, False) == "lightning-rainy"

    # ------------------------------------------------------------------
    # Clear / fair conditions respect day/night
    # ------------------------------------------------------------------

    def test_cloudless_daytime(self):
        assert sy_to_condition(1, True) == "sunny"

    def test_cloudless_nighttime(self):
        assert sy_to_condition(1, False) == "clear-night"

    def test_fair_daytime(self):
        assert sy_to_condition(2, True) == "sunny"

    def test_fair_nighttime(self):
        assert sy_to_condition(2, False) == "clear-night"

    # ------------------------------------------------------------------
    # Cloud cover codes
    # ------------------------------------------------------------------

    def test_partly_cloudy(self):
        assert sy_to_condition(3, True) == "partlycloudy"

    def test_heavily_overcast(self):
        assert sy_to_condition(4, True) == "cloudy"

    def test_overcast(self):
        assert sy_to_condition(5, True) == "cloudy"

    # ------------------------------------------------------------------
    # Fog codes
    # ------------------------------------------------------------------

    def test_ground_fog(self):
        assert sy_to_condition(6, True) == "fog"

    def test_high_fog(self):
        assert sy_to_condition(7, True) == "fog"

    # ------------------------------------------------------------------
    # Rain codes
    # ------------------------------------------------------------------

    def test_light_rain(self):
        assert sy_to_condition(8, True) == "rainy"

    def test_moderate_rain(self):
        assert sy_to_condition(9, True) == "rainy"

    def test_heavy_rain_pouring(self):
        assert sy_to_condition(10, True) == "pouring"

    def test_rain_showers(self):
        assert sy_to_condition(17, True) == "rainy"

    def test_heavy_showers_pouring(self):
        assert sy_to_condition(19, True) == "pouring"

    # ------------------------------------------------------------------
    # Snow-rain mix codes
    # ------------------------------------------------------------------

    def test_rain_snow_mix_11(self):
        assert sy_to_condition(11, True) == "snowy-rainy"

    def test_rain_snow_mix_20(self):
        assert sy_to_condition(20, True) == "snowy-rainy"

    def test_rain_snow_mix_22(self):
        assert sy_to_condition(22, True) == "snowy-rainy"

    # ------------------------------------------------------------------
    # Snow codes
    # ------------------------------------------------------------------

    def test_light_snow(self):
        assert sy_to_condition(14, True) == "snowy"

    def test_heavy_snow(self):
        assert sy_to_condition(16, True) == "snowy"

    def test_snow_showers(self):
        assert sy_to_condition(23, True) == "snowy"

    def test_heavy_snow_showers(self):
        assert sy_to_condition(25, True) == "snowy"

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_none_sy_returns_none(self):
        assert sy_to_condition(None, True) is None

    def test_unknown_code_returns_none(self):
        assert sy_to_condition(0, True) is None

    def test_unknown_code_33_returns_none(self):
        assert sy_to_condition(33, True) is None

    def test_float_code_is_accepted(self):
        # API may return sy as a float
        assert sy_to_condition(26.0, True) == "lightning-rainy"


class TestNwpToConditionWithSy:
    """nwp_to_condition prefers sy when available."""

    # ------------------------------------------------------------------
    # sy takes priority over derived conditions
    # ------------------------------------------------------------------

    def test_sy_thunderstorm_overrides_rainy_derived(self):
        # Without sy this would be "rainy" from rain_mm alone
        assert nwp_to_condition(0.5, 2.0, 0.0, 5.0, True, sy=26) == "lightning-rainy"

    def test_sy_thunderstorm_overrides_cloudy_derived(self):
        assert nwp_to_condition(0.9, 0.0, 0.0, 5.0, True, sy=28) == "lightning-rainy"

    def test_sy_fog_overrides_rainy_derived(self):
        assert nwp_to_condition(0.9, 0.5, 0.0, 5.0, True, sy=6) == "fog"

    def test_sy_sunny_used_when_no_precipitation(self):
        assert nwp_to_condition(0.9, 0.0, 0.0, 5.0, True, sy=1) == "sunny"

    def test_sy_clear_night_when_nighttime(self):
        assert nwp_to_condition(0.3, 0.0, 0.0, 5.0, False, sy=2) == "clear-night"

    # ------------------------------------------------------------------
    # Fallback to derived logic when sy is None
    # ------------------------------------------------------------------

    def test_no_sy_falls_back_to_derived_rainy(self):
        assert nwp_to_condition(0.5, 2.0, 0.0, 5.0, True, sy=None) == "rainy"

    def test_no_sy_falls_back_to_derived_cloudy(self):
        assert nwp_to_condition(0.9, 0.0, 0.0, 5.0, True, sy=None) == "cloudy"

    # ------------------------------------------------------------------
    # Backward compatibility: sy defaults to None
    # ------------------------------------------------------------------

    def test_missing_sy_arg_uses_derived_logic(self):
        # Calling without sy argument must still work (default=None)
        assert nwp_to_condition(0.9, 0.0, 0.0, 5.0, True) == "cloudy"
