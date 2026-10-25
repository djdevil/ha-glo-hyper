"""Integrazione Home Assistant per glo Hyper Pro+ via Bluetooth LE."""

from __future__ import annotations

from datetime import timedelta

from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .adapters import pinned_client_class
from .const import (
    CONF_ADAPTERS,
    CONF_NIGHT_END,
    CONF_NIGHT_INTERVAL,
    CONF_NIGHT_START,
    CONF_PERSISTENT,
    CONF_SCAN_INTERVAL,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_INTERVAL,
    DEFAULT_NIGHT_START,
    DEFAULT_PERSISTENT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import GloConfigEntry, GloCoordinator
from .device import GloDevice
from .night import NightWindow, parse_time

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LOCK,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: GloConfigEntry) -> bool:
    """Configura una voce dell'integrazione."""
    address: str = entry.unique_id or ""
    # Il glo si porta in giro: se ora non è in portata si parte lo stesso con un
    # BLEDevice provvisorio, aggiornato dal coordinator appena torna visibile.
    ble_device: BLEDevice = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    ) or BLEDevice(address, entry.title, None)

    persistent: bool = bool(entry.options.get(CONF_PERSISTENT, DEFAULT_PERSISTENT))
    scan_interval: int = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    adapters: frozenset[str] = frozenset(entry.options.get(CONF_ADAPTERS, []))
    device = GloDevice(
        ble_device,
        persistent=persistent,
        client_class=pinned_client_class(address, adapters),
    )
    coordinator = GloCoordinator(
        hass, entry, device, scan_interval, adapters, _night_window(entry)
    )
    await coordinator.async_load_snapshot()
    coordinator.async_start_presence_tracking()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Prima lettura in sottofondo: l'avvio di Home Assistant non aspetta il
    # Bluetooth, le entità partono dagli ultimi valori salvati.
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), f"{DOMAIN}_first_refresh"
    )
    return True


def _night_window(entry: GloConfigEntry) -> NightWindow | None:
    """Fascia notturna dalle opzioni; None se spenta o non valida."""
    try:
        window = NightWindow(
            start=parse_time(str(entry.options.get(CONF_NIGHT_START, DEFAULT_NIGHT_START))),
            end=parse_time(str(entry.options.get(CONF_NIGHT_END, DEFAULT_NIGHT_END))),
            interval=timedelta(
                minutes=int(entry.options.get(CONF_NIGHT_INTERVAL, DEFAULT_NIGHT_INTERVAL))
            ),
        )
    except ValueError:
        return None
    return window if window.enabled else None


async def async_unload_entry(hass: HomeAssistant, entry: GloConfigEntry) -> bool:
    """Rimuove una voce dell'integrazione."""
    unloaded: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: GloConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
