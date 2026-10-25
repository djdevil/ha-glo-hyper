"""Interruttori del glo Hyper (auto-start, auto-stop)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GloConfigEntry, GloCoordinator
from .device import GloData, GloDevice
from .entity import GloEntity


def _auto_start(data: GloData) -> bool | None:
    return data.status.auto_start if data.status else None


def _auto_stop(data: GloData) -> bool | None:
    return data.status.auto_stop if data.status else None


def _set_auto_start(device: GloDevice, enabled: bool) -> Awaitable[GloData]:
    return device.async_set_auto_start(enabled)


def _set_auto_stop(device: GloDevice, enabled: bool) -> Awaitable[GloData]:
    return device.async_set_auto_stop(enabled)


@dataclass(frozen=True, kw_only=True)
class GloSwitchDescription(SwitchEntityDescription):
    """Descrizione di un interruttore glo."""

    value_fn: Callable[[GloData], bool | None]
    set_fn: Callable[[GloDevice, bool], Awaitable[GloData]]


SWITCHES: tuple[GloSwitchDescription, ...] = (
    GloSwitchDescription(
        key="auto_start",
        translation_key="auto_start",
        entity_category=EntityCategory.CONFIG,
        value_fn=_auto_start,
        set_fn=_set_auto_start,
    ),
    GloSwitchDescription(
        key="auto_stop",
        translation_key="auto_stop",
        entity_category=EntityCategory.CONFIG,
        value_fn=_auto_stop,
        set_fn=_set_auto_stop,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea gli interruttori."""
    coordinator: GloCoordinator = entry.runtime_data
    async_add_entities(GloSwitch(coordinator, description) for description in SWITCHES)


class GloSwitch(GloEntity, SwitchEntity):
    """Interruttore glo."""

    entity_description: GloSwitchDescription

    @property
    def is_on(self) -> bool | None:
        """Stato corrente."""
        return self.entity_description.value_fn(self.glo_data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Attiva."""
        device: GloDevice = self.coordinator.device
        await self._async_command(lambda: self.entity_description.set_fn(device, True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disattiva."""
        device: GloDevice = self.coordinator.device
        await self._async_command(lambda: self.entity_description.set_fn(device, False))
