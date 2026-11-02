"""Connection handling for an Acova radiator.

Each operation connects, does its work and disconnects, so nothing is held open
between operations. There is no polling. See the class docstring for why.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, time
import logging
from math import ceil
from typing import Any

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_SCHEDULE, DATA_COMFORT, WEEKDAYS
from .protocol import (
    AcovaProtocolError,
    AcovaSession,
    Mode,
    RadiatorState,
    decode_day_plan,
    eco_for_comfort,
    encode_day_plan,
)

_LOGGER = logging.getLogger(__name__)

SETTLE_BEFORE_DISCONNECT = 3  # the app waits this long before closing a session
PAIR_TIMEOUT = 45
PAIR_RETRY_DELAY = 2
COMM_ERRORS = (BleakError, AcovaProtocolError, TimeoutError, EOFError)


def _seconds(value: Any) -> int:
    """Return seconds since midnight for a time or an HH:MM[:SS] string."""
    if isinstance(value, time):
        extra = 1 if value.microsecond else 0  # time.max stands for 24:00
        return value.hour * 3600 + value.minute * 60 + value.second + extra
    parts = [int(part) for part in str(value).split(":")]
    return parts[0] * 3600 + parts[1] * 60 + (parts[2] if len(parts) > 2 else 0)


def comfort_hours_from_blocks(blocks: list[dict[str, Any]]) -> list[bool]:
    """Mark every hour touched by a block, as the radiator only has whole hours."""
    hours = [False] * 24
    for block in blocks:
        start = _seconds(block["from"]) // 3600
        end = ceil(_seconds(block["to"]) / 3600)
        hours[start:end] = [True] * (end - start)
    return hours


async def _connect(hass: HomeAssistant, address: str):
    device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if device is None:
        raise BleakError(f"Radiator {address} is not in Bluetooth range")
    return await establish_connection(
        BleakClientWithServiceCache, device, device.name or address, max_attempts=3
    )


async def async_pair(hass: HomeAssistant, address: str) -> None:
    """Bond with the radiator; the user presses its button during this call."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PAIR_TIMEOUT
    client = await _connect(hass, address)
    try:
        session = AcovaSession(client)
        await session.start()
        while True:
            try:
                await session.read_state()
                break
            except COMM_ERRORS as err:
                if loop.time() >= deadline or not client.is_connected:
                    raise
                _LOGGER.debug("Radiator not ready: %r", err)
                await asyncio.sleep(PAIR_RETRY_DELAY)
        # Bonding only succeeded on real hardware after the button press. Without
        # a bond the radiator wants the button on every connection, so a failure
        # here must fail setup. An existing bond returns immediately.
        await asyncio.wait_for(client.pair(), PAIR_TIMEOUT)
    finally:
        await client.disconnect()


class AcovaCoordinator(DataUpdateCoordinator[RadiatorState]):
    """Reads and writes the radiator, only when asked.

    update_interval is None on purpose. The radiator runs its schedule by itself, it
    serves one client at a time, and each connection stops scanning, the step seen to
    freeze a Realtek RTL8852BU adapter. Values stay on screen between reads, and the
    last_read sensor shows their age.
    """

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=None,
        )
        self.address: str = entry.unique_id
        self._lock = asyncio.Lock()
        self.last_read: datetime | None = None

    async def _run(
        self, operation: Callable[[AcovaSession], Awaitable[None]] | None
    ) -> RadiatorState:
        """Connect, run the operation if any, read back and disconnect.

        Takes about 3 to 13 seconds on real hardware. The lock queues overlapping
        calls, such as repeated clicks, because the radiator serves one client.
        """
        async with self._lock:
            client = await _connect(self.hass, self.address)
            try:
                session = AcovaSession(client)
                await session.start()
                if operation is not None:
                    await operation(session)
                    await asyncio.sleep(SETTLE_BEFORE_DISCONNECT)
                state = await session.read_state()
                self.last_read = dt_util.utcnow()
                self._remember_comfort(state)
                return state
            finally:
                await client.disconnect()

    def _remember_comfort(self, state: RadiatorState) -> None:
        """Store the comfort setting, which the radiator only reports in comfort.

        Kept in the config entry so it survives restarts. In other modes the
        register holds a different temperature, but comfort keeps its own value
        (verified across pilot wire), so the last value seen in comfort stays valid
        unless the phone app changes it.
        """
        if state.mode != Mode.COMFORT:
            return
        entry = self.config_entry
        if entry.data.get(DATA_COMFORT) != state.comfort_temp:
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, DATA_COMFORT: state.comfort_temp}
            )

    @property
    def program_targets(self) -> tuple[float, float] | None:
        """Return (comfort, eco) used by the weekly program, when it is running."""
        comfort = self.config_entry.data.get(DATA_COMFORT)
        if self.data.mode != Mode.PROGRAM or comfort is None:
            return None
        return comfort, eco_for_comfort(comfort)

    async def _async_update_data(self) -> RadiatorState:
        try:
            return await self._run(None)
        except COMM_ERRORS as err:
            raise UpdateFailed(f"Could not read radiator: {err}") from err

    async def async_refresh_on_demand(self) -> None:
        """Read the radiator now, showing the user any failure."""
        await self.async_refresh()
        if not self.last_update_success:
            raise HomeAssistantError(str(self.last_exception))

    async def _async_command(
        self, operation: Callable[[AcovaSession], Awaitable[None]]
    ) -> RadiatorState:
        try:
            state = await self._run(operation)
        except COMM_ERRORS as err:
            raise HomeAssistantError(f"Could not reach radiator: {err}") from err
        self.async_set_updated_data(state)
        return state

    async def async_set_mode(self, mode: Mode) -> None:
        """Set a mode and verify that the radiator accepted it."""

        async def operation(session: AcovaSession) -> None:
            if mode is Mode.PROGRAM:  # the programme runs from the radiator's clock
                now = dt_util.now()
                await session.set_clock(
                    now.isoweekday(), now.hour, now.minute, now.second
                )
            await session.set_mode(mode)

        state = await self._async_command(operation)
        if state.mode != mode:
            raise HomeAssistantError(
                f"Radiator stayed in mode {state.mode} instead of {int(mode)}"
            )

    @property
    def temperature_in_effect(self) -> float | None:
        """Return the active temperature, or None when it cannot be known."""
        # On entering program the register still held the previous mode's value
        # (7 °C after frost) while the lights showed the schedule running.
        if self.data.mode == Mode.PROGRAM:
            return None
        return self.data.comfort_temp

    async def async_set_comfort_temp(self, temp: float) -> None:
        """Set the comfort setpoint and verify it."""
        # The register holds the temperature in effect, so a write is only
        # unambiguous in comfort. Eco follows comfort minus 3.5 °C, frost is locked
        # at 7 °C, the dial applies in pilot wire, and program can be in an eco hour.
        if self.data.mode != Mode.COMFORT:
            raise ServiceValidationError(
                "The temperature can only be set in comfort mode"
            )
        state = await self._async_command(lambda s: s.set_comfort_temp(temp))
        if state.comfort_temp != temp:
            raise HomeAssistantError(
                f"Radiator kept {state.comfort_temp} °C instead of {temp} °C"
            )

    async def async_sync_schedule(self, days: list[str] | None = None) -> None:
        """Write the Schedule helper to the radiator, comfort hours inside its blocks.

        All days are validated before connecting, so a bad day writes nothing. The
        previous week is logged because the radiator keeps no other copy of it.
        """
        entity_id = self.config_entry.options.get(CONF_SCHEDULE)
        if not entity_id or self.hass.states.get(entity_id) is None:
            raise ServiceValidationError(
                "Choose an existing Schedule helper in the integration's options first"
            )
        response = await self.hass.services.async_call(
            "schedule",
            "get_schedule",
            {"entity_id": entity_id},
            blocking=True,
            return_response=True,
        )
        schedule = response[entity_id]
        wanted: dict[int, bytes] = {}
        for index, day in enumerate(WEEKDAYS):
            if days is not None and day not in days:
                continue
            try:
                wanted[index] = encode_day_plan(
                    comfort_hours_from_blocks(schedule.get(day, []))
                )
            except ValueError as err:
                raise ServiceValidationError(f"{day.capitalize()}: {err}") from err

        async def operation(session: AcovaSession) -> None:
            before = await session.read_week_plan()
            # Compare raw bytes: a never-programmed day is all zeros, which decodes
            # like eco but is not a valid plan, so it has to be written.
            changed = {
                index: plan
                for index, plan in wanted.items()
                if before[index] != plan
            }
            if not changed:
                return
            _LOGGER.warning(
                "Replacing radiator schedule days %s. Previous week: %s",
                [WEEKDAYS[index] for index in changed],
                [plan.hex() for plan in before],
            )
            now = dt_util.now()  # the schedule runs from the radiator's clock
            await session.set_clock(now.isoweekday(), now.hour, now.minute, now.second)
            for index, plan in changed.items():
                await session.write_day_plan(index, plan)
            after = await session.read_week_plan()
            for index, plan in changed.items():
                if decode_day_plan(after[index]) != decode_day_plan(plan):
                    raise AcovaProtocolError(
                        f"{WEEKDAYS[index]} reads back as {after[index].hex()}"
                    )

        await self._async_command(operation)

    async def async_set_window_detection(self, enabled: bool) -> None:
        """Enable or disable open-window detection."""
        control = self.data.window_control
        await self._async_command(lambda s: s.set_window_detection(enabled, control))
