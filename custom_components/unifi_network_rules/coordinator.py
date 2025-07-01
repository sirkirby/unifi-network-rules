"""UniFi Network Rules Coordinator."""
from __future__ import annotations

from datetime import timedelta
import asyncio
from typing import Any, Dict, Callable, List, Optional, Set
import time

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward
from aiounifi.models.firewall_zone import FirewallZone
from aiounifi.models.wlan import Wlan
from aiounifi.models.device import Device

from .const import DOMAIN, LOGGER, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DEBUG_WEBSOCKET
from .udm import UDMAPI
from .websocket import SIGNAL_WEBSOCKET_MESSAGE, UnifiRuleWebsocket
from .helpers.rule import get_rule_id, get_rule_name, get_rule_enabled, get_child_unique_id
from .utils.logger import log_data, log_websocket
from .models.firewall_rule import FirewallRule
from .models.qos_rule import QoSRule
from .models.vpn_config import VPNConfig

# This is a fallback if no update_interval is specified
SCAN_INTERVAL = timedelta(seconds=60)

class NeedsFetch(Exception):
    """Raised when a rule needs to be fetched again after a discovery."""

class UnifiRuleUpdateCoordinator(DataUpdateCoordinator):
    """UniFi Network Rules API Coordinator."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        api: UDMAPI, 
        websocket: UnifiRuleWebsocket,
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
        platforms: Optional[List[Platform]] = None,
    ) -> None:
        """Initialize the coordinator with API and update interval."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

        # Keep a reference to the API and websocket
        self.api = api
        self.websocket = websocket
        
        # Initialize config_entry to None - it will be looked up when needed
        self.config_entry = None
        
        # Update lock - prevent simultaneous updates
        self._update_lock = asyncio.Lock()

        # Authentication state
        self._authentication_in_progress = False
        self._auth_failures = 0  
        self._max_auth_failures = 5  # After this many failures, we'll stop trying to reconnect

        # Error tracking
        self._in_error_state = False
        self._consecutive_errors = 0
        self._api_errors = 0
        self._last_successful_data = {}

        # Track initial update
        self._initial_update_done = False

        # Flag to track update in progress
        self._update_in_progress = False
        self._has_data = False
        
        # --- CQRS-style Operation Tracking ---
        # This tracks rule_ids for operations initiated within Home Assistant
        # to prevent the trigger from causing a redundant refresh and to prevent a potential race condition
        self._ha_initiated_operations: Dict[str, float] = {}
        
        # Websocket processing is now handled by trigger system
        
        # Track entities we added or removed
        # By unique ID rather than the objects themselves
        self.known_unique_ids: Set[str] = set()
        self.removed_unique_ids: Set[str] = set()
        self._entity_creation_queue = []
        
        # Rule collections - these are maintained by the coordinator
        # To be used by services for operations like enable/disable rules
        self.port_forwards: List[PortForward] = []
        self.traffic_routes: List[TrafficRoute] = []
        self.firewall_policies: List[FirewallPolicy] = []
        self.traffic_rules: List[TrafficRule] = []
        self.legacy_firewall_rules: List[FirewallRule] = []
        self.firewall_zones: List[FirewallZone] = []
        self.wlans: List[Wlan] = []
        self.qos_rules: List[QoSRule] = []
        self.vpn_clients: List[VPNConfig] = []
        self.vpn_servers: List[VPNConfig] = []
        self.devices: List[Device] = []  # For LED toggle switches

        # For dynamic entity creation
        self.async_add_entities_callback: AddEntitiesCallback | None = None
        self.entity_platform = None  # Store the entity platform for later use

        # Save platforms to load
        self._platforms = platforms or [Platform.SWITCH]

        # Webhook tracking
        self.webhook_id = None
        self.webhook_url = None
        self.webhook_registered = False

        # Error tracking
        self._in_error_state = False
        self._consecutive_errors = 0
        self._api_errors = 0

    def register_ha_initiated_operation(self, rule_id: str, timeout: int = 15) -> None:
        """Register that a rule change was initiated from HA.
        
        This is called by a switch entity just before it queues an API call.
        The trigger system will check this to avoid a redundant refresh.
        
        Args:
            rule_id: The ID of the rule being changed.
            timeout: How long (in seconds) to keep the registration active.
        """
        self._ha_initiated_operations[rule_id] = time.time()
        LOGGER.debug("[CQRS] Registered HA-initiated operation for rule_id: %s", rule_id)
        
        # Schedule cleanup to prevent the dictionary from growing indefinitely
        # if a corresponding websocket event never arrives.
        async def cleanup_op(op_rule_id):
            await asyncio.sleep(timeout)
            if op_rule_id in self._ha_initiated_operations:
                del self._ha_initiated_operations[op_rule_id]
                LOGGER.debug("[CQRS] Expired and removed HA-initiated operation for rule_id: %s", op_rule_id)

        self.hass.async_create_task(cleanup_op(rule_id))
        
    def check_and_consume_ha_initiated_operation(self, rule_id: str) -> bool:
        """Check if a rule change was HA-initiated and consume the flag.
        
        This is called by the trigger system before it decides to fire a
        refresh, to see if the change was expected.
        
        Args:
            rule_id: The ID of the rule that changed.
            
        Returns:
            True if the operation was initiated from HA, False otherwise.
        """
        if rule_id in self._ha_initiated_operations:
            LOGGER.debug("[CQRS] Consumed HA-initiated operation for rule_id: %s. Suppressing trigger refresh.", rule_id)
            del self._ha_initiated_operations[rule_id]
            return True
        return False

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
                    "vpn_clients": [],
                    "vpn_servers": [],
                    "devices": [],
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

                LOGGER.debug("Beginning rule data collection with fresh cache")

                # Periodically force a cleanup of stale entities (once per hour)
                force_cleanup_interval = 3600  # seconds
                last_cleanup = getattr(self, "_last_entity_cleanup", 0)
                if current_time - last_cleanup > force_cleanup_interval:
                    setattr(self, "_force_cleanup", True)
                    setattr(self, "_last_entity_cleanup", current_time)

                # Add delay between API calls to avoid rate limiting
                api_call_delay = 1.0  # seconds

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

                            # Preserve previous port forwards data if available
                            if previous_data and "port_forwards" in previous_data and previous_data["port_forwards"]:
                                LOGGER.info("Preserving previous port forwards data during authentication failure")
                                rules_data["port_forwards"] = previous_data["port_forwards"]
                except Exception as err:
                    LOGGER.error("Error in initial API call: %s", str(err))

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
                await asyncio.sleep(api_call_delay)
                
                # Then VPN clients
                await self._update_vpn_clients_in_dict(rules_data)
                await asyncio.sleep(api_call_delay)
                
                # Then VPN servers
                await self._update_vpn_servers_in_dict(rules_data)
                await asyncio.sleep(api_call_delay)
                
                # Then devices (for LED switches)
                await self._update_devices_in_dict(rules_data)

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

                    # Mark initial update as done AFTER first successful processing and BEFORE checks
                    if not self._initial_update_done:
                        self._initial_update_done = True

                    # Perform checks only AFTER the initial update is marked done
                    if self._initial_update_done:
                        # --- Check for DELETED Entities ---
                        self._check_for_deleted_rules(rules_data)

                        # --- Discover and Add NEW Entities --- 
                        await self._discover_and_add_new_entities(rules_data)

                    # --- Update Internal Collections --- 
                    self.port_forwards = rules_data.get("port_forwards", [])
                    self.traffic_routes = rules_data.get("traffic_routes", [])
                    self.firewall_policies = rules_data.get("firewall_policies", [])
                    self.traffic_rules = rules_data.get("traffic_rules", [])
                    self.legacy_firewall_rules = rules_data.get("legacy_firewall_rules", [])
                    self.wlans = rules_data.get("wlans", [])
                    self.firewall_zones = rules_data.get("firewall_zones", [])
                    self.qos_rules = rules_data.get("qos_rules", [])
                    self.vpn_clients = rules_data.get("vpn_clients", [])
                    self.vpn_servers = rules_data.get("vpn_servers", [])
                    self.devices = rules_data.get("devices", [])

                    LOGGER.info("Rule collections after refresh: Port Forwards=%d, Traffic Routes=%d, Firewall Policies=%d, Traffic Rules=%d, Legacy Firewall Rules=%d, WLANs=%d, QoS Rules=%d, VPN Clients=%d, VPN Servers=%d, Devices=%d", 
                               len(self.port_forwards),
                               len(self.traffic_routes),
                               len(self.firewall_policies),
                               len(self.traffic_rules),
                               len(self.legacy_firewall_rules),
                               len(self.wlans),
                               len(self.qos_rules),
                               len(self.vpn_clients),
                               len(self.vpn_servers),
                               len(self.devices))

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
            "vpn_servers",
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

        # Special handling for device LED switches in deletion check
        devices = new_data.get("devices", [])
        for device in devices:
            try:
                device_unique_id = f"unr_device_{device.mac}_led"
                all_current_unique_ids.add(device_unique_id)
            except Exception as e:
                LOGGER.warning("Error getting device ID during deletion check: %s", e)

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

    async def _update_vpn_servers_in_dict(self, data: Dict[str, List[Any]]) -> None:
        """Update VPN servers in the given data dictionary."""
        await self._update_rule_type_in_dict(data, "vpn_servers", self.api.get_vpn_servers)
        
    async def _update_devices_in_dict(self, data: Dict[str, List[Any]]) -> None:
        """Update devices in the data dictionary."""
        try:
            LOGGER.info("Fetching devices for LED switches...")
            
            # Get LED states from the stat/device endpoint (has comprehensive device data including LED states)
            led_states = await self.api.get_device_led_states()
            LOGGER.info("Retrieved LED states for %d devices from stat/device", len(led_states))
            
            # Debug: Print LED states found
            if led_states:
                LOGGER.info("LED-capable devices found:")
                for mac, led_info in led_states.items():
                    LOGGER.info("  %s (%s): LED=%s, Model=%s", 
                              led_info['name'], mac, led_info.get('led_override', 'unknown'), led_info['model'])
            
            # Create Device objects directly from the comprehensive LED states data
            # This avoids the issue where v2 /device endpoint may not return all devices
            led_capable_devices = []
            for mac, led_info in led_states.items():
                try:
                    # Create a device data structure from the LED info
                    device_data = {
                        'mac': mac,
                        '_id': led_info.get('_id', mac),  # Use _id if available, fallback to mac
                        'device_id': led_info.get('_id', mac),   # Device ID field expected by Device class
                        'name': led_info['name'],
                        'model': led_info['model'],
                        'type': led_info['type'],
                        'is_access_point': led_info['is_access_point'],
                        'led_override': led_info.get('led_override'),
                        'led_override_color': led_info.get('led_override_color'),
                        'led_override_color_brightness': led_info.get('led_override_color_brightness'),
                        'state': led_info.get('state', 1),  # Device connection state
                    }
                    
                    # Create Device object from this data
                    device = Device(device_data)
                    led_capable_devices.append(device)
                    LOGGER.info("Created LED-capable device: %s (%s) - LED state: %s", 
                              led_info['name'], mac, led_info.get('led_override', 'unknown'))
                    
                except Exception as device_err:
                    LOGGER.warning("Error creating device object for %s (%s): %s", 
                                 led_info.get('name', 'unknown'), mac, str(device_err))
                    continue
            
            data["devices"] = led_capable_devices
            self.devices = led_capable_devices
            LOGGER.info("Updated %d LED-capable devices with current LED states", len(led_capable_devices))
            
        except Exception as err:
            LOGGER.error("Failed to update devices: %s", str(err))
            LOGGER.exception("Device update exception details:")
            data["devices"] = []
            if not hasattr(self, 'devices'):
                self.devices = []

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
        """Handle a message from the WebSocket connection.
        
        NOTE: This method is now primarily handled by the trigger system.
        Triggers detect config changes and dispatch refreshes directly via _dispatch_coordinator_refresh().
        This keeps the detection logic DRY and centralized in one place.
        """
        # The trigger system now handles all websocket message detection and dispatches
        # coordinator refreshes when config changes are detected. This method is kept
        # for backward compatibility but should only be called as a fallback.
        pass

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
        """Process and create entities that were discovered."""
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
        
        # Add set for VPN servers
        vpn_servers_to_add = {
            get_rule_id(rule) for rule in self.vpn_servers
            if get_rule_id(rule) not in self.known_unique_ids and get_rule_id(rule) is not None
        }
        
        # Log counts of new rules detected
        if (port_forwards_to_add or routes_to_add or policies_to_add or 
            traffic_rules_to_add or firewall_rules_to_add or wlans_to_add or qos_rules_to_add or vpn_clients_to_add or vpn_servers_to_add):
            LOGGER.debug(
                "Detected new rules - Port Forwards: %d, Traffic Routes: %d, "
                "Firewall Policies: %d, Traffic Rules: %d, Legacy Firewall Rules: %d, WLANs: %d, QoS Rules: %d, VPN Clients: %d, VPN Servers: %d",
                len(port_forwards_to_add), len(routes_to_add), len(policies_to_add),
                len(traffic_rules_to_add), len(firewall_rules_to_add), len(wlans_to_add),
                len(qos_rules_to_add), len(vpn_clients_to_add), len(vpn_servers_to_add)
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

        # Process VPN clients
        for rule in self.vpn_clients:
            try:
                rule_id = get_rule_id(rule)
                # Skip if already known or not in our list to add
                if not rule_id or (
                    rule_id not in vpn_clients_to_add):
                    continue
                    
                if rule_id in vpn_clients_to_add:
                    LOGGER.debug("Adding new VPN client entity: %s", rule_id)
                    self._entity_creation_queue.append({
                        "rule_data": rule,
                        "rule_type": "vpn_clients",
                        "entity_class": None,  # Will be determined during creation
                    })
            except Exception as err:
                LOGGER.exception("Error processing VPN client for entity creation: %s", err)
                
        # Process VPN servers
        for rule in self.vpn_servers:
            try:
                rule_id = get_rule_id(rule)
                # Skip if already known or not in our list to add
                if not rule_id or (
                    rule_id not in vpn_servers_to_add):
                    continue
                    
                if rule_id in vpn_servers_to_add:
                    LOGGER.debug("Adding new VPN server entity: %s", rule_id)
                    self._entity_creation_queue.append({
                        "rule_data": rule,
                        "rule_type": "vpn_servers",
                        "entity_class": None,  # Will be determined during creation
                    })
            except Exception as err:
                LOGGER.exception("Error processing VPN server for entity creation: %s", err)

    async def _discover_and_add_new_entities(self, new_data: Dict[str, List[Any]]) -> None:
        """Discover new rules from fetched data and dynamically add corresponding entities."""
        LOGGER.debug("Entity discovery called - callback set: %s, initial_update_done: %s", 
                    bool(self.async_add_entities_callback), self._initial_update_done)
        
        if not self.async_add_entities_callback:
            LOGGER.warning("Cannot add entities: callback not set (this is normal during initial setup)")
            return
        
        # Import local reference to the entities to avoid circular imports
        from .switch import (
            UnifiPortForwardSwitch,
            UnifiTrafficRuleSwitch,
            UnifiFirewallPolicySwitch,
            UnifiTrafficRouteSwitch,
            UnifiLegacyFirewallRuleSwitch,
            UnifiQoSRuleSwitch,
            UnifiWlanSwitch,
            UnifiTrafficRouteKillSwitch,
            UnifiVPNClientSwitch,
            UnifiVPNServerSwitch,
            UnifiLedToggleSwitch
        )

        # Define mappings from rule types to entities
        rule_type_entity_map = [
            ("port_forwards", UnifiPortForwardSwitch),
            ("traffic_rules", UnifiTrafficRuleSwitch),
            ("firewall_policies", UnifiFirewallPolicySwitch),
            ("traffic_routes", UnifiTrafficRouteSwitch),
            ("legacy_firewall_rules", UnifiLegacyFirewallRuleSwitch), 
            ("qos_rules", UnifiQoSRuleSwitch),
            ("wlans", UnifiWlanSwitch),
            ("vpn_clients", UnifiVPNClientSwitch),
            ("vpn_servers", UnifiVPNServerSwitch),
        ]

        # Gather potential entities from the NEW data
        potential_entities_data = {} # Map: unique_id -> {rule_data, rule_type, entity_class}
        all_current_unique_ids = set() # Keep track of all IDs found in this run

        for rule_type_key, entity_class in rule_type_entity_map:
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

        # Special handling for LED-capable devices
        devices = new_data.get("devices", [])
        if devices:
            for device in devices:
                try:
                    device_unique_id = f"unr_device_{device.mac}_led"
                    all_current_unique_ids.add(device_unique_id)
                    
                    if device_unique_id not in self.known_unique_ids:
                        potential_entities_data[device_unique_id] = {
                            "rule_data": device,
                            "rule_type": "devices",
                            "entity_class": UnifiLedToggleSwitch,
                        }
                        LOGGER.debug("Coordinator: Discovered potential new LED switch: %s", device_unique_id)
                except Exception as err:
                    LOGGER.warning("Coordinator: Error processing device during dynamic discovery: %s", err)

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
                              # We could either get entities from DOMAIN data, or use registry to get state to check the object
                              # Use registry-based state since it's more reliable
                              parent_entity_state = self.hass.states.get(parent_entity_id_in_hass)
                              if parent_entity_state:
                                  # For convenience, store the basic known information we have
                                  LOGGER.debug("Found parent entity '%s' state for kill switch", parent_entity_id_in_hass)
                                  entity.parent_entity_id = parent_entity_id_in_hass
                                  # This is different from the parent_entity check below, which refers to newly created entities
                                  LOGGER.debug("Coordinator: Linked new child %s to parent state %s", 
                                             unique_id, parent_entity_id_in_hass)
                              else:
                                  LOGGER.warning("Coordinator: Could not find parent entity state %s for new kill switch %s", 
                                               parent_id, unique_id)

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

    async def _async_get_vpn_clients(self) -> List[VPNConfig]:
        """Get VPN clients from the API."""
        try:
            result = await self.api.get_vpn_clients()
            LOGGER.debug("Fetched %d VPN clients", len(result))
            
            # Update the internal list
            self.vpn_clients = result
            return result
        except Exception as err:
            LOGGER.error("Failed to fetch VPN clients: %s", err)
            self._api_errors += 1
            raise

    async def _async_get_vpn_servers(self) -> List[VPNConfig]:
        """Get VPN servers from the API."""
        try:
            result = await self.api.get_vpn_servers()
            LOGGER.debug("Fetched %d VPN servers", len(result))
            
            # Update the internal list
            self.vpn_servers = result
            return result
        except Exception as err:
            LOGGER.error("Failed to fetch VPN servers: %s", err)
            self._api_errors += 1
            raise
