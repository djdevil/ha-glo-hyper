"""Test del protocollo con i byte letti dal glo Hyper Pro+ reale."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_PATH: Path = (
    Path(__file__).resolve().parents[1] / "custom_components" / "glo_hyper" / "protocol.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("glo_protocol", _PATH)
    assert spec is not None and spec.loader is not None
    module: ModuleType = importlib.util.module_from_spec(spec)
    sys.modules["glo_protocol"] = module
    spec.loader.exec_module(module)
    return module


p: ModuleType = _load()


def test_battery_real() -> None:
    battery = p.parse_battery(bytes.fromhex("4F000F00"))
    assert battery.level == 79
    assert battery.charging_state is p.ChargingState.NOT_CHARGING
    assert battery.remaining_sessions == 15
    assert battery.is_authentic is True
    assert battery.is_charging is False


def test_battery_charging() -> None:
    battery = p.parse_battery(bytes.fromhex("640232"))
    assert battery.is_charging is True
    assert battery.is_authentic is None


def test_session_status_real() -> None:
    status = p.parse_session_status(bytes.fromhex("000001010001F40005"))
    assert status.session_state is p.SessionState.IDLE
    assert status.device_state is p.DeviceState.STANDBY
    assert status.auto_start is True
    assert status.auto_stop is True
    assert status.stick is p.StickStatus.EMPTY
    assert status.cleaning_threshold == 500
    assert status.sessions_since_cleaning == 5
    assert status.is_active is False


def test_session_status_short() -> None:
    status = p.parse_session_status(bytes.fromhex("0202000001"))
    assert status.session_state is p.SessionState.IN_SESSION
    assert status.device_state is p.DeviceState.BOOST
    assert status.stick is p.StickStatus.INSERTED
    assert status.cleaning_threshold is None
    assert status.is_active is True


def test_heating_real() -> None:
    assert p.parse_heating_mode(b"\x00") is p.HeatingMode.STANDARD
    assert p.parse_heating_mode(b"\x01") is p.HeatingMode.BOOST


def test_advertisement_real() -> None:
    adv = p.parse_advertisement(bytes.fromhex("332211CCBBAA0200"))
    assert adv.mac_address == "AA:BB:CC:11:22:33"
    assert adv.device_color == 2


def test_device_info() -> None:
    raw = bytes([1, 2, 0, 3, 0, 4]) + b"ABCDEFGHIJKLMN" + bytes([0, 0, 0, 7, 5, 6, 0, 9])
    info = p.parse_device_info(raw)
    assert info.serial_number == "ABCDEFGHIJKLMN"
    assert info.firmware_version == "1.2.3"
    assert info.ble_firmware_version == "5.6.9"
    assert info.bootloader_version == 7


def test_encoders() -> None:
    assert p.encode_session_command(p.SessionStatusCommand.AUTO_START, True) == b"\x02\x01"
    assert p.encode_session_command(p.SessionStatusCommand.AUTO_STOP, False) == b"\x03\x00"
    assert p.encode_heating_mode(p.HeatingMode.BOOST) == b"\x01"
    assert p.encode_lock(True) == b"\x01"
    assert p.encode_find(True, 10) == b"\x01\x0a"
    assert p.encode_time(0x01020304) == b"\x01\x02\x03\x04"


def test_uuids() -> None:
    assert p.CHAR_BATTERY == "6cd6c8b5-e378-0204-030a-1b9740683449"
    assert p.SESSION_SERVICE_UUID == "6cd6c8b5-e378-0204-000a-1b9740683449"


@pytest.mark.parametrize("raw", ["", "00", "0000000000000000"])
def test_bad_lengths(raw: str) -> None:
    with pytest.raises(p.ProtocolError):
        p.parse_session_status(bytes.fromhex(raw))


def test_lifecycle() -> None:
    assert p.encode_lifecycle_request(p.LifecycleStat.COMPLETE_SESSIONS) == b"\x00\x08"
    assert p.parse_lifecycle_value(bytes.fromhex("000004D2")) == 1234
    assert p.parse_lifecycle_value(bytes.fromhex("0102")) == 258
    with pytest.raises(p.ProtocolError):
        p.parse_lifecycle_value(b"\x00")
