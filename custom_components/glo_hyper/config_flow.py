"""Config flow con rilevamento Bluetooth."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TimeSelector,
)

from .adapters import connectable_adapters
from .const import (
    CONF_ADAPTERS,
    CONF_NIGHT_END,
    CONF_NIGHT_INTERVAL,
    CONF_NIGHT_START,
    CONF_PERSISTENT,
    CONF_SCAN_INTERVAL,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_INTERVAL,
    DEFAULT_NIGHT_START,
    DEFAULT_PERSISTENT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_NIGHT_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .protocol import SESSION_SERVICE_UUID


def _is_glo(info: BluetoothServiceInfoBleak) -> bool:
    return SESSION_SERVICE_UUID in [uuid.lower() for uuid in info.service_uuids]


def _title(info: BluetoothServiceInfoBleak) -> str:
    return info.name or f"glo {info.address}"


class GloConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gestisce l'aggiunta di un glo Hyper."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Dispositivo rilevato automaticamente da Home Assistant."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": _title(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Conferma del dispositivo rilevato."""
        discovery: BluetoothServiceInfoBleak | None = self._discovery
        if discovery is None:
            return self.async_abort(reason="no_devices_found")
        if user_input is not None:
            return self.async_create_entry(title=_title(discovery), data={})
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": _title(discovery)},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Aggiunta manuale: scelta tra i glo visibili."""
        if user_input is not None:
            address: str = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=_title(self._discovered[address]), data={}
            )

        current: set[str | None] = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current or not _is_glo(info):
                continue
            self._discovered[info.address] = info
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        options: dict[str, str] = {
            address: f"{_title(info)} ({address})"
            for address, info in self._discovered.items()
        }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GloOptionsFlow:
        """Opzioni: connessione persistente e intervallo di lettura."""
        return GloOptionsFlow()


class GloOptionsFlow(OptionsFlow):
    """Opzioni dell'integrazione."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Form delle opzioni."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        adapters: dict[str, str] = connectable_adapters(self.hass)
        # Mantiene visibili anche adattatori scelti ma ora offline.
        selected: list[str] = list(options.get(CONF_ADAPTERS, []))
        for source in selected:
            adapters.setdefault(source, source)
        schema = vol.Schema(
            {
                vol.Optional(CONF_ADAPTERS, default=selected): cv.multi_select(adapters),
                vol.Required(
                    CONF_PERSISTENT,
                    default=bool(options.get(CONF_PERSISTENT, DEFAULT_PERSISTENT)),
                ): bool,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=int(options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
                vol.Required(
                    CONF_NIGHT_START,
                    default=str(options.get(CONF_NIGHT_START, DEFAULT_NIGHT_START)),
                ): TimeSelector(),
                vol.Required(
                    CONF_NIGHT_END,
                    default=str(options.get(CONF_NIGHT_END, DEFAULT_NIGHT_END)),
                ): TimeSelector(),
                vol.Required(
                    CONF_NIGHT_INTERVAL,
                    default=int(options.get(CONF_NIGHT_INTERVAL, DEFAULT_NIGHT_INTERVAL)),
                ): vol.All(
                    NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=MAX_NIGHT_INTERVAL,
                            step=5,
                            unit_of_measurement="min",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Coerce(int),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
