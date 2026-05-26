from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VnishApiClient, VnishApiError, VnishAuthError

_LOGGER = logging.getLogger(__name__)


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

    async def _async_update_data(self) -> dict:
        try:
            data = await self.client.get_summary()
            # Retry get_info() if it failed at startup (miner was offline)
            if not self.info:
                try:
                    self.info = await self.client.get_info()
                except VnishApiError as err:
                    _LOGGER.debug("Could not fetch miner info (will retry): %s", err)
            return data
        except VnishAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except VnishApiError as err:
            raise UpdateFailed(str(err)) from err
