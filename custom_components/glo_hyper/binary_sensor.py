"""Sensori binari del glo Hyper."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GloConfigEntry, GloCoordinator
from .device import GloData
from .entity import GloEntity
from .protocol import StickStatus


def _charging(data: GloData) -> bool | None:
    return data.battery.is_charging if data.battery else None


def _active(data: GloData) -> bool | None:
    return data.status.is_active if data.status else None


def _stick_inserted(data: GloData) -> bool | None:
    return data.status.stick is StickStatus.INSERTED if data.status else None


def _cleaning_due(data: GloData) -> bool | None:
    status = data.status
    if status is None or status.cleaning_threshold is None:
        return None
    if status.sessions_since_cleaning is None or status.cleaning_threshold == 0:
        return None
    return status.sessions_since_cleaning >= status.cleaning_threshold


@dataclass(frozen=True, kw_only=True)
class GloBinarySensorDescription(BinarySensorEntityDescription):
    """Descrizione di un sensore binario glo."""

    value_fn: Callable[[GloData], bool | None]


BINARY_SENSORS: tuple[GloBinarySensorDescription, ...] = (
    GloBinarySensorDescription(
        key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=_charging,
    ),
    GloBinarySensorDescription(
        key="session_active",
        translation_key="session_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_active,
    ),
    GloBinarySensorDescription(
        key="stick_inserted",
        translation_key="stick_inserted",
        value_fn=_stick_inserted,
    ),
    GloBinarySensorDescription(
        key="cleaning_due",
        translation_key="cleaning_due",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_cleaning_due,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea i sensori binari."""
    coordinator: GloCoordinator = entry.runtime_data
    async_add_entities(
        GloBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class GloBinarySensor(GloEntity, BinarySensorEntity):
    """Sensore binario glo."""

    entity_description: GloBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """Stato corrente."""
        return self.entity_description.value_fn(self.glo_data)
