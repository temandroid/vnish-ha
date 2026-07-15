from homeassistant.const import Platform

DOMAIN = "vnish"
PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.SELECT,
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
