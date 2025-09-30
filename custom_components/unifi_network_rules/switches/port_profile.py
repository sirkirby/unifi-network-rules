"""Port profile switches for UniFi Network Rules integration."""
from __future__ import annotations

from typing import Any, Dict

from .base import UnifiRuleSwitch
from ..coordinator import UnifiRuleUpdateCoordinator
from ..models.port_profile import PortProfile


class UnifiPortProfileSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi Port Profile.

    Treats a profile as enabled when it has a native network configured and
    management VLAN tagging is not blocking, per PortProfile.enabled.
    """

    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: PortProfile,
        rule_type: str = "port_profiles",
        entry_id: str | None = None,
    ) -> None:
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        self._attr_icon = "mdi:ethernet"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        attrs: Dict[str, Any] = {}
        profile = self._get_current_rule()
        if profile and hasattr(profile, "raw"):
            raw = profile.raw
            attrs["native_networkconf_id"] = raw.get("native_networkconf_id")
            attrs["tagged_vlan_mgmt"] = raw.get("tagged_vlan_mgmt")
            attrs["op_mode"] = raw.get("op_mode")
            attrs["poe_mode"] = raw.get("poe_mode")
        return attrs
