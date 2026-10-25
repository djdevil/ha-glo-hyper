"""Selezione della modalità di riscaldamento."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GloConfigEntry, GloCoordinator
from .entity import GloEntity
from .protocol import HeatingMode

MODE_DESCRIPTION: SelectEntityDescription = SelectEntityDescription(
    key="heating_mode",
    translation_key="heating_mode",
    options=[mode.name.lower() for mode in HeatingMode],
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea il select."""
    coordinator: GloCoordinator = entry.runtime_data
    async_add_entities([GloHeatingModeSelect(coordinator, MODE_DESCRIPTION)])


class GloHeatingModeSelect(GloEntity, SelectEntity):
    """Standard / Boost."""

    @property
    def current_option(self) -> str | None:
        """Modalità corrente."""
        mode: HeatingMode | None = self.glo_data.heating_mode
        return mode.name.lower() if mode is not None else None

    async def async_select_option(self, option: str) -> None:
        """Imposta la modalità."""
        mode: HeatingMode = HeatingMode[option.upper()]
        await self._async_command(lambda: self.coordinator.device.async_set_heating_mode(mode))
