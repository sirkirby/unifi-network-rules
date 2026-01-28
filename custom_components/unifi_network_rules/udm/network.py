"""Module for UniFi network operations."""

from __future__ import annotations

from typing import Any

from aiounifi.models.device import Device

# Import directly from specific modules
from aiounifi.models.firewall_zone import FirewallZone, FirewallZoneListRequest
from aiounifi.models.wlan import Wlan, WlanEnableRequest, WlanListRequest

from ..const import (
    API_PATH_NETWORK_CONF,
    API_PATH_NETWORK_CONF_DETAIL,
    API_PATH_WLAN_DETAIL,
    LOGGER,
)
from ..models.network import NetworkConf


class NetworkMixin:
    """Mixin class for network operations."""

    async def get_firewall_zones(self) -> list[FirewallZone]:
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

    async def get_wlans(self) -> list[Wlan]:
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

    async def toggle_wlan(self, wlan: Any, target_state: bool) -> bool:
        """Set a WLAN to a specific enabled/disabled state.

        Args:
            wlan: The Wlan object to modify
            target_state: The desired state (True=enabled, False=disabled)

        Returns:
            bool: True if the operation was successful, False otherwise
        """
        LOGGER.debug("Setting WLAN state")
        try:
            # Ensure the wlan is a proper Wlan object
            if not isinstance(wlan, Wlan):
                LOGGER.error("Expected Wlan object but got %s", type(wlan))
                return False

            LOGGER.debug("Setting WLAN %s to %s", wlan.id, target_state)

            # Use update method with the updated Wlan
            result = await self.controller.request(WlanEnableRequest.create(wlan.id, target_state))
            if result:
                LOGGER.debug("WLAN %s set successfully to %s", wlan.id, target_state)
            else:
                LOGGER.error("Failed to set WLAN %s", wlan.id)
            return result
        except Exception as err:
            LOGGER.error("Failed to set WLAN state: %s", str(err))
            return False

    async def get_devices(self) -> list[Device]:
        """Get all network devices."""
        try:
            # Use the correct v2 API endpoint for devices
            request = self.create_api_request("GET", "/device", is_v2=True)
            data = await self.controller.request(request)
            if data and "data" in data:
                result: list[Device] = []
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
            device_raw = getattr(device, "raw", {}) if hasattr(device, "raw") else {}
            device_mac = device_raw.get("mac", device_raw.get("serial", "unknown"))

            # Get the current device configuration (full payload)
            device_payload = device.raw.copy() if hasattr(device, "raw") and device.raw else {}

            # Modify only the LED override field
            device_payload["led_override"] = status

            # Use the legacy API endpoint for device updates (not v2)
            # Path format: /rest/device/{device_id}
            path = f"/rest/device/{device_id}"
            request = self.create_api_request("PUT", path, data=device_payload, is_v2=False)

            result = await self.controller.request(request)

            # Check for successful response
            if result and isinstance(result, dict):
                meta = result.get("meta", {})
                if meta.get("rc") == "ok":
                    LOGGER.debug("Device %s LED set to %s", device_mac, status)
                    # Update the device's local state for immediate feedback
                    if hasattr(device, "raw") and device.raw:
                        device.raw["led_override"] = status
                    elif hasattr(device, "led_override"):
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
            device_raw = getattr(device, "raw", {}) if hasattr(device, "raw") else {}
            device_mac = device_raw.get("mac", device_raw.get("serial", "unknown"))
            LOGGER.error("Error setting device LED for %s: %s", device_mac, str(err))
            return False

    async def get_device_led_states(self) -> list[Device]:
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

            led_capable_devices: list[Device] = []
            if data and "data" in data:
                for device_data in data["data"]:
                    # Extract device information needed for LED control
                    mac = device_data.get("mac")
                    if not mac:
                        continue

                    # Only include devices that are access points or have LED override capability
                    device_type = device_data.get("type", "")
                    is_access_point = device_data.get("is_access_point", False)
                    has_led_override = "led_override" in device_data

                    # Include UAPs (type 'uap') that are access points, or any device with LED override
                    if (device_type == "uap" and is_access_point) or has_led_override:
                        try:
                            # Create Device object directly from API data, following the pattern of converting raw API responses into typed objects
                            device = Device(device_data)
                            led_capable_devices.append(device)
                            LOGGER.debug(
                                "Created LED-capable device: %s (%s) - LED state: %s",
                                device_data.get("name", "Unknown"),
                                mac,
                                device_data.get("led_override", "unknown"),
                            )
                        except Exception as device_err:
                            LOGGER.warning(
                                "Error creating Device object for %s (%s): %s",
                                device_data.get("name", "unknown"),
                                mac,
                                str(device_err),
                            )
                            continue

                LOGGER.debug("Created %d LED-capable Device objects from stat/device", len(led_capable_devices))
                return led_capable_devices
            return []
        except Exception as err:
            LOGGER.error("Failed to get device LED states: %s", str(err))
            return []

    async def get_networks(self) -> list[NetworkConf]:
        """Get manageable network configurations (excludes VPNs and default network).

        Returns only LAN/WAN networks that can be managed as switch entities.
        VPN configurations are handled separately via get_vpn_clients() and get_vpn_servers().
        """
        try:
            from ..helpers.rule import filter_switchable_networks

            request = self.create_api_request("GET", API_PATH_NETWORK_CONF)
            data = await self.controller.request(request)
            all_networks: list[NetworkConf] = []
            if data and isinstance(data, dict) and "data" in data:
                for n in data["data"]:
                    all_networks.append(NetworkConf(n))

            # Use the established helper to filter out VPNs and defaults
            filtered_networks = filter_switchable_networks(all_networks)
            LOGGER.debug("Filtered to %d manageable networks (excluded VPNs and defaults)", len(filtered_networks))
            return filtered_networks
        except Exception as err:
            LOGGER.error("Failed to get networks: %s", str(err))
            return []

    async def update_network(self, network: NetworkConf) -> bool:
        """Update a network configuration."""
        try:
            payload = dict(network.raw)
            path = API_PATH_NETWORK_CONF_DETAIL.format(network_id=network.id)
            req = self.create_api_request("PUT", path, data=payload)
            await self.controller.request(req)
            return True
        except Exception as err:
            LOGGER.error("Failed to update network %s: %s", getattr(network, "id", "unknown"), err)
            return False

    async def toggle_network(self, network: NetworkConf) -> bool:
        """Enable/disable a network by flipping 'enabled' key if present."""
        try:
            payload = dict(network.raw)
            # Only corporate LANs generally have 'enabled'
            if "enabled" not in payload:
                LOGGER.error("Network %s does not support enable/disable", network.id)
                return False
            payload["enabled"] = not bool(payload.get("enabled", True))
            path = API_PATH_NETWORK_CONF_DETAIL.format(network_id=network.id)
            req = self.create_api_request("PUT", path, data=payload)
            await self.controller.request(req)
            return True
        except Exception as err:
            LOGGER.error("Failed to toggle network %s: %s", getattr(network, "id", "unknown"), err)
            return False
