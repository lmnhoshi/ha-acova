"""Acova Bluetooth radiator integration.

Local control of Acova radiators that use the ACOVA Control app. Not affiliated with
Acova or Zehnder. coordinator.py handles connections and protocol.py the radio format.
"""

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, WEEKDAYS
from .coordinator import AcovaCoordinator

PLATFORMS = [
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SYNC_SCHEMA = vol.Schema({vol.Optional("days"): [vol.In(WEEKDAYS)]})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the schedule sync action."""

    async def sync_schedule(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is ConfigEntryState.LOADED:
                await entry.runtime_data.async_sync_schedule(call.data.get("days"))

    hass.services.async_register(DOMAIN, "sync_schedule", sync_schedule, SYNC_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a radiator."""
    coordinator = AcovaCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a radiator."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
