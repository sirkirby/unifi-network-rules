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

from .const import DOMAIN, MANUFACTURER
from .coordinator import UnifiRuleUpdateCoordinator
from .helpers.rule import get_rule_id, get_rule_name, get_rule_enabled

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

# Utility functions to set up entities for each rule type
def _setup_firewall_policy_switches(coordinator, api, rule) -> Optional[SwitchEntity]:
    """Set up firewall policy switch."""
    rule_id = get_rule_id(rule)
    if not rule_id:
        return None
    return UnifiRuleSwitch(coordinator, rule, "firewall_policies")

def _setup_traffic_rule_switches(coordinator, api, rule) -> Optional[SwitchEntity]:
    """Set up traffic rule switch."""
    rule_id = get_rule_id(rule)
    if not rule_id:
        return None
    return UnifiRuleSwitch(coordinator, rule, "traffic_rules")

def _setup_port_forward_switches(coordinator, api, rule) -> Optional[SwitchEntity]:
    """Set up port forward switch."""
    rule_id = get_rule_id(rule)
    if not rule_id:
        return None
    return UnifiRuleSwitch(coordinator, rule, "port_forwards")

def _setup_traffic_route_switches(coordinator, api, rule) -> Optional[SwitchEntity]:
    """Set up traffic route switch."""
    rule_id = get_rule_id(rule)
    if not rule_id:
        return None
    return UnifiRuleSwitch(coordinator, rule, "traffic_routes")

def _setup_legacy_firewall_rule_switches(coordinator, api, rule) -> Optional[SwitchEntity]:
    """Set up legacy firewall rule switch."""
    rule_id = get_rule_id(rule)
    if not rule_id:
        return None
    return UnifiRuleSwitch(coordinator, rule, "legacy_firewall_rules")

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the UniFi Network Rules switch platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    
    # Track entities for this entry to allow removal by ID
    entity_registry = {}
    
    # Add a listener for entity removals
    @callback
    def async_handle_removal(entity_id: str) -> None:
        """Handle removal of an entity when its rule is deleted."""
        LOGGER.debug("Received entity removal request for: %s", entity_id)
        LOGGER.debug("Current entity registry keys: %s", list(entity_registry.keys()))
        
        # Check if entity ID is in expected format
        try:
            # Find entity in our registry
            entity = None
            # Handle exact matches first
            if entity_id in entity_registry:
                entity = entity_registry[entity_id]
                LOGGER.debug("Found direct match for entity: %s", entity_id)
            else:
                # Try to find a partial match if not found directly
                # This helps with ID format inconsistencies between rule types
                LOGGER.debug("No direct match, trying to find partial match for: %s", entity_id)
                parts = entity_id.split("_")
                
                if len(parts) >= 2:
                    for key, value in entity_registry.items():
                        if entity_id in key:
                            LOGGER.debug("Found potential match: %s contains %s", key, entity_id)
                            entity = value
                            entity_id = key  # Use the full key for deletion
                            LOGGER.info("Using registry key: %s for removal", entity_id)
                            break
                        
            if entity:
                LOGGER.info("Removing entity with ID: %s", entity_id)
                # Get the entity object
                LOGGER.debug("Entity object details - type: %s, unique_id: %s", 
                           type(entity).__name__,
                           getattr(entity, "unique_id", "unknown"))
                
                # Get the entity registry to properly remove the entity
                er = async_get_entity_registry(hass)
                
                # Find and remove the entity from HA entity registry by unique_id
                if hasattr(entity, "unique_id"):
                    unique_id = entity.unique_id
                    for reg_entity_id, reg_entity in er.entities.items():
                        if reg_entity.unique_id == unique_id:
                            LOGGER.info("Found entity in HA registry: %s", reg_entity_id)
                            er.async_remove(reg_entity_id)
                            LOGGER.info("Removed entity from HA entity registry: %s", reg_entity_id)
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
                
                # Also remove from the entity cache to allow re-adding if it comes back
                if hasattr(entity, "unique_id") and entity.unique_id in _ENTITY_CACHE:
                    LOGGER.debug("Removing entity from cache: %s", entity.unique_id)
                    _ENTITY_CACHE.remove(entity.unique_id)
                    LOGGER.debug("Entity removed from cache")
                else:
                    LOGGER.warning("Entity not found in cache or missing unique_id: %s", 
                                 getattr(entity, "unique_id", "unknown"))
        except Exception as err:
            LOGGER.exception("Error in entity removal handler: %s", err)

    # Register listener for entity removals
    removal_unsub = async_dispatcher_connect(
        hass, f"{DOMAIN}_entity_removed", async_handle_removal
    )
    
    # Register listener for forced entity cleanup
    @callback
    def async_force_cleanup(_: None) -> None:
        """Handle forced cleanup of all entities that no longer exist in the coordinator data."""
        LOGGER.info("Performing forced entity cleanup")
        
        # Get all current rule IDs from the coordinator data
        current_rule_ids = set()
        for rule_type in setup_type_to_method.keys():
            if rule_type in coordinator.data:
                for rule in coordinator.data[rule_type]:
                    rule_id = get_rule_id(rule)
                    if rule_id:
                        current_rule_ids.add(rule_id)
        
        LOGGER.debug("Current rule IDs in coordinator: %s", current_rule_ids)
        LOGGER.debug("Current entity registry keys: %s", list(entity_registry.keys()))
        
        # Find entities in the registry that don't exist in the current data
        stale_entities = []
        for entity_id in list(entity_registry.keys()):
            if entity_id not in current_rule_ids:
                LOGGER.info("Found stale entity in registry: %s", entity_id)
                stale_entities.append(entity_id)
        
        # Remove all stale entities
        for entity_id in stale_entities:
            LOGGER.info("Forcing removal of stale entity: %s", entity_id)
            async_handle_removal(entity_id)
            
        # Also check _ENTITY_CACHE for any entities that should be removed
        unique_ids_to_remove = []
        for unique_id in _ENTITY_CACHE:
            # Extract the rule ID from the unique ID
            if "_" in unique_id:
                parts = unique_id.split("_")
                if len(parts) >= 3:  # Should be like "traffic_rules_unr_rule_12345"
                    rule_id = "_".join(parts[2:])  # Get everything after the rule type
                    if rule_id not in current_rule_ids:
                        LOGGER.info("Found stale entity in cache: %s -> %s", unique_id, rule_id)
                        unique_ids_to_remove.append(unique_id)
        
        # Remove stale entities from the cache
        for unique_id in unique_ids_to_remove:
            LOGGER.info("Removing stale entity from cache: %s", unique_id)
            _ENTITY_CACHE.remove(unique_id)
            
    cleanup_unsub = async_dispatcher_connect(
        hass, f"{DOMAIN}_force_entity_cleanup", async_force_cleanup
    )
    
    # Store unsub functions to ensure they get called on unload
    if not hasattr(hass.data[DOMAIN][config_entry.entry_id], "unsub_listeners"):
        hass.data[DOMAIN][config_entry.entry_id]["unsub_listeners"] = []
    hass.data[DOMAIN][config_entry.entry_id]["unsub_listeners"].extend([removal_unsub, cleanup_unsub])
    
    # Set up platform with the coordinator and API
    setup_type_to_method = {
        "firewall_policies": _setup_firewall_policy_switches,
        "traffic_rules": _setup_traffic_rule_switches,
        "port_forwards": _setup_port_forward_switches,
        "traffic_routes": _setup_traffic_route_switches,
        "legacy_firewall_rules": _setup_legacy_firewall_rule_switches
    }
    
    @callback
    def _add_new_rules() -> None:
        """Add switches for rules that have been added since last update."""
        new_entities = []
        
        # Check if data is empty or missing due to temporary API failure
        if not coordinator.data or not any(rule_type in coordinator.data for rule_type in setup_type_to_method.keys()):
            LOGGER.warning("Coordinator data is empty or missing rule types, likely a temporary API issue")
            # Don't remove entities during temporary API failures
            return
        
        # Process each rule type
        for setup_type, setup_method in setup_type_to_method.items():
            if not coordinator.data or setup_type not in coordinator.data:
                continue
            
            try:
                for rule in coordinator.data[setup_type]:
                    entity = setup_method(coordinator, api, rule)
                    if entity:
                        unique_id = entity.unique_id
                        if unique_id not in _ENTITY_CACHE:
                            _ENTITY_CACHE.add(unique_id)
                            new_entities.append(entity)
                            # Add to our registry for removal tracking
                            rule_id = get_rule_id(rule)
                            if rule_id:
                                # Use the rule_id directly since get_rule_id already includes prefixes
                                LOGGER.debug("Adding entity to registry with key: %s", rule_id)
                                entity_registry[rule_id] = entity
            except Exception as error:
                LOGGER.exception("Error setting up %s: %s", setup_type, error)
                
        if new_entities:
            LOGGER.info("Adding %d new rule entities", len(new_entities))
            async_add_entities(new_entities, True)
    
    # Add current rules
    _add_new_rules()
    
    # Register for updates
    config_entry.async_on_unload(
        coordinator.async_add_listener(_add_new_rules)
    )

class UnifiRuleSwitch(CoordinatorEntity[UnifiRuleUpdateCoordinator], SwitchEntity):
    """Switch to enable/disable UniFi Network rules."""

    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
    ) -> None:
        """Initialize the rule switch."""
        super().__init__(coordinator)
        self._rule_data = rule_data
        self._rule_type = rule_type
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
            
        self._attr_unique_id = f"{rule_type}_{self._rule_id}"
        
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
            # Only clear optimistic state if it's been more than 10 seconds
            # This prevents rapid authentication cycles from clearing optimistic state
            if self._optimistic_state is not None:
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
        if isinstance(obj, dict):
            return obj.copy()
            
        # Get the rule ID properly considering object type
        # From helpers.rule we know the id is accessed directly without underscore
        rule_id = None
        if hasattr(obj, "id"):
            rule_id = getattr(obj, "id")
            
        base_data = {
            "_id": rule_id,
            "enabled": getattr(obj, "enabled", False)
        }
        
        if isinstance(obj, PortForward):
            # PortForward specific conversion
            port_data = {
                "dst_port": getattr(obj, "dst", ""),  # Use dst instead of dst_port
                "fwd_port": getattr(obj, "fwd", ""),  # Use fwd instead of fwd_port
                "name": getattr(obj, "name", ""),
                "pfwd_interface": getattr(obj, "pfwd_interface", "wan"),
                "proto": getattr(obj, "proto", "tcp_udp"),
                "src": getattr(obj, "src", "any")
            }
            base_data.update(port_data)
            
        elif isinstance(obj, TrafficRoute):
            # TrafficRoute specific conversion
            route_data = {
                "description": getattr(obj, "description", ""),
                "matching_address": getattr(obj, "matching_address", ""),
                "target_gateway": getattr(obj, "target_gateway", ""),
                "priority": getattr(obj, "priority", 0),
                "source": getattr(obj, "source", "any")
            }
            base_data.update(route_data)
            
        elif isinstance(obj, FirewallPolicy):
            # FirewallPolicy specific conversion
            policy_data = {
                "name": getattr(obj, "name", ""),
                "description": getattr(obj, "description", ""),
                "action": getattr(obj, "action", None),
                "source": getattr(obj, "source", {}),
                "destination": getattr(obj, "destination", {}),
                "protocol": getattr(obj, "protocol", "all"),
                "ports": getattr(obj, "ports", [])
            }
            base_data.update(policy_data)
            
        return {k: v for k, v in base_data.items() if v is not None}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on (enable) the rule."""
        LOGGER.debug("Turning on rule %s (%s)", self._rule_id, self._rule_type)
        
        # Set optimistic state first for immediate UI feedback with timestamp
        self._optimistic_state = True
        self._optimistic_timestamp = time.time()
        self.async_write_ha_state()
        
        # Use toggle methods for all rule types
        success = False
        try:
            if self._rule_type == "firewall_policies":
                success = await self.coordinator.api.toggle_firewall_policy(self._rule_id, True)
            elif self._rule_type == "traffic_rules":
                success = await self.coordinator.api.toggle_traffic_rule(self._rule_id, True)
            elif self._rule_type == "port_forwards":
                success = await self.coordinator.api.toggle_port_forward(self._rule_id, True)
            elif self._rule_type == "traffic_routes":
                success = await self.coordinator.api.toggle_traffic_route(self._rule_id, True)
            elif self._rule_type == "legacy_firewall_rules":
                success = await self.coordinator.api.toggle_legacy_firewall_rule(self._rule_id, True)
        except Exception as err:
            LOGGER.error("Error enabling rule: %s", err)
            success = False
            
        if success:
            # Schedule update after success, but keep optimistic state for a bit
            LOGGER.debug("Rule %s enabled successfully, scheduling refresh", self._rule_id)
            await self.coordinator.async_request_refresh()
        else:
            # Revert optimistic state if failed
            LOGGER.error("Failed to enable rule %s", self._rule_id)
            self._optimistic_state = False
            self._optimistic_timestamp = time.time()  # Update timestamp for failed state
            self.async_write_ha_state()
            # Still try to refresh to get actual state
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off (disable) the rule."""
        LOGGER.debug("Turning off rule %s (%s)", self._rule_id, self._rule_type)
        
        # Set optimistic state first for immediate UI feedback with timestamp
        self._optimistic_state = False
        self._optimistic_timestamp = time.time()
        self.async_write_ha_state()
        
        # Use toggle methods for all rule types
        success = False
        try:
            if self._rule_type == "firewall_policies":
                success = await self.coordinator.api.toggle_firewall_policy(self._rule_id, False)
            elif self._rule_type == "traffic_rules":
                success = await self.coordinator.api.toggle_traffic_rule(self._rule_id, False)
            elif self._rule_type == "port_forwards":
                success = await self.coordinator.api.toggle_port_forward(self._rule_id, False)
            elif self._rule_type == "traffic_routes":
                success = await self.coordinator.api.toggle_traffic_route(self._rule_id, False)
            elif self._rule_type == "legacy_firewall_rules":
                success = await self.coordinator.api.toggle_legacy_firewall_rule(self._rule_id, False)
        except Exception as err:
            LOGGER.error("Error disabling rule: %s", err)
            success = False
            
        if success:
            # Schedule update after success, but keep optimistic state for a bit
            LOGGER.debug("Rule %s disabled successfully, scheduling refresh", self._rule_id)
            await self.coordinator.async_request_refresh()
        else:
            # Revert optimistic state if failed
            LOGGER.error("Failed to disable rule %s", self._rule_id)
            self._optimistic_state = True
            self._optimistic_timestamp = time.time()  # Update timestamp for failed state 
            self.async_write_ha_state()
            # Still try to refresh to get actual state
            await self.coordinator.async_request_refresh()

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