from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VnishApiClient
from .const import CONF_API_KEY, CONF_PASSWORD, DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import VnishCoordinator, mac_from_info


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    # Use .get(key, fallback) so that an empty string in options ("key cleared")
    # does NOT fall through to the original value in entry.data.
    api_key = entry.options.get(CONF_API_KEY, entry.data.get(CONF_API_KEY)) or None
    password = entry.options.get(CONF_PASSWORD, entry.data.get(CONF_PASSWORD)) or None
    host = entry.data[CONF_HOST]
    client = VnishApiClient(
        host=host,
        api_key=api_key,
        password=password,
        session=session,
    )

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = VnishCoordinator(
        hass, client, scan_interval, fallback_name=entry.title
    )

    # An identity adopted on an earlier run survives a restart in entry.unique_id.
    # Reuse it even while the miner is unreachable: recomputing it from an empty
    # /info would fall back to the host and register a SECOND, duplicate device
    # alongside the MAC-keyed one that already holds the user's history.
    if entry.unique_id and entry.unique_id != host:
        coordinator.device_id = entry.unique_id

    # Deliberately NOT async_config_entry_first_refresh(): miners are routinely
    # powered off (electricity tariffs, summer heat), and refusing to set up
    # would drop all of their entities and flag the entry as "needs attention".
    # Load anyway; entities report unavailable until the miner answers again.
    # An auth failure still surfaces — the coordinator starts the reauth flow.
    await coordinator.async_refresh()

    # Adopt the MAC as a stable, DHCP-resilient identity — but ONLY if it is
    # unique across configured miners. Vnish firmware is known to clone
    # device-reported identifiers (this is why v1.1.1 moved off the serial); if
    # another entry already claims this MAC we keep the guaranteed-unique host
    # IP to avoid merging two physical miners into one HA device.
    mac = mac_from_info(coordinator.info)
    if mac and _mac_available(hass, entry, mac):
        coordinator.device_id = mac
        _migrate_device_identity(hass, entry, host=host, device_id=mac)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _mac_available(hass: HomeAssistant, entry: ConfigEntry, mac: str) -> bool:
    """True if no other configured miner already claims this MAC as its id."""
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id and other.unique_id == mac:
            return False
    return True


def _migrate_device_identity(
    hass: HomeAssistant, entry: ConfigEntry, host: str, device_id: str
) -> None:
    """Re-key a legacy host-IP device/entry to the stable MAC-based identity.

    Idempotent, and tolerant of the state where both a host-keyed and a
    MAC-keyed device exist (a transient /info failure can re-create the former
    after the latter was already adopted): the leftover is merged away instead
    of lingering as a phantom device.
    """
    dev_reg = dr.async_get(hass)
    old_device = dev_reg.async_get_device(identifiers={(DOMAIN, host)})
    new_device = dev_reg.async_get_device(identifiers={(DOMAIN, device_id)})
    if old_device and new_device and old_device.id != new_device.id:
        ent_reg = er.async_get(hass)
        for ent in er.async_entries_for_device(
            ent_reg, old_device.id, include_disabled_entities=True
        ):
            ent_reg.async_update_entity(ent.entity_id, device_id=new_device.id)
        dev_reg.async_remove_device(old_device.id)
    elif old_device:
        dev_reg.async_update_device(
            old_device.id, new_identifiers={(DOMAIN, device_id)}
        )
    if entry.unique_id != device_id:
        hass.config_entries.async_update_entry(entry, unique_id=device_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
