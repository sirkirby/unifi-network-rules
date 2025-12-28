"""QoS switches for UniFi Network Rules integration."""

from __future__ import annotations

import logging
from typing import Any

from ..coordinator import UnifiRuleUpdateCoordinator
from .base import UnifiRuleSwitch

LOGGER = logging.getLogger(__name__)


class UnifiQoSRuleSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi QoS rule."""

    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize QoS rule switch."""
        LOGGER.info(
            "Initializing QoS rule switch with data: %s (type: %s)",
            getattr(rule_data, "id", "unknown"),
            type(rule_data).__name__,
        )
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Set icon for QoS rules
        self._attr_icon = "mdi:speedometer"
