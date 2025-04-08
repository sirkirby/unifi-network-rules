"""UniFi Network Rules Coordinator."""
from __future__ import annotations

from datetime import timedelta
import asyncio
from typing import Any, Dict, Callable, List
import time

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward
from aiounifi.models.firewall_zone import FirewallZone
from aiounifi.models.wlan import Wlan

from .const import DOMAIN, LOGGER, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DEBUG_WEBSOCKET
from .udm import UDMAPI
from .websocket import SIGNAL_WEBSOCKET_MESSAGE, UnifiRuleWebsocket
from .helpers.rule import get_rule_id, get_rule_name, get_rule_enabled, get_child_unique_id
from .utils.logger import log_data, log_websocket
from .models.firewall_rule import FirewallRule
from .models.qos_rule import QoSRule
from .models.vpn_client import VPNClient

# This is a fallback if no update_interval is specified
SCAN_INTERVAL = timedelta(seconds=60)

def _log_rule_info(rule: Any) -> None:
    """Log detailed information about a rule object."""
    try:
        # For all API objects with common properties (including FirewallRule)
        if hasattr(rule, "id") and hasattr(rule, "raw"):
            # Get common attributes that most rule objects have
            attrs = {
                "ID": getattr(rule, "id", ""),
                "Name": getattr(rule, "name", ""),
                "Enabled": getattr(rule, "enabled", False)
            }
            
            # Add description if available
            if hasattr(rule, "description"):
                attrs["Description"] = getattr(rule, "description", "")
                
            # Log the common attributes
            log_data(
                "Rule info - Type: %s, Attributes: %s",
                type(rule),
                attrs
            )
        else:
            # Fallback for other objects
            log_data(
                "Rule info - Type: %s, Dir: %s, Dict: %s", 
                type(rule),
                getattr(rule, "__dir__", lambda: ["no __dir__"])(),
                rule.__dict__ if hasattr(rule, "__dict__") else repr(rule),
            )
    except Exception as e:
        LOGGER.debug("Error logging rule: %s", e)

class UnifiRuleUpdateCoordinator(DataUpdateCoordinator[Dict[str, List[Any]]]):
    """Coordinator to manage data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UDMAPI,
        websocket: UnifiRuleWebsocket,
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.websocket = websocket
        self.hass = hass
        
        # Track authentication failures and API issues
        self._auth_failures = 0
        self._max_auth_failures = 3
        self._last_successful_data = None
        self._consecutive_errors = 0
        self._in_error_state = False
        
        # WebSocket refresh control variables
        self._last_ws_refresh = 0
        self._min_ws_refresh_interval = 1.5  # Reduced from 3.0 to 1.5 seconds minimum between refreshes
        self._pending_ws_refresh = False
        self._ws_refresh_task = None
        self._refresh_semaphore = asyncio.Semaphore(1)
        
        # Add a lock to prevent concurrent updates during authentication
        self._update_lock = asyncio.Lock()
        # Track authentication in progress
        self._authentication_in_progress = False

        # Set auth failure callback on API
        if hasattr(api, "set_auth_failure_callback"):
            api.set_auth_failure_callback(self._handle_auth_failure)

        # Convert update_interval from seconds to timedelta
        update_interval_td = timedelta(seconds=update_interval)

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=update_interval_td,
        )

        # Set up websocket message handler
        self.websocket.set_callback(self._handle_websocket_message)

        # Subscribe to websocket messages
        self._cleanup_callbacks: list[Callable[[], None]] = []
        self._cleanup_callbacks.append(
            async_dispatcher_connect(
                hass,
                SIGNAL_WEBSOCKET_MESSAGE,
                self._handle_websocket_message
            )
        )

        # For tracking entity updates
        self.device_name = None
        self.data: Dict[str, Any] = {}
        
        # Rule collections - initialized during update
        self.port_forwards: List[PortForward] = []
        self.traffic_routes: List[TrafficRoute] = []
        self.firewall_policies: List[FirewallPolicy] = []
        self.traffic_rules: List[TrafficRule] = []
        self.legacy_firewall_rules: List[FirewallRule] = []
        self.firewall_zones: List[FirewallZone] = []
        self.wlans: List[Wlan] = []
        self.qos_rules: List[QoSRule] = []
        self.vpn_clients: List[VPNClient] = []
        
        # For dynamic entity creation
        self.async_add_entities_callback: AddEntitiesCallback | None = None
        self.known_unique_ids: set[str] = set()
        
        # Entity removal callback
        self._entity_removal_callback = None
        
        # Flag to ensure post-setup check runs only once
        self._initial_update_done = False
        
        # Entity creation callback
        self.on_create_entity = None
        
        # Task handling queued entity creation
        self._queue_task = None
        self._queue_lock = asyncio.Lock()
        self._entity_creation_queue = []

        # API fetch counts
        self._api_requests = 0
        self._api_errors = 0

    async def _async_update_data(self) -> Dict[str, List[Any]]:
        """Fetch data from API endpoint.
        
        This is the place where data for all entities is updated from.
        
        Returns:
            Dict[str, list]: A dictionary containing lists of entities by type
        """
        if not self.api.is_initialized:
            LOGGER.error("API is not initialized during coordinator update.")
            return {}
            
        # Flag that update is in progress
        self._update_in_progress = True
        
        try:
            # Check for connection problems
            if not self.api.is_connected:
                LOGGER.warning("API not connected, attempting reconnection...")
                await self.api.login()
                
                if not self.api.is_connected:
                    LOGGER.error("Failed to reconnect to UniFi Network during update.")
                    # Set data to previous but flag as unavailable
                    self._has_data = False
                    result = self.data or {} 
                    # Return the previous data structure to avoid total loss of state
                    return result

            # Start collecting data - always get the data even if it may fail
            # Instead of immediately returning when any error occurs, try to get as much data as possible
            result = {}
            errors = []
            
            # Fetch each type of rule with individual try/except blocks
            
            # Fetch firewall policies
            try:
                result["firewall_policies"] = await self._async_get_firewall_policies()
            except Exception as err:
                errors.append(f"Error fetching firewall policies: {err}")
                # Keep existing data if available
                if self.data and "firewall_policies" in self.data:
                    result["firewall_policies"] = self.data["firewall_policies"]
                else:
                    result["firewall_policies"] = []
            
            # Fetch port forwards
            try:
                result["port_forwards"] = await self._async_get_port_forwards()
            except Exception as err:
                errors.append(f"Error fetching port forwards: {err}")
                # Keep existing data if available
                if self.data and "port_forwards" in self.data:
                    result["port_forwards"] = self.data["port_forwards"]
                else:
                    result["port_forwards"] = []
            
            # Fetch traffic routes
            try:
                result["traffic_routes"] = await self._async_get_traffic_routes()
            except Exception as err:
                errors.append(f"Error fetching traffic routes: {err}")
                # Keep existing data if available
                if self.data and "traffic_routes" in self.data:
                    result["traffic_routes"] = self.data["traffic_routes"]
                else:
                    result["traffic_routes"] = []
            
            # Fetch traffic rules
            try:
                result["traffic_rules"] = await self._async_get_traffic_rules()
            except Exception as err:
                errors.append(f"Error fetching traffic rules: {err}")
                # Keep existing data if available
                if self.data and "traffic_rules" in self.data:
                    result["traffic_rules"] = self.data["traffic_rules"]
                else:
                    result["traffic_rules"] = []
            
            # Fetch legacy firewall rules
            try:
                result["legacy_firewall_rules"] = await self._async_get_legacy_firewall_rules()
            except Exception as err:
                errors.append(f"Error fetching legacy firewall rules: {err}")
                # Keep existing data if available
                if self.data and "legacy_firewall_rules" in self.data:
                    result["legacy_firewall_rules"] = self.data["legacy_firewall_rules"]
                else:
                    result["legacy_firewall_rules"] = []
            
            # Fetch zones - needed for enriching policy data
            try:
                result["firewall_zones"] = await self._async_get_firewall_zones()
            except Exception as err:
                errors.append(f"Error fetching firewall zones: {err}")
                # Keep existing data if available
                if self.data and "firewall_zones" in self.data:
                    result["firewall_zones"] = self.data["firewall_zones"]
                else:
                    result["firewall_zones"] = []
            
            # Fetch wireless networks (WLANs)
            try:
                result["wlans"] = await self._async_get_wlans()
            except Exception as err:
                errors.append(f"Error fetching WLANs: {err}")
                # Keep existing data if available
                if self.data and "wlans" in self.data:
                    result["wlans"] = self.data["wlans"]
                else:
                    result["wlans"] = []

            # Fetch QoS rules
            try:
                result["qos_rules"] = await self._async_get_qos_rules()
            except Exception as err:
                errors.append(f"Error fetching QoS rules: {err}")
                # Keep existing data if available
                if self.data and "qos_rules" in self.data:
                    result["qos_rules"] = self.data["qos_rules"]
                else:
                    result["qos_rules"] = []
                    
            # Fetch VPN clients
            try:
                result["vpn_clients"] = await self._async_get_vpn_clients()
            except Exception as err:
                errors.append(f"Error fetching VPN clients: {err}")
                # Keep existing data if available
                if self.data and "vpn_clients" in self.data:
                    result["vpn_clients"] = self.data["vpn_clients"]
                else:
                    result["vpn_clients"] = []

            # Log errors if any occurred
            if errors:
                LOGGER.error("Errors during data update: %s", errors)
                
            # Mark that we now have data, even if some pieces failed
            if result:
                self._has_data = True
                
            return result
            
        except Exception as exception:
            LOGGER.exception("Error updating from UniFi Network: %s", exception)
            return self.data or {}  # Return last data on error
        finally:
            self._update_in_progress = False

    def _check_for_deleted_rules(self, new_data: Dict[str, List[Any]]) -> None:
        """Check for rules previously known but not in the new data, and trigger their removal."""
        # If the initial update isn't done, or we don't have known IDs yet, skip.
        if not self._initial_update_done or not self.known_unique_ids:
            LOGGER.debug("Skipping deletion check: Initial update done=%s, Known IDs=%s",
                         self._initial_update_done, bool(self.known_unique_ids))
            return

        LOGGER.debug("Starting deletion check against known_unique_ids (current size: %d)", len(self.known_unique_ids))

        current_known_ids = set(self.known_unique_ids) # Take a snapshot

        # Gather ALL unique IDs present in the new data passed to this function
        all_current_unique_ids = set()
        all_rule_sources_types = [
            "port_forwards",
            "traffic_routes",
            "firewall_policies",
            "traffic_rules",
            "legacy_firewall_rules",
            "qos_rules",
            "wlans",
            "vpn_clients",
        ]
        
        for rule_type in all_rule_sources_types:
             rules = new_data.get(rule_type, [])
             if rules:
                 for rule in rules:
                     try:
                         rule_id = get_rule_id(rule)
                         if rule_id:
                             all_current_unique_ids.add(rule_id)
                             # Add kill switch ID if applicable
                             if rule_type == "traffic_routes" and hasattr(rule, 'raw') and "kill_switch_enabled" in rule.raw:
                                 kill_switch_id = get_child_unique_id(rule_id, "kill_switch")
                                 all_current_unique_ids.add(kill_switch_id)
                     except Exception as e:
                          LOGGER.warning("Error getting ID during deletion check for %s: %s", rule_type, e)

        # Find IDs that are known but NOT in the current data
        deleted_unique_ids = current_known_ids - all_current_unique_ids
        LOGGER.debug("Deletion Check Final: Known IDs (Snapshot): %d, Current IDs (Calculated): %d, To Delete: %d",
                     len(current_known_ids), len(all_current_unique_ids), len(deleted_unique_ids))

        if deleted_unique_ids:
            # Process deletions using the identified IDs and the snapshot count
            self._process_deleted_rules("various_orphaned", deleted_unique_ids, len(self.known_unique_ids))
        else:
             LOGGER.debug("Deletion check: No discrepancies found between known IDs and current data.")

    def _process_deleted_rules(self, rule_type: str, deleted_ids: set, total_previous_count: int) -> None:
        """Process detected rule deletions and dispatch removal events.

        Args:
            rule_type: The type of rule being processed
            deleted_ids: Set of rule IDs that were detected as deleted
            total_previous_count: Total number of rules in the previous update
        """
        if not deleted_ids:
            return

        # If we're removing too many entities at once, this might be an API glitch
        if len(deleted_ids) > 5 and len(deleted_ids) > total_previous_count * 0.25:  # More than 25% of all entities
            LOGGER.warning(
                "Large number of %s deletions detected (%d of %d, %.1f%%). "
                "This could be an API connection issue rather than actual deletions.",
                rule_type,
                len(deleted_ids),
                total_previous_count,
                (len(deleted_ids) / total_previous_count) * 100
            )
            # For major deletions, only process a few at a time to be cautious
            # This prevents mass entity removal during API glitches
            if len(deleted_ids) > 10:
                LOGGER.warning(
                    "Processing only first 5 deletions to prevent mass removal during potential API issues"
                )
                deleted_ids_subset = list(deleted_ids)[:5]
                LOGGER.info("Processing subset of deletions: %s", deleted_ids_subset)
                deleted_ids = set(deleted_ids_subset)

        LOGGER.info("Found %d deleted %s rules: %s", len(deleted_ids), rule_type, sorted(list(deleted_ids)))

        # Dispatch deletion events for each deleted rule
        for rule_id in deleted_ids:
            # LOGGER.info("Processing deletion for rule_id: %s", rule_id)
            # Use _remove_entity which handles both callback and dispatching signals
            self.hass.async_create_task(self._remove_entity_async(rule_id))

    async def _remove_entity_async(self, unique_id: str) -> None:
        """Asynchronously remove an entity by its unique ID using direct registry removal."""
        LOGGER.debug("Attempting asynchronous removal for unique_id: %s", unique_id)

        # 1. Remove from coordinator tracking IMMEDIATELY
        if hasattr(self, 'known_unique_ids'):
            self.known_unique_ids.discard(unique_id)
            LOGGER.debug("Removed unique_id '%s' from coordinator known_unique_ids.", unique_id)

        # 2. Find the current entity_id using the unique_id
        entity_id = None
        entity_registry = async_get_entity_registry(self.hass)
        if entity_registry:
            entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, unique_id)

        # 3. Remove directly from the entity registry if entity_id found
        if entity_id:
            LOGGER.debug("Found current entity_id '%s' for unique_id '%s'. Proceeding with registry removal.", entity_id, unique_id)

            # Perform the removal
            if entity_registry.async_get(entity_id): # Check if it still exists before removing
                try:
                    entity_registry.async_remove(entity_id)
                    # NOTE: Entity's async_will_remove_from_hass runs automatically after this succeeds
                    LOGGER.info("Successfully removed entity %s (unique_id: %s) from registry.", entity_id, unique_id)
                except Exception as reg_err:
                    LOGGER.error("Error removing entity %s from registry: %s", entity_id, reg_err)
            else:
                LOGGER.debug("Entity %s already removed from registry.", entity_id)
        else:
            # If entity_id wasn't found in registry, log it.
            LOGGER.warning("Could not find entity_id for unique_id '%s' in registry. Cannot remove.", unique_id)

    async def _update_firewall_policies_in_dict(self, data: Dict[str, List[Any]]) -> None:
        """Update firewall policies in the provided dictionary."""
        await self._update_rule_type_in_dict(data, "firewall_policies", self.api.get_firewall_policies)
                    
    async def _update_traffic_rules_in_dict(self, data: Dict[str, List[Any]]) -> None:
        """Update traffic rules in the provided dictionary."""
        await self._update_rule_type_in_dict(data, "traffic_rules", self.api.get_traffic_rules)

    async def _update_port_forwards_in_dict(self, data: Dict[str, List[Any]]) -> bool:
        """Update port forwards in the provided dictionary."""
        try:
            await self._update_rule_type_in_dict(data, "port_forwards", self.api.get_port_forwards)
            return True
        except Exception as err:
            LOGGER.error("Error updating port forwards: %s", err)
            return False
        
    async def _update_traffic_routes_in_dict(self, data: Dict[str, List[Any]]) -> None:
        """Update traffic routes in the provided dictionary."""
        await self._update_rule_type_in_dict(data, "traffic_routes", self.api.get_traffic_routes)

    async def _update_firewall_zones_in_dict(self, data: Dict[str, List[Any]]) -> None:
        """Update firewall zones in the provided dictionary."""
        await self._update_rule_type_in_dict(data, "firewall_zones", self.api.get_firewall_zones)

    async def _update_wlans_in_dict(self, data: Dict[str, List[Any]]) -> None:
        """Update WLANs in the provided dictionary."""
        await self._update_rule_type_in_dict(data, "wlans", self.api.get_wlans)

    async def _update_legacy_firewall_rules_in_dict(self, data: Dict[str, List[Any]]) -> None:
        """Update legacy firewall rules in the provided dictionary."""
        await self._update_rule_type_in_dict(data, "legacy_firewall_rules", self.api.get_legacy_firewall_rules)

    async def _update_qos_rules_in_dict(self, data: Dict[str, List[Any]]) -> None:
        """Update QoS rules in the given data dictionary."""
        await self._update_rule_type_in_dict(data, "qos_rules", self.api.get_qos_rules)

    async def _update_vpn_clients_in_dict(self, data: Dict[str, List[Any]]) -> None:
        """Update VPN clients in the given data dictionary."""
        await self._update_rule_type_in_dict(data, "vpn_clients", self.api.get_vpn_clients)

    async def _update_rule_type(self, rule_type: str, fetch_method: Callable) -> None:
        """Update a specific rule type in self.data.
        
        Args:
            rule_type: The key to use in the data dictionary
            fetch_method: The API method to call to fetch the rules
        """
        LOGGER.debug("Updating %s rules", rule_type)
        try:
            # Use queue_api_operation and properly await the future
            future = await self.api.queue_api_operation(fetch_method)
            # Ensure we have the actual result, not the future itself
            rules = await future if hasattr(future, "__await__") else future
            
            self.data[rule_type] = rules
            LOGGER.debug("Updated %s rules: %d items", rule_type, len(rules))
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.error("Error updating %s rules: %s", rule_type, err)
            # Keep previous data if update fails
            if rule_type not in self.data:
                self.data[rule_type] = []
    
    async def _update_rule_type_in_dict(self, target_data: Dict[str, List[Any]], rule_type: str, fetch_method: Callable) -> None:
        """Update a specific rule type in the provided data dictionary.
        
        Args:
            target_data: The dictionary to update
            rule_type: The key to use in the data dictionary
            fetch_method: The API method to call to fetch the rules
        """
        LOGGER.debug("Updating %s rules in external dictionary", rule_type)
        try:
            # Log method being called
            LOGGER.info("Calling API method for %s: %s", rule_type, fetch_method.__name__)
            
            # Use queue_api_operation and properly await the future
            future = await self.api.queue_api_operation(fetch_method)
            # Ensure we have the actual result, not the future itself
            rules = await future if hasattr(future, "__await__") else future
            
            # Validate that we received properly typed objects
            if rules:
                LOGGER.info("API returned %d %s rules", len(rules), rule_type)
                
                # Check the first rule to validate type
                if len(rules) > 0:
                    first_rule = rules[0]
                    
                    # All our rule objects should have an 'id' attribute
                    if not hasattr(first_rule, "id"):
                        LOGGER.error(
                            "API returned non-typed object for %s: %s (type: %s)",
                            rule_type,
                            first_rule,
                            type(first_rule).__name__
                        )
                        # Don't update with untyped data
                        return

                    # Log rule details for debugging
                    rule_id = getattr(first_rule, "id", "unknown")
                    LOGGER.debug(
                        "First %s rule: ID=%s, Type=%s",
                        rule_type, 
                        rule_id, 
                        type(first_rule).__name__
                    )
                
                # Update the data with the new rules
                target_data[rule_type] = rules
            else:
                LOGGER.warning("API returned no %s rules (None or empty list)", rule_type)
                # Initialize with empty list if no rules returned
                target_data[rule_type] = []
        except Exception as err:  # pylint: disable=broad-except
            error_str = str(err).lower()
            
            # Special handling for 404 errors - may indicate path structure issue
            if "404 not found" in error_str:
                LOGGER.error("404 error when fetching %s rules: %s", rule_type, str(err))
                
                # Try to fix the API path if needed
                if hasattr(self.api, "_ensure_proxy_prefix_in_path"):
                    try:
                        LOGGER.info("Attempting to fix API path for %s rules", rule_type)
                        self.api._ensure_proxy_prefix_in_path()
                        
                        # Try one more time with the fixed path
                        LOGGER.debug("Retrying %s fetch with fixed path", rule_type)
                        retry_future = await self.api.queue_api_operation(fetch_method)
                        retry_rules = await retry_future if hasattr(retry_future, "__await__") else retry_future
                        
                        if retry_rules:
                            LOGGER.info("Successfully retrieved %d %s rules after path fix", 
                                      len(retry_rules), rule_type)
                            target_data[rule_type] = retry_rules
                            return
                    except Exception as retry_err:
                        LOGGER.error("Error in retry attempt for %s: %s", rule_type, retry_err)
            
            LOGGER.error("Error updating %s rules: %s", rule_type, err)
            # Keep previous data if update fails
            if rule_type not in target_data:
                target_data[rule_type] = []

    @callback
    def _handle_websocket_message(self, message: dict[str, Any]) -> None:
        """Handle incoming websocket message."""
        try:
            if not message:
                return

            # Get message meta data if available
            meta = message.get("meta", {})
            msg_type = meta.get("message", "")
            msg_data = message.get("data", {})
            
            # Log the message for debugging to keep full context
            log_websocket("Rule event received: %s - %s", 
                       msg_type, str(message)[:150] + "..." if len(str(message)) > 150 else str(message))
            
            # Device state changes don't require a full refresh
            if "device" in msg_type.lower() and "state" in str(message).lower():
                # Check if this is just a state update, not a configuration change
                if "state" in str(message).lower():
                    state_value = None
                    if isinstance(msg_data, list) and len(msg_data) > 0 and "state" in msg_data[0]:
                        state_value = msg_data[0].get("state")
                        log_websocket("Detected state change in %s: %s", msg_type, state_value)
                        # State updates don't need a full refresh
                        return
            
            # Define rule type-specific keywords to help identify relevant events
            rule_type_keywords = {
                "firewall_policies": ["firewall", "policy", "allow", "deny"],
                "traffic_rules": ["traffic", "rule"],
                "port_forwards": ["port", "forward", "nat"],
                "traffic_routes": ["route", "traffic"],
                "legacy_firewall_rules": ["firewall", "rule", "allow", "deny"],
                "qos_rules": ["qos", "quality", "service"],
                "vpn_clients": ["vpn", "client"],
            }
            
            # Check if this message might relate to rule changes
            should_refresh = False
            refresh_reason = None
            rule_type_affected = None
            
            # Configuration changes and provisioning often relate to rule updates
            if "cfgversion" in str(message).lower() or "provisioned" in str(message).lower():
                should_refresh = True
                refresh_reason = "Configuration version change detected"
            
            # Direct rule-related events
            elif any(word in msg_type.lower() for word in ["firewall", "rule", "policy", "route", "forward", "qos"]):
                should_refresh = True
                refresh_reason = f"Rule-related event type: {msg_type}"
                
                # Try to determine the specific rule type affected
                for rule_type, keywords in rule_type_keywords.items():
                    if any(keyword in msg_type.lower() for keyword in keywords):
                        rule_type_affected = rule_type
                        break
            
            # General CRUD operations that might indicate rule changes
            elif any(op in msg_type.lower() for op in ["add", "delete", "update", "remove"]):
                # Check if the operation relates to any rule types
                message_str = str(message).lower()
                
                # Special handling for port forwards vs device port tables
                if "port" in message_str:
                    # Check if this is a device port_table update (which is distinct from port forwards)
                    if "port_table" in message_str and not any(kw in message_str for kw in ["port_forward", "portforward", "nat"]):
                        # Skip false positive port_table updates that aren't related to port forwarding
                        log_websocket("Skipping CRUD operation for port_table (not related to port forwards)")
                        return
                
                for rule_type, keywords in rule_type_keywords.items():
                    if any(keyword in message_str for keyword in keywords):
                        # For port_forwards, require more specific keywords to avoid false positives
                        if rule_type == "port_forwards" and not any(kw in message_str for kw in ["port_forward", "portforward", "nat"]):
                            continue
                            
                        should_refresh = True
                        rule_type_affected = rule_type
                        refresh_reason = f"CRUD operation detected for {rule_type}"
                        break
            
            # Device updates - only process if they contain config changes
            elif "device" in msg_type.lower() and "update" in msg_type.lower():
                # Only refresh for specific configuration changes
                message_str = str(message).lower()
                config_keywords = ["config", "firewall", "rule", "policy", "route", "qos"]
                
                # Skip updating for commonly noisy device state update patterns
                if isinstance(msg_data, list) and len(msg_data) == 1:
                    # Skip purely device state updates - these don't affect configurations
                    if set(msg_data[0].keys()).issubset({"state", "upgrade_state", "provisioned_at"}):
                        log_websocket("Skipping refresh for routine device state update: %s", 
                                      set(msg_data[0].keys()))
                        return
                
                # Check if this is specifically a port_table update (which is not related to port forwards)
                if "port_table" in message_str and not any(kw in message_str for kw in ["port_forward", "portforward", "nat"]):
                    # Skip device updates that only contain port_table information without port forwarding references
                    log_websocket("Skipping refresh for device update with port_table (not related to port forwards)")
                    return
                
                # Check if this contains configuration version changes (accept these)
                if "cfgversion" in message_str:
                    should_refresh = True
                    refresh_reason = "Device update with configuration version change"
                # Otherwise, be more selective about what triggers refreshes
                elif any(keyword in message_str for keyword in config_keywords):
                    should_refresh = True
                    refresh_reason = "Device update with potential rule changes"
                else:
                    # Not all device updates need a refresh - skip ones without config changes
                    log_websocket("Skipping refresh for device update without rule-related changes")
                    return
            
            # Check for QoS-specific event patterns that might not be caught by other checks
            if not should_refresh and "qos" in str(message).lower():
                should_refresh = True
                rule_type_affected = "qos_rules"
                refresh_reason = "QoS-related event detected"
                log_websocket("QoS-specific event detected: %s", msg_type)
            
            if should_refresh:
                # Use a semaphore to prevent multiple concurrent refreshes
                if not hasattr(self, '_refresh_semaphore'):
                    self._refresh_semaphore = asyncio.Semaphore(1)
                
                # Only proceed if we can acquire the semaphore
                if self._refresh_semaphore.locked():
                    log_websocket("Skipping refresh as one is already in progress")
                    return
                
                # Should prevent rapid-fire refreshes during switch operations
                self._min_ws_refresh_interval = 1.5
                
                current_time = time.time()
                if current_time - self._last_ws_refresh < self._min_ws_refresh_interval:
                    log_websocket(
                        "Debouncing refresh request (last refresh was %0.1f seconds ago)",
                        current_time - self._last_ws_refresh
                    )
                    
                    # Cancel any pending refresh task
                    if self._ws_refresh_task and not self._ws_refresh_task.done():
                        self._ws_refresh_task.cancel()
                    
                    # Schedule a delayed refresh if one isn't already pending
                    if not self._pending_ws_refresh:
                        self._pending_ws_refresh = True
                        delay = self._min_ws_refresh_interval - (current_time - self._last_ws_refresh)
                        
                        async def delayed_refresh():
                            await asyncio.sleep(delay)
                            self._pending_ws_refresh = False
                            log_websocket("Executing delayed refresh after debounce period")
                            # Use the standard refresh workflow for all rule types
                            await self._controlled_refresh_wrapper()
                        
                        self._ws_refresh_task = self.hass.async_create_task(delayed_refresh())
                    return
                
                # Update last refresh timestamp
                self._last_ws_refresh = current_time
                
                log_websocket("Refreshing data due to: %s (rule type: %s)", 
                             refresh_reason, rule_type_affected or "unknown")
                
                # Use the standard refresh workflow for all rule types
                self.hass.async_create_task(self._controlled_refresh_wrapper())
            elif DEBUG_WEBSOCKET:
                # Only log non-refreshing messages when debug is enabled
                log_websocket("No refresh triggered for message type: %s", msg_type)

        except Exception as err:
            LOGGER.error("Error handling websocket message: %s", err)
    
    async def _controlled_refresh_wrapper(self):
        """Wrapper for the controlled refresh process to ensure proper semaphore handling."""
        # Acquire semaphore before starting refresh
        async def controlled_refresh():
            async with self._refresh_semaphore:
                await self._force_refresh_with_cache_clear()
                # Wait a moment before refreshing entities to let states settle
                await asyncio.sleep(0.5)
                self.async_update_listeners()
        
        # Start the controlled refresh task and await it
        await controlled_refresh()

    async def _force_refresh_with_cache_clear(self) -> None:
        """Force a refresh with cache clearing to ensure fresh data.
        
        This method is triggered by WebSocket events and follows the same core refresh
        and entity management logic as the regular polling updates:
        1. Clear API cache (but preserve authentication)
        2. Call async_refresh() which updates rule collections
        3. Process new entities through the same entity creation path
        4. Check for deleted rules to maintain consistency with polling
        
        The only major difference is the explicit call to _check_for_deleted_rules()
        which happens automatically during polling updates.
        """
        try:
            # Log that we're starting a refresh
            log_websocket("Starting forced refresh after rule change detected")
            
            # Store previous data for deletion detection
            previous_data = self.data.copy() if self.data else {}
            
            # Clear the API cache to ensure we get fresh data
            # But do so without disrupting authentication
            LOGGER.debug("Clearing API cache")
            if hasattr(self.api, "clear_cache"):
                await self.api.clear_cache()  # Modified in API to preserve auth
            else:
                LOGGER.warning("API object does not have clear_cache method")
            LOGGER.debug("API cache cleared")
            log_data("Cache cleared before refresh")
            
            # Force a full data refresh
            refresh_successful = await self.async_refresh()
            
            if refresh_successful:
                # After refreshing data, discovery and deletion checks are handled within async_refresh -> _async_update_data
                # REMOVED: await self.process_new_entities() # Redundant
                # REMOVED: if previous_data: # Incorrect check
                # REMOVED:     self._check_for_deleted_rules(previous_data) # Incorrect check
                
                # Update the data timestamp
                self._last_update = self.hass.loop.time()
                
                # Force an update of all entities
                self.async_update_listeners()
                
                log_data("Refresh completed successfully after WebSocket event")
            else:
                LOGGER.error("WebSocket-triggered refresh failed")
        except Exception as err:
            LOGGER.error("Error during forced refresh: %s", err)

    @callback
    def shutdown(self) -> None:
        """Clean up resources."""
        for cleanup_callback in self._cleanup_callbacks:
            cleanup_callback()
            
    async def async_shutdown(self) -> None:
        """Clean up resources asynchronously."""
        # Call the synchronous shutdown method
        self.shutdown()
        
        # Any additional async cleanup can be added here
        # For example, wait for pending tasks to complete

    async def _handle_auth_failure(self):
        """Handle authentication failures from API operations."""
        LOGGER.info("Authentication failure callback triggered, requesting data refresh")
        # Reset authentication flag
        self._authentication_in_progress = False
        
        # Reset _consecutive_errors to avoid conflating API errors with auth errors
        self._consecutive_errors = 0
        
        # Notify any entities that have optimistic state to handle auth issues appropriately
        async_dispatcher_send(self.hass, f"{DOMAIN}_auth_failure")
        
        # Request a refresh with some delay to allow auth to stabilize
        await asyncio.sleep(2.0)
        
        # Ensure a fresh session before refresh
        try:
            if hasattr(self.api, "refresh_session"):
                LOGGER.debug("Refreshing session before data refresh")
                await self.api.refresh_session(force=True)
        except Exception as err:
            LOGGER.error("Error refreshing session during auth recovery: %s", str(err))
            
        # Force a full refresh
        await self.async_refresh()
        
        # After successful refresh, notify components to clear any error states
        async_dispatcher_send(self.hass, f"{DOMAIN}_auth_restored")

    def set_entity_removal_callback(self, callback):
        """Set callback for entity removal.
        
        Args:
            callback: Function to call when an entity should be removed
        """
        self._entity_removal_callback = callback
        LOGGER.debug("Entity removal callback registered")

    async def _schedule_queue_reprocessing(self) -> None:
        """Schedule a delayed reprocessing of the entity creation queue."""
        import asyncio
        await asyncio.sleep(5)  # Wait 5 seconds before retrying
        await self._process_entity_queue()

    async def process_new_entities(self) -> None:
        """Check for new entities in all rule types and queue them for creation."""
        LOGGER.debug("Starting process_new_entities check")
        
        # Create sets of currently tracked rule IDs for comparison
        port_forwards_to_add = {
            get_rule_id(rule) for rule in self.port_forwards
            if get_rule_id(rule) not in self.known_unique_ids and get_rule_id(rule) is not None
        }
        
        routes_to_add = {
            get_rule_id(rule) for rule in self.traffic_routes 
            if get_rule_id(rule) not in self.known_unique_ids and get_rule_id(rule) is not None
        }
        
        policies_to_add = {
            get_rule_id(rule) for rule in self.firewall_policies 
            if get_rule_id(rule) not in self.known_unique_ids and get_rule_id(rule) is not None
        }
        
        traffic_rules_to_add = {
            get_rule_id(rule) for rule in self.traffic_rules 
            if get_rule_id(rule) not in self.known_unique_ids and get_rule_id(rule) is not None
        }
        
        firewall_rules_to_add = {
            get_rule_id(rule) for rule in self.legacy_firewall_rules 
            if get_rule_id(rule) not in self.known_unique_ids and get_rule_id(rule) is not None
        }
        
        wlans_to_add = {
            get_rule_id(rule) for rule in self.wlans 
            if get_rule_id(rule) not in self.known_unique_ids and get_rule_id(rule) is not None
        }
        
        # Add set for QoS rules
        qos_rules_to_add = {
            get_rule_id(rule) for rule in self.qos_rules
            if get_rule_id(rule) not in self.known_unique_ids and get_rule_id(rule) is not None
        }
        
        # Add set for VPN clients
        vpn_clients_to_add = {
            get_rule_id(rule) for rule in self.vpn_clients
            if get_rule_id(rule) not in self.known_unique_ids and get_rule_id(rule) is not None
        }
        
        # Log counts of new rules detected
        if (port_forwards_to_add or routes_to_add or policies_to_add or 
            traffic_rules_to_add or firewall_rules_to_add or wlans_to_add or qos_rules_to_add or vpn_clients_to_add):
            LOGGER.debug(
                "Detected new rules - Port Forwards: %d, Traffic Routes: %d, "
                "Firewall Policies: %d, Traffic Rules: %d, Legacy Firewall Rules: %d, WLANs: %d, QoS Rules: %d, VPN Clients: %d",
                len(port_forwards_to_add), len(routes_to_add), len(policies_to_add),
                len(traffic_rules_to_add), len(firewall_rules_to_add), len(wlans_to_add),
                len(qos_rules_to_add), len(vpn_clients_to_add)
            )
        
        # Queue new entities for creation
        for rule in self.port_forwards:
            rule_id = get_rule_id(rule)
            if rule_id in port_forwards_to_add:
                LOGGER.debug("Queueing new port forward for creation: %s (class: %s)", 
                           rule_id, type(rule).__name__)
                # Ensure rule is valid before queueing
                if hasattr(rule, 'id'):
                    self._entity_creation_queue.append({
                        "rule_type": "port_forwards",
                        "rule": rule
                    })
                    self.known_unique_ids.add(rule_id)
                else:
                    LOGGER.error("Cannot queue port forward rule without id attribute")
                
        for rule in self.traffic_routes:
            rule_id = get_rule_id(rule)
            if rule_id in routes_to_add:
                LOGGER.debug("Queueing new traffic route for creation: %s (class: %s)", 
                           rule_id, type(rule).__name__)
                # Ensure rule is valid before queueing
                if hasattr(rule, 'id'):
                    self._entity_creation_queue.append({
                        "rule_type": "traffic_routes",
                        "rule": rule
                    })
                    self.known_unique_ids.add(rule_id)
                else:
                    LOGGER.error("Cannot queue traffic route rule without id attribute")
                
        for rule in self.firewall_policies:
            rule_id = get_rule_id(rule)
            if rule_id in policies_to_add:
                LOGGER.debug(
                    "Queueing new firewall policy for creation: %s (class: %s)",
                    rule_id, 
                    type(rule).__name__
                )
                # Ensure rule is valid before queueing
                if hasattr(rule, 'id'):
                    self._entity_creation_queue.append({
                        "rule_type": "firewall_policies",
                        "rule": rule
                    })
                    self.known_unique_ids.add(rule_id)
                else:
                    LOGGER.error("Cannot queue firewall policy rule without id attribute")

        for rule in self.traffic_rules:
            rule_id = get_rule_id(rule)
            if rule_id in traffic_rules_to_add:
                LOGGER.debug("Queueing new traffic rule for creation: %s (class: %s)", 
                          rule_id, type(rule).__name__)
                # Ensure rule is valid before queueing
                if hasattr(rule, 'id'):
                    self._entity_creation_queue.append({
                        "rule_type": "traffic_rules",
                        "rule": rule
                    })
                    self.known_unique_ids.add(rule_id)
                else:
                    LOGGER.error("Cannot queue traffic rule without id attribute")
                
        for rule in self.legacy_firewall_rules:
            rule_id = get_rule_id(rule)
            if rule_id in firewall_rules_to_add:
                LOGGER.debug("Queueing new firewall rule for creation: %s (class: %s)", 
                          rule_id, type(rule).__name__)
                # Ensure rule is valid before queueing
                if hasattr(rule, 'id'):
                    self._entity_creation_queue.append({
                        "rule_type": "legacy_firewall_rules",
                        "rule": rule
                    })
                    self.known_unique_ids.add(rule_id)
                else:
                    LOGGER.error("Cannot queue legacy firewall rule without id attribute")
                
        for rule in self.wlans:
            rule_id = get_rule_id(rule)
            if rule_id in wlans_to_add:
                LOGGER.debug(
                    "Queueing new WLAN for creation: %s (class: %s)",
                    rule_id, 
                    type(rule).__name__
                )
                # Ensure rule is valid before queueing
                if hasattr(rule, 'id'):
                    self._entity_creation_queue.append({
                        "rule_type": "wlans",
                        "rule": rule
                    })
                    self.known_unique_ids.add(rule_id)
                else:
                    LOGGER.error("Cannot queue WLAN rule without id attribute")
                    
        # Add section for QoS rules
        for rule in self.qos_rules:
            rule_id = get_rule_id(rule)
            LOGGER.debug("Processing QoS rule with ID: %s, tracked: %s, in add set: %s", 
                       rule_id, 
                       rule_id in self.known_unique_ids,
                       rule_id in qos_rules_to_add)
            if rule_id in qos_rules_to_add:
                LOGGER.debug(
                    "Queueing new QoS rule for creation: %s (class: %s)",
                    rule_id, 
                    type(rule).__name__
                )
                # Ensure rule is valid before queueing
                if hasattr(rule, 'id'):
                    LOGGER.info("Adding QoS rule to entity creation queue: %s", rule_id)
                    self._entity_creation_queue.append({
                        "rule_type": "qos_rules",
                        "rule": rule
                    })
                    self.known_unique_ids.add(rule_id)
                else:
                    LOGGER.error("Cannot queue QoS rule without id attribute")

        # Add section for VPN clients
        for rule in self.vpn_clients:
            rule_id = get_rule_id(rule)
            LOGGER.debug("Processing VPN client with ID: %s, tracked: %s, in add set: %s", 
                       rule_id, 
                       rule_id in self.known_unique_ids,
                       rule_id in vpn_clients_to_add)
            if rule_id in vpn_clients_to_add:
                LOGGER.debug(
                    "Queueing new VPN client for creation: %s (class: %s)",
                    rule_id, 
                    type(rule).__name__
                )
                # Ensure rule is valid before queueing
                if hasattr(rule, 'id'):
                    LOGGER.info("Adding VPN client to entity creation queue: %s", rule_id)
                    self._entity_creation_queue.append({
                        "rule_type": "vpn_clients",
                        "rule": rule
                    })
                    self.known_unique_ids.add(rule_id)
                else:
                    LOGGER.error("Cannot queue VPN client without id attribute")

    async def _discover_and_add_new_entities(self, new_data: Dict[str, List[Any]]) -> None:
        """Discover new rules from fetched data and dynamically add corresponding entities."""
        if not self.async_add_entities_callback:
            LOGGER.debug("Coordinator: async_add_entities_callback not set, skipping dynamic entity creation.")
            return

        LOGGER.debug("Coordinator: Starting discovery of new entities.")
        potential_entities_data = {} # Map: unique_id -> {rule_data, rule_type, entity_class}
        all_current_unique_ids = set() # Keep track of all IDs found in this run

        # Import necessary entity classes here to avoid circular imports at module level
        from .switch import (
            UnifiPortForwardSwitch,
            UnifiTrafficRouteSwitch,
            UnifiFirewallPolicySwitch,
            UnifiTrafficRuleSwitch,
            UnifiLegacyFirewallRuleSwitch,
            UnifiQoSRuleSwitch,
            UnifiWlanSwitch,
            UnifiTrafficRouteKillSwitch,
            UnifiVPNClientSwitch
        )
        # Use a relative import for helpers
        from .helpers.rule import get_rule_id, get_child_unique_id 

        all_rule_source_configs = [
            ("port_forwards", UnifiPortForwardSwitch),
            ("traffic_routes", UnifiTrafficRouteSwitch),
            ("firewall_policies", UnifiFirewallPolicySwitch),
            ("traffic_rules", UnifiTrafficRuleSwitch),
            ("legacy_firewall_rules", UnifiLegacyFirewallRuleSwitch),
            ("qos_rules", UnifiQoSRuleSwitch),
            ("wlans", UnifiWlanSwitch),
            ("vpn_clients", UnifiVPNClientSwitch),
        ]

        # Gather potential entities from the NEW data
        for rule_type_key, entity_class in all_rule_source_configs:
            rules = new_data.get(rule_type_key, []) # Use new_data here
            if not rules:
                continue
            for rule in rules:
                try:
                    rule_id = get_rule_id(rule)
                    if not rule_id:
                        continue # Skip rules without ID

                    all_current_unique_ids.add(rule_id)
                    # Only consider if not already known
                    if rule_id not in self.known_unique_ids:
                        potential_entities_data[rule_id] = {
                            "rule_data": rule,
                            "rule_type": rule_type_key, # Use the key
                            "entity_class": entity_class,
                        }
                        LOGGER.debug("Coordinator: Discovered potential new entity: %s (%s)", rule_id, rule_type_key)

                    # Special handling for Traffic Routes Kill Switch
                    if rule_type_key == "traffic_routes" and hasattr(rule, 'raw') and "kill_switch_enabled" in rule.raw:
                        kill_switch_id = get_child_unique_id(rule_id, "kill_switch")
                        all_current_unique_ids.add(kill_switch_id)
                        if kill_switch_id not in self.known_unique_ids:
                            # Use PARENT rule data for the kill switch
                            potential_entities_data[kill_switch_id] = {
                                "rule_data": rule, # Parent data
                                "rule_type": rule_type_key, # Use the key
                                "entity_class": UnifiTrafficRouteKillSwitch,
                            }
                            LOGGER.debug("Coordinator: Discovered potential new kill switch: %s (for parent %s)", kill_switch_id, rule_id)
                except Exception as err:
                    LOGGER.warning("Coordinator: Error processing rule during dynamic discovery: %s", err)

        # Find IDs that are known but no longer present in the current data (should be handled by deletion logic, but double-check)
        stale_known_ids = self.known_unique_ids - all_current_unique_ids
        if stale_known_ids:
             LOGGER.debug("Coordinator: Found %d known IDs no longer present in current data.", len(stale_known_ids))
             # Optionally, force remove them from known_unique_ids here if deletion logic is unreliable?
             self.known_unique_ids -= stale_known_ids
             for stale_id in stale_known_ids:
                 LOGGER.info("Coordinator: Forcibly removing stale ID from tracking: %s", stale_id)
                 self._remove_entity_async(stale_id)

        # --- Create and Add New Entities ---
        entities_to_add = []
        added_ids_this_run = set()
        if not potential_entities_data:
            LOGGER.debug("Coordinator: No new entities discovered.")
            return

        LOGGER.debug("Coordinator: Creating instances for %d discovered potential new entities...", len(potential_entities_data))
        entity_map = {} # Store created entities to link parents/children

        for unique_id, data in potential_entities_data.items():
            # Double check it wasn't added in this run already (e.g. if discovered twice)
            if unique_id in self.known_unique_ids or unique_id in added_ids_this_run:
                 LOGGER.warning("Coordinator: Skipping entity creation for %s as it's already known or added.", unique_id)
                 continue
            try:
                entity_class = data["entity_class"]
                entity = entity_class(
                    self, # Pass coordinator
                    data["rule_data"],
                    data["rule_type"],
                    self.config_entry.entry_id if self.config_entry else None # Pass entry_id if available
                )

                # Sanity check unique ID
                if entity.unique_id != unique_id:
                    LOGGER.error("Coordinator: Mismatch! Expected unique_id %s but created entity has %s. Skipping.", unique_id, entity.unique_id)
                    continue

                entities_to_add.append(entity)
                added_ids_this_run.add(unique_id)
                entity_map[unique_id] = entity # Store for linking
                LOGGER.debug("Coordinator: Created new entity instance for %s", unique_id)

            except Exception as err:
                LOGGER.error("Coordinator: Error creating new entity instance for unique_id %s: %s", unique_id, err)

        # --- Establish Parent/Child Links for newly created entities ---
        if entity_map:
             LOGGER.debug("Coordinator: Establishing parent/child links for %d newly created entities...", len(entity_map))
             for unique_id, entity in entity_map.items():
                 # If it's a kill switch, find its parent in the map or existing entities
                 if isinstance(entity, UnifiTrafficRouteKillSwitch) and entity.linked_parent_id:
                     parent_id = entity.linked_parent_id
                     parent_entity = entity_map.get(parent_id)
                     # If parent wasn't created in this run, look it up in hass.data
                     if not parent_entity:
                         parent_entity_id_in_hass = None
                         registry = self.hass.helpers.entity_registry.async_get(self.hass)
                         if registry:
                              parent_entity_id_in_hass = registry.async_get_entity_id("switch", DOMAIN, parent_id)
                         if parent_entity_id_in_hass:
                              parent_entity = self.hass.data.get(DOMAIN, {}).get('entities', {}).get(parent_entity_id_in_hass)

                     if parent_entity and isinstance(parent_entity, UnifiTrafficRouteSwitch):
                          parent_entity.register_child_entity(unique_id)
                          entity.register_parent_entity(parent_id)
                          LOGGER.debug("Coordinator: Linked new child %s to parent %s", unique_id, parent_id)
                     else:
                          LOGGER.warning("Coordinator: Could not find parent entity %s for new kill switch %s", parent_id, unique_id)

        # --- Add Entities to Home Assistant ---
        if entities_to_add:
            LOGGER.info("Coordinator: Dynamically adding %d new entities to Home Assistant.", len(entities_to_add))
            try:
                self.async_add_entities_callback(entities_to_add)
                # Update known IDs *after* successful addition
                self.known_unique_ids.update(added_ids_this_run)
                LOGGER.debug("Coordinator: Added %d new IDs to known_unique_ids (Total: %d)",
                             len(added_ids_this_run), len(self.known_unique_ids))
            except Exception as add_err:
                 LOGGER.error("Coordinator: Failed to dynamically add entities: %s", add_err)
        else:
             LOGGER.debug("Coordinator: No new entities to add dynamically in this cycle.")
