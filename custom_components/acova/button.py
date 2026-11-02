"""Schedule sync button for Acova."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from .entity import AcovaEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Add the button."""
    async_add_entities(
        [AcovaRefresh(entry.runtime_data), AcovaSyncSchedule(entry.runtime_data)]
    )


class AcovaRefresh(AcovaEntity, ButtonEntity):
    """Connect now and update the displayed values."""

    _attr_translation_key = "refresh"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "refresh")

    async def async_press(self) -> None:
        await self.coordinator.async_refresh_on_demand()


class AcovaSyncSchedule(AcovaEntity, ButtonEntity):
    """Write the chosen Schedule helper to the radiator."""

    _attr_translation_key = "sync_schedule"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "sync_schedule")

    async def async_press(self) -> None:
        await self.coordinator.async_sync_schedule()
