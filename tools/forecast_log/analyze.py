#!/usr/bin/env python3
"""Wertet die von forecast_log.py gesammelten Laeufe aus (Nowcast vs. NWP vs. Messung).

  python analyze.py --data-dir data [--stations data/stations.json]

Temperatur: Fehler = Prognose - Messung (Grad C), je Modell, Vorlauf und Hoehenklasse
  roh        Modellwert unveraendert
  angegl.    letzte Stationsmessung + Modelltrend (Modell(t) - Modell(Zeit der Messung))
  Persist.   letzte Stationsmessung unveraendert ("bleibt wie jetzt")
Niederschlag: Stundensummen (mm/h). Prognose (Nowcast: 4 x 15 min, NWP: tp) gegen TAWES RR (6 x 10 min),
  Ereignis = mindestens PRECIP_THRESHOLD mm/h. POD = Trefferquote, FAR = Fehlalarmquote,
  CSI = Treffer / (Treffer + verpasst + Fehlalarm).

Nur Prognosen, die VOR den verglichenen Messungen erzeugt wurden (Vorlauf > 0).
Annahme: TAWES-Zeitstempel kennzeichnen das Ende des 10-Minuten-Intervalls, Prognose-Niederschlag
gilt fuer das Intervall, das am Zeitstempel endet.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Modell -> (Temperatur-Parameter, Niederschlags-Parameter)
MODELS = {"nowcast": ("t2m", "rr"), "nwp": ("2t", "tp")}
LEAD_BUCKETS = [(0, 30), (30, 60), (60, 120), (120, 180), (180, 360)]  # Minuten
PRECIP_THRESHOLD = 0.1  # mm/h
LOW, HIGH = "Flachland (<600 m)", "Berg (>=600 m)"
USER_STATION = "11389"


def parse_t(text: str) -> datetime:
    t = datetime.fromisoformat(text)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def load(data_dir: Path):
    runs = []
    obs: dict = defaultdict(lambda: defaultdict(dict))  # sid -> Parameter -> {Zeit: Wert}
    for path in sorted(data_dir.rglob("run_*.json.gz")):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                run = json.load(fh)
        except (OSError, ValueError) as err:
            print(f"WARNUNG: {path} nicht lesbar: {err}", file=sys.stderr)
            continue
        run["_fetched"] = parse_t(run["fetched_at"])
        for key in MODELS:
            if run.get(key):
                run[key]["_times"] = [parse_t(t) for t in run[key]["times"]]
        if run.get("obs"):
            times = [parse_t(t) for t in run["obs"]["times"]]
            for sid, params in run["obs"]["values"].items():
                for param, values in params.items():
                    for t, v in zip(times, values):
                        if v is not None:
                            obs[sid][param][t] = v
        runs.append(run)
    return runs, obs


def interp(times, values, t, extrapolate=timedelta(minutes=20)):
    """Linear zwischen Stuetzstellen; vor dem ersten Schritt nur bis 'extrapolate' Abstand
    (der Trend der ersten beiden Schritte wird rueckwaerts fortgesetzt, sonst waere der Nowcast
    mit seinem ersten Schritt erst 15 min nach dem Lauf im Nachteil)."""
    if not times:
        return None
    if t < times[0]:
        if times[0] - t > extrapolate or values[0] is None:
            return None
        if len(times) > 1 and values[1] is not None:
            slope = (values[1] - values[0]) / (times[1] - times[0]).total_seconds()
            return values[0] - slope * (times[0] - t).total_seconds()
        return values[0]
    for i in range(1, len(times)):
        if t <= times[i]:
            a, b = values[i - 1], values[i]
            if a is None or b is None:
                return None
            span = (times[i] - times[i - 1]).total_seconds()
            return a + (b - a) * (t - times[i - 1]).total_seconds() / span
    return None


def obs_at(series, t):
    """Messung zum Zeitpunkt t (exakt oder linear zwischen den 10-Minuten-Werten)."""
    if t in series:
        return series[t]
    low = t - timedelta(minutes=t.minute % 10, seconds=t.second, microseconds=t.microsecond)
    a, b = series.get(low), series.get(low + timedelta(minutes=10))
    if a is None or b is None:
        return None
    return a + (b - a) * (t - low).total_seconds() / 600


def last_obs(series, fetched, max_age_min=30):
    """Letzte Messung bis zum Abrufzeitpunkt: (Zeit, Wert) oder None."""
    t = fetched.replace(second=0, microsecond=0)
    t -= timedelta(minutes=t.minute % 10)
    for k in range(max_age_min // 10 + 1):
        tk = t - timedelta(minutes=10 * k)
        if tk in series:
            return tk, series[tk]
    return None


def bucket_of(lead_min):
    for lo, hi in LEAD_BUCKETS:
        if lo < lead_min <= hi:
            return lo, hi
    return None


def classes(station):
    out = ["alle", LOW if station["alt"] < 600 else HIGH]
    if station["id"] == USER_STATION:
        out.append(f"Station {USER_STATION} (St. Poelten)")
    return out


def rmse(errors):
    return math.sqrt(sum(e * e for e in errors) / len(errors))


def bias(errors):
    return sum(errors) / len(errors)


def eval_temperature(runs, obs, stations):
    groups = defaultdict(lambda: {"raw": [], "anch": [], "pers": []})
    for run in runs:
        fetched = run["_fetched"]
        for key, (tparam, _) in MODELS.items():
            fc = run.get(key)
            if not fc:
                continue
            for st in stations:
                values = fc["values"].get(st["id"], {}).get(tparam)
                series = obs.get(st["id"], {}).get("TL")
                if not values or not series:
                    continue
                last = last_obs(series, fetched)
                base = interp(fc["_times"], values, last[0]) if last else None
                if last is None or base is None:
                    continue
                for t, v in zip(fc["_times"], values):
                    if v is None or t <= fetched:
                        continue
                    truth = obs_at(series, t)
                    bucket = bucket_of((t - fetched).total_seconds() / 60)
                    if truth is None or bucket is None:
                        continue
                    for cls in classes(st):
                        g = groups[(cls, key, bucket)]
                        g["raw"].append(v - truth)
                        g["anch"].append(last[1] + (v - base) - truth)
                        g["pers"].append(last[1] - truth)
    print("\n=== Temperatur (Prognose - Messung, Grad C) ===")
    for cls in ["alle", LOW, HIGH, f"Station {USER_STATION} (St. Poelten)"]:
        keys = sorted(k for k in groups if k[0] == cls)
        if not keys:
            continue
        print(f"\n-- {cls} --")
        print("Modell   Vorlauf (min)      n |  roh: RMSE  Bias | angegl.: RMSE  Bias | Persist.: RMSE")
        for _, key, (lo, hi) in keys:
            g = groups[(cls, key, (lo, hi))]
            print(
                f"{key:8s} {lo:3d}-{hi:<3d}        {len(g['raw']):5d} |"
                f"  {rmse(g['raw']):9.2f} {bias(g['raw']):+5.2f} |"
                f"  {rmse(g['anch']):10.2f} {bias(g['anch']):+5.2f} |"
                f"  {rmse(g['pers']):12.2f}"
            )


def eval_precip(runs, obs, stations):
    rows = defaultdict(list)  # (Modell, Bucket) -> [(Prognose, Messung)]
    hour = timedelta(hours=1)
    for run in runs:
        fetched = run["_fetched"]
        for key, (_, pparam) in MODELS.items():
            fc = run.get(key)
            if not fc:
                continue
            for st in stations:
                values = fc["values"].get(st["id"], {}).get(pparam)
                series = obs.get(st["id"], {}).get("RR")
                if not values or not series:
                    continue
                by_time = dict(zip(fc["_times"], values))
                for end in sorted(t for t in by_time if t.minute == 0):
                    if end - hour < fetched:      # Fenster muss komplett in der Zukunft liegen
                        continue
                    if key == "nwp":
                        steps = [end]
                    else:
                        steps = [end - timedelta(minutes=15 * k) for k in range(4)]
                    parts = [by_time.get(t) for t in steps]
                    stamps = [series.get(end - timedelta(minutes=10 * k)) for k in range(6)]
                    bucket = bucket_of((end - fetched).total_seconds() / 60)
                    if None in parts or None in stamps or bucket is None:
                        continue
                    rows[(key, bucket)].append((sum(parts), sum(stamps)))
    print(f"\n=== Niederschlag, Stundensummen (alle Stationen; Ereignis >= {PRECIP_THRESHOLD} mm/h) ===")
    if not rows:
        print("(noch keine passenden Daten)")
        return
    print("Modell   Vorlauf (min)      n | MAE mm/h  Bias | Ereignisse Mess. | POD   FAR   CSI")
    for (key, (lo, hi)), pairs in sorted(rows.items()):
        mae = sum(abs(f - o) for f, o in pairs) / len(pairs)
        hits = sum(1 for f, o in pairs if f >= PRECIP_THRESHOLD and o >= PRECIP_THRESHOLD)
        miss = sum(1 for f, o in pairs if f < PRECIP_THRESHOLD and o >= PRECIP_THRESHOLD)
        false = sum(1 for f, o in pairs if f >= PRECIP_THRESHOLD and o < PRECIP_THRESHOLD)

        def ratio(num, den):
            return f"{num / den:4.2f}" if den else "  - "

        print(
            f"{key:8s} {lo:3d}-{hi:<3d}        {len(pairs):5d} |"
            f" {mae:8.3f} {bias([f - o for f, o in pairs]):+6.3f} |"
            f" {hits + miss:16d} |"
            f" {ratio(hits, hits + miss)}  {ratio(false, hits + false)}  {ratio(hits, hits + miss + false)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--stations", type=Path, help="Standard: <data-dir>/stations.json")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    stations = json.loads((args.stations or args.data_dir / "stations.json").read_text("utf-8"))
    runs, obs = load(args.data_dir)
    if not runs:
        print("Keine Laeufe gefunden.")
        return 1
    complete = sum(1 for r in runs if r.get("nowcast") and r.get("nwp") and r.get("obs"))
    print(f"{len(runs)} Laeufe ({complete} vollstaendig), "
          f"{runs[0]['_fetched']:%Y-%m-%d %H:%M} bis {runs[-1]['_fetched']:%Y-%m-%d %H:%M} UTC, "
          f"{len(stations)} Stationen")
    eval_temperature(runs, obs, stations)
    eval_precip(runs, obs, stations)
    return 0


if __name__ == "__main__":
    sys.exit(main())
