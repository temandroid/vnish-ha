"""Tests for setup: MAC identity adoption, collision fallback, and migration."""
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, STATE_UNAVAILABLE
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vnish.api import VnishApiError, VnishAuthError
from custom_components.vnish.const import CONF_PASSWORD, DOMAIN

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


# --- a powered-off miner must not break the integration -----------------

OFFLINE = "Cannot connect to host 192.168.254.65:80 ssl:default"


def _offline():
    return VnishApiError(OFFLINE)


async def test_entry_loads_while_the_miner_is_powered_off(hass):
    """Setup must survive an unreachable miner.

    Miners are routinely switched off (tariffs, heat). Refusing to set up drops
    every entity and flags the entry as "needs attention" in the UI.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antminer T21",
        data={CONF_HOST: MOCK_HOST},
        unique_id=MOCK_HOST,
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        side_effect=_offline(),
    ), patch(
        "custom_components.vnish.api.VnishApiClient.get_info",
        new_callable=AsyncMock,
        side_effect=_offline(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    # The device keeps the name it was added with instead of being renamed to
    # the "Vnish Miner" placeholder just because /info was unreachable.
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, MOCK_HOST)})
    assert device is not None
    assert device.name == "Antminer T21"
    # Entities exist, and honestly report that the miner is not answering.
    state = hass.states.get("sensor.antminer_t21_hashrate_realtime")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_password_auth_does_not_eager_login_at_setup(hass):
    """Reproduces the reported failure.

    The eager login aborted setup with
    "Connection error for /unlock: Cannot connect to host ...".
    Authentication is lazy now: the first request logs in when needed.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antminer T21",
        data={CONF_HOST: MOCK_HOST, CONF_PASSWORD: "secret"},
        unique_id=MOCK_HOST,
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.vnish.api.VnishApiClient.login", new_callable=AsyncMock
    ) as mock_login, patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        side_effect=_offline(),
    ), patch(
        "custom_components.vnish.api.VnishApiClient.get_info",
        new_callable=AsyncMock,
        side_effect=_offline(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        mock_login.assert_not_called()

    assert entry.state is ConfigEntryState.LOADED


async def test_offline_restart_does_not_create_a_duplicate_device(hass):
    """Restarting while the miner is off must not register a second device.

    device_id was recomputed from /info on every setup; with the miner offline
    the MAC is unknown, so it fell back to the host and HA created a second
    device beside the MAC-keyed one that holds the user's history.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antminer T21",
        data={CONF_HOST: MOCK_HOST},
        unique_id=MOCK_HOST,
    )
    entry.add_to_hass(hass)
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

    assert entry.unique_id == MOCK_MAC
    reg = dr.async_get(hass)
    assert len(dr.async_entries_for_config_entry(reg, entry.entry_id)) == 1

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        side_effect=_offline(),
    ), patch(
        "custom_components.vnish.api.VnishApiClient.get_info",
        new_callable=AsyncMock,
        side_effect=_offline(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = dr.async_get(hass)
    assert len(dr.async_entries_for_config_entry(reg, entry.entry_id)) == 1
    assert reg.async_get_device(identifiers={(DOMAIN, MOCK_MAC)}) is not None
    assert reg.async_get_device(identifiers={(DOMAIN, MOCK_HOST)}) is None


async def test_bad_credentials_still_trigger_reauth(hass):
    """Removing the eager login must not lose the reauth trigger.

    The eager login used to raise ConfigEntryAuthFailed directly; now the
    coordinator raises it from the first refresh and HA starts the flow.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Antminer T21",
        data={CONF_HOST: MOCK_HOST, CONF_PASSWORD: "wrong"},
        unique_id=MOCK_HOST,
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        side_effect=VnishAuthError("Authentication failed (HTTP 401)", status=401),
    ), patch(
        "custom_components.vnish.api.VnishApiClient.get_info",
        new_callable=AsyncMock,
        side_effect=VnishAuthError("Authentication failed (HTTP 401)", status=401),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    flows = [
        f
        for f in hass.config_entries.flow.async_progress()
        if f["handler"] == DOMAIN and f["context"].get("source") == "reauth"
    ]
    assert flows, "a bad password must prompt the user to re-authenticate"
