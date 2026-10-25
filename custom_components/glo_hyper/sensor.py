"""Sensori del glo Hyper."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import IntEnum

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorExtraStoredData,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import GloConfigEntry, GloCoordinator
from .device import GloData
from .entity import GloEntity
from .protocol import ChargingState, DeviceState, SessionState, StickStatus

SensorValue = StateType | date | datetime | Decimal


def _enum_value(value: IntEnum | None) -> StateType:
    """Nome dell'enum in minuscolo; i codici sconosciuti diventano None."""
    if value is None or value.name == "UNKNOWN":
        return None
    return value.name.lower()


def _options(enum_cls: type[IntEnum]) -> list[str]:
    return [m.name.lower() for m in enum_cls if m.name != "UNKNOWN"]


def _battery_level(data: GloData) -> StateType:
    return data.battery.level if data.battery else None


def _remaining_sessions(data: GloData) -> StateType:
    return data.battery.remaining_sessions if data.battery else None


def _charging_state(data: GloData) -> StateType:
    return _enum_value(data.battery.charging_state if data.battery else None)


def _session_state(data: GloData) -> StateType:
    return _enum_value(data.status.session_state if data.status else None)


def _device_state(data: GloData) -> StateType:
    return _enum_value(data.status.device_state if data.status else None)


def _stick(data: GloData) -> StateType:
    return _enum_value(data.status.stick if data.status else None)


def _since_cleaning(data: GloData) -> StateType:
    return data.status.sessions_since_cleaning if data.status else None


def _cleaning_threshold(data: GloData) -> StateType:
    return data.status.cleaning_threshold if data.status else None


def _complete_sessions(data: GloData) -> StateType:
    return data.complete_sessions


def _incomplete_sessions(data: GloData) -> StateType:
    return data.incomplete_sessions


def _last_seen(data: GloData) -> SensorValue:
    return data.last_seen


@dataclass(frozen=True, kw_only=True)
class GloSensorDescription(SensorEntityDescription):
    """Descrizione di un sensore glo."""

    value_fn: Callable[[GloData], SensorValue]


SENSORS: tuple[GloSensorDescription, ...] = (
    GloSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_battery_level,
    ),
    GloSensorDescription(
        key="remaining_sessions",
        translation_key="remaining_sessions",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_remaining_sessions,
    ),
    GloSensorDescription(
        key="charging_state",
        translation_key="charging_state",
        device_class=SensorDeviceClass.ENUM,
        options=_options(ChargingState),
        value_fn=_charging_state,
    ),
    GloSensorDescription(
        key="session_state",
        translation_key="session_state",
        device_class=SensorDeviceClass.ENUM,
        options=_options(SessionState),
        value_fn=_session_state,
    ),
    GloSensorDescription(
        key="device_state",
        translation_key="device_state",
        device_class=SensorDeviceClass.ENUM,
        options=_options(DeviceState),
        value_fn=_device_state,
    ),
    GloSensorDescription(
        key="stick",
        translation_key="stick",
        device_class=SensorDeviceClass.ENUM,
        options=_options(StickStatus),
        value_fn=_stick,
    ),
    GloSensorDescription(
        key="sessions_since_cleaning",
        translation_key="sessions_since_cleaning",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_since_cleaning,
    ),
    GloSensorDescription(
        key="complete_sessions",
        translation_key="complete_sessions",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_complete_sessions,
    ),
    GloSensorDescription(
        key="incomplete_sessions",
        translation_key="incomplete_sessions",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_incomplete_sessions,
    ),
    GloSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_seen,
    ),
    GloSensorDescription(
        key="cleaning_threshold",
        translation_key="cleaning_threshold",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_cleaning_threshold,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea i sensori."""
    coordinator: GloCoordinator = entry.runtime_data
    async_add_entities(GloSensor(coordinator, description) for description in SENSORS)


class GloSensor(GloEntity, RestoreSensor):
    """Sensore glo che ricorda l'ultimo valore anche dopo un riavvio di HA."""

    entity_description: GloSensorDescription
    _restored_value: SensorValue = None

    async def async_added_to_hass(self) -> None:
        """Recupera l'ultimo valore salvato."""
        await super().async_added_to_hass()
        last: SensorExtraStoredData | None = await self.async_get_last_sensor_data()
        if last is not None:
            self._restored_value = last.native_value

    @property
    def available(self) -> bool:
        """Disponibile se c'è un valore attuale o salvato."""
        return super().available or self._restored_value is not None

    @property
    def native_value(self) -> SensorValue:
        """Valore attuale, altrimenti l'ultimo salvato."""
        value: SensorValue = self.entity_description.value_fn(self.glo_data)
        return value if value is not None else self._restored_value
