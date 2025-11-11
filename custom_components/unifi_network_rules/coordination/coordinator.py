"""Refactored UniFi Network Rules Coordinator.

This is the main coordinator class that orchestrates data fetching, entity management,
authentication, and state tracking through dedicated modules. It replaces the monolithic
coordinator with a clean, modular architecture while maintaining full backward compatibility.
"""
from __future__ import annotations

from datetime import timedelta
import asyncio
from typing import Any, Dict, List, Optional, Set

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import Platform

# Import aiounifi models for type hints
from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward
from aiounifi.models.firewall_zone import FirewallZone
from aiounifi.models.wlan import Wlan
from aiounifi.models.device import Device

# Import our modules and models
from ..const import DOMAIN, LOGGER, DEFAULT_UPDATE_INTERVAL, LOG_TRIGGERS
from ..udm import UDMAPI
from ..models.firewall_rule import FirewallRule
from ..models.qos_rule import QoSRule
from ..models.vpn_config import VPNConfig
from ..models.port_profile import PortProfile
from ..models.network import NetworkConf
from ..models.static_route import StaticRoute
from ..models.nat_rule import NATRule
from ..models.oon_policy import OONPolicy
from ..smart_polling import SmartPollingManager, SmartPollingConfig
from ..unified_change_detector import UnifiedChangeDetector

# Import coordination modules
from .data_fetcher import CoordinatorDataFetcher
from .entity_manager import CoordinatorEntityManager
from .auth_manager import CoordinatorAuthManager
from .state_manager import CoordinatorStateManager

# Fallback scan interval
SCAN_INTERVAL = timedelta(seconds=60)


class NeedsFetch(Exception):
    """Raised when a rule needs to be fetched again after a discovery."""


class UnifiRuleUpdateCoordinator(DataUpdateCoordinator):
    """UniFi Network Rules API Coordinator with modular architecture."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        api: UDMAPI, 
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
        platforms: Optional[List[Platform]] = None,
        smart_polling_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the coordinator with modular components."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

        # Keep a reference to the API
        self.api = api
        
        # Initialize config_entry to None - it will be looked up when needed
        self.config_entry = None
        
        # Initialize coordination modules
        self.data_fetcher = CoordinatorDataFetcher(api, hass, self)
        self.entity_manager = CoordinatorEntityManager(hass, self)
        self.auth_manager = CoordinatorAuthManager(hass, api)
        self.state_manager = CoordinatorStateManager(hass, self)
        
        # Initialize Smart Polling Manager
        polling_config = SmartPollingConfig(
            base_interval=smart_polling_config.get('base_interval', 300) if smart_polling_config else 300,
            active_interval=smart_polling_config.get('active_interval', 30) if smart_polling_config else 30,
            realtime_interval=smart_polling_config.get('realtime_interval', 10) if smart_polling_config else 10,
            activity_timeout=smart_polling_config.get('activity_timeout', 120) if smart_polling_config else 120,
            debounce_seconds=smart_polling_config.get('debounce_seconds', 10) if smart_polling_config else 10,
            optimistic_timeout=smart_polling_config.get('optimistic_timeout', 15) if smart_polling_config else 15,
        )
        self.smart_polling = SmartPollingManager(self, polling_config)
        
        # Initialize Unified Change Detector
        self.change_detector = UnifiedChangeDetector(hass, self)
        
        # Update lock - prevent simultaneous updates
        self._update_lock = asyncio.Lock()

        # Track entities we added or removed (by unique ID)
        self.known_unique_ids: Set[str] = set()
        
        # Rule collections - maintained for backward compatibility
        self.port_forwards: List[PortForward] = []
        self.traffic_routes: List[TrafficRoute] = []
        self.firewall_policies: List[FirewallPolicy] = []
        self.traffic_rules: List[TrafficRule] = []
        self.static_routes: List[StaticRoute] = []
        self.legacy_firewall_rules: List[FirewallRule] = []
        self.firewall_zones: List[FirewallZone] = []
        self.wlans: List[Wlan] = []
        self.qos_rules: List[QoSRule] = []
        self.vpn_clients: List[VPNConfig] = []
        self.vpn_servers: List[VPNConfig] = []
        self.devices: List[Device] = []
        self.port_profiles: List[PortProfile] = []
        self.networks: List[NetworkConf] = []
        self.nat_rules: List[NATRule] = []
        self.oon_policies: List[OONPolicy] = []

        # For dynamic entity creation
        self.async_add_entities_callback: AddEntitiesCallback | None = None

        # Save platforms to load
        self._platforms = platforms or [Platform.SWITCH]

        # Webhook tracking
        self.webhook_id = None
        self.webhook_url = None
        self.webhook_registered = False

    # Backward compatibility methods - delegate to auth manager
    def register_ha_initiated_operation(self, rule_id: str, entity_id: str, change_type: str = "modified", timeout: int = 15) -> None:
        """Register that a rule change was initiated from HA."""
        self.auth_manager.register_ha_initiated_operation(rule_id, entity_id, change_type, timeout)
        
        # Register with smart polling system for debounced refresh
        self.hass.async_create_task(
            self.smart_polling.register_entity_change(entity_id, change_type)
        )
        
    def check_and_consume_ha_initiated_operation(self, rule_id: str) -> bool:
        """Check if a rule change was HA-initiated and consume the flag."""
        return self.auth_manager.check_and_consume_ha_initiated_operation(rule_id)

    def fire_device_trigger_via_dispatcher(self, device_id: str, device_name: str, change_type: str, old_state: Any = None, new_state: Any = None) -> None:
        """Fire device_changed triggers using Home Assistant's dispatcher pattern."""
        if LOG_TRIGGERS:
            LOGGER.info("🔥 COORDINATOR: Dispatching device trigger for %s (%s): %s", 
                       device_name, device_id, change_type)
        
        # Prepare trigger data
        trigger_data = {
            "device_id": device_id,
            "device_name": device_name,
            "change_type": change_type,
            "old_state": old_state,
            "new_state": new_state,
            "trigger_type": "device_changed"
        }
        
        # Dispatch via Home Assistant's dispatcher system
        try:
            entry_id = self.config_entry.entry_id if self.config_entry else "unknown"
            signal_name = f"{DOMAIN}_device_trigger_{entry_id}"
            
            async_dispatcher_send(self.hass, signal_name, trigger_data)
            
            if LOG_TRIGGERS:
                LOGGER.info("✅ COORDINATOR: Dispatched device trigger signal: %s", signal_name)
                
        except Exception as err:
            LOGGER.error("Error dispatching device trigger: %s", err)

    async def register_external_change_detected(self) -> None:
        """Register that external changes were detected during polling."""
        await self.smart_polling.register_external_change_detected()
        
    def get_smart_polling_status(self) -> Dict[str, Any]:
        """Get smart polling status for diagnostics."""
        return self.smart_polling.get_status()
    
    def get_change_detector_status(self) -> Dict[str, Any]:
        """Get change detector status for diagnostics."""
        return self.change_detector.get_status()

    async def _async_update_data(self) -> Dict[str, List[Any]]:
        """Fetch data from API endpoint using modular architecture."""
        # Use a lock to prevent concurrent updates
        if self._update_lock.locked():
            LOGGER.debug("Another update is already in progress, waiting for it to complete")
            if self.data:
                return self.data
            elif self.state_manager._last_successful_data:
                return self.state_manager._last_successful_data
        
        async with self._update_lock:
            try:
                # Check if authentication is in progress
                if self.auth_manager.is_authentication_in_progress():
                    LOGGER.warning("Update started while authentication is in progress - using cached data")
                    if self.data:
                        return self.data
                    elif self.state_manager._last_successful_data:
                        return self.state_manager._last_successful_data

                # Store previous data for change detection
                previous_data = self.data.copy() if self.data else {}

                # Fetch all entity data using the data fetcher
                rules_data = await self.data_fetcher.fetch_all_entity_data()

                # Validate data and handle errors
                is_valid = self.state_manager.validate_data_and_handle_errors(rules_data, previous_data)
                if not is_valid and self.state_manager._last_successful_data:
                    LOGGER.info("Using cached data from last successful update")
                    return self.state_manager._last_successful_data

                # Check for API authentication errors
                api_error_message = getattr(self.api, "_last_error_message", "")
                if api_error_message and ("401 Unauthorized" in api_error_message or "403 Forbidden" in api_error_message):
                    LOGGER.warning("Authentication error in API response: %s", api_error_message)
                    async_dispatcher_send(self.hass, f"{DOMAIN}_auth_failure")

                # Reset authentication state on successful operation
                self.auth_manager.reset_authentication_state()

                # Store whether this is the initial update before setting the flag
                is_initial_update = not self.state_manager.is_initial_update_done()

                # Run unified change detection and fire triggers BEFORE marking initial update done
                try:
                    changes = await self.change_detector.detect_and_fire_changes(rules_data)
                    if changes:
                        LOGGER.info("[UNIFIED_TRIGGERS] Detected %d changes, fired unified triggers", len(changes))
                    else:
                        if is_initial_update:
                            total_entities = sum(len(rules_data.get(key, [])) for key in [
                                "port_forwards", "traffic_routes", "static_routes", "nat_rules",
                                "firewall_policies", "traffic_rules", "legacy_firewall_rules", 
                                "wlans", "qos_rules", "vpn_clients", "vpn_servers", 
                                "devices", "networks"
                            ])
                            LOGGER.info("[UNIFIED_TRIGGERS] Initial discovery complete: %d entities discovered (no triggers fired)", total_entities)
                        else:
                            LOGGER.debug("[UNIFIED_TRIGGERS] No changes detected during this update cycle")
                except Exception as exc:
                    LOGGER.error("[UNIFIED_TRIGGERS] Error during change detection: %s", exc)
                    LOGGER.exception("Change detection exception details:")

                # Mark initial update as done AFTER change detection
                if not self.state_manager.is_initial_update_done():
                    self.state_manager.mark_initial_update_done()

                # Perform entity lifecycle operations only AFTER initial update
                if self.state_manager.is_initial_update_done():
                    # Check for deleted entities
                    self.entity_manager.check_for_deleted_rules(rules_data)

                    # Discover and add new entities
                    await self.entity_manager.discover_and_add_new_entities(rules_data)

                # Update internal collections for backward compatibility
                self._update_internal_collections(rules_data)

                # Log collection counts
                self._log_collection_counts()

                # Check if external changes were detected during baseline polling
                if previous_data and self.state_manager.data_has_changes(previous_data, rules_data):
                    if not self.smart_polling.is_in_smart_poll_cycle():
                        LOGGER.debug("[SMART_POLL] External changes detected during baseline polling cycle")
                        await self.register_external_change_detected()
                    else:
                        LOGGER.debug("[SMART_POLL] Changes detected during smart polling cycle - not registering as external")

                return rules_data

            except Exception as err:
                # Handle authentication errors
                if self.auth_manager.check_auth_error(err):
                    auth_recovered = await self.auth_manager.handle_authentication_error(err, self)
                    if auth_recovered and self.data:
                        return self.data

                # Return previous data during errors if available
                if self.data:
                    LOGGER.info("Returning previous data during error")
                    return self.data

                raise UpdateFailed(f"Error updating data: {err}") from err

    def _update_internal_collections(self, rules_data: Dict[str, List[Any]]) -> None:
        """Update internal collections for backward compatibility."""
        self.port_forwards = rules_data.get("port_forwards", [])
        self.traffic_routes = rules_data.get("traffic_routes", [])
        self.static_routes = rules_data.get("static_routes", [])
        self.firewall_policies = rules_data.get("firewall_policies", [])
        self.traffic_rules = rules_data.get("traffic_rules", [])
        self.legacy_firewall_rules = rules_data.get("legacy_firewall_rules", [])
        self.wlans = rules_data.get("wlans", [])
        self.firewall_zones = rules_data.get("firewall_zones", [])
        self.qos_rules = rules_data.get("qos_rules", [])
        self.vpn_clients = rules_data.get("vpn_clients", [])
        self.vpn_servers = rules_data.get("vpn_servers", [])
        self.devices = rules_data.get("devices", [])
        self.port_profiles = rules_data.get("port_profiles", [])
        self.networks = rules_data.get("networks", [])
        self.nat_rules = rules_data.get("nat_rules", [])
        self.oon_policies = rules_data.get("oon_policies", [])

    def _log_collection_counts(self) -> None:
        """Log the counts of all rule collections."""
        LOGGER.info("Rule collections after refresh: Port Forwards=%d, Traffic Routes=%d, Static Routes=%d, "
                   "Firewall Policies=%d, Traffic Rules=%d, NAT Rules=%d, Legacy Firewall Rules=%d, "
                   "WLANs=%d, QoS Rules=%d, VPN Clients=%d, VPN Servers=%d, Networks=%d, Devices=%d", 
                   len(self.port_forwards), len(self.traffic_routes), len(self.static_routes),
                   len(self.firewall_policies), len(self.traffic_rules), len(self.nat_rules),
                   len(self.legacy_firewall_rules), len(self.wlans), len(self.qos_rules),
                   len(self.vpn_clients), len(self.vpn_servers), len(self.networks), len(self.devices))

    # Backward compatibility methods
    async def process_new_entities(self) -> None:
        """Process and create entities that were discovered (backward compatibility)."""
        LOGGER.debug("process_new_entities called - delegating to entity_manager")
        # This method is kept for backward compatibility but functionality is now in entity_manager
        
    @callback
    def shutdown(self) -> None:
        """Clean up resources."""
        pass
            
    async def async_shutdown(self) -> None:
        """Clean up resources asynchronously."""
        # Clean up smart polling first
        if hasattr(self, 'smart_polling'):
            await self.smart_polling.cleanup()
        
        # Call the synchronous shutdown method
        self.shutdown()

    # Properties for backward compatibility - delegate to state manager
    @property 
    def _initial_update_done(self) -> bool:
        """Check if initial update is done (backward compatibility)."""
        return self.state_manager.is_initial_update_done()
    
    @_initial_update_done.setter
    def _initial_update_done(self, value: bool) -> None:
        """Set initial update done state (backward compatibility)."""
        if value:
            self.state_manager.mark_initial_update_done()

    @property
    def _last_successful_data(self) -> Dict[str, List[Any]]:
        """Get last successful data (backward compatibility)."""
        return self.state_manager._last_successful_data

    @_last_successful_data.setter 
    def _last_successful_data(self, value: Dict[str, List[Any]]) -> None:
        """Set last successful data (backward compatibility)."""
        self.state_manager._last_successful_data = value
