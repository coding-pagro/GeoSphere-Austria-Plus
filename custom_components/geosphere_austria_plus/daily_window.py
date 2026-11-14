"""Tagesfenster für die Tageszusammenfassung der Vorhersage.

GeoSphere- und Open-Meteo-Tage werden über dieselben Stunden gemittelt, damit
ihre Werte an der Grenze zwischen beiden Quellen vergleichbar bleiben.
"""
from __future__ import annotations

from datetime import datetime

_WINDOW_START_HOUR = 6.0
_WINDOW_END_HOUR = 21.0


def in_daily_window(dt_utc: datetime, lon: float) -> bool:
    """True, wenn dt (UTC) in Ortssonnenzeit zwischen 6 und 21 Uhr liegt."""
    local_hour = (dt_utc.hour + lon / 15.0) % 24
    return _WINDOW_START_HOUR <= local_hour < _WINDOW_END_HOUR
