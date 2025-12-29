"""Port forwarding switches for UniFi Network Rules integration."""

from __future__ import annotations

from typing import Any

from ..coordinator import UnifiRuleUpdateCoordinator
from .base import UnifiRuleSwitch


class UnifiPortForwardSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi port forward rule."""

    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize port forward switch."""
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Set icon for port forward rules
        self._attr_icon = "mdi:network-pos"
