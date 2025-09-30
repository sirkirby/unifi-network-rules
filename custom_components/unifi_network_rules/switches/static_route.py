"""Static route switches for UniFi Network Rules integration."""
from __future__ import annotations

from typing import Any

from .base import UnifiRuleSwitch
from ..coordinator import UnifiRuleUpdateCoordinator


class UnifiStaticRouteSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi static route."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize static route switch."""
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Set icon for static route rules
        self._attr_icon = "mdi:map-marker-path"
