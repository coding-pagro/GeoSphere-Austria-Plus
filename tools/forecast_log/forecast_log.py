#!/usr/bin/env python3
"""Loggt GeoSphere-Prognosen (Nowcast, NWP) und TAWES-Messungen fuer einen spaeteren Vergleich.

Gedacht fuer einen stuendlichen Lauf (siehe README.md). Jeder Lauf schreibt EINE Datei
``<data-dir>/JJJJ/MM/TT/run_HHMM.json.gz`` mit

* der aktuellen Nowcast-Prognose (Temperatur ``t2m``, Niederschlag ``rr``) fuer alle Stationen,
* der aktuellen NWP-Prognose (``2t``, ``tp``) fuer die naechsten 6 Stunden,
* den TAWES-Messungen (``TL``, ``RR``) der letzten ~2 Stunden.

Ausgewertet wird spaeter mit ``analyze.py``: Prognosen eines Laufs gegen die Messungen,
die erst NACH dem Lauf entstanden sind (faire Rueckschau, kein Nachrechnen mit bekannten Werten).

Nur Standardbibliothek. Wenige Abfragen pro Lauf (3), weil die GeoSphere-API ein Rate-Limit hat.

  python forecast_log.py init-stations --out stations.json [--n 25]
  python forecast_log.py collect --data-dir data [--stations stations.json]
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://dataset.api.hub.geosphere.at/v1"
HERE = Path(__file__).resolve().parent

# Modell -> (Ressource, Parameter: Temperatur, Niederschlag)
NOWCAST = ("nowcast-v1-15min-1km", ("t2m", "rr"))
NWP = ("nwp-v2-1h-1km", ("2t", "tp"))
NWP_STEPS = 7           # aktuelle Stunde + 6 Stunden
OBS_PARAMS = "TL,RR"
OBS_WINDOW_MIN = 130    # ueberlappt mit dem Vorlauf, damit ein verpasster Lauf keine Luecke hinterlaesst
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


def fetch_forecast(model: str, params: tuple[str, ...], stations: list[dict], keep: int | None) -> dict:
    """Mehrpunkt-Abfrage: ein Request fuer alle Stationen. Reihenfolge der Antwort = Reihenfolge der Punkte."""
    query = [("parameters", ",".join(params)), ("output_format", "geojson")]
    query += [("lat_lon", f"{s['lat']},{s['lon']}") for s in stations]
    data = fetch(f"{BASE}/timeseries/forecast/{model}?{urllib.parse.urlencode(query)}")
    features = data["features"]
    if len(features) != len(stations):
        raise ValueError(f"{model}: {len(features)} Features fuer {len(stations)} Stationen")
    times = data["timestamps"][:keep]
    values = {}
    for station, feature in zip(stations, features):
        got = feature["properties"]["parameters"]
        values[station["id"]] = {p: got[p]["data"][:keep] for p in params if p in got}
    return {"model": model, "ref": data.get("reference_time"), "times": times, "values": values}


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
    values = {}
    for feature in data["features"]:
        sid = str(feature["properties"]["station"])
        values[sid] = {p: v["data"] for p, v in feature["properties"]["parameters"].items()}
    return {"times": data["timestamps"], "values": values}


def collect(data_dir: Path, stations_file: Path) -> int:
    stations = json.loads(stations_file.read_text("utf-8"))
    now = datetime.now(timezone.utc)
    run: dict = {
        "version": 1,
        "fetched_at": now.isoformat(timespec="seconds"),
        "nowcast": None, "nwp": None, "obs": None, "errors": [],
    }
    for key, (model, params), keep in (("nowcast", NOWCAST, None), ("nwp", NWP, NWP_STEPS)):
        try:
            run[key] = fetch_forecast(model, params, stations, keep)
        except Exception as err:  # noqa: BLE001 - ein Teilausfall soll den Lauf nicht abbrechen
            run["errors"].append(f"{key}: {err!r}")
            print(f"::warning::{key} fehlgeschlagen: {err!r}")
        time.sleep(1)
    end = now.replace(minute=now.minute - now.minute % 10, second=0, microsecond=0)
    try:
        run["obs"] = fetch_obs(stations, end)
    except Exception as err:  # noqa: BLE001
        run["errors"].append(f"obs: {err!r}")
        print(f"::warning::obs fehlgeschlagen: {err!r}")

    path = data_dir / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}" / f"run_{now:%H%M}.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(run, fh, separators=(",", ":"))
    # Stationsliste mitspeichern, damit der Datenbestand allein auswertbar ist
    copy = data_dir / "stations.json"
    if not copy.exists() or copy.read_text("utf-8") != stations_file.read_text("utf-8"):
        copy.write_text(stations_file.read_text("utf-8"), "utf-8")

    ok = [k for k in ("nowcast", "nwp", "obs") if run[k]]
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
