"""Test del salvataggio dello stato su disco."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.glo_hyper.device import GloData  # noqa: E402
from custom_components.glo_hyper.protocol import (  # noqa: E402
    HeatingMode,
    parse_battery,
    parse_device_info,
    parse_session_status,
)
from custom_components.glo_hyper.snapshot import from_dict, to_dict  # noqa: E402


def _full() -> GloData:
    return GloData(
        battery=parse_battery(bytes.fromhex("4F000F00")),
        status=parse_session_status(bytes.fromhex("000001010101F40012")),
        heating_mode=HeatingMode.BOOST,
        locked=False,
        info=parse_device_info(
            bytes([1, 2, 0, 3, 0, 4]) + b"SERIAL12345678" + bytes([0, 0, 0, 7, 5, 6, 0, 9])
        ),
        complete_sessions=18,
        incomplete_sessions=2,
        last_seen=datetime(2026, 10, 24, 14, 41, 55, tzinfo=UTC),
    )


def test_roundtrip_through_json() -> None:
    original: GloData = _full()
    restored = from_dict(json.loads(json.dumps(to_dict(original))))
    assert restored == original


def test_empty_and_invalid() -> None:
    assert from_dict(None) is None
    assert from_dict(to_dict(GloData())) == GloData()
    assert from_dict({"battery": {"level": "molto"}}) is None
    assert from_dict("rotto") is None
