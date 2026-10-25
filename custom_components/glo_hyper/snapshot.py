"""Salvataggio su disco dell'ultimo stato letto dal glo.

Serve a far ripartire tutte le entità con l'ultimo valore noto dopo un
riavvio di Home Assistant, anche se il glo in quel momento è lontano.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .device import GloData
from .protocol import (
    Battery,
    ChargingState,
    DeviceInfo,
    DeviceState,
    HeatingMode,
    SessionState,
    SessionStatus,
    StickStatus,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION: int = 1

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonDict = dict[str, JsonValue]


def to_dict(data: GloData) -> JsonDict:
    """GloData → dizionario serializzabile in JSON."""
    battery: JsonDict | None = (
        {
            "level": data.battery.level,
            "charging_state": data.battery.charging_state.value,
            "remaining_sessions": data.battery.remaining_sessions,
            "is_authentic": data.battery.is_authentic,
        }
        if data.battery
        else None
    )
    status: JsonDict | None = (
        {
            "session_state": data.status.session_state.value,
            "device_state": data.status.device_state.value,
            "auto_start": data.status.auto_start,
            "auto_stop": data.status.auto_stop,
            "stick": data.status.stick.value,
            "cleaning_threshold": data.status.cleaning_threshold,
            "sessions_since_cleaning": data.status.sessions_since_cleaning,
        }
        if data.status
        else None
    )
    info: JsonDict | None = (
        {
            "firmware_major": data.info.firmware_major,
            "firmware_minor": data.info.firmware_minor,
            "sw_revision": data.info.sw_revision,
            "board_classification": data.info.board_classification,
            "serial_number": data.info.serial_number,
            "bootloader_version": data.info.bootloader_version,
            "ble_firmware_major": data.info.ble_firmware_major,
            "ble_firmware_minor": data.info.ble_firmware_minor,
            "ble_sw_revision": data.info.ble_sw_revision,
        }
        if data.info
        else None
    )
    return {
        "battery": battery,
        "status": status,
        "heating_mode": data.heating_mode.value if data.heating_mode is not None else None,
        "locked": data.locked,
        "info": info,
        "complete_sessions": data.complete_sessions,
        "incomplete_sessions": data.incomplete_sessions,
        "last_seen": data.last_seen.isoformat() if data.last_seen else None,
    }


def _int(value: JsonValue) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"atteso un intero, trovato {value!r}")
    return value


def _opt_int(value: JsonValue) -> int | None:
    return None if value is None else _int(value)


def _bool(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"atteso un booleano, trovato {value!r}")
    return value


def _opt_bool(value: JsonValue) -> bool | None:
    return None if value is None else _bool(value)


def _dict(value: JsonValue) -> JsonDict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError(f"atteso un oggetto, trovato {value!r}")
    return value


def from_dict(raw: JsonValue) -> GloData | None:
    """Dizionario salvato → GloData; None se il formato non è riconosciuto."""
    try:
        root: JsonDict | None = _dict(raw)
        if root is None:
            return None
        battery: Battery | None = None
        if (b := _dict(root.get("battery"))) is not None:
            battery = Battery(
                level=_int(b["level"]),
                charging_state=ChargingState.from_code(_int(b["charging_state"])),
                remaining_sessions=_int(b["remaining_sessions"]),
                is_authentic=_opt_bool(b.get("is_authentic")),
            )
        status: SessionStatus | None = None
        if (s := _dict(root.get("status"))) is not None:
            status = SessionStatus(
                session_state=SessionState.from_code(_int(s["session_state"])),
                device_state=DeviceState.from_code(_int(s["device_state"])),
                auto_start=_bool(s["auto_start"]),
                auto_stop=_bool(s["auto_stop"]),
                stick=StickStatus.from_code(_int(s["stick"])),
                cleaning_threshold=_opt_int(s.get("cleaning_threshold")),
                sessions_since_cleaning=_opt_int(s.get("sessions_since_cleaning")),
            )
        info: DeviceInfo | None = None
        if (i := _dict(root.get("info"))) is not None:
            serial = i["serial_number"]
            info = DeviceInfo(
                firmware_major=_int(i["firmware_major"]),
                firmware_minor=_int(i["firmware_minor"]),
                sw_revision=_int(i["sw_revision"]),
                board_classification=_int(i["board_classification"]),
                serial_number=serial if isinstance(serial, str) else "",
                bootloader_version=_int(i["bootloader_version"]),
                ble_firmware_major=_int(i["ble_firmware_major"]),
                ble_firmware_minor=_int(i["ble_firmware_minor"]),
                ble_sw_revision=_int(i["ble_sw_revision"]),
            )
        mode_raw: int | None = _opt_int(root.get("heating_mode"))
        last_seen_raw = root.get("last_seen")
        return GloData(
            battery=battery,
            status=status,
            heating_mode=HeatingMode(mode_raw) if mode_raw is not None else None,
            locked=_opt_bool(root.get("locked")),
            info=info,
            complete_sessions=_opt_int(root.get("complete_sessions")),
            incomplete_sessions=_opt_int(root.get("incomplete_sessions")),
            last_seen=(
                datetime.fromisoformat(last_seen_raw)
                if isinstance(last_seen_raw, str)
                else None
            ),
        )
    except (KeyError, ValueError, TypeError) as err:
        _LOGGER.warning("Stato salvato del glo non leggibile, ignorato: %s", err)
        return None
