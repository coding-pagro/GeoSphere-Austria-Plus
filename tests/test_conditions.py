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

    def test_windy_variant_when_tcc_above_875_and_wind_strong(self):
        assert nwp_to_condition(0.9, 0.0, 0.0, 11.0, True) == "windy-variant"

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


def _sy(code: int | float, is_day: bool = True) -> str:
    """Shorthand: nwp_to_condition with only a sy code (no tcc/precip/wind)."""
    return nwp_to_condition(None, 0.0, 0.0, 0.0, is_day, sy=code)


class TestSyCodeMapping:
    # ------------------------------------------------------------------
    # Thunderstorm codes (26–32) → lightning-rainy
    # ------------------------------------------------------------------

    def test_thunderstorm_code_26(self):
        assert _sy(26) == "lightning-rainy"

    def test_thunderstorm_code_27(self):
        assert _sy(27) == "lightning-rainy"

    def test_thunderstorm_code_28(self):
        assert _sy(28) == "lightning-rainy"

    def test_thunderstorm_code_29(self):
        assert _sy(29) == "lightning-rainy"

    def test_thunderstorm_code_30(self):
        assert _sy(30) == "lightning-rainy"

    def test_thunderstorm_code_31(self):
        assert _sy(31) == "lightning-rainy"

    def test_thunderstorm_code_32(self):
        assert _sy(32) == "lightning-rainy"

    def test_thunderstorm_at_night_still_lightning_rainy(self):
        assert _sy(26, is_day=False) == "lightning-rainy"

    # ------------------------------------------------------------------
    # Clear / fair conditions respect day/night
    # ------------------------------------------------------------------

    def test_cloudless_daytime(self):
        assert _sy(1) == "sunny"

    def test_cloudless_nighttime(self):
        assert _sy(1, is_day=False) == "clear-night"

    def test_fair_daytime(self):
        assert _sy(2) == "partlycloudy"

    def test_fair_nighttime(self):
        assert _sy(2, is_day=False) == "partlycloudy"

    # ------------------------------------------------------------------
    # Cloud cover codes
    # ------------------------------------------------------------------

    def test_partly_cloudy(self):
        assert _sy(3) == "partlycloudy"

    def test_heavily_overcast(self):
        assert _sy(4) == "cloudy"

    def test_overcast(self):
        assert _sy(5) == "cloudy"

    # ------------------------------------------------------------------
    # Fog codes
    # ------------------------------------------------------------------

    def test_ground_fog(self):
        assert _sy(6) == "fog"

    def test_high_fog(self):
        assert _sy(7) == "fog"

    # ------------------------------------------------------------------
    # Rain codes
    # ------------------------------------------------------------------

    def test_light_rain(self):
        assert _sy(8) == "rainy"

    def test_moderate_rain(self):
        assert _sy(9) == "rainy"

    def test_heavy_rain_pouring(self):
        assert _sy(10) == "pouring"

    def test_rain_showers(self):
        assert _sy(17) == "rainy"

    def test_heavy_showers_pouring(self):
        assert _sy(19) == "pouring"

    # ------------------------------------------------------------------
    # Snow-rain mix codes
    # ------------------------------------------------------------------

    def test_rain_snow_mix_11(self):
        assert _sy(11) == "snowy-rainy"

    def test_rain_snow_mix_20(self):
        assert _sy(20) == "snowy-rainy"

    def test_rain_snow_mix_22(self):
        assert _sy(22) == "snowy-rainy"

    # ------------------------------------------------------------------
    # Snow codes
    # ------------------------------------------------------------------

    def test_light_snow(self):
        assert _sy(14) == "snowy"

    def test_heavy_snow(self):
        assert _sy(16) == "snowy"

    def test_snow_showers(self):
        assert _sy(23) == "snowy"

    def test_heavy_snow_showers(self):
        assert _sy(25) == "snowy"

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_float_code_is_accepted(self):
        assert _sy(26.0) == "lightning-rainy"


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
        assert nwp_to_condition(0.3, 0.0, 0.0, 5.0, False, sy=1) == "clear-night"

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

    def test_sy_sunny_with_strong_wind_gives_windy(self):
        assert nwp_to_condition(None, 0.0, 0.0, 11.0, True, sy=1) == "windy"

    def test_sy_partlycloudy_with_strong_wind_gives_windy_variant(self):
        assert nwp_to_condition(None, 0.0, 0.0, 11.0, True, sy=3) == "windy-variant"

    def test_sy_cloudy_with_strong_wind_gives_windy_variant(self):
        assert nwp_to_condition(None, 0.0, 0.0, 11.0, True, sy=4) == "windy-variant"

    def test_sy_precipitation_not_upgraded_by_wind(self):
        assert nwp_to_condition(None, 0.0, 0.0, 11.0, True, sy=8) == "rainy"
