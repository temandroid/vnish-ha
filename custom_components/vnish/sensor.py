from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VnishCoordinator
from .entity import VnishEntity


@dataclass(frozen=True, kw_only=True)
class VnishSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict], Any]
    is_hashrate: bool = False


def _miner(data: dict) -> dict:
    return data.get("miner") or {}


def _active_pool(data: dict) -> dict:
    pools = _miner(data).get("pools") or []
    for pool in pools:
        if pool.get("status") == "active":
            return pool
    return pools[0] if pools else {}


SENSORS: tuple[VnishSensorDescription, ...] = (
    VnishSensorDescription(
        key="hashrate_rt",
        translation_key="hashrate_rt",
        native_unit_of_measurement="GH/s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pickaxe",
        is_hashrate=True,
        value_fn=lambda d: _miner(d).get("hr_realtime"),
    ),
    VnishSensorDescription(
        key="hashrate_average",
        translation_key="hashrate_average",
        native_unit_of_measurement="GH/s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
        is_hashrate=True,
        value_fn=lambda d: _miner(d).get("hr_average"),
    ),
    VnishSensorDescription(
        key="hashrate_nominal",
        translation_key="hashrate_nominal",
        native_unit_of_measurement="GH/s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        is_hashrate=True,
        value_fn=lambda d: _miner(d).get("hr_nominal"),
    ),
    VnishSensorDescription(
        key="power_consumption",
        translation_key="power_consumption",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _miner(d).get("power_consumption"),
    ),
    VnishSensorDescription(
        key="power_efficiency",
        translation_key="power_efficiency",
        native_unit_of_measurement="J/TH",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt-circle",
        value_fn=lambda d: _miner(d).get("power_efficiency"),
    ),
    VnishSensorDescription(
        key="pcb_temp_max",
        translation_key="pcb_temp_max",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (_miner(d).get("pcb_temp") or {}).get("max"),
    ),
    VnishSensorDescription(
        key="pcb_temp_min",
        translation_key="pcb_temp_min",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (_miner(d).get("pcb_temp") or {}).get("min"),
    ),
    VnishSensorDescription(
        key="chip_temp_max",
        translation_key="chip_temp_max",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (_miner(d).get("chip_temp") or {}).get("max"),
    ),
    VnishSensorDescription(
        key="chip_temp_min",
        translation_key="chip_temp_min",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (_miner(d).get("chip_temp") or {}).get("min"),
    ),
    VnishSensorDescription(
        key="fan_duty",
        translation_key="fan_duty",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
        value_fn=lambda d: (_miner(d).get("cooling") or {}).get("fan_duty"),
    ),
    VnishSensorDescription(
        key="hw_errors_percent",
        translation_key="hw_errors_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:alert-circle-outline",
        value_fn=lambda d: _miner(d).get("hw_errors_percent"),
    ),
    VnishSensorDescription(
        key="miner_state",
        translation_key="miner_state",
        icon="mdi:state-machine",
        value_fn=lambda d: (_miner(d).get("miner_status") or {}).get("miner_state"),
    ),
    VnishSensorDescription(
        key="restart_count",
        translation_key="restart_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:restart",
        value_fn=lambda d: _miner(d).get("restart_count"),
    ),
    VnishSensorDescription(
        key="active_pool",
        translation_key="active_pool",
        icon="mdi:server-network",
        value_fn=lambda d: _active_pool(d).get("url"),
    ),
    VnishSensorDescription(
        key="pool_accepted",
        translation_key="pool_accepted",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:check-circle-outline",
        value_fn=lambda d: _active_pool(d).get("accepted"),
    ),
    VnishSensorDescription(
        key="pool_rejected",
        translation_key="pool_rejected",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:close-circle-outline",
        value_fn=lambda d: _active_pool(d).get("rejected"),
    ),
    VnishSensorDescription(
        key="pool_ping",
        translation_key="pool_ping",
        native_unit_of_measurement="ms",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        value_fn=lambda d: _active_pool(d).get("ping"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VnishCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(VnishSensor(coordinator, desc) for desc in SENSORS)


class VnishSensor(VnishEntity, SensorEntity):
    entity_description: VnishSensorDescription

    def __init__(
        self, coordinator: VnishCoordinator, description: VnishSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        serial = coordinator.info.get("serial", coordinator.client.host)
        self._attr_unique_id = f"{serial}_{description.key}"
        if description.is_hashrate:
            hr_measure = coordinator.info.get("hr_measure", "GH/s")
            if hr_measure and hr_measure != "N/A":
                self._attr_native_unit_of_measurement = hr_measure

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data or {})
