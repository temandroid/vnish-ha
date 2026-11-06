"""Tests for the restart/reboot-required binary sensors fed by GET /status."""
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er

from custom_components.vnish.api import VnishApiError, VnishAuthError
from custom_components.vnish.const import DOMAIN

from .conftest import MOCK_HOST, MOCK_INFO, MOCK_STATUS, MOCK_SUMMARY

RESTART_ID = "binary_sensor.antminer_s19k_pro_restart_required"
REBOOT_ID = "binary_sensor.antminer_s19k_pro_reboot_required"


async def _setup(hass):
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T",
        data={CONF_HOST: MOCK_HOST}, source=config_entries.SOURCE_USER,
        options={}, unique_id=MOCK_HOST, discovery_keys={}, subentries_data={},
    )
    with patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value=MOCK_INFO), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=MOCK_SUMMARY):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return entry


async def _refresh(hass, entry):
    with patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=MOCK_SUMMARY):
        await hass.data[DOMAIN][entry.entry_id].async_refresh()
        await hass.async_block_till_done()


async def test_flags_are_problem_sensors(hass):
    await _setup(hass)
    for entity_id in (RESTART_ID, REBOOT_ID):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_OFF
        assert state.attributes["device_class"] == "problem"
    reg = er.async_get(hass)
    assert reg.async_get(RESTART_ID).unique_id == f"{MOCK_HOST}_restart_required"
    assert reg.async_get(REBOOT_ID).unique_id == f"{MOCK_HOST}_reboot_required"


async def test_restart_required_turns_on(hass, mock_status):
    entry = await _setup(hass)
    mock_status.return_value = {**MOCK_STATUS, "restart_required": True}
    await _refresh(hass, entry)
    assert hass.states.get(RESTART_ID).state == STATE_ON
    assert hass.states.get(REBOOT_ID).state == STATE_OFF


async def test_status_error_is_unknown_not_unavailable(hass, mock_status):
    """A failed /status must not take the miner's other entities down."""
    entry = await _setup(hass)
    mock_status.side_effect = VnishApiError("HTTP 503 for /status", status=503)
    await _refresh(hass, entry)
    assert hass.states.get(RESTART_ID).state == STATE_UNKNOWN
    assert hass.states.get("binary_sensor.antminer_s19k_pro_mining").state == STATE_ON

    mock_status.side_effect = None
    mock_status.return_value = dict(MOCK_STATUS)
    await _refresh(hass, entry)
    assert hass.states.get(RESTART_ID).state == STATE_OFF


async def test_firmware_without_status_gets_no_sensors(hass, mock_status):
    mock_status.side_effect = VnishApiError("HTTP 404 for /status", status=404)
    entry = await _setup(hass)
    assert hass.states.get(RESTART_ID) is None
    assert hass.states.get(REBOOT_ID) is None
    calls = mock_status.await_count

    await _refresh(hass, entry)
    assert mock_status.await_count == calls  # not asked again


async def test_sensors_appear_once_status_answers(hass, mock_status):
    """Miner offline-ish at setup: /status times out first, answers later."""
    mock_status.side_effect = VnishApiError("Connection error for /status")
    entry = await _setup(hass)
    assert hass.states.get(RESTART_ID) is None

    mock_status.side_effect = None
    mock_status.return_value = {**MOCK_STATUS, "reboot_required": True}
    await _refresh(hass, entry)
    assert hass.states.get(RESTART_ID).state == STATE_OFF
    assert hass.states.get(REBOOT_ID).state == STATE_ON


async def test_status_auth_failure_starts_reauth(hass, mock_status):
    mock_status.side_effect = VnishAuthError("Authentication failed (HTTP 401)", status=401)
    entry = await _setup(hass)
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"].get("source") == "reauth" for f in flows)


async def test_diagnostics_include_status(hass):
    from custom_components.vnish.diagnostics import async_get_config_entry_diagnostics

    entry = await _setup(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["status"]["restart_required"] is False
