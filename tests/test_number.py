"""Tests for the throttle number entity."""
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, STATE_UNKNOWN

from custom_components.vnish.const import DOMAIN

from .conftest import MOCK_HOST, MOCK_INFO, MOCK_SUMMARY, MOCK_SUMMARY_STOPPED

NUMBER_ID = "number.antminer_s19k_pro_throttle"


async def _setup(hass, summary=MOCK_SUMMARY):
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T",
        data={CONF_HOST: MOCK_HOST}, source=config_entries.SOURCE_USER,
        options={}, unique_id=MOCK_HOST, discovery_keys={}, subentries_data={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value=MOCK_INFO), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=summary):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return entry


async def test_throttle_reflects_miner_status(hass):
    """MinerStatus.throttled is the slider value, within the documented 20–100."""
    await _setup(hass)
    state = hass.states.get(NUMBER_ID)
    assert state is not None
    assert float(state.state) == 100
    assert state.attributes["min"] == 20
    assert state.attributes["max"] == 100


async def test_throttle_outside_range_is_unknown(hass):
    """A reported throttle below 20 is not a setpoint (stopped mock sends 0)."""
    await _setup(hass, MOCK_SUMMARY_STOPPED)
    assert hass.states.get(NUMBER_ID).state == STATE_UNKNOWN


async def test_set_throttle_calls_the_api(hass):
    await _setup(hass)

    with patch(
        "custom_components.vnish.api.VnishApiClient.mining_throttle",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_throttle, patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": NUMBER_ID, "value": 80},
            blocking=True,
        )
        mock_throttle.assert_called_once_with(80)

    # Optimistic until the miner reports the new percent. The refresh above
    # still says 100, so the slider must keep the value we just sent.
    assert float(hass.states.get(NUMBER_ID).state) == 80
