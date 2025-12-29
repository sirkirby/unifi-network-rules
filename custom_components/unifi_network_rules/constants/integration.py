"""Integration constants for UniFi Network Rules."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

# Integration
DOMAIN: Final = "unifi_network_rules"
DEFAULT_NAME: Final = "UniFi Network Rules"
MANUFACTURER: Final = "Ubiquiti, Inc."

# Platforms
PLATFORMS: Final = [Platform.SWITCH]

# Default values
DEFAULT_SITE: Final = "default"
DEFAULT_PORT: Final = 443

# Timers and retry values
DEFAULT_UPDATE_INTERVAL: Final = 300  # 5 minutes - smart polling manages real-time updates
DEFAULT_RETRY_TIMER: Final = 30  # seconds - Time between retries for failed commands
DEFAULT_TIMEOUT: Final = 10

# Maximum number of failed attempts
MAX_FAILED_ATTEMPTS: Final = 5

# Rate limiting and delays
MIN_REQUEST_INTERVAL: Final = 2.0
STATE_VERIFICATION_SLEEP_SECONDS: Final = 2
SWITCH_DELAYED_VERIFICATION_SLEEP_SECONDS: Final = 20
# Must be > SWITCH_DELAYED_VERIFICATION_SLEEP_SECONDS + typical API response time
# to prevent cleanup racing with delayed verification (see issue #136)
HA_INITIATED_OPERATION_TIMEOUT_SECONDS: Final = 30
