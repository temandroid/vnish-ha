"""Pacing for POST /mining/throttle.

Every accepted throttle command makes Vnish (seen on 1.3.5) re-apply the
performance preset, which takes ~10 s ("Switching preset …" → "Performance
settings setup completed" in /logs/miner). A second command that arrives in
that window is dropped with `WARN: Overclocking settings setup in progress`,
and the miner then raises `restart_required` and keeps running at a percent
that differs from the one the API reports. Three automation writes within one
second on 2026-11-06 left an S21+ Hydro at 448 TH/s / 6.6 kW while it claimed
92 %.

The gate below makes that impossible from Home Assistant, whoever writes:

* Commands are serialised and spaced by at least THROTTLE_MIN_INTERVAL,
  measured from the moment the previous command *returned*.
* A write that arrives while the gate is idle is sent at once and awaited, so
  the service call still reports a rejected or failed command as before.
* A write that arrives inside the pause is not sent and not awaited: it only
  replaces the pending value (latest wins), and a background task sends it when
  the pause is over. `number.set_value` returns immediately instead of hanging
  for up to 15 s, and a burst of N writes costs at most two commands on the
  miner — the first one and the last one.
* A pending value equal to the last accepted one is dropped: the miner is
  already there, and the extra command would only cost another preset cycle.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from homeassistant.core import HomeAssistant

from .api import VnishApiError

_LOGGER = logging.getLogger(__name__)


class ThrottleGate:
    def __init__(
        self,
        hass: HomeAssistant,
        send: Callable[[int], Awaitable[bool]],
        interval: float,
        on_sent: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._hass = hass
        self._send_fn = send
        self._interval = interval
        self._on_sent = on_sent
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0
        self._pending: int | None = None
        self._applied: int | None = None
        self._task: asyncio.Task | None = None

    @property
    def pending(self) -> int | None:
        """The value waiting for the pause to end, if any."""
        return self._pending

    async def async_request(self, percent: int) -> bool | None:
        """Ask for a throttle percent.

        Returns what the miner answered (True accepted / False rejected) when
        the command went out right away, or None when it was queued behind the
        pause and will be sent later by the background task.
        """
        if (
            self._task is None
            and not self._lock.locked()
            and time.monotonic() >= self._next_allowed
        ):
            async with self._lock:
                return await self._send(percent)

        self._pending = percent
        if self._task is None:
            self._task = self._hass.async_create_background_task(
                self._drain(), "vnish throttle gate"
            )
        _LOGGER.debug(
            "Throttle %s%% queued: the previous command is still being applied",
            percent,
        )
        return None

    async def _send(self, percent: int) -> bool:
        """Send one command. The caller holds the lock."""
        try:
            accepted = await self._send_fn(percent)
        finally:
            # Counted even for a failed or rejected request: the miner may have
            # started reconfiguring before the error reached us.
            self._next_allowed = time.monotonic() + self._interval
        if accepted:
            self._applied = percent
        return accepted

    async def _drain(self) -> None:
        try:
            while True:
                async with self._lock:
                    delay = self._next_allowed - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    percent, self._pending = self._pending, None
                    if percent is None:
                        return
                    if percent == self._applied:
                        _LOGGER.debug(
                            "Throttle %s%% already applied, not resending", percent
                        )
                        continue
                    try:
                        accepted = await self._send(percent)
                    except VnishApiError as err:
                        _LOGGER.warning(
                            "Deferred throttle %s%% failed: %s", percent, err
                        )
                        continue
                    if not accepted:
                        _LOGGER.warning(
                            "Deferred throttle %s%% was rejected by the miner",
                            percent,
                        )
                if self._on_sent is not None:
                    await self._on_sent()
        finally:
            if self._task is asyncio.current_task():
                self._task = None

    def cancel(self) -> None:
        """Drop the pending value and stop the background task (entry unload)."""
        self._pending = None
        if self._task is not None:
            self._task.cancel()
            self._task = None
