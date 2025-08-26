"""Module for UniFi network operations."""

from __future__ import annotations

from typing import Any, List

# Import directly from specific modules
from aiounifi.models.firewall_zone import FirewallZoneListRequest, FirewallZone
from aiounifi.models.wlan import (
    WlanListRequest,
    WlanEnableRequest,
    Wlan
)

from ..const import (
    LOGGER,
    API_PATH_WLAN_DETAIL,
    API_PATH_NETWORK_CONF,
)

from aiounifi.models.device import Device
from ..models.network import NetworkConf

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
            result = await self.controller.request(WlanEnableRequest.create(wlan.id, new_state))
            if result:
                LOGGER.debug("WLAN %s toggled successfully to %s", wlan.id, new_state)
            else:
                LOGGER.error("Failed to toggle WLAN %s", wlan.id)
            return result
        except Exception as err:
            LOGGER.error("Failed to toggle WLAN: %s", str(err))
            return False

    async def get_devices(self) -> List[Device]:
        """Get all network devices."""
        try:
            # Use the correct v2 API endpoint for devices
            request = self.create_api_request("GET", "/device", is_v2=True)
            data = await self.controller.request(request)
            if data and "data" in data:
                result: List[Device] = []
                for dev in data["data"]:
                    result.append(Device(dev))
                LOGGER.debug("Converted %d devices to typed objects", len(result))
                return result
            return []
        except Exception as err:
            LOGGER.error("Failed to get devices: %s", str(err))
            return []

    async def set_device_led(self, device: Device, enable: bool = True) -> bool:
        """Set LED status of a device (simple on/off toggle).
        
        Args:
            device: The Device object to control
            enable: True to turn LED on, False to turn off
            
        Returns:
            bool: True if successful, False otherwise
            
        Note:
            This method only supports simple on/off control. For advanced features
            like brightness and color control, a Light entity would be more appropriate.
            
        Implementation:
            Uses the pattern of getting full device payload, modifying only the LED field,
            and PUTting the entire payload back to the device-specific endpoint.
        """
        try:
            device_id = device.id
            status = "on" if enable else "off"
            
            # Get device MAC safely for logging
            device_raw = getattr(device, 'raw', {}) if hasattr(device, 'raw') else {}
            device_mac = device_raw.get('mac', device_raw.get('serial', 'unknown'))
            
            # Get the current device configuration (full payload)
            device_payload = device.raw.copy() if hasattr(device, 'raw') and device.raw else {}
            
            # Modify only the LED override field
            device_payload['led_override'] = status
            
            # Use the legacy API endpoint for device updates (not v2)
            # Path format: /rest/device/{device_id}
            path = f"/rest/device/{device_id}"
            request = self.create_api_request("PUT", path, data=device_payload, is_v2=False)
            
            result = await self.controller.request(request)
            
            # Check for successful response
            if result and isinstance(result, dict):
                meta = result.get('meta', {})
                if meta.get('rc') == 'ok':
                    LOGGER.debug("Device %s LED set to %s", device_mac, status)
                    # Update the device's local state for immediate feedback
                    if hasattr(device, 'raw') and device.raw:
                        device.raw['led_override'] = status
                    elif hasattr(device, 'led_override'):
                        device.led_override = status
                    return True
                else:
                    LOGGER.error("API returned error for device %s LED update: %s", device_mac, meta)
                    return False
            else:
                LOGGER.error("Failed to set LED for device %s - unexpected API response", device_mac)
                return False
        except Exception as err:
            # Get device MAC safely for error logging
            device_raw = getattr(device, 'raw', {}) if hasattr(device, 'raw') else {}
            device_mac = device_raw.get('mac', device_raw.get('serial', 'unknown'))
            LOGGER.error("Error setting device LED for %s: %s", device_mac, str(err))
            return False

    async def get_device_led_states(self) -> List[Device]:
        """Get LED-capable devices with their current states.
        
        Returns properly typed Device objects for LED control switches and triggers.
        Connection state monitoring is handled by the core UniFi integration.
        
        Returns:
            List[Device]: LED-capable Device objects with full device data
        """
        try:
            # Use the stat/device endpoint which has full device config including LED state
            request = self.create_api_request("GET", "/stat/device", is_v2=False)
            data = await self.controller.request(request)
            
            led_capable_devices: List[Device] = []
            if data and "data" in data:
                for device_data in data["data"]:
                    # Extract device information needed for LED control
                    mac = device_data.get('mac')
                    if not mac:
                        continue
                        
                    # Only include devices that are access points or have LED override capability
                    device_type = device_data.get('type', '')
                    is_access_point = device_data.get('is_access_point', False)
                    has_led_override = 'led_override' in device_data
                    
                    # Include UAPs (type 'uap') that are access points, or any device with LED override
                    if (device_type == 'uap' and is_access_point) or has_led_override:
                        try:
                            # Create Device object directly from API data, following the pattern of converting raw API responses into typed objects
                            device = Device(device_data)
                            led_capable_devices.append(device)
                            LOGGER.debug("Created LED-capable device: %s (%s) - LED state: %s", 
                                       device_data.get('name', 'Unknown'), mac, 
                                       device_data.get('led_override', 'unknown'))
                        except Exception as device_err:
                            LOGGER.warning("Error creating Device object for %s (%s): %s", 
                                         device_data.get('name', 'unknown'), mac, str(device_err))
                            continue
                        
                LOGGER.debug("Created %d LED-capable Device objects from stat/device", len(led_capable_devices))
                return led_capable_devices
            return []
        except Exception as err:
            LOGGER.error("Failed to get device LED states: %s", str(err))
            return []

    async def get_networks(self) -> List[NetworkConf]:
        """Get all network configurations (networkconf)."""
        try:
            request = self.create_api_request("GET", API_PATH_NETWORK_CONF)
            data = await self.controller.request(request)
            items: List[NetworkConf] = []
            if data and isinstance(data, dict) and "data" in data:
                for n in data["data"]:
                    items.append(NetworkConf(n))
            return items
        except Exception as err:
            LOGGER.error("Failed to get networks: %s", str(err))
            return []