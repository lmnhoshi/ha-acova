"""Climate entity for Acova.

Maps the radiator's modes onto HVAC modes and presets. Home Assistant always shows
both controls for a climate entity, so select.py offers the same modes as one control.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    PRESET_COMFORT,
    PRESET_ECO,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError

from .entity import AcovaEntity
from .protocol import MAX_TEMP, MIN_TEMP, TEMP_STEP, Mode

PRESET_FROST = "frost_protection"
PRESET_PROGRAM = "program"
PRESET_PILOT_WIRE = "pilot_wire"
PRESET_TO_MODE = {
    PRESET_COMFORT: Mode.COMFORT,
    PRESET_ECO: Mode.ECO,
    PRESET_FROST: Mode.FROST,
    PRESET_PROGRAM: Mode.PROGRAM,
    PRESET_PILOT_WIRE: Mode.PILOT_WIRE,
}
MODE_TO_PRESET = {mode: preset for preset, mode in PRESET_TO_MODE.items()}
# Standby is deliberately not offered: on real hardware it dropped Bluetooth and
# the radiator needed its physical button. Frost protection stays reachable.
HVAC_TO_MODE = {
    HVACMode.OFF: Mode.FROST,
    HVACMode.HEAT: Mode.COMFORT,
    HVACMode.AUTO: Mode.PROGRAM,
}


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Add the climate entity."""
    async_add_entities([AcovaClimate(entry.runtime_data)])


class AcovaClimate(AcovaEntity, ClimateEntity):
    """The radiator. The target temperature is the one in effect, if known."""

    _attr_name = None
    _attr_translation_key = "radiator"
    # Home Assistant 2026.11 deprecates this and target_temperature for removal in
    # 2027.11. Their replacements are not in 2026.10, the oldest version tested here.
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    _attr_hvac_modes = list(HVAC_TO_MODE)
    _attr_preset_modes = list(PRESET_TO_MODE)
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "climate")

    @property
    def hvac_mode(self) -> HVACMode | None:
        mode = self.coordinator.data.mode
        if mode in (Mode.STANDBY, Mode.FROST):
            return HVACMode.OFF
        if mode in (Mode.ECO, Mode.COMFORT):
            return HVACMode.HEAT
        if mode in (Mode.PROGRAM, Mode.PILOT_WIRE):
            return HVACMode.AUTO
        return None

    @property
    def preset_mode(self) -> str | None:
        return MODE_TO_PRESET.get(self.coordinator.data.mode)

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.temperature_in_effect

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {"eco_temperature": data.eco_temp, "calibration_offset": data.offset}

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.coordinator.async_set_mode(HVAC_TO_MODE[hvac_mode])

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self.coordinator.async_set_mode(PRESET_TO_MODE[preset_mode])

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs[ATTR_TEMPERATURE]
        if temperature * 2 != int(temperature * 2):
            raise ServiceValidationError("Temperature must be in 0.5 °C steps")
        await self.coordinator.async_set_comfort_temp(temperature)
