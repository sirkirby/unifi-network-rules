"""Switch platform for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Any, Final, Optional, Set
import time  # Add this import
import asyncio
import contextlib
import re
import copy

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
from homeassistant.exceptions import HomeAssistantError

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward
from aiounifi.models.firewall_zone import FirewallZone
from aiounifi.models.wlan import Wlan

from .const import DOMAIN, MANUFACTURER
from .coordinator import UnifiRuleUpdateCoordinator
from .helpers.rule import (
    get_rule_id, 
    get_rule_name, 
    get_rule_enabled,
    get_object_id, 
    get_child_entity_name, 
    get_child_unique_id, 
    get_child_entity_id,
    extract_descriptive_name
)
from .models.firewall_rule import FirewallRule  # Import FirewallRule
from .models.traffic_route import TrafficRoute  # Import TrafficRoute
from .models.qos_rule import QoSRule  # Import QoSRule
from .services.constants import SIGNAL_ENTITIES_CLEANUP

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1
RULE_TYPES: Final = {
    "firewall_policies": "Firewall Policy",
    "traffic_rules": "Traffic Rule",
    "port_forwards": "Port Forward",
    "traffic_routes": "Traffic Route",
    "legacy_firewall_rules": "Legacy Firewall Rule",
    "qos_rules": "QoS Rule"
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
    entity_registry = async_get_entity_registry(hass)

    # --- Step 1: Gather all potential entities and their data ---
    potential_entities_data = {} # Map: unique_id -> {rule_data, rule_type, entity_class}

    all_rule_sources = [
        ("port_forwards", coordinator.port_forwards, UnifiPortForwardSwitch),
        ("traffic_routes", coordinator.traffic_routes, UnifiTrafficRouteSwitch),
        ("firewall_policies", coordinator.firewall_policies, UnifiFirewallPolicySwitch),
        ("traffic_rules", coordinator.traffic_rules, UnifiTrafficRuleSwitch),
        ("legacy_firewall_rules", coordinator.legacy_firewall_rules, UnifiLegacyFirewallRuleSwitch),
        ("qos_rules", coordinator.data.get("qos_rules", []), UnifiQoSRuleSwitch),
        ("wlans", coordinator.wlans, UnifiWlanSwitch),
    ]

    for rule_type, rules, entity_class in all_rule_sources:
        if not rules: # Skip if no rules of this type
            continue
        for rule in rules:
            try:
                rule_id = get_rule_id(rule)
                if not rule_id:
                    LOGGER.error("Cannot process rule without ID: %s", rule)
                    continue

                # Add parent entity data if not already seen
                if rule_id not in potential_entities_data:
                    potential_entities_data[rule_id] = {
                        "rule_data": rule,
                        "rule_type": rule_type,
                        "entity_class": entity_class,
                    }
                    LOGGER.debug("Gathered potential entity: %s", rule_id)

                # Special handling for Traffic Routes: Add potential Kill Switch data
                if rule_type == "traffic_routes" and "kill_switch_enabled" in rule.raw:
                    kill_switch_id = get_child_unique_id(rule_id, "kill_switch")
                    if kill_switch_id not in potential_entities_data:
                        # Pass the PARENT rule data for the kill switch
                        potential_entities_data[kill_switch_id] = {
                            "rule_data": rule, # Use parent data
                            "rule_type": rule_type, # Still traffic_routes type
                            "entity_class": UnifiTrafficRouteKillSwitch,
                        }
                        LOGGER.debug("Gathered potential kill switch entity: %s (for parent %s)", kill_switch_id, rule_id)

            except Exception as err:
                LOGGER.exception("Error processing rule during gathering phase: %s", str(err))

    # --- Step 2: Create entity instances for unique IDs ---
    switches_to_add = []
    processed_unique_ids = set()

    LOGGER.debug("Creating entity instances from %d potential entities...", len(potential_entities_data))
    for unique_id, data in potential_entities_data.items():
        try:
            # Prevent duplicate processing if somehow gathered twice
            if unique_id in processed_unique_ids:
                 LOGGER.warning("Skipping already processed unique_id during instance creation: %s", unique_id)
                 continue

            # Create the entity instance
            entity_class = data["entity_class"]
            entity = entity_class(
                coordinator,
                data["rule_data"],
                data["rule_type"],
                config_entry.entry_id
            )

            # Check if the created entity's unique_id matches the key (sanity check)
            if entity.unique_id != unique_id:
                 LOGGER.error("Mismatch! Expected unique_id %s but created entity has %s. Skipping.", unique_id, entity.unique_id)
                 continue

            switches_to_add.append(entity)
            processed_unique_ids.add(unique_id)
            LOGGER.debug("Created entity instance for %s", unique_id)

        except Exception as err:
            LOGGER.exception("Error creating entity instance for unique_id %s: %s", unique_id, str(err))

    # --- Step 3: Add the uniquely created entities ---
    if switches_to_add:
        LOGGER.debug("Adding %d newly created entity instances to Home Assistant", len(switches_to_add))
        async_add_entities(switches_to_add)
        LOGGER.info("Added %d new UniFi Network Rules switches", len(switches_to_add))
    else:
        LOGGER.info("No new UniFi Network Rules switches to add in this run.")

# Helper function to create kill switch entities
async def create_traffic_route_kill_switch(hass, coordinator, rule, config_entry_id=None, return_entity=False):
    """Create a kill switch entity for a traffic route.
    
    This centralized function is used by both async_setup_entry and async_create_entity 
    to ensure consistent kill switch creation.
    
    Args:
        hass: The Home Assistant instance
        coordinator: The UnifiRuleUpdateCoordinator
        rule: The traffic route rule data
        config_entry_id: The config entry ID
        return_entity: Whether to return the created entity (for async_setup_entry)
        
    Returns:
        If return_entity is True, returns the created entity or None
        Otherwise, returns True if kill switch was created, False otherwise
    """
    # Check if this rule has kill switch support
    if not hasattr(rule, 'raw') or "kill_switch_enabled" not in rule.raw:
        return None if return_entity else False
        
    # Import necessary components
    from homeassistant.helpers.entity_registry import async_get as get_entity_registry
    import copy
    from .helpers.rule import get_child_unique_id, get_rule_id
    
    try:
        # Get the parent rule ID
        parent_rule_id = get_rule_id(rule)
        if not parent_rule_id:
            LOGGER.error("Cannot create kill switch - parent rule has no valid ID")
            return None if return_entity else False
            
        # Generate kill switch ID
        kill_switch_id = get_child_unique_id(parent_rule_id, "kill_switch")
        
        # Check if already exists in registry
        entity_registry = get_entity_registry(hass)
        existing_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, kill_switch_id)
        
        # Don't create if already created this session
        if kill_switch_id in _CREATED_UNIQUE_IDS:
            LOGGER.debug("Kill switch already created in this session: %s", kill_switch_id)
            # If it exists but we need to return it (e.g., for setup_entry linking)
            if return_entity:
                 # Attempt to find the existing entity instance? This is tricky.
                 # For now, returning None prevents duplicate creation attempt by setup_entry.
                 # Linking logic in setup_entry will handle finding existing entities later.
                 LOGGER.warning("Kill switch %s already created, returning None for setup_entry", kill_switch_id)
                 return None
            return False # Don't proceed if not returning entity

        # Create a copy of the rule for the kill switch
        rule_copy = copy.deepcopy(rule)

        # Create the kill switch entity - REMOVED parent_entity argument
        kill_switch = UnifiTrafficRouteKillSwitch(
            coordinator, rule_copy, "traffic_routes", config_entry_id
        )

        # Mark as created to prevent duplicates
        _CREATED_UNIQUE_IDS.add(kill_switch_id)

        # If called from setup_entry, just return the entity
        if return_entity:
            LOGGER.debug("Returning kill switch entity for setup_entry: %s", kill_switch_id)
            return kill_switch

        # Otherwise, add it to the platform
        platform = None
        # Ensure platform data structure exists before accessing
        if DOMAIN in hass.data and "platforms" in hass.data[DOMAIN] and "switch" in hass.data[DOMAIN]["platforms"]:
             platform = hass.data[DOMAIN]["platforms"]["switch"]

        # Add entity if platform is available
        if platform and hasattr(platform, 'async_add_entities'):
            parent_name_for_log = getattr(rule, 'name', parent_rule_id) # Get parent name if possible
            LOGGER.info("Creating kill switch entity for %s", parent_name_for_log)
            await platform.async_add_entities([kill_switch])
            return True
        else:
            LOGGER.error("Cannot create kill switch - switch platform unavailable or lacks async_add_entities method")
            # Clean up tracking if creation failed
            if kill_switch_id in _CREATED_UNIQUE_IDS:
                _CREATED_UNIQUE_IDS.remove(kill_switch_id)
            return False
    except Exception as err:
        LOGGER.error("Error creating kill switch entity: %s", err)
        # Clean up tracking on error
        kill_switch_id_on_error = get_child_unique_id(get_rule_id(rule), "kill_switch") if get_rule_id(rule) else None
        if kill_switch_id_on_error and kill_switch_id_on_error in _CREATED_UNIQUE_IDS:
            _CREATED_UNIQUE_IDS.remove(kill_switch_id_on_error)
        return None if return_entity else False

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
            
        # Get rule name using helper function - rely entirely on rule.py for naming
        # Pass coordinator to get_rule_name to enable zone name lookups for FirewallPolicy objects
        self._attr_name = get_rule_name(rule_data, coordinator) or f"Rule {self._rule_id}"
        
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
        self._optimistic_max_age = 5  # Maximum age in seconds for optimistic state
        self._operation_pending = False
        self._last_auth_failure_time = 0
        
        # Initialize linked entity tracking
        self._linked_parent_id = None  # Unique ID of parent entity, if any
        self._linked_child_ids = set()  # Set of unique IDs of child entities

        LOGGER.debug("Initialized entity instance for unique_id=%s, entity_id=%s",
                   self._attr_unique_id, self.entity_id)

    @property
    def linked_parent_id(self) -> Optional[str]:
        """Return the unique ID of the parent entity, if this is a child entity."""
        return self._linked_parent_id
        
    @property
    def linked_child_ids(self) -> Set[str]:
        """Return the set of unique IDs of child entities."""
        return self._linked_child_ids
        
    def register_child_entity(self, child_unique_id: str) -> None:
        """Register a child entity with this entity."""
        self._linked_child_ids.add(child_unique_id)
        LOGGER.debug("Registered child entity %s with parent %s", 
                   child_unique_id, self._attr_unique_id)
                   
    def register_parent_entity(self, parent_unique_id: str) -> None:
        """Register this entity as a child of the given parent."""
        self._linked_parent_id = parent_unique_id
        LOGGER.debug("Registered entity %s as child of %s", 
                   self._attr_unique_id, parent_unique_id)
                   
    @staticmethod
    def establish_parent_child_relationship(parent: 'UnifiRuleSwitch', child: 'UnifiRuleSwitch') -> None:
        """Establish bidirectional parent-child relationship between two entities.
        
        Args:
            parent: The parent entity
            child: The child entity
        """
        parent.register_child_entity(child.unique_id)
        child.register_parent_entity(parent.unique_id)
        LOGGER.debug("Established parent-child relationship: %s → %s", 
                   parent.entity_id, child.entity_id)

    def clear_optimistic_state(self, force: bool = False) -> None:
        """Clear the optimistic state if it exists.
        
        Args:
            force: If True, force clearing regardless of timestamp
        """
        if self._optimistic_state is not None:
            if force:
                LOGGER.debug("Forcibly clearing optimistic state for %s", self._rule_id)
                self._optimistic_state = None
                self._optimistic_timestamp = 0
                self._operation_pending = False
            else:
                current_time = time.time()
                age = current_time - self._optimistic_timestamp
                if age > self._optimistic_max_age:
                    LOGGER.debug("Clearing optimistic state for %s (age: %.1f seconds)",
                               self._rule_id, age)
                    self._optimistic_state = None
                    self._optimistic_timestamp = 0
                    self._operation_pending = False

    def mark_pending_operation(self, target_state: bool) -> None:
        """Mark that an operation is pending with a target state.
        
        Args:
            target_state: The target state (True for on, False for off)
        """
        self._optimistic_state = target_state
        self._optimistic_timestamp = time.time()
        self._operation_pending = True
        
    def handle_auth_failure(self) -> None:
        """Handle authentication failure by adjusting optimistic states."""
        # Record when this auth failure happened
        self._last_auth_failure_time = time.time()
        
        # Only retain optimistic state for a shorter period during auth failures
        if self._optimistic_state is not None:
            self._optimistic_max_age = 2  # Reduced maximum age during auth problems
            
        # Log that we're handling an auth failure for this entity
        LOGGER.debug("Handling auth failure for entity %s (current optimistic state: %s)",
                   self.entity_id, 
                   "on" if self._optimistic_state else "off" if self._optimistic_state is not None else "None")
        
        # Don't immediately clear optimistic state - let it expire naturally
        # This gives time for auth recovery to succeed

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Add entry log
        LOGGER.debug("%s(%s): Handling coordinator update.", type(self).__name__, self.entity_id or self.unique_id)

        if not self.coordinator or not self.coordinator.data:
            LOGGER.debug("%s(%s): Coordinator or coordinator data missing, skipping update.", type(self).__name__, self.entity_id or self.unique_id)
            return

        # Get the current rule from the coordinator data
        new_rule = self._get_current_rule()
        current_availability = new_rule is not None
        LOGGER.debug("%s(%s): Rule lookup result: %s. Availability: %s",
                     type(self).__name__, self.entity_id or self.unique_id,
                     "Found" if new_rule else "Not Found",
                     current_availability)

        if new_rule is not None:
            # Store the NEW rule data
            self._rule_data = new_rule

            # --- Optimistic State Handling ---
            if self._optimistic_state is not None:
                current_time = time.time()
                age = current_time - self._optimistic_timestamp
                max_age = self._optimistic_max_age

                # Check if optimistic state expired
                if age > max_age:
                    LOGGER.debug("%s(%s): Optimistic state expired (age: %.1fs > max: %ds).",
                               type(self).__name__, self.entity_id or self.unique_id, age, max_age)

                    # Get actual state from the NEW rule data
                    actual_state = self._get_actual_state_from_rule(new_rule)
                    LOGGER.debug("%s(%s): Actual state from new rule data: %s",
                              type(self).__name__, self.entity_id or self.unique_id, actual_state)

                    # Clear optimistic state only if actual state matches or is unknown
                    if self._optimistic_state == actual_state or actual_state is None:
                         LOGGER.debug("%s(%s): Clearing optimistic state (matches actual or actual is None).",
                                     type(self).__name__, self.entity_id or self.unique_id)
                         self.clear_optimistic_state(force=True) # Force clear here
                    else:
                        LOGGER.debug("%s(%s): State mismatch: optimistic=%s, actual=%s. Keeping optimistic state briefly.",
                                  type(self).__name__, self.entity_id or self.unique_id,
                                  self._optimistic_state, actual_state)
                        # Optionally slightly extend timestamp to give backend more time?
                        # self._optimistic_timestamp = current_time - (max_age - 1) # e.g., give 1 more sec
                # else: # Log commented out for brevity
                    # LOGGER.debug("%s(%s): Keeping optimistic state, only %.1f seconds elapsed (max %d)",
                    #           type(self).__name__, self.entity_id or self.unique_id, age, max_age)

            # Clear operation pending flag if not cleared by optimistic logic
            # This should happen *after* optimistic check clears state
            if self._operation_pending and self._optimistic_state is None:
                LOGGER.debug("%s(%s): Clearing pending operation flag as optimistic state is now None.",
                           type(self).__name__, self.entity_id or self.unique_id)
                self._operation_pending = False

        else:
            # --- Rule Not Found ---
            LOGGER.debug("%s(%s): Rule not found in coordinator data. Initiating removal.",
                       type(self).__name__, self.entity_id or self.unique_id)
            # Ensure internal data reflects disappearance
            self._rule_data = None
            # Clear any lingering optimistic state
            self.clear_optimistic_state(force=True)
            # Mark as unavailable immediately
            self._attr_available = False
            # Proactively trigger the removal process
            self.hass.async_create_task(self.async_initiate_self_removal())
            # Write state to reflect unavailability before removal completes
            self.async_write_ha_state()
            return # Exit early as the entity is being removed

        # Write the state AFTER processing coordinator update if not removing
        LOGGER.debug("%s(%s): Writing HA state after coordinator update.", type(self).__name__, self.entity_id or self.unique_id)
        self.async_write_ha_state()

    def _get_actual_state_from_rule(self, rule: Any) -> Optional[bool]:
        """Helper to get the actual state from a rule object, handling different types."""
        # Default implementation for most rules
        if hasattr(rule, 'enabled'):
            return getattr(rule, 'enabled')
        # Handle raw dict case if needed
        if isinstance(rule, dict) and 'enabled' in rule:
            return rule.get('enabled')
        LOGGER.warning("%s(%s): Could not determine actual state from rule object type %s",
                     type(self).__name__, self.entity_id or self.unique_id, type(rule).__name__)
        return None # Return None if state cannot be determined

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # If parent entity is linked, base availability on parent
        if self._linked_parent_id:
            # Find parent entity by unique ID
            parent_entity_id = None
            entity_registry = async_get_entity_registry(self.hass)
            if entity_registry:
                parent_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, self._linked_parent_id)

            if parent_entity_id:
                parent_state = self.hass.states.get(parent_entity_id)
                # Check if parent state exists and is not unavailable
                # Also check if the parent entity itself thinks it's available
                parent_is_available = parent_state and parent_state.state != "unavailable"
                if parent_is_available:
                    # Check the parent entity object's available property if possible
                    parent_entity = self.hass.data.get(DOMAIN, {}).get('entities', {}).get(parent_entity_id)
                    if parent_entity and hasattr(parent_entity, 'available'):
                        parent_is_truly_available = parent_entity.available
                        if not parent_is_truly_available:
                             LOGGER.debug("%s(%s): Parent entity %s state is available, but parent.available property is False.",
                                          type(self).__name__, self.entity_id or self.unique_id, parent_entity_id)
                             return False # If parent object says it's not available, we aren't either
                    # If we passed checks, return True
                    return True
                else:
                    # If parent state is unavailable or missing, we are unavailable
                     LOGGER.debug("%s(%s): Unavailable because linked parent %s state is unavailable or missing.",
                                  type(self).__name__, self.entity_id or self.unique_id, parent_entity_id)
                     return False

        # Standard availability check (if not a child or parent lookup failed)
        # An entity is available if the coordinator succeeded AND the rule exists in the data
        rule_exists = self._get_current_rule() is not None
        is_available = self.coordinator.last_update_success and rule_exists

        # Log if availability changes based on rule existence
        if self.coordinator.last_update_success and not rule_exists:
            LOGGER.debug("%s(%s): Determined unavailable because coordinator succeeded but rule is missing.",
                       type(self).__name__, self.entity_id or self.unique_id)
        elif not self.coordinator.last_update_success:
            LOGGER.debug("%s(%s): Determined unavailable due to coordinator last update failure.",
                       type(self).__name__, self.entity_id or self.unique_id)

        return is_available

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
        self.mark_pending_operation(enable)
        
        # Write state and force an update to ensure all clients receive it immediately
        self.async_write_ha_state()
        
        # Get the current rule object
        current_rule = self._get_current_rule()
        if current_rule is None:
            LOGGER.error("Rule not found in coordinator data: %s", self._rule_id)
            # Revert optimistic state
            self.mark_pending_operation(not enable)
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
                    self.mark_pending_operation(not enable)
                    self.async_write_ha_state()
                else:
                    # On success, refresh the optimistic state timestamp to prevent premature clearing
                    self._optimistic_timestamp = time.time()
                    self.async_write_ha_state()
                
                # Request refresh to update state from backend
                await self.coordinator.async_request_refresh()
                
                # Improve rapid toggling experience by reducing delay and adding direct updates
                if success:
                    async def delayed_verify():
                        # Reduced wait time for faster feedback
                        await asyncio.sleep(1)  # Reduced from 2 seconds
                        # Request refresh first
                        await self.coordinator.async_request_refresh()
                        # Force a state update immediately after refresh
                        self.async_write_ha_state()
                        # Also notify on a dispatcher channel for anyone listening
                        from homeassistant.helpers.dispatcher import async_dispatcher_send
                        async_dispatcher_send(self.hass, f"{DOMAIN}_entity_update_{self._rule_id}")
                        LOGGER.debug("Performed verification refresh for rule %s", self._rule_id)
                    
                    asyncio.create_task(delayed_verify())
                
            except Exception as err:
                # Check if this is an auth error
                error_str = str(err).lower()
                if "401 unauthorized" in error_str or "403 forbidden" in error_str:
                    LOGGER.warning("Authentication error in toggle operation for rule %s: %s", 
                                 self._rule_id, err)
                    # Report auth failure to handle it appropriately
                    self.handle_auth_failure()
                else:
                    LOGGER.error("Error in toggle operation for rule %s: %s", 
                                self._rule_id, err)
                
                # Revert optimistic state on error
                self.mark_pending_operation(not enable)
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
            elif self._rule_type == "qos_rules":
                toggle_func = self.coordinator.api.toggle_qos_rule
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
            self.mark_pending_operation(not enable)
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal from Home Assistant.
        
        If this is a parent entity, remove all linked child entities as well.
        """
        LOGGER.debug("Entity %s will be removed from Home Assistant", self.entity_id)
        
        # Clean up from global tracking
        global _CREATED_UNIQUE_IDS
        if self._attr_unique_id in _CREATED_UNIQUE_IDS:
            _CREATED_UNIQUE_IDS.remove(self._attr_unique_id)
            
        # If this entity has child entities, remove them as well
        if self._linked_child_ids:
            LOGGER.debug("Removing %d child entities of %s", 
                       len(self._linked_child_ids), self.entity_id)
                       
            # Get entity registry to find children
            entity_registry = async_get_entity_registry(self.hass)
            
            # For each child, remove it from HA
            for child_id in self._linked_child_ids:
                # Find entity ID in registry using unique_id
                entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, child_id)
                if entity_id:
                    LOGGER.debug("Removing child entity %s (unique_id: %s)", 
                               entity_id, child_id)
                    entity_registry.async_remove(entity_id)
                    # Remove from global tracking
                    if child_id in _CREATED_UNIQUE_IDS:
                        _CREATED_UNIQUE_IDS.remove(child_id)
                        
        # Call parent method
        await super().async_will_remove_from_hass()

    @callback
    def _handle_entity_removal(self, removed_entity_id: str) -> None:
        """Handle the removal of an entity via dispatcher signal."""
        # This function is primarily for reacting to EXTERNAL removal signals.
        # Proactive removal initiated by _handle_coordinator_update uses async_initiate_self_removal.
        if removed_entity_id != self._rule_id:
            # LOGGER.debug("Ignoring removal signal for %s (not matching %s)", removed_entity_id, self._rule_id)
            return

        LOGGER.info("Received external removal signal for entity %s (%s). Initiating cleanup.",
                   self.entity_id, self._rule_id)
        # Avoid duplicate removal if already initiated
        if getattr(self, '_removal_initiated', False):
             LOGGER.debug("Removal already initiated for %s, skipping signal handler.", self.entity_id)
             return

        # Initiate removal asynchronously
        self.hass.async_create_task(self.async_initiate_self_removal())

    async def async_initiate_self_removal(self) -> None:
        """Proactively remove this entity and its children from Home Assistant."""
        if getattr(self, '_removal_initiated', False):
            LOGGER.debug("Removal already in progress for %s.", self.entity_id)
            return

        LOGGER.info("Initiating self-removal for entity %s (%s)", self.entity_id, self._attr_unique_id)
        self._removal_initiated = True # Set flag to prevent loops

        entity_registry = async_get_entity_registry(self.hass)

        # 1. Remove Child Entities
        if self._linked_child_ids:
            LOGGER.debug("Removing %d child entities of %s", len(self._linked_child_ids), self.entity_id)
            children_to_remove = list(self._linked_child_ids) # Copy ids before iterating/modifying
            for child_unique_id in children_to_remove:
                child_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, child_unique_id)
                if child_entity_id:
                    # Look up child entity instance from hass.data
                    child_entity = self.hass.data.get(DOMAIN, {}).get('entities', {}).get(child_entity_id)
                    try:
                        if child_entity and hasattr(child_entity, 'async_initiate_self_removal'):
                            # Ask child to remove itself (handles its own children if any)
                            LOGGER.debug("Requesting child %s (%s) to initiate self-removal.", child_entity_id, child_unique_id)
                            await child_entity.async_initiate_self_removal()
                        else:
                            # Fallback: Directly remove from registry if entity object not found or method missing
                            LOGGER.debug("Removing child %s (%s) directly from registry (object or method missing).", child_entity_id, child_unique_id)
                            if entity_registry.async_get(child_entity_id):
                                entity_registry.async_remove(child_entity_id)
                        # Remove from parent's list after attempting removal
                        if child_unique_id in self._linked_child_ids:
                             self._linked_child_ids.remove(child_unique_id)
                        # Clean up global tracking for child
                        if child_unique_id in _CREATED_UNIQUE_IDS:
                             _CREATED_UNIQUE_IDS.remove(child_unique_id)
                    except Exception as child_err:
                        LOGGER.error("Error removing child entity %s (%s): %s", child_entity_id, child_unique_id, child_err)
                else:
                    LOGGER.debug("Child entity with unique_id %s not found in registry for removal.", child_unique_id)
                    # Clean up global tracking even if not in registry
                    if child_unique_id in _CREATED_UNIQUE_IDS:
                         _CREATED_UNIQUE_IDS.remove(child_unique_id)
                    # Remove from parent's list
                    if child_unique_id in self._linked_child_ids:
                         self._linked_child_ids.remove(child_unique_id)


        # 2. Remove Self from Global Tracking
        if self._attr_unique_id in _CREATED_UNIQUE_IDS:
            LOGGER.debug("Removing self (%s) from global _CREATED_UNIQUE_IDS.", self._attr_unique_id)
            _CREATED_UNIQUE_IDS.remove(self._attr_unique_id)

        # 3. Remove Self from Entity Registry
        if self.entity_id and entity_registry.async_get(self.entity_id):
            LOGGER.debug("Removing self (%s) from entity registry.", self.entity_id)
            try:
                entity_registry.async_remove(self.entity_id)
            except Exception as reg_err:
                LOGGER.error("Error removing entity %s from registry: %s", self.entity_id, reg_err)

        # 4. Final HA Cleanup (Optional but recommended)
        # This tells HA core to perform its internal cleanup for the entity
        try:
            LOGGER.debug("Calling async_remove for %s.", self.entity_id)
            # Ensure the entity is marked unavailable before final removal
            self._attr_available = False
            self.async_write_ha_state()
            await self.async_remove(force_remove=True)
            LOGGER.info("Successfully completed removal steps for %s.", self.entity_id)
        except Exception as remove_err:
            # Log expected errors during removal less severely
            if isinstance(remove_err, HomeAssistantError) and "Entity not found" in str(remove_err):
                LOGGER.debug("Entity %s already removed from HA core.", self.entity_id)
            else:
                LOGGER.error("Error during final async_remove for %s: %s", self.entity_id, remove_err)

        # 5. Cleanup internal references (if any)
        # Example: remove from a central entity dictionary if used
        entity_dict = self.hass.data.get(DOMAIN, {}).get('entities', {})
        if self.entity_id in entity_dict:
             del entity_dict[self.entity_id]
             LOGGER.debug("Removed %s from internal entity tracking.", self.entity_id)

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # Store entity in a central place for easy lookup (e.g., by parent/child logic)
        if DOMAIN not in self.hass.data:
            self.hass.data[DOMAIN] = {}
        if 'entities' not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN]['entities'] = {}
        self.hass.data[DOMAIN]['entities'][self.entity_id] = self
        LOGGER.debug("Stored entity %s in hass.data[%s]['entities']", self.entity_id, DOMAIN)

        # ADDED: Perform global unique ID tracking here
        global _CREATED_UNIQUE_IDS
        if self.unique_id in _CREATED_UNIQUE_IDS:
             # This case should ideally not happen if setup_entry filtering works,
             # but log if it does.
             LOGGER.warning("Entity %s added to HASS, but unique_id %s was already tracked.", 
                            self.entity_id, self.unique_id)
        else:
             _CREATED_UNIQUE_IDS.add(self.unique_id)
             LOGGER.debug("Added unique_id %s to global tracking upon adding entity %s to HASS.",
                          self.unique_id, self.entity_id)

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
        
        # Listen for authentication failure events
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_auth_failure",
                self._handle_auth_failure_event
            )
        )
        
        # Listen for authentication restored events
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_auth_restored",
                self._handle_auth_restored_event
            )
        )
        
        # Listen for entity removal signals - use targeted signal first
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_entity_removed_{self._rule_id}",
                lambda _: self._handle_entity_removal(self._rule_id)
            )
        )
        
        # Also listen for general removal signal for backward compatibility
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
    def _handle_auth_failure_event(self, _: Any = None) -> None:
        """Handle authentication failure event."""
        LOGGER.debug("Authentication failure event received for entity %s", self.entity_id)
        
        # Track the auth failure time
        self._last_auth_failure_time = time.time()
        
        # Notify the entity to handle auth failure appropriately
        self.handle_auth_failure()
        
        # Force a state update to reflect any changes
        self.async_write_ha_state()
        
    @callback
    def _handle_auth_restored_event(self, _: Any = None) -> None:
        """Handle authentication restored event."""
        LOGGER.debug("Authentication restored event received for entity %s", self.entity_id)
        
        # Reset auth failure time
        self._last_auth_failure_time = 0
        
        # Reset optimistic max age to normal
        self._optimistic_max_age = 5
        
        # If we have an operation pending and optimistic state is set, keep it longer
        # to allow time for the next refresh to verify state
        if self._operation_pending and self._optimistic_state is not None:
            self._optimistic_timestamp = time.time()
            LOGGER.debug("Refreshed optimistic state timestamp due to auth restoration")
        else:
            # No operations pending, clear any lingering optimistic state
            self.clear_optimistic_state()
        
        # Force an update
        self.async_schedule_update_ha_state(True)

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

class UnifiTrafficRouteKillSwitch(UnifiRuleSwitch):
    """Switch to enable/disable kill switch for a UniFi traffic route rule."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize traffic route kill switch using super() and overriding."""
        # 1. Initialize using the base class with the PARENT rule data.
        # The base __init__ will set initial name, unique_id etc based on the parent.
        super().__init__(coordinator, rule_data, "traffic_routes", entry_id)

        # 2. Determine Parent and Kill Switch IDs
        original_rule_id = get_rule_id(rule_data) # Parent unique ID (e.g., unr_route_xyz)
        if not original_rule_id:
             raise ValueError("KillSwitch init: Cannot determine original rule ID from rule data")
        kill_switch_id = get_child_unique_id(original_rule_id, "kill_switch")

        # 3. Override attributes for the Kill Switch
        self._rule_id = kill_switch_id        # Internal ID used by this instance
        self._attr_unique_id = kill_switch_id # The unique ID for HA (OVERRIDE)

        # Override name based on the name generated by super()
        # Ensure super() set a name before modifying
        if self._attr_name:
             self._attr_name = get_child_entity_name(self._attr_name, "kill_switch") # OVERRIDE
        else:
             # Fallback name if super init failed to set one
             fallback_parent_name = extract_descriptive_name(rule_data, coordinator) or original_rule_id
             self._attr_name = get_child_entity_name(fallback_parent_name, "kill_switch")

        # Override entity_id based on the object_id generated by super()
        # Note: get_object_id uses rule_data (parent), which is correct base
        parent_object_id = get_object_id(rule_data, "traffic_routes")
        kill_switch_object_id = get_child_entity_id(parent_object_id, "kill_switch")
        self.entity_id = generate_entity_id(
            f"{DOMAIN}.{{}}", kill_switch_object_id, hass=coordinator.hass # OVERRIDE
        )

        # 4. Initialize kill switch state specifically
        # (Optimistic state handling is managed by base class, but we set initial value)
        self._optimistic_state = None
        self._optimistic_timestamp = 0
        if hasattr(rule_data, 'raw') and "kill_switch_enabled" in rule_data.raw:
            actual_state = rule_data.raw.get("kill_switch_enabled", False)
            self._optimistic_state = actual_state # Start optimistic state matching actual
            self._optimistic_timestamp = time.time()
            LOGGER.debug("KillSwitch %s: Initialized specific state to %s from parent rule data",
                         self.unique_id, actual_state)
        else:
             LOGGER.warning("KillSwitch %s: Initialized without specific state from rule data.", self.unique_id)

        # 5. Linking Information (Parent ID needed for lookups)
        self._linked_parent_id = original_rule_id # Store parent's unique_id
        self._linked_child_ids = set() # Kill switches have no children

        # Global tracking is now handled in base async_added_to_hass

        LOGGER.debug("Finished KillSwitch __init__ for unique_id=%s, entity_id=%s",
                   self._attr_unique_id, self.entity_id)

    def _get_actual_state_from_rule(self, rule: Any) -> Optional[bool]:
        """Helper to get the actual kill switch state from the PARENT rule object."""
        if rule is None:
            LOGGER.debug("KillSwitch(%s): Cannot get state, parent rule object is None.", self.entity_id or self.unique_id)
            return None

        # Check if the rule has the kill_switch_enabled attribute in raw data
        if hasattr(rule, 'raw') and isinstance(rule.raw, dict):
            state = rule.raw.get("kill_switch_enabled") # Use .get() for safety
            if state is not None:
                 # LOGGER.debug("KillSwitch(%s): Got state '%s' from rule.raw['kill_switch_enabled']", self.entity_id or self.unique_id, state)
                 return state
            # else:
                 # LOGGER.debug("KillSwitch(%s): 'kill_switch_enabled' not found in rule.raw dict.", self.entity_id or self.unique_id)

        # Fallback: Check direct attribute if raw doesn't have it
        if hasattr(rule, 'kill_switch_enabled'):
            state = getattr(rule, 'kill_switch_enabled')
            # LOGGER.debug("KillSwitch(%s): Got state '%s' from rule.kill_switch_enabled attribute.", self.entity_id or self.unique_id, state)
            return state

        LOGGER.warning("KillSwitch(%s): Cannot determine actual state from parent rule object %s (type: %s)",
                     self.entity_id or self.unique_id, getattr(rule, 'id', 'N/A'), type(rule).__name__)
        return None # Return None if state cannot be determined

    def _get_current_rule(self) -> Any | None:
        """Get the current rule from the coordinator data.

        This special implementation handles finding the parent route for kill switches.
        """
        # Extract parent ID for kill switch
        rule_id = self._rule_id # This is the kill switch's unique_id (e.g., unr_route_abc_kill_switch)
        parent_rule = None # Initialize parent_rule
        
        if rule_id and rule_id.endswith('_kill_switch'):
            parent_id = rule_id[:-12]  # Remove '_kill_switch' suffix (e.g., unr_route_abc)
            parent_raw_id = parent_id.replace('unr_route_', '')  # Extract raw ID without prefix (e.g., abc)

            # Add detailed logging
            LOGGER.debug("KillSwitch(%s): Looking for parent rule with raw ID: '%s'", self.entity_id or rule_id, parent_raw_id)

            # Find the parent route in the coordinator data
            # Ensure coordinator and data dictionary exist
            if self.coordinator and self.coordinator.data and "traffic_routes" in self.coordinator.data:
                traffic_routes = self.coordinator.data["traffic_routes"]
                # Log available routes only if lookup might fail or for detailed debugging
                # available_ids = [getattr(r, 'id', None) for r in traffic_routes]
                # LOGGER.debug("KillSwitch(%s): Available parent traffic route IDs: %s", self.entity_id or rule_id, available_ids)

                found = False
                for rule in traffic_routes:
                    current_rule_id = getattr(rule, 'id', None)
                    if current_rule_id == parent_raw_id:
                        # Log success
                        LOGGER.debug("KillSwitch(%s): Found parent rule object with ID: %s", self.entity_id or rule_id, rule.id)
                        parent_rule = rule
                        found = True
                        break # Exit loop once found
                
                if not found:
                    # Log failure
                    LOGGER.debug("KillSwitch(%s): Parent rule with raw ID '%s' not found in coordinator traffic_routes list (count: %d).", 
                               self.entity_id or rule_id, parent_raw_id, len(traffic_routes))
            else:
                # Log reason for not searching
                reason = "coordinator data missing" if not self.coordinator.data else "traffic_routes missing from data"
                LOGGER.debug("KillSwitch(%s): Cannot search for parent rule - %s.", self.entity_id or rule_id, reason)
            
            # Return the found parent rule or None
            return parent_rule
            
        else:
             # Log if rule_id is invalid or not a kill switch
             LOGGER.warning("KillSwitch(%s): Invalid rule_id '%s' for parent lookup.", self.entity_id or self._rule_id, rule_id)
             # Fallback to parent class implementation might be needed if this class is misused
             # return super()._get_current_rule() 
             return None # Explicitly return None if not a valid kill switch ID pattern

    @property
    def is_on(self) -> bool:
        """Return true if kill switch is enabled."""
        # Use optimistic state if set
        if self._optimistic_state is not None:
            return self._optimistic_state
            
        current_rule = self._get_current_rule()
        if current_rule is None:
            return False
            
        # Check if the rule has the kill_switch_enabled attribute
        if hasattr(current_rule, 'raw') and isinstance(current_rule.raw, dict):
            return current_rule.raw.get("kill_switch_enabled", False)
            
        # If the rule doesn't have the attribute, check if it has a direct kill_switch_enabled property
        if hasattr(current_rule, 'kill_switch_enabled'):
            return getattr(current_rule, 'kill_switch_enabled')
            
        # As a last resort, default to False
        LOGGER.warning("Kill switch %s cannot determine state from rule %s", 
                    self._rule_id, type(current_rule).__name__)
        return False
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Add log at the very start
        LOGGER.debug("KillSwitch(%s): Evaluating available property...", self.entity_id or self.unique_id)
        
        # Start with coordinator status
        coord_ok = self.coordinator.last_update_success
        if not coord_ok:
            LOGGER.debug("KillSwitch(%s): Unavailable due to coordinator failure.", self.entity_id or self.unique_id)
            return False

        # Now check if the parent rule exists in the coordinator's data
        parent_rule = self._get_current_rule()
        is_available = parent_rule is not None

        # Log the availability status, especially if it's False
        if not is_available:
             LOGGER.debug("KillSwitch(%s): Determined unavailable because parent rule lookup failed.", self.entity_id or self.unique_id)
        else:
             # Optionally log when available too, but can be noisy
             LOGGER.debug("KillSwitch(%s): Determined available (parent rule found).", self.entity_id or self.unique_id)

        return is_available

    async def _async_toggle_rule(self, enable: bool) -> None:
        """Toggle the kill switch setting."""
        rule = self._get_current_rule()
        if rule is None:
            raise HomeAssistantError(f"Cannot find rule with ID: {self._rule_id}")

        LOGGER.debug("%s kill switch for %s", "Enabling" if enable else "Disabling", self.name)
        
        # Store current state for optimistic updates
        self._optimistic_state = enable
        self._optimistic_timestamp = time.time()
        self.async_write_ha_state()
        
        # Track the operation in coordinator for proper state management
        if hasattr(self.coordinator, "_pending_operations"):
            # Use a special key for kill switch operations to avoid conflicts with parent
            kill_switch_operation_id = f"{self._rule_id}_kill_switch"
            self.coordinator._pending_operations[kill_switch_operation_id] = enable
        
        # Queue the toggle operation
        try:
            # Get the toggle function from the API client
            toggle_func = self.coordinator.api.toggle_traffic_route_kill_switch
            
            # Queue the operation using the coordinator's queue method
            future = await self.coordinator.api.queue_api_operation(toggle_func, rule)
            
            async def handle_operation_complete(future):
                """Handle the completion of the toggle operation."""
                try:
                    result = future.result()
                    if result:
                        LOGGER.debug("Successfully toggled kill switch for %s", self.name)
                        # Request a data update
                        await self.coordinator.async_request_refresh()
                    else:
                        LOGGER.error("Failed to toggle kill switch for %s", self.name)
                        # Revert optimistic state on failure
                        self._optimistic_state = not enable
                        self._optimistic_timestamp = time.time()
                        self.async_write_ha_state()
                    
                    # Clean up pending operations
                    if hasattr(self.coordinator, "_pending_operations"):
                        kill_switch_operation_id = f"{self._rule_id}_kill_switch"
                        if kill_switch_operation_id in self.coordinator._pending_operations:
                            del self.coordinator._pending_operations[kill_switch_operation_id]
                        
                except Exception as err:
                    LOGGER.error("Error in kill switch toggle operation: %s", str(err))
                
                    # Revert optimistic state on error
                    self._optimistic_state = not enable
                    self._optimistic_timestamp = time.time()
                    self.async_write_ha_state()
            
            # Add the completion callback
            future.add_done_callback(
                lambda f: self.hass.async_create_task(handle_operation_complete(f))
            )
            
            LOGGER.debug("Successfully queued kill switch toggle operation for rule %s", self._rule_id)
            
        except Exception as error:
            LOGGER.exception("Failed to queue kill switch toggle operation: %s", str(error))
            
            # Clean up pending operations if queuing failed
            if hasattr(self.coordinator, "_pending_operations"):
                kill_switch_operation_id = f"{self._rule_id}_kill_switch"
                if kill_switch_operation_id in self.coordinator._pending_operations:
                    del self.coordinator._pending_operations[kill_switch_operation_id]
            
            # Revert optimistic state
            self._optimistic_state = not enable
            self._optimistic_timestamp = time.time()
            self.async_write_ha_state()
            
            raise HomeAssistantError(f"Error toggling kill switch for {self.name}: {error}")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        This method now relies entirely on the base class implementation.
        The base class handles:
        - Checking coordinator/data validity.
        - Calling _get_current_rule() (which finds the parent for KillSwitch).
        - Initiating removal if the parent rule is not found.
        - Handling optimistic state based on _get_actual_state_from_rule().
        - Writing HA state.
        """
        # Add entry log specific to KillSwitch for clarity
        LOGGER.debug("KillSwitch(%s): Delegating coordinator update handling to base class.", self.entity_id or self.unique_id)
        # Call the base class implementation directly
        super()._handle_coordinator_update()

# Define QoS rule switch class
class UnifiQoSRuleSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi QoS rule."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize QoS rule switch."""
        LOGGER.info("Initializing QoS rule switch with data: %s (type: %s)", 
                  getattr(rule_data, "id", "unknown"), type(rule_data).__name__)
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        # Add any QoS-rule specific functionality here