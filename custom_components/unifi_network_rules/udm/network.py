"""Module for UniFi network operations."""

import logging
from typing import Any, Dict, List, Optional, Tuple

# Import directly from specific modules
from aiounifi.models.firewall_zone import FirewallZoneListRequest, FirewallZone
from aiounifi.models.wlan import (
    WlanListRequest,
    WlanEnableRequest,
    Wlan
)

from ..const import (
    LOGGER,
    API_PATH_WLAN_DETAIL
)

class NetworkMixin:
    """Mixin class for network operations."""

    async def get_firewall_zones(self) -> List[FirewallZone]:
        """Get all firewall zones."""
        try:
            # Using FirewallZoneListRequest for proper typing
            request = FirewallZoneListRequest.create()
            data = await self.controller.request(request)
            
            if data and "data" in data:
                # Convert to typed FirewallZone objects
                result = []
                for zone_data in data["data"]:
                    # Explicitly create FirewallZone objects
                    zone = FirewallZone(zone_data)
                    result.append(zone)
                LOGGER.debug("Converted %d firewall zones to typed objects", len(result))
                return result
            return []
        except Exception as err:
            LOGGER.error("Failed to get firewall zones: %s", str(err))
            return []

    async def get_wlans(self) -> List[Wlan]:
        """Get all WLANs."""
        try:
            # Using WlanListRequest for proper typing
            request = WlanListRequest.create()
            data = await self.controller.request(request)
            
            if data and "data" in data:
                # Convert to typed Wlan objects
                result = []
                for wlan_data in data["data"]:
                    # Explicitly create Wlan objects
                    wlan = Wlan(wlan_data)
                    result.append(wlan)
                LOGGER.debug("Converted %d WLANs to typed objects", len(result))
                return result
            return []
        except Exception as err:
            LOGGER.error("Failed to get WLANs: %s", str(err))
            return []

    async def update_wlan(self, wlan: Wlan) -> bool:
        """Update a WLAN.
        
        Args:
            wlan: The Wlan object to update
            
        Returns:
            bool: True if the update was successful, False otherwise
        """
        wlan_id = wlan.id
        LOGGER.debug("Updating WLAN %s", wlan_id)
        try:
            # Convert wlan to dictionary for update
            wlan_dict = wlan.raw.copy()
                
            # Using the path with wlan_id
            path = API_PATH_WLAN_DETAIL.format(wlan_id=wlan_id)
            request = self.create_api_request("PUT", path, data=wlan_dict)
            
            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("WLAN %s updated successfully", wlan_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to update WLAN: %s", str(err))
            return False

    async def toggle_wlan(self, wlan: Any) -> bool:
        """Toggle a WLAN on/off."""
        LOGGER.debug("Toggling WLAN state")
        try:
            # Ensure the wlan is a proper Wlan object
            if not isinstance(wlan, Wlan):
                LOGGER.error("Expected Wlan object but got %s", type(wlan))
                return False
            
            new_state = not wlan.enabled
            # Use update method with the updated Wlan
            result = await self.controller.request(WlanEnableRequest.create(wlan, new_state))
            if result:
                LOGGER.debug("WLAN %s toggled successfully to %s", wlan.id, new_state)
            else:
                LOGGER.error("Failed to toggle WLAN %s", wlan.id)
            return result
        except Exception as err:
            LOGGER.error("Failed to toggle WLAN: %s", str(err))
            return False