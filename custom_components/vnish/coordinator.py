from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VnishApiClient, VnishApiError, VnishAuthError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def mac_from_info(info: dict | None) -> str | None:
    """Extract and normalise the MAC address from a /info payload.

    Only a string is accepted: a miner reporting a number/list here must not be
    able to abort setup with a TypeError out of format_mac().
    """
    mac = (((info or {}).get("system") or {}).get("network_status") or {}).get("mac")
    return format_mac(mac) if isinstance(mac, str) and mac else None


class VnishCoordinator(DataUpdateCoordinator[dict]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: VnishApiClient,
        scan_interval: int,
        fallback_name: str = "Vnish Miner",
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Vnish Miner",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.info: dict = {}
        # Device name to use until /info answers. The config entry title is the
        # name the miner reported when it was added, so a miner that is offline
        # at startup keeps its real name instead of being renamed to a placeholder.
        self.fallback_name = fallback_name
        # Stable device identity, resolved once during setup (MAC if available,
        # otherwise the host IP). Kept constant for the session to avoid the
        # device being re-keyed mid-run.
        self.device_id: str = client.host

    async def _async_update_data(self) -> dict:
        try:
            data = await self.client.get_summary()
        except VnishAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except VnishApiError as err:
            raise UpdateFailed(str(err)) from err

        # A malformed /summary must mark the device unavailable and retry, not
        # be handed to entities as data they will choke on.
        if not isinstance(data, dict):
            raise UpdateFailed(f"Malformed /summary payload: {type(data).__name__}")

        # Best-effort: backfill static info if it was missing at startup.
        # Auth failures here must still surface (so re-auth is triggered);
        # other transient errors are logged and retried on the next cycle.
        if not self.info:
            try:
                info = await self.client.get_info()
                # Guard against a malformed /info (None / list) permanently
                # poisoning consumers that call self.info.get(...).
                self.info = info if isinstance(info, dict) else {}
            except VnishAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except VnishApiError as err:
                _LOGGER.debug("Could not fetch miner info (will retry): %s", err)
            else:
                if self.info:
                    self._async_refresh_device_card()
        return data

    @callback
    def _async_refresh_device_card(self) -> None:
        """Fill in the device card after a late /info backfill.

        HA reads Entity.device_info only when the entity is added, so a miner
        that was unreachable at startup would otherwise keep a placeholder card
        ("Vnish Miner", no model/firmware) for the rest of the session.
        Identity is deliberately NOT re-keyed here — only the metadata.
        """
        device = dr.async_get(self.hass).async_get_device(
            identifiers={(DOMAIN, self.device_id)}
        )
        if device is None:
            # Normal during the first refresh: entities do not exist yet, so
            # device_info will pick the info up at add time anyway.
            return
        dr.async_get(self.hass).async_update_device(
            device.id,
            name=self.info.get("miner") or self.info.get("model") or self.fallback_name,
            model=self.info.get("model"),
            sw_version=self.info.get("fw_version"),
            serial_number=self.info.get("serial"),
        )
