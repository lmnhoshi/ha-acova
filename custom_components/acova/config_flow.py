"""Config flow for Acova: discover, then pair using the radiator's 2H button.

The options flow chooses the Schedule helper that the sync button writes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_SCHEDULE, DOMAIN
from .coordinator import COMM_ERRORS, async_pair
from .protocol import DEVICE_NAME_MARKER

_LOGGER = logging.getLogger(__name__)


class AcovaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle adding a radiator."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return AcovaOptionsFlow()

    def __init__(self) -> None:
        self._address: str | None = None
        self._name: str | None = None
        self._pair_task: asyncio.Task[None] | None = None
        self._errors: dict[str, str] = {}

    async def _async_select(self, address: str, name: str) -> None:
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        self._address, self._name = address, name
        self.context["title_placeholders"] = {"name": name}

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a radiator found by Home Assistant."""
        await self._async_select(discovery_info.address, discovery_info.name)
        return await self.async_step_confirm()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose from the radiators in range."""
        current = self._async_current_ids()
        found = {
            info.address: info.name
            for info in bluetooth.async_discovered_service_info(self.hass, True)
            if DEVICE_NAME_MARKER in (info.name or "") and info.address not in current
        }
        if not found:
            return self.async_abort(reason="no_devices_found")
        if user_input is not None:
            address = user_input["address"]
            await self._async_select(address, found[address])
            return await self.async_step_confirm()
        labels = {address: f"{name} ({address})" for address, name in found.items()}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("address"): vol.In(labels)}),
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain the button press before connecting."""
        if user_input is not None:
            self._errors = {}
            return await self.async_step_pair()
        return self.async_show_form(
            step_id="confirm",
            errors=self._errors,
            description_placeholders={"name": self._name},
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pair in the background while the user presses the button."""
        if self._pair_task is None:
            # eager_start=False: a task that fails instantly (radiator out of range)
            # would skip the progress step and make the flow loop forever.
            self._pair_task = self.hass.async_create_task(
                async_pair(self.hass, self._address), eager_start=False
            )
        if not self._pair_task.done():
            return self.async_show_progress(
                step_id="pair",
                progress_action="pairing",
                progress_task=self._pair_task,
            )
        task, self._pair_task = self._pair_task, None
        try:
            await task
        except COMM_ERRORS as err:
            _LOGGER.warning("Pairing with %s failed: %r", self._address, err)
            self._errors = {"base": "pairing_failed"}
            return self.async_show_progress_done(next_step_id="confirm")
        return self.async_show_progress_done(next_step_id="finish")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry."""
        return self.async_create_entry(title=self._name, data={})


class AcovaOptionsFlow(OptionsFlow):
    """Choose the Schedule helper to sync to the radiator."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the helper picker."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCHEDULE)
        key = (
            vol.Required(CONF_SCHEDULE, default=current)
            if current
            else vol.Required(CONF_SCHEDULE)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {key: selector.EntitySelector(selector.EntitySelectorConfig(domain="schedule"))}
            ),
        )
