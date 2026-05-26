from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VnishApiClient, VnishApiError, VnishAuthError
from .const import CONF_API_KEY, CONF_PASSWORD, DEFAULT_SCAN_INTERVAL, DOMAIN


class VnishConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip().removeprefix("http://").removeprefix("https://").rstrip("/")
            api_key = user_input.get(CONF_API_KEY) or None
            password = user_input.get(CONF_PASSWORD) or None
            data = {**user_input, CONF_HOST: host}
            try:
                session = async_get_clientsession(self.hass)
                client = VnishApiClient(
                    host=host,
                    api_key=api_key,
                    password=password,
                    session=session,
                )
                if password:
                    await client.login()
                info = await client.get_info()
            except VnishAuthError:
                errors["base"] = "invalid_auth"
            except VnishApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
                title = info.get("miner") or info.get("model") or host
                return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_API_KEY, default=""): str,
                    vol.Optional(CONF_PASSWORD, default=""): str,
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
        errors: dict[str, str] = {}

        # Use .get(key, fallback) so that "" in options correctly means "cleared".
        current_api_key = self._config_entry.options.get(
            CONF_API_KEY, self._config_entry.data.get(CONF_API_KEY) or ""
        )
        current_password = self._config_entry.options.get(
            CONF_PASSWORD, self._config_entry.data.get(CONF_PASSWORD) or ""
        )

        if user_input is not None:
            new_api_key = user_input.get(CONF_API_KEY) or None
            # Empty password field = explicitly remove password authentication.
            # The field is pre-filled, so users must clear it intentionally.
            password = user_input.get(CONF_PASSWORD) or None

            credentials_changed = (user_input.get(CONF_API_KEY, "") != current_api_key) or (
                (user_input.get(CONF_PASSWORD, "") != current_password)
            )
            if credentials_changed:
                try:
                    session = async_get_clientsession(self.hass)
                    client = VnishApiClient(
                        host=self._config_entry.data[CONF_HOST],
                        api_key=new_api_key,
                        password=password,
                        session=session,
                    )
                    if password:
                        await client.login()
                    await client.get_info()
                except VnishAuthError:
                    errors["base"] = "invalid_auth"
                except VnishApiError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    errors["base"] = "unknown"

            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_API_KEY: user_input.get(CONF_API_KEY, ""),
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    },
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_API_KEY, default=current_api_key): str,
                    vol.Optional(CONF_PASSWORD, default=current_password): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(int, vol.Range(min=10, max=3600)),
                }
            ),
            errors=errors,
        )
