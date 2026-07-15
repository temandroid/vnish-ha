from __future__ import annotations

import asyncio
import logging

import aiohttp
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Exceptions raised by aiohttp on a total-timeout are bare asyncio.TimeoutError
# (an OSError subclass since 3.11), NOT aiohttp.ClientError — so we catch both.
_NETWORK_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError)


def format_host(host: str) -> str:
    """Bracket a bare IPv6 literal so it can be embedded in a URL.

    'fe80::1' -> '[fe80::1]'. A host:port pair (one colon) and an already
    bracketed literal are left untouched.
    """
    if host.count(":") >= 2 and not host.startswith("["):
        return f"[{host}]"
    return host


class VnishApiError(Exception):
    def __init__(
        self, message: str, status: int | None = None, endpoint: str | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        # Which request produced this error. Lets callers tell an error from the
        # endpoint they asked for apart from one raised by an internal
        # sub-request such as the /unlock re-login.
        self.endpoint = endpoint


class VnishAuthError(VnishApiError):
    pass


class VnishApiClient:
    _TIMEOUT = aiohttp.ClientTimeout(total=10)
    # One initial try plus two retries: enough to survive a token that expires
    # mid-flight and a concurrent re-login racing us for it.
    _MAX_ATTEMPTS = 3

    def __init__(
        self,
        host: str,
        api_key: str | None,
        password: str | None,
        session: aiohttp.ClientSession,
    ) -> None:
        self._base = f"http://{format_host(host)}/api/v1"
        self._api_key = api_key
        self._password = password
        self._session = session
        # Raw host: identity key for entities/devices, never reformatted.
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

    async def _ensure_fresh_auth(self, sent_epoch: int) -> None:
        """Re-login unless another task already refreshed the token.

        `sent_epoch` is the epoch of the token whose request got the 401. If the
        epoch has moved on since, someone else already re-logged in and our
        retry will pick up their token — logging in again would only invalidate
        it on single-session firmware.
        """
        async with self._login_lock:
            if self._auth_epoch != sent_epoch:
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
                        f"Authentication failed (HTTP {resp.status})",
                        status=resp.status,
                        endpoint="/unlock",
                    )
                resp.raise_for_status()
                data = await resp.json()
        except VnishAuthError:
            raise
        except aiohttp.ClientResponseError as err:
            raise VnishApiError(
                f"HTTP {err.status} for /unlock", status=err.status, endpoint="/unlock"
            ) from err
        except _NETWORK_ERRORS as err:
            raise VnishApiError(
                f"Connection error for /unlock: {err}", endpoint="/unlock"
            ) from err
        except ValueError as err:
            raise VnishApiError(
                f"Invalid JSON from /unlock: {err}", endpoint="/unlock"
            ) from err
        if not isinstance(data, dict) or not data.get("token"):
            raise VnishAuthError("No token in /unlock response", endpoint="/unlock")
        headers = self._base_headers()
        headers["Authorization"] = f"Bearer {data['token']}"
        self._headers = headers
        self._auth_epoch += 1

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base}{path}"
        stale_epoch: int | None = None
        for attempt in range(self._MAX_ATTEMPTS):
            if stale_epoch is not None:
                # Re-login here, outside the previous response's context manager,
                # so that connection is already released.
                await self._ensure_fresh_auth(stale_epoch)
                stale_epoch = None
            # Epoch of the token we are about to send. Sampling it BEFORE the
            # request is what makes the guard correct: if a concurrent task
            # re-logs in while we are in flight, our 401 refers to the old token
            # and _ensure_fresh_auth will skip a redundant second login.
            sent_epoch = self._auth_epoch
            is_last = attempt == self._MAX_ATTEMPTS - 1
            try:
                async with self._session.request(
                    method, url, headers=self._headers, timeout=self._TIMEOUT, **kwargs
                ) as resp:
                    if resp.status == 401 and self._password and not is_last:
                        # Token likely expired: remember which token we sent,
                        # exit the context manager cleanly, then re-login & retry.
                        stale_epoch = sent_epoch
                        continue
                    if resp.status in (401, 403):
                        raise VnishAuthError(
                            f"Authentication failed (HTTP {resp.status})",
                            status=resp.status,
                            endpoint=path,
                        )
                    resp.raise_for_status()
                    if resp.content_type == "application/json":
                        return await resp.json()
                    return None
            except VnishAuthError:
                raise
            except aiohttp.ClientResponseError as err:
                raise VnishApiError(
                    f"HTTP {err.status} for {path}", status=err.status, endpoint=path
                ) from err
            except _NETWORK_ERRORS as err:
                raise VnishApiError(
                    f"Connection error for {path}: {err}", endpoint=path
                ) from err
            except ValueError as err:
                raise VnishApiError(
                    f"Invalid JSON for {path}: {err}", endpoint=path
                ) from err
        # Unreachable: the last attempt never `continue`s. Guard against None.
        raise VnishAuthError(
            "Authentication failed after retry", status=401, endpoint=path
        )

    async def _command(self, path: str, **kwargs: Any) -> bool:
        """Send a control command; return True if the miner accepted it.

        Vnish firmware returns exactly HTTP 500 *from the command endpoint* when
        a command is not applicable in the current state (e.g. start while
        already mining). Raising there would break HA automations, so that one
        case is swallowed and reported as False. Everything else still
        propagates — including a 500 raised by the internal /unlock re-login,
        which must never be mistaken for "command not applicable".
        """
        try:
            await self._request("POST", path, **kwargs)
        except VnishAuthError:
            raise
        except VnishApiError as err:
            if err.status == 500 and err.endpoint == path:
                _LOGGER.warning(
                    "Control command %s returned HTTP 500 — firmware rejected "
                    "the command in the current state (ignored)",
                    path,
                )
                return False
            raise
        return True

    async def get_summary(self) -> Any:
        return await self._request("GET", "/summary")

    async def get_info(self) -> Any:
        return await self._request("GET", "/info")

    async def mining_start(self) -> bool:
        return await self._command("/mining/start")

    async def mining_stop(self) -> bool:
        return await self._command("/mining/stop")

    async def mining_pause(self) -> bool:
        return await self._command("/mining/pause")

    async def mining_resume(self) -> bool:
        return await self._command("/mining/resume")

    async def mining_restart(self) -> bool:
        return await self._command("/mining/restart")

    async def system_reboot(self) -> bool:
        return await self._command("/system/reboot")

    async def switch_pool(self, pool_id: Any) -> bool:
        return await self._command("/mining/switch-pool", json={"pool_id": pool_id})
