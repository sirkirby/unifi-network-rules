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

from .const import DOMAIN, LOGGER, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DEBUG_WEBSOCKET
from .udm_api import UDMAPI
from .websocket import SIGNAL_WEBSOCKET_MESSAGE, UnifiRuleWebsocket
from .helpers.rule import get_rule_id
from .utils.logger import log_data, log_websocket

# This is a fallback if no update_interval is specified
SCAN_INTERVAL = timedelta(seconds=60)

def _log_rule_info(rule: Any) -> None:
    """Log detailed information about a rule object."""
    try:
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

    async def _async_update_data(self) -> Dict[str, List[Any]]:
        """Fetch data from API endpoint."""
        try:
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
            
            # Store the previous data to detect deletions
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
            
            # First get firewall policies
            await self._update_firewall_policies(rules_data)
            await asyncio.sleep(api_call_delay)
            
            # Then port forwards
            await self._update_port_forwards(rules_data)
            await asyncio.sleep(api_call_delay)
            
            # Then traffic routes
            await self._update_traffic_routes(rules_data)
            await asyncio.sleep(api_call_delay)
            
            # Then firewall zones
            await self._update_firewall_zones(rules_data)
            await asyncio.sleep(api_call_delay)
            
            # Then WLANs
            await self._update_wlans(rules_data)
            await asyncio.sleep(api_call_delay)
            
            # Then traffic rules
            await self._update_traffic_rules(rules_data)
            await asyncio.sleep(api_call_delay)
            
            # Finally legacy firewall rules
            await self._update_legacy_firewall_rules(rules_data)
            
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
                    
                # Try forcing a session refresh on error
                LOGGER.info("Forcing session refresh due to API data issue")
                try:
                    await self.api.refresh_session()
                except Exception as session_err:
                    LOGGER.error("Failed to refresh session during error recovery: %s", session_err)
                
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
                
                # Check for deleted rules and dispatch events for each
                if previous_data:
                    LOGGER.debug("Checking for deleted rules in latest update")
                    self._check_for_deleted_rules(previous_data, rules_data)
                
            return rules_data
            
        except Exception as err:
            LOGGER.error("Error updating coordinator data: %s", err)
            
            # Check if this is an authentication error
            if "401 Unauthorized" in str(err) or "403 Forbidden" in str(err):
                self._auth_failures += 1
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

    def _detect_deleted_rules(
        self, rule_type: str, previous_rules: List[Any], new_rules: List[Any]
    ) -> set:
        """Detect rules that have been deleted between updates.
        
        Args:
            rule_type: The type of rule being processed
            previous_rules: The list of rules from the previous update
            new_rules: The list of rules from the current update
            
        Returns:
            Set of rule IDs that were detected as deleted
        """
        # If we have fewer items now than before, something was probably deleted
        if len(previous_rules) > len(new_rules):
            # But only warn if the difference is significant - avoid entity churn on minor changes
            if len(previous_rules) - len(new_rules) > len(previous_rules) * 0.5:
                # If we lost more than 50% of entities, this might be a temporary API issue
                LOGGER.warning(
                    "More than 50%% of %s rules disappeared (%d -> %d). This may be a temporary API issue - skipping entity removal",
                    rule_type,
                    len(previous_rules),
                    len(new_rules)
                )
                # Skip this rule type to avoid entity churn during API issues
                return set()
            else:
                LOGGER.warning("Count decreased for %s: %d -> %d (-%d items)", 
                            rule_type, 
                            len(previous_rules), 
                            len(new_rules), 
                            len(previous_rules) - len(new_rules))
        
        # Extract raw ID helper function
        def extract_raw_id(rule_id):
            """Extract the raw ID part without the prefix."""
            if rule_id and "_" in rule_id:
                parts = rule_id.split("_")
                # Return the last part which should be the actual ID
                return parts[-1]
            return rule_id
            
        # Create maps of rules by ID for efficient comparison
        prev_rules = {get_rule_id(rule): rule for rule in previous_rules if get_rule_id(rule)}
        new_rules = {get_rule_id(rule): rule for rule in new_rules if get_rule_id(rule)}
        
        # Create sets for more efficient comparison
        prev_ids = set(prev_rules.keys())
        new_ids = set(new_rules.keys())
        
        # Add debug logs to show what IDs we're comparing
        LOGGER.debug("Checking for deleted %s rules - Previous IDs: %s", rule_type, sorted(list(prev_ids)))
        LOGGER.debug("Checking for deleted %s rules - Current IDs: %s", rule_type, sorted(list(new_ids)))
        
        # Find IDs that existed before but not now (deleted rules)
        deleted_ids = prev_ids - new_ids
        
        # Also try comparing raw IDs without prefixes if we didn't find any deletions
        if not deleted_ids and len(previous_rules) != len(new_rules):
            prev_raw_ids = {extract_raw_id(get_rule_id(rule)) for rule in previous_rules if get_rule_id(rule)}
            new_raw_ids = {extract_raw_id(get_rule_id(rule)) for rule in new_rules if get_rule_id(rule)}
            raw_deleted_ids = prev_raw_ids - new_raw_ids
            
            if raw_deleted_ids:
                LOGGER.info("Found %d deleted rules using raw ID comparison: %s", 
                            len(raw_deleted_ids), raw_deleted_ids)
                
                # Convert raw IDs back to entity IDs for removal
                for raw_id in raw_deleted_ids:
                    for rule in previous_rules:
                        rule_id = get_rule_id(rule)
                        if rule_id and extract_raw_id(rule_id) == raw_id:
                            deleted_ids.add(rule_id)
                            LOGGER.info("Adding rule for removal - raw_id: %s -> entity_id: %s", 
                                        raw_id, rule_id)
        
        # Double-check if counts don't match but no deletions found
        # This could indicate an issue with ID matching or API caching
        if len(previous_rules) != len(new_rules) and not deleted_ids:
            LOGGER.warning(
                "Rule count mismatch detected! Previous: %d, Current: %d, but no deleted IDs found. "
                "This might indicate a caching issue or ID format mismatch.",
                len(previous_rules), 
                len(new_rules)
            )
            # If we have fewer rules now but no deletions detected, force entity removal based on raw data
            if len(previous_rules) > len(new_rules):
                LOGGER.warning("Rule count decreased but no deletions detected - comparing rule contents")
                
                # Create a deep comparison of rule contents
                for prev_rule in previous_rules:
                    prev_id = get_rule_id(prev_rule)
                    if not prev_id:
                        continue
                        
                    # Check if this rule still exists in any form
                    found = False
                    for new_rule in new_rules:
                        # Try to match on any attribute that might be stable
                        if hasattr(prev_rule, 'id') and hasattr(new_rule, 'id') and prev_rule.id == new_rule.id:
                            found = True
                            break
                        elif hasattr(prev_rule, 'name') and hasattr(new_rule, 'name') and prev_rule.name == new_rule.name:
                            found = True
                            break
                            
                    if not found:
                        # This rule doesn't seem to exist in the new data
                        LOGGER.info("Rule %s appears to be missing in new data", prev_id)
                        deleted_ids.add(prev_id)
                        
        return deleted_ids
            
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

    async def _update_firewall_policies(self, data: Dict[str, List[Any]]) -> None:
        """Update firewall policies."""
        await self._update_rule_type(
            data, 
            "firewall_policies", 
            self.api.get_firewall_policies, 
            force_refresh=True,
            log_details=True
        )
            
    async def _update_traffic_rules(self, data: Dict[str, List[Any]]) -> None:
        """Update traffic rules."""
        await self._update_rule_type(data, "traffic_rules", self.api.get_traffic_rules)

    async def _update_port_forwards(self, data: Dict[str, List[Any]]) -> None:
        """Update port forwards."""
        await self._update_rule_type(data, "port_forwards", self.api.get_port_forwards)

    async def _update_traffic_routes(self, data: Dict[str, List[Any]]) -> None:
        """Update traffic routes."""
        await self._update_rule_type(data, "traffic_routes", self.api.get_traffic_routes)

    async def _update_firewall_zones(self, data: Dict[str, List[Any]]) -> None:
        """Update firewall zones."""
        await self._update_rule_type(data, "firewall_zones", self.api.get_firewall_zones)

    async def _update_wlans(self, data: Dict[str, List[Any]]) -> None:
        """Update WLANs."""
        await self._update_rule_type(data, "wlans", self.api.get_wlans)

    async def _update_legacy_firewall_rules(self, data: Dict[str, List[Any]]) -> None:
        """Update legacy firewall rules."""
        await self._update_rule_type(
            data, 
            "legacy_firewall_rules", 
            self.api.get_legacy_firewall_rules,
            log_details=True
        )

    async def _update_rule_type(
        self, 
        data: Dict[str, List[Any]], 
        rule_type: str, 
        fetch_method: Callable, 
        force_refresh: bool = False,
        log_details: bool = False
    ) -> None:
        """Generic method to update a rule type.
        
        Args:
            data: Data dictionary to update
            rule_type: Type of rule being updated
            fetch_method: API method to call to fetch the rules
            force_refresh: Whether to force a refresh in the API call
            log_details: Whether to log detailed rule information
        """
        try:
            if force_refresh:
                LOGGER.debug(f"Fetching {rule_type} from API with force_refresh=True")
                rules = await fetch_method(force_refresh=True)
            else:
                rules = await fetch_method()
            
            rules_list = list(rules)
            
            if log_details:
                # Log detailed rule information for debugging
                rule_ids = [get_rule_id(rule) for rule in rules_list]
                LOGGER.debug(f"Received {len(rules_list)} {rule_type} from API: {rule_ids}")
                
                # Additional check: log any rules that might be marked as deleted but still returned
                for rule in rules_list:
                    if hasattr(rule, "deleted") and getattr(rule, "deleted", False):
                        LOGGER.warning(f"API returned a deleted {rule_type}: {get_rule_id(rule)}")
            else:
                LOGGER.debug(f"Fetched {len(rules_list)} {rule_type}")
                
            data[rule_type] = rules_list
        except Exception as err:
            LOGGER.error(f"Error fetching {rule_type}: {err}")
            data[rule_type] = []

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
