from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTIVE_MINING_STATES, DOMAIN
from .coordinator import VnishCoordinator
from .entity import VnishEntity
from .payload import fan_by_id, fan_ids, miner_of

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class VnishBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict], bool | None]


BINARY_SENSORS: tuple[VnishBinarySensorDescription, ...] = (
    VnishBinarySensorDescription(
        key="is_mining",
        translation_key="is_mining",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: (
            (miner_of(d).get("miner_status") or {}).get("miner_state")
            in ACTIVE_MINING_STATES
        ),
    ),
)


# Flags from GET /status (MinerStatus). Created only once the miner reports
# them, so firmware without /status does not get two sensors stuck at unknown.
STATUS_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    # Set by Vnish when performance settings could not be applied cleanly —
    # e.g. a throttle command that collided with a preset setup still in
    # progress. The miner then runs at a different percent than it reports
    # until mining is restarted.
    BinarySensorEntityDescription(
        key="restart_required",
        translation_key="restart_required",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    BinarySensorEntityDescription(
        key="reboot_required",
        translation_key="reboot_required",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VnishCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(VnishBinarySensor(coordinator, desc) for desc in BINARY_SENSORS)

    seen: set[int] = set()

    @callback
    def _add_fans() -> None:
        fresh: list[VnishFanFaultBinarySensor] = []
        for fan_id in fan_ids(coordinator.data):
            if fan_id in seen:
                continue
            seen.add(fan_id)
            fresh.append(VnishFanFaultBinarySensor(coordinator, fan_id))
        if fresh:
            async_add_entities(fresh)

    entry.async_on_unload(coordinator.async_add_listener(_add_fans))
    _add_fans()

    pending_status = list(STATUS_SENSORS)

    @callback
    def _add_status_flags() -> None:
        fresh = [d for d in pending_status if d.key in coordinator.status]
        for desc in fresh:
            pending_status.remove(desc)
        if fresh:
            async_add_entities(
                VnishStatusFlagBinarySensor(coordinator, desc) for desc in fresh
            )

    entry.async_on_unload(coordinator.async_add_listener(_add_status_flags))
    _add_status_flags()


class VnishBinarySensor(VnishEntity, BinarySensorEntity):
    entity_description: VnishBinarySensorDescription

    def __init__(
        self,
        coordinator: VnishCoordinator,
        description: VnishBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.client.host}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data or {})


class VnishFanFaultBinarySensor(VnishEntity, BinarySensorEntity):
    """On when Cooling.fans[].status is `lost`."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: VnishCoordinator, fan_id: int) -> None:
        super().__init__(coordinator)
        self._fan_id = fan_id
        self._attr_unique_id = f"{coordinator.client.host}_fan_{fan_id}_fault"
        self._attr_translation_key = "fan_fault"
        self._attr_translation_placeholders = {"id": str(fan_id)}

    @property
    def is_on(self) -> bool | None:
        status = fan_by_id(self.coordinator.data, self._fan_id).get("status")
        if status == "lost":
            return True
        if status == "ok":
            return False
        return None


class VnishStatusFlagBinarySensor(VnishEntity, BinarySensorEntity):
    """A boolean flag of GET /status; unknown while /status did not answer."""

    def __init__(
        self,
        coordinator: VnishCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.client.host}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.status.get(self.entity_description.key)
        return value if isinstance(value, bool) else None
