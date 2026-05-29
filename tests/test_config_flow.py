"""Tests for config flow."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResultType

from custom_components.vnish.api import VnishApiError, VnishAuthError
from custom_components.vnish.const import CONF_API_KEY, CONF_PASSWORD, DOMAIN

from .conftest import MOCK_HOST, MOCK_INFO


async def test_form_success(hass):
    """Config flow creates entry on valid host."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.vnish.config_flow.VnishApiClient.get_info",
        new_callable=AsyncMock,
        return_value=MOCK_INFO,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: MOCK_HOST}
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Antminer S19k Pro"
    assert result2["data"][CONF_HOST] == MOCK_HOST


async def test_form_success_with_password(hass):
    """Config flow creates entry when valid password is provided."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.vnish.config_flow.VnishApiClient.login",
        new_callable=AsyncMock,
    ), patch(
        "custom_components.vnish.config_flow.VnishApiClient.get_info",
        new_callable=AsyncMock,
        return_value=MOCK_INFO,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: MOCK_HOST, CONF_PASSWORD: "secret"}
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_PASSWORD] == "secret"


def test_host_is_normalized(hass):
    """Host strips http:// prefix and trailing slash."""
    raw = "  http://192.168.1.100/  "
    normalized = raw.strip().removeprefix("http://").removeprefix("https://").rstrip("/")
    assert normalized == "192.168.1.100"


async def test_form_cannot_connect(hass):
    """Config flow shows error when miner is unreachable."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.vnish.config_flow.VnishApiClient.get_info",
        new_callable=AsyncMock,
        side_effect=VnishApiError("Connection refused"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: MOCK_HOST}
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"]["base"] == "cannot_connect"


async def test_form_invalid_auth(hass):
    """Config flow shows invalid_auth error when password is wrong."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.vnish.config_flow.VnishApiClient.login",
        new_callable=AsyncMock,
        side_effect=VnishAuthError("Authentication failed (HTTP 401)"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: MOCK_HOST, CONF_PASSWORD: "wrongpass"}
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"]["base"] == "invalid_auth"


async def test_form_duplicate(hass):
    """Config flow aborts when same host is already configured."""
    with patch(
        "custom_components.vnish.config_flow.VnishApiClient.get_info",
        new_callable=AsyncMock,
        return_value=MOCK_INFO,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: MOCK_HOST}
        )

        result2 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"], {CONF_HOST: MOCK_HOST}
        )

    assert result3["type"] == FlowResultType.ABORT
    assert result3["reason"] == "already_configured"


async def test_reauth_flow_success(hass, mock_api):
    """Reauth flow validates new credentials and updates the entry."""
    entry = await _setup_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.vnish.config_flow.VnishApiClient.login",
        new_callable=AsyncMock,
    ), patch(
        "custom_components.vnish.config_flow.VnishApiClient.get_info",
        new_callable=AsyncMock,
        return_value=MOCK_INFO,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "newsecret"}
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert entry.options[CONF_PASSWORD] == "newsecret"


async def test_reauth_flow_invalid_auth(hass, mock_api):
    """Reauth flow shows invalid_auth when new credentials are wrong."""
    entry = await _setup_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )

    with patch(
        "custom_components.vnish.config_flow.VnishApiClient.login",
        new_callable=AsyncMock,
        side_effect=VnishAuthError("Authentication failed (HTTP 401)"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "stillwrong"}
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"]["base"] == "invalid_auth"


async def test_options_flow_scan_interval(hass, mock_api):
    """Options flow saves scan_interval."""
    entry = await _setup_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60}
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 60


async def test_options_flow_api_key_update(hass, mock_api):
    """Options flow validates and saves updated API key."""
    entry = await _setup_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with patch(
        "custom_components.vnish.config_flow.VnishApiClient.get_info",
        new_callable=AsyncMock,
        return_value=MOCK_INFO,
    ):
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "new-api-key", CONF_SCAN_INTERVAL: 30},
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_API_KEY] == "new-api-key"


async def test_options_flow_password_update(hass, mock_api):
    """Options flow validates password via login() and saves it."""
    entry = await _setup_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with patch(
        "custom_components.vnish.config_flow.VnishApiClient.login",
        new_callable=AsyncMock,
    ), patch(
        "custom_components.vnish.config_flow.VnishApiClient.get_info",
        new_callable=AsyncMock,
        return_value=MOCK_INFO,
    ):
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_PASSWORD: "newpassword", CONF_SCAN_INTERVAL: 30},
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_PASSWORD] == "newpassword"


async def _setup_entry(hass):
    """Helper: create and set up a config entry."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Miner",
        data={CONF_HOST: MOCK_HOST},
        source=config_entries.SOURCE_USER,
        options={},
        unique_id=MOCK_HOST,
        discovery_keys={},
    )
    with patch(
        "custom_components.vnish.api.VnishApiClient.get_info",
        new_callable=AsyncMock,
        return_value=MOCK_INFO,
    ), patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value={"miner": {}},
    ):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return entry
