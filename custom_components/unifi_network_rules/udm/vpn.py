"""VPN management mixin for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from ..const import (
    LOGGER,
    API_PATH_NETWORK_CONF,
    API_PATH_NETWORK_CONF_DETAIL,
)
from ..models.vpn_config import VPNConfig

class VPNMixin:
    """Mixin to add VPN management capabilities to the UDMAPI class."""

    async def get_vpn_configs(self, include_clients=True, include_servers=True) -> List[VPNConfig]:
        """Get VPN configurations.
        
        Args:
            include_clients: Whether to include VPN clients in the results
            include_servers: Whether to include VPN servers in the results
            
        Returns:
            List of VPN configuration objects
        """
        config_types = []
        if include_clients:
            config_types.extend(["vpn-client", "openvpn-client", "wireguard-client"])
        if include_servers:
            config_types.extend(["vpn-server", "openvpn-server", "wireguard-server"])
            
        LOGGER.debug("Fetching VPN configurations (clients: %s, servers: %s)", include_clients, include_servers)
        
        try:
            # Create API request using the wrapper method in the base class
            request = self.create_api_request("GET", API_PATH_NETWORK_CONF)
            data = await self.controller.request(request)
            
            if not data or "data" not in data:
                LOGGER.warning("No response or invalid response from network configuration API")
                return []
                
            network_data = data.get("data", [])
            
            # Filter the network configurations to get requested VPN configs
            vpn_configs = []
            for network in network_data:
                purpose = network.get("purpose", "")
                vpn_type = network.get("vpn_type", "")
                
                # Check for both purpose and vpn_type to catch all VPN configs
                from ..helpers.rule import classify_vpn_type
                is_client, is_server = classify_vpn_type(purpose, vpn_type)
                
                if (include_clients and is_client) or (include_servers and is_server):
                    try:
                        vpn_config = VPNConfig(network)
                        vpn_configs.append(vpn_config)
                        LOGGER.debug(f"Found VPN config: {vpn_config.display_name} (Type: {vpn_config.vpn_type})")
                    except Exception as config_err:
                        LOGGER.error(f"Error creating VPN config from data: {config_err}")
                    
            LOGGER.debug(f"Found {len(vpn_configs)} VPN configurations")
            return vpn_configs
            
        except Exception as err:
            LOGGER.error(f"Error fetching VPN configurations: {err}")
            return []
    
    async def get_vpn_clients(self) -> List[VPNConfig]:
        """Get VPN client connections.
        
        Returns:
            List of VPN client objects
        """
        LOGGER.debug("Fetching VPN client connections")
        return await self.get_vpn_configs(include_clients=True, include_servers=False)
    
    async def get_vpn_servers(self) -> List[VPNConfig]:
        """Get VPN server configurations.
        
        Returns:
            List of VPN server objects
        """
        LOGGER.debug("Fetching VPN server configurations")
        return await self.get_vpn_configs(include_clients=False, include_servers=True)
            
    async def add_vpn_config(self, config_data: Dict[str, Any]) -> Optional[VPNConfig]:
        """Add a new VPN configuration.
        
        Args:
            config_data: Dictionary with the VPN configuration
            
        Returns:
            VPNConfig object if successful, None otherwise
        """
        # Determine if this is a client or server based on vpn_type or purpose
        is_server = False
        vpn_type = config_data.get("vpn_type", "")
        purpose = config_data.get("purpose", "")
        
        if vpn_type in ["openvpn-server", "wireguard-server"] or purpose == "vpn-server":
            is_server = True
            LOGGER.debug("Adding new VPN server")
        else:
            LOGGER.debug("Adding new VPN client")
        
        try:
            # Set the purpose based on whether this is a client or server
            config_data["purpose"] = "vpn-server" if is_server else "vpn-client"
            
            # Set default values if not provided
            if "name" not in config_data:
                vpn_variant = "Server" if is_server else "Client"
                if "wireguard" in vpn_type:
                    config_data["name"] = f"WireGuard {vpn_variant}"
                else:
                    config_data["name"] = f"OpenVPN {vpn_variant}"
            
            # Ensure enabled is set (default to enabled)
            if "enabled" not in config_data:
                config_data["enabled"] = True
                
            # Create and execute the API request using the wrapper method
            request = self.create_api_request("POST", API_PATH_NETWORK_CONF, data=config_data)
            response = await self.controller.request(request)
            
            if not response or "data" not in response:
                LOGGER.error(f"Failed to add VPN {config_data['purpose']}")
                return None
                
            # Return the newly created VPN config as a typed object
            LOGGER.info(f"Successfully added VPN {config_data['purpose']}")
            return VPNConfig(response["data"])
            
        except Exception as err:
            LOGGER.error(f"Error adding VPN {config_data.get('purpose', 'configuration')}: {err}")
            return None
    
    # Convenience wrappers for add_vpn_config
    async def add_vpn_client(self, client_data: Dict[str, Any]) -> Optional[VPNConfig]:
        """Add a new VPN client configuration."""
        if "purpose" not in client_data:
            client_data["purpose"] = "vpn-client"
        return await self.add_vpn_config(client_data)
    
    async def add_vpn_server(self, server_data: Dict[str, Any]) -> Optional[VPNConfig]:
        """Add a new VPN server configuration."""
        if "purpose" not in server_data:
            server_data["purpose"] = "vpn-server"
        return await self.add_vpn_config(server_data)
            
    async def update_vpn_config(self, config: VPNConfig) -> bool:
        """Update a VPN configuration.
        
        Args:
            config: The VPN configuration to update
            
        Returns:
            True if successful, False otherwise
        """
        if not config.id:
            LOGGER.error("Cannot update VPN configuration without an ID")
            return False
            
        LOGGER.debug(f"Updating VPN configuration {config.display_name} ({config.id})")
        
        try:
            config_data = config.to_dict()
            
            # Log what we're updating (excluding sensitive data)
            LOGGER.debug(f"Updating VPN configuration {config.display_name} with enabled={config.enabled}")
            
            # Create path with the network ID and execute the API request
            path = API_PATH_NETWORK_CONF_DETAIL.format(network_id=config.id)
            request = self.create_api_request("PUT", path, data=config_data)
            response = await self.controller.request(request)
            
            if not response:
                LOGGER.error(f"Failed to update VPN configuration {config.display_name}")
                return False
                
            LOGGER.info(f"Successfully updated VPN configuration {config.display_name}")
            return True
            
        except Exception as err:
            LOGGER.error(f"Error updating VPN configuration {config.display_name}: {err}")
            return False
            
    async def toggle_vpn_config(self, config: VPNConfig) -> bool:
        """Toggle a VPN configuration.
        
        Args:
            config: The VPN configuration to toggle
            
        Returns:
            True if successful, False otherwise
        """
        new_state = not config.enabled
        LOGGER.debug(f"Toggling VPN configuration {config.display_name} ({config.id}) to {new_state}")
        
        try:
            # Update the enabled state
            config.enabled = new_state
            
            # Create path with the network ID and execute the API request
            path = API_PATH_NETWORK_CONF_DETAIL.format(network_id=config.id)
            request = self.create_api_request("PUT", path, data=config.to_dict())
            response = await self.controller.request(request)
            
            if not response:
                LOGGER.error(f"Failed to toggle VPN configuration {config.display_name}")
                return False
                
            LOGGER.info(f"VPN configuration {config.display_name} toggled to {'enabled' if new_state else 'disabled'}")
            return True
            
        except Exception as err:
            LOGGER.error(f"Error toggling VPN configuration {config.display_name}: {err}")
            return False
            
    async def remove_vpn_config(self, config: Union[VPNConfig, str]) -> bool:
        """Remove a VPN configuration.
        
        Args:
            config: The VPN configuration object or config ID to remove
            
        Returns:
            True if successful, False otherwise
        """
        # Extract the config ID
        config_id = config if isinstance(config, str) else config.id
        display_name = config.display_name if isinstance(config, VPNConfig) else config_id
        
        if not config_id:
            LOGGER.error("Cannot remove VPN configuration without an ID")
            return False
            
        LOGGER.debug(f"Removing VPN configuration {display_name} ({config_id})")
        
        try:
            # Create path with the network ID and execute the API request
            path = API_PATH_NETWORK_CONF_DETAIL.format(network_id=config_id)
            request = self.create_api_request("DELETE", path)
            response = await self.controller.request(request)
            
            if not response:
                LOGGER.error(f"Failed to remove VPN configuration {display_name}")
                return False
                
            LOGGER.info(f"Successfully removed VPN configuration {display_name}")
            return True
            
        except Exception as err:
            LOGGER.error(f"Error removing VPN configuration {display_name}: {err}")
            return False
    
    # Convenience methods for readability
    toggle_vpn_client = toggle_vpn_config
    toggle_vpn_server = toggle_vpn_config
    update_vpn_client = update_vpn_config
    remove_vpn_client = remove_vpn_config
    remove_vpn_server = remove_vpn_config