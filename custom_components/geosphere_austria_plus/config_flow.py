"""Config Flow für GeoSphere Austria Plus."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import GeoSphereApi, GeoSphereApiError
from .const import (
    DOMAIN,
    DEFAULT_NAME,
    CONF_STATION_ID,
    CONF_FORECAST_MODELS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STATION_NAME,
    FORECAST_MODELS,
    DEFAULT_FORECAST_MODEL,
    FORECAST_MODEL_LABELS,
)


class GeoSphereOptionsFlowHandler(config_entries.OptionsFlow):
    """Vorhersagemodelle nach der Ersteinrichtung ändern."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if user_input is not None:
            raw = user_input.get(CONF_FORECAST_MODELS) or []
            models = [m for m in raw if m in FORECAST_MODELS] or [DEFAULT_FORECAST_MODEL]
            return self.async_create_entry(title="", data={CONF_FORECAST_MODELS: models})

        current_models = (
            self.config_entry.options.get(CONF_FORECAST_MODELS)
            or self.config_entry.data.get(CONF_FORECAST_MODELS)
            or [DEFAULT_FORECAST_MODEL]
        )
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_FORECAST_MODELS, default=current_models
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
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


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
        errors = {}

        # Stationsliste einmalig laden
        if self._stations is None:
            api = GeoSphereApi(async_get_clientsession(self.hass))
            try:
                self._stations = await api.get_stations()
            except GeoSphereApiError:
                self._stations = []

        if user_input is not None:
            station_id = user_input[CONF_STATION_ID].strip()
            # Nur bekannte Modell-IDs akzeptieren
            raw_models = user_input.get(CONF_FORECAST_MODELS) or []
            models = [m for m in raw_models if m in FORECAST_MODELS] or [DEFAULT_FORECAST_MODEL]

            await self.async_set_unique_id(station_id)
            self._abort_if_unique_id_configured()

            station_meta = next((s for s in self._stations if s["id"] == station_id), None)
            lat = station_meta["lat"] if station_meta else None
            lon = station_meta["lon"] if station_meta else None
            station_name = station_meta["name"] if station_meta else station_id

            # Koordinaten-Fallback über aktuelle Messwerte (z. B. wenn Stationsliste leer war)
            if lat is None or lon is None:
                api = GeoSphereApi(async_get_clientsession(self.hass))
                try:
                    data = await api.get_current(station_id)
                    lat = data.get("_lat")
                    lon = data.get("_lon")
                except GeoSphereApiError:
                    errors[CONF_STATION_ID] = "invalid_station"

            if not errors:
                return self.async_create_entry(
                    title=station_name,
                    data={
                        CONF_STATION_ID: station_id,
                        CONF_FORECAST_MODELS: models,
                        CONF_LATITUDE: lat,
                        CONF_LONGITUDE: lon,
                        CONF_STATION_NAME: station_name,
                    },
                )

        station_options = [
            {"value": s["id"], "label": f"{s['name']} ({s['id']})"}
            for s in sorted(self._stations, key=lambda x: x["name"])
        ]

        if station_options:
            station_field = SelectSelector(
                SelectSelectorConfig(
                    options=station_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            # Fallback auf Texteingabe wenn Stationsliste nicht geladen werden konnte
            station_field = str
            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_STATION_ID): station_field,
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
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
