"""Diagnostica scaricabile dalla pagina dell'integrazione."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from enum import Enum
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_ADAPTERS
from .coordinator import GloConfigEntry, GloCoordinator
from .device import GloData

# Il seriale identifica il dispositivo: non va nei file condivisi.
TO_REDACT: frozenset[str] = frozenset({"serial_number"})

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def _to_json(value: object) -> JsonValue:
    """Converte dataclass, enum e date in valori serializzabili."""
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _data_dict(data: GloData | None) -> JsonValue:
    if data is None:
        return None
    return _to_json(asdict(data))


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GloConfigEntry
) -> dict[str, Any]:
    """Stato dell'integrazione, ultimi dati e adattatori che vedono il glo."""
    coordinator: GloCoordinator = entry.runtime_data
    address: str = coordinator.device.address
    allowed: list[str] = list(entry.options.get(CONF_ADAPTERS, []))

    adapters: list[dict[str, JsonValue]] = [
        {
            "name": scanner_device.scanner.name,
            "source": scanner_device.scanner.source,
            "rssi": scanner_device.advertisement.rssi,
            "allowed": not allowed or scanner_device.scanner.source in allowed,
        }
        for scanner_device in bluetooth.async_scanner_devices_by_address(
            hass, address, connectable=True
        )
    ]

    return {
        "entry": {
            "title": entry.title,
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_s": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "out_of_range": coordinator.out_of_range,
            "connected": coordinator.device.is_connected,
            "invalid_reads": coordinator.device.invalid_reads,
        },
        "adapters_seeing_device": adapters,
        "data": async_redact_data(_data_dict(coordinator.data), TO_REDACT),
        "raw_values_hex": coordinator.device.raw_values,
    }
