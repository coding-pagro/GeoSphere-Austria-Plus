"""Config Flow für GeoSphere Austria Plus."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
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
    CONF_ENABLE_WARNINGS,
    CONF_ENABLE_AIR_QUALITY,
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

    _stations: list[dict] | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._stations is None:
            api = GeoSphereApi(async_get_clientsession(self.hass))
            try:
                self._stations = await api.get_stations()
            except GeoSphereApiError:
                self._stations = []

        if user_input is not None:
            raw = user_input.get(CONF_FORECAST_MODELS) or []
            models = [m for m in raw if m in FORECAST_MODELS]

            name = (user_input.get(CONF_NAME) or "").strip() or self.config_entry.title
            lat = float(user_input[CONF_LATITUDE])
            lon = float(user_input[CONF_LONGITUDE])
            station_raw = user_input.get(CONF_STATION_ID) or _NO_STATION
            station_id: str | None = station_raw.strip() or None
            enable_warnings: bool = bool(user_input.get(CONF_ENABLE_WARNINGS, True))
            enable_air_quality: bool = bool(user_input.get(CONF_ENABLE_AIR_QUALITY, True))

            if name != self.config_entry.title:
                self.hass.config_entries.async_update_entry(self.config_entry, title=name)

            return self.async_create_entry(title="", data={
                CONF_NAME: name,
                CONF_LATITUDE: lat,
                CONF_LONGITUDE: lon,
                CONF_STATION_ID: station_id,
                CONF_FORECAST_MODELS: models,
                CONF_ENABLE_WARNINGS: enable_warnings,
                CONF_ENABLE_AIR_QUALITY: enable_air_quality,
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
        if CONF_FORECAST_MODELS in self.config_entry.options:
            current_models = self.config_entry.options[CONF_FORECAST_MODELS]
        elif CONF_FORECAST_MODELS in self.config_entry.data:
            current_models = self.config_entry.data[CONF_FORECAST_MODELS]
        else:
            current_models = [DEFAULT_FORECAST_MODEL]

        current_enable_warnings: bool = self.config_entry.options.get(
            CONF_ENABLE_WARNINGS,
            self.config_entry.data.get(CONF_ENABLE_WARNINGS, True),
        )
        current_enable_air_quality: bool = self.config_entry.options.get(
            CONF_ENABLE_AIR_QUALITY,
            self.config_entry.data.get(CONF_ENABLE_AIR_QUALITY, True),
        )

        schema = self._build_schema(
            current_name, current_lat, current_lon, current_station,
            current_models, current_enable_warnings, current_enable_air_quality,
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    def _build_schema(
        self,
        name: str,
        lat: float,
        lon: float,
        station: str,
        models: list[str],
        enable_warnings: bool = True,
        enable_air_quality: bool = True,
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
                NumberSelectorConfig(min=-90, max=90, step=0.001, mode="box")
            ),
            vol.Required(CONF_LONGITUDE, default=lon): NumberSelector(
                NumberSelectorConfig(min=-180, max=180, step=0.001, mode="box")
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
            vol.Optional(CONF_ENABLE_WARNINGS, default=enable_warnings): BooleanSelector(),
            vol.Optional(CONF_ENABLE_AIR_QUALITY, default=enable_air_quality): BooleanSelector(),
        })


class GeoSphereAustriaPlusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config Flow Handler."""

    VERSION = 1
    _stations: list[dict] | None = None

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> GeoSphereOptionsFlowHandler:
        return GeoSphereOptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._stations is None:
            api = GeoSphereApi(async_get_clientsession(self.hass))
            try:
                self._stations = await api.get_stations()
            except GeoSphereApiError:
                self._stations = []

        if user_input is not None:
            name = (user_input.get(CONF_NAME) or "").strip() or self.hass.config.location_name
            lat = float(user_input[CONF_LATITUDE])
            lon = float(user_input[CONF_LONGITUDE])
            station_raw = user_input.get(CONF_STATION_ID) or _NO_STATION
            station_id: str | None = station_raw.strip() or None

            raw_models = user_input.get(CONF_FORECAST_MODELS) or []
            models = [m for m in raw_models if m in FORECAST_MODELS]
            enable_warnings: bool = bool(user_input.get(CONF_ENABLE_WARNINGS, True))
            enable_air_quality: bool = bool(user_input.get(CONF_ENABLE_AIR_QUALITY, True))

            await self.async_set_unique_id(f"{round(lat, 3)}_{round(lon, 3)}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=name,
                data={
                    CONF_NAME: name,
                    CONF_LATITUDE: lat,
                    CONF_LONGITUDE: lon,
                    CONF_STATION_ID: station_id,
                    CONF_FORECAST_MODELS: models,
                    CONF_ENABLE_WARNINGS: enable_warnings,
                    CONF_ENABLE_AIR_QUALITY: enable_air_quality,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_schema(),
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
                NumberSelectorConfig(min=-90, max=90, step=0.001, mode="box")
            ),
            vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): NumberSelector(
                NumberSelectorConfig(min=-180, max=180, step=0.001, mode="box")
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
            vol.Optional(CONF_ENABLE_WARNINGS, default=True): BooleanSelector(),
            vol.Optional(CONF_ENABLE_AIR_QUALITY, default=True): BooleanSelector(),
        })
