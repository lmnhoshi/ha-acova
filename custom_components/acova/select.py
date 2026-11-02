"""Single mode selector for Acova, for use without the climate entity's two controls."""

from homeassistant.components.select import SelectEntity

from .climate import MODE_TO_PRESET, PRESET_TO_MODE
from .entity import AcovaEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Add the selector."""
    async_add_entities([AcovaMode(entry.runtime_data)])


class AcovaMode(AcovaEntity, SelectEntity):
    """Every radiator mode in one control."""

    _attr_translation_key = "mode"
    _attr_options = list(PRESET_TO_MODE)

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "mode")

    @property
    def current_option(self) -> str | None:
        return MODE_TO_PRESET.get(self.coordinator.data.mode)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_mode(PRESET_TO_MODE[option])
