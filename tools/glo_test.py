"""Script di test da PC per il glo Hyper Pro+ (richiede: pip install bleak).

Uso:
    python glo_test.py scan
    python glo_test.py read   [--address XX:XX:...]
    python glo_test.py watch  [--address ...]          # notifiche in tempo reale
    python glo_test.py mode standard|boost
    python glo_test.py autostart on|off
    python glo_test.py autostop on|off
    python glo_test.py lock on|off
    python glo_test.py find [--seconds 10]

Chiudere l'app myglo prima di usarlo: il dispositivo accetta una sola connessione.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData


def _load_protocol() -> ModuleType:
    path: Path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "glo_hyper"
        / "protocol.py"
    )
    spec = importlib.util.spec_from_file_location("glo_protocol", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Impossibile caricare {path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    sys.modules["glo_protocol"] = module
    spec.loader.exec_module(module)
    return module


P: ModuleType = _load_protocol()


async def find_device(address: str | None, timeout: float = 15.0) -> BLEDevice:
    """Trova il glo per indirizzo o per UUID del servizio Session."""
    if address:
        device: BLEDevice | None = await BleakScanner.find_device_by_address(
            address, timeout=timeout
        )
    else:

        def _match(_: BLEDevice, adv: AdvertisementData) -> bool:
            return P.SESSION_SERVICE_UUID in [u.lower() for u in adv.service_uuids]

        device = await BleakScanner.find_device_by_filter(_match, timeout=timeout)
    if device is None:
        raise SystemExit("glo non trovato: è acceso e l'app myglo è chiusa?")
    return device


async def cmd_scan() -> None:
    found: dict[str, tuple[BLEDevice, AdvertisementData]] = (
        await BleakScanner.discover(timeout=10.0, return_adv=True)
    )
    for device, adv in found.values():
        if P.SESSION_SERVICE_UUID not in [u.lower() for u in adv.service_uuids]:
            continue
        payload: bytes | None = adv.manufacturer_data.get(P.MANUFACTURER_ID)
        extra: str = ""
        if payload is not None and len(payload) == 8:
            parsed = P.parse_advertisement(payload)
            extra = f" MAC reale={parsed.mac_address} colore={parsed.device_color}"
        print(f"{device.name} [{device.address}] RSSI={adv.rssi}{extra}")


async def _read_all(client: BleakClient) -> None:
    battery = P.parse_battery(bytes(await client.read_gatt_char(P.CHAR_BATTERY)))
    print(
        f"Batteria: {battery.level}% | ricarica={battery.charging_state.name} "
        f"| sessioni rimanenti={battery.remaining_sessions}"
    )
    status = P.parse_session_status(
        bytes(await client.read_gatt_char(P.CHAR_SESSION_STATUS))
    )
    print(
        f"Sessione: {status.session_state.name} | dispositivo={status.device_state.name} "
        f"| auto-start={status.auto_start} | auto-stop={status.auto_stop} "
        f"| stick={status.stick.name} | pulizia={status.sessions_since_cleaning}/"
        f"{status.cleaning_threshold}"
    )
    mode = P.parse_heating_mode(bytes(await client.read_gatt_char(P.CHAR_HEATING)))
    print(f"Modalità: {mode.name}")
    locked: bool = P.parse_lock(bytes(await client.read_gatt_char(P.CHAR_LOCK)))
    print(f"Bloccato: {locked}")
    raw_info: bytes = bytes(await client.read_gatt_char(P.CHAR_DEVICE_INFO))
    try:
        info = P.parse_device_info(raw_info)
        print(
            f"Seriale: {info.serial_number} | FW {info.firmware_version} "
            f"| BLE FW {info.ble_firmware_version}"
        )
    except P.ProtocolError:
        print(f"Device info (grezzo, {len(raw_info)} B): {raw_info.hex()}")
    print(f"LED (grezzo): {bytes(await client.read_gatt_char(P.CHAR_LED)).hex()}")


async def cmd_read(address: str | None) -> None:
    device: BLEDevice = await find_device(address)
    async with BleakClient(device) as client:
        await _read_all(client)


def _notification_handler(name: str) -> Callable[[BleakGATTCharacteristic, bytearray], None]:
    def _handler(_: BleakGATTCharacteristic, data: bytearray) -> None:
        raw: bytes = bytes(data)
        try:
            if name == "battery":
                print("[notifica] batteria:", P.parse_battery(raw))
            elif name == "status":
                print("[notifica] sessione:", P.parse_session_status(raw))
            elif name == "heating":
                print("[notifica] modalità:", P.parse_heating_mode(raw).name)
            else:
                print("[notifica] lock:", P.parse_lock(raw))
        except P.ProtocolError as err:
            print(f"[notifica] {name} non decodificata ({err}): {raw.hex()}")

    return _handler


async def cmd_watch(address: str | None) -> None:
    device: BLEDevice = await find_device(address)
    async with BleakClient(device) as client:
        await _read_all(client)
        await client.start_notify(P.CHAR_BATTERY, _notification_handler("battery"))
        await client.start_notify(P.CHAR_SESSION_STATUS, _notification_handler("status"))
        await client.start_notify(P.CHAR_HEATING, _notification_handler("heating"))
        await client.start_notify(P.CHAR_LOCK, _notification_handler("lock"))
        print("In ascolto... (Ctrl+C per uscire). Prova ad avviare una sessione.")
        while client.is_connected:
            await asyncio.sleep(1.0)


async def cmd_write(address: str | None, char_uuid: str, payload: bytes) -> None:
    device: BLEDevice = await find_device(address)
    async with BleakClient(device) as client:
        print(f"Scrivo {payload.hex()} su {char_uuid}")
        await client.write_gatt_char(char_uuid, payload, response=True)
        await asyncio.sleep(1.0)
        await _read_all(client)


def _on(value: str) -> bool:
    return value.lower() in ("on", "1", "true", "si", "sì")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test BLE glo Hyper Pro+")
    parser.add_argument("--address", default=None, help="Indirizzo/UUID BLE del glo")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    sub.add_parser("read")
    sub.add_parser("watch")
    sub.add_parser("mode").add_argument("value", choices=["standard", "boost"])
    sub.add_parser("autostart").add_argument("value", choices=["on", "off"])
    sub.add_parser("autostop").add_argument("value", choices=["on", "off"])
    sub.add_parser("lock").add_argument("value", choices=["on", "off"])
    find = sub.add_parser("find")
    find.add_argument("--seconds", type=int, default=10)
    args = parser.parse_args()

    address: str | None = args.address
    cmd: str = args.cmd
    if cmd == "scan":
        asyncio.run(cmd_scan())
    elif cmd == "read":
        asyncio.run(cmd_read(address))
    elif cmd == "watch":
        asyncio.run(cmd_watch(address))
    elif cmd == "mode":
        mode = P.HeatingMode.BOOST if args.value == "boost" else P.HeatingMode.STANDARD
        asyncio.run(cmd_write(address, P.CHAR_HEATING, P.encode_heating_mode(mode)))
    elif cmd in ("autostart", "autostop"):
        command = (
            P.SessionStatusCommand.AUTO_START
            if cmd == "autostart"
            else P.SessionStatusCommand.AUTO_STOP
        )
        payload: bytes = P.encode_session_command(command, _on(args.value))
        asyncio.run(cmd_write(address, P.CHAR_SESSION_STATUS, payload))
    elif cmd == "lock":
        asyncio.run(cmd_write(address, P.CHAR_LOCK, P.encode_lock(_on(args.value))))
    elif cmd == "find":
        seconds: int = args.seconds
        asyncio.run(cmd_write(address, P.CHAR_FIND, P.encode_find(True, seconds)))


if __name__ == "__main__":
    main()
