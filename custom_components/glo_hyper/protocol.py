"""Protocollo BLE del glo Hyper Pro+ (famiglia "Boreas" nell'SDK BAT).

Modulo puro, senza dipendenze da Home Assistant: contiene UUID, parser ed
encoder ricostruiti dall'app myglo 1.25.0 e verificati sul dispositivo reale.
Tutti gli interi multi-byte sono big-endian.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Final

_UUID_PREFIX: Final[str] = "6cd6c8b5-e378-0204-"
_UUID_SUFFIX: Final[str] = "-1b9740683449"


def _uuid(code: str) -> str:
    """Costruisce l'UUID completo della famiglia Boreas da un codice SSCC."""
    return f"{_UUID_PREFIX}{code.lower()}{_UUID_SUFFIX}"


# --- Servizi -----------------------------------------------------------------
SESSION_SERVICE_UUID: Final[str] = _uuid("000A")

# --- Caratteristiche del servizio Session ------------------------------------
CHAR_DEVICE_INFO: Final[str] = _uuid("010A")
CHAR_TIME: Final[str] = _uuid("020A")
CHAR_BATTERY: Final[str] = _uuid("030A")
CHAR_LOCK: Final[str] = _uuid("040A")
CHAR_SESSION_RECORDS: Final[str] = _uuid("060A")
CHAR_SESSION_STATUS: Final[str] = _uuid("070A")
CHAR_FIND: Final[str] = _uuid("090A")
CHAR_LED: Final[str] = _uuid("0A0A")
# 0B0A = factory reset: volutamente NON esposto.
CHAR_HEATING: Final[str] = _uuid("0C0A")
CHAR_HAPTIC: Final[str] = _uuid("0D0A")
CHAR_BUZZER: Final[str] = _uuid("0E0A")

# --- Servizio Debug ----------------------------------------------------------
# Statistiche del ciclo di vita: si scrive una richiesta e la risposta arriva
# come notifica sulla stessa caratteristica.
CHAR_LIFECYCLE: Final[str] = _uuid("030B")

# Caratteristiche con notifiche che l'integrazione sottoscrive.
NOTIFY_CHARACTERISTICS: Final[tuple[str, ...]] = (
    CHAR_BATTERY,
    CHAR_SESSION_STATUS,
    CHAR_HEATING,
    CHAR_LOCK,
)

MANUFACTURER_ID: Final[int] = 0xFFFF


class ProtocolError(ValueError):
    """Payload ricevuto non conforme al formato atteso."""


# --- Enum --------------------------------------------------------------------
class ChargingState(IntEnum):
    """Stato di ricarica (byte 1 della caratteristica batteria)."""

    NOT_CHARGING = 0
    REGULAR = 1
    FAST = 2
    WIRELESS = 3
    UNKNOWN = 4

    @classmethod
    def from_code(cls, code: int) -> ChargingState:
        """Converte un codice grezzo, con fallback su UNKNOWN."""
        return cls(code) if 0 <= code <= 3 else cls.UNKNOWN


class SessionState(IntEnum):
    """Stato della sessione (byte 0 dello stato sessione)."""

    IDLE = 0
    HEATING = 1
    IN_SESSION = 2
    ENDING = 3
    UNKNOWN = 255

    @classmethod
    def from_code(cls, code: int) -> SessionState:
        """Converte un codice grezzo, con fallback su UNKNOWN."""
        return cls(code) if 0 <= code <= 3 else cls.UNKNOWN


class DeviceState(IntEnum):
    """Stato del dispositivo (byte 1 dello stato sessione)."""

    STANDBY = 0
    STANDARD = 1
    BOOST = 2
    SELF_CLEANING = 3
    UNKNOWN = 255

    @classmethod
    def from_code(cls, code: int) -> DeviceState:
        """Converte un codice grezzo, con fallback su UNKNOWN."""
        return cls(code) if 0 <= code <= 3 else cls.UNKNOWN


class StickStatus(IntEnum):
    """Presenza dello stick (byte 4 dello stato sessione)."""

    EMPTY = 0
    INSERTED = 1
    NON_CONSUMABLE = 2
    UNKNOWN = 255

    @classmethod
    def from_code(cls, code: int) -> StickStatus:
        """Converte un codice grezzo, con fallback su UNKNOWN."""
        return cls(code) if 0 <= code <= 2 else cls.UNKNOWN


class HeatingMode(IntEnum):
    """Modalità di riscaldamento (caratteristica 0C0A)."""

    STANDARD = 0
    BOOST = 1


class LifecycleStat(IntEnum):
    """Indici delle statistiche del ciclo di vita (contatori a 4 byte)."""

    TOTAL_CHARGE_TIME = 6
    FULL_CHARGES = 7
    COMPLETE_SESSIONS = 8
    INCOMPLETE_SESSIONS = 9


class SessionStatusCommand(IntEnum):
    """Opcode dei comandi sulla caratteristica stato sessione."""

    EOS_WARNING = 0x01
    AUTO_START = 0x02
    AUTO_STOP = 0x03
    RESET_CLEANING_UI = 0x05


# --- Strutture dati ----------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Battery:
    """Stato batteria."""

    level: int
    charging_state: ChargingState
    remaining_sessions: int
    is_authentic: bool | None

    @property
    def is_charging(self) -> bool:
        """True se il dispositivo è in carica."""
        return self.charging_state not in (
            ChargingState.NOT_CHARGING,
            ChargingState.UNKNOWN,
        )


@dataclass(frozen=True, slots=True)
class SessionStatus:
    """Stato sessione in tempo reale."""

    session_state: SessionState
    device_state: DeviceState
    auto_start: bool
    auto_stop: bool
    stick: StickStatus
    cleaning_threshold: int | None
    sessions_since_cleaning: int | None

    @property
    def is_active(self) -> bool:
        """True durante riscaldamento o sessione."""
        return self.session_state in (
            SessionState.HEATING,
            SessionState.IN_SESSION,
            SessionState.ENDING,
        )


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Versioni e seriale del dispositivo."""

    firmware_major: int
    firmware_minor: int
    sw_revision: int
    board_classification: int
    serial_number: str
    bootloader_version: int
    ble_firmware_major: int
    ble_firmware_minor: int
    ble_sw_revision: int

    @property
    def firmware_version(self) -> str:
        """Versione firmware leggibile."""
        return f"{self.firmware_major}.{self.firmware_minor}.{self.sw_revision}"

    @property
    def ble_firmware_version(self) -> str:
        """Versione firmware BLE leggibile."""
        return (
            f"{self.ble_firmware_major}.{self.ble_firmware_minor}."
            f"{self.ble_sw_revision}"
        )


@dataclass(frozen=True, slots=True)
class AdvertisementData:
    """Dati decodificati dalla manufacturer data (8 byte)."""

    mac_address: str
    device_color: int


# --- Helper ------------------------------------------------------------------
def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "big")


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "big")


# --- Parser ------------------------------------------------------------------
def parse_battery(data: bytes) -> Battery:
    """Decodifica la caratteristica batteria (3 o 4 byte).

    Esempio reale: ``4F 00 0F 00`` -> 79%, non in carica, 15 sessioni.
    """
    if len(data) not in (3, 4):
        raise ProtocolError(f"Battery: lunghezza inattesa {len(data)}: {data.hex()}")
    authentic: bool | None = data[3] == 0 if len(data) == 4 else None
    return Battery(
        level=data[0],
        charging_state=ChargingState.from_code(data[1]),
        remaining_sessions=data[2],
        is_authentic=authentic,
    )


def parse_session_status(data: bytes) -> SessionStatus:
    """Decodifica lo stato sessione Boreas (5 o 9 byte).

    Esempio reale: ``00 00 01 01 00 01F4 0005``.
    """
    if len(data) not in (5, 9):
        raise ProtocolError(
            f"SessionStatus: lunghezza inattesa {len(data)}: {data.hex()}"
        )
    threshold: int | None = _u16(data, 5) if len(data) == 9 else None
    since_cleaning: int | None = _u16(data, 7) if len(data) == 9 else None
    return SessionStatus(
        session_state=SessionState.from_code(data[0]),
        device_state=DeviceState.from_code(data[1]),
        auto_start=data[2] == 1,
        auto_stop=data[3] == 1,
        stick=StickStatus.from_code(data[4]),
        cleaning_threshold=threshold,
        sessions_since_cleaning=since_cleaning,
    )


def parse_heating_mode(data: bytes) -> HeatingMode:
    """Decodifica la modalità di riscaldamento Boreas (1 byte)."""
    if len(data) != 1:
        raise ProtocolError(f"Heating: lunghezza inattesa {len(data)}: {data.hex()}")
    return HeatingMode.BOOST if data[0] == 1 else HeatingMode.STANDARD


def parse_lock(data: bytes) -> bool:
    """Decodifica lo stato di blocco (1 byte, 1 = bloccato)."""
    if len(data) != 1 or data[0] > 1:
        raise ProtocolError(f"Lock: payload inatteso {data.hex()}")
    return data[0] == 1


def parse_device_info(data: bytes) -> DeviceInfo:
    """Decodifica le informazioni dispositivo Boreas (28 byte)."""
    if len(data) != 28:
        raise ProtocolError(
            f"DeviceInfo: lunghezza inattesa {len(data)}: {data.hex()}"
        )
    serial: str = data[6:20].decode("ascii", errors="replace").strip("\x00 ")
    return DeviceInfo(
        firmware_major=data[0],
        firmware_minor=data[1],
        sw_revision=_u16(data, 2),
        board_classification=_u16(data, 4),
        serial_number=serial,
        bootloader_version=_u32(data, 20),
        ble_firmware_major=data[24],
        ble_firmware_minor=data[25],
        ble_sw_revision=_u16(data, 26),
    )


def parse_advertisement(manufacturer_payload: bytes) -> AdvertisementData:
    """Decodifica gli 8 byte di manufacturer data (company ID escluso).

    Esempio reale: ``332211CCBBAA 02 00`` -> MAC ``AA:BB:CC:11:22:33``, colore 2.
    """
    if len(manufacturer_payload) != 8:
        raise ProtocolError(
            f"Advertisement: lunghezza inattesa {len(manufacturer_payload)}"
        )
    mac: str = ":".join(f"{b:02X}" for b in reversed(manufacturer_payload[0:6]))
    return AdvertisementData(mac_address=mac, device_color=manufacturer_payload[6])


def parse_lifecycle_value(data: bytes) -> int:
    """Valore di una singola statistica (uint16 o uint32 big-endian).

    Le risposte da 1 byte (statistiche azzerate) o da 32/36/56 byte (tutte le
    statistiche) non sono valori singoli e vengono rifiutate.
    """
    if len(data) not in (2, 4):
        raise ProtocolError(f"Lifecycle: lunghezza inattesa {len(data)}: {data.hex()}")
    return int.from_bytes(data, "big")


def parse_time(data: bytes) -> int:
    """Decodifica l'orologio del dispositivo (uint32, secondi Unix)."""
    if len(data) != 4:
        raise ProtocolError(f"Time: lunghezza inattesa {len(data)}")
    return _u32(data, 0)


# --- Encoder -----------------------------------------------------------------
def encode_session_command(command: SessionStatusCommand, enabled: bool) -> bytes:
    """Comando a 2 byte per lo stato sessione (auto-start, auto-stop, EOS)."""
    if command is SessionStatusCommand.RESET_CLEANING_UI:
        return bytes((command.value, 0))
    return bytes((command.value, 1 if enabled else 0))


def encode_heating_mode(mode: HeatingMode) -> bytes:
    """Imposta Standard (0) o Boost (1)."""
    return bytes((mode.value,))


def encode_lock(locked: bool) -> bytes:
    """Blocca (1) o sblocca (0) il dispositivo."""
    return bytes((1 if locked else 0,))


def encode_find(alerting: bool, seconds: int) -> bytes:
    """Attiva/disattiva "Trova il mio glo" per ``seconds`` secondi (0-255)."""
    if not 0 <= seconds <= 255:
        raise ValueError("seconds deve essere tra 0 e 255")
    return bytes((1 if alerting else 0, seconds))


def encode_lifecycle_request(stat: LifecycleStat) -> bytes:
    """Richiesta di una singola statistica: ``00 NN``.

    Mai inviare ``02``: azzera tutte le statistiche del dispositivo.
    """
    return bytes((0x00, stat.value))


def encode_time(unix_seconds: int) -> bytes:
    """Imposta l'orologio del dispositivo."""
    return unix_seconds.to_bytes(4, "big")
