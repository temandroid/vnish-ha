"""Tests for button platform."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST

from custom_components.vnish.const import DOMAIN

from .conftest import MOCK_HOST, MOCK_INFO, MOCK_SUMMARY


async def _setup(hass):
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T",
        data={CONF_HOST: MOCK_HOST}, source=config_entries.SOURCE_USER,
        options={}, unique_id=MOCK_INFO["serial"], discovery_keys={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value=MOCK_INFO), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=MOCK_SUMMARY):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return entry


async def test_reboot_button_exists(hass):
    """Reboot button entity is created."""
    await _setup(hass)
    state = hass.states.get("button.antminer_s19k_pro_reboot")
    assert state is not None


async def test_press_reboot(hass):
    """Pressing reboot calls system_reboot API."""
    await _setup(hass)

    with patch(
        "custom_components.vnish.api.VnishApiClient.system_reboot",
        new_callable=AsyncMock,
    ) as mock_reboot, patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        await hass.services.async_call(
            "button", "press",
            {"entity_id": "button.antminer_s19k_pro_reboot"},
            blocking=True,
        )
        mock_reboot.assert_called_once()


async def test_press_mining_pause(hass):
    """Pressing pause calls mining_pause API."""
    await _setup(hass)

    with patch(
        "custom_components.vnish.api.VnishApiClient.mining_pause",
        new_callable=AsyncMock,
    ) as mock_pause, patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        await hass.services.async_call(
            "button", "press",
            {"entity_id": "button.antminer_s19k_pro_pause_mining"},
            blocking=True,
        )
        mock_pause.assert_called_once()


async def test_press_mining_resume(hass):
    """Pressing resume calls mining_resume API."""
    await _setup(hass)

    with patch(
        "custom_components.vnish.api.VnishApiClient.mining_resume",
        new_callable=AsyncMock,
    ) as mock_resume, patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        await hass.services.async_call(
            "button", "press",
            {"entity_id": "button.antminer_s19k_pro_resume_mining"},
            blocking=True,
        )
        mock_resume.assert_called_once()


async def test_press_mining_restart(hass):
    """Pressing restart calls mining_restart API."""
    await _setup(hass)

    with patch(
        "custom_components.vnish.api.VnishApiClient.mining_restart",
        new_callable=AsyncMock,
    ) as mock_restart, patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        await hass.services.async_call(
            "button", "press",
            {"entity_id": "button.antminer_s19k_pro_restart_mining"},
            blocking=True,
        )
        mock_restart.assert_called_once()
