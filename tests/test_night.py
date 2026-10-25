"""Test della fascia notturna."""

from __future__ import annotations

import sys
from datetime import datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.glo_hyper.night import NightWindow, parse_time  # noqa: E402

NORMAL: timedelta = timedelta(seconds=500)
NIGHT: NightWindow = NightWindow(time(23, 0), time(7, 0), timedelta(minutes=60))


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 25, hour, minute)


def test_window_across_midnight() -> None:
    assert NIGHT.contains(time(23, 0))
    assert NIGHT.contains(time(2, 30))
    assert not NIGHT.contains(time(7, 0))
    assert not NIGHT.contains(time(22, 59))


def test_window_same_day() -> None:
    day = NightWindow(time(13, 0), time(15, 0), timedelta(minutes=30))
    assert day.contains(time(14, 0))
    assert not day.contains(time(16, 0))


def test_interval_inside_and_outside() -> None:
    assert NIGHT.interval_at(_at(1), NORMAL) == timedelta(minutes=60)
    assert NIGHT.interval_at(_at(12), NORMAL) == NORMAL


def test_interval_capped_at_window_end() -> None:
    # 06:40: mancano 20 minuti alla fine, non si aspetta un'ora intera.
    assert NIGHT.interval_at(_at(6, 40), NORMAL) == timedelta(minutes=20)
    # 06:58: mai sotto l'intervallo normale.
    assert NIGHT.interval_at(_at(6, 58), NORMAL) == NORMAL


def test_disabled() -> None:
    off = NightWindow(time(23, 0), time(7, 0), timedelta(0))
    assert not off.enabled
    assert not off.contains(time(2, 0))
    assert off.interval_at(_at(2), NORMAL) == NORMAL


def test_parse_time() -> None:
    assert parse_time("23:30:00") == time(23, 30)
    assert parse_time("07:00") == time(7, 0)
