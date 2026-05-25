"""Tests for mining switch."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, STATE_OFF, STATE_ON

from custom_components.vnish.const import DOMAIN

from .conftest import MOCK_HOST, MOCK_INFO, MOCK_SUMMARY, MOCK_SUMMARY_STOPPED

SWITCH_ID = "switch.antminer_s19k_pro_mining"


async def _setup(hass, summary=MOCK_SUMMARY):
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T",
        data={CONF_HOST: MOCK_HOST}, source=config_entries.SOURCE_USER,
        options={}, unique_id=MOCK_INFO["serial"], discovery_keys={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value=MOCK_INFO), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=summary):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return entry


async def test_switch_on_when_mining(hass):
    """Switch is ON when miner_state is 'mining'."""
    await _setup(hass)
    state = hass.states.get(SWITCH_ID)
    assert state is not None
    assert state.state == STATE_ON


async def test_switch_off_when_stopped(hass):
    """Switch is OFF when miner_state is 'stopped'."""
    await _setup(hass, MOCK_SUMMARY_STOPPED)
    state = hass.states.get(SWITCH_ID)
    assert state is not None
    assert state.state == STATE_OFF


async def test_turn_off_calls_mining_stop(hass):
    """Turning switch off calls mining_stop API."""
    await _setup(hass)

    with patch(
        "custom_components.vnish.api.VnishApiClient.mining_stop",
        new_callable=AsyncMock,
    ) as mock_stop, patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY_STOPPED,
    ):
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": SWITCH_ID}, blocking=True
        )
        mock_stop.assert_called_once()


async def test_turn_on_calls_mining_start(hass):
    """Turning switch on calls mining_start API."""
    await _setup(hass, MOCK_SUMMARY_STOPPED)

    with patch(
        "custom_components.vnish.api.VnishApiClient.mining_start",
        new_callable=AsyncMock,
    ) as mock_start, patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": SWITCH_ID}, blocking=True
        )
        mock_start.assert_called_once()
