"""Switch platform for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Any, Final, Optional, Set
import time  # Add this import

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import async_get as async_get_entity_registry
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward
from aiounifi.models.firewall_zone import FirewallZone
from aiounifi.models.wlan import Wlan

from .const import DOMAIN, MANUFACTURER
from .coordinator import UnifiRuleUpdateCoordinator
from .helpers.rule import get_rule_id, get_rule_name, get_rule_enabled
from .models.firewall_rule import FirewallRule  # Import FirewallRule

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1
RULE_TYPES: Final = {
    "firewall_policies": "Firewall Policy",
    "traffic_rules": "Traffic Rule",
    "port_forwards": "Port Forward",
    "traffic_routes": "Traffic Route",
    "legacy_firewall_rules": "Legacy Firewall Rule"
}

# Track entities across the platform
_ENTITY_CACHE: Set[str] = set()

# Shared registry to track entities for removal
entity_registry = {}

# Utility functions to set up entities for each rule type
def _setup_firewall_policy_switches(coordinator, api, rule) -> Optional[SwitchEntity]:
    """Set up firewall policy switch."""
    rule_id = get_rule_id(rule)
    if not rule_id:
        LOGGER.warning("Unable to get rule_id for firewall policy")
        return None
    LOGGER.debug("Creating firewall policy switch for rule_id: %s", rule_id)
    return UnifiFirewallPolicySwitch(coordinator, rule, "firewall_policies")

def _setup_traffic_rule_switches(coordinator, api, rule) -> Optional[SwitchEntity]:
    """Set up traffic rule switch."""
    rule_id = get_rule_id(rule)
    if not rule_id:
        LOGGER.warning("Unable to get rule_id for traffic rule")
        return None
    LOGGER.debug("Creating traffic rule switch for rule_id: %s", rule_id)
    return UnifiTrafficRuleSwitch(coordinator, rule, "traffic_rules")

def _setup_port_forward_switches(coordinator, api, rule) -> Optional[SwitchEntity]:
    """Set up port forward switch."""
    rule_id = get_rule_id(rule)
    if not rule_id:
        LOGGER.warning("Unable to get rule_id for port forward")
        return None
    LOGGER.debug("Creating port forward switch for rule_id: %s", rule_id)
    return UnifiPortForwardSwitch(coordinator, rule, "port_forwards")

def _setup_traffic_route_switches(coordinator, api, rule) -> Optional[SwitchEntity]:
    """Set up traffic route switch."""
    rule_id = get_rule_id(rule)
    if not rule_id:
        LOGGER.warning("Unable to get rule_id for traffic route")
        return None
    LOGGER.debug("Creating traffic route switch for rule_id: %s", rule_id)
    return UnifiTrafficRouteSwitch(coordinator, rule, "traffic_routes")

def _setup_legacy_firewall_rule_switches(coordinator, api, rule) -> Optional[SwitchEntity]:
    """Set up legacy firewall rule switch."""
    rule_id = get_rule_id(rule)
    if not rule_id:
        LOGGER.warning("Unable to get rule_id for legacy firewall rule")
        return None
    LOGGER.debug("Creating legacy firewall rule switch for rule_id: %s", rule_id)
    return UnifiLegacyFirewallRuleSwitch(coordinator, rule, "legacy_firewall_rules")

def _setup_wlan_switches(coordinator, api, rule) -> Optional[SwitchEntity]:
    """Set up WLAN switch."""
    rule_id = get_rule_id(rule)
    if not rule_id:
        LOGGER.warning("Unable to get rule_id for WLAN")
        return None
    LOGGER.debug("Creating WLAN switch for rule_id: %s", rule_id)
    return UnifiWlanSwitch(coordinator, rule, "wlans")

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the UniFi Network Rules switch platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    # Add detailed debug logging about coordinator state
    LOGGER.info("Setting up switch platform with coordinator data status:")
    LOGGER.info("- Coordinator last update success: %s", coordinator.last_update_success)
    LOGGER.info("- Coordinator data present: %s", bool(coordinator.data))
    
    if coordinator.data:
        rule_counts = {
            "port_forwards": len(coordinator.port_forwards),
            "traffic_routes": len(coordinator.traffic_routes),
            "firewall_policies": len(coordinator.firewall_policies),
            "traffic_rules": len(coordinator.traffic_rules),
            "legacy_firewall_rules": len(coordinator.legacy_firewall_rules),
            "wlans": len(coordinator.wlans) if hasattr(coordinator, "wlans") else 0
        }
        LOGGER.info("- Rule counts: %s", rule_counts)
    else:
        LOGGER.warning("No coordinator data available for entity creation")
    
    # Create a closure that has access to hass
    @callback
    def handle_entity_removal(entity_id: str) -> None:
        """Handle entity removal with access to hass."""
        if entity_id in entity_registry:
            entity = entity_registry[entity_id]
            LOGGER.info("Found entity to remove: %s", entity_id)
            
            # Get the entity registry to properly remove the entity
            er = async_get_entity_registry(hass)
            
            # Find and remove the entity from HA entity registry by unique_id
            if hasattr(entity, "unique_id"):
                unique_id = entity.unique_id
                for reg_entity_id, reg_entity in er.entities.items():
                    if reg_entity.unique_id == unique_id:
                        LOGGER.info("Removing entity from HA registry: %s", reg_entity_id)
                        er.async_remove(reg_entity_id)
                        break
            
            # Signal platform to remove entity
            try:
                hass.async_create_task(entity.async_remove())
                LOGGER.debug("Async remove task created for entity: %s", entity_id)
            except Exception as err:
                LOGGER.error("Error creating remove task: %s", err)
            
            # Remove from our registry
            del entity_registry[entity_id]
            LOGGER.debug("Entity removed from registry: %s", entity_id)
            
            # Also remove from the entity cache
            if entity_id in _ENTITY_CACHE:
                LOGGER.debug("Removing entity from cache: %s", entity_id)
                _ENTITY_CACHE.remove(entity_id)
                LOGGER.debug("Entity removed from cache")
        else:
            LOGGER.warning("Entity not found for removal: %s", entity_id)
    
    # Register our entity removal handler with the coordinator
    coordinator._entity_removal_callback = handle_entity_removal

    # Create entities for each existing rule
    entities = []
    entry_id = config_entry.entry_id
    
    # Port Forwards
    for rule in coordinator.port_forwards:
        # Generate a unique rule ID for this rule
        rule_id = get_rule_id(rule)
        if not rule_id:
            continue
            
        # Create a new entity for this rule
        entity = UnifiPortForwardSwitch(
            coordinator, rule, "port_forwards", entry_id
        )
        entities.append(entity)
        entity_registry[rule_id] = entity
        
        # Store the rule ID for tracking
        if rule_id not in coordinator._tracked_port_forwards:
            coordinator._tracked_port_forwards.add(rule_id)
    
    # Traffic Routes
    for rule in coordinator.traffic_routes:
        rule_id = get_rule_id(rule)
        if not rule_id:
            continue
            
        entity = UnifiTrafficRouteSwitch(
            coordinator, rule, "traffic_routes", entry_id
        )
        entities.append(entity)
        entity_registry[rule_id] = entity
        
        if rule_id not in coordinator._tracked_routes:
            coordinator._tracked_routes.add(rule_id)
    
    # Firewall Policies
    for rule in coordinator.firewall_policies:
        rule_id = get_rule_id(rule)
        if not rule_id:
            continue
            
        entity = UnifiFirewallPolicySwitch(
            coordinator, rule, "firewall_policies", entry_id
        )
        entities.append(entity)
        entity_registry[rule_id] = entity
        
        if rule_id not in coordinator._tracked_policies:
            coordinator._tracked_policies.add(rule_id)
    
    # Traffic Rules
    for rule in coordinator.traffic_rules:
        rule_id = get_rule_id(rule)
        if not rule_id:
            continue
            
        entity = UnifiTrafficRuleSwitch(
            coordinator, rule, "traffic_rules", entry_id
        )
        entities.append(entity)
        entity_registry[rule_id] = entity
        
        if rule_id not in coordinator._tracked_traffic_rules:
            coordinator._tracked_traffic_rules.add(rule_id)
    
    # Legacy Firewall Rules
    for rule in coordinator.legacy_firewall_rules:
        rule_id = get_rule_id(rule)
        if not rule_id:
            continue
            
        entity = UnifiLegacyFirewallRuleSwitch(
            coordinator, rule, "legacy_firewall_rules", entry_id
        )
        entities.append(entity)
        entity_registry[rule_id] = entity
        
        if rule_id not in coordinator._tracked_firewall_rules:
            coordinator._tracked_firewall_rules.add(rule_id)
    
    # Wireless Networks
    for rule in coordinator.wlans:
        rule_id = get_rule_id(rule)
        if not rule_id:
            continue
            
        entity = UnifiWlanSwitch(
            coordinator, rule, "wlans", entry_id
        )
        entities.append(entity)
        entity_registry[rule_id] = entity
        
        if rule_id not in coordinator._tracked_wlans:
            coordinator._tracked_wlans.add(rule_id)
    
    LOGGER.info("Adding %d entities to Home Assistant", len(entities))
    async_add_entities(entities)

class UnifiRuleSwitch(CoordinatorEntity[UnifiRuleUpdateCoordinator], SwitchEntity):
    """Switch to enable/disable UniFi Network rules."""

    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize the rule switch."""
        super().__init__(coordinator)
        self._rule_data = rule_data
        self._rule_type = rule_type
        self._entry_id = entry_id
        # Set entity category as a configuration entity
        self.entity_category = EntityCategory.CONFIG
        
        # Log detailed information about the rule object
        LOGGER.debug(
            "Initializing switch for rule - Type: %s", 
            type(rule_data)
        )
        
        # Get rule ID using helper function
        self._rule_id = get_rule_id(rule_data)
        if not self._rule_id:
            raise ValueError("Rule must have an ID")
        
        # Get rule name using helper function
        name = get_rule_name(rule_data) or f"Rule {self._rule_id}"
        self._attr_name = name
        
        # Fix unique_id to use the rule_id directly since it already has type prefixes
        # This prevents double-prefixing issues
        self._attr_unique_id = self._rule_id
        
        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.api.host)},
            name="UniFi Network Rules",
            manufacturer="Ubiquiti",
            model="UniFi Dream Machine"
        )
        
        # Enable optimistic updates for better UX
        self._attr_assumed_state = True
        self._optimistic_state = None
        self._optimistic_timestamp = 0  # Add timestamp for optimistic state

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Check if we're in a temporary auth failure state
        if not self.coordinator.data or self._rule_type not in self.coordinator.data:
            # Likely a temporary API error, don't update state
            LOGGER.debug("Coordinator missing data for %s - skipping update", self._rule_type)
            return
            
        # Only update rule data if we have a valid rule in the coordinator
        new_rule = self._get_current_rule()
        if new_rule is not None:
            # Check if this entity has a pending operation
            has_pending_op = (hasattr(self.coordinator, "_pending_operations") and 
                             self._rule_id in self.coordinator._pending_operations)
            
            # If there's a pending operation, keep the optimistic state
            if has_pending_op:
                target_state = self.coordinator._pending_operations[self._rule_id]
                LOGGER.debug("Entity %s has pending operation to state %s - keeping optimistic state",
                           self._rule_id, target_state)
                self._optimistic_state = target_state
                self._optimistic_timestamp = time.time()  # Refresh timestamp
            # Only clear optimistic state if no pending operations and it's been more than 10 seconds
            # This prevents rapid authentication cycles from clearing optimistic state
            elif self._optimistic_state is not None:
                current_time = time.time()
                if current_time - self._optimistic_timestamp > 10:
                    LOGGER.debug("Clearing optimistic state after 10 seconds")
                    self._optimistic_state = None
                    self._optimistic_timestamp = 0
                else:
                    LOGGER.debug("Keeping optimistic state, only %d seconds elapsed", 
                               current_time - self._optimistic_timestamp)
            
            self._rule_data = new_rule
            
        # Schedule update to Home Assistant
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._get_current_rule() is not None

    @property
    def is_on(self) -> bool:
        """Return the enabled state of the rule."""
        # Use optimistic state if set
        if self._optimistic_state is not None:
            return self._optimistic_state
            
        rule = self._get_current_rule()
        if rule is None:
            return False
            
        return get_rule_enabled(rule)

    @property
    def assumed_state(self) -> bool:
        """Return True as we're implementing optimistic state."""
        return True

    def _get_current_rule(self) -> Any | None:
        """Get current rule data from coordinator."""
        try:
            rules = self.coordinator.data.get(self._rule_type, [])
            for rule in rules:
                if get_rule_id(rule) == self._rule_id:
                    return rule
            return None
        except Exception as err:
            LOGGER.error("Error getting rule data: %s", err)
            return None

    def _to_dict(self, obj: Any) -> dict:
        """Convert a rule object to a dictionary."""
        # Handle objects with raw property (aiounifi API objects and FirewallRule)
        if hasattr(obj, "raw") and isinstance(obj.raw, dict):
            return obj.raw.copy()
        
        # Handle plain dictionaries
        if isinstance(obj, dict):
            return obj.copy()
            
        # Handle other objects by creating a dict from properties
        # Get the rule ID properly considering object type
        rule_id = None
        if hasattr(obj, "id"):
            rule_id = getattr(obj, "id")
            
        base_data = {
            "_id": rule_id,
            "enabled": getattr(obj, "enabled", False)
        }
        
        # Include other common attributes if they exist
        for attr in ["name", "description", "action"]:
            if hasattr(obj, attr):
                base_data[attr] = getattr(obj, attr)
        
        return {k: v for k, v in base_data.items() if v is not None}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on (enable) the rule."""
        await self._async_toggle_rule(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off (disable) the rule."""
        await self._async_toggle_rule(False)

    async def _async_toggle_rule(self, enable: bool) -> None:
        """Handle toggling the rule state."""
        action_type = "Turning on" if enable else "Turning off"
        LOGGER.debug("%s rule %s (%s)", action_type, self._rule_id, self._rule_type)
        
        # Set optimistic state first for immediate UI feedback with timestamp
        self._optimistic_state = enable
        self._optimistic_timestamp = time.time()
        self.async_write_ha_state()
        
        # Get the current rule object
        current_rule = self._get_current_rule()
        if current_rule is None:
            LOGGER.error("Rule not found in coordinator data: %s", self._rule_id)
            # Revert optimistic state
            self._optimistic_state = not enable
            self._optimistic_timestamp = time.time()
            self.async_write_ha_state()
            return
        
        # Initialize pending operations dict if needed
        if not hasattr(self.coordinator, "_pending_operations"):
            self.coordinator._pending_operations = {}
            
        # Add this entity's ID to pending operations with target state
        self.coordinator._pending_operations[self._rule_id] = enable
        
        LOGGER.debug("Adding rule %s to pending operations queue with target state: %s", 
                   self._rule_id, enable)
        
        # Define callback to handle operation completion
        async def handle_operation_complete(future):
            """Handle operation completion."""
            try:
                success = future.result()
                LOGGER.debug("Operation completed for rule %s with result: %s", 
                            self._rule_id, success)
                
                if not success:
                    # Revert optimistic state if failed
                    LOGGER.error("Failed to %s rule %s", 
                                "enable" if enable else "disable", self._rule_id)
                    self._optimistic_state = not enable
                    self._optimistic_timestamp = time.time()
                    self.async_write_ha_state()
                
                # Request refresh to update state from backend
                await self.coordinator.async_request_refresh()
            except Exception as err:
                LOGGER.error("Error in toggle operation for rule %s: %s", 
                            self._rule_id, err)
                # Revert optimistic state on error
                self._optimistic_state = not enable
                self._optimistic_timestamp = time.time()
                self.async_write_ha_state()
            finally:
                # Always remove from pending operations when complete
                if self._rule_id in self.coordinator._pending_operations:
                    LOGGER.debug("Removing rule %s from pending operations after completion", 
                               self._rule_id)
                    del self.coordinator._pending_operations[self._rule_id]
        
        # Queue the appropriate toggle operation based on rule type
        try:
            # Select the appropriate toggle function
            toggle_func = None
            if self._rule_type == "firewall_policies":
                toggle_func = self.coordinator.api.toggle_firewall_policy
            elif self._rule_type == "traffic_rules":
                toggle_func = self.coordinator.api.toggle_traffic_rule
            elif self._rule_type == "port_forwards":
                toggle_func = self.coordinator.api.toggle_port_forward
            elif self._rule_type == "traffic_routes":
                toggle_func = self.coordinator.api.toggle_traffic_route
            elif self._rule_type == "legacy_firewall_rules":
                toggle_func = self.coordinator.api.toggle_legacy_firewall_rule
            elif self._rule_type == "wlans":
                toggle_func = self.coordinator.api.toggle_wlan
            else:
                raise ValueError(f"Unknown rule type: {self._rule_type}")
            
            # Queue the operation
            future = await self.coordinator.api.queue_api_operation(toggle_func, current_rule)
            
            # Add the completion callback
            future.add_done_callback(
                lambda f: self.hass.async_create_task(handle_operation_complete(f))
            )
            
            LOGGER.debug("Successfully queued toggle operation for rule %s", self._rule_id)
        except Exception as err:
            LOGGER.error("Failed to queue toggle operation for rule %s: %s", 
                         self._rule_id, err)
            # Remove from pending operations if queueing failed
            if self._rule_id in self.coordinator._pending_operations:
                del self.coordinator._pending_operations[self._rule_id]
            
            # Revert optimistic state
            self._optimistic_state = not enable
            self._optimistic_timestamp = time.time()
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is being removed from Home Assistant."""
        LOGGER.debug("Entity %s is being removed from Home Assistant", self.entity_id)
        # Make sure we don't leave any listeners around
        await super().async_will_remove_from_hass()
        
        # Log detailed info for diagnostics
        LOGGER.info(
            "Removing entity - Type: %s, Rule ID: %s, Unique ID: %s", 
            self._rule_type, 
            self._rule_id,
            self.unique_id
        )

# Define specific switch classes for each rule type
class UnifiPortForwardSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi port forward rule."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str, 
        entry_id: str = None,
    ) -> None:
        """Initialize port forward switch."""
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Add any port-forward specific functionality here

class UnifiTrafficRouteSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi traffic route rule."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize traffic route switch."""
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Add any traffic-route specific functionality here

class UnifiFirewallPolicySwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi firewall policy."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize firewall policy switch."""
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Add any firewall-policy specific functionality here

class UnifiTrafficRuleSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi traffic rule."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize traffic rule switch."""
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Add any traffic-rule specific functionality here

class UnifiLegacyFirewallRuleSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi legacy firewall rule."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize legacy firewall rule switch."""
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Add any legacy-firewall specific functionality here

class UnifiWlanSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi wireless network."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize WLAN switch."""
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Add any WLAN-specific functionality here