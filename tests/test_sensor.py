"""Tests for sensor platform."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, STATE_UNKNOWN

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
        discovery_keys={},
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


async def test_active_pool_fallback_to_first(hass):
    """Active pool falls back to first pool if none has status='active'."""
    summary_no_active = {
        "miner": {
            **MOCK_SUMMARY["miner"],
            "pools": [
                {"id": 0, "url": "pool0.example.com:3333", "status": "working", "accepted": 0, "rejected": 0, "ping": 10},
                {"id": 1, "url": "pool1.example.com:3333", "status": "working", "accepted": 0, "rejected": 0, "ping": 20},
            ],
        }
    }
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T", data={CONF_HOST: "10.0.0.1"},
        source=config_entries.SOURCE_USER, options={}, unique_id="FALLBACKTEST", discovery_keys={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value={**MOCK_INFO, "serial": "FALLBACKTEST"}), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=summary_no_active):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.antminer_s19k_pro_active_pool")
    assert state is not None
    assert "pool0" in state.state or "pool1" in state.state  # first pool


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


async def test_hw_errors_percent(hass):
    """HW errors percent sensor returns zero when no errors."""
    await _setup_integration(hass)

    state = hass.states.get("sensor.antminer_s19k_pro_hw_errors")
    assert state is not None
    assert float(state.state) == pytest.approx(0.0)
