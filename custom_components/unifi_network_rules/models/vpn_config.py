"""VPN configuration model for UniFi Network Rules integration."""
from __future__ import annotations

from typing import Any, Dict

class VPNConfig:
    """Representation of a VPN configuration (client or server)."""
    
    def __init__(self, data: Dict[str, Any]) -> None:
        """Initialize a VPN configuration from raw data."""
        self.raw = data
        self._id = data.get("_id")
        self.enabled = data.get("enabled", False)
        self.name = data.get("name", "")
        self.purpose = data.get("purpose", "")
        self.vpn_type = data.get("vpn_type", "")
        self.site_id = data.get("site_id", "")
        self.firewall_zone_id = data.get("firewall_zone_id", "")
        
        # OpenVPN specific fields
        self.openvpn = {
            "id": data.get("openvpn_id"),
            "configuration": data.get("openvpn_configuration", ""),
            "configuration_status": data.get("openvpn_configuration_status", ""),
            "configuration_filename": data.get("openvpn_configuration_filename", ""),
            "username": data.get("openvpn_username", ""),
            "password": data.get("openvpn_password", "")  # Will be masked in logs
        }
        
        # WireGuard specific fields - check for nested dicts
        wg_config = {}
        if "wireguard_client_peer" in data and isinstance(data["wireguard_client_peer"], dict):
            wg_config = data["wireguard_client_peer"]
        
        self.wireguard = {
            "id": data.get("wireguard_id"),
            "client_mode": data.get("wireguard_client_mode", ""),
            "configuration_file": data.get("wireguard_client_configuration_file", ""),
            "configuration_filename": data.get("wireguard_client_configuration_filename", ""),
            "public_key": wg_config.get("public_key", data.get("wireguard_public_key", "")),
            "private_key": wg_config.get("private_key", data.get("wireguard_private_key", "")),
            "endpoint": wg_config.get("endpoint", data.get("wireguard_endpoint", "")),
            "allowed_ips": wg_config.get("allowed_ips", data.get("wireguard_allowed_ips", [])),
            "persistent_keepalive": wg_config.get("persistent_keepalive", data.get("wireguard_persistent_keepalive", 0))
        }
        
        # Server-specific fields (for server types)
        self.server = {
            "port": data.get("openvpn_port", data.get("wireguard_port", "")),
            "protocol": data.get("openvpn_protocol", ""),
            "subnet": data.get("subnet", ""),
            "interface": data.get("interface", ""),
            "network": data.get("network", ""),
            "mask": data.get("mask", ""),
        }
        
        # IP configuration
        self.ip_subnet = data.get("ip_subnet", "")
        
        # Status tracking
        self.connection_status = data.get("connection_status", "")
        self.last_seen = data.get("last_seen", None)
        self.uptime = data.get("uptime", 0)
    
    @property
    def id(self) -> str:
        """Get the ID of the VPN configuration."""
        return self._id
    
    @property
    def is_openvpn(self) -> bool:
        """Check if this is an OpenVPN configuration."""
        return self.vpn_type in ["openvpn-client", "openvpn-server"]
    
    @property
    def is_wireguard(self) -> bool:
        """Check if this is a WireGuard configuration."""
        return self.vpn_type in ["wireguard-client", "wireguard-server"]
    
    @property
    def is_client(self) -> bool:
        """Check if this is a client configuration."""
        from ..helpers.rule import classify_vpn_type
        is_client, _ = classify_vpn_type(self.purpose, self.vpn_type)
        return is_client
    
    @property
    def is_server(self) -> bool:
        """Check if this is a server configuration."""
        from ..helpers.rule import classify_vpn_type
        _, is_server = classify_vpn_type(self.purpose, self.vpn_type)
        return is_server
    
    @property
    def is_connected(self) -> bool:
        """Check if the VPN client is currently connected or server is running."""
        return self.connection_status == "connected" or self.connection_status == "up"
    
    @property
    def display_name(self) -> str:
        """Get a user-friendly display name."""
        if self.name:
            return self.name
        
        # For clients
        if self.is_client:
            if self.is_openvpn and self.openvpn["configuration_filename"]:
                return f"OpenVPN Client: {self.openvpn['configuration_filename']}"
            
            if self.is_wireguard and self.wireguard["configuration_filename"]:
                return f"WireGuard Client: {self.wireguard['configuration_filename']}"
        
        # For servers
        if self.is_server:
            if self.is_openvpn:
                port = self.server.get("port", "")
                return f"OpenVPN Server{f' (Port {port})' if port else ''}"
            
            if self.is_wireguard:
                port = self.server.get("port", "")
                return f"WireGuard Server{f' (Port {port})' if port else ''}"
            
        return f"VPN {self._id}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the VPN configuration to a dictionary for API requests.
        
        We're primarily concerned with updating the enabled state while
        preserving the original structure of the data to avoid unexpected
        side effects.
        """
        # Start with the original data to preserve all fields
        if not self.raw:
            # Fallback for cases where raw data might be missing
            return {"_id": self._id, "enabled": self.enabled}
            
        # Create a copy to avoid modifying the original
        result = self.raw.copy()
        
        # Only set the enabled state, which is what we primarily need to toggle
        result["enabled"] = self.enabled
        
        return result
    
    def __repr__(self) -> str:
        """Return string representation with sensitive data masked."""
        # Create a sanitized version for logging
        sensitive_fields = ["openvpn_password", "wireguard_private_key"]
        sanitized = self.raw.copy() if self.raw else {}
        
        for field in sensitive_fields:
            if field in sanitized:
                sanitized[field] = "***REDACTED***"
                
        return f"VPNConfig({self.vpn_type}, {self.display_name}, enabled={self.enabled})"