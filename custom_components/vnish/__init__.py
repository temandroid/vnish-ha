from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VnishApiClient, VnishApiError, VnishAuthError
from .const import CONF_API_KEY, CONF_PASSWORD, DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import VnishCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    # Use .get(key, fallback) so that an empty string in options ("key cleared")
    # does NOT fall through to the original value in entry.data.
    api_key = entry.options.get(CONF_API_KEY, entry.data.get(CONF_API_KEY)) or None
    password = entry.options.get(CONF_PASSWORD, entry.data.get(CONF_PASSWORD)) or None
    client = VnishApiClient(
        host=entry.data[CONF_HOST],
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

    try:
        coordinator.info = await client.get_info()
    except VnishApiError as err:
        _LOGGER.warning("Could not fetch miner info: %s", err)
        coordinator.info = {}

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
