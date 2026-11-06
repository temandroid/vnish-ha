"""Tests for the throttle gate: pacing and coalescing of POST /mining/throttle."""
import asyncio
import logging
import time
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST

from custom_components.vnish.api import VnishApiError
from custom_components.vnish.const import DOMAIN, THROTTLE_MIN_INTERVAL
from custom_components.vnish.throttle import ThrottleGate

from .conftest import MOCK_HOST, MOCK_INFO, MOCK_SUMMARY

INTERVAL = 0.05
NUMBER_ID = "number.antminer_s19k_pro_throttle"


class _Miner:
    """A fake send() that records calls and fails on overlapping commands."""

    def __init__(self, result=True):
        self.calls: list[int] = []
        self.times: list[float] = []
        self.result = result
        self._inflight = False

    async def send(self, percent: int) -> bool:
        assert not self._inflight, "two throttle commands in flight at once"
        self._inflight = True
        try:
            await asyncio.sleep(0)
            self.calls.append(percent)
            self.times.append(time.monotonic())
            if isinstance(self.result, Exception):
                raise self.result
            return self.result
        finally:
            self._inflight = False


async def _drain(gate: ThrottleGate) -> None:
    task = gate._task
    if task is not None:
        await task


def test_interval_has_a_margin_over_the_preset_setup():
    """Vnish 1.3.5 took up to 12 s to apply a preset; the pause must exceed it."""
    assert THROTTLE_MIN_INTERVAL >= 15


async def test_idle_gate_sends_at_once(hass):
    miner = _Miner()
    gate = ThrottleGate(hass, miner.send, INTERVAL)
    assert await gate.async_request(90) is True
    assert miner.calls == [90]
    assert gate._task is None


async def test_burst_is_coalesced_to_first_and_last(hass):
    """The 2026-11-06 incident: several writes within a second."""
    miner = _Miner()
    on_sent = AsyncMock()
    gate = ThrottleGate(hass, miner.send, INTERVAL, on_sent=on_sent)

    assert await gate.async_request(90) is True
    assert await gate.async_request(91) is None
    assert await gate.async_request(92) is None
    assert await gate.async_request(93) is None
    assert gate.pending == 93
    assert miner.calls == [90]

    await _drain(gate)
    assert miner.calls == [90, 93]
    assert miner.times[1] - miner.times[0] >= INTERVAL
    on_sent.assert_awaited_once()
    assert gate.pending is None


async def test_concurrent_writes_never_overlap(hass):
    miner = _Miner()
    gate = ThrottleGate(hass, miner.send, INTERVAL)
    results = await asyncio.gather(*(gate.async_request(p) for p in (50, 60, 70)))
    assert results.count(True) == 1
    await _drain(gate)
    assert miner.calls == [50, 70]


async def test_pending_equal_to_applied_is_dropped(hass):
    """90 → 95 → 90 inside the pause: the miner is already at 90."""
    miner = _Miner()
    gate = ThrottleGate(hass, miner.send, INTERVAL)
    await gate.async_request(90)
    await gate.async_request(95)
    await gate.async_request(90)
    await _drain(gate)
    assert miner.calls == [90]


async def test_rejected_command_is_not_treated_as_applied(hass):
    miner = _Miner(result=False)
    gate = ThrottleGate(hass, miner.send, INTERVAL)
    assert await gate.async_request(80) is False
    miner.result = True
    assert await gate.async_request(80) is None  # still inside the pause
    await _drain(gate)
    assert miner.calls == [80, 80]


async def test_idle_again_after_the_pause(hass):
    miner = _Miner()
    gate = ThrottleGate(hass, miner.send, INTERVAL)
    await gate.async_request(80)
    await asyncio.sleep(INTERVAL * 1.5)
    assert await gate.async_request(70) is True
    assert miner.calls == [80, 70]


async def test_immediate_error_propagates_and_still_pauses(hass):
    miner = _Miner(result=VnishApiError("boom"))
    gate = ThrottleGate(hass, miner.send, INTERVAL)
    try:
        await gate.async_request(80)
    except VnishApiError:
        pass
    else:
        raise AssertionError("error from an immediate send must reach the caller")
    assert await gate.async_request(70) is None


async def test_deferred_error_is_logged_not_raised(hass, caplog):
    miner = _Miner()
    gate = ThrottleGate(hass, miner.send, INTERVAL)
    await gate.async_request(80)
    miner.result = VnishApiError("Connection error")
    await gate.async_request(70)
    with caplog.at_level(logging.WARNING):
        await _drain(gate)
    assert "Deferred throttle 70% failed" in caplog.text
    assert gate._task is None


async def test_cancel_drops_the_pending_value(hass):
    miner = _Miner()
    gate = ThrottleGate(hass, miner.send, 10)
    await gate.async_request(80)
    await gate.async_request(70)
    gate.cancel()
    await asyncio.sleep(0)
    assert miner.calls == [80]
    assert gate._task is None
    assert gate.pending is None


async def _setup(hass):
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN, title="T",
        data={CONF_HOST: MOCK_HOST}, source=config_entries.SOURCE_USER,
        options={}, unique_id=MOCK_HOST, discovery_keys={}, subentries_data={},
    )
    with patch("custom_components.vnish.coordinator.THROTTLE_MIN_INTERVAL", INTERVAL), \
         patch("custom_components.vnish.api.VnishApiClient.get_info", new_callable=AsyncMock, return_value=MOCK_INFO), \
         patch("custom_components.vnish.api.VnishApiClient.get_summary", new_callable=AsyncMock, return_value=MOCK_SUMMARY):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return entry


async def test_number_burst_reaches_miner_twice(hass):
    """Three set_value calls in a row: two commands, the last value wins,
    and the queued calls return without waiting out the pause."""
    entry = await _setup(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]

    with patch(
        "custom_components.vnish.api.VnishApiClient.mining_throttle",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_throttle, patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        for value in (92, 95, 96):
            await hass.services.async_call(
                "number", "set_value",
                {"entity_id": NUMBER_ID, "value": value}, blocking=True,
            )
        assert [c.args for c in mock_throttle.call_args_list] == [(92,)]
        # The slider shows the value that is going to be applied.
        assert float(hass.states.get(NUMBER_ID).state) == 96

        await _drain(coordinator.throttle_gate)
        assert [c.args for c in mock_throttle.call_args_list] == [(92,), (96,)]


async def test_unload_cancels_a_queued_throttle(hass):
    entry = await _setup(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    gate = coordinator.throttle_gate
    with patch(
        "custom_components.vnish.api.VnishApiClient.mining_throttle",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_throttle:
        gate._interval = 10
        await gate.async_request(90)
        await gate.async_request(80)
        assert await hass.config_entries.async_unload(entry.entry_id)
        await asyncio.sleep(0)
        assert [c.args for c in mock_throttle.call_args_list] == [(90,)]
        assert gate._task is None
