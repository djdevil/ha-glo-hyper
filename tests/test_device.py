"""Test di GloDevice con un client BLE simulato (byte reali dell'Hyper Pro+)."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bleak.backends.characteristic import BleakGATTCharacteristic  # noqa: E402
from bleak.backends.device import BLEDevice  # noqa: E402

from custom_components.glo_hyper import device as device_mod  # noqa: E402
from custom_components.glo_hyper.device import GloData, GloDevice  # noqa: E402
from custom_components.glo_hyper.protocol import (  # noqa: E402
    CHAR_BATTERY,
    CHAR_DEVICE_INFO,
    CHAR_HEATING,
    CHAR_LIFECYCLE,
    CHAR_LOCK,
    CHAR_SESSION_STATUS,
    CHAR_TIME,
    DeviceState,
    HeatingMode,
    SessionState,
)

NotifyCallback = Callable[[BleakGATTCharacteristic, bytearray], None]

DEVICE_INFO: bytes = (
    bytes([1, 2, 0, 3, 0, 4]) + b"SERIAL12345678" + bytes([0, 0, 0, 7, 5, 6, 0, 9])
)


class FakeCharacteristic:
    """Sostituto minimo di BleakGATTCharacteristic."""

    def __init__(self, uuid: str) -> None:
        self.uuid: str = uuid


class FakeClient:
    """Client BLE simulato."""

    def __init__(self) -> None:
        self.is_connected: bool = True
        self.values: dict[str, bytes] = {
            CHAR_BATTERY: bytes.fromhex("4F000F00"),
            CHAR_SESSION_STATUS: bytes.fromhex("000001010001F40005"),
            CHAR_HEATING: b"\x00",
            CHAR_LOCK: b"\x00",
            CHAR_DEVICE_INFO: DEVICE_INFO,
        }
        self.writes: list[tuple[str, bytes]] = []
        self.notify: dict[str, NotifyCallback] = {}
        # Statistiche: 8 = sessioni complete, 9 = interrotte.
        self.stats: dict[int, bytes] = {8: (1234).to_bytes(4, "big"), 9: (56).to_bytes(4, "big")}
        self.answer_stats: bool = True
        self.echo: bytes | None = None

    async def read_gatt_char(self, uuid: str) -> bytearray:
        return bytearray(self.values[uuid])

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool) -> None:
        self.writes.append((uuid, bytes(data)))
        if uuid in (CHAR_HEATING, CHAR_LOCK):
            self.values[uuid] = bytes(data)
        elif uuid == CHAR_LIFECYCLE:
            if self.answer_stats and uuid in self.notify:
                payload: bytes = self.stats[data[1]]
                asyncio.get_running_loop().call_soon(self.push, uuid, payload)
        elif uuid == CHAR_SESSION_STATUS:
            status = bytearray(self.values[uuid])
            status[data[0]] = data[1]  # opcode 2 -> byte 2, opcode 3 -> byte 3
            self.values[uuid] = bytes(status)

    async def start_notify(self, uuid: str, callback: NotifyCallback) -> None:
        self.notify[uuid] = callback
        # Come il glo reale: all'attivazione rimanda l'ultimo valore inviato.
        if uuid == CHAR_LIFECYCLE and self.echo is not None:
            asyncio.get_running_loop().call_soon(self.push, uuid, self.echo)

    async def stop_notify(self, uuid: str) -> None:
        self.notify.pop(uuid, None)

    async def disconnect(self) -> None:
        self.is_connected = False

    def push(self, uuid: str, payload: bytes) -> None:
        char = FakeCharacteristic(uuid)
        self.notify[uuid](char, bytearray(payload))  # type: ignore[arg-type]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient()

    async def _connect(*args: object, **kwargs: object) -> FakeClient:
        client.is_connected = True
        return client

    monkeypatch.setattr(device_mod, "establish_connection", _connect)
    return client


def _ble() -> BLEDevice:
    return BLEDevice("AA:BB:CC:11:22:33", "Hyper Pro+ 1234", None)


def test_update_polling(fake: FakeClient) -> None:
    dev = GloDevice(_ble(), persistent=False)
    data: GloData = asyncio.run(dev.async_update())
    assert data.battery is not None and data.battery.level == 79
    assert data.status is not None and data.status.sessions_since_cleaning == 5
    assert data.heating_mode is HeatingMode.STANDARD
    assert data.locked is False
    assert data.info is not None and data.info.serial_number == "SERIAL12345678"
    assert any(uuid == CHAR_TIME for uuid, _ in fake.writes)  # ora sincronizzata
    assert data.complete_sessions == 1234
    assert data.incomplete_sessions == 56
    assert (CHAR_LIFECYCLE, b"\x00\x08") in fake.writes
    assert all(payload[0] != 0x02 for uuid, payload in fake.writes if uuid == CHAR_LIFECYCLE)
    assert data.last_seen is not None
    assert fake.is_connected is False  # disconnesso dopo la lettura
    assert fake.notify == {}


def test_persistent_notifications(fake: FakeClient) -> None:
    dev = GloDevice(_ble(), persistent=True)
    received: list[GloData] = []
    dev.add_listener(received.append)
    asyncio.run(dev.async_update())
    assert fake.is_connected is True
    assert CHAR_SESSION_STATUS in fake.notify

    fake.push(CHAR_SESSION_STATUS, bytes.fromhex("020100000101F40006"))
    assert received[-1].status is not None
    assert received[-1].status.session_state is SessionState.IN_SESSION
    assert received[-1].status.device_state is DeviceState.STANDARD
    assert received[-1].status.sessions_since_cleaning == 6
    assert received[-1].battery is not None  # gli altri dati restano

    fake.push(CHAR_BATTERY, bytes.fromhex("4E000E00"))
    assert received[-1].battery is not None and received[-1].battery.level == 78

    # Una risposta a un comando con formato diverso non deve rompere nulla.
    fake.push(CHAR_SESSION_STATUS, b"\x02")
    assert len(received) == 2


def test_commands(fake: FakeClient) -> None:
    dev = GloDevice(_ble(), persistent=False)
    asyncio.run(dev.async_update())

    data = asyncio.run(dev.async_set_heating_mode(HeatingMode.BOOST))
    assert fake.writes[-1] == (CHAR_HEATING, b"\x01")
    assert data.heating_mode is HeatingMode.BOOST

    data = asyncio.run(dev.async_set_auto_start(False))
    assert fake.writes[-1] == (CHAR_SESSION_STATUS, b"\x02\x00")
    assert data.status is not None and data.status.auto_start is False

    data = asyncio.run(dev.async_set_locked(True))
    assert fake.writes[-1] == (CHAR_LOCK, b"\x01")
    assert data.locked is True
    assert fake.is_connected is False


def test_stats_timeout_is_not_fatal(fake: FakeClient) -> None:
    fake.answer_stats = False
    dev = GloDevice(_ble(), persistent=False)
    data: GloData = asyncio.run(dev.async_update())
    assert data.battery is not None and data.battery.level == 79
    assert data.complete_sessions is None
    assert data.last_seen is not None


def test_failed_update_keeps_previous_data(fake: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    dev = GloDevice(_ble(), persistent=False)
    first: GloData = asyncio.run(dev.async_update())

    async def _fail(*args: object, **kwargs: object) -> FakeClient:
        raise TimeoutError("fuori portata")

    monkeypatch.setattr(device_mod, "establish_connection", _fail)
    with pytest.raises(device_mod.GloConnectionError):
        asyncio.run(dev.async_update())
    assert dev.data == first


def test_anomalous_value_retried(fake: FakeClient) -> None:
    """Un valore scambiato dal proxy viene riletto e non fa fallire la lettura."""
    dev = GloDevice(_ble(), persistent=False)
    good_status: bytes = fake.values[CHAR_SESSION_STATUS]
    reads: list[int] = [0]
    original = fake.read_gatt_char

    async def _read(uuid: str) -> bytearray:
        if uuid == CHAR_SESSION_STATUS and reads[0] == 0:
            reads[0] += 1
            return bytearray(bytes.fromhex("3b000b00"))  # risposta della batteria
        return await original(uuid)

    fake.read_gatt_char = _read  # type: ignore[method-assign]
    data: GloData = asyncio.run(dev.async_update())
    assert data.status is not None
    assert dev.raw_values[CHAR_SESSION_STATUS] == good_status.hex()
    assert dev.invalid_reads == 0


def test_persistently_anomalous_value_keeps_previous(fake: FakeClient) -> None:
    dev = GloDevice(_ble(), persistent=False)
    first: GloData = asyncio.run(dev.async_update())
    fake.values[CHAR_SESSION_STATUS] = bytes.fromhex("3b000b00")
    fake.values[CHAR_BATTERY] = bytes.fromhex("3a000a00")
    second: GloData = asyncio.run(dev.async_update())
    assert second.status == first.status  # mantenuto l'ultimo valore buono
    assert second.battery is not None and second.battery.level == 58  # aggiornato
    assert dev.invalid_reads == 1
    assert dev.raw_values[CHAR_SESSION_STATUS] == "3b000b00"


def test_stale_stat_notification_is_discarded(fake: FakeClient) -> None:
    """Il valore rimandato all'attivazione delle notifiche non va preso per risposta."""
    fake.echo = (1234).to_bytes(4, "big")
    dev = GloDevice(_ble(), persistent=False)
    data: GloData = asyncio.run(dev.async_update())
    assert data.complete_sessions == 1234
    assert data.incomplete_sessions == 56


def test_incomplete_equal_to_complete_keeps_known_value() -> None:
    previous = GloData(incomplete_sessions=2)
    assert device_mod._checked_incomplete(19, 19, previous) == 2
    assert device_mod._checked_incomplete(19, 3, previous) == 3
    assert device_mod._checked_incomplete(19, 19, GloData()) == 19

