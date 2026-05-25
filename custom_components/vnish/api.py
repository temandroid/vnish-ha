from __future__ import annotations

import aiohttp
from typing import Any


class VnishApiError(Exception):
    pass


class VnishApiClient:
    def __init__(self, host: str, api_key: str | None, session: aiohttp.ClientSession) -> None:
        self._base = f"http://{host}/api/v1"
        self._headers: dict[str, str] = {"x-api-key": api_key} if api_key else {}
        self._session = session
        self.host = host

    _TIMEOUT = aiohttp.ClientTimeout(total=10)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base}{path}"
        try:
            async with self._session.request(
                method, url, headers=self._headers, timeout=self._TIMEOUT, **kwargs
            ) as resp:
                resp.raise_for_status()
                if resp.content_type == "application/json":
                    return await resp.json()
                return None
        except aiohttp.ClientResponseError as err:
            raise VnishApiError(f"HTTP {err.status} for {path}") from err
        except aiohttp.ClientError as err:
            raise VnishApiError(str(err)) from err

    async def get_summary(self) -> dict:
        return await self._request("GET", "/summary")

    async def get_info(self) -> dict:
        return await self._request("GET", "/info")

    async def get_status(self) -> dict:
        return await self._request("GET", "/status")

    async def mining_start(self) -> None:
        await self._request("POST", "/mining/start")

    async def mining_stop(self) -> None:
        await self._request("POST", "/mining/stop")

    async def mining_pause(self) -> None:
        await self._request("POST", "/mining/pause")

    async def mining_resume(self) -> None:
        await self._request("POST", "/mining/resume")

    async def mining_restart(self) -> None:
        await self._request("POST", "/mining/restart")

    async def system_reboot(self) -> None:
        await self._request("POST", "/system/reboot")

    async def switch_pool(self, pool_id: int) -> None:
        await self._request("POST", "/mining/switch-pool", json={"pool_id": pool_id})
