"""Test della logica di presenza e dell'intervallo del coordinator."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.glo_hyper import coordinator as coord_mod  # noqa: E402
from custom_components.glo_hyper.coordinator import GloCoordinator  # noqa: E402
from custom_components.glo_hyper.device import GloData  # noqa: E402
from custom_components.glo_hyper.protocol import (  # noqa: E402
    DeviceState,
    SessionState,
    SessionStatus,
    StickStatus,
)

ADDRESS: str = "AA:BB:CC:11:22:33"
ESP: str = "AA:00:00:00:00:03"
DONGLE: str = "AA:00:00:00:00:01"


@dataclass
class FakeScanner:
    source: str


@dataclass
class FakeScannerDevice:
    scanner: FakeScanner


class FakeDevice:
    address: str = ADDRESS
    is_connected: bool = False

    def __init__(self) -> None:
        self.updates: int = 0

    def set_ble_device(self, ble_device: object) -> None:
        pass

    async def async_update(self) -> GloData:
        self.updates += 1
        return GloData(status=_status(SessionState.IN_SESSION))


class FakeStore:
    def __init__(self) -> None:
        self.saved: list[object] = []

    def async_delay_save(self, data_func: object, delay: float) -> None:
        self.saved.append(data_func())  # type: ignore[operator]


def _status(state: SessionState) -> SessionStatus:
    return SessionStatus(state, DeviceState.STANDARD, True, True, StickStatus.INSERTED, 500, 7)


def _coordinator(allowed: frozenset[str]) -> GloCoordinator:
    coord = GloCoordinator.__new__(GloCoordinator)
    coord.device = FakeDevice()  # type: ignore[assignment]
    coord.hass = object()  # type: ignore[assignment]
    coord.data = GloData(complete_sessions=5)
    coord._normal_interval = timedelta(seconds=300)
    coord._session_interval = timedelta(seconds=30)
    coord._allowed_sources = allowed
    coord._night = None
    coord._out_of_range = False
    coord.update_interval = timedelta(seconds=300)
    coord._store = FakeStore()  # type: ignore[assignment]
    return coord


def _visible_from(monkeypatch: pytest.MonkeyPatch, sources: list[str]) -> None:
    monkeypatch.setattr(
        coord_mod.bluetooth,
        "async_scanner_devices_by_address",
        lambda hass, address, connectable: [FakeScannerDevice(FakeScanner(s)) for s in sources],
    )
    monkeypatch.setattr(
        coord_mod.bluetooth,
        "async_ble_device_from_address",
        lambda hass, address, connectable: object() if sources else None,
    )


def test_no_attempt_when_only_unpaired_adapter_sees_glo(monkeypatch: pytest.MonkeyPatch) -> None:
    coord = _coordinator(frozenset({ESP}))
    _visible_from(monkeypatch, [DONGLE])
    data = asyncio.run(coord._async_update_data())
    assert data.complete_sessions == 5  # dati invariati
    assert coord.device.updates == 0  # type: ignore[attr-defined]
    assert coord._store.saved == []  # type: ignore[attr-defined]
    assert coord.out_of_range is True


def test_reads_and_switches_to_session_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    coord = _coordinator(frozenset({ESP}))
    coord._out_of_range = True
    _visible_from(monkeypatch, [ESP, DONGLE])
    data = asyncio.run(coord._async_update_data())
    assert coord.device.updates == 1  # type: ignore[attr-defined]
    assert data.status is not None and data.status.is_active
    assert coord.update_interval == timedelta(seconds=30)
    assert coord.out_of_range is False
    assert len(coord._store.saved) == 1  # type: ignore[attr-defined]


def test_back_to_normal_interval_after_session(monkeypatch: pytest.MonkeyPatch) -> None:
    coord = _coordinator(frozenset())
    coord.update_interval = timedelta(seconds=30)
    coord._adjust_interval(GloData(status=_status(SessionState.IDLE)))
    assert coord.update_interval == timedelta(seconds=300)


def test_no_filter_uses_any_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    coord = _coordinator(frozenset())
    _visible_from(monkeypatch, [DONGLE])
    asyncio.run(coord._async_update_data())
    assert coord.device.updates == 1  # type: ignore[attr-defined]


@dataclass
class FakeInfo:
    source: str


class FakeHass:
    def __init__(self) -> None:
        self.tasks: int = 0

    def async_create_task(self, coro: object) -> None:
        self.tasks += 1
        coro.close()  # type: ignore[attr-defined]


def test_immediate_refresh_on_return_in_range() -> None:
    coord = _coordinator(frozenset({ESP}))
    hass = FakeHass()
    coord.hass = hass  # type: ignore[assignment]
    coord._out_of_range = True
    coord._handle_advertisement(FakeInfo(DONGLE), None)  # type: ignore[arg-type]
    assert hass.tasks == 0 and coord.out_of_range is True  # adattatore non ammesso
    coord._handle_advertisement(FakeInfo(ESP), None)  # type: ignore[arg-type]
    assert hass.tasks == 1 and coord.out_of_range is False
    coord._handle_advertisement(FakeInfo(ESP), None)  # type: ignore[arg-type]
    assert hass.tasks == 1  # già in portata: nessuna lettura extra
