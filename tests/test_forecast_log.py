"""Tests für die zeitgleiche Aufzeichnung und den INCA-Vergleich."""
from datetime import datetime, timedelta
from io import BytesIO
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from tools.forecast_log import analyze, forecast_log as logger


STATION = {"id": "123", "name": "Test", "lat": 48.2, "lon": 15.6, "alt": 250}
FETCHED = datetime.fromisoformat("2026-11-11T12:05:00+00:00")
HOUR_END = FETCHED.replace(minute=0)


def model_data(times, **series):
    return {
        "times": [t.isoformat() if isinstance(t, datetime) else t for t in times],
        "values": {"123": series},
        "retrieved_at": FETCHED.isoformat(),
    }


def test_fallback_keeps_first_eligible_point_in_api_order():
    older = FETCHED - timedelta(minutes=61)
    first = FETCHED - timedelta(hours=1)
    data = model_data([older, "invalid", first, HOUR_END],
                      **{"2t": [8, 7, None, 6], "rain": [0, 0, 0.25, 0], "sf": [0, 0, 0.5, 0]})
    result = logger.candidates(logger.NWP[0], "123", FETCHED, data)
    assert result["temperature"] == {"status": "missing", "valid_at": first.isoformat(), "value": None}
    assert result["precipitation"]["value"] == 0.75
    assert result["precipitation"]["entity_value"] == 0.75
    assert result["precipitation"]["interval_start"] == (first - timedelta(hours=1)).isoformat()
    assert result["precipitation"]["interval_end"] == first.isoformat()


def test_inca_takes_latest_eligible_timestamp_even_if_field_is_missing():
    data = model_data([HOUR_END, HOUR_END - timedelta(hours=1), HOUR_END + timedelta(hours=1)],
                      **{"2t": [None, 6, 7], "tp": [0, 2, 3]})
    result = logger.candidates(logger.INCA[0], "123", FETCHED, data)
    assert result["temperature"]["status"] == "missing"
    assert result["temperature"]["valid_at"] == HOUR_END.isoformat()
    assert result["precipitation"]["value"] == 0
    stale = model_data([FETCHED - timedelta(hours=2, seconds=1)], **{"2t": [6]})
    assert logger.candidates(logger.INCA[0], "123", FETCHED, stale)["temperature"]["status"] == "missing"


@pytest.mark.parametrize("snow, amount, status", [(0, 0, "ok"), (None, None, "missing")])
def test_dry_fallback_distinguishes_zero_from_missing(snow, amount, status):
    data = model_data([HOUR_END], **{"rain": [0], "sf": [snow]})
    precip = logger.candidates(logger.NWP[0], "123", FETCHED, data)["precipitation"]
    assert precip["value"] == amount
    assert precip["entity_value"] is None
    assert precip["status"] == status


def test_inca_isolates_grid_gap_and_counts_transport_error(monkeypatch):
    outside = {**STATION, "id": "456", "lat": 53}

    def fetch_points(endpoint, params, stations, **filters):
        assert filters["tries"] == 1
        if outside in stations:
            body = BytesIO(b'{"detail":"Requested point is outside of dataset bounds!"}')
            raise HTTPError(endpoint, 400, "Bad Request", {}, body)
        raise TimeoutError("timeout")

    monkeypatch.setattr(logger, "fetch_points", fetch_points)
    errors = []
    assert logger.fetch_inca([STATION, outside], FETCHED, errors) == {
        "123": (None, "fetch_error"), "456": (None, "grid_gap"),
    }
    assert len(errors) == 1


@pytest.mark.parametrize("nwp_failed", [False, True])
def test_collect_records_same_points_and_preserves_legacy_series(monkeypatch, tmp_path, nwp_failed):
    stations_file = tmp_path / "stations.json"
    stations_file.write_text(json.dumps([STATION]), encoding="utf-8")
    calls = {}

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return FETCHED

    def fetch(url, tries=4):
        url = urlparse(url)
        query = parse_qs(url.query)
        calls[url.path] = (query, tries)
        if nwp_failed and url.path.endswith(logger.NWP[0]) and tries == 1:
            raise TimeoutError("first NWP request")
        params = query["parameters"][0].split(",")
        return {
            "timestamps": [HOUR_END.isoformat()],
            "features": [{
                "geometry": {"coordinates": [STATION["lon"], STATION["lat"]]},
                "properties": {"station": STATION["id"],
                               "parameters": {p: {"data": [1]} for p in params}},
            }],
        }

    monkeypatch.setattr(logger, "datetime", FixedDatetime)
    monkeypatch.setattr(logger, "fetch", fetch)
    monkeypatch.setattr(logger.time, "sleep", lambda _: None)
    data_dir = tmp_path / "data"
    assert logger.collect(data_dir, stations_file) == 0
    runs, _ = analyze.load(data_dir)
    run = runs[0]
    assert run["stations"] == [STATION]
    assert run["nwp"]["values"]["123"]["tp"] == [1]
    assert run["nowcast"]["values"]["123"]["rr"] == [1]
    assert run["obs"]["locations"] == {"123": [48.2, 15.6]}
    forecast = run["comparison"]["forecast"]["123"]
    inca = run["comparison"]["inca"]["123"]
    assert inca["retrieved_at"] == run["comparison"]["sampled_at"]
    if nwp_failed:
        assert forecast["precipitation"]["status"] == "fetch_error"
        assert forecast["retrieved_at"] is None
    else:
        assert forecast["retrieved_at"] == inca["retrieved_at"]
        assert forecast["precipitation"]["value"] == 2
    assert inca["precipitation"]["value"] == 1
    if not nwp_failed:
        assert forecast["precipitation_inca_interval"]["value"] == 2
    nwp_query = calls[f"/v1/timeseries/forecast/{logger.NWP[0]}"][0]
    assert nwp_query["start"] == [(HOUR_END - timedelta(hours=2)).isoformat(timespec="minutes")]
    assert calls[f"/v1/timeseries/forecast/{logger.NWP[0]}"][0]["lat_lon"] == ["48.2,15.6"]
    assert calls[f"/v1/timeseries/historical/{logger.INCA[0]}"][0]["lat_lon"] == ["48.2,15.6"]


def comparison_run():
    nwp = model_data([HOUR_END], **{"2t": [5], "rain": [0.2], "sf": [0]})
    inca = logger.candidates(logger.INCA[0], "123", FETCHED, model_data(
        [HOUR_END], **{"2t": [3], "tp": [0]},
    ))
    forecast = logger.candidates(logger.NWP[0], "123", FETCHED, nwp)
    forecast["precipitation_inca_interval"] = logger.forecast_for_interval(
        "123", nwp, inca["precipitation"],
    )
    return {
        "stations": [STATION],
        "comparison": {"sampled_at": FETCHED.isoformat(), "forecast": {"123": forecast},
                       "inca": {"123": inca}},
    }


def measurement_run(lat=48.2, amounts=None):
    times = [HOUR_END + timedelta(minutes=10 * k) for k in range(-5, 2)]
    return {
        "obs": {
            "times": [t.isoformat() for t in times],
            "values": {"123": {"TL": [1, 1, 1, 1, 1, 2, 6], "RR": amounts or [0] * 7}},
            "locations": {"123": [lat, 15.6]},
        },
    }


@pytest.mark.parametrize("lat, expected", [(48.2, [(5, 3, 4)]), (48.3, [])])
def test_temperature_reference_at_capture_time_and_same_point(lat, expected):
    run = comparison_run()
    obs = analyze.comparison_observations([measurement_run(lat)])
    counts, excluded, ages, groups = analyze.compare_current([run], "temperature", obs)
    assert counts["inca"]["ok"] == 1
    assert ages == [5]
    assert groups.get(0, []) == expected
    assert excluded["missing_obs"] == int(not expected)


def test_precipitation_needs_complete_identical_interval():
    run = comparison_run()
    obs = analyze.comparison_observations([measurement_run(amounts=[0, 0.1, 0, 0, 0, 0.2, 20])])
    _, excluded, _, groups = analyze.compare_current([run], "precipitation", obs)
    nwp, inca, reference = groups[0][0]
    assert (nwp, inca, reference) == pytest.approx((0.2, 0, 0.3))
    assert analyze.precipitation_events(groups[0], 0) == (1, 0, 0)
    assert analyze.precipitation_events(groups[0], 1) == (0, 1, 0)
    assert not excluded

    incomplete = analyze.comparison_observations([measurement_run(amounts=[0, None, 0, 0, 0, 0, 0])])
    _, excluded, _, groups = analyze.compare_current([run], "precipitation", incomplete)
    assert not groups
    assert excluded["missing_obs"] == 1

    candidate = run["comparison"]["forecast"]["123"]["precipitation_inca_interval"]
    candidate["interval_start"] = HOUR_END.isoformat()
    candidate["interval_end"] = (HOUR_END + timedelta(hours=1)).isoformat()
    _, excluded, _, groups = analyze.compare_current([run], "precipitation", obs)
    assert not groups
    assert excluded["different_interval"] == 1


def test_precipitation_uses_forecast_for_inca_interval_not_displayed_hour():
    """Der angezeigte Fallback gilt für die laufende Stunde, INCA für eine frühere."""
    inca_end = HOUR_END - timedelta(hours=1)
    nwp = model_data([inca_end, HOUR_END], **{"2t": [4, 5], "rain": [0.4, 3], "sf": [0.1, 0]})
    inca = logger.candidates(logger.INCA[0], "123", FETCHED, model_data(
        [inca_end], **{"2t": [3], "tp": [0.3]},
    ))
    forecast = logger.candidates(logger.NWP[0], "123", FETCHED, nwp)
    assert forecast["precipitation"]["interval_end"] == HOUR_END.isoformat()
    forecast["precipitation_inca_interval"] = logger.forecast_for_interval(
        "123", nwp, inca["precipitation"],
    )
    assert forecast["precipitation_inca_interval"] == {
        "status": "ok", "value": 0.5,
        "interval_start": (inca_end - timedelta(hours=1)).isoformat(),
        "interval_end": inca_end.isoformat(),
    }
    run = {"stations": [STATION], "comparison": {
        "sampled_at": FETCHED.isoformat(), "forecast": {"123": forecast}, "inca": {"123": inca},
    }}
    amounts = [0.1] * 6 + [0] * 7
    times = [inca_end + timedelta(minutes=10 * k) for k in range(-5, 8)]
    obs = analyze.comparison_observations([{"obs": {
        "times": [t.isoformat() for t in times],
        "values": {"123": {"TL": [1] * len(times), "RR": amounts}},
        "locations": {"123": [48.2, 15.6]},
    }}])
    counts, excluded, _, groups = analyze.compare_current([run], "precipitation", obs)
    assert counts["forecast"]["ok"] == 1
    assert not excluded
    assert groups[60] == [pytest.approx((0.5, 0.3, 0.6))]


def test_forecast_for_interval_reports_missing_values():
    inca = {"interval_start": HOUR_END.isoformat(),
            "interval_end": (HOUR_END + timedelta(hours=1)).isoformat()}
    data = model_data([HOUR_END], **{"rain": [1], "sf": [0]})
    assert logger.forecast_for_interval("123", data, inca)["status"] == "missing"
    assert logger.forecast_for_interval("123", None, inca) == {"status": "fetch_error"}
    assert logger.forecast_for_interval("123", data, {"status": "missing"}) == {"status": "missing"}
    gap = {**data, "grid_gaps": ["123"]}
    assert logger.forecast_for_interval("123", gap, inca) == {"status": "grid_gap"}
    partial = model_data([HOUR_END], **{"rain": [1], "sf": [None]})
    assert logger.forecast_for_interval(
        "123", partial, {"interval_start": "x", "interval_end": HOUR_END.isoformat()},
    )["status"] == "missing"


def test_legacy_comparison_without_inca_interval_counts_as_different_interval():
    run = comparison_run()
    del run["comparison"]["forecast"]["123"]["precipitation_inca_interval"]
    obs = analyze.comparison_observations([measurement_run()])
    counts, excluded, _, groups = analyze.compare_current([run], "precipitation", obs)
    assert counts["forecast"]["ok"] == 1
    assert not groups
    assert excluded["different_interval"] == 1


def test_trim_forecast_starts_at_current_hour():
    times = [HOUR_END + timedelta(hours=k) for k in range(-2, 3)]
    data = {"times": [t.isoformat() for t in times], "values": {"123": {"tp": [0, 1, 2, 3, 4]}}}
    trimmed = logger.trim_forecast(data, 2, since=HOUR_END)
    assert trimmed["times"] == [t.isoformat() for t in times[2:4]]
    assert trimmed["values"]["123"]["tp"] == [2, 3]
    assert logger.trim_forecast(data, 2)["values"]["123"]["tp"] == [0, 1]


def test_report_ignores_legacy_forecast_without_inca(capsys):
    analyze.report_current_comparison([{"version": 1, "nwp": {}}])
    assert "Keine zeitgleich aufgezeichneten" in capsys.readouterr().out
