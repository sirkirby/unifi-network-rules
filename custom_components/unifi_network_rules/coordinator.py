"""UniFi Network Rules Coordinator."""
from __future__ import annotations

from datetime import timedelta
import asyncio
from typing import Any, Dict, Callable, List
import time

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
from .helpers.rule import get_rule_id, get_rule_name, get_rule_enabled, get_child_unique_id
from .utils.logger import log_data, log_websocket
from .models.firewall_rule import FirewallRule
from .models.qos_rule import QoSRule

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
        
        # Sets to track what rules we have seen for deletion detection
        self._tracked_port_forwards = set()
        self._tracked_routes = set()
        self._tracked_policies = set()
        self._tracked_traffic_rules = set()
        self._tracked_firewall_rules = set()  
        self._tracked_wlans = set()
        self._tracked_qos_rules = set()
        
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
                    "legacy_firewall_rules": [],
                    "qos_rules": [],
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
                
                # Try a core API call first to detect auth issues early
                try:
                    # First get port forwards - CRITICAL to check auth early but also preserve during auth failures
                    port_forwards_success = await self._update_port_forwards_in_dict(rules_data)
                    if not port_forwards_success:
                        error_msg = getattr(self.api, "_last_error_message", "")
                        if error_msg and ("401 Unauthorized" in error_msg or "403 Forbidden" in error_msg):
                            auth_failure_during_update = True
                            LOGGER.warning("Authentication failure detected during initial fetch: %s", error_msg)
                            # Trigger auth recovery but continue trying other endpoints
                            if hasattr(self.api, "handle_auth_failure"):
                                recovery_task = asyncio.create_task(self.api.handle_auth_failure(error_msg))
                                # Don't await so we can continue with other endpoints
                                
                            # Preserve previous port forwards data if available
                            if previous_data and "port_forwards" in previous_data and previous_data["port_forwards"]:
                                LOGGER.info("Preserving previous port forwards data during authentication failure")
                                rules_data["port_forwards"] = previous_data["port_forwards"]
                except Exception as err:
                    LOGGER.error("Error in initial API call: %s", str(err))
                    # Continue with other calls
                    
                await asyncio.sleep(api_call_delay)
                
                # Then firewall policies
                await self._update_firewall_policies_in_dict(rules_data)
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
                
                # Then legacy firewall rules
                await self._update_legacy_firewall_rules_in_dict(rules_data)
                await asyncio.sleep(api_call_delay)
                
                # Then QoS rules
                await self._update_qos_rules_in_dict(rules_data)
                
                # Verify the data is valid - check if we have at least some data in key categories
                # This helps prevent entity removal during temporary API errors
                data_valid = (
                    len(rules_data["firewall_policies"]) > 0 or 
                    len(rules_data["traffic_rules"]) > 0 or
                    len(rules_data["port_forwards"]) > 0 or
                    len(rules_data["qos_rules"]) > 0 or
                    len(rules_data["traffic_routes"]) > 0 or
                    len(rules_data["legacy_firewall_rules"]) > 0
                )
                
                # Special handling for authentication failures detected during update
                if auth_failure_during_update:
                    LOGGER.warning("Authentication issues detected during update - preserving existing data")
                    # If authentication failures occurred, preserve previous data for key categories
                    for key in ["port_forwards", "firewall_policies", "traffic_rules", "traffic_routes"]:
                        if not rules_data[key] and previous_data and key in previous_data and previous_data[key]:
                            LOGGER.info(f"Preserving previous {key} data due to authentication issues")
                            rules_data[key] = previous_data[key]
                
                # Check any API responses for auth errors
                api_error_message = getattr(self.api, "_last_error_message", "")
                if api_error_message and ("401 Unauthorized" in api_error_message or "403 Forbidden" in api_error_message):
                    LOGGER.warning("Authentication error in API response: %s", api_error_message)
                    auth_failure_during_update = True
                    
                    # Notify entities about auth failure
                    async_dispatcher_send(self.hass, f"{DOMAIN}_auth_failure")
                
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
                        await self.api.refresh_session(force=True)
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
                    
                    # If we previously had auth issues but now have valid data, signal recovery
                    if auth_failure_during_update:
                        LOGGER.info("Successfully recovered from authentication issues")
                        async_dispatcher_send(self.hass, f"{DOMAIN}_auth_restored")
                    
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
                    self.qos_rules = rules_data.get("qos_rules", [])
                    
                    # Update tracking collections with current rule IDs
                    self._update_tracked_rules()
                    
                    # Log the updated rule counts
                    LOGGER.info("Rule collections after refresh: Port Forwards=%d, Traffic Routes=%d, Firewall Policies=%d, Traffic Rules=%d, Legacy Firewall Rules=%d, WLANs=%d, QoS Rules=%d", 
                               len(self.port_forwards),
                               len(self.traffic_routes),
                               len(self.firewall_policies),
                               len(self.traffic_rules),
                               len(self.legacy_firewall_rules),
                               len(self.wlans),
                               len(self.qos_rules))
                    
                return rules_data
                
            except Exception as err:
                LOGGER.error("Error updating coordinator data: %s", err)
                
                # Check if this is an authentication error
                auth_error = False
                error_str = str(err).lower()
                if "401 unauthorized" in error_str or "403 forbidden" in error_str:
                    auth_error = True
                    self._auth_failures += 1
                    self._authentication_in_progress = True
                    try:
                        LOGGER.warning("Authentication failure #%d during data update", self._auth_failures)
                        
                        # Signal auth failure to entities
                        async_dispatcher_send(self.hass, f"{DOMAIN}_auth_failure")
                        
                        # Try to refresh the session if we haven't exceeded max failures
                        if self._auth_failures < self._max_auth_failures:
                            LOGGER.info("Attempting to refresh authentication session")
                            try:
                                await self.api.refresh_session(force=True)
                                # If we succeeded in refreshing, notify components
                                async_dispatcher_send(self.hass, f"{DOMAIN}_auth_restored")
                                # Return the previous data
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
            "legacy_firewall_rules",
            "qos_rules"
        ]
        
        LOGGER.debug("Starting deletion check between previous and new data sets")
        
        for rule_type in entity_rule_types:
            if rule_type not in previous_data or rule_type not in new_data:
                LOGGER.debug("Skipping %s - not found in both datasets", rule_type)
                continue
                
            LOGGER.debug("Checking for deletions in %s: Previous count: %d, Current count: %d", 
                         rule_type, len(previous_data[rule_type]), len(new_data[rule_type]))
            
            # Process each rule type to detect and handle deletions
            self._process_deleted_rules(
                rule_type,
                self._get_deleted_rule_ids(rule_type, previous_data[rule_type], new_data[rule_type]),
                len(previous_data[rule_type])
            )

    def _get_deleted_rule_ids(self, rule_type: str, previous_rules: List[Any], current_rules: List[Any]) -> set:
        """Identify rules that have been deleted.
        
        Args:
            rule_type: The type of rule being processed
            previous_rules: List of rules from the previous update
            current_rules: List of rules from the current update
            
        Returns:
            set: Set of rule IDs that were detected as deleted
        """
        # Extract IDs from previous and current rules
        previous_ids = {get_rule_id(rule) for rule in previous_rules}
        current_ids = {get_rule_id(rule) for rule in current_rules}
        
        # Find IDs that are in previous_ids but not in current_ids
        deleted_ids = previous_ids - current_ids
        
        if deleted_ids:
            LOGGER.debug("Detected %d deleted %s rules: %s", 
                         len(deleted_ids), rule_type, deleted_ids)
        
        return deleted_ids
        
    def _update_tracked_rules(self) -> None:
        """Update the collections of tracked rules based on current data.
        
        This updates the internal tracking collections used to detect rule deletions
        between update cycles.
        """
        LOGGER.debug("Updating tracked rule collections")
        
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
        current_qos_rules = {
            get_rule_id(rule): rule for rule in getattr(self, "qos_rules", [])
        }
        
        # Update tracked rules to current state
        self._tracked_port_forwards = set(current_port_forwards.keys())
        self._tracked_routes = set(current_routes.keys())
        self._tracked_policies = set(current_policies.keys())
        self._tracked_traffic_rules = set(current_traffic_rules.keys())
        self._tracked_firewall_rules = set(current_firewall_rules.keys())
        self._tracked_wlans = set(current_wlans.keys())
        # Add QoS rules tracking
        self._tracked_qos_rules = set(current_qos_rules.keys())
        
        LOGGER.debug("Tracked rule counts: Port Forwards=%d, Traffic Routes=%d, Firewall Policies=%d, "
                     "Traffic Rules=%d, Legacy Firewall Rules=%d, WLANs=%d, QoS Rules=%d",
                     len(self._tracked_port_forwards),
                     len(self._tracked_routes),
                     len(self._tracked_policies),
                     len(self._tracked_traffic_rules),
                     len(self._tracked_firewall_rules),
                     len(self._tracked_wlans),
                     len(self._tracked_qos_rules))

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
        
        LOGGER.info("Found %d deleted %s rules: %s", len(deleted_ids), rule_type, deleted_ids)
    
        # Dispatch deletion events for each deleted rule
        for rule_id in deleted_ids:
            LOGGER.debug("Rule deletion detected - type: %s, id: %s", rule_type, rule_id)
            
            # Use _remove_entity which handles both callback and dispatching signals
            self._remove_entity(rule_id)
            
            # Update tracking collections to keep them in sync
            if rule_type == "port_forwards" and hasattr(self, "_tracked_port_forwards"):
                self._tracked_port_forwards.discard(rule_id)
            elif rule_type == "traffic_routes" and hasattr(self, "_tracked_routes"):
                self._tracked_routes.discard(rule_id)
            elif rule_type == "firewall_policies" and hasattr(self, "_tracked_policies"):
                self._tracked_policies.discard(rule_id)
            elif rule_type == "traffic_rules" and hasattr(self, "_tracked_traffic_rules"):
                self._tracked_traffic_rules.discard(rule_id)
            elif rule_type == "legacy_firewall_rules" and hasattr(self, "_tracked_firewall_rules"):
                self._tracked_firewall_rules.discard(rule_id)
            elif rule_type == "wlans" and hasattr(self, "_tracked_wlans"):
                self._tracked_wlans.discard(rule_id)
            elif rule_type == "qos_rules" and hasattr(self, "_tracked_qos_rules"):
                self._tracked_qos_rules.discard(rule_id)

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
                "qos_rules": ["qos", "quality", "service"]  # Keep QoS rule keywords
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
            elif any(word in msg_type.lower() for word in ["firewall", "rule", "policy", "route", "forward", "qos"]):  # Keep qos keyword
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
                config_keywords = ["config", "firewall", "rule", "policy", "route", "qos"]  # Keep qos keyword
                
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
                await self._schedule_entity_refresh()
        
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
                # After refreshing data, check for and process new entities
                await self.process_new_entities()
                
                # Also check for deleted rules
                if previous_data:
                    self._check_for_deleted_rules(previous_data, self.data)
                
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
            
        # In any case, dispatch the entity removed event just once
        # Entities listen for this event to handle their own removal
        LOGGER.info("Dispatching entity removal for: %s", rule_id)
        
        # Use a specific event format with the rule_id to allow targeted listening
        signal = f"{DOMAIN}_entity_removed_{rule_id}"
        LOGGER.debug("Sending targeted signal: %s", signal)
        
        try:
            # Dispatch a targeted event that only the specific entity will receive
            async_dispatcher_send(self.hass, signal, rule_id)
            
            # Also send the general event for backward compatibility
            async_dispatcher_send(self.hass, f"{DOMAIN}_entity_removed", rule_id)
            LOGGER.debug("Entity removal signal dispatched")
        except Exception as err:
            LOGGER.error("Error dispatching entity removal: %s", err)

    async def async_refresh(self) -> bool:
        """Refresh data from the UniFi API."""
        try:
            # Verify authentication by refreshing the session
            # This will reuse the existing session if valid
            if hasattr(self.api, "refresh_session"):
                LOGGER.debug("Refreshing authentication session")
                refresh_success = await self.api.refresh_session()
                if not refresh_success:
                    LOGGER.warning("Failed to refresh UniFi Network API session")
            else:
                # Fallback for older API versions
                LOGGER.warning("API missing refresh_session method, skipping authentication check")
            
            # Use a default device name
            self.device_name = "UniFi Network Controller"
            
            # Store the previous data for state comparison
            previous_data = self.data.copy() if self.data else {}
             
            # Update each rule type with specialized helper functions
            await self._update_port_forwards()
            await self._update_traffic_routes() 
            await self._update_firewall_rules()
            await self._update_traffic_rules()
            await self._update_firewall_zones()
            await self._update_wlans()
            # Add QoS rules update
            await self._update_qos_rules()
            
            # Process new entities
            await self.process_new_entities()
            
            # Process the entity creation queue if needed
            await self._process_entity_queue()
            
            # Set updated data based on the refreshed rule collections
            # This triggers entity state updates
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
            self.qos_rules = self.data.get("qos_rules", [])
            
            # Update tracking collections with current rule IDs
            self._update_tracked_rules()
            
            # Log the updated rule counts
            LOGGER.info("Rule collections after refresh: Port Forwards=%d, Traffic Routes=%d, Firewall Policies=%d, Traffic Rules=%d, Legacy Firewall Rules=%d, WLANs=%d, QoS Rules=%d", 
                       len(self.port_forwards),
                       len(self.traffic_routes),
                       len(self.firewall_policies),
                       len(self.traffic_rules),
                       len(self.legacy_firewall_rules),
                       len(self.wlans),
                       len(self.qos_rules))
            
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
        
    async def _update_qos_rules(self) -> None:
        """Update QoS rules."""
        await self._update_rule_type("qos_rules", self.api.get_qos_rules)
        self.qos_rules = self.data.get("qos_rules", [])
        
    async def _process_entity_queue(self) -> None:
        """Process any queued entity creation tasks."""
        import asyncio
        
        if not self._entity_creation_queue:
            return
        
        # Wait for platforms to be ready to ensure reliable entity creation
        platforms_ready = False
        max_platform_wait_attempts = 5
        platform_wait_attempts = 0
        
        while not platforms_ready and platform_wait_attempts < max_platform_wait_attempts:
            platform_wait_attempts += 1
            
            try:
                if DOMAIN in self.hass.data and "platforms" in self.hass.data[DOMAIN]:
                    platforms = self.hass.data[DOMAIN]["platforms"]
                    if "switch" in platforms:
                        platforms_ready = True
                        LOGGER.debug("Switch platform found - ready to process entity queue")
                        break
                    else:
                        LOGGER.debug("Switch platform not ready (attempt %d/%d)", 
                                   platform_wait_attempts, max_platform_wait_attempts)
                else:
                    LOGGER.debug("Platform data structure not initialized (attempt %d/%d)",
                               platform_wait_attempts, max_platform_wait_attempts)
            except Exception as err:
                LOGGER.error("Error checking platform readiness: %s", err)
            
            # Wait before next attempt
            await asyncio.sleep(1)
        
        if not platforms_ready:
            LOGGER.warning("Platform not ready after %d attempts - deferring entity creation", 
                         max_platform_wait_attempts)
            # Schedule a retry
            self.hass.async_create_task(self._schedule_queue_reprocessing())
            return
        
        # Use a semaphore to prevent concurrent entity creation
        if not hasattr(self, '_entity_queue_semaphore'):
            self._entity_queue_semaphore = asyncio.Semaphore(1)
        
        # Only proceed if we can acquire the semaphore
        if self._entity_queue_semaphore.locked():
            LOGGER.debug("Skipping entity queue processing as one is already in progress")
            return
        
        async with self._entity_queue_semaphore:
            # Process the queue with rate limiting to prevent overwhelming HA
            from homeassistant.helpers.entity_registry import async_get as get_entity_registry
            entity_registry = get_entity_registry(self.hass)
            
            # Create a copy of the queue to process
            queue_to_process = self._entity_creation_queue.copy()
            self._entity_creation_queue = []
            
            # Track successfully created entities
            created_entities = []
            
            # Process each item in the queue
            for item in queue_to_process:
                try:
                    # Expect only dictionary format items
                    if not isinstance(item, dict) or "rule_type" not in item or "rule" not in item:
                        LOGGER.error("Invalid queue item format: %s", item)
                        continue
                    
                    rule_type = item["rule_type"]
                    rule = item["rule"]
                    
                    # Skip if rule or rule_type is invalid
                    if not rule or not rule_type:
                        LOGGER.warning("Skipping invalid queue item: %s", item)
                        continue
                        
                    # Get rule ID for tracking
                    rule_id = get_rule_id(rule)
                    
                    if not rule_id:
                        LOGGER.warning("Cannot create entity for rule without ID")
                        continue
                    
                    # Check if entity already exists in registry
                    existing_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, rule_id)
                    if existing_entity_id:
                        LOGGER.debug("Entity already exists in registry: %s", existing_entity_id)
                        continue
                    
                    # Import the entity creation function
                    from . import async_create_entity
                    
                    # Create the entity
                    success = await async_create_entity(self.hass, rule_type, rule)
                    
                    if success:
                        created_entities.append((rule_type, rule_id))
                    else:
                        # Re-queue for later if creation failed
                        self._entity_creation_queue.append({
                            "rule_type": rule_type,
                            "rule": rule
                        })
                    
                    # Rate limit entity creation to prevent overwhelming HA
                    await asyncio.sleep(0.5)
                    
                except Exception as err:
                    LOGGER.error("Error creating entity for queue item: %s", err)
                    # Don't re-queue - it might be causing the errors
            
            # Log summary of created entities
            if created_entities:
                LOGGER.info("Created %d entities in this batch", len(created_entities))
            
            # If there are still items in the queue, schedule another processing
            if self._entity_creation_queue:
                LOGGER.debug("%d entities remaining in queue - scheduling another processing",
                           len(self._entity_creation_queue))
                self.hass.async_create_task(self._schedule_queue_reprocessing())

    async def _schedule_entity_refresh(self) -> None:
        """Schedule a delayed refresh of all entities to ensure they appear in the UI."""
        # Wait a short time to allow Home Assistant to process the entity creation
        await asyncio.sleep(1)
        
        try:
            # Update data to refresh entity states
            await self.async_request_refresh()
            
            # Option 1: Use dispatcher to notify entities to update
            async_dispatcher_send(self.hass, f"{DOMAIN}_update")
            
            # Option 2: Try to update the component directly if available
            try:
                from homeassistant.helpers.entity_component import EntityComponent
                component = self.hass.data.get("switch")
                if isinstance(component, EntityComponent) and hasattr(component, "async_update_entity_states"):
                    # This is a low-level method that forces all entities in the component to update
                    LOGGER.debug("Forcing component entity states update")
                    await component.async_update_entity_states()
            except Exception as component_err:
                LOGGER.debug("Error updating component entity states: %s", component_err)
        except Exception as err:
            LOGGER.error("Error in entity refresh: %s", err)

    async def process_new_entities(self) -> None:
        """Check for new entities in all rule types and queue them for creation."""
        LOGGER.debug("Starting process_new_entities check")
        
        # Create sets of currently tracked rule IDs for comparison
        port_forwards_to_add = {
            get_rule_id(rule) for rule in self.port_forwards
            if get_rule_id(rule) not in self._tracked_port_forwards and get_rule_id(rule) is not None
        }
        
        routes_to_add = {
            get_rule_id(rule) for rule in self.traffic_routes 
            if get_rule_id(rule) not in self._tracked_routes and get_rule_id(rule) is not None
        }
        
        policies_to_add = {
            get_rule_id(rule) for rule in self.firewall_policies 
            if get_rule_id(rule) not in self._tracked_policies and get_rule_id(rule) is not None
        }
        
        traffic_rules_to_add = {
            get_rule_id(rule) for rule in self.traffic_rules 
            if get_rule_id(rule) not in self._tracked_traffic_rules and get_rule_id(rule) is not None
        }
        
        firewall_rules_to_add = {
            get_rule_id(rule) for rule in self.legacy_firewall_rules 
            if get_rule_id(rule) not in self._tracked_firewall_rules and get_rule_id(rule) is not None
        }
        
        wlans_to_add = {
            get_rule_id(rule) for rule in self.wlans 
            if get_rule_id(rule) not in self._tracked_wlans and get_rule_id(rule) is not None
        }
        
        # Add set for QoS rules
        qos_rules_to_add = {
            get_rule_id(rule) for rule in self.qos_rules
            if get_rule_id(rule) not in self._tracked_qos_rules and get_rule_id(rule) is not None
        }
        
        # Log counts of new rules detected
        if (port_forwards_to_add or routes_to_add or policies_to_add or 
            traffic_rules_to_add or firewall_rules_to_add or wlans_to_add or qos_rules_to_add):
            LOGGER.debug(
                "Detected new rules - Port Forwards: %d, Traffic Routes: %d, "
                "Firewall Policies: %d, Traffic Rules: %d, Legacy Firewall Rules: %d, WLANs: %d, QoS Rules: %d",
                len(port_forwards_to_add), len(routes_to_add), len(policies_to_add),
                len(traffic_rules_to_add), len(firewall_rules_to_add), len(wlans_to_add),
                len(qos_rules_to_add)
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
                    self._tracked_port_forwards.add(rule_id)
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
                    self._tracked_routes.add(rule_id)
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
                    self._tracked_policies.add(rule_id)
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
                    self._tracked_traffic_rules.add(rule_id)
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
                    self._tracked_firewall_rules.add(rule_id)
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
                    self._tracked_wlans.add(rule_id)
                else:
                    LOGGER.error("Cannot queue WLAN rule without id attribute")
                    
        # Add section for QoS rules
        for rule in self.qos_rules:
            rule_id = get_rule_id(rule)
            LOGGER.debug("Processing QoS rule with ID: %s, tracked: %s, in add set: %s", 
                       rule_id, 
                       rule_id in self._tracked_qos_rules,
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
                    self._tracked_qos_rules.add(rule_id)
                else:
                    LOGGER.error("Cannot queue QoS rule without id attribute")

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
