from __future__ import annotations

import asyncio
import logging

import aiohttp
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Exceptions raised by aiohttp on a total-timeout are bare asyncio.TimeoutError
# (an OSError subclass since 3.11), NOT aiohttp.ClientError — so we catch both.
_NETWORK_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError)


class VnishApiError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class VnishAuthError(VnishApiError):
    pass


class VnishApiClient:
    _TIMEOUT = aiohttp.ClientTimeout(total=10)

    def __init__(
        self,
        host: str,
        api_key: str | None,
        password: str | None,
        session: aiohttp.ClientSession,
    ) -> None:
        self._base = f"http://{host}/api/v1"
        self._api_key = api_key
        self._password = password
        self._session = session
        self.host = host
        self._headers: dict[str, str] = self._base_headers()
        self._auth_epoch = 0
        self._login_lock = asyncio.Lock()

    def _base_headers(self) -> dict[str, str]:
        """Headers present regardless of JWT state (x-api-key never expires)."""
        return {"x-api-key": self._api_key} if self._api_key else {}

    async def login(self) -> None:
        """Force a login (used at setup for fail-fast credential validation)."""
        async with self._login_lock:
            await self._do_login()

    async def _ensure_fresh_auth(self, seen_epoch: int) -> None:
        """Re-login unless another task already refreshed the token.

        Serialised by a lock and guarded by an epoch counter so two concurrent
        401s produce a single POST /unlock instead of duelling logins that can
        invalidate each other's token on single-session firmware.
        """
        async with self._login_lock:
            if self._auth_epoch != seen_epoch:
                return
            await self._do_login()

    async def _do_login(self) -> None:
        url = f"{self._base}/unlock"
        try:
            async with self._session.request(
                "POST", url, json={"pw": self._password}, timeout=self._TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise VnishAuthError(
                        f"Authentication failed (HTTP {resp.status})", status=resp.status
                    )
                resp.raise_for_status()
                data = await resp.json()
        except VnishAuthError:
            raise
        except aiohttp.ClientResponseError as err:
            raise VnishApiError(f"HTTP {err.status} for /unlock", status=err.status) from err
        except _NETWORK_ERRORS as err:
            raise VnishApiError(f"Connection error for /unlock: {err}") from err
        except ValueError as err:
            raise VnishApiError(f"Invalid JSON from /unlock: {err}") from err
        if not isinstance(data, dict) or not data.get("token"):
            raise VnishAuthError("No token in /unlock response")
        headers = self._base_headers()
        headers["Authorization"] = f"Bearer {data['token']}"
        self._headers = headers
        self._auth_epoch += 1

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base}{path}"
        epoch_at_401: int | None = None
        for attempt in range(2):
            # Re-login at the START of the retry iteration so the previous
            # response context manager is already closed before we open a
            # new connection to /unlock.
            if attempt == 1 and self._password and epoch_at_401 is not None:
                await self._ensure_fresh_auth(epoch_at_401)
            try:
                async with self._session.request(
                    method, url, headers=self._headers, timeout=self._TIMEOUT, **kwargs
                ) as resp:
                    if resp.status == 401 and self._password and attempt == 0:
                        # Token likely expired: remember the epoch we saw, exit
                        # the context manager cleanly, then re-login & retry.
                        epoch_at_401 = self._auth_epoch
                        continue
                    if resp.status in (401, 403):
                        raise VnishAuthError(
                            f"Authentication failed (HTTP {resp.status})",
                            status=resp.status,
                        )
                    resp.raise_for_status()
                    if resp.content_type == "application/json":
                        return await resp.json()
                    return None
            except VnishAuthError:
                raise
            except aiohttp.ClientResponseError as err:
                raise VnishApiError(f"HTTP {err.status} for {path}", status=err.status) from err
            except _NETWORK_ERRORS as err:
                raise VnishApiError(f"Connection error for {path}: {err}") from err
            except ValueError as err:
                raise VnishApiError(f"Invalid JSON for {path}: {err}") from err
        # Unreachable: attempt 0 may `continue`, but attempt 1 always returns or
        # raises above. Guard against silent None just in case.
        raise VnishAuthError("Authentication failed after retry", status=401)

    async def _command(self, path: str, **kwargs: Any) -> None:
        """Send a control command; HTTP 500 is treated as a warning (not an error).

        Vnish firmware returns exactly HTTP 500 when a command is not applicable
        in the current state (e.g. start while already mining).  Raising an
        exception in that case breaks HA automations, so we swallow it and log.
        All other errors (network, auth, 503/504, …) still propagate normally.
        """
        try:
            await self._request("POST", path, **kwargs)
        except VnishAuthError:
            raise
        except VnishApiError as err:
            if err.status == 500:
                _LOGGER.warning(
                    "Control command %s returned HTTP 500 — firmware rejected "
                    "the command in the current state (ignored)",
                    path,
                )
            else:
                raise

    async def get_summary(self) -> dict:
        return await self._request("GET", "/summary")

    async def get_info(self) -> dict:
        return await self._request("GET", "/info")

    async def mining_start(self) -> None:
        await self._command("/mining/start")

    async def mining_stop(self) -> None:
        await self._command("/mining/stop")

    async def mining_pause(self) -> None:
        await self._command("/mining/pause")

    async def mining_resume(self) -> None:
        await self._command("/mining/resume")

    async def mining_restart(self) -> None:
        await self._command("/mining/restart")

    async def system_reboot(self) -> None:
        await self._command("/system/reboot")

    async def switch_pool(self, pool_id: int) -> None:
        await self._command("/mining/switch-pool", json={"pool_id": pool_id})
