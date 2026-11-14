"""Tests für das gemeinsame Tagesfenster der Tageszusammenfassung."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from custom_components.geosphere_austria_plus.daily_window import in_daily_window


@pytest.mark.parametrize(
    ("utc_hour", "expected"),
    [
        (4, False),   # 05:05 Ortssonnenzeit
        (5, True),    # 06:05
        (19, True),   # 20:05
        (20, False),  # 21:05
    ],
)
def test_window_boundaries_in_vienna(utc_hour, expected):
    """lon 16.37 → Ortssonnenzeit = UTC + 1 h 5 min."""
    dt = datetime(2026, 11, 15, utc_hour, tzinfo=timezone.utc)
    assert in_daily_window(dt, 16.37) is expected


def test_naive_utc_timestamps_are_accepted():
    """Open-Meteo liefert Stundenzeitstempel ohne Zeitzone (UTC)."""
    assert in_daily_window(datetime(2026, 11, 15, 12), 16.37) is True
