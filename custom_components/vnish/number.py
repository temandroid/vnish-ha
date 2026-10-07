from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, OPTIMISTIC_MAX_CYCLES, THROTTLE_MAX, THROTTLE_MIN
from .coordinator import VnishCoordinator
from .entity import VnishEntity
from .payload import miner_of

PARALLEL_UPDATES = 0


def _reported_throttle(data: dict | None) -> int | None:
    """MinerStatus.throttled when it is inside the documented 20–100 range.

    A value outside that range (older firmware, or a miner that has not
    reported a throttle yet) is not a setpoint the number entity can show.
    """
    status = miner_of(data).get("miner_status")
    if not isinstance(status, dict):
        return None
    value = status.get("throttled")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    value = int(value)
    if THROTTLE_MIN <= value <= THROTTLE_MAX:
        return value
    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VnishCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VnishThrottleNumber(coordinator)])


class VnishThrottleNumber(VnishEntity, NumberEntity):
    _attr_translation_key = "throttle"
    _attr_icon = "mdi:speedometer"
    _attr_native_min_value = THROTTLE_MIN
    _attr_native_max_value = THROTTLE_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: VnishCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}_throttle"
        self._optimistic: int | None = None
        self._optimistic_cycles = 0

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._optimistic is not None:
            if _reported_throttle(self.coordinator.data) == self._optimistic:
                self._optimistic = None
            else:
                self._optimistic_cycles += 1
                if self._optimistic_cycles >= OPTIMISTIC_MAX_CYCLES:
                    self._optimistic = None
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float | None:
        if self._optimistic is not None:
            return float(self._optimistic)
        reported = _reported_throttle(self.coordinator.data)
        return float(reported) if reported is not None else None

    async def async_set_native_value(self, value: float) -> None:
        percent = int(value)
        accepted = await self.coordinator.client.mining_throttle(percent)
        if accepted:
            self._optimistic = percent
            self._optimistic_cycles = 0
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
