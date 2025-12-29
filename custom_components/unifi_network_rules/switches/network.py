"""Network switches for UniFi Network Rules integration."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError

from ..coordinator import UnifiRuleUpdateCoordinator
from ..models.network import NetworkConf
from .base import UnifiRuleSwitch


class UnifiWlanSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi wireless network."""

    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize WLAN switch."""
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Set icon for WLAN switches
        self._attr_icon = "mdi:wifi"


class UnifiNetworkSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi Network (LAN)."""

    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: NetworkConf,
        rule_type: str = "networks",
        entry_id: str | None = None,
    ) -> None:
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        self._attr_icon = "mdi:lan"

    async def _async_toggle_rule(self, enable: bool) -> None:
        network = self._get_current_rule()
        if network is None:
            raise HomeAssistantError(f"Cannot find network with ID: {self._rule_id}")

        # Optimistic
        self.mark_pending_operation(enable)
        self.async_write_ha_state()

        async def handle_operation_complete(f):
            try:
                ok = f.result()
                if not ok:
                    self.mark_pending_operation(not enable)
                self.async_write_ha_state()
            except Exception:
                self.mark_pending_operation(not enable)
                self.async_write_ha_state()

        # Queue via API
        async def toggle_wrapper(n: NetworkConf):
            # Force desired enabled in payload
            n.raw["enabled"] = enable
            return await self.coordinator.api.update_network(n)

        future = await self.coordinator.api.queue_api_operation(toggle_wrapper, network)
        future.add_done_callback(lambda f: self.hass.async_create_task(handle_operation_complete(f)))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        net = self._get_current_rule()
        if net and hasattr(net, "raw"):
            raw = net.raw
            attrs["purpose"] = raw.get("purpose")
            attrs["ip_subnet"] = raw.get("ip_subnet")
            attrs["vlan_enabled"] = raw.get("vlan_enabled")
            attrs["networkgroup"] = raw.get("networkgroup")
        return attrs
