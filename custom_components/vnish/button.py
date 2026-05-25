from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import VnishApiClient
from .const import DOMAIN
from .coordinator import VnishCoordinator
from .entity import VnishEntity


@dataclass(frozen=True, kw_only=True)
class VnishButtonDescription(ButtonEntityDescription):
    action_fn: Callable[[VnishApiClient], Coroutine[Any, Any, None]]


BUTTONS: tuple[VnishButtonDescription, ...] = (
    VnishButtonDescription(
        key="reboot",
        translation_key="reboot",
        icon="mdi:restart",
        action_fn=lambda c: c.system_reboot(),
    ),
    VnishButtonDescription(
        key="mining_restart",
        translation_key="mining_restart",
        icon="mdi:pickaxe",
        action_fn=lambda c: c.mining_restart(),
    ),
    VnishButtonDescription(
        key="mining_pause",
        translation_key="mining_pause",
        icon="mdi:pause-circle-outline",
        action_fn=lambda c: c.mining_pause(),
    ),
    VnishButtonDescription(
        key="mining_resume",
        translation_key="mining_resume",
        icon="mdi:play-circle-outline",
        action_fn=lambda c: c.mining_resume(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VnishCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(VnishButton(coordinator, desc) for desc in BUTTONS)


class VnishButton(VnishEntity, ButtonEntity):
    entity_description: VnishButtonDescription

    def __init__(
        self, coordinator: VnishCoordinator, description: VnishButtonDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        serial = coordinator.info.get("serial", coordinator.client.host)
        self._attr_unique_id = f"{serial}_{description.key}"

    async def async_press(self) -> None:
        await self.entity_description.action_fn(self.coordinator.client)
        await self.coordinator.async_request_refresh()
