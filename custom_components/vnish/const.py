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

ACTIVE_MINING_STATES = frozenset(
    {"mining", "starting", "initializing", "auto-tuning", "restarting"}
)
