"""Restrizione degli adattatori Bluetooth usati per collegarsi al glo.

Il glo accetta connessioni solo dai central con cui è abbinato: ogni adattatore
(dongle locale o proxy ESPHome) è un central diverso. Home Assistant sceglie
sempre il percorso con il segnale migliore, quindi qui si limita la scelta agli
adattatori indicati nelle opzioni dell'integrazione.

Usa un'API interna di habluetooth (``_async_get_best_available_backend_and_device``):
se in una versione futura non esiste più, si torna al comportamento standard.
"""

from __future__ import annotations

import logging

from bleak.exc import BleakError
from habluetooth import BluetoothManager, BluetoothScannerDevice
from habluetooth.usage import HaBleakClientWithServiceCache
from habluetooth.wrappers import _HaWrappedBleakBackend
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_PRIVATE_HOOK: str = "_async_get_best_available_backend_and_device"


def connectable_adapters(hass: HomeAssistant) -> dict[str, str]:
    """Adattatori in grado di connettersi: ``{source: etichetta}``."""
    adapters: dict[str, str] = {}
    for scanner in bluetooth.async_current_scanners(hass):
        if scanner.connectable:
            adapters[scanner.source] = f"{scanner.name} ({scanner.source})"
    return adapters


def pinned_client_class(
    address: str, sources: frozenset[str]
) -> type[HaBleakClientWithServiceCache]:
    """Client che si collega solo tramite gli adattatori in ``sources``."""
    if not sources or not hasattr(HaBleakClientWithServiceCache, _PRIVATE_HOOK):
        if sources:
            _LOGGER.warning(
                "Selezione degli adattatori non supportata da questa versione "
                "di Home Assistant: verranno usati tutti"
            )
        return HaBleakClientWithServiceCache

    class GloPinnedClient(HaBleakClientWithServiceCache):
        """Wrapper HA con scelta del percorso limitata agli adattatori scelti."""

        def _async_get_best_available_backend_and_device(
            self, manager: BluetoothManager
        ) -> _HaWrappedBleakBackend:
            candidates: list[BluetoothScannerDevice] = sorted(
                (
                    device
                    for device in manager.async_scanner_devices_by_address(address, True)
                    if device.scanner.source in sources
                ),
                key=lambda device: device.advertisement.rssi,
                reverse=True,
            )
            # Stesso criterio di Home Assistant: segnale, ma penalizzando gli
            # adattatori che hanno appena fallito (es. un dongle non abbinato),
            # così il tentativo successivo passa al prossimo adattatore.
            if len(candidates) > 1:
                rssi_diff: int = (
                    candidates[0].advertisement.rssi - candidates[1].advertisement.rssi
                )
                candidates.sort(
                    key=lambda device: device.score_connection_path(rssi_diff),
                    reverse=True,
                )
            for device in candidates:
                backend: _HaWrappedBleakBackend | None = (
                    self._async_get_backend_for_ble_device(
                        manager, device.scanner, device.ble_device
                    )
                )
                if backend is not None:
                    _LOGGER.debug(
                        "%s: connessione tramite %s (RSSI %s)",
                        address,
                        device.scanner.name,
                        device.advertisement.rssi,
                    )
                    return backend
            raise BleakError(
                f"{address}: nessuno degli adattatori scelti vede il glo o ha uno slot libero"
            )

    return GloPinnedClient
