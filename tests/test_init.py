from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.ev_load_controller.const import (
    CONF_CHARGER, CONF_CONNECTOR_STATUS, CONF_DLM, CONF_GRID, CONF_PRICE, DOMAIN, EVENT_DECISION,
)

DLM = ["sensor.dlm_l1", "sensor.dlm_l2", "sensor.dlm_l3"]
GRID = ["sensor.grid_l1", "sensor.grid_l2", "sensor.grid_l3"]
CHARGER = ["sensor.chg_l1", "sensor.chg_l2", "sensor.chg_l3"]
DATA = {CONF_DLM: DLM, CONF_GRID: GRID, CONF_CHARGER: CHARGER,
        CONF_CONNECTOR_STATUS: "sensor.connector", CONF_PRICE: "sensor.price"}

LIMIT = "sensor.ev_load_controller_current_limit"


def _set_inputs(hass, dlm=(14, 10, 14), charger=(10.9, 0, 0), status="Charging", logged_at=None):
    logged_at = (logged_at or dt_util.utcnow()).isoformat()
    for entity_id, value in zip(DLM, dlm):
        hass.states.async_set(entity_id, str(value), {"logged_at": logged_at})
    for entity_id, value in zip(GRID, (13.4, 5.6, 2.5)):
        hass.states.async_set(entity_id, str(value))
    for entity_id, value in zip(CHARGER, charger):
        hass.states.async_set(entity_id, str(value))
    hass.states.async_set("sensor.connector", status)
    hass.states.async_set("sensor.price", "2.6")


async def _setup(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, title="EV load controller")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_and_decision(hass: HomeAssistant):
    _set_inputs(hass)
    events = []
    hass.bus.async_listen(EVENT_DECISION, lambda e: events.append(e))
    await _setup(hass)

    state = hass.states.get(LIMIT)
    assert state.state == "14"
    assert state.attributes["limiting_phase"] == "L1"
    assert hass.states.get("sensor.ev_load_controller_active_phases").state == "L1"
    assert hass.states.get("sensor.ev_load_controller_availability").state == "operative"
    assert hass.states.get("number.ev_load_controller_main_fuse").state == "20"
    assert events and events[0].data["limit"] == 14


async def test_reacts_to_input_and_settings(hass: HomeAssistant):
    _set_inputs(hass)
    await _setup(hass)

    _set_inputs(hass, dlm=(8, 10, 14))
    await hass.async_block_till_done()
    assert hass.states.get(LIMIT).state == "8"

    await hass.services.async_call("select", "select_option", {
        "entity_id": "select.ev_load_controller_charger_access", "option": "locked"}, blocking=True)
    assert hass.states.get(LIMIT).state == "0"
    assert hass.states.get("sensor.ev_load_controller_availability").state == "inoperative_stop"


async def test_stale_data_detected_by_interval(hass: HomeAssistant, freezer):
    _set_inputs(hass)
    await _setup(hass)
    freezer.tick(timedelta(seconds=120))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(LIMIT)
    assert state.state == "6"
    assert state.attributes["source"] == "fallback_min"


async def test_unload(hass: HomeAssistant):
    _set_inputs(hass)
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_config_flow(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    user_input = {f"{g}_l{i}": f"sensor.{g}_{i}" for g in (CONF_DLM, CONF_GRID, CONF_CHARGER) for i in (1, 2, 3)}
    user_input[CONF_CONNECTOR_STATUS] = "sensor.connector"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DLM] == [f"sensor.{CONF_DLM}_{i}" for i in (1, 2, 3)]
    assert CONF_PRICE not in result["data"]
