from unittest.mock import MagicMock, patch

from bleak.exc import BleakError
import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.acova.const import DOMAIN
from fake_radiator import FakeRadiator

ADDRESS = "AA:BB:CC:DD:EE:FF"
ENTITY = "climate.tempo_3"
SWITCH = "switch.tempo_3_open_window_detection"
MODE = "select.tempo_3_mode"
TEMP = "number.tempo_3_temperature"
SYNC = "button.tempo_3_sync_schedule_to_radiator"
REFRESH = "button.tempo_3_refresh_from_radiator"
LAST_READ = "sensor.tempo_3_last_read"
C = "custom_components.acova.coordinator"


@pytest.fixture
def radiator():
    fake = FakeRadiator()

    async def connect(*args, **kwargs):
        return fake

    with (
        patch(f"{C}.establish_connection", connect),
        patch(f"{C}.bluetooth.async_ble_device_from_address", return_value=MagicMock(name="d")),
        patch(f"{C}.SETTLE_BEFORE_DISCONNECT", 0),
    ):
        yield fake


@pytest.fixture
async def setup(hass, radiator):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, title="TEMPO 3")
    entry.add_to_hass(hass)
    with patch("homeassistant.components.bluetooth.async_setup", return_value=True), patch(
        "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
    ), patch("homeassistant.setup.async_process_deps_reqs", return_value=None):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
    await hass.async_block_till_done()
    return entry


async def call(hass, domain, service, **data):
    await hass.services.async_call(domain, service, data, blocking=True)
    await hass.async_block_till_done()


async def test_state(hass, setup):
    state = hass.states.get(ENTITY)
    assert state.state == "heat"
    assert state.attributes["preset_mode"] == "comfort"
    assert state.attributes["temperature"] == 21
    assert state.attributes["eco_temperature"] == 17.5
    assert hass.states.get(SWITCH).state == "on"


async def test_preset_and_hvac(hass, setup, radiator):
    await call(hass, "climate", "set_preset_mode", entity_id=ENTITY, preset_mode="eco")
    assert radiator.commits[-1] == (116, 3, [3])
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "eco"
    await call(hass, "climate", "set_hvac_mode", entity_id=ENTITY, hvac_mode="off")
    assert radiator.commits[-1] == (116, 3, [2])  # frost, never standby
    assert hass.states.get(ENTITY).state == "off"
    assert radiator.disconnected


async def test_program_syncs_clock_first(hass, setup, radiator):
    await call(hass, "climate", "set_hvac_mode", entity_id=ENTITY, hvac_mode="auto")
    assert [c[:2] for c in radiator.commits] == [
        (115, 2), (115, 7), (115, 8), (115, 9), (115, 3), (115, 2), (116, 3),
    ]
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "program"


async def test_temperature(hass, setup, radiator):
    await call(hass, "climate", "set_temperature", entity_id=ENTITY, temperature=23.5)
    assert radiator.commits == [(116, 5, [47])]
    assert hass.states.get(ENTITY).attributes["temperature"] == 23.5


@pytest.mark.parametrize("mode", [3, 2, 9, 8])
async def test_temperature_blocked_where_app_blocks_it(hass, setup, radiator, mode):
    radiator.registers[(116, 3)] = [mode]
    await setup.runtime_data.async_refresh()
    with pytest.raises(ServiceValidationError):
        await call(hass, "climate", "set_temperature", entity_id=ENTITY, temperature=22)
    assert radiator.commits == []


async def test_program_hides_stale_temperature(hass, setup, radiator):
    await call(hass, "climate", "set_hvac_mode", entity_id=ENTITY, hvac_mode="auto")
    assert hass.states.get(ENTITY).attributes["temperature"] is None


async def test_select_lists_all_modes_and_sets_them(hass, setup, radiator):
    state = hass.states.get(MODE)
    assert state.state == "comfort"
    assert state.attributes["options"] == [
        "comfort", "eco", "frost_protection", "program", "pilot_wire",
    ]
    await call(hass, "select", "select_option", entity_id=MODE, option="eco")
    assert radiator.commits[-1] == (116, 3, [3])
    assert hass.states.get(MODE).state == "eco"
    assert hass.states.get(ENTITY).attributes["preset_mode"] == "eco"


async def test_number_sets_comfort_only(hass, setup, radiator):
    assert hass.states.get(TEMP).state == "21.0"
    await call(hass, "number", "set_value", entity_id=TEMP, value=20)
    assert radiator.commits[-1] == (116, 5, [40])
    await call(hass, "select", "select_option", entity_id=MODE, option="eco")
    count = len(radiator.commits)
    with pytest.raises(ServiceValidationError):
        await call(hass, "number", "set_value", entity_id=TEMP, value=22)
    assert len(radiator.commits) == count


async def test_number_unknown_in_program(hass, setup):
    await call(hass, "select", "select_option", entity_id=MODE, option="program")
    assert hass.states.get(TEMP).state == "unknown"


@pytest.fixture
def expected_lingering_timers():
    return True  # the real Schedule helper keeps a timer for its next change


@pytest.fixture
async def schedule(hass):
    assert await async_setup_component(
        hass,
        "schedule",
        {
            "schedule": {
                "bath": {
                    "name": "Bath",
                    "monday": [
                        {"from": "06:30:00", "to": "08:00:00"},
                        {"from": "22:00:00", "to": "24:00:00"},
                    ],
                }
            }
        },
    )
    await hass.async_block_till_done()
    return "schedule.bath"


def use_schedule(hass, entry, entity_id):
    hass.config_entries.async_update_entry(entry, options={"schedule_entity": entity_id})


MONDAY = [3, 0, 4, 24, 3, 32, 4, 88] + [0] * 12
EMPTY_DAY = [3] + [0] * 19


async def test_sync_writes_widened_hours_and_clock(hass, setup, radiator, schedule, caplog):
    use_schedule(hass, setup, schedule)
    await call(hass, "button", "press", entity_id=SYNC)
    writes = [c for c in radiator.commits if c[0] == 117]
    assert writes[0] == (117, 3, MONDAY)
    assert (117, 4, EMPTY_DAY) not in writes  # already eco all day, so left alone
    assert radiator.commits[0][:2] == (115, 2)
    assert "Previous week" in caplog.text


async def test_sync_can_be_limited_to_days(hass, setup, radiator, schedule):
    use_schedule(hass, setup, schedule)
    await call(hass, DOMAIN, "sync_schedule", days=["tuesday"])
    assert radiator.commits == []
    await call(hass, DOMAIN, "sync_schedule", days=["monday"])
    assert [c for c in radiator.commits if c[0] == 117] == [(117, 3, MONDAY)]


async def test_sync_replaces_never_programmed_days(hass, setup, radiator, schedule):
    radiator.registers[(117, 4)] = [0] * 20
    use_schedule(hass, setup, schedule)
    await call(hass, "button", "press", entity_id=SYNC)
    assert (117, 4, EMPTY_DAY) in radiator.commits


async def test_second_sync_changes_nothing(hass, setup, radiator, schedule):
    use_schedule(hass, setup, schedule)
    await call(hass, "button", "press", entity_id=SYNC)
    radiator.commits.clear()
    await call(hass, "button", "press", entity_id=SYNC)
    assert radiator.commits == []


async def test_sync_rejects_too_many_changes_before_writing(hass, setup, radiator):
    blocks = [{"from": f"{h:02}:00:00", "to": f"{h + 1:02}:00:00"} for h in range(1, 20, 2)]
    assert await async_setup_component(
        hass, "schedule", {"schedule": {"busy": {"name": "Busy", "friday": blocks}}}
    )
    await hass.async_block_till_done()
    use_schedule(hass, setup, "schedule.busy")
    with pytest.raises(ServiceValidationError, match="Friday"):
        await call(hass, "button", "press", entity_id=SYNC)
    assert radiator.commits == []


async def test_sync_requires_helper(hass, setup, radiator):
    with pytest.raises(ServiceValidationError, match="Schedule helper"):
        await call(hass, "button", "press", entity_id=SYNC)


async def test_sync_detects_failed_write(hass, setup, radiator, schedule):
    use_schedule(hass, setup, schedule)
    radiator.reject.add((117, 3))
    with pytest.raises(HomeAssistantError, match="monday reads back"):
        await call(hass, "button", "press", entity_id=SYNC)


async def test_options_flow(hass, setup, schedule):
    result = await hass.config_entries.options.async_init(setup.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"schedule_entity": schedule}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup.options == {"schedule_entity": schedule}


async def test_no_polling(hass, setup):
    assert setup.runtime_data.update_interval is None


async def test_refresh_button_reads_radiator(hass, setup, radiator):
    radiator.registers[(116, 5)] = [40]
    await call(hass, "button", "press", entity_id=REFRESH)
    assert hass.states.get(TEMP).state == "20.0"


async def test_failed_refresh_keeps_values_and_reports(hass, setup):
    before = hass.states.get(LAST_READ).state
    assert before not in ("unknown", "unavailable")
    with patch(f"{C}.establish_connection", side_effect=BleakError("gone")):
        with pytest.raises(HomeAssistantError, match="gone"):
            await call(hass, "button", "press", entity_id=REFRESH)
    assert hass.states.get(TEMP).state == "21.0"
    assert hass.states.get(ENTITY).state == "heat"
    assert hass.states.get(LAST_READ).state == before


COMFORT_T = "sensor.tempo_3_auto_comfort_target"
ECO_T = "sensor.tempo_3_auto_eco_target"


async def test_program_targets_shown_only_in_program(hass, setup, radiator):
    assert hass.states.get(COMFORT_T).state == "unknown"  # in comfort, not program
    await call(hass, "select", "select_option", entity_id=MODE, option="program")
    assert hass.states.get(COMFORT_T).state == "21.0"  # remembered from comfort
    assert hass.states.get(ECO_T).state == "17.5"
    await call(hass, "select", "select_option", entity_id=MODE, option="eco")
    assert hass.states.get(ECO_T).state == "unknown"


async def test_program_targets_follow_new_comfort_and_persist(hass, setup, radiator):
    await call(hass, "number", "set_value", entity_id=TEMP, value=24)
    assert setup.data["comfort_setting"] == 24
    await call(hass, "select", "select_option", entity_id=MODE, option="program")
    assert hass.states.get(COMFORT_T).state == "24.0"
    assert hass.states.get(ECO_T).state == "19.0"  # capped, per the app's text


async def test_program_targets_unknown_until_comfort_seen(hass, radiator):
    radiator.registers[(116, 3)] = [8]
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, title="TEMPO 3")
    entry.add_to_hass(hass)
    with patch("homeassistant.components.bluetooth.async_setup", return_value=True), patch(
        "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
    ), patch("homeassistant.setup.async_process_deps_reqs", return_value=None):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
    assert hass.states.get(COMFORT_T).state == "unknown"


async def test_rejected_mode_is_reported(hass, setup, radiator):
    radiator.reject.add((116, 3))
    with pytest.raises(HomeAssistantError, match="stayed in mode"):
        await call(hass, "climate", "set_hvac_mode", entity_id=ENTITY, hvac_mode="off")
    assert hass.states.get(ENTITY).state == "heat"


async def test_window_switch(hass, setup, radiator):
    await call(hass, "switch", "turn_off", entity_id=SWITCH)
    assert radiator.commits == [(113, 2, [2])]


async def test_connection_error_is_surfaced(hass, setup):
    with patch(f"{C}.establish_connection", side_effect=BleakError("gone")):
        with pytest.raises(HomeAssistantError, match="Could not reach"):
            await call(hass, "climate", "set_temperature", entity_id=ENTITY, temperature=20)


async def test_unload(hass, setup):
    assert await hass.config_entries.async_unload(setup.entry_id)


async def _start_flow(hass):
    info = MagicMock(address=ADDRESS)
    info.name = "TEMPO 3"
    with patch(
        "custom_components.acova.config_flow.bluetooth.async_discovered_service_info",
        return_value=[info],
    ), patch("homeassistant.setup.async_process_deps_reqs", return_value=None), patch(
        "homeassistant.components.bluetooth.async_setup", return_value=True
    ), patch("homeassistant.components.bluetooth_adapters.async_setup", return_value=True):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        assert result["step_id"] == "user"
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {"address": ADDRESS}
        )


async def _submit_pair(hass, result):
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    await hass.async_block_till_done()
    return await hass.config_entries.flow.async_configure(result["flow_id"])


async def test_flow_pairs_and_creates_entry(hass, radiator):
    result = await _start_flow(hass)
    assert result["step_id"] == "confirm"
    result = await _submit_pair(hass, result)
    assert radiator.paired and radiator.disconnected
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "TEMPO 3"
    assert result["result"].unique_id == ADDRESS


async def test_flow_fails_when_bond_cannot_be_made(hass, radiator):
    radiator.pair_error = BleakError("Authentication Failed")
    result = await _start_flow(hass)
    result = await _submit_pair(hass, result)
    assert result["errors"] == {"base": "pairing_failed"}
    assert radiator.disconnected


async def test_flow_failure_allows_retry(hass, radiator):
    result = await _start_flow(hass)
    with patch(
        "custom_components.acova.config_flow.async_pair", side_effect=BleakError("no")
    ):
        result = await _submit_pair(hass, result)
    assert result["step_id"] == "confirm"
    assert result["errors"] == {"base": "pairing_failed"}
    result = await _submit_pair(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
