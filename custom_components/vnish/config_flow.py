from __future__ import annotations

from typing import Any, Mapping

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VnishApiClient, VnishApiError, VnishAuthError
from .const import CONF_API_KEY, CONF_PASSWORD, DEFAULT_SCAN_INTERVAL, DOMAIN


def _normalise_host(raw: str) -> str:
    """Reduce user input to a bare host[:port].

    Accepts a pasted URL ('http://192.168.1.5/docs/') as well as a plain
    address. The path is dropped rather than only the trailing slash, so a
    pasted deep link does not end up inside the API base URL.
    """
    host = raw.strip().removeprefix("http://").removeprefix("https://")
    return host.split("/")[0].strip()


async def _validate_connection(
    hass: HomeAssistant, host: str, api_key: str | None, password: str | None
) -> dict:
    """Validate credentials against the miner.

    Returns the /info dict on success. Raises VnishAuthError on bad
    credentials, VnishApiError on connection problems.
    """
    session = async_get_clientsession(hass)
    client = VnishApiClient(
        host=host, api_key=api_key, password=password, session=session
    )
    if password:
        await client.login()
    info = await client.get_info()
    # A wrong IP / captive portal can answer 200 with a non-JSON body (-> None)
    # or with JSON null/list. Turn that into cannot_connect rather than letting
    # an AttributeError escape the flow when the caller does info.get(...).
    if not isinstance(info, dict):
        raise VnishApiError(f"Malformed /info payload: {type(info).__name__}")
    return info


def _errors_for(exc: Exception) -> str:
    """Map a validation exception to a config-flow error key."""
    if isinstance(exc, VnishAuthError):
        return "invalid_auth"
    if isinstance(exc, VnishApiError):
        return "cannot_connect"
    return "unknown"


class VnishConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = _normalise_host(user_input[CONF_HOST])
            api_key = user_input.get(CONF_API_KEY) or None
            password = user_input.get(CONF_PASSWORD) or None
            data = {**user_input, CONF_HOST: host}
            try:
                info = await _validate_connection(self.hass, host, api_key, password)
            except Exception as err:  # noqa: BLE001
                errors["base"] = _errors_for(err)
            else:
                # Dedup on the host stored in entry.data. This must NOT rely on
                # unique_id: setup re-keys the entry from host to MAC once the
                # MAC proves unique, after which a host-based unique_id lookup
                # would no longer match and the same miner could be added twice.
                self._async_abort_entries_match({CONF_HOST: host})
                # Host IP is guaranteed unique per device on a LAN; the MAC may
                # be cloned by the firmware, so it is adopted (collision-safely)
                # only later in setup, never as the add-time dedup key.
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

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="reauth_failed")

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY) or None
            password = user_input.get(CONF_PASSWORD) or None
            try:
                await _validate_connection(
                    self.hass, entry.data[CONF_HOST], api_key, password
                )
            except Exception as err:  # noqa: BLE001
                errors["base"] = _errors_for(err)
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    options={
                        **entry.options,
                        CONF_API_KEY: user_input.get(CONF_API_KEY, ""),
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_API_KEY, default=""): str,
                    vol.Optional(CONF_PASSWORD, default=""): str,
                }
            ),
            description_placeholders={"host": entry.data[CONF_HOST]},
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
            api_key = user_input.get(CONF_API_KEY) or None
            # Fields are pre-filled, so clearing one means "remove auth".
            password = user_input.get(CONF_PASSWORD) or None

            credentials_changed = (
                user_input.get(CONF_API_KEY, "") != current_api_key
                or user_input.get(CONF_PASSWORD, "") != current_password
            )
            if credentials_changed:
                try:
                    await _validate_connection(
                        self.hass, self._config_entry.data[CONF_HOST], api_key, password
                    )
                except Exception as err:  # noqa: BLE001
                    errors["base"] = _errors_for(err)

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
