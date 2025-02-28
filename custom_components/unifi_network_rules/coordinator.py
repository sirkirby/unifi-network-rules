"""UniFi Network Rules Coordinator."""
from __future__ import annotations

from datetime import timedelta
import asyncio
from typing import Any, Dict, Callable, List

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward
from aiounifi.models.firewall_zone import FirewallZone
from aiounifi.models.wlan import Wlan

from .const import DOMAIN, LOGGER, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DEBUG_WEBSOCKET
from .udm import UDMAPI
from .websocket import SIGNAL_WEBSOCKET_MESSAGE, UnifiRuleWebsocket
from .helpers.rule import get_rule_id
from .utils.logger import log_data, log_websocket
from .models.firewall_rule import FirewallRule  # Import the FirewallRule type

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
        
        # Track authentication failures and API issues
        self._auth_failures = 0
        self._max_auth_failures = 3
        self._last_successful_data = None
        self._consecutive_errors = 0
        self._in_error_state = False
        
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
        self.websocket.set_message_handler(self._handle_websocket_message)

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
        
        # Sets to track what rules we have seen for deletion detection
        self._tracked_port_forwards = set()
        self._tracked_routes = set()
        self._tracked_policies = set()
        self._tracked_traffic_rules = set()
        self._tracked_firewall_rules = set()  
        self._tracked_wlans = set()
        
        # Entity removal callback
        self._entity_removal_callback = None
        
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
        """Fetch data from API endpoint."""
        # Use a lock to prevent concurrent updates, especially during authentication
        if self._update_lock.locked():
            LOGGER.debug("Another update is already in progress, waiting for it to complete")
            # If an update is already in progress, wait for it to complete and use its result
            if self.data:
                return self.data
            elif self._last_successful_data:
                return self._last_successful_data
        
        async with self._update_lock:
            try:
                # Track authentication state at start of update
                authentication_active = self._authentication_in_progress
                if authentication_active:
                    LOGGER.warning("Update started while authentication is in progress - using cached data")
                    if self.data:
                        return self.data
                    elif self._last_successful_data:
                        return self._last_successful_data
                
                # ADDED: Log at start of update
                LOGGER.info("Starting data update process - current data state: %s", 
                           {k: len(v) if isinstance(v, list) else v 
                            for k, v in (self.data or {}).items()})
                
                # Proactively refresh the session to prevent 403 errors
                # Only refresh every 5 minutes to avoid excessive API calls
                refresh_interval = 300  # seconds
                current_time = asyncio.get_event_loop().time()
                last_refresh = getattr(self, "_last_session_refresh", 0)
                
                if current_time - last_refresh > refresh_interval:
                    LOGGER.debug("Proactively refreshing session")
                    try:
                        # We'll track successful refreshes but not fail the update if refresh fails
                        refresh_success = await self.api.refresh_session()
                        if refresh_success:
                            self._last_session_refresh = current_time
                            LOGGER.debug("Session refresh successful")
                        else:
                            LOGGER.warning("Session refresh skipped or failed, continuing with update")
                    except Exception as refresh_err:
                        LOGGER.warning("Failed to refresh session: %s", str(refresh_err))
                        # Continue with update despite refresh failure
                
                # Ensure we always use force_refresh to avoid stale data issues
                LOGGER.debug("Starting data refresh cycle with force_refresh=True")
                
                # Initialize with empty lists for each rule type
                rules_data: Dict[str, List[Any]] = {
                    "firewall_policies": [],
                    "traffic_rules": [],
                    "port_forwards": [],
                    "traffic_routes": [],
                    "firewall_zones": [],
                    "wlans": [],
                    "legacy_firewall_rules": []
                }
                
                # Store the previous data to detect deletions and protect against API failures
                previous_data = self.data.copy() if self.data else {}
                
                # Check if we're rate limited before proceeding
                if hasattr(self.api, "_rate_limited") and self.api._rate_limited:
                    current_time = asyncio.get_event_loop().time()
                    if current_time < getattr(self.api, "_rate_limit_until", 0):
                        # If rate limited, return last good data and don't attempt API calls
                        LOGGER.warning(
                            "Rate limit in effect. Skipping update and returning last good data. "
                            "This prevents excessive API calls during rate limiting."
                        )
                        if self._last_successful_data:
                            return self._last_successful_data
                        else:
                            return rules_data
                
                # Clear any caches before fetching to ensure we get fresh data
                await self.api.clear_cache()
                
                # Log the start of the update process
                LOGGER.debug("Beginning rule data collection with fresh cache")
                
                # Periodically force a cleanup of stale entities (once per hour)
                force_cleanup_interval = 3600  # seconds
                last_cleanup = getattr(self, "_last_entity_cleanup", 0)
                if current_time - last_cleanup > force_cleanup_interval:
                    setattr(self, "_force_cleanup", True)
                    setattr(self, "_last_entity_cleanup", current_time)
                    LOGGER.debug("Scheduling forced entity cleanup after this update cycle")
                
                # Add delay between API calls to avoid rate limiting
                # Increase the delay for more aggressive throttling
                api_call_delay = 1.0  # seconds (increased from default)
                
                # Track authentication failures during the update
                auth_failure_during_update = False
                
                # First get firewall policies
                await self._update_firewall_policies_in_dict(rules_data)
                await asyncio.sleep(api_call_delay)
                
                # Then port forwards - CRITICAL to preserve during auth failures
                port_forwards_success = await self._update_port_forwards_in_dict(rules_data)
                if not port_forwards_success and "401 Unauthorized" in str(self.api._last_error_message):
                    auth_failure_during_update = True
                    LOGGER.warning("Authentication failure detected during port forwards fetch")
                    # Preserve previous port forwards data if available
                    if previous_data and "port_forwards" in previous_data and previous_data["port_forwards"]:
                        LOGGER.info("Preserving previous port forwards data during authentication failure")
                        rules_data["port_forwards"] = previous_data["port_forwards"]
                
                await asyncio.sleep(api_call_delay)
                
                # Then traffic routes
                await self._update_traffic_routes_in_dict(rules_data)
                await asyncio.sleep(api_call_delay)
                
                # Then firewall zones
                await self._update_firewall_zones_in_dict(rules_data)
                await asyncio.sleep(api_call_delay)
                
                # Then WLANs
                await self._update_wlans_in_dict(rules_data)
                await asyncio.sleep(api_call_delay)
                
                # Then traffic rules
                await self._update_traffic_rules_in_dict(rules_data)
                await asyncio.sleep(api_call_delay)
                
                # Finally legacy firewall rules
                await self._update_legacy_firewall_rules_in_dict(rules_data)
                
                # Log detailed info for traffic routes
                LOGGER.debug("Traffic routes received: %d items", len(rules_data["traffic_routes"]))
                for route in rules_data["traffic_routes"]:
                    _log_rule_info(route)
                
                # Verify the data is valid - check if we have at least some data in key categories
                # This helps prevent entity removal during temporary API errors
                data_valid = (
                    len(rules_data["firewall_policies"]) > 0 or 
                    len(rules_data["traffic_rules"]) > 0 or
                    len(rules_data["port_forwards"]) > 0 or
                    len(rules_data["traffic_routes"]) > 0
                )
                
                # Special handling for authentication failures
                if auth_failure_during_update:
                    LOGGER.warning("Authentication issues detected during update - preserving existing data")
                    # If authentication failures occurred, preserve previous data for key categories
                    for key in ["port_forwards", "firewall_policies", "traffic_rules", "traffic_routes"]:
                        if not rules_data[key] and previous_data and key in previous_data and previous_data[key]:
                            LOGGER.info(f"Preserving previous {key} data due to authentication issues")
                            rules_data[key] = previous_data[key]
                
                # If we get no data but had data before, likely a temporary API issue
                if not data_valid and previous_data and any(
                    len(previous_data.get(key, [])) > 0 
                    for key in ["firewall_policies", "traffic_rules", "port_forwards", "traffic_routes"]
                ):
                    # We're in a potential error state
                    self._consecutive_errors += 1
                    LOGGER.warning(
                        "No valid rule data received but had previous data. "
                        "Likely a temporary API issue (attempt %d).", 
                        self._consecutive_errors
                    )
                    
                    # If this is a persistent issue (3+ consecutive failures)
                    if self._consecutive_errors >= 3:
                        if not self._in_error_state:
                            LOGGER.error(
                                "Multiple consecutive empty data responses. "
                                "API may be experiencing issues. Using last valid data."
                            )
                            self._in_error_state = True
                            
                        # Return last known good data instead of empty data
                        if self._last_successful_data:
                            LOGGER.info("Using cached data from last successful update")
                            return self._last_successful_data
                        
                    # Try forcing a session refresh on error - mark authentication in progress
                    self._authentication_in_progress = True
                    try:
                        LOGGER.info("Forcing session refresh due to API data issue")
                        await self.api.refresh_session()
                    except Exception as session_err:
                        LOGGER.error("Failed to refresh session during error recovery: %s", session_err)
                    finally:
                        self._authentication_in_progress = False
                    
                    # If we have previous data and this is likely a temporary failure, return previous data
                    if previous_data:
                        LOGGER.info("Returning previous data during API issue")
                        return previous_data
                        
                    # Otherwise, raise an error
                    raise UpdateFailed("Failed to get any valid rule data")
                
                # If we got here with valid data, reset error counters
                if data_valid:
                    if self._consecutive_errors > 0:
                        LOGGER.info("Recovered from API data issue after %d attempts", self._consecutive_errors)
                    self._consecutive_errors = 0
                    self._in_error_state = False
                    self._last_successful_data = rules_data.copy()
                    
                    # Check for deleted rules in latest update
                    if previous_data:
                        LOGGER.debug("Checking for deleted rules in latest update")
                        self._check_for_deleted_rules(previous_data, rules_data)
                    
                    # Update rule collections from new data for immediate use
                    self.port_forwards = rules_data.get("port_forwards", [])
                    self.traffic_routes = rules_data.get("traffic_routes", [])
                    self.firewall_policies = rules_data.get("firewall_policies", [])
                    self.traffic_rules = rules_data.get("traffic_rules", [])
                    self.legacy_firewall_rules = rules_data.get("legacy_firewall_rules", [])
                    self.wlans = rules_data.get("wlans", [])
                    self.firewall_zones = rules_data.get("firewall_zones", [])
                    
                    # Log the populated rule counts
                    LOGGER.info("Rule collections after update: Port Forwards=%d, Traffic Routes=%d, Firewall Policies=%d, Traffic Rules=%d, Legacy Firewall Rules=%d, WLANs=%d", 
                               len(self.port_forwards),
                               len(self.traffic_routes),
                               len(self.firewall_policies),
                               len(self.traffic_rules),
                               len(self.legacy_firewall_rules),
                               len(self.wlans))
                    
                return rules_data
                
            except Exception as err:
                LOGGER.error("Error updating coordinator data: %s", err)
                
                # Check if this is an authentication error
                if "401 Unauthorized" in str(err) or "403 Forbidden" in str(err):
                    self._auth_failures += 1
                    self._authentication_in_progress = True
                    try:
                        LOGGER.warning("Authentication failure #%d during data update", self._auth_failures)
                        
                        # Try to refresh the session if we haven't exceeded max failures
                        if self._auth_failures < self._max_auth_failures:
                            LOGGER.info("Attempting to refresh authentication session")
                            try:
                                await self.api.refresh_session()
                                # If we succeeded in refreshing, return the previous data
                                if self.data:
                                    return self.data
                            except Exception as refresh_err:
                                LOGGER.error("Failed to refresh session: %s", refresh_err)
                    finally:
                        self._authentication_in_progress = False
                
                # Return previous data during errors if available to prevent entity flickering
                if self.data:
                    LOGGER.info("Returning previous data during error")
                    return self.data
                    
                raise UpdateFailed(f"Error updating data: {err}")

    def _check_for_deleted_rules(self, previous_data: Dict[str, List[Any]], new_data: Dict[str, List[Any]]) -> None:
        """Check for rules that existed in previous data but not in new data."""
        # Only process rule types that would create entities
        entity_rule_types = [
            "firewall_policies",
            "traffic_rules", 
            "port_forwards", 
            "traffic_routes",
            "legacy_firewall_rules"
        ]
        
        LOGGER.debug("Starting deletion check between previous and new data sets")
        
        for rule_type in entity_rule_types:
            if rule_type not in previous_data or rule_type not in new_data:
                LOGGER.debug("Skipping %s - not found in both datasets", rule_type)
                continue
                
            LOGGER.debug("Checking for deletions in %s: Previous count: %d, Current count: %d", 
                         rule_type, len(previous_data[rule_type]), len(new_data[rule_type]))
            
            # Process each rule type to detect and handle deletions
            deleted_ids = self._detect_deleted_rules(
                rule_type,
                previous_data[rule_type],
                new_data[rule_type]
            )
            
            if deleted_ids:
                self._process_deleted_rules(rule_type, deleted_ids, len(previous_data[rule_type]))

    async def _detect_deleted_rules(self, current_data: Dict[str, List[Any]], previous_data: Dict[str, List[Any]], rule_type: str) -> None:
        """Detect rules that have been deleted and remove associated entities."""
        # Create maps of current rules by their IDs
        current_port_forwards = {
            get_rule_id(rule): rule for rule in self.port_forwards
        }
        current_routes = {
            get_rule_id(rule): rule for rule in self.traffic_routes
        }
        current_policies = {
            get_rule_id(rule): rule for rule in self.firewall_policies
        }
        current_traffic_rules = {
            get_rule_id(rule): rule for rule in self.traffic_rules
        }
        current_firewall_rules = {
            get_rule_id(rule): rule for rule in self.legacy_firewall_rules
        }
        current_wlans = {
            get_rule_id(rule): rule for rule in self.wlans
        }
        
        # Check if previously tracked rules are still in the current rules
        # For each rule type, if a previously tracked rule is not in current_rules,
        # call on_entity_remove to remove the corresponding entity
        
        # Port Forwards
        for rule_id in self._tracked_port_forwards.copy():
            if rule_id not in current_port_forwards:
                LOGGER.debug("Detected deleted port forward: %s", rule_id)
                self._remove_entity(rule_id)
                self._tracked_port_forwards.remove(rule_id)
                
        # Traffic Routes
        for rule_id in self._tracked_routes.copy():
            if rule_id not in current_routes:
                LOGGER.debug("Detected deleted route: %s", rule_id)
                self._remove_entity(rule_id)
                self._tracked_routes.remove(rule_id)
                
        # Firewall Policies
        for rule_id in self._tracked_policies.copy():
            if rule_id not in current_policies:
                LOGGER.debug("Detected deleted policy: %s", rule_id)
                self._remove_entity(rule_id)
                self._tracked_policies.remove(rule_id)
                
        # Traffic Rules
        for rule_id in self._tracked_traffic_rules.copy():
            if rule_id not in current_traffic_rules:
                LOGGER.debug("Detected deleted traffic rule: %s", rule_id)
                self._remove_entity(rule_id)
                self._tracked_traffic_rules.remove(rule_id)
                
        # Legacy Firewall Rules
        for rule_id in self._tracked_firewall_rules.copy():
            if rule_id not in current_firewall_rules:
                LOGGER.debug("Detected deleted firewall rule: %s", rule_id)
                self._remove_entity(rule_id)
                self._tracked_firewall_rules.remove(rule_id)
                
        # WLANs
        for rule_id in self._tracked_wlans.copy():
            if rule_id not in current_wlans:
                LOGGER.debug("Detected deleted WLAN: %s", rule_id)
                self._remove_entity(rule_id)
                self._tracked_wlans.remove(rule_id)

        # Update tracked rules to current state
        self._tracked_port_forwards = set(current_port_forwards.keys())
        self._tracked_routes = set(current_routes.keys())
        self._tracked_policies = set(current_policies.keys())
        self._tracked_traffic_rules = set(current_traffic_rules.keys())
        self._tracked_firewall_rules = set(current_firewall_rules.keys())
        self._tracked_wlans = set(current_wlans.keys())

    def _process_deleted_rules(self, rule_type: str, deleted_ids: set, total_previous_count: int) -> None:
        """Process detected rule deletions and dispatch removal events.
        
        Args:
            rule_type: The type of rule being processed
            deleted_ids: Set of rule IDs that were detected as deleted
            total_previous_count: Total number of rules in the previous update
        """
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
        
        LOGGER.info("Found %d deleted %s rules: %s", len(deleted_ids), rule_type, deleted_ids)
    
        # Dispatch deletion events for each deleted rule
        for rule_id in deleted_ids:
            LOGGER.debug("Rule deletion detected - type: %s, id: %s", rule_type, rule_id)
            
            # The registry in switch.py uses the format: rule_type_rule_id (e.g., firewall_policies_unr_policy_123)
            # Use this exact format for the signal to ensure match with the registry
            entity_id = rule_id
            LOGGER.info("Dispatching entity removal for: %s", entity_id)
            
            # Debug log the signal we're sending
            LOGGER.debug("Sending signal: %s with payload: %s", f"{DOMAIN}_entity_removed", entity_id)
            
            # Use try-except to catch any dispatching errors
            try:
                # Explicitly use async_dispatcher_send directly
                async_dispatcher_send(
                    self.hass,
                    f"{DOMAIN}_entity_removed",
                    entity_id
                )
                LOGGER.debug("Entity removal signal dispatched successfully")
            except Exception as err:
                LOGGER.error("Error dispatching entity removal: %s", err)

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

    async def _update_rule_type(self, rule_type: str, fetch_method: Callable) -> None:
        """Update a specific rule type in self.data.
        
        Args:
            rule_type: The key to use in the data dictionary
            fetch_method: The API method to call to fetch the rules
        """
        LOGGER.debug("Updating %s rules", rule_type)
        try:
            rules = await fetch_method()
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
            
            rules = await fetch_method()
            
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
            
            # Check for relevant message types
            relevant_types = [
                "firewall", "rule", "policy", "traffic", "route", "port-forward",
                "delete", "update", "insert", "events"
            ]
            
            # Check if this is a relevant message type
            should_log_full = any(keyword in msg_type.lower() for keyword in relevant_types)
            
            if should_log_full:
                log_websocket("Processing important WebSocket message: %s", message)
            else:
                # For non-rule messages, just log the type without the full content
                log_websocket("Received WebSocket message type: %s (non-rule related)", msg_type)
            
            # Determine if we need to refresh data based on message
            should_refresh = False
            refresh_reason = None
            
            # Always refresh for certain events
            if msg_type in ["events", "event", "delete", "update", "insert", "changed", "alarm", "remove", "firewall"]:
                should_refresh = True
                refresh_reason = f"Event type detected: {msg_type}"
            
            # Check for data attributes that suggest a rule change
            elif isinstance(msg_data, dict):
                # Attributes that indicate policy or rule changes
                rule_attributes = ["_id", "id", "name", "enabled", "type", "deleted", "firewall", "rule", "policy"]
                
                for attr in rule_attributes:
                    if attr in msg_data:
                        should_refresh = True
                        refresh_reason = f"Rule attribute detected: {attr}"
                        break
                        
                # Check for special events that might be in nested data
                if not should_refresh and "data" in msg_data and isinstance(msg_data["data"], dict):
                    nested_data = msg_data["data"]
                    for attr in rule_attributes:
                        if attr in nested_data:
                            should_refresh = True
                            refresh_reason = f"Rule attribute detected in nested data: {attr}"
                            break
            
            # Fallback for any message containing keywords that suggest rule changes
            if not should_refresh:
                keywords = ["firewall", "rule", "policy", "delete", "removed", "deleted", "changed"]
                message_str = str(message).lower()
                
                for keyword in keywords:
                    if keyword in message_str:
                        should_refresh = True
                        refresh_reason = f"Keyword detected in message: {keyword}"
                        break
            
            if should_refresh:
                log_websocket("Refreshing data due to: %s", refresh_reason)
                # Create a task to clear cache first, then refresh
                asyncio.create_task(self._force_refresh_with_cache_clear())
            elif should_log_full:
                # Only log "no refresh" for messages we're fully logging
                log_websocket("No refresh triggered for relevant message type: %s", msg_type)

        except Exception as err:
            LOGGER.error("Error handling websocket message: %s", err)
    
    async def _force_refresh_with_cache_clear(self) -> None:
        """Force a refresh with cache clearing to ensure fresh data."""
        try:
            # Clear API cache first
            await self.api.clear_cache()
            log_data("Cache cleared before refresh")
            
            # Then force a data refresh
            await self.async_refresh()
            log_data("Refresh completed after WebSocket event")
        except Exception as err:
            LOGGER.error("Error during forced refresh: %s", err)

    @callback
    def shutdown(self) -> None:
        """Clean up resources."""
        for cleanup_callback in self._cleanup_callbacks:
            cleanup_callback()

    async def _handle_auth_failure(self):
        """Handle authentication failures from API operations."""
        LOGGER.info("Authentication failure callback triggered, requesting data refresh")
        # Reset authentication flag
        self._authentication_in_progress = False
        # Request a refresh with some delay to allow auth to stabilize
        await asyncio.sleep(2.0)
        await self.async_refresh()

    def _remove_entity(self, rule_id: str) -> None:
        """Remove entity associated with a rule.
        
        Args:
            rule_id: The rule ID generated by get_rule_id()
        """
        LOGGER.debug("Entity removal initiated for rule_id: %s", rule_id)
        
        if self._entity_removal_callback is not None:
            self._entity_removal_callback(rule_id)
        else:
            LOGGER.warning("No entity removal callback registered")

    async def async_refresh(self) -> bool:
        """Refresh data from the UniFi API."""
        try:
            if not await self.api.async_connect():
                LOGGER.warning("Failed to connect to UniFi Network API")
                return False
                
            # Use a default device name
            self.device_name = "UniFi Network Controller"
             
            # Update each rule type with specialized helper functions
            await self._update_port_forwards()
            await self._update_traffic_routes() 
            await self._update_firewall_rules()
            await self._update_traffic_rules()
            await self._update_firewall_zones()
            await self._update_wlans()
            
            # Process new entities
            await self.process_new_entities()
            
            # Process the entity creation queue if needed
            await self._process_entity_queue()
            
            self.async_set_updated_data(self.data)
            
            # Ensure the rule collections are populated from updated data
            # This is critical for entity creation and updates
            self.port_forwards = self.data.get("port_forwards", [])
            self.traffic_routes = self.data.get("traffic_routes", [])
            self.firewall_policies = self.data.get("firewall_policies", [])
            self.traffic_rules = self.data.get("traffic_rules", [])
            self.legacy_firewall_rules = self.data.get("legacy_firewall_rules", [])
            self.wlans = self.data.get("wlans", [])
            self.firewall_zones = self.data.get("firewall_zones", [])
            
            # Log the updated rule counts
            LOGGER.info("Rule collections after refresh: Port Forwards=%d, Traffic Routes=%d, Firewall Policies=%d, Traffic Rules=%d, Legacy Firewall Rules=%d, WLANs=%d", 
                       len(self.port_forwards),
                       len(self.traffic_routes),
                       len(self.firewall_policies),
                       len(self.traffic_rules),
                       len(self.legacy_firewall_rules),
                       len(self.wlans))
            
            return True
            
        except Exception as err:  # pylint: disable=broad-except
            LOGGER.exception("Error refreshing data: %s", err)
            return False

    async def _update_port_forwards(self) -> None:
        """Update port forward rules."""
        await self._update_rule_type("port_forwards", self.api.get_port_forwards)
        self.port_forwards = self.data.get("port_forwards", [])
        
    async def _update_traffic_routes(self) -> None:
        """Update traffic route rules."""
        await self._update_rule_type("traffic_routes", self.api.get_traffic_routes)
        self.traffic_routes = self.data.get("traffic_routes", [])
        
    async def _update_firewall_rules(self) -> None:
        """Update firewall rules and policies."""
        # Update legacy firewall rules
        await self._update_rule_type("legacy_firewall_rules", self.api.get_legacy_firewall_rules)
        self.legacy_firewall_rules = self.data.get("legacy_firewall_rules", [])
        
        # Update firewall policies
        await self._update_rule_type("firewall_policies", self.api.get_firewall_policies)
        self.firewall_policies = self.data.get("firewall_policies", [])
        
    async def _update_traffic_rules(self) -> None:
        """Update traffic rules."""
        await self._update_rule_type("traffic_rules", self.api.get_traffic_rules)
        self.traffic_rules = self.data.get("traffic_rules", [])
        
    async def _update_firewall_zones(self) -> None:
        """Update firewall zones."""
        await self._update_rule_type("firewall_zones", self.api.get_firewall_zones)
        self.firewall_zones = self.data.get("firewall_zones", [])
        
    async def _update_wlans(self) -> None:
        """Update WLANs."""
        await self._update_rule_type("wlans", self.api.get_wlans)
        self.wlans = self.data.get("wlans", [])
        
    async def _process_entity_queue(self) -> None:
        """Process any queued entity creation tasks."""
        if not self._entity_creation_queue:
            return
            
        async with self._queue_lock:
            LOGGER.debug("Processing entity creation queue - %d items", len(self._entity_creation_queue))
            # Process entity creation queue
            for item in self._entity_creation_queue.copy():
                rule_type = item.get("rule_type")
                rule = item.get("rule")
                if not rule or not rule_type:
                    continue
                    
                try:
                    # Call the entity creation callback if registered
                    if self.on_create_entity is not None:
                        await self.on_create_entity(rule_type, rule)
                    self._entity_creation_queue.remove(item)
                except Exception as err:  # pylint: disable=broad-except
                    LOGGER.error("Error creating entity: %s", err)
            
            LOGGER.debug("Entity queue processing complete - %d items remaining", 
                      len(self._entity_creation_queue))

    async def process_new_entities(self) -> None:
        """Check for new entities in all rule types and queue them for creation."""
        # Create sets of currently tracked rule IDs for comparison
        port_forwards_to_add = {
            get_rule_id(rule) for rule in self.port_forwards
            if get_rule_id(rule) not in self._tracked_port_forwards
        }
        
        routes_to_add = {
            get_rule_id(rule) for rule in self.traffic_routes 
            if get_rule_id(rule) not in self._tracked_routes
        }
        
        policies_to_add = {
            get_rule_id(rule) for rule in self.firewall_policies 
            if get_rule_id(rule) not in self._tracked_policies
        }
        
        traffic_rules_to_add = {
            get_rule_id(rule) for rule in self.traffic_rules 
            if get_rule_id(rule) not in self._tracked_traffic_rules
        }
        
        firewall_rules_to_add = {
            get_rule_id(rule) for rule in self.legacy_firewall_rules 
            if get_rule_id(rule) not in self._tracked_firewall_rules
        }
        
        wlans_to_add = {
            get_rule_id(rule) for rule in self.wlans 
            if get_rule_id(rule) not in self._tracked_wlans
        }
        
        # Queue new entities for creation
        for rule in self.port_forwards:
            rule_id = get_rule_id(rule)
            if rule_id in port_forwards_to_add:
                LOGGER.debug("Queueing new port forward for creation: %s", rule_id)
                self._entity_creation_queue.append({
                    "rule_type": "port_forwards",
                    "rule": rule
                })
                self._tracked_port_forwards.add(rule_id)
                
        for rule in self.traffic_routes:
            rule_id = get_rule_id(rule)
            if rule_id in routes_to_add:
                LOGGER.debug("Queueing new traffic route for creation: %s", rule_id)
                self._entity_creation_queue.append({
                    "rule_type": "traffic_routes",
                    "rule": rule
                })
                self._tracked_routes.add(rule_id)
                
        for rule in self.firewall_policies:
            rule_id = get_rule_id(rule)
            if rule_id in policies_to_add:
                LOGGER.debug("Queueing new firewall policy for creation: %s", rule_id)
                self._entity_creation_queue.append({
                    "rule_type": "firewall_policies",
                    "rule": rule
                })
                self._tracked_policies.add(rule_id)
                
        for rule in self.traffic_rules:
            rule_id = get_rule_id(rule)
            if rule_id in traffic_rules_to_add:
                LOGGER.debug("Queueing new traffic rule for creation: %s", rule_id)
                self._entity_creation_queue.append({
                    "rule_type": "traffic_rules",
                    "rule": rule
                })
                self._tracked_traffic_rules.add(rule_id)
                
        for rule in self.legacy_firewall_rules:
            rule_id = get_rule_id(rule)
            if rule_id in firewall_rules_to_add:
                LOGGER.debug("Queueing new firewall rule for creation: %s", rule_id)
                self._entity_creation_queue.append({
                    "rule_type": "legacy_firewall_rules",
                    "rule": rule
                })
                self._tracked_firewall_rules.add(rule_id)
                
        for rule in self.wlans:
            rule_id = get_rule_id(rule)
            if rule_id in wlans_to_add:
                LOGGER.debug("Queueing new WLAN for creation: %s", rule_id)
                self._entity_creation_queue.append({
                    "rule_type": "wlans",
                    "rule": rule
                })
                self._tracked_wlans.add(rule_id)
