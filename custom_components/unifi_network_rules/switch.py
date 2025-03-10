"""Switch platform for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Any, Final, Optional, Set
import time  # Add this import
import asyncio
import contextlib
import re

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription, PLATFORM_SCHEMA
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.device_registry import async_get as async_get_entity_registry
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import generate_entity_id

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward
from aiounifi.models.firewall_zone import FirewallZone
from aiounifi.models.wlan import Wlan

from .const import DOMAIN, MANUFACTURER
from .coordinator import UnifiRuleUpdateCoordinator
from .helpers.rule import get_rule_id, get_rule_name, get_rule_enabled, get_object_id
from .models.firewall_rule import FirewallRule  # Import FirewallRule
from .services.constants import SIGNAL_ENTITIES_CLEANUP

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

# Global registry to track created entity unique IDs
_CREATED_UNIQUE_IDS = set()

async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    """Set up the UniFi Network Rules switch platform."""
    LOGGER.debug("Setting up switch platform for UniFi Network Rules")
    # This function will be called when the platform is loaded manually
    # Most functionality is handled through config_flow and config_entries
    return True

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up switches for UniFi Network Rules component."""
    LOGGER.debug("Setting up UniFi Network Rules switches")
    
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    # Initialize platform with entities that already exist
    switches = []
    
    # Track entity IDs to prevent duplicates - use unique_ids not entity_ids
    unique_ids_seen = set()
    
    # Get the entity registry to check for existing entities
    from homeassistant.helpers.entity_registry import async_get as get_entity_registry
    entity_registry = get_entity_registry(hass)
    
    # Process all rule types using consistent entity creation
    for rule_type, rules in [
        ("port_forwards", coordinator.port_forwards),
        ("traffic_routes", coordinator.traffic_routes),
        ("firewall_policies", coordinator.firewall_policies),
        ("traffic_rules", coordinator.traffic_rules),
        ("legacy_firewall_rules", coordinator.legacy_firewall_rules),
        ("wlans", coordinator.wlans)
    ]:
        for rule in rules:
            try:
                # Get the rule ID first - if we can't get a valid ID, skip this rule
                rule_id = get_rule_id(rule)
                if not rule_id:
                    LOGGER.error("Cannot create entity for rule without ID: %s", rule)
                    continue
                
                # Check if we've already seen this unique_id
                if rule_id in unique_ids_seen:
                    LOGGER.debug("Skipping duplicate rule ID: %s", rule_id)
                    continue
                
                # Check if this entity already exists in the registry
                existing_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, rule_id)
                if existing_entity_id:
                    LOGGER.debug("Entity already exists in registry: %s (%s)", existing_entity_id, rule_id)
                
                # Use the appropriate entity class based on rule type
                entity_class = None
                if rule_type == "port_forwards":
                    entity_class = UnifiPortForwardSwitch
                elif rule_type == "traffic_routes":
                    entity_class = UnifiTrafficRouteSwitch
                elif rule_type == "firewall_policies":
                    entity_class = UnifiFirewallPolicySwitch
                elif rule_type == "traffic_rules":
                    entity_class = UnifiTrafficRuleSwitch
                elif rule_type == "legacy_firewall_rules":
                    entity_class = UnifiLegacyFirewallRuleSwitch
                elif rule_type == "wlans":
                    entity_class = UnifiWlanSwitch
                
                if entity_class:
                    entity = entity_class(coordinator, rule, rule_type, config_entry.entry_id)
                    
                    # Add to seen unique IDs
                    unique_ids_seen.add(rule_id)
                    
                    # Add to switch list
                    switches.append(entity)
                    LOGGER.debug("Added %s entity: %s (unique_id: %s)", rule_type, entity.name, entity.unique_id)
            except Exception as err:
                LOGGER.error("Error creating %s entity: %s", rule_type, err)
        
    if switches:
        LOGGER.info("Adding %d UniFi Network Rules switch entities", len(switches))
        try:
            # Add entities with update_before_add=True to ensure they're fully initialized
            async_add_entities(switches, update_before_add=True)
                
        except Exception as e:
            LOGGER.error("Error adding entities: %s", e)

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
        
        # Get rule ID using helper function
        self._rule_id = get_rule_id(rule_data)
        if not self._rule_id:
            raise ValueError("Rule must have an ID")
            
        # Track globally that we're creating this unique ID
        global _CREATED_UNIQUE_IDS
        if self._rule_id in _CREATED_UNIQUE_IDS:
            LOGGER.warning("Duplicate entity creation attempted with unique_id: %s", self._rule_id)
        _CREATED_UNIQUE_IDS.add(self._rule_id)
        
        # Get rule name using helper function - rely entirely on rule.py for naming
        self._attr_name = get_rule_name(rule_data) or f"Rule {self._rule_id}"
        
        # Set unique_id to the rule ID directly - this is what the helper provides
        # This ensures consistency with how rules are identified throughout the integration
        self._attr_unique_id = self._rule_id
        
        # Get the object_id from our helper for consistency
        object_id = get_object_id(rule_data, rule_type)
        
        # Set the entity_id properly using generate_entity_id helper
        # This is the correct way to set a custom entity_id
        self.entity_id = generate_entity_id(
            f"{DOMAIN}.{{}}", object_id, hass=coordinator.hass
        )
        
        # Set has_entity_name to False to ensure the entity name is shown in UI
        self._attr_has_entity_name = False
        
        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.api.host)},
            name="UniFi Network Rules",
            manufacturer=MANUFACTURER,
            model="UniFi Dream Machine"
        )
        
        # Enable optimistic updates for better UX
        self._attr_assumed_state = True
        self._optimistic_state = None
        self._optimistic_timestamp = 0  # Add timestamp for optimistic state
        
        LOGGER.debug("Initialized entity with unique_id=%s, entity_id=%s", 
                   self._attr_unique_id, self.entity_id)

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
                    # Before clearing optimistic state, verify the rule's current state from coordinator data
                    if hasattr(new_rule, "enabled"):
                        current_state = new_rule.enabled
                        LOGGER.debug("Actual rule state from API is %s for rule %s", 
                                  current_state, self._rule_id)
                        # Only clear if actual state matches optimistic state
                        if self._optimistic_state == current_state:
                            self._optimistic_state = None
                            self._optimistic_timestamp = 0
                        else:
                            LOGGER.warning(
                                "Optimistic state (%s) doesn't match actual state (%s) for rule %s, keeping optimistic", 
                                self._optimistic_state, 
                                current_state, 
                                self._rule_id
                            )
                            # Extend optimistic state time to give more time for state to sync
                            self._optimistic_timestamp = time.time()
                    else:
                        # If no enabled attribute, default to clearing optimistic state
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
                else:
                    # On success, refresh the optimistic state timestamp to prevent premature clearing
                    self._optimistic_timestamp = time.time()
                    self.async_write_ha_state()
                
                # Request refresh to update state from backend
                await self.coordinator.async_request_refresh()
                
                # Extra verification: If operation succeeded, schedule a delayed verification refresh
                # to ensure state is consistent after UI navigation
                if success:
                    async def delayed_verify():
                        # Wait a bit to allow navigation events to complete
                        await asyncio.sleep(2)
                        await self.coordinator.async_request_refresh()
                        LOGGER.debug("Performed delayed verification refresh for rule %s", self._rule_id)
                    
                    asyncio.create_task(delayed_verify())
                
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
        
        # Explicitly remove from entity registry to ensure complete removal
        try:
            from homeassistant.helpers.entity_registry import async_get as get_entity_registry
            registry = get_entity_registry(self.hass)
            if registry and self.registry_entry:
                registry.async_remove(self.entity_id)
                LOGGER.debug("Entity %s explicitly removed from registry", self.entity_id)
        except Exception as err:
            LOGGER.error("Error removing entity from registry: %s", err)
            
    @callback
    def _handle_entity_removal(self, removed_entity_id: str) -> None:
        """Handle the removal of an entity."""
        LOGGER.debug("Entity removal notification received: %s, my id: %s", 
                   removed_entity_id, self._rule_id)
        
        # Check if this is our entity that's being removed
        if removed_entity_id == self._rule_id:
            LOGGER.info("Removing entity %s", self.entity_id)
            
            # Explicitly remove from entity registry first
            try:
                from homeassistant.helpers.entity_registry import async_get as get_entity_registry
                registry = get_entity_registry(self.hass)
                entity_id = self.entity_id
                
                # Schedule the removal for after current execution
                async def remove_entity():
                    try:
                        # First remove from the entity registry
                        if registry and registry.async_get(entity_id):
                            registry.async_remove(entity_id)
                            LOGGER.debug("Entity %s removed from registry", entity_id)
                        
                        # Force removal from Home Assistant through HA's API
                        try:
                            # Set the entity as unavailable first
                            self._attr_available = False
                            self.async_write_ha_state()
                            
                            # Use the async_remove method from Entity
                            await self.async_remove(force_remove=True)
                            LOGGER.info("Force-removed entity %s", entity_id)
                        except Exception as force_err:
                            LOGGER.error("Error during force-removal: %s", force_err)
                            
                    except Exception as err:
                        LOGGER.error("Error during entity removal: %s", err)
                        
                # Create task to run asynchronously
                self.hass.async_create_task(remove_entity())
            except Exception as err:
                LOGGER.error("Error during entity removal: %s", err)

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # Add update callbacks
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        
        # Also listen for specific events related to this entity
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, 
                f"{DOMAIN}_entity_update_{self._rule_id}", 
                self.async_schedule_update_ha_state
            )
        )
        
        # Listen for entity removal signals
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_entity_removed",
                self._handle_entity_removal
            )
        )
        
        # Listen for entity created events
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_entity_created",
                self._handle_entity_created
            )
        )
        
        # Listen for force cleanup signal
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ENTITIES_CLEANUP,
                self._handle_force_cleanup
            )
        )
        
        # Make sure the entity is properly registered in the entity registry
        try:
            from homeassistant.helpers.entity_registry import async_get as get_entity_registry
            registry = get_entity_registry(self.hass)
            
            # Log the entity registry state
            LOGGER.debug("Entity registry check - unique_id: %s, entity_id: %s", 
                      self.unique_id, self.entity_id)
            
            # Check if the entity already exists in the registry
            existing_entity = registry.async_get_entity_id("switch", DOMAIN, self.unique_id)
            
            if existing_entity:
                LOGGER.debug("Entity already exists in registry: %s", existing_entity)
                # Don't try to update the entity_id - this has been causing problems
                # Just force a state update to ensure it's current
                self.async_write_ha_state()
            else:
                # Register the entity with our consistent ID format
                try:
                    # Use the object_id from rule.py
                    object_id = get_object_id(self._rule_data, self._rule_type)
                    
                    entity_entry = registry.async_get_or_create(
                        "switch",
                        DOMAIN,
                        self.unique_id,
                        suggested_object_id=object_id,
                        # Don't set disabled_by to ensure it's enabled
                        disabled_by=None,
                    )
                    
                    if entity_entry:
                        LOGGER.info("Entity registered in registry: %s", entity_entry.entity_id)
                    else:
                        LOGGER.warning("Failed to register entity with registry")
                except Exception as reg_err:
                    LOGGER.warning("Could not register entity: %s", reg_err)
            
            # Force a state update to ensure it shows up
            self.async_write_ha_state()
        except Exception as err:
            LOGGER.error("Error during entity registration: %s", err)

    @callback
    def _handle_entity_created(self) -> None:
        """Handle entity created event."""
        LOGGER.debug("Entity created event received for %s", self.entity_id)
        
        # Force a state update
        self.async_write_ha_state()
        
        # Use a dispatcher instead of trying to call async_update_entity directly
        async_dispatcher_send(self.hass, f"{DOMAIN}_entity_update_{self.unique_id}")

    @callback
    def _handle_force_cleanup(self, _: Any = None) -> None:
        """Handle force cleanup signal."""
        LOGGER.debug("Force cleanup signal received for entity %s", self.entity_id)
        # Force an update to synchronize with latest data
        self.async_schedule_update_ha_state(True)

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