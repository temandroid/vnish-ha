from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VnishCoordinator


class VnishEntity(CoordinatorEntity[VnishCoordinator]):
    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        # Built dynamically so the device card fills in once the coordinator
        # backfills static info (the miner may have been offline at startup).
        info = self.coordinator.info
        host = self.coordinator.client.host
        return DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=info.get("miner") or info.get("model") or "Vnish Miner",
            manufacturer="Anthill",
            model=info.get("model"),
            sw_version=info.get("fw_version"),
            serial_number=info.get("serial"),
            configuration_url=f"http://{host}",
        )
