from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VnishCoordinator


class VnishEntity(CoordinatorEntity[VnishCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: VnishCoordinator) -> None:
        super().__init__(coordinator)
        info = coordinator.info
        host = coordinator.client.host
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=info.get("miner") or info.get("model", "Vnish Miner"),
            manufacturer="Anthill",
            model=info.get("model"),
            sw_version=info.get("fw_version"),
            serial_number=info.get("serial"),
            configuration_url=f"http://{host}",
        )
