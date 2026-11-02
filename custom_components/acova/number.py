"""Temperature control for Acova, for use without the climate entity."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature

from .entity import AcovaEntity
from .protocol import MAX_TEMP, MIN_TEMP, TEMP_STEP


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Add the temperature control."""
    async_add_entities([AcovaTemperature(entry.runtime_data)])


class AcovaTemperature(AcovaEntity, NumberEntity):
    """The temperature in effect, settable in comfort only."""

    _attr_translation_key = "temperature"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_TEMP
    _attr_native_max_value = MAX_TEMP
    _attr_native_step = TEMP_STEP
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "temperature")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.temperature_in_effect

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_comfort_temp(value)
