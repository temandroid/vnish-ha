from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VnishApiClient, VnishApiError, VnishAuthError
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

    if password:
        try:
            await client.login()
        except VnishAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except VnishApiError as err:
            raise ConfigEntryNotReady(str(err)) from err

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = VnishCoordinator(hass, client, scan_interval)

    # Static info (model, serial, hr_measure, MAC) is fetched by the coordinator
    # on its first refresh and backfilled later if the miner was offline.
    await coordinator.async_config_entry_first_refresh()

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

    Idempotent: only acts while the old host-keyed device still exists and no
    MAC-keyed device has been created yet.
    """
    dev_reg = dr.async_get(hass)
    old_device = dev_reg.async_get_device(identifiers={(DOMAIN, host)})
    new_device = dev_reg.async_get_device(identifiers={(DOMAIN, device_id)})
    if old_device and not new_device:
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
