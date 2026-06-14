from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, CONF_PASSWORD, DOMAIN
from .coordinator import VnishCoordinator

TO_REDACT = {
    CONF_API_KEY,
    CONF_PASSWORD,
    "host",
    "mac",
    "ip",
    "gateway",
    "dns",
    "hostname",
    "user",
    "url",
    "serial",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: VnishCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
            "unique_id_set": entry.unique_id is not None,
        },
        "info": async_redact_data(coordinator.info, TO_REDACT),
        "summary": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
