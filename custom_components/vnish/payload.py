"""Readers for the Vnish `/summary` document.

Field names follow the miner OpenAPI (`AntmMinerStats`, `PoolStats`, `Cooling`,
`AntmBoard`, `AntmPsuTemps`).
"""

from __future__ import annotations

from .const import is_user_pool


def miner_of(data: dict | None) -> dict:
    """The `miner` object, or {} when it is missing or JSON null."""
    miner = (data or {}).get("miner")
    return miner if isinstance(miner, dict) else {}


def _int_id(value: object) -> int | None:
    """An integer id. Bool is a subclass of int and is never an id."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def fan_ids(data: dict | None) -> list[int]:
    cooling = miner_of(data).get("cooling")
    if not isinstance(cooling, dict):
        return []
    fans = cooling.get("fans")
    if not isinstance(fans, list):
        return []
    ids: list[int] = []
    for fan in fans:
        if not isinstance(fan, dict):
            continue
        fan_id = _int_id(fan.get("id"))
        if fan_id is not None and fan_id not in ids:
            ids.append(fan_id)
    return ids


def fan_by_id(data: dict | None, fan_id: int) -> dict:
    cooling = miner_of(data).get("cooling")
    if not isinstance(cooling, dict):
        return {}
    fans = cooling.get("fans")
    if not isinstance(fans, list):
        return {}
    for fan in fans:
        if isinstance(fan, dict) and fan.get("id") == fan_id:
            return fan
    return {}


def chain_ids(data: dict | None) -> list[int]:
    chains = miner_of(data).get("chains")
    if not isinstance(chains, list):
        return []
    ids: list[int] = []
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        chain_id = _int_id(chain.get("id"))
        if chain_id is not None and chain_id not in ids:
            ids.append(chain_id)
    return ids


def chain_by_id(data: dict | None, chain_id: int) -> dict:
    chains = miner_of(data).get("chains")
    if not isinstance(chains, list):
        return {}
    for chain in chains:
        if isinstance(chain, dict) and chain.get("id") == chain_id:
            return chain
    return {}


def psu_temp_keys(data: dict | None) -> list[str]:
    """PSU temperature fields that are actually reported (the object is nullable)."""
    psu = miner_of(data).get("psu")
    if not isinstance(psu, dict):
        return []
    temps = psu.get("temps")
    if not isinstance(temps, dict):
        return []
    return [
        key
        for key in ("pfc_temp", "llc1_temp", "llc2_temp")
        if _int_id(temps.get(key)) is not None
    ]


def active_user_pool(data: dict | None) -> dict:
    """The user pool the miner reports as active, or {} if none is.

    DevFee and Refund pools are skipped: the firmware can mark them `active`
    next to the user's pool, and their URL and share counts must not be shown
    as the active pool.

    No fallback to pools[0]: reporting an inactive pool as active is wrong, and
    it made these sensors contradict the pool select.
    """
    pools = miner_of(data).get("pools")
    if not isinstance(pools, list):
        return {}
    for pool in pools:
        if (
            isinstance(pool, dict)
            and is_user_pool(pool)
            and pool.get("status") == "active"
        ):
            return pool
    return {}
