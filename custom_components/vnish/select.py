from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VnishCoordinator
from .entity import VnishEntity

PARALLEL_UPDATES = 0


def _pools(data: dict | None) -> list[dict]:
    return ((data or {}).get("miner") or {}).get("pools") or []


def _active_url(data: dict | None) -> str | None:
    for pool in _pools(data):
        if pool.get("status") == "active":
            return pool.get("url")
    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VnishCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VnishPoolSelect(coordinator)])


class VnishPoolSelect(VnishEntity, SelectEntity):
    _attr_translation_key = "pool"
    _attr_icon = "mdi:server-network"

    def __init__(self, coordinator: VnishCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_pool_select"
        self._optimistic: str | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._optimistic is not None and _active_url(self.coordinator.data) == self._optimistic:
            self._optimistic = None
        super()._handle_coordinator_update()

    @property
    def options(self) -> list[str]:
        return [p["url"] for p in _pools(self.coordinator.data) if p.get("url")]

    @property
    def current_option(self) -> str | None:
        if self._optimistic is not None:
            return self._optimistic
        return _active_url(self.coordinator.data)

    async def async_select_option(self, option: str) -> None:
        for pool in _pools(self.coordinator.data):
            if pool.get("url") == option and pool.get("id") is not None:
                await self.coordinator.client.switch_pool(pool["id"])
                self._optimistic = option
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()
                return
