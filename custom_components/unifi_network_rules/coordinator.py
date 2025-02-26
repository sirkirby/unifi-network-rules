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
                    await self.api.refresh_session()
                    self._last_session_refresh = current_time
                except Exception as refresh_err:
                    LOGGER.warning("Failed to refresh session: %s", str(refresh_err))
            
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
            
            # Clear any caches before fetching to ensure we get fresh data
            await self.api.clear_cache()
            
            # Log the start of the update process
            LOGGER.debug("Beginning rule data collection with fresh cache")
            
            # Periodically force a cleanup of stale entities (once per hour)
            force_cleanup_interval = 3600  # seconds
            last_cleanup = getattr(self, "_last_entity_cleanup", 0)
            if current_time - last_cleanup > force_cleanup_interval:
                LOGGER.info("Performing periodic forced entity cleanup")
                self._last_entity_cleanup = current_time
                
                # Dispatch a special force-cleanup signal
                try:
                    async_dispatcher_send(
                        self.hass,
                        f"{DOMAIN}_force_entity_cleanup",
                        None
                    )
                except Exception as cleanup_err:
                    LOGGER.error("Error dispatching forced cleanup: %s", cleanup_err)
            
            # Gather all rule types SEQUENTIALLY instead of in parallel
            # This avoids overwhelming the API with parallel requests
            
            # Define delay between API calls to prevent rate limiting
            api_call_delay = 1.0  # seconds between API calls - reduced slightly
            
            # Firewall policies first - most important
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
                
            # Check for deleted rules and dispatch events for each
            if previous_data:
                LOGGER.debug("Checking for deleted rules in latest update")
                self._check_for_deleted_rules(previous_data, rules_data)
                
            return rules_data
            
        except Exception as err:
            LOGGER.error("Error updating coordinator data: %s", err)
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
                
            # If we have fewer items now than before, something was probably deleted
            if len(previous_data[rule_type]) > len(new_data[rule_type]):
                LOGGER.warning("Count decreased for %s: %d -> %d (-%d items)", 
                               rule_type, 
                               len(previous_data[rule_type]), 
                               len(new_data[rule_type]), 
                               len(previous_data[rule_type]) - len(new_data[rule_type]))
            
            # Get the raw rule IDs without prefixes to compare data accurately
            # This extracts only the ID portion from each rule for comparison
            def extract_raw_id(rule_id):
                """Extract the raw ID part without the prefix."""
                if rule_id and "_" in rule_id:
                    parts = rule_id.split("_")
                    # Return the last part which should be the actual ID
                    return parts[-1]
                return rule_id
                
            # Create maps of rules by ID for efficient comparison
            prev_rules = {get_rule_id(rule): rule for rule in previous_data[rule_type] if get_rule_id(rule)}
            new_rules = {get_rule_id(rule): rule for rule in new_data[rule_type] if get_rule_id(rule)}
            
            # Create sets for more efficient comparison
            prev_ids = set(prev_rules.keys())
            new_ids = set(new_rules.keys())
            
            # Add debug logs to show what IDs we're comparing
            LOGGER.debug("Checking for deleted %s rules - Previous IDs: %s", rule_type, sorted(list(prev_ids)))
            LOGGER.debug("Checking for deleted %s rules - Current IDs: %s", rule_type, sorted(list(new_ids)))
            
            # Find IDs that existed before but not now (deleted rules)
            deleted_ids = prev_ids - new_ids
            
            # Also try comparing raw IDs without prefixes
            prev_raw_ids = {extract_raw_id(get_rule_id(rule)) for rule in previous_data[rule_type] if get_rule_id(rule)}
            new_raw_ids = {extract_raw_id(get_rule_id(rule)) for rule in new_data[rule_type] if get_rule_id(rule)}
            raw_deleted_ids = prev_raw_ids - new_raw_ids
            
            if raw_deleted_ids and not deleted_ids:
                LOGGER.info("Found %d deleted rules using raw ID comparison: %s", 
                            len(raw_deleted_ids), raw_deleted_ids)
                
                # Convert raw IDs back to entity IDs for removal
                for raw_id in raw_deleted_ids:
                    for rule in previous_data[rule_type]:
                        rule_id = get_rule_id(rule)
                        if rule_id and extract_raw_id(rule_id) == raw_id:
                            deleted_ids.add(rule_id)
                            LOGGER.info("Adding rule for removal - raw_id: %s -> entity_id: %s", 
                                        raw_id, rule_id)
            
            # Double-check if counts don't match but no deletions found
            # This could indicate an issue with ID matching or API caching
            if len(previous_data[rule_type]) != len(new_data[rule_type]) and not deleted_ids:
                LOGGER.warning(
                    "Rule count mismatch detected! Previous: %d, Current: %d, but no deleted IDs found. "
                    "This might indicate a caching issue or ID format mismatch.",
                    len(previous_data[rule_type]), 
                    len(new_data[rule_type])
                )
                # If we have fewer rules now but no deletions detected, force entity removal based on raw data
                if len(previous_data[rule_type]) > len(new_data[rule_type]):
                    LOGGER.warning("Rule count decreased but no deletions detected - comparing rule contents")
                    
                    # Create a deep comparison of rule contents
                    for prev_rule in previous_data[rule_type]:
                        prev_id = get_rule_id(prev_rule)
                        if not prev_id:
                            continue
                            
                        # Check if this rule still exists in any form
                        found = False
                        for new_rule in new_data[rule_type]:
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
            
            if deleted_ids:
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
        try:
            LOGGER.debug("Fetching firewall policies from API with force_refresh=True")
            # Force a fresh fetch from the API to bypass any caching
            policies = await self.api.get_firewall_policies(force_refresh=True)
            
            # Log detailed policy information for debugging
            policy_ids = [get_rule_id(policy) for policy in policies]
            LOGGER.debug("Received %d firewall policies from API: %s", len(policies), policy_ids)
            
            # Additional check: log any policies that might be marked as deleted but still returned
            for policy in policies:
                if hasattr(policy, "deleted") and getattr(policy, "deleted", False):
                    LOGGER.warning("API returned a deleted policy: %s", get_rule_id(policy))
                    
            data["firewall_policies"] = list(policies)
        except Exception as err:
            LOGGER.error("Error fetching firewall policies: %s", err)
            data["firewall_policies"] = []
            
    async def _update_traffic_rules(self, data: Dict[str, List[Any]]) -> None:
        """Update traffic rules."""
        try:
            rules = await self.api.get_traffic_rules()
            data["traffic_rules"] = list(rules)
        except Exception as err:
            LOGGER.error("Error fetching traffic rules: %s", err)
            data["traffic_rules"] = []

    async def _update_port_forwards(self, data: Dict[str, List[Any]]) -> None:
        """Update port forwards."""
        try:
            forwards = await self.api.get_port_forwards()
            data["port_forwards"] = list(forwards)
        except Exception as err:
            LOGGER.error("Error fetching port forwards: %s", err)
            data["port_forwards"] = []

    async def _update_traffic_routes(self, data: Dict[str, List[Any]]) -> None:
        """Update traffic routes."""
        try:
            routes = await self.api.get_traffic_routes()
            data["traffic_routes"] = list(routes)
        except Exception as err:
            LOGGER.error("Error fetching traffic routes: %s", err)
            data["traffic_routes"] = []

    async def _update_firewall_zones(self, data: Dict[str, List[Any]]) -> None:
        """Update firewall zones."""
        try:
            zones = await self.api.get_firewall_zones()
            data["firewall_zones"] = list(zones)
        except Exception as err:
            LOGGER.error("Error fetching firewall zones: %s", err)
            data["firewall_zones"] = []

    async def _update_wlans(self, data: Dict[str, List[Any]]) -> None:
        """Update WLANs."""
        try:
            wlans = await self.api.get_wlans()
            data["wlans"] = list(wlans)
        except Exception as err:
            LOGGER.error("Error fetching WLANs: %s", err)
            data["wlans"] = []

    async def _update_legacy_firewall_rules(self, data: Dict[str, List[Any]]) -> None:
        """Update legacy firewall rules."""
        try:
            rules = await self.api.get_legacy_firewall_rules()
            data["legacy_firewall_rules"] = list(rules)
            LOGGER.debug("Fetched %d legacy firewall rules", len(rules))
        except Exception as err:
            LOGGER.error("Error fetching legacy firewall rules: %s", err)
            data["legacy_firewall_rules"] = []

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
