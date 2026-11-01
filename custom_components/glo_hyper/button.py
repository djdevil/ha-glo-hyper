"""Pulsanti "Trova il mio glo" e "Interroga ora"."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, FIND_DURATION_SECONDS
from .coordinator import GloConfigEntry, GloCoordinator
from .entity import GloEntity

FIND_DESCRIPTION: ButtonEntityDescription = ButtonEntityDescription(
    key="find",
    translation_key="find",
)

REFRESH_DESCRIPTION: ButtonEntityDescription = ButtonEntityDescription(
    key="refresh",
    translation_key="refresh",
    icon="mdi:refresh",
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea i pulsanti."""
    coordinator: GloCoordinator = entry.runtime_data
    async_add_entities(
        [
            GloFindButton(coordinator, FIND_DESCRIPTION),
            GloRefreshButton(coordinator, REFRESH_DESCRIPTION),
        ]
    )


class GloFindButton(GloEntity, ButtonEntity):
    """Fa vibrare il dispositivo per ritrovarlo."""

    async def async_press(self) -> None:
        """Avvia la ricerca."""
        await self._async_command(
            lambda: self.coordinator.device.async_find(FIND_DURATION_SECONDS)
        )


class GloRefreshButton(GloEntity, ButtonEntity):
    """Legge subito il glo senza aspettare il prossimo giro.

    Utile dopo l'abbinamento di un nuovo adattatore (5 pressioni sul glo):
    la modalità pairing dura poco e non conviene aspettare l'intervallo.
    """

    @property
    def available(self) -> bool:
        """Sempre disponibile: serve proprio quando il glo non è mai stato letto."""
        return True

    async def async_press(self) -> None:
        """Esegue subito una lettura e segnala l'eventuale errore."""
        await self.coordinator.async_refresh()
        if self.coordinator.out_of_range:
            # Nessun adattatore scelto riceve il glo: la lettura non è partita.
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_in_range",
            )
        if not self.coordinator.last_update_success:
            error: BaseException | None = self.coordinator.last_exception
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="refresh_failed",
                translation_placeholders={"error": str(error) if error else "?"},
            )
