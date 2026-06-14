from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VnishApiClient, VnishApiError, VnishAuthError

_LOGGER = logging.getLogger(__name__)


def mac_from_info(info: dict | None) -> str | None:
    """Extract and normalise the MAC address from a /info payload."""
    mac = (((info or {}).get("system") or {}).get("network_status") or {}).get("mac")
    return format_mac(mac) if mac else None


class VnishCoordinator(DataUpdateCoordinator[dict]):
    def __init__(
        self, hass: HomeAssistant, client: VnishApiClient, scan_interval: int
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Vnish Miner",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.info: dict = {}
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
        return data
