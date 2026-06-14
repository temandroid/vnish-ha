from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTIVE_MINING_STATES, DOMAIN
from .coordinator import VnishCoordinator
from .entity import VnishEntity

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
            ((d.get("miner") or {}).get("miner_status") or {}).get("miner_state")
            in ACTIVE_MINING_STATES
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VnishCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(VnishBinarySensor(coordinator, desc) for desc in BINARY_SENSORS)


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
