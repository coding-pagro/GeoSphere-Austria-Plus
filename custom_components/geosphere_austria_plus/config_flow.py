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
    CONF_ENABLE_OPEN_METEO,
    CONF_OPEN_METEO_FORECAST_DAYS,
    FORECAST_MODELS,
    DEFAULT_FORECAST_MODEL,
    FORECAST_MODEL_LABELS,
    OPEN_METEO_FORECAST_DAYS_MIN,
    OPEN_METEO_FORECAST_DAYS_MAX,
    OPEN_METEO_FORECAST_DAYS_DEFAULT,
)

_LOGGER = logging.getLogger(__name__)

_NO_STATION = ""


def _station_options(stations: list[dict]) -> list[dict]:
    """Stations-Dropdown-Optionen inkl. Leer-Eintrag aufbauen."""
    return [{"value": _NO_STATION, "label": "— keine Station —"}] + [
        {"value": s["id"], "label": f"{s['name']} ({s['id']})"}
        for s in sorted(stations, key=lambda x: x["name"])
    ]


def _parse_user_input(user_input: dict[str, Any], default_name: str) -> dict[str, Any]:
    """User-Input in das gespeicherte entry.data-Format normalisieren.

    Modulweite Funktion (kein static method auf der Class), damit sowohl
    Config- als auch Reconfigure-Flow drauf zugreifen können — und damit
    Tests mit Class-Doubles arbeiten können, die nicht von ConfigFlow erben.
    """
    name = (user_input.get(CONF_NAME) or "").strip() or default_name
    lat = float(user_input[CONF_LATITUDE])
    lon = float(user_input[CONF_LONGITUDE])
    station_raw = user_input.get(CONF_STATION_ID) or _NO_STATION
    station_id: str | None = station_raw.strip() or None
    raw_models = user_input.get(CONF_FORECAST_MODELS) or []
    models = [m for m in raw_models if m in FORECAST_MODELS]
    return {
        CONF_NAME: name,
        CONF_LATITUDE: lat,
        CONF_LONGITUDE: lon,
        CONF_STATION_ID: station_id,
        CONF_FORECAST_MODELS: models,
        CONF_ENABLE_WARNINGS: bool(user_input.get(CONF_ENABLE_WARNINGS, True)),
        CONF_ENABLE_AIR_QUALITY: bool(user_input.get(CONF_ENABLE_AIR_QUALITY, True)),
        CONF_ENABLE_OPEN_METEO: bool(user_input.get(CONF_ENABLE_OPEN_METEO, False)),
        CONF_OPEN_METEO_FORECAST_DAYS: int(
            user_input.get(CONF_OPEN_METEO_FORECAST_DAYS, OPEN_METEO_FORECAST_DAYS_DEFAULT)
        ),
    }


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
            enable_open_meteo: bool = bool(user_input.get(CONF_ENABLE_OPEN_METEO, False))
            open_meteo_forecast_days: int = int(
                user_input.get(CONF_OPEN_METEO_FORECAST_DAYS, OPEN_METEO_FORECAST_DAYS_DEFAULT)
            )

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
                CONF_ENABLE_OPEN_METEO: enable_open_meteo,
                CONF_OPEN_METEO_FORECAST_DAYS: open_meteo_forecast_days,
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
        current_enable_open_meteo: bool = self.config_entry.options.get(
            CONF_ENABLE_OPEN_METEO,
            self.config_entry.data.get(CONF_ENABLE_OPEN_METEO, False),
        )
        current_om_forecast_days: int = int(self.config_entry.options.get(
            CONF_OPEN_METEO_FORECAST_DAYS,
            self.config_entry.data.get(CONF_OPEN_METEO_FORECAST_DAYS, OPEN_METEO_FORECAST_DAYS_DEFAULT),
        ))

        schema = self._build_schema(
            current_name, current_lat, current_lon, current_station,
            current_models, current_enable_warnings, current_enable_air_quality,
            current_enable_open_meteo, current_om_forecast_days,
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
        enable_open_meteo: bool = False,
        open_meteo_forecast_days: int = OPEN_METEO_FORECAST_DAYS_DEFAULT,
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
            vol.Optional(CONF_ENABLE_OPEN_METEO, default=enable_open_meteo): BooleanSelector(),
            vol.Optional(
                CONF_OPEN_METEO_FORECAST_DAYS, default=open_meteo_forecast_days
            ): NumberSelector(
                NumberSelectorConfig(
                    min=OPEN_METEO_FORECAST_DAYS_MIN,
                    max=OPEN_METEO_FORECAST_DAYS_MAX,
                    step=1,
                    mode="slider",
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
        return GeoSphereOptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._stations is None:
            api = GeoSphereApi(async_get_clientsession(self.hass))
            try:
                self._stations = await api.get_stations()
            except GeoSphereApiError:
                self._stations = []

        if user_input is not None:
            data = _parse_user_input(user_input, self.hass.config.location_name)
            await self.async_set_unique_id(
                f"{round(data[CONF_LATITUDE], 5)}_{round(data[CONF_LONGITUDE], 5)}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=data[CONF_NAME], data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_schema(),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Bestehenden Eintrag rekonfigurieren (Gold-Quality-Scale Anforderung).

        Ermöglicht User-Änderungen an Standort, Station und Forecast-Modellen
        nach der Ersteinrichtung — ohne den Eintrag löschen zu müssen.
        """
        if self._stations is None:
            api = GeoSphereApi(async_get_clientsession(self.hass))
            try:
                self._stations = await api.get_stations()
            except GeoSphereApiError:
                self._stations = []

        entry = self._get_reconfigure_entry()

        if user_input is not None:
            data = _parse_user_input(user_input, entry.title)
            # unique_id auf neuen Koordinaten setzen; Kollision mit *anderen*
            # Einträgen verhindern (gleicher Eintrag ist erlaubt).
            new_unique = f"{round(data[CONF_LATITUDE], 5)}_{round(data[CONF_LONGITUDE], 5)}"
            await self.async_set_unique_id(new_unique)
            self._abort_if_unique_id_mismatch(reason="reconfigure_unique_id_mismatch")
            return self.async_update_reload_and_abort(
                entry, data=data, title=data[CONF_NAME]
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._build_schema_with_defaults(entry),
        )

    def _build_schema_with_defaults(self, entry: config_entries.ConfigEntry) -> vol.Schema:
        """Schema mit Default-Werten aus dem bestehenden Entry (für Reconfigure)."""
        def _current(key: str, fallback: Any) -> Any:
            if key in entry.options:
                return entry.options[key]
            return entry.data.get(key, fallback)

        current_name = entry.title
        current_lat = _current(CONF_LATITUDE, self.hass.config.latitude)
        current_lon = _current(CONF_LONGITUDE, self.hass.config.longitude)
        current_station = _current(CONF_STATION_ID, None) or _NO_STATION
        if CONF_FORECAST_MODELS in entry.options:
            current_models = entry.options[CONF_FORECAST_MODELS]
        elif CONF_FORECAST_MODELS in entry.data:
            current_models = entry.data[CONF_FORECAST_MODELS]
        else:
            current_models = [DEFAULT_FORECAST_MODEL]

        return self._schema_from_defaults(
            current_name, current_lat, current_lon, current_station, current_models,
            _current(CONF_ENABLE_WARNINGS, True),
            _current(CONF_ENABLE_AIR_QUALITY, True),
            _current(CONF_ENABLE_OPEN_METEO, False),
            int(_current(CONF_OPEN_METEO_FORECAST_DAYS, OPEN_METEO_FORECAST_DAYS_DEFAULT)),
        )

    def _build_schema(self) -> vol.Schema:
        """Schema mit HA-System-Defaults für Erstkonfiguration."""
        return self._schema_from_defaults(
            self.hass.config.location_name,
            self.hass.config.latitude,
            self.hass.config.longitude,
            _NO_STATION,
            [DEFAULT_FORECAST_MODEL],
            True, True, False, OPEN_METEO_FORECAST_DAYS_DEFAULT,
        )

    def _schema_from_defaults(
        self,
        name: str,
        lat: float,
        lon: float,
        station: str,
        models: list[str],
        enable_warnings: bool,
        enable_air_quality: bool,
        enable_open_meteo: bool,
        open_meteo_forecast_days: int,
    ) -> vol.Schema:
        """Gemeinsame Schema-Konstruktion für user- und reconfigure-Step."""
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
            vol.Optional(CONF_ENABLE_OPEN_METEO, default=enable_open_meteo): BooleanSelector(),
            vol.Optional(
                CONF_OPEN_METEO_FORECAST_DAYS, default=open_meteo_forecast_days
            ): NumberSelector(
                NumberSelectorConfig(
                    min=OPEN_METEO_FORECAST_DAYS_MIN,
                    max=OPEN_METEO_FORECAST_DAYS_MAX,
                    step=1,
                    mode="slider",
                )
            ),
        })
