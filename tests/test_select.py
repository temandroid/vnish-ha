"""Tests for the pool select platform."""
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, STATE_UNKNOWN

from custom_components.vnish.const import DOMAIN, OPTIMISTIC_MAX_CYCLES

from .conftest import MOCK_HOST, MOCK_INFO, MOCK_SUMMARY

SELECT_ID = "select.antminer_s19k_pro_pool"


async def _setup(hass, summary=MOCK_SUMMARY):
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T",
        data={CONF_HOST: MOCK_HOST}, source=config_entries.SOURCE_USER,
        options={}, unique_id=MOCK_HOST, discovery_keys={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value=MOCK_INFO), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=summary):
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
        return_value=True,
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


def _summary_with_pools(pools):
    return {"miner": {**MOCK_SUMMARY["miner"], "pools": pools}}


async def test_pools_sharing_a_url_stay_addressable(hass):
    """A primary/failover pair on one URL must not collapse into one option.

    Keying the dropdown purely by URL made the second pool unreachable and made
    HA complain about duplicate options.
    """
    summary = _summary_with_pools(
        [
            {"id": 0, "url": "btc.pool.example.com:3333", "status": "active", "user": "w1"},
            {"id": 1, "url": "btc.pool.example.com:3333", "status": "working", "user": "w2"},
        ]
    )
    await _setup(hass, summary)

    options = hass.states.get(SELECT_ID).attributes["options"]
    assert len(options) == len(set(options)) == 2

    with patch(
        "custom_components.vnish.api.VnishApiClient.switch_pool",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_switch, patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=summary,
    ):
        # The second pool is reachable precisely because the label is unique.
        target = next(o for o in options if o.endswith("#1)"))
        await hass.services.async_call(
            "select", "select_option", {"entity_id": SELECT_ID, "option": target}, blocking=True
        )
        mock_switch.assert_called_once_with(1)


async def test_pool_without_id_is_not_offered(hass):
    """An id-less pool cannot be switched to, so it must not be selectable.

    Offering it produced a silent no-op: the user thinks they switched pools
    and nothing happened, with no error anywhere.
    """
    summary = _summary_with_pools(
        [
            {"id": 0, "url": "good.example.com:3333", "status": "active"},
            {"url": "no-id.example.com:3333", "status": "working"},
        ]
    )
    await _setup(hass, summary)

    options = hass.states.get(SELECT_ID).attributes["options"]
    assert options == ["good.example.com:3333"]


async def test_select_reports_none_when_no_pool_is_active(hass):
    await _setup(hass, _summary_with_pools([{"id": 0, "url": "p.example.com:3333", "status": "dead"}]))
    assert hass.states.get(SELECT_ID).state == STATE_UNKNOWN


async def test_optimistic_option_gives_up_if_pool_never_activates(hass):
    """Selecting a dead pool must not report it as current forever."""
    summary = _summary_with_pools(
        [
            {"id": 0, "url": "primary.example.com:3333", "status": "active"},
            {"id": 1, "url": "dead.example.com:3333", "status": "dead"},
        ]
    )
    entry = await _setup(hass, summary)
    coordinator = hass.data[DOMAIN][entry.entry_id]

    with patch(
        "custom_components.vnish.api.VnishApiClient.switch_pool",
        new_callable=AsyncMock,
        return_value=True,
    ), patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=summary,  # the dead pool never becomes active
    ):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": SELECT_ID, "option": "dead.example.com:3333"},
            blocking=True,
        )
        await hass.async_block_till_done()
        assert hass.states.get(SELECT_ID).state == "dead.example.com:3333"

        for _ in range(OPTIMISTIC_MAX_CYCLES + 1):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

    assert hass.states.get(SELECT_ID).state == "primary.example.com:3333"
