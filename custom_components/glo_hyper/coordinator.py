"""Coordinator dell'integrazione glo Hyper."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SESSION_SCAN_INTERVAL
from .device import GloConnectionError, GloData, GloDevice
from .night import NightWindow
from .snapshot import STORAGE_VERSION, JsonDict, from_dict, to_dict

# Attesa prima di scrivere su disco: raggruppa aggiornamenti ravvicinati.
_SAVE_DELAY: float = 30.0

_LOGGER = logging.getLogger(__name__)

type GloConfigEntry = ConfigEntry[GloCoordinator]


class GloCoordinator(DataUpdateCoordinator[GloData]):
    """Lettura periodica, aggiornamenti push e gestione della presenza.

    - Se nessun adattatore scelto riceve il glo, non tenta la connessione
      (niente tentativi a vuoto né errori nei log) e mantiene gli ultimi dati.
    - Appena un adattatore scelto torna a ricevere il glo, legge subito.
    - Durante una sessione legge più spesso per cogliere subito la fine.
    """

    config_entry: GloConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GloConfigEntry,
        device: GloDevice,
        scan_interval: int,
        allowed_sources: frozenset[str],
        night: NightWindow | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{device.address}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.device: GloDevice = device
        self._normal_interval: timedelta = timedelta(seconds=scan_interval)
        self._session_interval: timedelta = timedelta(seconds=SESSION_SCAN_INTERVAL)
        self._allowed_sources: frozenset[str] = allowed_sources
        self._night: NightWindow | None = night
        self._out_of_range: bool = False
        self._unsubscribers: list[Callable[[], None]] = [
            device.add_listener(self._handle_push)
        ]
        self._store: Store[JsonDict] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    # --- Stato salvato ------------------------------------------------------------
    async def async_load_snapshot(self) -> None:
        """Riparte dall'ultimo stato salvato (tutte le entità restano disponibili)."""
        saved: GloData | None = from_dict(await self._store.async_load())
        if saved is not None:
            self.data = saved
            self.device.restore_data(saved)

    def _save_snapshot(self, data: GloData) -> None:
        self._store.async_delay_save(lambda: to_dict(data), _SAVE_DELAY)

    # --- Presenza -----------------------------------------------------------------
    @property
    def out_of_range(self) -> bool:
        """True se il glo non è ricevuto da nessun adattatore scelto."""
        return self._out_of_range

    @callback
    def async_start_presence_tracking(self) -> None:
        """Ascolta gli annunci del glo per accorgersi subito del rientro in zona."""
        self._unsubscribers.append(
            bluetooth.async_register_callback(
                self.hass,
                self._handle_advertisement,
                BluetoothCallbackMatcher(address=self.device.address, connectable=True),
                BluetoothScanningMode.PASSIVE,
            )
        )
        self._unsubscribers.append(
            bluetooth.async_track_unavailable(
                self.hass,
                self._handle_unavailable,
                self.device.address,
                connectable=True,
            )
        )

    def _is_visible(self) -> bool:
        """True se almeno un adattatore ammesso riceve il glo."""
        if self.device.is_connected:
            # Collegato: il glo non trasmette annunci ma è raggiungibile.
            return True
        devices = bluetooth.async_scanner_devices_by_address(
            self.hass, self.device.address, connectable=True
        )
        if self._allowed_sources:
            return any(d.scanner.source in self._allowed_sources for d in devices)
        return bool(devices)

    def _set_out_of_range(self, value: bool) -> None:
        if value == self._out_of_range:
            return
        self._out_of_range = value
        if value:
            _LOGGER.info("%s: glo fuori portata, letture sospese", self.device.address)
        else:
            _LOGGER.info("%s: glo di nuovo in portata", self.device.address)

    @callback
    def _handle_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        if self._allowed_sources and service_info.source not in self._allowed_sources:
            return
        if self._out_of_range:
            self._set_out_of_range(False)
            # Rientro in zona: lettura immediata invece di attendere il giro.
            self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _handle_unavailable(self, service_info: BluetoothServiceInfoBleak) -> None:
        if self.device.is_connected:
            return  # niente annunci perché è collegato, non perché è lontano
        self._set_out_of_range(True)

    # --- Aggiornamenti ------------------------------------------------------------
    def _adjust_interval(self, data: GloData) -> None:
        """Breve in sessione, lungo nella fascia notturna, normale altrimenti."""
        active: bool = data.status is not None and data.status.is_active
        wanted: timedelta
        reason: str
        if active:
            wanted, reason = self._session_interval, "sessione attiva"
        elif self._night is not None and self._night.contains(dt_util.now().time()):
            wanted = self._night.interval_at(dt_util.now(), self._normal_interval)
            reason = "fascia notturna"
        else:
            wanted, reason = self._normal_interval, "normale"
        if self.update_interval != wanted:
            _LOGGER.debug(
                "%s: intervallo di lettura %s s (%s)",
                self.device.address,
                int(wanted.total_seconds()),
                reason,
            )
            self.update_interval = wanted

    @callback
    def _handle_push(self, data: GloData) -> None:
        self._adjust_interval(data)
        self._save_snapshot(data)
        self.async_set_updated_data(data)

    async def _async_update_data(self) -> GloData:
        previous: GloData = self.data if self.data is not None else GloData()
        if not self._is_visible():
            # Assenza normale: nessun tentativo, nessun errore, dati invariati.
            self._set_out_of_range(True)
            self._adjust_interval(GloData())
            return previous
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.device.address, connectable=True
        )
        if ble_device is None:
            self._set_out_of_range(True)
            return previous
        self._set_out_of_range(False)
        self.device.set_ble_device(ble_device)
        try:
            data: GloData = await self.device.async_update()
        except GloConnectionError as err:
            raise UpdateFailed(str(err)) from err
        self._adjust_interval(data)
        self._save_snapshot(data)
        return data

    async def async_shutdown(self) -> None:
        """Chiude la connessione e rimuove gli ascoltatori allo scaricamento."""
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        await self.device.async_disconnect()
        await super().async_shutdown()
