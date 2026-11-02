"""Open-window detection switch for Acova."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .entity import AcovaEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Add the switch."""
    async_add_entities([AcovaWindowDetection(entry.runtime_data)])


class AcovaWindowDetection(AcovaEntity, SwitchEntity):
    """Whether the radiator's open-window detection is enabled."""

    _attr_translation_key = "window_detection"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "window_detection")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.window_detection

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_window_detection(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_window_detection(False)
