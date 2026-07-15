from __future__ import annotations

from typing import Any, NamedTuple

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, OPTIMISTIC_MAX_CYCLES
from .coordinator import VnishCoordinator
from .entity import VnishEntity

PARALLEL_UPDATES = 0


class _Pool(NamedTuple):
    label: str
    pool_id: Any
    active: bool


def _pools(data: dict | None) -> list[dict]:
    return ((data or {}).get("miner") or {}).get("pools") or []


def _pool_entries(data: dict | None) -> list[_Pool]:
    """Selectable pools as (label, id, active).

    Only pools that have both a URL and an id are offered: an id-less pool
    could be picked but never switched to, which would look like a silent no-op.
    Labels are the URL, disambiguated with the id when two pools share one (a
    common primary/failover pattern), so every pool stays addressable.
    """
    pools = [p for p in _pools(data) if p.get("url") and p.get("id") is not None]
    urls = [p["url"] for p in pools]
    return [
        _Pool(
            label=p["url"] if urls.count(p["url"]) == 1 else f"{p['url']} (#{p['id']})",
            pool_id=p["id"],
            active=p.get("status") == "active",
        )
        for p in pools
    ]


def _active_label(data: dict | None) -> str | None:
    return next((p.label for p in _pool_entries(data) if p.active), None)


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
        self._optimistic_cycles = 0

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._optimistic is not None:
            if _active_label(self.coordinator.data) == self._optimistic:
                self._optimistic = None
            else:
                # Bounded: a pool the miner never activates (dead/misconfigured)
                # must not be reported as current forever.
                self._optimistic_cycles += 1
                if self._optimistic_cycles >= OPTIMISTIC_MAX_CYCLES:
                    self._optimistic = None
        super()._handle_coordinator_update()

    @property
    def options(self) -> list[str]:
        return [p.label for p in _pool_entries(self.coordinator.data)]

    @property
    def current_option(self) -> str | None:
        # Never report an optimistic value that has dropped out of the list —
        # HA logs an error for a state that is not among the options.
        if self._optimistic is not None and self._optimistic in self.options:
            return self._optimistic
        return _active_label(self.coordinator.data)

    async def async_select_option(self, option: str) -> None:
        pool = next(
            (p for p in _pool_entries(self.coordinator.data) if p.label == option), None
        )
        if pool is None:
            return
        accepted = await self.coordinator.client.switch_pool(pool.pool_id)
        if accepted:
            self._optimistic = option
            self._optimistic_cycles = 0
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
