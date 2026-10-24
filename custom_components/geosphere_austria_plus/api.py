"""GeoSphere Austria DataHub API Client."""
from __future__ import annotations

import asyncio
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import (
    API_BASE,
    TAWES_RESOURCE,
    TAWES_PARAMS,
    NWP_PARAMS,
    NWP_PARAM_MAP,
    NOWCAST_PARAMS,
    ENSEMBLE_PARAMS,
    ENSEMBLE_PARAM_MAP,
    WARNINGS_API_BASE,
    CHEM_RESOURCE,
    CHEM_PARAMS,
)

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
                data = await resp.json(content_type=None)
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
                f"?parameters={params}&station_ids={quote(station_id, safe='')}&output_format=geojson"
            )
            try:
                async with self._session.get(url, timeout=TIMEOUT) as resp:
                    if resp.status == 400:
                        body = await resp.json(content_type=None)
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
                    data = await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise GeoSphereApiError(f"Fehler beim Abrufen aktueller Daten: {err}") from err
            return self._parse_station_geojson(data, station_id)

        raise GeoSphereApiError(f"Fehler beim Abrufen aktueller Daten für Station {station_id}")

    @staticmethod
    def _normalize_v2_params(
        entries: list[dict[str, Any]], param_map: dict[str, str]
    ) -> list[dict[str, Any]]:
        """NWP-/Ensemble-v2-Parameter in interne Namen und Einheiten umwandeln.

        v2 nutzt GRIB-Kurznamen (2t, 10u, …), Ensemble zusätzlich das Suffix
        _p50. Durch die Umbenennung kann weather.py alle Modelle identisch
        verarbeiten. Einheiten werden angeglichen: tcc % → Anteil 0–1,
        msl Pa → hPa. Niederschlag und Strahlung sind bereits Intervallwerte.
        """
        normalized = []
        for entry in entries:
            new: dict[str, Any] = {"datetime": entry.get("datetime")}
            for api_key, internal_key in param_map.items():
                new[internal_key] = entry.get(api_key)
            if new.get("tcc") is not None:
                new["tcc"] = new["tcc"] / 100.0
            if new.get("pressure") is not None:
                new["pressure"] = round(new["pressure"] / 100.0, 1)
            normalized.append(new)
        return normalized

    @staticmethod
    def _normalize_nowcast_params(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Nowcast-Parameter in NWP-kompatible Namen umwandeln.

        Nowcast liefert rr (Niederschlagsrate kg/m²) + pt (Niederschlagstyp)
        statt rain_acc/snow_acc, sowie ff/dd statt u10m/v10m.
        Wolkenbedeckung (tcc) ist nicht verfügbar → None.

        pt-Kodierung (WMO-Konvention): 0/255=kein Niederschlag, 1=Regen,
        2=Schnee, 3=gemischt/Schneeregen.
        """
        normalized = []
        for entry in entries:
            rr = entry.get("rr") or 0.0
            pt_raw = entry.get("pt")
            try:
                pt_int = int(pt_raw) if pt_raw is not None else 255
            except (ValueError, TypeError):
                pt_int = 255

            if rr == 0 or pt_int in (0, 255):
                rain_acc, snow_acc = 0.0, 0.0
            elif pt_int == 2:       # Schnee
                rain_acc, snow_acc = 0.0, rr
            elif pt_int == 3:       # Schneeregen
                rain_acc, snow_acc = rr * 0.5, rr * 0.5
            else:                   # 1=Regen und unbekannte Typen
                rain_acc, snow_acc = rr, 0.0

            # Windvektor aus Betrag (ff) und Richtung (dd) rekonstruieren
            ff = entry.get("ff") or 0.0
            dd_rad = math.radians(entry.get("dd") or 0.0)
            u10m = -ff * math.sin(dd_rad)
            v10m = -ff * math.cos(dd_rad)

            normalized.append({
                "datetime": entry.get("datetime"),
                "t2m": entry.get("t2m"),
                "rh2m": entry.get("rh2m"),
                "rain_acc": rain_acc,
                "snow_acc": snow_acc,
                "u10m": u10m,
                "v10m": v10m,
                "wind_gust_speed": entry.get("fx"),  # Nowcast liefert fx (skalare Böengeschwindigkeit)
                "tcc": None,  # Nowcast liefert keine Wolkenbedeckung
            })
        return normalized

    @staticmethod
    def _extract_missing_params(detail: str) -> set[str]:
        """Extrahiert Parameternamen aus einer API-400-Fehlermeldung.

        Die GeoSphere-API liefert ihre Detail-Strings in der Form
        ``... not found in resource: {param_a, param_b}``. Ändert sich
        dieses Format, kann der Parameter-Removal-Retry nicht mehr greifen
        — daher wird in dem Fall eine Warnung geloggt.
        """
        match = re.search(r"\{([^}]+)\}", detail)
        if not match:
            # Wenn der Detail-String gegen Parameter sprechen sollte, aber
            # kein Match liefert, ist das ein Hinweis auf eine API-Änderung.
            if detail and "parameter" in detail.lower():
                _LOGGER.warning(
                    "GeoSphere-400-Detail enthält kein Parameter-Set in {…}-Notation "
                    "— Parameter-Removal-Retry kann nicht greifen. Detail: %s",
                    detail,
                )
            return set()
        return {p.strip().strip("'\"") for p in match.group(1).split(",")}

    def _parse_station_geojson(self, data: dict[str, Any], station_id: str) -> dict[str, Any]:
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
            if not values:
                # Station liefert den Parameter-Slot, aber ohne Messwerte (z.B.
                # TB1 an Stationen ohne Bodensonde). Key NICHT setzen, damit der
                # Sensor `unavailable` zeigt statt `unknown`. Wenn dagegen
                # values[-1] = None ist (kurzzeitiger Datenausfall), wird der
                # Key gesetzt und der Sensor zeigt `unknown` — gewolltes Verhalten.
                continue
            result[param_name] = values[-1]

        # Koordinaten für spätere Verwendung (mit Bounds-Validierung)
        coords = feature.get("geometry", {}).get("coordinates", [])
        if len(coords) >= 2:
            lon_val, lat_val = coords[0], coords[1]
            if (
                isinstance(lon_val, (int, float))
                and isinstance(lat_val, (int, float))
                and -180.0 <= lon_val <= 180.0
                and -90.0 <= lat_val <= 90.0
            ):
                result["_lon"] = lon_val
                result["_lat"] = lat_val
            else:
                _LOGGER.warning(
                    "Ungültige Koordinaten für Station %s: lon=%s, lat=%s",
                    station_id,
                    lon_val,
                    lat_val,
                )
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
            params = NOWCAST_PARAMS

        for _attempt in range(2):
            url = (
                f"{API_BASE}/timeseries/forecast/{model}"
                f"?parameters={params}&lat_lon={lat},{lon}&output_format=geojson"
            )
            try:
                async with self._session.get(url, timeout=TIMEOUT) as resp:
                    if resp.status == 400:
                        body = await resp.json(content_type=None)
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
                    data = await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise GeoSphereApiError(f"Fehler beim Abrufen der Vorhersage: {err}") from err
            result = self._parse_forecast_geojson(data)
            if "ensemble" in model:
                return self._normalize_v2_params(result, ENSEMBLE_PARAM_MAP)
            if "nwp" in model:
                return self._normalize_v2_params(result, NWP_PARAM_MAP)
            # Nowcast liefert rr bereits als Intervallrate → keine De-Akkumulation nötig
            return self._normalize_nowcast_params(result)

        raise GeoSphereApiError("Fehler beim Abrufen der Vorhersage")

    def _parse_forecast_geojson(self, data: dict[str, Any]) -> list[dict[str, Any]]:
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
        param_data: dict[str, list[Any]] = {
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

    # ------------------------------------------------------------------
    # Wetterwarnungen
    # ------------------------------------------------------------------

    async def get_warnings(
        self,
        lat: float,
        lon: float,
        lang: str = "de",
    ) -> list[dict[str, Any]]:
        """
        Aktive Wetterwarnungen für einen Koordinatenpunkt abrufen.
        Gibt eine Liste normalisierter Warnungs-Dicts zurück.
        """
        url = (
            f"{WARNINGS_API_BASE}/getWarningsForCoords"
            f"?lon={lon}&lat={lat}&lang={lang}"
        )
        try:
            async with self._session.get(url, timeout=TIMEOUT) as resp:
                resp.raise_for_status()
                # content_type=None: API liefert teils abweichende MIME-Types
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GeoSphereApiError(f"Fehler beim Abrufen der Warnungen: {err}") from err

        raw_warnings = data.get("properties", {}).get("warnings", [])
        result: list[dict[str, Any]] = []
        for w in raw_warnings:
            raw = w.get("rawinfo", {})
            begin_ts = raw.get("start")
            end_ts = raw.get("end")
            result.append({
                "id": w.get("warnid"),
                "type_id": w.get("warntypid"),
                "level": w.get("warnstufeid", 0),
                "begin": int(begin_ts) if begin_ts is not None else None,
                "end": int(end_ts) if end_ts is not None else None,
                "text": w.get("text", ""),
                "effects": w.get("auswirkungen", ""),
                "recommendations": w.get("empfehlungen", ""),
            })
        return result

    # ------------------------------------------------------------------
    # Schadstoffvorhersage (chem-v2-1h-3km)
    # ------------------------------------------------------------------

    async def get_air_quality(
        self,
        lat: float,
        lon: float,
    ) -> dict[str, Any]:
        """
        Stündliche Schadstoffvorhersage für einen Koordinatenpunkt abrufen.
        Gibt ein Dict zurück: {'timestamps': [...], 'no2surf': [...], 'o3surf': [...], ...}
        """
        url = (
            f"{API_BASE}/timeseries/forecast/{CHEM_RESOURCE}"
            f"?parameters={CHEM_PARAMS}&lat_lon={lat},{lon}"
        )
        try:
            async with self._session.get(url, timeout=TIMEOUT) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GeoSphereApiError(
                f"Fehler beim Abrufen der Schadstoffvorhersage: {err}"
            ) from err

        timestamps: list[str] = data.get("timestamps", [])
        features = data.get("features", [])
        if not features:
            return {"timestamps": timestamps}

        props = features[0].get("properties", {}).get("parameters", {})
        result: dict[str, Any] = {"timestamps": timestamps}
        for param, info in props.items():
            result[param] = info.get("data", [])
        return result


