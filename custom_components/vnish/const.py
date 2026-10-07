from homeassistant.const import Platform

DOMAIN = "vnish"
PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
]

CONF_API_KEY = "api_key"
CONF_PASSWORD = "password"
DEFAULT_SCAN_INTERVAL = 30

# How many coordinator updates an optimistic switch/select value may disagree
# with the miner's reported state before it is dropped. The miner's state
# machine takes seconds, but a command it silently never acts on must not be
# masked forever.
OPTIMISTIC_MAX_CYCLES = 3

ACTIVE_MINING_STATES = frozenset(
    {"mining", "starting", "initializing", "auto-tuning", "restarting"}
)

# ThrottleSettings.percent and MinerStatus.throttled, both inclusive.
THROTTLE_MIN = 20
THROTTLE_MAX = 100

# PoolStats.pool_type values that belong to the firmware, not the user.
# A missing pool_type is treated as a user pool: older firmware omitted it.
NON_USER_POOL_TYPES = frozenset({"DevFee", "Refund"})


def is_user_pool(pool: dict) -> bool:
    """Whether this pool is the user's, not a firmware DevFee/Refund pool."""
    return pool.get("pool_type") not in NON_USER_POOL_TYPES
