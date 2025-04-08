"""Switch platform for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Any, Final, Optional, Set, Dict
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
from .models.qos_rule import QoSRule
from .models.vpn_config import VPNConfig
from .services.constants import SIGNAL_ENTITIES_CLEANUP

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1
RULE_TYPES: Final = {
    "firewall_policies": "Firewall Policy",
    "traffic_rules": "Traffic Rule",
    "port_forwards": "Port Forward",
    "traffic_routes": "Traffic Route",
    "legacy_firewall_rules": "Legacy Firewall Rule",
    "qos_rules": "QoS Rule",
    "vpn_clients": "VPN Client",
    "vpn_servers": "VPN Server"
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

    coordinator: UnifiRuleUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    entity_registry = async_get_entity_registry(hass)

    # --- Initialize known_unique_ids from registry --- 
    coordinator.known_unique_ids = { 
        entry.unique_id 
        for entry in entity_registry.entities.values() # Iterate through values 
        if entry.config_entry_id == config_entry.entry_id # Filter by config entry ID
        and entry.domain == "switch" 
        and entry.platform == DOMAIN 
        and entry.unique_id
    }
    # LOGGER.debug("Initialized known_unique_ids from registry (count: %d): %s", len(coordinator.known_unique_ids), sorted(list(coordinator.known_unique_ids))) # ADDED detailed log
    LOGGER.debug("Initialized known_unique_ids from registry: %d entries", len(coordinator.known_unique_ids))
    
    # --- Trigger an immediate refresh after initial known_ids population ---
    # This ensures the first deletion check runs with IDs from the registry
    await coordinator.async_request_refresh()
    LOGGER.debug("Requested coordinator refresh after switch setup")

    # Initialize as empty, coordinator will manage it
    # if not hasattr(coordinator, 'known_unique_ids'): # Initialize only if it doesn't exist (e.g. first load)
    #     coordinator.known_unique_ids = set()
    # Do NOT clear on reload, let coordinator handle sync

    # --- Store add_entities callback --- 
    coordinator.async_add_entities_callback = async_add_entities

    # --- Step 1: Gather all potential entities and their data ---
    potential_entities_data = {} # Map: unique_id -> {rule_data, rule_type, entity_class}

    all_rule_sources = [
        ("port_forwards", coordinator.port_forwards, UnifiPortForwardSwitch),
        ("traffic_routes", coordinator.traffic_routes, UnifiTrafficRouteSwitch),
        ("firewall_policies", coordinator.firewall_policies, UnifiFirewallPolicySwitch),
        ("traffic_rules", coordinator.traffic_rules, UnifiTrafficRuleSwitch),
        ("legacy_firewall_rules", coordinator.legacy_firewall_rules, UnifiLegacyFirewallRuleSwitch),
        ("qos_rules", coordinator.qos_rules, UnifiQoSRuleSwitch),
        ("wlans", coordinator.wlans, UnifiWlanSwitch),
        ("vpn_clients", coordinator.vpn_clients, UnifiVPNClientSwitch),
        ("vpn_servers", coordinator.vpn_servers, UnifiVPNServerSwitch),
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

        # --- Update coordinator's known IDs --- 
        # Let the coordinator update known_unique_ids when dynamically adding
        # This prevents adding IDs during initial setup that might already be known from registry
        pass 

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

            # Clear operation pending flag if not cleared by optimistic logic
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
            # Proactively trigger the removal process - This is already in the event loop
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
                parent_state_available = parent_state and parent_state.state != "unavailable"

                parent_is_available = parent_state_available
                if parent_is_available:
                    # Check the parent entity object's available property if possible
                    parent_entity = self.hass.data.get(DOMAIN, {}).get(DOMAIN, {}).get(parent_entity_id)
                    if parent_entity and hasattr(parent_entity, 'available'):
                        try:
                            # Use a flag to prevent infinite recursion if parent also checks child
                            if getattr(self, '_checking_parent_availability', False):
                                 parent_is_truly_available = True # Assume true to break loop
                            else:
                                 setattr(parent_entity, '_checking_parent_availability', True)
                                 parent_is_truly_available = parent_entity.available
                                 delattr(parent_entity, '_checking_parent_availability')
                            if not parent_is_truly_available:
                                 return False # If parent object says it's not available, we aren't either
                        except Exception as e:
                             LOGGER.warning("%s(%s): Error checking parent entity availability property: %s", 
                                           type(self).__name__, self.entity_id, e)
                    return True
                else:
                     return False

        # Standard availability check (if not a child or parent lookup failed)
        coord_success = self.coordinator.last_update_success
        current_rule = self._get_current_rule()
        rule_exists = current_rule is not None
        is_available = coord_success and rule_exists

        return is_available

    @property
    def is_on(self) -> bool:
        """Return the enabled state of the rule."""
        # Use optimistic state if set
        if self._optimistic_state is not None:
            return self._optimistic_state

        rule = self._get_current_rule()
        if rule is None:
            # Add log for debugging is_on when rule is None
            # entity_id_for_log = self.entity_id or self.unique_id
            # LOGGER.debug("%s(%s): is_on check - rule is None, returning False.", type(self).__name__, entity_id_for_log)
            return False

        return get_rule_enabled(rule)

    @property
    def assumed_state(self) -> bool:
        """Return True as we're implementing optimistic state."""
        return True

    def _get_current_rule(self) -> Any | None:
        """Get current rule data from coordinator."""
        try:
            if not self.coordinator or not self.coordinator.data or self._rule_type not in self.coordinator.data:
                return None

            rules = self.coordinator.data.get(self._rule_type, [])
            
            found_rule = None
            for rule in rules:
                current_rule_id = get_rule_id(rule)
                if current_rule_id == self._rule_id:
                    found_rule = rule
                    break # Exit loop once found

            return found_rule
        except Exception as err:
            LOGGER.error("%s(%s): Error getting rule data in _get_current_rule: %s", 
                        type(self).__name__, self.entity_id or self._rule_id, err)
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
            elif self._rule_type == "vpn_clients":
                toggle_func = self.coordinator.api.toggle_vpn_client
            elif self._rule_type == "vpn_servers":
                toggle_func = self.coordinator.api.toggle_vpn_server
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
        """Handle entity cleanup when removed from Home Assistant."""
        LOGGER.debug("Entity %s cleaning up before removal from Home Assistant", self.entity_id)

        # Clean up internal entity tracking dictionary
        entity_dict = self.hass.data.get(DOMAIN, {}).get('entities', {})
        if self.entity_id in entity_dict:
            del entity_dict[self.entity_id]
            LOGGER.debug("Removed %s from internal entity tracking.", self.entity_id)

        # Clean up global _CREATED_UNIQUE_IDS set (if still used)
        global _CREATED_UNIQUE_IDS
        _CREATED_UNIQUE_IDS.discard(self._attr_unique_id) # Use discard for safety

        # IMPORTANT: Call super().async_will_remove_from_hass() LAST
        # This ensures base class cleanup (like removing listeners registered with self.async_on_remove) happens.
        await super().async_will_remove_from_hass()
        LOGGER.debug("Finished async_will_remove_from_hass for %s", self.entity_id)

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

        # Initiate removal asynchronously in a thread-safe way
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            self.async_initiate_self_removal()
        )

    async def async_initiate_self_removal(self) -> None:
        """Proactively remove this entity and its children from Home Assistant."""
        global _CREATED_UNIQUE_IDS
        entity_id_for_log = self.entity_id or self._attr_unique_id

        if getattr(self, '_removal_initiated', False):
            return

        self._removal_initiated = True # Set flag to prevent loops

        entity_registry = async_get_entity_registry(self.hass)

        # 0. Always remove from coordinator known_unique_ids first to prevent recreation
        if hasattr(self.coordinator, 'known_unique_ids'):
            self.coordinator.known_unique_ids.discard(self._attr_unique_id)

        # Also remove from global tracking set immediately
        _CREATED_UNIQUE_IDS.discard(self._attr_unique_id)

        # 1. Remove Child Entities RECURSIVELY
        if self._linked_child_ids:
            children_to_remove = list(self._linked_child_ids)
            for child_unique_id in children_to_remove:
                child_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, child_unique_id)
                child_entity = None
                if child_entity_id:
                    # Look up child entity instance from hass.data
                    child_entity = self.hass.data.get(DOMAIN, {}).get('entities', {}).get(child_entity_id)

                if child_entity and hasattr(child_entity, 'async_initiate_self_removal'):
                    try:
                        await child_entity.async_initiate_self_removal()
                    except Exception as child_err:
                        LOGGER.error("%s(%s): Error requesting self-removal for child entity %s (%s): %s",
                                     type(self).__name__, entity_id_for_log, child_entity_id or child_unique_id, child_unique_id, child_err)
                else:
                    # Fallback: Child object not found or doesn't have the method. Remove directly from registry.
                    if child_entity_id and entity_registry.async_get(child_entity_id):
                        try:
                            entity_registry.async_remove(child_entity_id)
                        except Exception as reg_rem_err:
                            LOGGER.error("%s(%s): Error removing child %s from registry directly: %s",
                                         type(self).__name__, entity_id_for_log, child_entity_id, reg_rem_err)
                    # Also clean up tracking even if registry removal fails or wasn't needed
                    if hasattr(self.coordinator, 'known_unique_ids'):
                        self.coordinator.known_unique_ids.discard(child_unique_id)
                    _CREATED_UNIQUE_IDS.discard(child_unique_id) # Use discard

                # Remove from parent's list regardless of success/failure of child removal
                self._linked_child_ids.discard(child_unique_id)

        # 3. Remove Self from Entity Registry and HA Core
        entity_id_to_remove = self.entity_id # Store current entity_id for logging
        LOGGER.debug("%s(%s): Preparing to call self.async_remove(force_remove=True) for entity_id: %s",
                     type(self).__name__, entity_id_for_log, entity_id_to_remove)
        try:
            await self.async_remove(force_remove=True)
            LOGGER.info("%s(%s): Successfully completed self.async_remove() for entity_id: %s.",
                         type(self).__name__, entity_id_for_log, entity_id_to_remove)
        except Exception as remove_err:
            # Log expected errors during removal less severely
            if isinstance(remove_err, HomeAssistantError) and "Entity not found" in str(remove_err):
                LOGGER.debug("%s(%s): Entity %s already removed from HA core.",
                             type(self).__name__, entity_id_for_log, entity_id_to_remove)
            else:
                LOGGER.error("%s(%s): Error during final async_remove for entity_id %s: %s",
                             type(self).__name__, entity_id_for_log, entity_id_to_remove, remove_err)
                LOGGER.exception("%s(%s): Exception during async_remove for entity_id %s:",
                                 type(self).__name__, entity_id_for_log, entity_id_to_remove)

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        global _CREATED_UNIQUE_IDS  # Add global declaration here

        await super().async_added_to_hass()

        # Store entity in a central place for easy lookup (e.g., by parent/child logic)
        if DOMAIN not in self.hass.data:
            self.hass.data[DOMAIN] = {}
        if 'entities' not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN]['entities'] = {}
        self.hass.data[DOMAIN]['entities'][self.entity_id] = self
        LOGGER.debug("Stored entity %s in hass.data[%s]['entities']", self.entity_id, DOMAIN)

        # ADDED: Perform global unique ID tracking here
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

        # --- Ensure initial state is based on current coordinator data --- 
        # LOGGER.debug("%s(%s): Explicitly calling _handle_coordinator_update in async_added_to_hass.",
        #              type(self).__name__, self.entity_id or self.unique_id)
        # self._handle_coordinator_update() # REMOVED - Process current data before first write

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
                # self.async_write_ha_state() # Moved lower
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

            # Force a state update to ensure it shows up AFTER potentially registering
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
            "switch.{}", kill_switch_object_id, hass=coordinator.hass # OVERRIDE
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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        This method delegates to the base class implementation.
        The base class handles all the necessary logic:
        - Checking coordinator data validity
        - Finding the parent rule using our specialized _get_current_rule method
        - Handling optimistic state management
        - Triggering removal if the parent rule is missing
        """
        LOGGER.debug("KillSwitch(%s): Delegating coordinator update to base class", self.entity_id or self.unique_id)
        super()._handle_coordinator_update()
        
    def _get_actual_state_from_rule(self, rule: Any) -> Optional[bool]:
        """Helper to get the actual kill switch state from the PARENT rule object."""
        if rule is None:
            LOGGER.debug("KillSwitch(%s): Cannot get state, parent rule object is None.", self.entity_id or self.unique_id)
            return None

        # Check if the rule has the kill_switch_enabled attribute in raw data
        if hasattr(rule, 'raw') and isinstance(rule.raw, dict):
            state = rule.raw.get("kill_switch_enabled") # Use .get() for safety
            if state is not None:
                return state

        # Fallback: Check direct attribute if raw doesn't have it
        if hasattr(rule, 'kill_switch_enabled'):
            state = getattr(rule, 'kill_switch_enabled')
            return state

        LOGGER.warning("KillSwitch(%s): Cannot determine actual state from parent rule object %s (type: %s)",
                     self.entity_id or self.unique_id, getattr(rule, 'id', 'N/A'), type(rule).__name__)
        return None # Return None if state cannot be determined
        
    def _get_current_rule(self) -> Any | None:
        """Get the current rule from the coordinator data.
        
        Special implementation for KillSwitch that finds the PARENT rule in traffic_routes.
        Kill switches don't have their own rule objects - they are settings on parent objects.
        """
        try:
            # 1. Validate the kill switch ID format
            kill_switch_id = self._rule_id  # This should be a kill switch ID like "unr_route_abc_kill_switch"
            if not kill_switch_id or not kill_switch_id.endswith('_kill_switch'):
                LOGGER.warning("KillSwitch(%s): Invalid kill switch ID format: %s", 
                              self.entity_id, kill_switch_id)
                return None
                
            # 2. Get the parent unique ID from our stored property 
            parent_unique_id = self._linked_parent_id
            if not parent_unique_id:
                LOGGER.error("KillSwitch(%s): Cannot find parent rule - _linked_parent_id is not set!",
                            self.entity_id)
                return None
                
            # 3. Look for the parent rule in traffic_routes collection
            # The parent's rule type is always traffic_routes for kill switches
            parent_rule_type = "traffic_routes" 
            
            # Basic validations - ensure coordinator data exists
            if not self.coordinator or not self.coordinator.data or parent_rule_type not in self.coordinator.data:
                return None
                
            # Get the traffic routes collection
            traffic_routes = self.coordinator.data[parent_rule_type]
            
            # Search for the parent rule by its unique ID
            parent_rule = None
            for rule in traffic_routes:
                current_parent_unique_id = get_rule_id(rule)
                if current_parent_unique_id == parent_unique_id:
                    parent_rule = rule
                    break  # Found it
                    
            # Return the parent rule (or None if not found)
            return parent_rule
            
        except Exception as err:
            LOGGER.error("KillSwitch(%s): Error finding parent rule: %s", 
                        self.entity_id, err)
            return None

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

class UnifiVPNClientSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi VPN client."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: VPNConfig,
        rule_type: str = "vpn_clients",
        entry_id: str = None,
    ) -> None:
        """Initialize VPN client switch."""
        # Call parent init first
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        
        # Customize properties after parent init
        vpn_type = "WireGuard" if rule_data.is_wireguard else "OpenVPN"
        self._attr_name = f"{vpn_type} VPN: {rule_data.display_name}"
        
        # Set appropriate icon
        if rule_data.is_wireguard:
            self._attr_icon = "mdi:vpn"
        elif rule_data.is_openvpn:
            self._attr_icon = "mdi:security-network"
        else:
            self._attr_icon = "mdi:vpn"
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return entity specific state attributes."""
        attributes = {}
        
        # Get current rule from coordinator data
        current_client = self._get_current_rule()
        
        if not current_client:
            return attributes
        
        # Add core attributes
        attributes["vpn_type"] = current_client.vpn_type
        attributes["name"] = current_client.name
        
        # Add connection status if available
        if hasattr(current_client, "connection_status") and current_client.connection_status:
            attributes["connection_status"] = current_client.connection_status
        
        # Type-specific attributes
        if current_client.is_wireguard:
            attributes["wireguard_endpoint"] = current_client.wireguard.get("endpoint", "")
        elif current_client.is_openvpn:
            config_file = current_client.openvpn.get("configuration_filename", "")
            if config_file:
                attributes["openvpn_config"] = config_file
        
        return attributes

class UnifiVPNServerSwitch(UnifiRuleSwitch):
    """Switch to enable/disable a UniFi VPN server."""
    
    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: VPNConfig,
        rule_type: str = "vpn_servers",
        entry_id: str = None,
    ) -> None:
        """Initialize VPN server switch."""
        # Call parent init first
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        
        # Customize properties after parent init
        vpn_type = "WireGuard" if rule_data.is_wireguard else "OpenVPN"
        self._attr_name = f"{vpn_type} VPN Server: {rule_data.display_name}"
        
        # Set appropriate icon - using distinct icons for servers
        if rule_data.is_wireguard:
            self._attr_icon = "mdi:server-network"
        elif rule_data.is_openvpn:
            self._attr_icon = "mdi:shield-lock-outline"
        else:
            self._attr_icon = "mdi:server-security"
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return entity specific state attributes."""
        attributes = {}
        
        # Get current rule from coordinator data
        current_server = self._get_current_rule()
        
        if not current_server:
            return attributes
        
        # Add core attributes
        attributes["vpn_type"] = current_server.vpn_type
        attributes["name"] = current_server.name
        
        # Add connection status if available
        if hasattr(current_server, "connection_status") and current_server.connection_status:
            attributes["status"] = current_server.connection_status
        
        # Type-specific attributes
        if current_server.is_wireguard:
            attributes["port"] = current_server.server.get("port", "")
            attributes["interface"] = current_server.server.get("interface", "")
        elif current_server.is_openvpn:
            attributes["port"] = current_server.server.get("port", "")
            attributes["protocol"] = current_server.server.get("protocol", "")
        
        # Add network info
        if current_server.server.get("subnet"):
            attributes["subnet"] = current_server.server.get("subnet")
        
        return attributes