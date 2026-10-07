"""Tests for sensor platform."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er

from custom_components.vnish.const import DOMAIN

from .conftest import MOCK_HOST, MOCK_INFO, MOCK_SUMMARY


async def _setup_integration(hass):
    """Set up vnish integration with mock data and return the config entry."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Miner",
        data={CONF_HOST: MOCK_HOST},
        source=config_entries.SOURCE_USER,
        options={},
        unique_id=MOCK_INFO["serial"],
        discovery_keys={}, subentries_data={},
    )
    with patch(
        "custom_components.vnish.api.VnishApiClient.get_info",
        new_callable=AsyncMock,
        return_value=MOCK_INFO,
    ), patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return entry


async def test_hashrate_rt(hass):
    """Hashrate realtime sensor returns correct value and unit."""
    await _setup_integration(hass)

    state = hass.states.get(f"sensor.antminer_s19k_pro_hashrate_realtime")
    assert state is not None
    assert float(state.state) == pytest.approx(22977.2, rel=1e-3)
    assert state.attributes["unit_of_measurement"] == "GH/s"


async def test_power_consumption(hass):
    """Power sensor returns watts."""
    await _setup_integration(hass)

    state = hass.states.get("sensor.antminer_s19k_pro_power_consumption")
    assert state is not None
    assert state.state == "683"
    assert state.attributes["unit_of_measurement"] == "W"


async def test_pcb_temp_max(hass):
    """PCB temperature max sensor returns correct value."""
    await _setup_integration(hass)

    state = hass.states.get("sensor.antminer_s19k_pro_pcb_temperature_max")
    assert state is not None
    assert state.state == "50"


async def test_chip_temp_min(hass):
    """Chip temperature min sensor returns correct value."""
    await _setup_integration(hass)

    state = hass.states.get("sensor.antminer_s19k_pro_chip_temperature_min")
    assert state is not None
    assert state.state == "58"


async def test_miner_state(hass):
    """Miner state sensor reflects coordinator data."""
    await _setup_integration(hass)

    state = hass.states.get("sensor.antminer_s19k_pro_miner_state")
    assert state is not None
    assert state.state == "mining"


async def test_active_pool_uses_status(hass):
    """Active pool sensor finds pool with status='active', not index 0."""
    await _setup_integration(hass)

    state = hass.states.get("sensor.antminer_s19k_pro_active_pool")
    assert state is not None
    assert state.state == "btc.pool.example.com:3333"


async def test_active_pool_unknown_when_none_active(hass):
    """With no pool marked active the sensor reports unknown, not pools[0].

    Falling back to the first pool used to report an inactive pool's URL and
    share counts as if it were active, which also contradicted the pool select.
    """
    summary_no_active = {
        "miner": {
            **MOCK_SUMMARY["miner"],
            "pools": [
                {"id": 0, "url": "pool0.example.com:3333", "status": "dead", "accepted": 7, "rejected": 0, "ping": 10},
                {"id": 1, "url": "pool1.example.com:3333", "status": "dead", "accepted": 0, "rejected": 0, "ping": 20},
            ],
        }
    }
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T", data={CONF_HOST: "10.0.0.1"},
        source=config_entries.SOURCE_USER, options={}, unique_id="10.0.0.1", discovery_keys={}, subentries_data={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value={**MOCK_INFO, "serial": "FALLBACKTEST"}), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=summary_no_active):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    assert hass.states.get("sensor.antminer_s19k_pro_active_pool").state == STATE_UNKNOWN
    # ...and the per-pool stats must not report the dead pool's numbers either.
    assert hass.states.get("sensor.antminer_s19k_pro_pool_accepted_shares").state == STATE_UNKNOWN


async def test_pool_accepted_shares(hass):
    """Pool accepted shares sensor returns correct count."""
    await _setup_integration(hass)

    state = hass.states.get("sensor.antminer_s19k_pro_pool_accepted_shares")
    assert state is not None
    assert state.state == "3897"


async def test_pool_rejected_shares(hass):
    """Pool rejected shares sensor returns correct count."""
    await _setup_integration(hass)

    state = hass.states.get("sensor.antminer_s19k_pro_pool_rejected_shares")
    assert state is not None
    assert state.state == "14"


async def test_pool_ping(hass):
    """Pool ping sensor returns ms value."""
    await _setup_integration(hass)

    state = hass.states.get("sensor.antminer_s19k_pro_pool_ping")
    assert state is not None
    assert state.state == "51"
    assert state.attributes["unit_of_measurement"] == "ms"


async def test_fan_duty(hass):
    """Fan duty sensor returns percent value."""
    await _setup_integration(hass)

    state = hass.states.get("sensor.antminer_s19k_pro_fan_duty")
    assert state is not None
    assert state.state == "50"


async def test_devfee_pool_is_not_reported_as_active(hass):
    """An active DevFee pool must not steal the active-pool sensors.

    The firmware marks its own pool active alongside the user's. Taking the
    first `status=active` pool reported the devfee URL and its share counts.
    """
    summary = {
        "miner": {
            **MOCK_SUMMARY["miner"],
            "pools": [
                {
                    "id": 0,
                    "url": "devfee.example.com:3333",
                    "pool_type": "DevFee",
                    "status": "active",
                    "accepted": 9,
                    "rejected": 1,
                    "stale": 4,
                    "ping": 3,
                },
                {
                    "id": 1,
                    "url": "btc.pool.example.com:3333",
                    "pool_type": "UserPool",
                    "status": "active",
                    "accepted": 3897,
                    "rejected": 14,
                    "stale": 5,
                    "ping": 51,
                },
            ],
        }
    }
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T", data={CONF_HOST: "10.0.0.1"},
        source=config_entries.SOURCE_USER, options={}, unique_id="10.0.0.1", discovery_keys={}, subentries_data={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value={**MOCK_INFO, "serial": "DEVFEETEST"}), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=summary):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    assert hass.states.get("sensor.antminer_s19k_pro_active_pool").state == "btc.pool.example.com:3333"
    assert hass.states.get("sensor.antminer_s19k_pro_pool_accepted_shares").state == "3897"


async def test_summary_fields_from_the_current_api(hass):
    """Sensors added for fields the current OpenAPI documents on /summary and /info."""
    await _setup_integration(hass)

    assert hass.states.get("sensor.antminer_s19k_pro_hashrate_stock").state == "138364"
    assert hass.states.get("sensor.antminer_s19k_pro_hw_error_count").state == "1"
    assert hass.states.get("sensor.antminer_s19k_pro_time_in_state").state == "3600"
    assert hass.states.get("sensor.antminer_s19k_pro_pool_stale_shares").state == "5"
    assert hass.states.get("sensor.antminer_s19k_pro_uptime").state == "1:00"
    assert hass.states.get("sensor.antminer_s19k_pro_free_memory").state == "59"
    assert hass.states.get("sensor.antminer_s19k_pro_free_memory").attributes["unit_of_measurement"] == "%"


async def test_miner_state_exposes_failure_details(hass):
    """MinerStatus.description and failure_code ride on the state sensor."""
    summary = {
        "miner": {
            **MOCK_SUMMARY["miner"],
            "miner_status": {
                "miner_state": "failure",
                "throttled": 100,
                "miner_state_time": 12,
                "description": "board 0 lost",
                "failure_code": 7,
            },
        }
    }
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T", data={CONF_HOST: "10.0.0.2"},
        source=config_entries.SOURCE_USER, options={}, unique_id="10.0.0.2", discovery_keys={}, subentries_data={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value={**MOCK_INFO, "serial": "FAILTEST"}), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=summary):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.antminer_s19k_pro_miner_state")
    assert state.state == "failure"
    assert state.attributes["description"] == "board 0 lost"
    assert state.attributes["failure_code"] == 7


async def test_hw_errors_percent(hass):
    """HW errors percent sensor returns zero when no errors."""
    await _setup_integration(hass)

    state = hass.states.get("sensor.antminer_s19k_pro_hw_errors")
    assert state is not None
    assert float(state.state) == pytest.approx(0.0)


def _state_by_unique_id(hass, domain: str, unique_id: str):
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return hass.states.get(entity_id)


async def test_fan_and_board_sensors(hass):
    """Per-fan RPM and per-board stats come from Cooling.fans and chains[]."""
    await _setup_integration(hass)

    fan = _state_by_unique_id(hass, "sensor", f"{MOCK_HOST}_fan_0_rpm")
    assert fan.state == "3000"
    assert fan.attributes["unit_of_measurement"] == "rpm"

    board = _state_by_unique_id(hass, "sensor", f"{MOCK_HOST}_chain_0_hashrate")
    assert float(board.state) == pytest.approx(11488.6, rel=1e-3)
    assert board.attributes["unit_of_measurement"] == "GH/s"

    pcb = _state_by_unique_id(hass, "sensor", f"{MOCK_HOST}_chain_0_pcb_temp")
    assert pcb.state == "48"
    state = _state_by_unique_id(hass, "sensor", f"{MOCK_HOST}_chain_0_state")
    assert state.state == "mining"

    fault = _state_by_unique_id(hass, "binary_sensor", f"{MOCK_HOST}_fan_0_fault")
    assert fault.state == "off"


async def test_fan_fault_when_status_is_lost(hass):
    summary = {
        "miner": {
            **MOCK_SUMMARY["miner"],
            "cooling": {
                "fan_duty": 50,
                "fan_num": 1,
                "fans": [{"id": 0, "rpm": 0, "max_rpm": 6000, "status": "lost"}],
            },
        }
    }
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T", data={CONF_HOST: MOCK_HOST},
        source=config_entries.SOURCE_USER, options={}, unique_id=MOCK_HOST, discovery_keys={}, subentries_data={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value=MOCK_INFO), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=summary):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    fault = _state_by_unique_id(hass, "binary_sensor", f"{MOCK_HOST}_fan_0_fault")
    assert fault.state == "on"


async def test_psu_temperatures_appear_when_reported(hass):
    """AntmPsuInfo.temps is nullable; sensors exist only for values the miner sent."""
    summary = {
        "miner": {
            **MOCK_SUMMARY["miner"],
            "psu": {"temps": {"pfc_temp": 42, "llc1_temp": None, "llc2_temp": 40}},
        }
    }
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T", data={CONF_HOST: MOCK_HOST},
        source=config_entries.SOURCE_USER, options={}, unique_id=MOCK_HOST, discovery_keys={}, subentries_data={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value=MOCK_INFO), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=summary):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    pfc = _state_by_unique_id(hass, "sensor", f"{MOCK_HOST}_psu_pfc_temp")
    assert pfc.state == "42"
    llc2 = _state_by_unique_id(hass, "sensor", f"{MOCK_HOST}_psu_llc2_temp")
    assert llc2.state == "40"
    assert er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{MOCK_HOST}_psu_llc1_temp") is None


async def test_fan_sensor_is_added_when_cooling_data_arrives(hass):
    """A miner that was offline at startup grows fan sensors on the first real summary."""
    summary = {"miner": {**MOCK_SUMMARY["miner"], "cooling": {"fan_duty": 0, "fans": []}}}
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T", data={CONF_HOST: MOCK_HOST},
        source=config_entries.SOURCE_USER, options={}, unique_id=MOCK_HOST, discovery_keys={}, subentries_data={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value=MOCK_INFO), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=summary):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    assert er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{MOCK_HOST}_fan_0_rpm") is None

    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(MOCK_SUMMARY)
    await hass.async_block_till_done()

    fan = _state_by_unique_id(hass, "sensor", f"{MOCK_HOST}_fan_0_rpm")
    assert fan.state == "3000"
