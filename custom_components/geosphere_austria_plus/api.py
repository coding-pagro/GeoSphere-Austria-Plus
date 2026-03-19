"""GeoSphere Austria DataHub API Client."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .const import API_BASE, TAWES_RESOURCE, TAWES_PARAMS, NWP_PARAMS, ENSEMBLE_PARAMS, ENSEMBLE_PARAM_MAP

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=30)


class GeoSphereApiError(Exception):
    """Allgemeiner API-Fehler."""


class GeoSphereApi:
    """Asynchroner Client für die GeoSphere Austria DataHub API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Stationsliste
    # ------------------------------------------------------------------

    async def get_stations(self) -> list[dict[str, Any]]:
        """Gibt alle verfügbaren TAWES-Stationen zurück."""
        url = f"{API_BASE}/station/current/{TAWES_RESOURCE}/metadata"
        try:
            async with self._session.get(url, timeout=TIMEOUT) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GeoSphereApiError(f"Fehler beim Abrufen der Stationsliste: {err}") from err

        stations = []
        for station in data.get("stations", []):
            stations.append(
                {
                    "id": str(station["id"]),
                    "name": station.get("name", str(station["id"])),
                    "lat": station.get("lat"),
                    "lon": station.get("lon"),
                    "altitude": station.get("altitude"),
                }
            )
        return stations

    # ------------------------------------------------------------------
    # Aktuelle Messwerte (TAWES)
    # ------------------------------------------------------------------

    async def get_current(self, station_id: str) -> dict[str, Any]:
        """
        Aktuelle Messwerte einer Station abrufen.
        Gibt ein flaches Dict mit Parameternamen → Wert zurück.
        Nicht verfügbare Parameter werden automatisch aus der Anfrage entfernt.
        """
        params = TAWES_PARAMS
        for _attempt in range(2):
            url = (
                f"{API_BASE}/station/current/{TAWES_RESOURCE}"
                f"?parameters={params}&station_ids={station_id}&output_format=geojson"
            )
            try:
                async with self._session.get(url, timeout=TIMEOUT) as resp:
                    if resp.status == 400:
                        body = await resp.json()
                        detail = body.get("detail", "")
                        missing = self._extract_missing_params(detail)
                        if missing and _attempt == 0:
                            _LOGGER.debug(
                                "Station %s: Parameter %s nicht verfügbar, wird übersprungen",
                                station_id, missing,
                            )
                            params = ",".join(
                                p for p in params.split(",") if p not in missing
                            )
                            continue
                        raise GeoSphereApiError(
                            f"Fehler beim Abrufen aktueller Daten: HTTP 400 – {detail}"
                        )
                    resp.raise_for_status()
                    data = await resp.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise GeoSphereApiError(f"Fehler beim Abrufen aktueller Daten: {err}") from err
            return self._parse_station_geojson(data, station_id)

        raise GeoSphereApiError(f"Fehler beim Abrufen aktueller Daten für Station {station_id}")

    @staticmethod
    def _normalize_ensemble_params(entries: list[dict]) -> list[dict]:
        """Benennt Ensemble-Parameternamen in NWP-Parameternamen um.

        Ensemble liefert z. B. t2m_p50 statt t2m. Durch die Umbenennung
        kann weather.py beide Modelle identisch verarbeiten.
        Sunshine-Dauer (sundur, s/h) wird in approximative Wolkenbedeckung
        tcc [0–1] umgerechnet: tcc = 1 - sundur / 3600.
        """
        normalized = []
        for entry in entries:
            new = {"datetime": entry.get("datetime")}
            for old_key, new_key in ENSEMBLE_PARAM_MAP.items():
                new[new_key] = entry.get(old_key)
            # Wolkenbedeckung aus Sonnenscheindauer ableiten
            sundur = new.pop("sundur", None)
            if sundur is not None:
                new["tcc"] = max(0.0, 1.0 - sundur / 3600.0)
            normalized.append(new)
        return normalized

    @staticmethod
    def _extract_missing_params(detail: str) -> set[str]:
        """Extrahiert Parameternamen aus einer API-400-Fehlermeldung."""
        import re
        match = re.search(r"\{([^}]+)\}", detail)
        if not match:
            return set()
        return {p.strip().strip("'\"") for p in match.group(1).split(",")}

    def _parse_station_geojson(self, data: dict, station_id: str) -> dict[str, Any]:
        """GeoJSON-Antwort in flaches Parameterwert-Dict umwandeln."""
        features = data.get("features", [])
        if not features:
            raise GeoSphereApiError(f"Keine Daten für Station {station_id}")

        feature = features[0]
        props = feature.get("properties", {})
        parameters = props.get("parameters", {})

        result: dict[str, Any] = {}
        for param_name, param_data in parameters.items():
            values = param_data.get("data", [])
            result[param_name] = values[-1] if values else None

        # Koordinaten für spätere Verwendung
        coords = feature.get("geometry", {}).get("coordinates", [])
        if len(coords) >= 2:
            result["_lon"] = coords[0]
            result["_lat"] = coords[1]
        if len(coords) >= 3:
            result["_alt"] = coords[2]

        return result

    # ------------------------------------------------------------------
    # Vorhersage (NWP / Ensemble / Nowcast)
    # ------------------------------------------------------------------

    async def get_forecast(
        self,
        lat: float,
        lon: float,
        model: str,
    ) -> list[dict[str, Any]]:
        """
        Vorhersagedaten für einen Koordinatenpunkt abrufen.
        Gibt eine Liste von stündlichen Vorhersage-Dicts zurück.
        Nicht verfügbare Parameter werden automatisch aus der Anfrage entfernt.
        """
        if "ensemble" in model:
            params = ENSEMBLE_PARAMS
        elif "nwp" in model:
            params = NWP_PARAMS
        else:
            params = "rain_acc,snow_acc,t2m,rh2m,u10m,v10m,tcc"  # Nowcast

        for _attempt in range(2):
            url = (
                f"{API_BASE}/timeseries/forecast/{model}"
                f"?parameters={params}&lat_lon={lat},{lon}&output_format=geojson"
            )
            try:
                async with self._session.get(url, timeout=TIMEOUT) as resp:
                    if resp.status == 400:
                        body = await resp.json()
                        detail = body.get("detail", "")
                        missing = self._extract_missing_params(detail)
                        if missing and _attempt == 0:
                            _LOGGER.debug(
                                "Vorhersage: Parameter %s nicht verfügbar, wird übersprungen",
                                missing,
                            )
                            params = ",".join(
                                p for p in params.split(",") if p not in missing
                            )
                            continue
                        raise GeoSphereApiError(
                            f"Fehler beim Abrufen der Vorhersage: HTTP 400 – {detail}"
                        )
                    resp.raise_for_status()
                    data = await resp.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise GeoSphereApiError(f"Fehler beim Abrufen der Vorhersage: {err}") from err
            result = self._parse_forecast_geojson(data)
            if "ensemble" in model:
                result = self._normalize_ensemble_params(result)
            return result

        raise GeoSphereApiError("Fehler beim Abrufen der Vorhersage")

    def _parse_forecast_geojson(self, data: dict) -> list[dict[str, Any]]:
        """
        NWP GeoJSON → Liste von Zeitschritt-Dicts.
        Jedes Dict hat 'datetime' + alle Parameter als Schlüssel.

        Die API liefert Zeitstempel auf oberster Ebene unter 'timestamps',
        die Parameterwerte als 'data'-Arrays in features[0].properties.parameters.
        """
        features = data.get("features", [])
        if not features:
            return []

        # Zeitstempel: immer auf oberster GeoJSON-Ebene
        times: list[str] = (
            data.get("timestamps")
            or data.get("features", [{}])[0].get("properties", {}).get("datetimes", [])
        )
        if not times:
            return []

        feature = features[0]
        props = feature.get("properties", {})
        param_data: dict[str, list] = {
            param_name: param_info.get("data", [])
            for param_name, param_info in props.get("parameters", {}).items()
        }

        result = []
        for i, ts in enumerate(times):
            entry: dict[str, Any] = {"datetime": ts}
            for param_name, values in param_data.items():
                entry[param_name] = values[i] if i < len(values) else None
            result.append(entry)

        return result

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    async def validate_station(self, station_id: str) -> bool:
        """Prüft, ob eine Stations-ID gültig ist."""
        try:
            await self.get_current(station_id)
            return True
        except GeoSphereApiError:
            return False
