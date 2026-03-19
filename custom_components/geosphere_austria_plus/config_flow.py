"""Config Flow für GeoSphere Austria Plus."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GeoSphereApi, GeoSphereApiError
from .const import (
    DOMAIN,
    DEFAULT_NAME,
    CONF_STATION_ID,
    CONF_FORECAST_MODEL,
    FORECAST_MODELS,
    DEFAULT_FORECAST_MODEL,
)


class GeoSphereAustriaPlusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config Flow Handler."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            station_id = user_input[CONF_STATION_ID].strip()
            model = user_input.get(CONF_FORECAST_MODEL, DEFAULT_FORECAST_MODEL)

            # Duplikat prüfen
            await self.async_set_unique_id(f"{station_id}_{model}")
            self._abort_if_unique_id_configured()

            # Station validieren
            api = GeoSphereApi(async_get_clientsession(self.hass))
            try:
                data = await api.get_current(station_id)
                lat = data.get("_lat")
                lon = data.get("_lon")
            except GeoSphereApiError:
                errors[CONF_STATION_ID] = "invalid_station"
            else:
                return self.async_create_entry(
                    title=f"GeoSphere {station_id}",
                    data={
                        CONF_STATION_ID: station_id,
                        CONF_FORECAST_MODEL: model,
                        "lat": lat,
                        "lon": lon,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_STATION_ID): str,
                vol.Optional(
                    CONF_FORECAST_MODEL, default=DEFAULT_FORECAST_MODEL
                ): vol.In(FORECAST_MODELS),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
