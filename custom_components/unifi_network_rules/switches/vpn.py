"""VPN switches for UniFi Network Rules integration."""
from __future__ import annotations

from typing import Any, Dict

from .base import UnifiRuleSwitch
from ..coordinator import UnifiRuleUpdateCoordinator
from ..models.vpn_config import VPNConfig


class UnifiVPNClientSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi VPN client."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: VPNConfig,
        rule_type: str = "vpn_clients",
        entry_id: str = None,
    ) -> None:
        """Initialize VPN client switch."""
        # Call parent init first
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        
        # Customize properties after parent init
        vpn_type = "WireGuard" if rule_data.is_wireguard else "OpenVPN"
        self._attr_name = f"{vpn_type} VPN: {rule_data.display_name}"
        
        # Set appropriate icon
        if rule_data.is_wireguard:
            self._attr_icon = "mdi:vpn"
        elif rule_data.is_openvpn:
            self._attr_icon = "mdi:security-network"
        else:
            self._attr_icon = "mdi:vpn"
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return entity specific state attributes."""
        attributes = {}
        
        # Get current rule from coordinator data
        current_client = self._get_current_rule()
        
        if not current_client:
            return attributes
        
        # Add core attributes
        attributes["vpn_type"] = current_client.vpn_type
        attributes["name"] = current_client.name
        
        # Add connection status if available
        if hasattr(current_client, "connection_status") and current_client.connection_status:
            attributes["connection_status"] = current_client.connection_status
        
        # Type-specific attributes
        if current_client.is_wireguard:
            attributes["wireguard_endpoint"] = current_client.wireguard.get("endpoint", "")
        elif current_client.is_openvpn:
            config_file = current_client.openvpn.get("configuration_filename", "")
            if config_file:
                attributes["openvpn_config"] = config_file
        
        return attributes


class UnifiVPNServerSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi VPN server."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: VPNConfig,
        rule_type: str = "vpn_servers",
        entry_id: str = None,
    ) -> None:
        """Initialize VPN server switch."""
        # Call parent init first
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        
        # Customize properties after parent init
        vpn_type = "WireGuard" if rule_data.is_wireguard else "OpenVPN"
        self._attr_name = f"{vpn_type} VPN Server: {rule_data.display_name}"
        
        # Set appropriate icon - using distinct icons for servers
        if rule_data.is_wireguard:
            self._attr_icon = "mdi:server-network"
        elif rule_data.is_openvpn:
            self._attr_icon = "mdi:shield-lock-outline"
        else:
            self._attr_icon = "mdi:server-security"
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return entity specific state attributes."""
        attributes = {}
        
        # Get current rule from coordinator data
        current_server = self._get_current_rule()
        
        if not current_server:
            return attributes
        
        # Add core attributes
        attributes["vpn_type"] = current_server.vpn_type
        attributes["name"] = current_server.name
        
        # Add connection status if available
        if hasattr(current_server, "connection_status") and current_server.connection_status:
            attributes["status"] = current_server.connection_status
        
        # Type-specific attributes
        if current_server.is_wireguard:
            attributes["port"] = current_server.server.get("port", "")
            attributes["interface"] = current_server.server.get("interface", "")
        elif current_server.is_openvpn:
            attributes["port"] = current_server.server.get("port", "")
            attributes["protocol"] = current_server.server.get("protocol", "")
        
        # Add network info
        if current_server.server.get("subnet"):
            attributes["subnet"] = current_server.server.get("subnet")
        
        return attributes
