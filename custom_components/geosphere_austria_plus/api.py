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
    def _normalize_nowcast_params(entries: list[dict]) -> list[dict]:
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
    def _deaccumulate_grad(entries: list[dict]) -> None:
        """NWP-Globalstrahlung von akkumulierten Ws/m² in mittlere W/m² je Zeitschritt umrechnen.

        NWP liefert grad als Energiesumme seit Modellstart (Ws/m²). Für stündliche Schritte
        ergibt Delta/3600 die mittlere Bestrahlungsstärke (W/m²) des jeweiligen Zeitschritts.
        Negative Deltas (Modell-Reset) werden als 0 behandelt. Ändert die Einträge in-place.
        """
        prev: float | None = None
        for entry in entries:
            raw = entry.get("grad")
            if raw is None:
                prev = None
                continue
            if prev is None:
                entry["grad"] = round(raw / 3600.0, 2)
            else:
                entry["grad"] = round(max(0.0, raw - prev) / 3600.0, 2)
            prev = raw

    @staticmethod
    def _deaccumulate_precip(entries: list[dict]) -> None:
        """NWP/Ensemble-Niederschlag von akkumulierten mm in mm je Zeitschritt umrechnen.

        Die API liefert rain_acc/snow_acc als Summe seit Modellstart (mm).
        Das Delta aufeinanderfolgender Zeitschritte ergibt den Intervallniederschlag.
        Negative Deltas (Modell-Reset) werden als 0 behandelt. Ändert die Einträge in-place.
        Der erste Eintrag enthält die Akkumulation ab Modellstart und wird direkt übernommen.
        """
        prev_rain: float | None = None
        prev_snow: float | None = None
        for entry in entries:
            raw_rain = entry.get("rain_acc")
            if raw_rain is not None:
                entry["rain_acc"] = round(max(0.0, raw_rain if prev_rain is None else raw_rain - prev_rain), 2)
                prev_rain = raw_rain
            else:
                prev_rain = None

            raw_snow = entry.get("snow_acc")
            if raw_snow is not None:
                entry["snow_acc"] = round(max(0.0, raw_snow if prev_snow is None else raw_snow - prev_snow), 2)
                prev_snow = raw_snow
            else:
                prev_snow = None

    @staticmethod
    def _extract_missing_params(detail: str) -> set[str]:
        """Extrahiert Parameternamen aus einer API-400-Fehlermeldung."""
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
                result = self._normalize_ensemble_params(result)
                # rain_p50/snow_p50 sind Periodensummen (mm/Periode, 1h Fenster),
                # keine Akkumulationen seit Modellstart → direkt übernehmen, kein _deaccumulate_precip.
            elif "nowcast" in model:
                # Nowcast liefert rr bereits als Intervallrate → keine De-Akkumulation nötig
                result = self._normalize_nowcast_params(result)
            else:
                # NWP: grad und rain_acc/snow_acc sind akkumuliert seit Modellstart
                self._deaccumulate_grad(result)
                self._deaccumulate_precip(result)
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


