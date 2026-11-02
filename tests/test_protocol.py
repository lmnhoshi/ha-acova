import pytest

from custom_components.acova import protocol as p
from fake_radiator import FakeRadiator


async def session():
    radiator = FakeRadiator()
    s = p.AcovaSession(radiator)
    await s.start()
    return radiator, s


def test_write_frame_layout():
    frame = p.build_write_frame(p.THERMOSTAT_COMFORT, bytes((42,)))
    assert frame == bytes((116, 5, 1, 42)) + bytes(26)


@pytest.mark.parametrize("value,raw", [(7, 14), (21, 42), (21.5, 43), (30, 60)])
def test_encode_temp(value, raw):
    assert p.encode_temp(value) == raw


@pytest.mark.parametrize("value", [6.5, 30.5, 21.2])
def test_encode_temp_rejects(value):
    with pytest.raises(ValueError):
        p.encode_temp(value)


def test_window_control_preserves_other_bits():
    assert p.window_control_value(0b100, True) == 0b101
    assert p.window_control_value(0b101, False) == 0b110


def hours(*ranges):
    flags = [False] * 24
    for start, end in ranges:
        flags[start:end] = [True] * (end - start)
    return flags


def test_day_plan_bytes_match_app_format():
    plan = p.encode_day_plan(hours((6, 8), (18, 22)))
    assert plan == bytes((3, 0, 4, 24, 3, 32, 4, 72, 3, 88)) + bytes(10)


@pytest.mark.parametrize(
    "flags",
    [hours(), hours((0, 24)), hours((0, 7)), hours((23, 24)), hours((6, 8), (18, 22))],
)
def test_day_plan_round_trip(flags):
    assert p.decode_day_plan(p.encode_day_plan(flags)) == flags


def test_day_plan_limit():
    five_blocks = hours((1, 2), (3, 4), (5, 6), (7, 8), (9, 10))
    assert len(p.encode_day_plan(hours((1, 2), (3, 4), (5, 6), (7, 8)))) == 20
    with pytest.raises(ValueError, match="10 changes"):
        p.encode_day_plan(five_blocks)


async def test_read_state_decodes():
    _, s = await session()
    state = await s.read_state()
    assert state.mode == 4
    assert state.comfort_temp == 21
    assert state.eco_temp == 17.5
    assert state.offset == -2.0  # signed byte 0xEC / 10
    assert state.window_detection is True
    assert state.firmware == "2.55"


async def test_long_read_uses_characteristic_read():
    _, s = await session()
    assert await s.read(p.Register(117, 3)) == bytes(range(1, 21))


async def test_write_commits_after_delayed_echo():
    radiator, s = await session()
    radiator.echo_delay = 3
    await s.set_comfort_temp(22.5)
    assert radiator.commits == [(116, 5, [45])]


async def test_write_fails_without_ack():
    radiator, s = await session()
    radiator.echo_delay = 99
    with pytest.raises(p.AcovaProtocolError):
        await s.set_mode(p.Mode.ECO)
    assert radiator.commits == []


async def test_clock_sequence_matches_app():
    radiator, s = await session()
    await s.set_clock(7, 13, 14, 15)
    assert radiator.commits == [
        (115, 2, [1]), (115, 7, [13]), (115, 8, [14]),
        (115, 9, [15]), (115, 3, [7]), (115, 2, [5]),
    ]


async def test_wrong_echo_rejected():
    radiator, s = await session()
    original = radiator.write_gatt_char

    async def wrong(char, data, response=None):
        radiator.callback(None, bytearray((1, 2, 1, 3)))

    radiator.write_gatt_char = wrong
    with pytest.raises(p.AcovaProtocolError):
        await s.read(p.THERMOSTAT_MODE)
    radiator.write_gatt_char = original


async def test_firmware_timeout_tolerated(monkeypatch):
    radiator, s = await session()
    radiator.silent = {p.FW_MINOR}
    real = s.read
    monkeypatch.setattr(
        s, "read", lambda reg, timeout=0.01: real(reg, timeout=0.01)
    )
    assert (await s.read_state()).firmware is None
