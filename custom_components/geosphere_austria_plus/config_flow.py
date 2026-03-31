"""Config Flow für GeoSphere Austria Plus."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import GeoSphereApi, GeoSphereApiError
from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_STATION_ID,
    CONF_FORECAST_MODELS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STATION_NAME,
    FORECAST_MODELS,
    DEFAULT_FORECAST_MODEL,
    FORECAST_MODEL_LABELS,
)

_LOGGER = logging.getLogger(__name__)

_NO_STATION = ""


def _station_options(stations: list[dict]) -> list[dict]:
    """Stations-Dropdown-Optionen inkl. Leer-Eintrag aufbauen."""
    return [{"value": _NO_STATION, "label": "— keine Station —"}] + [
        {"value": s["id"], "label": f"{s['name']} ({s['id']})"}
        for s in sorted(stations, key=lambda x: x["name"])
    ]


class GeoSphereOptionsFlowHandler(config_entries.OptionsFlow):
    """Einstellungen nach der Ersteinrichtung ändern."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialisieren."""
        super().__init__()
        self.config_entry = config_entry
        self._stations: list[dict] | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._stations is None:
            api = GeoSphereApi(async_get_clientsession(self.hass))
            try:
                self._stations = await api.get_stations()
            except GeoSphereApiError:
                self._stations = []

        if user_input is not None:
            raw = user_input.get(CONF_FORECAST_MODELS) or []
            models = [m for m in raw if m in FORECAST_MODELS] or [DEFAULT_FORECAST_MODEL]

            name = (user_input.get(CONF_NAME) or "").strip() or self.config_entry.title
            lat = float(user_input[CONF_LATITUDE])
            lon = float(user_input[CONF_LONGITUDE])
            station_raw = user_input.get(CONF_STATION_ID) or _NO_STATION
            station_id: str | None = station_raw.strip() or None

            station_name: str | None = None
            if station_id:
                meta = next((s for s in self._stations if s["id"] == station_id), None)
                station_name = meta["name"] if meta else station_id

            if name != self.config_entry.title:
                self.hass.config_entries.async_update_entry(self.config_entry, title=name)

            return self.async_create_entry(title="", data={
                CONF_NAME: name,
                CONF_LATITUDE: lat,
                CONF_LONGITUDE: lon,
                CONF_STATION_ID: station_id,
                CONF_STATION_NAME: station_name,
                CONF_FORECAST_MODELS: models,
            })

        # Aktuelle Werte — Options haben Vorrang vor Data
        current_name = (
            self.config_entry.options.get(CONF_NAME)
            or self.config_entry.data.get(CONF_NAME)
            or self.config_entry.title
        )
        current_lat = (
            self.config_entry.options[CONF_LATITUDE]
            if CONF_LATITUDE in self.config_entry.options
            else self.config_entry.data.get(CONF_LATITUDE, self.hass.config.latitude)
        )
        current_lon = (
            self.config_entry.options[CONF_LONGITUDE]
            if CONF_LONGITUDE in self.config_entry.options
            else self.config_entry.data.get(CONF_LONGITUDE, self.hass.config.longitude)
        )
        current_station = (
            self.config_entry.options[CONF_STATION_ID]
            if CONF_STATION_ID in self.config_entry.options
            else self.config_entry.data.get(CONF_STATION_ID)
        ) or _NO_STATION
        current_models = (
            self.config_entry.options.get(CONF_FORECAST_MODELS)
            or self.config_entry.data.get(CONF_FORECAST_MODELS)
            or [DEFAULT_FORECAST_MODEL]
        )

        schema = self._build_schema(
            current_name, current_lat, current_lon, current_station, current_models
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    def _build_schema(
        self,
        name: str,
        lat: float,
        lon: float,
        station: str,
        models: list[str],
    ) -> vol.Schema:
        station_field: Any
        if self._stations:
            station_field = SelectSelector(
                SelectSelectorConfig(
                    options=_station_options(self._stations),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            station_field = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))

        return vol.Schema({
            vol.Required(CONF_NAME, default=name): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(CONF_LATITUDE, default=lat): NumberSelector(
                NumberSelectorConfig(min=-90, max=90, step=0.0001, mode="box")
            ),
            vol.Required(CONF_LONGITUDE, default=lon): NumberSelector(
                NumberSelectorConfig(min=-180, max=180, step=0.0001, mode="box")
            ),
            vol.Optional(CONF_STATION_ID, default=station): station_field,
            vol.Optional(CONF_FORECAST_MODELS, default=models): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": k, "label": FORECAST_MODEL_LABELS[k]}
                        for k in FORECAST_MODELS
                    ],
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        })


class GeoSphereAustriaPlusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config Flow Handler."""

    VERSION = 1
    _stations: list[dict] | None = None

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> GeoSphereOptionsFlowHandler:
        return GeoSphereOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        errors: dict[str, str] = {}

        try:
            if self._stations is None:
                api = GeoSphereApi(async_get_clientsession(self.hass))
                try:
                    self._stations = await api.get_stations()
                except GeoSphereApiError:
                    self._stations = []
        except Exception:
            _LOGGER.exception("Fehler beim Initialisieren des Config Flows")
            raise

        if user_input is not None:
            name = (user_input.get(CONF_NAME) or "").strip() or self.hass.config.location_name
            lat = float(user_input[CONF_LATITUDE])
            lon = float(user_input[CONF_LONGITUDE])
            station_raw = user_input.get(CONF_STATION_ID) or _NO_STATION
            station_id: str | None = station_raw.strip() or None

            raw_models = user_input.get(CONF_FORECAST_MODELS) or []
            models = [m for m in raw_models if m in FORECAST_MODELS] or [DEFAULT_FORECAST_MODEL]

            await self.async_set_unique_id(f"{round(lat, 3)}_{round(lon, 3)}")
            self._abort_if_unique_id_configured()

            station_name: str | None = None
            if station_id:
                meta = next(
                    (s for s in (self._stations or []) if s["id"] == station_id), None
                )
                station_name = meta["name"] if meta else station_id

            if not errors:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_NAME: name,
                        CONF_LATITUDE: lat,
                        CONF_LONGITUDE: lon,
                        CONF_STATION_ID: station_id,
                        CONF_STATION_NAME: station_name,
                        CONF_FORECAST_MODELS: models,
                    },
                )

        try:
            schema = self._build_schema()
        except Exception:
            _LOGGER.exception("Fehler beim Erstellen des Config-Flow-Schemas")
            raise
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    def _build_schema(self) -> vol.Schema:
        station_field: Any
        if self._stations:
            station_field = SelectSelector(
                SelectSelectorConfig(
                    options=_station_options(self._stations),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            station_field = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))

        return vol.Schema({
            vol.Required(CONF_NAME, default=self.hass.config.location_name): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): NumberSelector(
                NumberSelectorConfig(min=-90, max=90, step=0.0001, mode="box")
            ),
            vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): NumberSelector(
                NumberSelectorConfig(min=-180, max=180, step=0.0001, mode="box")
            ),
            vol.Optional(CONF_STATION_ID, default=_NO_STATION): station_field,
            vol.Optional(
                CONF_FORECAST_MODELS, default=[DEFAULT_FORECAST_MODEL]
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": k, "label": FORECAST_MODEL_LABELS[k]}
                        for k in FORECAST_MODELS
                    ],
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        })
