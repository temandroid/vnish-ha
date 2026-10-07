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
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VnishCoordinator
from .entity import VnishEntity
from .payload import (
    active_user_pool,
    chain_by_id,
    chain_ids,
    fan_by_id,
    fan_ids,
    miner_of,
    psu_temp_keys,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class VnishSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict], Any]
    is_hashrate: bool = False
    # "summary" reads coordinator.data; "info" reads the static /info document.
    source: str = "summary"


def _miner(data: dict) -> dict:
    return miner_of(data)


def _active_pool(data: dict) -> dict:
    return active_user_pool(data)


def _psu_temp(key: str) -> Callable[[dict], Any]:
    def _value(data: dict) -> Any:
        psu = _miner(data).get("psu")
        if not isinstance(psu, dict):
            return None
        temps = psu.get("temps")
        if not isinstance(temps, dict):
            return None
        value = temps.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    return _value


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
        key="hashrate_stock",
        translation_key="hashrate_stock",
        native_unit_of_measurement="GH/s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        is_hashrate=True,
        value_fn=lambda d: _miner(d).get("hr_stock"),
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
        key="hw_errors",
        translation_key="hw_error_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:alert-circle-outline",
        value_fn=lambda d: _miner(d).get("hw_errors"),
    ),
    VnishSensorDescription(
        key="hr_error",
        translation_key="hr_error",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bell-curve",
        value_fn=lambda d: _miner(d).get("hr_error"),
    ),
    VnishSensorDescription(
        key="miner_state",
        translation_key="miner_state",
        icon="mdi:state-machine",
        value_fn=lambda d: (_miner(d).get("miner_status") or {}).get("miner_state"),
    ),
    VnishSensorDescription(
        key="miner_state_time",
        translation_key="miner_state_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        value_fn=lambda d: (_miner(d).get("miner_status") or {}).get(
            "miner_state_time"
        ),
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
        key="pool_stale",
        translation_key="pool_stale",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:clock-alert-outline",
        value_fn=lambda d: _active_pool(d).get("stale"),
    ),
    VnishSensorDescription(
        key="pool_ping",
        translation_key="pool_ping",
        native_unit_of_measurement="ms",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        value_fn=lambda d: _active_pool(d).get("ping"),
    ),
    VnishSensorDescription(
        key="uptime",
        translation_key="uptime",
        icon="mdi:timer-sand",
        value_fn=lambda d: ((d.get("system") or {}).get("uptime")),
        source="info",
    ),
    VnishSensorDescription(
        key="memory_free",
        translation_key="memory_free",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        value_fn=lambda d: ((d.get("system") or {}).get("mem_free_percent")),
        source="info",
    ),
)


FAN_SPEED = VnishSensorDescription(
    key="fan_speed",
    translation_key="fan_speed",
    native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:fan",
    value_fn=lambda fan: fan.get("rpm"),
)

CHAIN_SENSORS: tuple[VnishSensorDescription, ...] = (
    VnishSensorDescription(
        key="hashrate",
        translation_key="chain_hashrate",
        native_unit_of_measurement="GH/s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pickaxe",
        is_hashrate=True,
        value_fn=lambda chain: chain.get("hashrate_rt"),
    ),
    VnishSensorDescription(
        key="pcb_temp",
        translation_key="chain_pcb_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda chain: (chain.get("pcb_temp") or {}).get("max"),
    ),
    VnishSensorDescription(
        key="chip_temp",
        translation_key="chain_chip_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda chain: (chain.get("chip_temp") or {}).get("max"),
    ),
    VnishSensorDescription(
        key="hw_errors",
        translation_key="chain_hw_errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:alert-circle-outline",
        value_fn=lambda chain: chain.get("hw_errors"),
    ),
    VnishSensorDescription(
        key="state",
        translation_key="chain_state",
        icon="mdi:chip",
        value_fn=lambda chain: (chain.get("status") or {}).get("state"),
    ),
)

PSU_SENSORS: dict[str, VnishSensorDescription] = {
    "pfc_temp": VnishSensorDescription(
        key="psu_pfc_temp",
        translation_key="psu_pfc_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:power-plug",
        value_fn=_psu_temp("pfc_temp"),
    ),
    "llc1_temp": VnishSensorDescription(
        key="psu_llc1_temp",
        translation_key="psu_llc1_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:power-plug",
        value_fn=_psu_temp("llc1_temp"),
    ),
    "llc2_temp": VnishSensorDescription(
        key="psu_llc2_temp",
        translation_key="psu_llc2_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:power-plug",
        value_fn=_psu_temp("llc2_temp"),
    ),
}


def _watch(
    entry: ConfigEntry,
    coordinator: VnishCoordinator,
    async_add_entities: AddEntitiesCallback,
    discover: Callable[[dict | None], list],
    factory: Callable[[Any], list[SensorEntity]],
) -> None:
    """Add entities the first time their hardware shows up in /summary.

    Fans, boards and PSU temperatures are absent while the miner is offline
    and on hardware that does not have them, so they cannot be created up front.
    """
    seen: set[Any] = set()

    @callback
    def _add() -> None:
        fresh: list[SensorEntity] = []
        for item in discover(coordinator.data):
            if item in seen:
                continue
            seen.add(item)
            fresh.extend(factory(item))
        if fresh:
            async_add_entities(fresh)

    entry.async_on_unload(coordinator.async_add_listener(_add))
    _add()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VnishCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(VnishSensor(coordinator, desc) for desc in SENSORS)

    def _fan(fan_id: int) -> list[SensorEntity]:
        return [
            VnishChildSensor(
                coordinator,
                FAN_SPEED,
                unique_suffix=f"fan_{fan_id}_rpm",
                placeholders={"id": str(fan_id)},
                lookup=lambda data, fan_id=fan_id: fan_by_id(data, fan_id),
            )
        ]

    def _chain(chain_id: int) -> list[SensorEntity]:
        return [
            VnishChildSensor(
                coordinator,
                description,
                unique_suffix=f"chain_{chain_id}_{description.key}",
                placeholders={"id": str(chain_id)},
                lookup=lambda data, chain_id=chain_id: chain_by_id(data, chain_id),
            )
            for description in CHAIN_SENSORS
        ]

    _watch(entry, coordinator, async_add_entities, fan_ids, _fan)
    _watch(entry, coordinator, async_add_entities, chain_ids, _chain)
    _watch(
        entry,
        coordinator,
        async_add_entities,
        psu_temp_keys,
        lambda key: [VnishSensor(coordinator, PSU_SENSORS[key])],
    )


class VnishSensor(VnishEntity, SensorEntity):
    entity_description: VnishSensorDescription

    def __init__(
        self, coordinator: VnishCoordinator, description: VnishSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.client.host}_{description.key}"

    @property
    def native_unit_of_measurement(self) -> str | None:
        # Resolved dynamically: hr_measure comes from static info which may be
        # backfilled after startup. Falls back to the description's default.
        if self.entity_description.is_hashrate:
            hr_measure = self.coordinator.info.get("hr_measure")
            if hr_measure and hr_measure != "N/A":
                return hr_measure
        return self.entity_description.native_unit_of_measurement

    @property
    def native_value(self) -> Any:
        if self.entity_description.source == "info":
            payload: dict = self.coordinator.info or {}
        else:
            payload = self.coordinator.data or {}
        return self.entity_description.value_fn(payload)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        # MinerStatus.description / failure_code explain a `failure` state.
        # They are not worth their own entities.
        if self.entity_description.key != "miner_state":
            return None
        status = (_miner(self.coordinator.data or {}).get("miner_status") or {})
        if not isinstance(status, dict):
            return None
        attrs: dict[str, Any] = {}
        description = status.get("description")
        if isinstance(description, str) and description:
            attrs["description"] = description
        code = status.get("failure_code")
        if isinstance(code, int) and not isinstance(code, bool):
            attrs["failure_code"] = code
        return attrs or None


class VnishChildSensor(VnishSensor):
    """A sensor whose value comes from one fan or one hashboard, not the miner."""

    def __init__(
        self,
        coordinator: VnishCoordinator,
        description: VnishSensorDescription,
        *,
        unique_suffix: str,
        placeholders: dict[str, str],
        lookup: Callable[[dict], dict],
    ) -> None:
        super().__init__(coordinator, description)
        self._attr_unique_id = f"{coordinator.client.host}_{unique_suffix}"
        self._attr_translation_placeholders = placeholders
        self._lookup = lookup

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(
            self._lookup(self.coordinator.data or {})
        )
