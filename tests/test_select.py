"""Tests for the pool select platform."""
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST

from custom_components.vnish.const import DOMAIN

from .conftest import MOCK_HOST, MOCK_INFO, MOCK_SUMMARY

SELECT_ID = "select.antminer_s19k_pro_pool"


async def _setup(hass):
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T",
        data={CONF_HOST: MOCK_HOST}, source=config_entries.SOURCE_USER,
        options={}, unique_id=MOCK_HOST, discovery_keys={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value=MOCK_INFO), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=MOCK_SUMMARY):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return entry


async def test_select_reflects_active_pool(hass):
    """current_option equals the pool with status='active'."""
    await _setup(hass)
    state = hass.states.get(SELECT_ID)
    assert state is not None
    assert state.state == "btc.pool.example.com:3333"
    assert "btc.backup.example.com:3333" in state.attributes["options"]


async def test_select_option_calls_switch_pool(hass):
    """Selecting a pool calls switch_pool with that pool's id."""
    await _setup(hass)

    with patch(
        "custom_components.vnish.api.VnishApiClient.switch_pool",
        new_callable=AsyncMock,
    ) as mock_switch, patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": SELECT_ID, "option": "btc.backup.example.com:3333"},
            blocking=True,
        )
        mock_switch.assert_called_once_with(1)
