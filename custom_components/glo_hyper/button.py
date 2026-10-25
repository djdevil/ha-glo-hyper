"""Pulsante "Trova il mio glo"."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import FIND_DURATION_SECONDS
from .coordinator import GloConfigEntry, GloCoordinator
from .entity import GloEntity

FIND_DESCRIPTION: ButtonEntityDescription = ButtonEntityDescription(
    key="find",
    translation_key="find",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea il pulsante."""
    coordinator: GloCoordinator = entry.runtime_data
    async_add_entities([GloFindButton(coordinator, FIND_DESCRIPTION)])


class GloFindButton(GloEntity, ButtonEntity):
    """Fa vibrare il dispositivo per ritrovarlo."""

    async def async_press(self) -> None:
        """Avvia la ricerca."""
        await self._async_command(
            lambda: self.coordinator.device.async_find(FIND_DURATION_SECONDS)
        )
