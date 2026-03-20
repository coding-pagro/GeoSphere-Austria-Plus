"""Config Flow für GeoSphere Austria Plus."""
from __future__ import annotations

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

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            models = user_input.get(CONF_FORECAST_MODELS) or [DEFAULT_FORECAST_MODEL]
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
    async_get_options_flow = GeoSphereOptionsFlowHandler

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            station_id = user_input[CONF_STATION_ID].strip()
            models = user_input.get(CONF_FORECAST_MODELS) or [DEFAULT_FORECAST_MODEL]

            # Duplikat prüfen (eine Konfiguration pro Station)
            await self.async_set_unique_id(station_id)
            self._abort_if_unique_id_configured()

            # Station validieren
            api = GeoSphereApi(async_get_clientsession(self.hass))
            try:
                data = await api.get_current(station_id)
                lat = data.get("_lat")
                lon = data.get("_lon")
                station_name = await api.get_station_name(station_id)
            except GeoSphereApiError:
                errors[CONF_STATION_ID] = "invalid_station"
            else:
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

        schema = vol.Schema(
            {
                vol.Required(CONF_STATION_ID): str,
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
