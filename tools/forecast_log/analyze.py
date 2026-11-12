#!/usr/bin/env python3
"""Wertet die von forecast_log.py gesammelten Laeufe aus (Nowcast vs. NWP vs. Messung).

  python analyze.py --data-dir data [--stations data/stations.json]
  python analyze.py --data-dir data --inca

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
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    LOCAL_TZ = ZoneInfo("Europe/Vienna")
except ZoneInfoNotFoundError:  # Windows ohne tzdata
    LOCAL_TZ = timezone(timedelta(hours=1))
# Tageszeiten in Ortszeit: (Bezeichnung, erste Stunde, Stunde nach dem Ende)
DAY_PARTS = (
    ("Nacht 22–6", 22, 6), ("Morgen 6–10", 6, 10), ("Tag 10–16", 10, 16), ("Abend 16–22", 16, 22),
)

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


def point(station):
    return station["id"], station["lat"], station["lon"]


def comparison_observations(runs):
    """TAWES-Zeitreihen nach ID und den vom Messdienst gelieferten Koordinaten."""
    obs = defaultdict(lambda: defaultdict(dict))
    for run in runs:
        snapshot = run.get("obs")
        if not snapshot:
            continue
        times = [parse_t(t) for t in snapshot["times"]]
        for sid, location in snapshot.get("locations", {}).items():
            for param, values in snapshot["values"][sid].items():
                obs[(sid, *location)][param].update(
                    (t, v) for t, v in zip(times, values)
                    if type(v) in (int, float) and math.isfinite(v)
                )
    return obs


def precipitation_reference(forecast, inca, series):
    """Nur identische Stundenfenster mit allen sechs TAWES-Intervallen."""
    start, end = (parse_t(inca[k]) for k in ("interval_start", "interval_end"))
    if (
        (start, end) != (parse_t(forecast["interval_start"]), parse_t(forecast["interval_end"]))
        or end - start != timedelta(hours=1)
    ):
        return None, "different_interval"
    parts = [series.get(end - timedelta(minutes=10 * k)) for k in range(6)]
    if None in parts:
        return None, "missing_obs"
    return sum(parts), None


def compare_current(runs, field, obs):
    availability = {"forecast": Counter(), "inca": Counter()}
    excluded = Counter()
    ages = []
    groups = defaultdict(list)
    for run in runs:
        comparison = run["comparison"]
        sampled = parse_t(comparison["sampled_at"])
        for station in run["stations"]:
            sid = station["id"]
            # Verfügbarkeit bezieht sich auf den Wert, den Plus anzeigen würde.
            forecast = comparison["forecast"][sid][field]
            inca = comparison["inca"][sid][field]
            availability["forecast"][forecast["status"]] += 1
            availability["inca"][inca["status"]] += 1
            if inca["status"] == "ok":
                age = (sampled - parse_t(inca["valid_at"])).total_seconds() / 60
                ages.append(age)
            if field == "precipitation":
                # Der angezeigte Fallback gilt für die laufende Stunde, INCA für eine
                # frühere. Die Menge vergleicht daher den NWP-Wert des INCA-Intervalls.
                forecast = comparison["forecast"][sid].get("precipitation_inca_interval")
                if forecast is None:  # Aufzeichnung ohne diesen Wert
                    excluded["different_interval"] += 1
                    continue
            if forecast["status"] != "ok" or inca["status"] != "ok":
                excluded["missing_candidate"] += 1
                continue

            reference = obs.get(point(station), {})
            if field == "temperature":
                truth = obs_at(reference.get("TL", {}), sampled)
                reason = "missing_obs" if truth is None else None
            else:
                truth, reason = precipitation_reference(forecast, inca, reference.get("RR", {}))
            if reason:
                excluded[reason] += 1
                continue
            groups[int(age // 30) * 30].append((forecast["value"], inca["value"], truth))
    return availability, excluded, ages, groups


def day_part(t):
    hour = t.astimezone(LOCAL_TZ).hour
    for label, first, end in DAY_PARTS:
        if (first <= hour < end) if first < end else (hour >= first or hour < end):
            return label
    raise ValueError(hour)


def compare_nowcast_temperature(runs, obs):
    """Temperatur aus NWP-Fallback, INCA und Nowcast auf gemeinsamen Fällen.

    Zeilen: (NWP, INCA, Nowcast, Messung, Tageszeit). Aufzeichnungen ohne
    Nowcast-Kandidaten fließen nicht ein.
    """
    availability = Counter()
    ages = []
    rows = []
    for run in runs:
        comparison = run["comparison"]
        if "nowcast" not in comparison:
            continue
        sampled = parse_t(comparison["sampled_at"])
        for station in run["stations"]:
            sid = station["id"]
            nowcast = comparison["nowcast"][sid]
            candidate = nowcast["temperature"]
            availability[candidate["status"]] += 1
            if nowcast.get("reference_time"):
                ages.append((sampled - parse_t(nowcast["reference_time"])).total_seconds() / 60)
            values = [comparison[source][sid]["temperature"] for source in ("forecast", "inca")]
            values.append(candidate)
            if any(v["status"] != "ok" for v in values):
                continue
            truth = obs_at(obs.get(point(station), {}).get("TL", {}), sampled)
            if truth is not None:
                rows.append((*(v["value"] for v in values), truth, day_part(sampled)))
    return availability, ages, rows


def report_nowcast_temperature(runs, obs):
    availability, ages, rows = compare_nowcast_temperature(runs, obs)
    print("\n### Mit Nowcast\n")
    total = sum(availability.values())
    if not total:
        print("Keine Aufzeichnungen mit Nowcast-Kandidaten.")
        return
    print(f"Nowcast nutzbar in {availability['ok']}/{total} Fällen "
          f"({availability['ok'] / total:.1%}); fehlender Wert {availability['missing']}, "
          f"Rasterlücke {availability['grid_gap']}, Abruffehler {availability['fetch_error']}.")
    if ages:
        print(f"Alter des Nowcast-Laufs in Minuten (Minimum / Median / Maximum) "
              f"{min(ages):.1f} / {median(ages):.1f} / {max(ages):.1f}.")
    if not rows:
        print("\nKeine gemeinsamen Fälle aller drei Quellen mit TAWES-Messung.")
        return
    print("\nGemeinsame Fälle, in denen alle drei Quellen und eine Messung vorliegen.\n")
    print("| Tageszeit (Ortszeit) | Fälle | MAE NWP (°C) | MAE INCA (°C) | MAE Nowcast (°C) |")
    print("|---|---:|---:|---:|---:|")
    parts = [(label, [r for r in rows if r[4] == label]) for label, _, _ in DAY_PARTS]
    for label, group in [("Alle", rows), *((label, g) for label, g in parts if g)]:
        nwp, inca, nowcast = (mean(abs(r[i] - r[3]) for r in group) for i in range(3))
        print(f"| {label} | {len(group)} | {nwp:.3f} | {inca:.3f} | {nowcast:.3f} |")
    errors = {
        name: mean(abs(r[i] - r[3]) for r in rows)
        for i, name in enumerate(("NWP-Fallback", "INCA", "Nowcast"))
    }
    best = min(errors, key=errors.get)
    print(f"\nIm gemeinsamen Satz liegt {best} am nächsten an der Messung.")
    if errors["Nowcast"] <= errors["INCA"]:
        print("Nowcast ist dabei mindestens so genau wie INCA, ohne die Verzögerung der "
              "stündlichen Analyse. Für aktuelle Werte spricht das gegen INCA.")
    if len({row[4] for row in rows}) < len(DAY_PARTS):
        print("Nicht alle Tageszeiten sind erfasst. Morgen und Abend sind wegen des "
              "Tagesgangs für die Verzögerung von INCA entscheidend.")


def comparison_mae(rows, index):
    return mean(abs(row[index] - row[2]) for row in rows)


def precipitation_events(rows, index):
    events = Counter(
        (row[index] >= PRECIP_THRESHOLD, row[2] >= PRECIP_THRESHOLD) for row in rows
    )
    return events[True, True], events[False, True], events[True, False]


def report_nowcast(field, runs, obs):
    if field == "temperature":
        report_nowcast_temperature(runs, obs)
    else:
        print("\nNowcast fehlt beim Niederschlag. Er liefert 15-Minuten-Summen erst ab seinem "
              "Referenzzeitpunkt und deckt das zurückliegende INCA-Stundenintervall nicht ab.")


def report_current_comparison(runs):
    obs = comparison_observations(runs)
    runs = [run for run in runs if run.get("comparison")]
    print("# INCA v2, NWP-Fallback und Nowcast im Vergleich")
    if not runs:
        print("\nKeine zeitgleich aufgezeichneten INCA- und Fallback-Abrufe vorhanden.")
        return

    times = sorted(parse_t(run["comparison"]["sampled_at"]) for run in runs)
    minutes = ", ".join(f"{m:02d}" for m in sorted({t.minute for t in times}))
    stations = {point(st): st for run in runs for st in run["stations"]}
    print(f"\n{len(runs)} Abrufe an {len(stations)} Standorten von {times[0]:%Y-%m-%d %H:%M} "
          f"bis {times[-1]:%Y-%m-%d %H:%M} UTC. Erfasste Minuten innerhalb der Stunde sind {minutes}.")
    print("Vergleich auf denselben Stationsabrufen gegen TAWES. "
          "Wiederholte Abrufe können dieselbe Analyse oder dasselbe Stundenintervall enthalten.")

    for field, title, unit in (
        ("temperature", "Temperatur", "°C"),
        ("precipitation", "Niederschlag", "mm"),
    ):
        counts, excluded, ages, groups = compare_current(runs, field, obs)
        print(f"\n## {title}\n")
        print("| Quelle | Nutzbar | Fehlender Wert | Rasterlücke | Abruffehler |")
        print("|---|---:|---:|---:|---:|")
        for source, label in (("forecast", "NWP-Fallback"), ("inca", "INCA v2")):
            c = counts[source]
            total = sum(c.values())
            availability = f"{c['ok'] / total:.1%}" if total else "—"
            print(f"| {label} | {c['ok']}/{total} ({availability}) | "
                  f"{c['missing']} | {c['grid_gap']} | {c['fetch_error']} |")
        if ages:
            print(f"\nINCA-Alter in Minuten (Minimum / Median / Maximum) "
                  f"{min(ages):.1f} / {median(ages):.1f} / {max(ages):.1f}.")
        else:
            print("\nINCA-Alter nicht verfügbar.")
        rows = [row for group in groups.values() for row in group]
        print(f"\n{len(rows)} vergleichbare Fälle. Ausgeschlossen sind "
              f"{excluded['missing_candidate']} Fälle ohne beide nutzbaren Kandidaten, "
              f"{excluded['missing_obs']} ohne passende TAWES-Messung"
              + (f", {excluded['different_interval']} mit verschiedenen Intervallen."
                 if field == "precipitation" else "."))
        if field == "precipitation":
            print("\nDie Verfügbarkeit bezieht sich auf den angezeigten NWP-Fallback der laufenden Stunde. "
                  "Für die Fehler vergleicht die Auswertung den NWP-Wert für dasselbe Stundenintervall "
                  "wie die INCA-Analyse aus demselben Abruf.")
        if not rows:
            print("\nForecast-Fallback beibehalten. Für dieses Feld fehlen vergleichbare Fälle.")
            report_nowcast(field, runs, obs)
            continue

        print(f"\n| INCA-Alter (min) | Fälle | MAE NWP ({unit}) | MAE INCA ({unit}) |")
        print("|---|---:|---:|---:|")
        age_groups = [(f"{age} bis <{age + 30}", group) for age, group in sorted(groups.items())]
        for label, group in [("Alle", rows), *age_groups]:
            print(f"| {label} | {len(group)} | {comparison_mae(group, 0):.3f} | "
                  f"{comparison_mae(group, 1):.3f} |")
        reasons = []
        if comparison_mae(rows, 1) >= comparison_mae(rows, 0):
            reasons.append("Der mittlere absolute Fehler von INCA ist gleich hoch oder größer.")
        if counts["inca"]["ok"] < counts["forecast"]["ok"]:
            reasons.append("INCA ist seltener verfügbar.")
        if field == "precipitation":
            nwp_hits, nwp_miss, nwp_false = precipitation_events(rows, 0)
            inca_hits, inca_miss, inca_false = precipitation_events(rows, 1)
            print(f"\nEreignisse ab {PRECIP_THRESHOLD:g} mm je Stunde.\n")
            print("| Quelle | Treffer | Übersehen | Fehlalarme |")
            print("|---|---:|---:|---:|")
            print(f"| NWP-Fallback | {nwp_hits} | {nwp_miss} | {nwp_false} |")
            print(f"| INCA v2 | {inca_hits} | {inca_miss} | {inca_false} |")
            if nwp_hits + nwp_miss == 0:
                reasons.append("In der Stichprobe fehlt gemessener Niederschlag.")
            elif inca_miss > nwp_miss or inca_false > nwp_false:
                reasons.append("INCA übersieht mehr Ereignisse oder erzeugt mehr Fehlalarme.")
        if reasons:
            print("\nForecast-Fallback beibehalten. " + " ".join(reasons))
        else:
            print("\nFür die erfassten Standorte und Zeiten stützt die Stichprobe einen Vorrang "
                  "für INCA. Der MAE ist kleiner und die Verfügbarkeit mindestens gleich hoch.")
        report_nowcast(field, runs, obs)

    print("\n## Unabhängigkeit der Referenz\n")
    print("TAWES-Beobachtungen können in INCA einfließen. Die Nachweise sind je Standort aufgeführt.\n")
    for (sid, lat, lon), station in sorted(stations.items()):
        evidence = station.get("inca_independence_source") or "unbelegt"
        print(f"- {sid} {station['name']} ({lat}, {lon}) · {evidence}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--stations", type=Path, help="Standard: <data-dir>/stations.json")
    parser.add_argument("--inca", action="store_true", help="INCA und NWP-Fallback als Markdown-Bericht auswerten")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    runs, obs = load(args.data_dir)
    if args.inca:
        report_current_comparison(runs)
        return 0
    stations = json.loads((args.stations or args.data_dir / "stations.json").read_text("utf-8"))
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
