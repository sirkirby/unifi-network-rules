"""VPN client management mixin for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from ..const import (
    LOGGER,
    API_PATH_NETWORK_CONF,
    API_PATH_NETWORK_CONF_DETAIL,
)
from ..models.vpn_client import VPNClient

class VPNMixin:
    """Mixin to add VPN client management capabilities to the UDMAPI class."""

    async def get_vpn_clients(self) -> List[VPNClient]:
        """Get VPN client connections.
        
        Returns:
            List of VPN client objects
        """
        LOGGER.debug("Fetching VPN client connections")
        
        try:
            # Create API request using the wrapper method in the base class
            request = self.create_api_request("GET", API_PATH_NETWORK_CONF)
            data = await self.controller.request(request)
            
            if not data or "data" not in data:
                LOGGER.warning("No response or invalid response from network configuration API")
                return []
                
            network_data = data.get("data", [])
            
            # Filter the network configurations to only get VPN clients
            vpn_clients = []
            for network in network_data:
                purpose = network.get("purpose", "")
                vpn_type = network.get("vpn_type", "")
                
                # Check for both purpose and vpn_type to ensure we only get VPN clients
                if purpose == "vpn-client" or vpn_type in ["openvpn-client", "wireguard-client"]:
                    try:
                        vpn_client = VPNClient(network)
                        vpn_clients.append(vpn_client)
                        LOGGER.debug(f"Found VPN client: {vpn_client.display_name} (Type: {vpn_client.vpn_type})")
                    except Exception as client_err:
                        LOGGER.error(f"Error creating VPN client from data: {client_err}")
                    
            LOGGER.debug(f"Found {len(vpn_clients)} VPN client connections")
            return vpn_clients
            
        except Exception as err:
            LOGGER.error(f"Error fetching VPN client connections: {err}")
            return []
            
    async def add_vpn_client(self, client_data: Dict[str, Any]) -> Optional[VPNClient]:
        """Add a new VPN client configuration.
        
        Args:
            client_data: Dictionary with the VPN client configuration
            
        Returns:
            VPNClient object if successful, None otherwise
        """
        LOGGER.debug("Adding new VPN client")
        
        try:
            # Ensure the purpose is set to vpn-client
            client_data["purpose"] = "vpn-client"
            
            # Set default values if not provided
            if "name" not in client_data:
                vpn_type = client_data.get("vpn_type", "openvpn-client")
                if vpn_type == "wireguard-client":
                    client_data["name"] = "WireGuard Client"
                else:
                    client_data["name"] = "OpenVPN Client"
            
            # Ensure enabled is set (default to enabled)
            if "enabled" not in client_data:
                client_data["enabled"] = True
                
            # Create and execute the API request using the wrapper method
            request = self.create_api_request("POST", API_PATH_NETWORK_CONF, data=client_data)
            response = await self.controller.request(request)
            
            if not response or "data" not in response:
                LOGGER.error("Failed to add VPN client")
                return None
                
            # Return the newly created VPN client as a typed object
            LOGGER.info("Successfully added VPN client")
            return VPNClient(response["data"])
            
        except Exception as err:
            LOGGER.error(f"Error adding VPN client: {err}")
            return None
            
    async def update_vpn_client(self, client: VPNClient) -> bool:
        """Update a VPN client configuration.
        
        Args:
            client: The VPN client to update
            
        Returns:
            True if successful, False otherwise
        """
        if not client.id:
            LOGGER.error("Cannot update VPN client without an ID")
            return False
            
        LOGGER.debug(f"Updating VPN client {client.display_name} ({client.id})")
        
        try:
            client_data = client.to_dict()
            
            # Log what we're updating (excluding sensitive data)
            LOGGER.debug(f"Updating VPN client {client.display_name} with enabled={client.enabled}")
            
            # Create path with the network ID and execute the API request
            path = API_PATH_NETWORK_CONF_DETAIL.format(network_id=client.id)
            request = self.create_api_request("PUT", path, data=client_data)
            response = await self.controller.request(request)
            
            if not response:
                LOGGER.error(f"Failed to update VPN client {client.display_name}")
                return False
                
            LOGGER.info(f"Successfully updated VPN client {client.display_name}")
            return True
            
        except Exception as err:
            LOGGER.error(f"Error updating VPN client {client.display_name}: {err}")
            return False
            
    async def toggle_vpn_client(self, client: VPNClient) -> bool:
        """Toggle a VPN client connection.
        
        Args:
            client: The VPN client to toggle
            
        Returns:
            True if successful, False otherwise
        """
        new_state = not client.enabled
        LOGGER.debug(f"Toggling VPN client {client.display_name} ({client.id}) to {new_state}")
        
        try:
            # Update the enabled state
            client.enabled = new_state
            
            # Create path with the network ID and execute the API request
            path = API_PATH_NETWORK_CONF_DETAIL.format(network_id=client.id)
            request = self.create_api_request("PUT", path, data=client.to_dict())
            response = await self.controller.request(request)
            
            if not response:
                LOGGER.error(f"Failed to toggle VPN client {client.display_name}")
                return False
                
            LOGGER.info(f"VPN client {client.display_name} toggled to {'enabled' if new_state else 'disabled'}")
            return True
            
        except Exception as err:
            LOGGER.error(f"Error toggling VPN client {client.display_name}: {err}")
            return False
            
    async def remove_vpn_client(self, client: Union[VPNClient, str]) -> bool:
        """Remove a VPN client configuration.
        
        Args:
            client: The VPN client object or client ID to remove
            
        Returns:
            True if successful, False otherwise
        """
        # Extract the client ID
        client_id = client if isinstance(client, str) else client.id
        display_name = client.display_name if isinstance(client, VPNClient) else client_id
        
        if not client_id:
            LOGGER.error("Cannot remove VPN client without an ID")
            return False
            
        LOGGER.debug(f"Removing VPN client {display_name} ({client_id})")
        
        try:
            # Create path with the network ID and execute the API request
            path = API_PATH_NETWORK_CONF_DETAIL.format(network_id=client_id)
            request = self.create_api_request("DELETE", path)
            response = await self.controller.request(request)
            
            if not response:
                LOGGER.error(f"Failed to remove VPN client {display_name}")
                return False
                
            LOGGER.info(f"Successfully removed VPN client {display_name}")
            return True
            
        except Exception as err:
            LOGGER.error(f"Error removing VPN client {display_name}: {err}")
            return False