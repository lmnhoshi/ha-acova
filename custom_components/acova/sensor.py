"""Sensors for Acova: last contact, and the weekly program's temperatures."""

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory, UnitOfTemperature

from .entity import AcovaEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Add the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            AcovaLastRead(coordinator),
            AcovaProgramTarget(coordinator, "auto_comfort_target", 0),
            AcovaProgramTarget(coordinator, "auto_eco_target", 1),
        ]
    )


class AcovaProgramTarget(AcovaEntity, SensorEntity):
    """A temperature the weekly program uses, shown only while it runs.

    Unknown in other modes, and until the integration has seen the radiator in
    comfort once, because the radiator does not report its comfort setting otherwise.
    """

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, key: str, index: int) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._index = index

    @property
    def native_value(self) -> float | None:
        targets = self.coordinator.program_targets
        return None if targets is None else targets[self._index]


class AcovaLastRead(AcovaEntity, SensorEntity):
    """When the displayed values were read from the radiator."""

    _attr_translation_key = "last_read"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "last_read")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_read
