from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VnishApiClient, VnishApiError
from .const import CONF_API_KEY, DEFAULT_SCAN_INTERVAL, DOMAIN


class VnishConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip().removeprefix("http://").removeprefix("https://").rstrip("/")
            user_input = {**user_input, CONF_HOST: host}
            try:
                session = async_get_clientsession(self.hass)
                client = VnishApiClient(
                    host=host,
                    api_key=user_input.get(CONF_API_KEY) or None,
                    session=session,
                )
                info = await client.get_info()
            except VnishApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                serial = info.get("serial") or user_input[CONF_HOST]
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()
                title = info.get("miner") or info.get("model") or user_input[CONF_HOST]
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_API_KEY, default=""): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> VnishOptionsFlow:
        return VnishOptionsFlow(config_entry)


class VnishOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(int, vol.Range(min=10, max=3600)),
                }
            ),
        )
