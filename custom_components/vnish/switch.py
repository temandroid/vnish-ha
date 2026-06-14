from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTIVE_MINING_STATES, DOMAIN
from .coordinator import VnishCoordinator
from .entity import VnishEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VnishCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VnishMiningSwitch(coordinator)])


def _is_mining(data: dict | None) -> bool:
    miner = (data or {}).get("miner") or {}
    state = (miner.get("miner_status") or {}).get("miner_state")
    return state in ACTIVE_MINING_STATES


class VnishMiningSwitch(VnishEntity, SwitchEntity):
    _attr_translation_key = "mining"
    _attr_icon = "mdi:pickaxe"

    def __init__(self, coordinator: VnishCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_mining"
        # Optimistic target held until the miner's reported state catches up
        # (its state machine takes a few seconds), to avoid the toggle bouncing
        # back on the immediate post-command refresh.
        self._optimistic: bool | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._optimistic is not None and _is_mining(self.coordinator.data) == self._optimistic:
            self._optimistic = None
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool:
        if self._optimistic is not None:
            return self._optimistic
        return _is_mining(self.coordinator.data)

    async def _set_mining(self, turn_on: bool) -> None:
        # Send the command first so a failure surfaces and leaves state intact.
        if turn_on:
            await self.coordinator.client.mining_start()
        else:
            await self.coordinator.client.mining_stop()
        self._optimistic = turn_on
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._set_mining(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._set_mining(False)
