"""Debug constants for UniFi Network Rules."""

from __future__ import annotations

import logging
from typing import Final

# Define logger
LOGGER = logging.getLogger(__package__.replace(".constants", ""))

# Debug related constants
DEBUG_WEBSOCKET: Final = False  # DEPRECATED

# Debugging flags - set specific flags to True only when troubleshooting that area
# These can also be enabled via configuration.yaml:
# logger:
#   logs:
#     custom_components.unifi_network_rules: debug
#     aiounifi: debug

# More targeted debugging flags - enable only what you need
LOG_WEBSOCKET: Final = False  # DEPRECATED
LOG_API_CALLS: Final = False  # API requests and responses
LOG_DATA_UPDATES: Final = False  # Data refresh and update cycles
LOG_ENTITY_CHANGES: Final = False  # Entity addition/removal/state changes
LOG_TRIGGERS: Final = False  # Trigger detection and firing logs
