"""NAT switches for UniFi Network Rules integration."""

from __future__ import annotations

from typing import Any

from ..coordinator import UnifiRuleUpdateCoordinator
from .base import UnifiRuleSwitch


class UnifiNATRuleSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi NAT rule."""

    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize NAT rule switch."""
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Icon differs by type (SNAT vs DNAT) if available in raw
        nat_type = None
        try:
            if hasattr(rule_data, "raw"):
                nat_type = rule_data.raw.get("type")
            elif isinstance(rule_data, dict):
                nat_type = rule_data.get("type")
        except Exception:
            nat_type = None

        if nat_type == "SNAT":
            self._attr_icon = "mdi:swap-horizontal"
        elif nat_type == "DNAT":
            self._attr_icon = "mdi:swap-vertical"
        else:
            # Default neutral NAT icon if type missing/unknown
            self._attr_icon = "mdi:swap-horizontal"
