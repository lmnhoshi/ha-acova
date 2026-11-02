"""Base entity for Acova."""

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AcovaCoordinator


class AcovaEntity(CoordinatorEntity[AcovaCoordinator]):
    """Entity attached to the radiator device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AcovaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="Acova",
            name=coordinator.config_entry.title,
            sw_version=coordinator.data.firmware,
        )

    @property
    def available(self) -> bool:
        """Keep the last known values through a failed read."""
        return self.coordinator.data is not None
