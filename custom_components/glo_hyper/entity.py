"""Entità base del glo Hyper."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import GloCoordinator
from .device import GloConnectionError, GloData


class GloEntity(CoordinatorEntity[GloCoordinator]):
    """Entità collegata al coordinator del dispositivo."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GloCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        address: str = coordinator.device.address
        self._attr_unique_id = f"{address}_{description.key}"
        info = coordinator.data.info if coordinator.data else None
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, address)},
            identifiers={(DOMAIN, address)},
            name=coordinator.config_entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
            serial_number=info.serial_number if info else None,
            sw_version=info.firmware_version if info else None,
            hw_version=info.ble_firmware_version if info else None,
        )

    @property
    def glo_data(self) -> GloData:
        """Ultimi dati noti (vuoti se il glo non è mai stato raggiunto)."""
        data: GloData | None = self.coordinator.data
        return data if data is not None else GloData()

    @property
    def available(self) -> bool:
        """Disponibile dopo il primo contatto, anche quando il glo è lontano.

        Il glo si porta in giro: invece di diventare "non disponibile" a ogni
        lettura fallita, l'entità mostra l'ultimo valore noto. Il sensore
        "Ultimo contatto" dice quanto è recente.
        """
        return self.glo_data.last_seen is not None

    async def _async_command(self, command: Callable[[], Awaitable[GloData]]) -> None:
        """Esegue un comando e pubblica subito il nuovo stato."""
        try:
            data: GloData = await command()
        except GloConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self.coordinator.async_set_updated_data(data)
