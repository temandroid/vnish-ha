from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import format_host
from .const import DOMAIN
from .coordinator import VnishCoordinator, mac_from_info


class VnishEntity(CoordinatorEntity[VnishCoordinator]):
    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        # NOTE: HA reads this only when the entity is added, so it is a snapshot
        # of whatever info was known by then — it does not self-update. A late
        # /info backfill refreshes the card via
        # VnishCoordinator._async_refresh_device_card() instead.
        coordinator = self.coordinator
        info = coordinator.info
        host = coordinator.client.host
        connections: set[tuple[str, str]] = set()
        mac = mac_from_info(info)
        # Only advertise the MAC connection when it was actually adopted as the
        # device identity (i.e. verified unique). Adding it unconditionally
        # would merge two miners in HA if the firmware cloned their MAC.
        if mac and coordinator.device_id == mac:
            connections.add((CONNECTION_NETWORK_MAC, mac))
        return DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            connections=connections,
            name=info.get("miner") or info.get("model") or "Vnish Miner",
            manufacturer="Anthill",
            model=info.get("model"),
            sw_version=info.get("fw_version"),
            serial_number=info.get("serial"),
            configuration_url=f"http://{format_host(host)}",
        )
