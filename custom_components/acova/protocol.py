"""Acova Control BLE protocol, worked out from the ACOVA Control 3.4.1 Android app.

The radiator exposes numbered registers, addressed as (object id, data id), through
two vendor GATT characteristics. docs/PROTOCOL.md describes the format in full.

No Home Assistant imports here, so probe.py can use this file on its own.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, NamedTuple

# COMMAND carries read requests and write commits. DATA carries values both ways.
CHAR_COMMAND = "350a1b80-cf4b-11e1-ac36-0002a5d5c51b"  # service ...9ab4
CHAR_DATA = "350a1b80-cf4b-11e1-ac37-0002a5d5c51b"  # service ...9ab5
DEVICE_NAME_MARKER = "TEMPO 3"  # the app lists only devices with this in their name

OP_READ = 0
OP_COMMIT = 1
WRITE_FRAME_SIZE = 30
MAX_NOTIFY_PAYLOAD = 17  # longer values must be read from DATA after the notification
# The app retries reads 10 times with no delay. That was too short here for at least
# one clock write, so this allows about 5 seconds.
ACK_POLL_ATTEMPTS = 20
ACK_POLL_DELAY = 0.25
READ_TIMEOUT = 8.0  # same as the app

# Limits of the app's temperature control.
MIN_TEMP = 7.0
MAX_TEMP = 30.0
TEMP_STEP = 0.5
# Verified: comfort 20 °C gave eco 16.5 °C, and comfort 24 °C gave eco 19 °C.
ECO_OFFSET = 3.5
ECO_MIN = 7.0  # from the app's text, not tested
ECO_MAX = 19.0


def eco_for_comfort(comfort: float) -> float:
    """Return the eco temperature the radiator derives from a comfort setting."""
    return min(max(comfort - ECO_OFFSET, ECO_MIN), ECO_MAX)


class Register(NamedTuple):
    """Address of a value on the radiator."""

    object_id: int
    data_id: int


FW_MINOR = Register(100, 1)
FW_MAJOR = Register(100, 2)
WINDOW_STATUS = Register(113, 1)
WINDOW_CONTROL = Register(113, 2)
CALENDAR_CONTROL = Register(115, 2)
CALENDAR_WEEKDAY = Register(115, 3)
CALENDAR_HOUR = Register(115, 7)
CALENDAR_MINUTE = Register(115, 8)
CALENDAR_SECOND = Register(115, 9)
THERMOSTAT_MODE = Register(116, 3)
THERMOSTAT_ECO = Register(116, 4)
# Writing sets the comfort temperature. Reading returns the temperature in effect:
# comfort minus 3.5 °C in eco, 7 °C in frost, the dial's value in pilot wire.
THERMOSTAT_COMFORT = Register(116, 5)
THERMOSTAT_OFFSET = Register(116, 6)

WEEK_PLAN_DAYS = tuple(Register(117, data_id) for data_id in range(3, 10))  # Monday first
DAY_PLAN_SIZE = 20
MAX_DAY_CHANGES = 9  # the plan holds the 00:00 mode plus nine changes

# Calendar control bits: 0 locks the time registers, 2 applies them as the new clock.
CALENDAR_LOCK = 0b001
CALENDAR_LOCK_AND_SET = 0b101


class Mode(IntEnum):
    """Thermostat mode values."""

    # Never sent: it cuts Bluetooth until the radiator's physical button is pressed.
    STANDBY = 1
    FROST = 2
    ECO = 3
    COMFORT = 4
    PROGRAM = 8  # weekly programme stored on the radiator
    PILOT_WIRE = 9  # "Auto" in the app: the dial sets the temperature


class AcovaProtocolError(Exception):
    """The radiator returned something the protocol does not allow."""


@dataclass(slots=True)
class RadiatorState:
    """Values read from the radiator.

    comfort_temp comes from register 116/5, so it is the temperature in effect
    rather than always the comfort setting. See THERMOSTAT_COMFORT.
    """

    mode: int
    comfort_temp: float
    eco_temp: float
    offset: float
    window_detection: bool
    window_control: int
    firmware: str | None = None


def encode_temp(temp: float) -> int:
    """Encode a setpoint in half degrees, rejecting what the app cannot send."""
    raw = temp * 2
    if not MIN_TEMP <= temp <= MAX_TEMP or raw != int(raw):
        raise ValueError(f"Temperature must be {MIN_TEMP}-{MAX_TEMP} in 0.5 steps: {temp}")
    return int(raw)


def window_control_value(current: int, enabled: bool) -> int:
    """Return the control byte: bit 0 enables detection, bit 1 disables it."""
    return (current & ~0b11) | (0b01 if enabled else 0b10)


def encode_day_plan(comfort_hours: list[bool]) -> bytes:
    """Encode 24 comfort flags as <mode at 00:00> 00, then <mode> <hour*4> per change."""
    changes = [
        hour for hour in range(1, 24) if comfort_hours[hour] != comfort_hours[hour - 1]
    ]
    if len(changes) > MAX_DAY_CHANGES:
        raise ValueError(f"{len(changes)} changes, the radiator allows {MAX_DAY_CHANGES}")
    plan = bytearray(DAY_PLAN_SIZE)
    plan[0] = Mode.COMFORT if comfort_hours[0] else Mode.ECO
    for index, hour in enumerate(changes, start=1):
        plan[index * 2] = Mode.COMFORT if comfort_hours[hour] else Mode.ECO
        plan[index * 2 + 1] = hour * 4
    return bytes(plan)


def decode_day_plan(plan: bytes) -> list[bool]:
    """Decode a day plan into 24 comfort flags, following the app's logic."""
    plan = plan.ljust(DAY_PLAN_SIZE, b"\x00")
    hours = [False] * 24
    comfort = plan[0] == Mode.COMFORT
    start = plan[1] // 4
    for index in range(2, DAY_PLAN_SIZE, 2):
        quarter = plan[index + 1]
        if quarter == 0 or quarter % 4:
            break
        hour = min(quarter // 4, 24)
        hours[start:hour] = [comfort] * (hour - start)
        comfort, start = plan[index] == Mode.COMFORT, hour
    hours[start:] = [comfort] * (24 - start)
    return hours


def build_write_frame(register: Register, payload: bytes) -> bytes:
    """Build the fixed 30-byte frame [object, data, length, payload, zeros]."""
    if len(payload) > WRITE_FRAME_SIZE - 3:
        raise ValueError("Payload too long")
    frame = bytes((register.object_id, register.data_id, len(payload))) + payload
    return frame.ljust(WRITE_FRAME_SIZE, b"\x00")


class AcovaSession:
    """Register access over a connected BLE client, one operation at a time."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._pending: asyncio.Future[bytes] | None = None

    async def start(self) -> None:
        """Subscribe to read responses."""
        await self._client.start_notify(CHAR_DATA, self._on_notify)

    def _on_notify(self, _sender: Any, data: bytearray) -> None:
        if self._pending is not None and not self._pending.done():
            self._pending.set_result(bytes(data))

    async def read(self, register: Register, timeout: float = READ_TIMEOUT) -> bytes:
        """Request a register and return its payload."""
        self._pending = asyncio.get_running_loop().create_future()
        try:
            await self._client.write_gatt_char(
                CHAR_COMMAND,
                bytes((OP_READ, register.object_id, register.data_id)),
                response=True,
            )
            frame = await asyncio.wait_for(self._pending, timeout)
        finally:
            self._pending = None
        self._check_echo(frame, register)
        if frame[2] > MAX_NOTIFY_PAYLOAD:  # notification was truncated
            frame = bytes(await self._client.read_gatt_char(CHAR_DATA))
            self._check_echo(frame, register)
        length = frame[2]
        if len(frame) < 3 + length:
            raise AcovaProtocolError(f"Short frame for {register}: {frame.hex()}")
        return frame[3 : 3 + length]

    async def write(self, register: Register, payload: bytes) -> None:
        """Write a register using the app's write, echo, commit, ack exchange."""
        await self._client.write_gatt_char(
            CHAR_DATA, build_write_frame(register, payload), response=True
        )
        await self._await_data_prefix(register.object_id, register.data_id)
        await self._client.write_gatt_char(
            CHAR_COMMAND,
            bytes((OP_COMMIT, register.object_id, register.data_id)),
            response=True,
        )
        await self._await_data_prefix(0, 0)

    async def _await_data_prefix(self, first: int, second: int) -> None:
        last = b""
        for _ in range(ACK_POLL_ATTEMPTS):
            last = bytes(await self._client.read_gatt_char(CHAR_DATA))
            if last[:2] == bytes((first, second)):
                return
            await asyncio.sleep(ACK_POLL_DELAY)
        raise AcovaProtocolError(f"Expected ack {first},{second}, last got {last.hex()}")

    @staticmethod
    def _check_echo(frame: bytes, register: Register) -> None:
        if len(frame) < 3 or (frame[0], frame[1]) != register:
            raise AcovaProtocolError(f"Unexpected frame for {register}: {frame.hex()}")

    async def _read_byte(self, register: Register) -> int:
        payload = await self.read(register)
        if not payload:
            raise AcovaProtocolError(f"Empty payload for {register}")
        return payload[0]

    async def read_state(self) -> RadiatorState:
        """Read everything the integration exposes."""
        status = await self._read_byte(WINDOW_STATUS)
        control = await self._read_byte(WINDOW_CONTROL)
        mode = await self._read_byte(THERMOSTAT_MODE)
        eco = await self._read_byte(THERMOSTAT_ECO)
        comfort = await self._read_byte(THERMOSTAT_COMFORT)
        raw_offset = await self._read_byte(THERMOSTAT_OFFSET)
        offset = raw_offset - 256 if raw_offset > 127 else raw_offset
        firmware = None
        try:  # the app also tolerates a timeout on these two
            minor = await self._read_byte(FW_MINOR)
            major = await self._read_byte(FW_MAJOR)
            firmware = f"{major}.{minor}"
        except TimeoutError:
            pass
        return RadiatorState(
            mode=mode,
            comfort_temp=comfort * 0.5,
            eco_temp=eco * 0.5,
            offset=offset / 10,
            window_detection=bool(status & 1),
            window_control=control,
            firmware=firmware,
        )

    async def read_week_plan(self) -> list[bytes]:
        """Read the seven raw day plans, Monday first."""
        return [await self.read(register) for register in WEEK_PLAN_DAYS]

    async def write_day_plan(self, day: int, plan: bytes) -> None:
        """Write one raw day plan; day 0 is Monday."""
        await self.write(WEEK_PLAN_DAYS[day], plan)

    async def set_mode(self, mode: Mode) -> None:
        """Set the thermostat mode."""
        await self.write(THERMOSTAT_MODE, bytes((int(mode),)))

    async def set_comfort_temp(self, temp: float) -> None:
        """Set the comfort setpoint."""
        await self.write(THERMOSTAT_COMFORT, bytes((encode_temp(temp),)))

    async def set_window_detection(self, enabled: bool, current_control: int) -> None:
        """Enable or disable open-window detection."""
        value = window_control_value(current_control, enabled)
        await self.write(WINDOW_CONTROL, bytes((value,)))

    async def set_clock(self, weekday: int, hour: int, minute: int, second: int) -> None:
        """Set the radiator clock; weekday runs from 1 (Monday) to 7 (Sunday)."""
        await self.write(CALENDAR_CONTROL, bytes((CALENDAR_LOCK,)))
        await self.write(CALENDAR_HOUR, bytes((hour,)))
        await self.write(CALENDAR_MINUTE, bytes((minute,)))
        await self.write(CALENDAR_SECOND, bytes((second,)))
        await self.write(CALENDAR_WEEKDAY, bytes((weekday,)))
        await self.write(CALENDAR_CONTROL, bytes((CALENDAR_LOCK_AND_SET,)))
