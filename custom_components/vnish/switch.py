from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTIVE_MINING_STATES, DOMAIN
from .coordinator import VnishCoordinator
from .entity import VnishEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VnishCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VnishMiningSwitch(coordinator)])


class VnishMiningSwitch(VnishEntity, SwitchEntity):
    _attr_translation_key = "mining"
    _attr_icon = "mdi:pickaxe"

    def __init__(self, coordinator: VnishCoordinator) -> None:
        super().__init__(coordinator)
        serial = coordinator.info.get("serial", coordinator.client.host)
        self._attr_unique_id = f"{serial}_mining"

    @property
    def is_on(self) -> bool:
        miner = (self.coordinator.data or {}).get("miner") or {}
        state = (miner.get("miner_status") or {}).get("miner_state")
        return state in ACTIVE_MINING_STATES

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.client.mining_start()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.client.mining_stop()
        await self.coordinator.async_request_refresh()
