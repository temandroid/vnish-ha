"""Shared fixtures and mock data for vnish-ha tests."""
from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True, scope="session")
def _warm_pycares_shutdown_thread():
    """Pre-start the aiodns/pycares DNS-shutdown daemon thread.

    pycares starts a daemon thread lazily the first time a DNS channel is
    destroyed (HA's aiohttp session uses the aiodns resolver). HA's per-test
    ``verify_cleanup`` snapshots threads before each test and fails if a new
    one appears, so whichever test first triggers it would spuriously error.
    Starting it once up-front (before any per-test snapshot) keeps it out of
    the diff. Not a defect in the integration — purely test-harness hygiene.
    """
    try:
        import pycares

        pycares._shutdown_manager.start()
    except Exception:  # noqa: BLE001 — best-effort warm-up only
        pass
    yield


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the vnish custom integration in every test."""
    yield


MOCK_HOST = "192.168.1.100"
MOCK_API_KEY = "test-api-key"

MOCK_INFO = {
    "miner": "Antminer S19k Pro",
    "model": "s19kpro",
    "fw_name": "Vnish",
    "fw_version": "1.3.3",
    "algorithm": "sha256d",
    "hr_measure": "GH/s",
    "serial": "TEST000000000001",
    "platform": "aml",
    "install_type": "nand",
    "build_time": "2026-05-22 04:37:48",
    "build_uuid": "00000000-0000-0000-0000-000000000000",
    "build_name": "vnishnet",
    "system": {
        "os": "GNU/Linux",
        "miner_name": "test-miner",
        "mem_total": 243704,
        "mem_free": 144892,
        "mem_free_percent": 59,
        "mem_buf": 51628,
        "mem_buf_percent": 21,
        "network_status": {
            "mac": "02:00:00:00:00:01",
            "dhcp": True,
            "ip": MOCK_HOST,
            "netmask": "255.255.255.0",
            "gateway": "192.168.1.1",
            "dns": ["8.8.8.8"],
            "hostname": "Antminer",
        },
        "uptime": "1:00",
    },
}

MOCK_SUMMARY = {
    "miner": {
        "miner_status": {
            "miner_state": "mining",
            "throttled": 100,
            "miner_state_time": 3600,
        },
        "miner_type": "Antminer S19k Pro (Vnish 1.3.3)",
        "hr_stock": 138364,
        "average_hashrate": 23.15,
        "instant_hashrate": 22.97,
        "hr_realtime": 22977.2,
        "hr_nominal": 23471.0,
        "hr_average": 23151.8,
        "pcb_temp": {"min": 43, "max": 50},
        "chip_temp": {"min": 58, "max": 65},
        "power_consumption": 683,
        "power_usage": 683,
        "power_efficiency": 29.5,
        "hw_errors_percent": 0.0,
        "hr_error": 0.0,
        "hw_errors": 1,
        "devfee_percent": 2.8,
        "devfee": 644.0,
        "restart_count": 0,
        "found_blocks": 0,
        "best_share": 0,
        "cooling": {
            "fan_duty": 50,
            "fan_num": 2,
            "fans": [
                {"id": 0, "rpm": 3000, "max_rpm": 6000, "status": "ok"},
                {"id": 1, "rpm": 3010, "max_rpm": 6000, "status": "ok"},
            ],
        },
        "pools": [
            {
                "id": 0,
                "url": "btc.pool.example.com:3333",
                "pool_type": "UserPool",
                "user": "worker1",
                "status": "active",
                "asic_boost": True,
                "diff": "65.5K",
                "accepted": 3897,
                "rejected": 14,
                "stale": 5,
                "ls_diff": 65526,
                "ls_time": "0:00:10",
                "diffa": 250014453,
                "ping": 51,
            },
            {
                "id": 1,
                "url": "btc.backup.example.com:3333",
                "pool_type": "UserPool",
                "user": "worker1",
                "status": "working",
                "asic_boost": True,
                "diff": "16.4K",
                "accepted": 0,
                "rejected": 0,
                "stale": 0,
                "ls_diff": 0,
                "ls_time": "0",
                "diffa": 0,
                "ping": 0,
            },
        ],
        "chains": [],
        "psu": None,
    }
}

MOCK_SUMMARY_STOPPED = {
    "miner": {
        **MOCK_SUMMARY["miner"],
        "miner_status": {
            "miner_state": "stopped",
            "throttled": 0,
            "miner_state_time": 0,
        },
    }
}


@pytest.fixture
def mock_api():
    """Patch VnishApiClient with mock responses."""
    with patch(
        "custom_components.vnish.api.VnishApiClient.get_info",
        new_callable=AsyncMock,
        return_value=MOCK_INFO,
    ), patch(
        "custom_components.vnish.api.VnishApiClient.get_summary",
        new_callable=AsyncMock,
        return_value=MOCK_SUMMARY,
    ):
        yield
