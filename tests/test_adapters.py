"""Test della selezione degli adattatori (solo quelli abbinati al glo)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bleak.exc import BleakError  # noqa: E402
from habluetooth.usage import HaBleakClientWithServiceCache  # noqa: E402

from custom_components.glo_hyper.adapters import pinned_client_class  # noqa: E402

ADDRESS: str = "AA:BB:CC:11:22:33"


@dataclass
class FakeScanner:
    source: str
    name: str


@dataclass
class FakeAdv:
    rssi: int


@dataclass
class FakeScannerDevice:
    scanner: FakeScanner
    ble_device: str
    advertisement: FakeAdv
    failures: int = 0

    def score_connection_path(self, rssi_diff: int) -> float:
        # Come habluetooth: il segnale, penalizzato dai fallimenti recenti.
        return self.advertisement.rssi - self.failures * 10


class FakeManager:
    def __init__(self, devices: list[FakeScannerDevice]) -> None:
        self.devices = devices

    def async_scanner_devices_by_address(
        self, address: str, connectable: bool
    ) -> list[FakeScannerDevice]:
        assert address == ADDRESS and connectable
        return self.devices


class FakeSelf:
    """Sostituisce l'istanza del wrapper: restituisce la sorgente scelta."""

    def _async_get_backend_for_ble_device(
        self, manager: FakeManager, scanner: FakeScanner, ble_device: str
    ) -> str:
        return scanner.source


DEVICES: list[FakeScannerDevice] = [
    FakeScannerDevice(FakeScanner("AA:00:00:00:00:01", "hci0"), "d0", FakeAdv(-60)),
    FakeScannerDevice(FakeScanner("AA:00:00:00:00:02", "hci1"), "d1", FakeAdv(-62)),
    FakeScannerDevice(FakeScanner("AA:00:00:00:00:03", "esp32"), "d2", FakeAdv(-85)),
]


def test_no_selection_uses_standard_client() -> None:
    assert pinned_client_class(ADDRESS, frozenset()) is HaBleakClientWithServiceCache


def test_pinned_ignores_stronger_unpaired_adapters() -> None:
    cls = pinned_client_class(ADDRESS, frozenset({"AA:00:00:00:00:03"}))
    assert cls is not HaBleakClientWithServiceCache
    chosen = cls._async_get_best_available_backend_and_device(  # type: ignore[arg-type]
        FakeSelf(), FakeManager(DEVICES)  # type: ignore[arg-type]
    )
    assert chosen == "AA:00:00:00:00:03"


def test_pinned_picks_best_rssi_among_selected() -> None:
    cls = pinned_client_class(ADDRESS, frozenset({"AA:00:00:00:00:03", "AA:00:00:00:00:02"}))
    chosen = cls._async_get_best_available_backend_and_device(  # type: ignore[arg-type]
        FakeSelf(), FakeManager(DEVICES)  # type: ignore[arg-type]
    )
    assert chosen == "AA:00:00:00:00:02"


def test_pinned_raises_when_selected_adapter_not_in_range() -> None:
    cls = pinned_client_class(ADDRESS, frozenset({"AA:BB:CC:DD:EE:FF"}))
    with pytest.raises(BleakError):
        cls._async_get_best_available_backend_and_device(  # type: ignore[arg-type]
            FakeSelf(), FakeManager(DEVICES)  # type: ignore[arg-type]
        )


def test_failed_adapter_is_skipped_on_next_attempt() -> None:
    devices: list[FakeScannerDevice] = [
        FakeScannerDevice(FakeScanner("AA:00:00:00:00:02", "hci1"), "d1", FakeAdv(-62), failures=3),
        FakeScannerDevice(FakeScanner("AA:00:00:00:00:03", "esp32"), "d2", FakeAdv(-80)),
    ]
    cls = pinned_client_class(ADDRESS, frozenset({"AA:00:00:00:00:02", "AA:00:00:00:00:03"}))
    chosen = cls._async_get_best_available_backend_and_device(  # type: ignore[arg-type]
        FakeSelf(), FakeManager(devices)  # type: ignore[arg-type]
    )
    assert chosen == "AA:00:00:00:00:03"
