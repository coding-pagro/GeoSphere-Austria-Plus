#!/usr/bin/env python3
"""Loggt GeoSphere-Prognosen, INCA-Analysen und TAWES-Messungen.

Jeder Lauf schreibt eine Datei
``<data-dir>/JJJJ/MM/TT/run_HHMM.json.gz`` mit

* der aktuellen Nowcast-Prognose (Temperatur ``t2m``, Niederschlag ``rr``) fuer alle Stationen,
* der aktuellen NWP-Prognose (``2t``, ``tp``) fuer die naechsten 6 Stunden,
* den aktuellen Vergleichswerten aus NWP-Fallback, Nowcast und INCA v2,
* den TAWES-Messungen (``TL``, ``RR``) der letzten ~2 Stunden.

Ausgewertet wird mit ``analyze.py``. Der Schalter ``--inca`` vergleicht aktuelle Werte.

Nur Standardbibliothek.

  python forecast_log.py init-stations --out stations.json [--n 25]
  python forecast_log.py collect --data-dir data [--stations stations.json]
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://dataset.api.hub.geosphere.at/v1"
HERE = Path(__file__).resolve().parent

# Modell -> (Ressource, Parameter: Temperatur, Niederschlag)
NOWCAST = ("nowcast-v1-15min-1km", ("t2m", "rr"))
NWP = ("nwp-v2-1h-1km", ("2t", "tp", "rain", "sf"))
INCA = ("inca-v2-1h-1km", ("2t", "tp"))
INCA_MAX_AGE = timedelta(hours=2)  # wie im Entwurf #69
HOUR = timedelta(hours=1)
NOWCAST_STEP = timedelta(minutes=15)
NWP_STEPS = 7           # aktuelle Stunde + 6 Stunden
OBS_PARAMS = "TL,RR"
# 12 h: GitHub laesst geplante Laeufe oft ausfallen (gemessen: 3-5 pro Tag statt 24). Das Fenster
# muss die Luecke bis zum vorherigen Lauf abdecken, sonst finden dessen Prognosen keine Messung.
OBS_WINDOW_MIN = 720
ALWAYS_INCLUDE = "11389"  # ST.POELTEN LANDHAUS, Station des Users
USER_AGENT = "geosphere-forecast-log/1.0"


def fetch(url: str, tries: int = 4) -> dict:
    """GET mit Wiederholung bei Rate-Limit (429) und Serverfehlern."""
    delay = 15
    for attempt in range(tries):
        last = attempt == tries - 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code not in (429, 500, 502, 503, 504) or last:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if last:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


def fetch_points(
    endpoint: str, params: tuple[str, ...], stations: list[dict], *,
    tries: int = 4, **filters: str,
) -> dict:
    """Mehrpunkt-Abfrage: ein Request fuer alle Stationen. Reihenfolge der Antwort = Reihenfolge der Punkte."""
    query = [("parameters", ",".join(params)), ("output_format", "geojson")]
    query += [("lat_lon", f"{s['lat']},{s['lon']}") for s in stations]
    query.extend(filters.items())
    data = fetch(f"{BASE}/timeseries/{endpoint}?{urllib.parse.urlencode(query)}", tries=tries)
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    features = data["features"]
    if len(features) != len(stations):
        raise ValueError(f"{endpoint}: {len(features)} Features fuer {len(stations)} Stationen")
    values, grid_gaps = {}, []
    for station, feature in zip(stations, features):
        if "geometry" in feature and feature["geometry"] is None:
            grid_gaps.append(station["id"])
            continue
        got = feature["properties"]["parameters"]
        values[station["id"]] = {p: got[p]["data"] for p in params if p in got}
    return {
        "ref": data.get("reference_time"), "times": data["timestamps"],
        "values": values, "retrieved_at": retrieved_at, "grid_gaps": grid_gaps,
    }


def fetch_forecast(
    model: str, params: tuple[str, ...], stations: list[dict], *, tries: int = 4, **filters: str,
) -> dict:
    return {"model": model, **fetch_points(f"forecast/{model}", params, stations, tries=tries, **filters)}


def trim_forecast(result: dict, keep: int, since: datetime | None = None) -> dict:
    """Ab der Stunde ``since`` die nächsten ``keep`` Zeitschritte behalten."""
    first = 0
    if since is not None:
        first = next(
            (i for i, t in enumerate(result["times"]) if datetime.fromisoformat(t) >= since),
            len(result["times"]),
        )
    window = slice(first, first + keep)
    return {
        **result, "times": result["times"][window],
        "values": {
            sid: {p: series[window] for p, series in values.items()}
            for sid, values in result["values"].items()
        },
    }


def finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def candidates(source: str, sid: str, fetched: datetime, data: dict | None, status="missing") -> dict:
    """Wählt einen Zeitschritt pro Quelle, auch wenn einzelne Felder fehlen."""
    if data and sid in data.get("grid_gaps", []):
        status = "grid_gap"
    result = {
        "source": source, "retrieved_at": data.get("retrieved_at") if data else None,
        "temperature": {"status": status}, "precipitation": {"status": status},
    }
    if data is None or status == "grid_gap":
        return result

    is_inca = source == INCA[0]
    is_nowcast = source == NOWCAST[0]
    if not is_inca:
        result["reference_time"] = data.get("ref")
    times = []
    for index, raw_time in enumerate(data["times"]):
        try:
            timestamp = datetime.fromisoformat(raw_time)
        except (TypeError, ValueError):
            continue
        if timestamp.tzinfo is not None:
            times.append((timestamp, index))
    if is_inca:
        selected = max(
            ((t, i) for t, i in times if fetched - INCA_MAX_AGE <= t <= fetched),
            default=None,
        )
    else:
        # GeoSphereWeatherEntity._first_forecast_entry nimmt den ersten
        # Zeitstempel in API-Reihenfolge, maximal eine Stunde in der Vergangenheit.
        selected = next(((t, i) for t, i in times if t >= fetched - HOUR), None)
    if selected is None:
        return result
    valid_at, index = selected
    series = data["values"].get(sid, {})

    def value(param: str):
        points = series.get(param, [])
        raw = points[index] if index < len(points) else None
        return raw if finite(raw) else None

    temperature = value("t2m" if is_nowcast else "2t")
    interval = NOWCAST_STEP if is_nowcast else HOUR
    if is_inca:
        amount = value("tp")
        entity_amount = amount
    elif is_nowcast:
        # Plus zeigt die 15-Minuten-Summe rr des ersten Schritts, bei Trockenheit leer.
        amount = value("rr")
        entity_amount = amount or None
    else:
        rain, snow = value("rain"), value("sf")
        # Plus liefert None bei Trockenheit und behandelt einzelne fehlende
        # Komponenten als 0. Für den Mengenvergleich braucht es beide Werte.
        components = rain or 0.0, snow or 0.0
        entity_amount = sum(components) if any(components) else None
        amount = rain + snow if rain is not None and snow is not None else None
    result["temperature"] = {
        "status": "ok" if temperature is not None else "missing",
        "valid_at": valid_at.isoformat(), "value": temperature,
    }
    result["precipitation"] = {
        "status": "ok" if amount is not None else "missing",
        "valid_at": valid_at.isoformat(), "value": amount, "entity_value": entity_amount,
        "interval_start": (valid_at - interval).isoformat(), "interval_end": valid_at.isoformat(),
    }
    return result


def forecast_for_interval(sid: str, data: dict | None, inca: dict) -> dict:
    """NWP-Niederschlag für das Stundenintervall des INCA-Kandidaten.

    Der angezeigte Fallback gilt für die laufende Stunde, die jüngste INCA-Analyse
    ist dagegen über eine Stunde alt. Für den Mengenvergleich braucht es deshalb
    den NWP-Wert desselben Intervalls aus demselben Abruf.
    """
    if data is None:
        return {"status": "fetch_error"}
    if sid in data.get("grid_gaps", []):
        return {"status": "grid_gap"}
    end = inca.get("interval_end")
    if end is None:
        return {"status": "missing"}
    result = {"status": "missing", "interval_start": inca["interval_start"], "interval_end": end}
    target = datetime.fromisoformat(end)
    for index, raw_time in enumerate(data["times"]):
        try:
            if datetime.fromisoformat(raw_time) == target:
                break
        except (TypeError, ValueError):
            continue
    else:
        return result
    series = data["values"].get(sid, {})
    amounts = []
    for param in ("rain", "sf"):
        points = series.get(param, [])
        raw = points[index] if index < len(points) else None
        if not finite(raw):
            return result
        amounts.append(raw)
    result.update(status="ok", value=sum(amounts))
    return result


def fetch_inca(stations: list[dict], started: datetime, errors: list[str]) -> dict:
    """Eine Mehrpunktabfrage; bei Rastergrenzen fehlerhafte Punkte isolieren."""
    resource, params = INCA
    try:
        data = fetch_points(
            f"historical/{resource}", params, stations, tries=1,
            start=(started - INCA_MAX_AGE).isoformat(timespec="minutes"),
            end=started.isoformat(timespec="minutes"),
        )
    except urllib.error.HTTPError as err:
        if err.code == 400 and b"outside of dataset bounds" in err.read():
            if len(stations) == 1:
                return {stations[0]["id"]: (None, "grid_gap")}
            mid = len(stations) // 2
            return fetch_inca(stations[:mid], started, errors) | fetch_inca(stations[mid:], started, errors)
        errors.append(f"inca: {err!r}")
    except Exception as err:  # Teilausfälle protokollieren
        errors.append(f"inca: {err!r}")
    else:
        return {station["id"]: (data, "missing") for station in stations}
    return {station["id"]: (None, "fetch_error") for station in stations}


def fetch_obs(stations: list[dict], end: datetime) -> dict:
    """TAWES-Messungen (10 min) der letzten OBS_WINDOW_MIN Minuten, alle Stationen in einem Request."""
    start = end - timedelta(minutes=OBS_WINDOW_MIN)
    query = urllib.parse.urlencode({
        "parameters": OBS_PARAMS,
        "station_ids": ",".join(s["id"] for s in stations),
        "start": start.strftime("%Y-%m-%dT%H:%M"),
        "end": end.strftime("%Y-%m-%dT%H:%M"),
        "output_format": "geojson",
    })
    data = fetch(f"{BASE}/station/historical/tawes-v1-10min?{query}")
    values, locations = {}, {}
    for feature in data["features"]:
        sid = str(feature["properties"]["station"])
        values[sid] = {p: v["data"] for p, v in feature["properties"]["parameters"].items()}
        geometry = feature.get("geometry")
        if geometry:
            lon, lat = geometry["coordinates"][:2]
            locations[sid] = [lat, lon]
    return {"times": data["timestamps"], "values": values, "locations": locations}


def collect(data_dir: Path, stations_file: Path) -> int:
    stations = json.loads(stations_file.read_text("utf-8"))
    now = datetime.now(timezone.utc)
    run: dict = {
        "version": 2,
        "fetched_at": now.isoformat(timespec="seconds"),
        "stations": stations,
        "nowcast": None, "nwp": None, "obs": None, "errors": [],
    }
    # Alle drei Requests gehören zum selben Abruf. Ein späterer Retry könnte
    # bereits einen anderen Forecast-Lauf oder eine neue Analyse liefern.
    inca_errors: list[str] = []
    # Ohne "start" beginnt die NWP-Antwort mit der laufenden Stunde. Das INCA-Intervall
    # liegt aber bis zu zwei Stunden zurück, daher die Zeitreihe früher beginnen lassen.
    # Der Fallback-Kandidat (erster Schritt ab "jetzt - 1 h") bleibt dabei derselbe.
    hour = now.replace(minute=0, second=0, microsecond=0)
    nwp_start = {"start": (hour - INCA_MAX_AGE).isoformat(timespec="minutes")}
    with ThreadPoolExecutor(max_workers=3) as pool:
        inca_task = pool.submit(fetch_inca, stations, now, inca_errors)
        nowcast_task = pool.submit(fetch_forecast, *NOWCAST, stations, tries=1)
        try:
            nwp = fetch_forecast(*NWP, stations, tries=1, **nwp_start)
        except Exception as err:  # Teilausfälle protokollieren
            nwp = None
            run["errors"].append(f"nwp: {err!r}")
        try:
            nowcast = nowcast_task.result()
        except Exception as err:
            nowcast = None
            run["errors"].append(f"nowcast: {err!r}")
        inca = inca_task.result()
    sampled = datetime.now(timezone.utc)
    run["errors"].extend(inca_errors)
    inca_candidates = {
        sid: candidates(INCA[0], sid, sampled, data, status)
        for sid, (data, status) in inca.items()
    }
    forecast_candidates = {}
    for sid, inca_candidate in inca_candidates.items():
        forecast_candidates[sid] = candidates(
            NWP[0], sid, sampled, nwp, "fetch_error" if nwp is None else "missing",
        )
        forecast_candidates[sid]["precipitation_inca_interval"] = forecast_for_interval(
            sid, nwp, inca_candidate["precipitation"],
        )
    run["comparison"] = {
        "sampled_at": sampled.isoformat(timespec="milliseconds"),
        "forecast": forecast_candidates,
        "inca": inca_candidates,
        "nowcast": {
            sid: candidates(
                NOWCAST[0], sid, sampled, nowcast, "fetch_error" if nowcast is None else "missing",
            )
            for sid in inca_candidates
        },
    }
    if nwp is None:
        # Die Vorhersage-Zeitreihe darf nachgeladen werden. Der Kandidat für
        # den INCA-Vergleich bleibt der bereits protokollierte Abruffehler.
        try:
            nwp = fetch_forecast(*NWP, stations, **nwp_start)
        except Exception as err:
            run["errors"].append(f"nwp (Vorhersagearchiv): {err!r}")
    if nwp:
        # Vorhersageauswertung wie bisher: laufende Stunde + 6 h.
        run["nwp"] = trim_forecast(nwp, NWP_STEPS, since=hour)
    if nowcast is None:
        try:
            nowcast = fetch_forecast(*NOWCAST, stations)
        except Exception as err:
            run["errors"].append(f"nowcast (Vorhersagearchiv): {err!r}")
    run["nowcast"] = nowcast
    time.sleep(1)
    end = now.replace(minute=now.minute - now.minute % 10, second=0, microsecond=0)
    try:
        run["obs"] = fetch_obs(stations, end)
    except Exception as err:  # noqa: BLE001
        run["errors"].append(f"obs: {err!r}")
    for error in run["errors"]:
        print(f"::warning::{error}")

    path = data_dir / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}" / f"run_{now:%H%M}.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(run, fh, separators=(",", ":"))
    # Stationsliste mitspeichern, damit der Datenbestand allein auswertbar ist
    copy = data_dir / "stations.json"
    if not copy.exists() or copy.read_text("utf-8") != stations_file.read_text("utf-8"):
        copy.write_text(stations_file.read_text("utf-8"), "utf-8")

    ok = [k for k in ("nowcast", "nwp", "obs") if run[k]]
    if any(result["retrieved_at"] for result in run["comparison"]["inca"].values()):
        ok.append("inca")
    print(f"{path}  ok={ok}  fehler={len(run['errors'])}  {path.stat().st_size / 1024:.1f} KiB")
    return 0 if ok else 1


def init_stations(out: Path, n: int) -> int:
    """n aktive Stationen gleichmaessig ueber die Hoehe verteilt (Flachland bis Gipfel) + Pflichtstation."""
    meta = fetch(f"{BASE}/station/current/tawes-v1-10min/metadata")
    active = [s for s in meta["stations"] if s.get("is_active") and s.get("lat") and s.get("lon")]
    active.sort(key=lambda s: (s.get("altitude") or 0, str(s["id"])))
    picked = {str(active[round(i * (len(active) - 1) / (n - 1))]["id"]) for i in range(n)}
    if ALWAYS_INCLUDE not in picked:
        by_id = {str(s["id"]): s for s in active}
        alt = by_id[ALWAYS_INCLUDE].get("altitude") or 0
        nearest = min(picked, key=lambda i: abs((by_id[i].get("altitude") or 0) - alt))
        picked.discard(nearest)
        picked.add(ALWAYS_INCLUDE)
    chosen = [
        {"id": str(s["id"]), "name": s["name"], "lat": s["lat"], "lon": s["lon"],
         "alt": s.get("altitude") or 0}
        for s in active if str(s["id"]) in picked
    ]
    chosen.sort(key=lambda s: s["alt"])
    out.write_text(json.dumps(chosen, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"{len(chosen)} Stationen -> {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init-stations", help="Stationsliste erzeugen")
    p_init.add_argument("--out", type=Path, default=HERE / "stations.json")
    p_init.add_argument("--n", type=int, default=25)
    p_col = sub.add_parser("collect", help="Prognosen und Messungen eines Laufs speichern")
    p_col.add_argument("--data-dir", type=Path, required=True)
    p_col.add_argument("--stations", type=Path, default=HERE / "stations.json")
    args = parser.parse_args()
    if args.cmd == "init-stations":
        return init_stations(args.out, args.n)
    return collect(args.data_dir, args.stations)


if __name__ == "__main__":
    sys.exit(main())
