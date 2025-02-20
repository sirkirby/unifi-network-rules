"""Support for UniFi Network Rules switches."""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING
import asyncio
from datetime import datetime

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .utils.logger import log_call
from .utils.registry import async_get_registry
from .rule_template import RuleType

if TYPE_CHECKING:
    from .coordinator import UnifiRuleUpdateCoordinator
    from .udm_api import UDMAPI

class EntityIDManager:
    """Manage entity IDs and handle cleanup of legacy formats."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the ID manager."""
        self.hass = hass
        self._known_formats = {
            'port_forward': [
                lambda rule: f"pf_rule_{rule['_id']}",  # Current format
                lambda rule: f"port_forward_{rule.get('name', '').lower().replace(' ', '_')}_{rule.get('fwd', '').replace('.', '_')}",  # Legacy format 1
                lambda rule: f"port_forward_{rule.get('name', '').lower().replace(' ', '_')}_{rule.get('fwd', '').replace('.', '_')}_{rule['_id'][-4:]}"  # Legacy format 2
            ],
            'traffic_route': [
                lambda rule: f"network_route_{rule['_id']}"  # Current format only
            ],
            'firewall_policy': [
                lambda rule: f"network_policy_{rule['_id']}"  # Current format only
            ],
            'legacy_firewall': [
                lambda rule: f"network_rule_firewall_{rule['_id']}"  # Current format only
            ],
            'legacy_traffic': [
                lambda rule: f"network_rule_traffic_{rule['_id']}"  # Current format only
            ]
        }

    def get_current_unique_id(self, rule_type: str, rule_data: dict) -> str:
        """Get the current format unique ID for a rule."""
        # Legacy format to current format mapping
        legacy_to_current = {
            'port_forward': lambda rule: f"port_forward_{rule['name'].lower().replace(' ', '_')}_{rule.get('fwd', '').replace('.', '_')}_{rule['_id']}",
            'traffic_route': lambda rule: f"network_route_{rule['_id']}",
            'firewall_policy': lambda rule: f"network_policy_{rule['_id']}",
            'legacy_firewall': lambda rule: f"network_rule_firewall_{rule['_id']}",
            'legacy_traffic': lambda rule: f"network_rule_traffic_{rule['_id']}"
        }
        
        if rule_type in legacy_to_current:
            return legacy_to_current[rule_type](rule_data)
        return None

    def get_legacy_unique_ids(self, rule_type: str, rule_data: dict) -> list[str]:
        """Get legacy format IDs for a rule."""
        legacy_formats = {
            'port_forward': [
                lambda rule: f"pf_rule_{rule['_id']}",
                lambda rule: f"port_forward_{rule.get('name', '').lower().replace(' ', '_')}_{rule.get('fwd', '').replace('.', '_')}"
            ],
            'traffic_route': [],  # No legacy formats
            'firewall_policy': [], # No legacy formats
            'legacy_firewall': [], # No legacy formats
            'legacy_traffic': []   # No legacy formats
        }
        
        if rule_type in legacy_formats:
            return [
                id_format(rule_data)
                for id_format in legacy_formats[rule_type]
                if id_format(rule_data) is not None
            ]
        return []

    async def cleanup_legacy_entities(self, domain: str, rule_type: str, rule_data: dict) -> None:
        """Clean up legacy format entities for a rule."""
        try:
            registry = self._get_registry()
            rule_id = rule_data.get('_id')
            
            # Build all possible unique ID formats this rule might have
            possible_ids = [f"{rule_type}_{rule_id}"]  # Current format
            
            # Add legacy format IDs
            if legacy_ids := self.get_legacy_unique_ids(rule_type, rule_data):
                possible_ids.extend(legacy_ids)
            
            # Find and remove any matching entities
            for unique_id in possible_ids:
                # Direct match first
                if entity_id := registry.async_get_entity_id("switch", domain, unique_id):
                    registry.async_remove(entity_id)
                    LOGGER.info("Removed legacy entity %s (unique_id: %s)", entity_id, unique_id)
                    
                # Also check for partial matches (for legacy IDs)
                for entity_id, entry in list(registry.entities.items()):
                    if (entry.domain == domain and 
                        rule_id in entry.unique_id and
                        entry.unique_id not in possible_ids):
                        registry.async_remove(entity_id)
                        LOGGER.info("Removed partially matching legacy entity %s (unique_id: %s)", 
                                  entity_id, entry.unique_id)
            
        except Exception as e:
            LOGGER.error("Error cleaning up legacy entities for rule %s: %s", 
                        rule_data.get('_id'), str(e))

    @callback
    def _cleanup_stale_entities(self, platform: str) -> None:
        """Clean up stale entities from the registry."""
        registry = self._get_registry()
        removed = []

        # Get all entities for our domain and platform
        for entity_id, entry in list(registry.entities.items()):
            if entry.domain == DOMAIN and entry.platform == platform:
                try:
                    # Extract the rule ID from the unique_id
                    rule_id = entry.unique_id.split('_')[-1]
                    
                    # Check if entity exists in any config entry's coordinator
                    exists = False
                    if self.hass and DOMAIN in self.hass.data:
                        for config_entry_data in self.hass.data[DOMAIN].values():
                            coordinator = config_entry_data.get('coordinator')
                            if coordinator and coordinator.data:
                                if coordinator.get_rule(rule_id):
                                    exists = True
                                    break
                    
                    if not exists:
                        # Force remove the entity
                        registry.async_remove(entity_id)
                        removed.append(entity_id)
                        LOGGER.info("Removed stale entity %s (rule %s not found)", entity_id, rule_id)
                        
                except Exception as e:
                    LOGGER.error("Error processing entity %s: %s", entity_id, str(e))

        if removed:
            LOGGER.info("Cleaned up %d stale entities: %s", len(removed), removed)

class UDMBaseSwitch(CoordinatorEntity, SwitchEntity):
    """Base class for UDM switches."""

    def __init__(self, coordinator, api, item_data: Dict[str, Any], data_key: str):
        """Initialize the switch."""
        super().__init__(coordinator)
        self.api = api
        self._item_data = item_data
        self._data_key = data_key
        self.entity_id = f"switch.{DOMAIN}_{data_key}_{item_data['_id']}"
        self._attr_unique_id = f"{data_key}_{item_data['_id']}"
        self._attr_name = item_data.get('name', item_data['_id'])
        self._attr_is_on = item_data.get('enabled', False)
        self._attr_assumed_state = False
        self._optimistic_state = None
        self._optimistic_request_time = None

    @property 
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        # If we have an optimistic state and it's recent (within last 30 seconds), use it
        if self._optimistic_state is not None and self._optimistic_request_time is not None:
            if (datetime.now() - self._optimistic_request_time).total_seconds() < 30:
                return self._optimistic_state
            else:
                # Clear expired optimistic state
                self._optimistic_state = None
                self._optimistic_request_time = None

        # Otherwise get current state from coordinator
        if rule := self.coordinator.get_rule(self._item_data['_id']):
            self._attr_is_on = rule.get('enabled', False)
        return self._attr_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        try:
            # Set optimistic state
            self._optimistic_state = True
            self._optimistic_request_time = datetime.now()
            self._attr_is_on = True
            self.async_write_ha_state()
            
            # Map the data key to the API method name
            data_key_mapping = {
                "firewall_policies": ("toggle_firewall_policy", '_id'),
                "traffic_routes": ("toggle_traffic_route", '_id'),
                "port_forward_rules": ("toggle_port_forward_rule", '_id'),
                "firewall_rules": ("toggle_legacy_firewall_rule", '_id'),
                "traffic_rules": ("toggle_legacy_traffic_rule", '_id'),
                "network_policies": ("toggle_firewall_policy", '_id'),
                "network_routes": ("toggle_traffic_route", '_id'),
            }
            
            if self._data_key not in data_key_mapping:
                raise ValueError(f"Unsupported rule type: {self._data_key}")
            
            method_name, id_field = data_key_mapping[self._data_key]
            toggle_method = getattr(self.api, method_name)
            rule_id = self._item_data[id_field]
            
            success, error = await toggle_method(rule_id, True)
            
            if not success:
                # Clear optimistic state on failure
                self._optimistic_state = None
                self._optimistic_request_time = None
                self._attr_is_on = False
                self.async_write_ha_state()
                raise HomeAssistantError(f"Failed to enable rule: {error}")
                
            # Request refresh in background
            self.hass.async_create_task(self.coordinator.async_request_refresh())
            
        except Exception as e:
            # Clear optimistic state on error
            self._optimistic_state = None
            self._optimistic_request_time = None
            self._attr_is_on = False
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error enabling rule: {str(e)}")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        try:
            # Set optimistic state
            self._optimistic_state = False
            self._optimistic_request_time = datetime.now()
            self._attr_is_on = False
            self.async_write_ha_state()
            
            # Map the data key to the API method name
            data_key_mapping = {
                "firewall_policies": ("toggle_firewall_policy", '_id'),
                "traffic_routes": ("toggle_traffic_route", '_id'),
                "port_forward_rules": ("toggle_port_forward_rule", '_id'),
                "firewall_rules": ("toggle_legacy_firewall_rule", '_id'),
                "traffic_rules": ("toggle_legacy_traffic_rule", '_id'),
                "network_policies": ("toggle_firewall_policy", '_id'),
                "network_routes": ("toggle_traffic_route", '_id'),
            }
            
            if self._data_key not in data_key_mapping:
                raise ValueError(f"Unsupported rule type: {self._data_key}")
            
            method_name, id_field = data_key_mapping[self._data_key]
            toggle_method = getattr(self.api, method_name)
            rule_id = self._item_data[id_field]
            
            success, error = await toggle_method(rule_id, False)
            
            if not success:
                # Clear optimistic state on failure
                self._optimistic_state = None
                self._optimistic_request_time = None
                self._attr_is_on = True
                self.async_write_ha_state()
                raise HomeAssistantError(f"Failed to disable rule: {error}")
                
            # Request refresh in background
            self.hass.async_create_task(self.coordinator.async_request_refresh())
            
        except Exception as e:
            # Clear optimistic state on error
            self._optimistic_state = None
            self._optimistic_request_time = None
            self._attr_is_on = True
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error disabling rule: {str(e)}")

class UDMPortForwardRuleSwitch(UDMBaseSwitch):
    """Representation of a UDM Port Forward Rule Switch."""

    def __init__(self, coordinator, api, rule: Dict[str, Any]):
        """Initialize the UDM Port Forward Rule Switch."""
        super().__init__(coordinator, api, rule, 'port_forward_rules')
        name = rule.get('name', 'Unnamed')
        fwd_ip = rule.get('fwd', '')
        self._attr_name = f"Port Forward: {name} ({fwd_ip})"

class UDMTrafficRouteSwitch(UDMBaseSwitch):
    """Representation of a UDM Traffic Route Switch."""

    def __init__(self, coordinator, api, route: Dict[str, Any]):
        """Initialize the UDM Traffic Route Switch."""
        super().__init__(coordinator, api, route, 'traffic_routes')
        desc = route.get('description', 'Unnamed')
        self._attr_name = f"Network Route: {desc}"

class UDMFirewallPolicySwitch(UDMBaseSwitch):
    """Representation of a UDM Firewall Policy Switch."""

    def __init__(self, coordinator, api, policy: Dict[str, Any]):
        """Initialize the UDM Firewall Policy Switch."""
        super().__init__(coordinator, api, policy, 'firewall_policies')
        base_name = policy.get('name', 'Unnamed')
        self._attr_name = f"Network Policy: {base_name} ({policy['_id'][-4:]})"

class UDMLegacyRuleSwitch(UDMBaseSwitch):
    """Base class for legacy rule switches."""

    def __init__(self, coordinator, api, rule: Dict[str, Any], rule_type: str, data_key: str):
        """Initialize the legacy rule switch."""
        super().__init__(coordinator, api, rule, data_key)
        rule_name = rule.get('name', rule.get('description', 'Unnamed'))
        self._attr_name = f"Network Rule: {rule_name} ({rule['_id'][-4:]})"

class UDMLegacyFirewallRuleSwitch(UDMLegacyRuleSwitch):
    """Representation of a UDM Legacy Firewall Rule Switch."""

    def __init__(self, coordinator, api, rule: Dict[str, Any]):
        """Initialize the UDM Legacy Firewall Rule Switch."""
        super().__init__(coordinator, api, rule, "legacy_firewall", "firewall_rules")

class UDMLegacyTrafficRuleSwitch(UDMLegacyRuleSwitch):
    """Representation of a UDM Legacy Traffic Rule Switch."""

    def __init__(self, coordinator, api, rule: Dict[str, Any]):
        """Initialize the UDM Legacy Traffic Rule Switch."""
        super().__init__(coordinator, api, rule, "legacy_traffic", "traffic_rules")

@log_call
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up UniFi Network Rules switches from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]['coordinator']
    api = hass.data[DOMAIN][entry.entry_id]['api']

    entities = []

    # Create switches for each rule type
    if coordinator.data:
        # Firewall policies
        if 'firewall_policies' in coordinator.data:
            policies = coordinator.data['firewall_policies']
            if isinstance(policies, list):
                entities.extend([
                    UDMFirewallPolicySwitch(coordinator, api, policy)
                    for policy in policies
                    if isinstance(policy, dict) and not policy.get('predefined', False)
                ])

        # Traffic routes
        if 'traffic_routes' in coordinator.data:
            routes = coordinator.data['traffic_routes']
            if isinstance(routes, list):
                entities.extend([
                    UDMTrafficRouteSwitch(coordinator, api, route)
                    for route in routes
                ])

        # Port forward rules
        if 'port_forward_rules' in coordinator.data:
            rules = coordinator.data['port_forward_rules']
            if isinstance(rules, list):
                entities.extend([
                    UDMPortForwardRuleSwitch(coordinator, api, rule)
                    for rule in rules
                ])

        # Legacy firewall rules
        if 'legacy_firewall_rules' in coordinator.data:
            firewall_rules = coordinator.data['legacy_firewall_rules']
            if isinstance(firewall_rules, list):
                entities.extend([
                    UDMLegacyFirewallRuleSwitch(coordinator, api, rule)
                    for rule in firewall_rules
                ])

        # Legacy traffic rules
        if 'legacy_traffic_rules' in coordinator.data:
            traffic_rules = coordinator.data['legacy_traffic_rules']
            if isinstance(traffic_rules, list):
                entities.extend([
                    UDMLegacyTrafficRuleSwitch(coordinator, api, rule)
                    for rule in traffic_rules
                ])

    async_add_entities(entities)