"""Tests für async_setup_entry in __init__.py (bedingte Coordinator-Erstellung)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.geosphere_austria_plus.const import (
    CONF_FORECAST_MODELS,
    CONF_ENABLE_WARNINGS,
    CONF_ENABLE_AIR_QUALITY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STATION_ID,
    DATA_FORECASTS,
    DATA_WARNINGS,
    DATA_AIR_QUALITY,
    DATA_CURRENT,
    DOMAIN,
    DEFAULT_FORECAST_MODEL,
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_entry(data=None, options=None):
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = data or {}
    entry.options = options or {}
    entry.async_on_unload = MagicMock()
    return entry


def _make_hass():
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    return hass


def _make_coordinator_mock(raises=False):
    """Erstellt einen Mock-Coordinator; optional mit ConfigEntryNotReady beim ersten Refresh."""
    mock = MagicMock()
    if raises:
        mock.async_config_entry_first_refresh = AsyncMock(side_effect=Exception("API down"))
    else:
        mock.async_config_entry_first_refresh = AsyncMock()
    return mock


# ---------------------------------------------------------------------------
# Patches für alle Koordinator-Klassen + er-Modul
# ---------------------------------------------------------------------------

_PATCH_BASE = "custom_components.geosphere_austria_plus"

_BASE_DATA = {
    CONF_LATITUDE: 48.21,
    CONF_LONGITUDE: 16.37,
    CONF_FORECAST_MODELS: [DEFAULT_FORECAST_MODEL],
}


class TestWarningsCoordinatorConditional:
    async def test_warnings_enabled_coordinator_created(self):
        entry = _make_entry(data={**_BASE_DATA, CONF_ENABLE_WARNINGS: True})
        hass = _make_hass()
        warnings_instance = _make_coordinator_mock()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator", return_value=warnings_instance) as MockWarnings,
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockWarnings.assert_called_once()
        assert DATA_WARNINGS in hass.data[DOMAIN][entry.entry_id]

    async def test_warnings_disabled_coordinator_not_created(self):
        entry = _make_entry(data={**_BASE_DATA, CONF_ENABLE_WARNINGS: False})
        hass = _make_hass()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator") as MockWarnings,
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockWarnings.assert_not_called()
        assert DATA_WARNINGS not in hass.data[DOMAIN][entry.entry_id]

    async def test_warnings_missing_key_defaults_to_enabled(self):
        """Rückwärtskompatibilität: fehlender Schlüssel → Warnungen aktiv."""
        entry = _make_entry(data=_BASE_DATA)  # kein CONF_ENABLE_WARNINGS
        hass = _make_hass()
        warnings_instance = _make_coordinator_mock()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator", return_value=warnings_instance) as MockWarnings,
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockWarnings.assert_called_once()

    async def test_warnings_disabled_via_options_overrides_data(self):
        """Options haben Vorrang: data=True, options=False → deaktiviert."""
        entry = _make_entry(
            data={**_BASE_DATA, CONF_ENABLE_WARNINGS: True},
            options={CONF_ENABLE_WARNINGS: False},
        )
        hass = _make_hass()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator") as MockWarnings,
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockWarnings.assert_not_called()


class TestAirQualityCoordinatorConditional:
    async def test_air_quality_enabled_coordinator_created(self):
        entry = _make_entry(data={**_BASE_DATA, CONF_ENABLE_AIR_QUALITY: True})
        hass = _make_hass()
        aq_instance = _make_coordinator_mock()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator", return_value=aq_instance) as MockAQ,
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockAQ.assert_called_once()
        assert DATA_AIR_QUALITY in hass.data[DOMAIN][entry.entry_id]

    async def test_air_quality_disabled_coordinator_not_created(self):
        entry = _make_entry(data={**_BASE_DATA, CONF_ENABLE_AIR_QUALITY: False})
        hass = _make_hass()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator") as MockAQ,
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockAQ.assert_not_called()
        assert DATA_AIR_QUALITY not in hass.data[DOMAIN][entry.entry_id]

    async def test_air_quality_missing_key_defaults_to_enabled(self):
        """Rückwärtskompatibilität: fehlender Schlüssel → Luftqualität aktiv."""
        entry = _make_entry(data=_BASE_DATA)  # kein CONF_ENABLE_AIR_QUALITY
        hass = _make_hass()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator", return_value=_make_coordinator_mock()) as MockAQ,
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockAQ.assert_called_once()

    async def test_air_quality_disabled_via_options_overrides_data(self):
        """Options haben Vorrang: data=True, options=False → deaktiviert."""
        entry = _make_entry(
            data={**_BASE_DATA, CONF_ENABLE_AIR_QUALITY: True},
            options={CONF_ENABLE_AIR_QUALITY: False},
        )
        hass = _make_hass()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator") as MockAQ,
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockAQ.assert_not_called()


class TestForecastModelsConditional:
    async def test_zero_models_no_forecast_coordinators(self):
        """Leere Modellliste → keine Forecast-Koordinatoren."""
        entry = _make_entry(data={
            CONF_LATITUDE: 48.21,
            CONF_LONGITUDE: 16.37,
            CONF_FORECAST_MODELS: [],
        })
        hass = _make_hass()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator") as MockForecast,
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockForecast.assert_not_called()
        assert hass.data[DOMAIN][entry.entry_id][DATA_FORECASTS] == {}

    async def test_zero_models_via_options_overrides_data(self):
        """Options [] überschreibt data [nwp] → keine Forecast-Koordinatoren."""
        entry = _make_entry(
            data={CONF_LATITUDE: 48.21, CONF_LONGITUDE: 16.37, CONF_FORECAST_MODELS: [DEFAULT_FORECAST_MODEL]},
            options={CONF_FORECAST_MODELS: []},
        )
        hass = _make_hass()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator") as MockForecast,
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockForecast.assert_not_called()

    async def test_legacy_entry_without_forecast_models_key_uses_default(self):
        """Alte Einträge ohne CONF_FORECAST_MODELS fallen auf DEFAULT_FORECAST_MODEL zurück."""
        entry = _make_entry(data={CONF_LATITUDE: 48.21, CONF_LONGITUDE: 16.37})
        hass = _make_hass()
        forecast_instance = _make_coordinator_mock()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator", return_value=forecast_instance) as MockForecast,
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator", return_value=_make_coordinator_mock()),
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockForecast.assert_called_once()
        _, kwargs = MockForecast.call_args
        assert DEFAULT_FORECAST_MODEL in MockForecast.call_args.args

    async def test_all_features_disabled(self):
        """Alle optionalen Features deaktiviert + 0 Modelle → nur TAWES-Koordinator (falls Station)."""
        entry = _make_entry(data={
            CONF_LATITUDE: 48.21,
            CONF_LONGITUDE: 16.37,
            CONF_FORECAST_MODELS: [],
            CONF_ENABLE_WARNINGS: False,
            CONF_ENABLE_AIR_QUALITY: False,
        })
        hass = _make_hass()

        with (
            patch(f"{_PATCH_BASE}.GeoSphereForecastCoordinator") as MockForecast,
            patch(f"{_PATCH_BASE}.GeoSphereWarningsCoordinator") as MockWarnings,
            patch(f"{_PATCH_BASE}.GeoSphereAirQualityCoordinator") as MockAQ,
            patch(f"{_PATCH_BASE}.er") as mock_er,
        ):
            mock_er.async_entries_for_config_entry.return_value = []
            from custom_components.geosphere_austria_plus import async_setup_entry
            await async_setup_entry(hass, entry)

        MockForecast.assert_not_called()
        MockWarnings.assert_not_called()
        MockAQ.assert_not_called()
        coordinators = hass.data[DOMAIN][entry.entry_id]
        assert DATA_FORECASTS in coordinators
        assert coordinators[DATA_FORECASTS] == {}
        assert DATA_WARNINGS not in coordinators
        assert DATA_AIR_QUALITY not in coordinators


class TestAsyncUnloadEntry:
    async def test_unload_removes_entry_from_hass_data(self):
        entry = _make_entry(data=_BASE_DATA)
        hass = _make_hass()
        hass.data = {DOMAIN: {entry.entry_id: {"some": "data"}}}
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        from custom_components.geosphere_austria_plus import async_unload_entry
        result = await async_unload_entry(hass, entry)

        assert result is True
        assert entry.entry_id not in hass.data[DOMAIN]

    async def test_unload_keeps_entry_when_unload_fails(self):
        entry = _make_entry(data=_BASE_DATA)
        hass = _make_hass()
        hass.data = {DOMAIN: {entry.entry_id: {"some": "data"}}}
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        from custom_components.geosphere_austria_plus import async_unload_entry
        result = await async_unload_entry(hass, entry)

        assert result is False
        assert entry.entry_id in hass.data[DOMAIN]
