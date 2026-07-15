"""Tests for setup: MAC identity adoption, collision fallback, and migration."""
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vnish.api import VnishApiError
from custom_components.vnish.const import DOMAIN

from .conftest import MOCK_HOST, MOCK_INFO, MOCK_SUMMARY

MOCK_MAC = "02:00:00:00:00:01"  # matches MOCK_INFO system.network_status.mac
OTHER_HOST = "192.168.1.101"


async def _setup(hass, host, info=MOCK_INFO, unique_id=None):
    """Add and set up an entry, returning it."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: host}, unique_id=unique_id or host
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.vnish.api.VnishApiClient.get_info",
        new_callable=AsyncMock,
        return_value=info,
    ), patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_unique_mac_is_adopted_as_identity(hass):
    """A MAC nobody else claims becomes the entry + device identity."""
    entry = await _setup(hass, MOCK_HOST)

    assert entry.unique_id == MOCK_MAC
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, MOCK_MAC)})
    assert device is not None
    assert (CONNECTION_NETWORK_MAC, MOCK_MAC) in device.connections


async def test_cloned_mac_falls_back_to_host(hass):
    """A second miner reporting the SAME MAC must stay a separate device.

    Vnish firmware clones device-reported identifiers (the reason v1.1.1 moved
    off the serial). Adopting a duplicate MAC would merge two physical miners
    into one HA device and lose one of them entirely.
    """
    first = await _setup(hass, MOCK_HOST)
    second = await _setup(hass, OTHER_HOST)

    assert first.unique_id == MOCK_MAC
    # The clone keeps its guaranteed-unique host identity.
    assert second.unique_id == OTHER_HOST

    reg = dr.async_get(hass)
    mac_device = reg.async_get_device(identifiers={(DOMAIN, MOCK_MAC)})
    host_device = reg.async_get_device(identifiers={(DOMAIN, OTHER_HOST)})
    assert mac_device is not None
    assert host_device is not None
    assert mac_device.id != host_device.id  # two distinct devices, no merge
    # Only the entry that actually owns the MAC advertises the connection,
    # otherwise the registry would still fuse them.
    assert (CONNECTION_NETWORK_MAC, MOCK_MAC) not in host_device.connections


async def test_missing_mac_keeps_host_identity(hass):
    """A miner that reports no MAC simply stays keyed by host."""
    info = {**MOCK_INFO, "system": {"network_status": {}}}
    entry = await _setup(hass, MOCK_HOST, info=info)

    assert entry.unique_id == MOCK_HOST
    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, MOCK_HOST)})


async def test_non_string_mac_does_not_abort_setup(hass):
    """A malformed MAC must not take the whole integration down.

    format_mac() raises TypeError on a non-string, which would escape
    async_setup_entry and park the entry in SETUP_ERROR with no retry.
    """
    info = {**MOCK_INFO, "system": {"network_status": {"mac": 112233445566}}}
    entry = await _setup(hass, MOCK_HOST, info=info)

    assert entry.state is entry.state.LOADED
    assert entry.unique_id == MOCK_HOST


async def test_orphan_host_device_is_merged_into_the_mac_device(hass):
    """A leftover host device must be merged away, not linger as a phantom.

    A transient /info failure on a reload can re-create the host-keyed device
    after the MAC was already adopted, stranding entities on the old row.
    """
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: MOCK_HOST}, unique_id=MOCK_MAC
    )
    entry.add_to_hass(hass)
    reg = dr.async_get(hass)
    mac_device = reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, MOCK_MAC)}
    )
    host_device = reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, MOCK_HOST)}
    )
    assert host_device.id != mac_device.id
    stranded = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, "stranded", config_entry=entry, device_id=host_device.id
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
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, MOCK_HOST)}) is None
    # The entity followed the merge instead of pointing at a deleted device.
    assert er.async_get(hass).async_get(stranded.entity_id).device_id == mac_device.id


async def test_device_card_fills_in_after_a_late_info_backfill(hass):
    """A miner offline at startup must not keep a placeholder card all session.

    HA reads device_info only when the entity is added, so the coordinator has
    to refresh the card itself once /info finally answers.
    """
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: MOCK_HOST}, unique_id=MOCK_HOST
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.vnish.api.VnishApiClient.get_info",
        new_callable=AsyncMock,
        side_effect=[VnishApiError("miner offline"), MOCK_INFO],
    ), patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        placeholder = dr.async_get(hass).async_get_device(
            identifiers={(DOMAIN, MOCK_HOST)}
        )
        assert placeholder.model is None  # /info was unavailable at add time

        await hass.data[DOMAIN][entry.entry_id].async_refresh()
        await hass.async_block_till_done()

    card = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, MOCK_HOST)})
    assert card.model == MOCK_INFO["model"]
    assert card.sw_version == MOCK_INFO["fw_version"]


async def test_legacy_host_device_is_rekeyed_to_mac(hass):
    """Upgrading re-keys the existing host-identified device in place.

    Re-keying (rather than creating a new device) is what preserves the user's
    history, customisations and automations.
    """
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: MOCK_HOST}, unique_id=MOCK_HOST
    )
    entry.add_to_hass(hass)
    legacy = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, MOCK_HOST)}
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
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = dr.async_get(hass)
    assert reg.async_get_device(identifiers={(DOMAIN, MOCK_HOST)}) is None
    migrated = reg.async_get_device(identifiers={(DOMAIN, MOCK_MAC)})
    assert migrated is not None
    assert migrated.id == legacy.id  # same device row -> history kept
    assert entry.unique_id == MOCK_MAC
