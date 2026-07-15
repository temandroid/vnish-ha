"""Unit tests for VnishApiClient: command semantics and the auth/retry engine.

These exercise _request/_do_login/_command directly against a scripted fake
session, which the entity-level tests never reach (they patch the high-level
mining_*/get_summary methods wholesale).
"""
import asyncio

import aiohttp
import pytest
from multidict import CIMultiDict
from yarl import URL

from custom_components.vnish.api import (
    VnishApiClient,
    VnishApiError,
    VnishAuthError,
    format_host,
)

HOST = "10.0.0.7"
BASE = f"http://{HOST}/api/v1"


def _req_info(url: str = "http://x/") -> aiohttp.RequestInfo:
    u = URL(url)
    return aiohttp.RequestInfo(u, "GET", CIMultiDict(), u)


class _Resp:
    """A scripted aiohttp-like response usable as an async context manager."""

    def __init__(self, status=200, payload=None, content_type="application/json"):
        self.status = status
        self._payload = payload
        self.content_type = content_type

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=_req_info(), history=(), status=self.status
            )

    async def __aenter__(self):
        # A real request always yields to the loop; without this, tasks never
        # interleave and concurrency tests would not exercise anything.
        await asyncio.sleep(0)
        return self

    async def __aexit__(self, *exc):
        return False


class _Raiser:
    """Fails on entry, the way aiohttp surfaces connection/timeout errors."""

    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Serves a scripted queue of responses per API path.

    The last entry for a path repeats, so a queue of [401, 200] means "fail the
    first call, succeed from then on".
    """

    def __init__(self, script: dict):
        self._script = {k: list(v) for k, v in script.items()}
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, url, **kwargs):
        path = str(url).split("/api/v1", 1)[-1]
        self.calls.append((method, path, dict(kwargs.get("headers") or {})))
        queue = self._script[path]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        return item

    def paths(self, path: str) -> int:
        return sum(1 for _, p, _ in self.calls if p == path)


def _client(session, *, api_key=None, password=None) -> VnishApiClient:
    return VnishApiClient(
        host=HOST, api_key=api_key, password=password, session=session
    )


# --- host formatting ----------------------------------------------------


def test_format_host_brackets_bare_ipv6():
    assert format_host("fe80::1") == "[fe80::1]"
    assert format_host("192.168.1.5") == "192.168.1.5"
    assert format_host("192.168.1.5:8080") == "192.168.1.5:8080"
    assert format_host("[fe80::1]:80") == "[fe80::1]:80"


def test_ipv6_host_builds_a_parsable_url():
    """A bare IPv6 literal must not produce an unusable base URL."""
    client = _client(_FakeSession({}))
    client_v6 = VnishApiClient(
        host="fe80::1", api_key=None, password=None, session=_FakeSession({})
    )
    assert URL(f"{client_v6._base}/summary").host == "fe80::1"
    # The raw host stays untouched: it keys entity/device unique_ids.
    assert client_v6.host == "fe80::1"
    assert client.host == HOST


# --- _command semantics -------------------------------------------------


async def test_command_swallows_500_from_the_command_endpoint():
    """HTTP 500 from the command itself means 'not applicable in current state'."""
    session = _FakeSession({"/mining/start": [_Resp(status=500)]})
    assert await _client(session).mining_start() is False


async def test_command_propagates_503():
    """503/504 are infrastructure errors and must not be mistaken for a no-op."""
    session = _FakeSession({"/mining/start": [_Resp(status=503)]})
    with pytest.raises(VnishApiError) as err:
        await _client(session).mining_start()
    assert err.value.status == 503


async def test_command_accepted_returns_true():
    session = _FakeSession({"/mining/start": [_Resp(status=200, payload={})]})
    assert await _client(session).mining_start() is True


async def test_command_does_not_swallow_500_from_the_unlock_subrequest():
    """A 500 from the re-login must not be reported as 'command rejected'.

    Otherwise an auth failure silently looks like a successful no-op and the
    miner never reboots.
    """
    session = _FakeSession(
        {
            "/system/reboot": [_Resp(status=401)],
            "/unlock": [_Resp(status=500)],
        }
    )
    with pytest.raises(VnishApiError) as err:
        await _client(session, password="pw").system_reboot()
    assert err.value.endpoint == "/unlock"


async def test_command_propagates_auth_error():
    session = _FakeSession({"/mining/stop": [_Resp(status=403)]})
    with pytest.raises(VnishAuthError):
        await _client(session).mining_stop()


# --- auth / retry engine ------------------------------------------------


async def test_401_triggers_relogin_and_retry():
    """Expired token: 401 -> POST /unlock -> retry with the fresh token."""
    session = _FakeSession(
        {
            "/summary": [_Resp(status=401), _Resp(payload={"miner": {"ok": True}})],
            "/unlock": [_Resp(payload={"token": "T1"})],
        }
    )
    client = _client(session, password="pw")
    assert await client.get_summary() == {"miner": {"ok": True}}
    assert session.paths("/unlock") == 1
    # The retry carried the new bearer token.
    assert session.calls[-1][2]["Authorization"] == "Bearer T1"


async def test_concurrent_401s_produce_a_single_login():
    """Two racing requests holding the same expired token log in once.

    Both sample the same auth epoch before sending; whoever wins the lock
    re-logs in and the other must notice the epoch moved and reuse that token.
    A second /unlock would invalidate the first on single-session firmware and
    surface as a spurious re-auth prompt.
    """
    session = _FakeSession(
        {
            "/summary": [_Resp(status=401), _Resp(payload={"a": 1})],
            "/info": [_Resp(status=401), _Resp(payload={"b": 2})],
            "/unlock": [_Resp(payload={"token": "T1"})],
        }
    )
    client = _client(session, password="pw")
    assert await asyncio.gather(client.get_summary(), client.get_info()) == [
        {"a": 1},
        {"b": 2},
    ]
    assert session.paths("/unlock") == 1


async def test_api_key_401_is_classified_as_auth_error():
    """Without a password there is no re-login, but a 401 is still an auth failure."""
    session = _FakeSession({"/summary": [_Resp(status=401)]})
    with pytest.raises(VnishAuthError):
        await _client(session, api_key="bad").get_summary()


async def test_api_key_survives_a_jwt_login():
    """Logging in must merge, not replace, the base headers."""
    session = _FakeSession({"/unlock": [_Resp(payload={"token": "T1"})]})
    client = _client(session, api_key="K", password="pw")
    await client.login()
    assert client._headers["x-api-key"] == "K"
    assert client._headers["Authorization"] == "Bearer T1"


async def test_login_rejects_a_response_without_a_token():
    session = _FakeSession({"/unlock": [_Resp(payload={"nope": 1})]})
    with pytest.raises(VnishAuthError):
        await _client(session, password="pw").login()


async def test_login_rejects_a_non_dict_body():
    session = _FakeSession({"/unlock": [_Resp(payload=["not", "a", "dict"])]})
    with pytest.raises(VnishAuthError):
        await _client(session, password="pw").login()


# --- error classification -----------------------------------------------


async def test_timeout_is_wrapped_not_leaked():
    """aiohttp's total-timeout raises asyncio.TimeoutError, NOT a ClientError.

    Leaking it aborts setup into SETUP_ERROR with no retry.
    """
    session = _FakeSession({"/summary": [_Raiser(asyncio.TimeoutError())]})
    with pytest.raises(VnishApiError):
        await _client(session).get_summary()


async def test_connection_error_is_wrapped():
    session = _FakeSession({"/summary": [_Raiser(aiohttp.ClientError("boom"))]})
    with pytest.raises(VnishApiError):
        await _client(session).get_summary()


async def test_malformed_json_is_wrapped():
    session = _FakeSession({"/summary": [_Resp(payload=ValueError("bad json"))]})
    with pytest.raises(VnishApiError):
        await _client(session).get_summary()


async def test_non_json_response_returns_none():
    session = _FakeSession({"/summary": [_Resp(content_type="text/html")]})
    assert await _client(session).get_summary() is None
