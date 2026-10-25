"""Blocco del glo Hyper."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GloConfigEntry, GloCoordinator
from .entity import GloEntity

LOCK_DESCRIPTION: LockEntityDescription = LockEntityDescription(
    key="lock",
    translation_key="device_lock",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea il lock."""
    coordinator: GloCoordinator = entry.runtime_data
    async_add_entities([GloLock(coordinator, LOCK_DESCRIPTION)])


class GloLock(GloEntity, LockEntity):
    """Blocca/sblocca il dispositivo."""

    @property
    def is_locked(self) -> bool | None:
        """True se bloccato."""
        return self.glo_data.locked

    async def async_lock(self, **kwargs: Any) -> None:
        """Blocca."""
        await self._async_command(lambda: self.coordinator.device.async_set_locked(True))

    async def async_unlock(self, **kwargs: Any) -> None:
        """Sblocca."""
        await self._async_command(lambda: self.coordinator.device.async_set_locked(False))
