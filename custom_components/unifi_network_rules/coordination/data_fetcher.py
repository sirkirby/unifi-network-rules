"""Data fetching module for UniFi Network Rules coordinator.

Handles all API data fetching with consistent patterns and error handling.
Replaces multiple duplicate update methods with a single, efficient implementation.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Callable, TYPE_CHECKING
import time

from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send

from ..const import DOMAIN, LOGGER
from ..models.port_profile import PortProfile

if TYPE_CHECKING:
    from ..udm import UDMAPI


class CoordinatorDataFetcher:
    """Handles data fetching for the coordinator with unified patterns."""

    def __init__(self, api: "UDMAPI", hass, coordinator) -> None:
        """Initialize the data fetcher.
        
        Args:
            api: The UDMAPI instance for making API calls
            hass: Home Assistant instance
            coordinator: Reference to parent coordinator for state access
        """
        self.api = api
        self.hass = hass
        self.coordinator = coordinator
        
        # Define entity type to API method mapping for consistent fetching
        self.entity_type_methods = {
            "firewall_policies": self.api.get_firewall_policies,
            "traffic_routes": self.api.get_traffic_routes,
            "firewall_zones": self.api.get_firewall_zones,
            "wlans": self.api.get_wlans,
            "traffic_rules": self.api.get_traffic_rules,
            "networks": self.api.get_networks,
            "vpn_clients": self.api.get_vpn_clients,
            "vpn_servers": self.api.get_vpn_servers,
            "static_routes": self.api.get_static_routes,
            "nat_rules": self.api.get_nat_rules,
            "legacy_firewall_rules": self.api.get_legacy_firewall_rules,
            "qos_rules": self.api.get_qos_rules,
            "port_forwards": self.api.get_port_forwards,
            "oon_policies": self.api.get_oon_policies,
        }

    async def fetch_all_entity_data(self) -> Dict[str, List[Any]]:
        """Fetch all entity types efficiently with parallel calls.
        
        Returns:
            Dictionary mapping entity types to their data collections
            
        Raises:
            UpdateFailed: If critical API errors occur
        """
        # Initialize with empty lists for each rule type
        rules_data: Dict[str, List[Any]] = {
            entity_type: [] for entity_type in self.entity_type_methods.keys()
        }
        rules_data.update({
            "firewall_zones": [],
            "devices": [],
            "port_profiles": [],
        })

        # Proactively refresh session to prevent 403 errors
        await self._refresh_session_if_needed()

        # Check rate limiting before proceeding
        if await self._is_rate_limited():
            LOGGER.warning("Rate limit in effect. Using cached data.")
            return self.coordinator._last_successful_data or rules_data

        # Clear any caches before fetching to ensure fresh data
        await self.api.clear_cache()
        LOGGER.debug("Beginning rule data collection with fresh cache")

        # Fetch all standard entity types in parallel (more efficient than sequential)
        await self._fetch_standard_entities_parallel(rules_data)
        
        # Handle special entity types that need custom processing
        await self._fetch_special_entities(rules_data)
        
        # Filter out OON policies from QoS and Traffic Routes to prevent duplicates
        # UniFi may return OON policies in multiple endpoints
        self._filter_oon_policy_duplicates(rules_data)

        return rules_data

    async def _fetch_standard_entities_parallel(self, rules_data: Dict[str, List[Any]]) -> None:
        """Fetch standard entity types in parallel for efficiency."""
        tasks = {}
        
        # Create tasks for all standard entity types
        for entity_type, api_method in self.entity_type_methods.items():
            tasks[entity_type] = asyncio.create_task(
                self._fetch_entity_type_safe(entity_type, api_method)
            )
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        # Process results
        for entity_type, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                LOGGER.error("Failed to fetch %s: %s", entity_type, result)
                rules_data[entity_type] = []
                # Re-raise auth errors for session refresh
                if self._is_auth_error(result):
                    raise result
            else:
                rules_data[entity_type] = result or []
                LOGGER.info("Fetched %d %s", len(rules_data[entity_type]), entity_type)

    async def _fetch_special_entities(self, rules_data: Dict[str, List[Any]]) -> None:
        """Handle entity types that need special processing."""
        # Devices (LED-capable devices)
        await self._fetch_devices(rules_data)
        
        # Port profiles (need special typing)
        await self._fetch_port_profiles(rules_data)

    async def _fetch_entity_type_safe(self, entity_type: str, api_method: Callable) -> List[Any]:
        """Safely fetch a single entity type with error handling.
        
        Args:
            entity_type: The type of entity being fetched
            api_method: The API method to call
            
        Returns:
            List of entities or empty list on error
            
        Raises:
            Exception: Re-raises authentication errors for session refresh
        """
        try:
            LOGGER.debug("Fetching %s via %s", entity_type, api_method.__name__)
            
            # Use queue_api_operation and properly await the future
            future = await self.api.queue_api_operation(api_method)
            result = await future if hasattr(future, "__await__") else future
            
            if result and len(result) > 0:
                # Validate first item has expected attributes
                first_item = result[0]
                if not hasattr(first_item, "id"):
                    LOGGER.error(
                        "API returned non-typed object for %s: %s (type: %s)",
                        entity_type, first_item, type(first_item).__name__
                    )
                    return []
                
                LOGGER.debug("First %s: ID=%s, Type=%s", 
                           entity_type, getattr(first_item, "id", "unknown"), 
                           type(first_item).__name__)
            
            return result or []
            
        except Exception as err:
            error_str = str(err).lower()
            
            # Re-raise auth errors for session refresh handling
            if "401 unauthorized" in error_str or "403 forbidden" in error_str:
                LOGGER.warning("Authentication error when fetching %s: %s", entity_type, err)
                raise
            
            # Handle 404 errors with path fix retry
            if "404 not found" in error_str:
                return await self._retry_with_path_fix(entity_type, api_method, err)
            
            LOGGER.error("Error fetching %s: %s", entity_type, err)
            return []

    async def _fetch_devices(self, rules_data: Dict[str, List[Any]]) -> None:
        """Fetch LED-capable devices."""
        try:
            LOGGER.info("Fetching LED-capable devices for LED switches...")
            
            led_capable_devices = await self.api.get_device_led_states()
            LOGGER.info("Retrieved %d LED-capable Device objects", len(led_capable_devices))
            
            if led_capable_devices:
                LOGGER.info("LED-capable devices found:")
                for device in led_capable_devices:
                    device_mac = getattr(device, 'mac', getattr(device, 'id', 'unknown'))
                    device_name = getattr(device, 'name', 'Unknown')
                    led_state = getattr(device, 'led_override', 'unknown')
                    device_model = getattr(device, 'model', 'Unknown')
                    LOGGER.info("  %s (%s): LED=%s, Model=%s", 
                              device_name, device_mac, led_state, device_model)
            
            rules_data["devices"] = led_capable_devices
            LOGGER.info("Updated %d LED-capable devices with current LED states", len(led_capable_devices))
            
        except Exception as err:
            error_str = str(err).lower()
            
            # Re-raise auth errors for session refresh
            if "401 unauthorized" in error_str or "403 forbidden" in error_str:
                LOGGER.warning("Authentication error when fetching devices: %s", err)
                raise
                
            LOGGER.error("Failed to update devices: %s", err)
            LOGGER.exception("Device update exception details:")
            rules_data["devices"] = []

    async def _fetch_port_profiles(self, rules_data: Dict[str, List[Any]]) -> None:
        """Fetch port profiles with proper typing."""
        try:
            LOGGER.info("Fetching port profiles...")
            future = await self.api.queue_api_operation(self.api.get_port_profiles)
            profiles = await future if hasattr(future, "__await__") else future
            
            typed: List[PortProfile] = []
            for item in profiles or []:
                try:
                    typed.append(PortProfile(item))
                except Exception as err:
                    LOGGER.warning("Error converting port profile: %s", err)
            
            rules_data["port_profiles"] = typed
            LOGGER.info("Updated %d port profiles", len(typed))
            
        except Exception as err:
            error_str = str(err).lower()
            
            # Re-raise auth errors for session refresh
            if "401 unauthorized" in error_str or "403 forbidden" in error_str:
                LOGGER.warning("Authentication error when fetching port profiles: %s", err)
                raise
                
            LOGGER.error("Failed to update port profiles: %s", err)
            rules_data["port_profiles"] = []

    async def _retry_with_path_fix(self, entity_type: str, api_method: Callable, original_error: Exception) -> List[Any]:
        """Retry API call after attempting to fix path structure."""
        LOGGER.error("404 error when fetching %s: %s", entity_type, original_error)
        
        if hasattr(self.api, "_ensure_proxy_prefix_in_path"):
            try:
                LOGGER.info("Attempting to fix API path for %s", entity_type)
                self.api._ensure_proxy_prefix_in_path()
                
                # Retry with fixed path
                LOGGER.debug("Retrying %s fetch with fixed path", entity_type)
                retry_future = await self.api.queue_api_operation(api_method)
                retry_result = await retry_future if hasattr(retry_future, "__await__") else retry_future
                
                if retry_result:
                    LOGGER.info("Successfully retrieved %d %s after path fix", 
                              len(retry_result), entity_type)
                    return retry_result
                    
            except Exception as retry_err:
                # Re-raise auth errors
                retry_error_str = str(retry_err).lower()
                if "401 unauthorized" in retry_error_str or "403 forbidden" in retry_error_str:
                    LOGGER.warning("Authentication error in retry for %s: %s", entity_type, retry_err)
                    raise retry_err
                LOGGER.error("Error in retry attempt for %s: %s", entity_type, retry_err)
        
        return []

    async def _refresh_session_if_needed(self) -> None:
        """Proactively refresh session to prevent 403 errors."""
        refresh_interval = 300  # seconds
        current_time = asyncio.get_event_loop().time()
        last_refresh = getattr(self.coordinator, "_last_session_refresh", 0)

        if current_time - last_refresh > refresh_interval:
            LOGGER.debug("Proactively refreshing session")
            try:
                refresh_success = await self.api.refresh_session()
                if refresh_success:
                    self.coordinator._last_session_refresh = current_time
                    LOGGER.debug("Session refresh successful")
                else:
                    LOGGER.warning("Session refresh skipped or failed, continuing with update")
            except Exception as refresh_err:
                LOGGER.warning("Failed to refresh session: %s", str(refresh_err))

    async def _is_rate_limited(self) -> bool:
        """Check if API is currently rate limited."""
        if hasattr(self.api, "_rate_limited") and self.api._rate_limited:
            current_time = asyncio.get_event_loop().time()
            if current_time < getattr(self.api, "_rate_limit_until", 0):
                return True
        return False

    def _is_auth_error(self, error: Exception) -> bool:
        """Check if error is authentication-related."""
        error_str = str(error).lower()
        return "401 unauthorized" in error_str or "403 forbidden" in error_str

    def _filter_oon_policy_duplicates(self, rules_data: Dict[str, List[Any]]) -> None:
        """Filter out OON policies from QoS and Traffic Routes collections.
        
        UniFi may return the same OON policy in multiple endpoints (QoS rules,
        Traffic Routes, and OON Policies). The QoS/Traffic Route endpoints return
        portions of the OON policy with the same name but different IDs, so we
        match by name to prevent duplicate entities.
        
        Args:
            rules_data: The fetched data dictionary to filter
        """
        oon_policies = rules_data.get("oon_policies", [])
        if not oon_policies:
            return  # No OON policies to filter against
        
        # Build a set of OON policy names for fast lookup
        # Name is the reliable way to match since IDs differ between endpoints
        oon_policy_names = set()
        for policy in oon_policies:
            policy_name = getattr(policy, "name", None)
            if not policy_name and hasattr(policy, "raw"):
                policy_name = policy.raw.get("name")
            if policy_name:
                # Normalize name for comparison (strip whitespace, case-insensitive)
                normalized_name = policy_name.strip().lower()
                oon_policy_names.add(normalized_name)
                LOGGER.debug("OON policy name for filtering: '%s' (normalized: '%s')", policy_name, normalized_name)
        
        if not oon_policy_names:
            LOGGER.debug("No OON policy names found for filtering")
            return  # No valid names found
        
        LOGGER.debug("Filtering duplicates using %d OON policy name(s): %s", len(oon_policy_names), oon_policy_names)
        
        # Filter QoS rules - remove any that match OON policy names
        qos_rules = rules_data.get("qos_rules", [])
        if qos_rules:
            filtered_qos = []
            removed_count = 0
            for rule in qos_rules:
                # Get rule name from property or raw data
                rule_name = getattr(rule, "name", None)
                if not rule_name and hasattr(rule, "raw"):
                    rule_name = rule.raw.get("name")
                
                if rule_name:
                    normalized_rule_name = rule_name.strip().lower()
                    if normalized_rule_name in oon_policy_names:
                        removed_count += 1
                        LOGGER.info("Filtering OON policy duplicate from QoS rules: '%s' (matches OON policy name)", rule_name)
                        continue
                
                filtered_qos.append(rule)
            
            if removed_count > 0:
                LOGGER.info("Filtered %d OON policy duplicate(s) from QoS rules", removed_count)
                rules_data["qos_rules"] = filtered_qos
        
        # Filter Traffic Routes - remove any that match OON policy names
        traffic_routes = rules_data.get("traffic_routes", [])
        if traffic_routes:
            filtered_routes = []
            removed_count = 0
            for route in traffic_routes:
                # Get route name from property or raw data
                route_name = getattr(route, "name", None)
                if not route_name and hasattr(route, "raw"):
                    route_name = route.raw.get("name")
                # Traffic routes might use "description" instead of "name"
                if not route_name and hasattr(route, "description"):
                    route_name = getattr(route, "description", None)
                if not route_name and hasattr(route, "raw"):
                    route_name = route.raw.get("description")
                
                if route_name:
                    normalized_route_name = route_name.strip().lower()
                    if normalized_route_name in oon_policy_names:
                        removed_count += 1
                        LOGGER.info("Filtering OON policy duplicate from Traffic Routes: '%s' (matches OON policy name)", route_name)
                        continue
                
                filtered_routes.append(route)
            
            if removed_count > 0:
                LOGGER.info("Filtered %d OON policy duplicate(s) from Traffic Routes", removed_count)
                rules_data["traffic_routes"] = filtered_routes

    def validate_fetched_data(self, data: Dict[str, List[Any]]) -> bool:
        """Validate that fetched data contains expected content.
        
        Args:
            data: The fetched data dictionary
            
        Returns:
            True if data appears valid, False otherwise
        """
        # Check if we have at least some data in key categories
        key_categories = [
            "firewall_policies", "traffic_rules", "port_forwards", "qos_rules",
            "traffic_routes", "static_routes", "legacy_firewall_rules",
            "port_profiles", "networks", "devices"
        ]
        
        return any(len(data.get(category, [])) > 0 for category in key_categories)
