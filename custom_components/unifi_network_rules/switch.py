"""Support for UniFi Network Rules switches."""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING
import asyncio

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
    from .entity_loader import UnifiRuleEntityLoader
    from .coordinator import UDMUpdateCoordinator
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
            current_id = self.get_current_unique_id(rule_type, rule_data)
            if not current_id:
                return

            legacy_ids = self.get_legacy_unique_ids(rule_type, rule_data)
            if not legacy_ids:
                return

            registry = async_get_registry(self.hass)
            
            # Track which entities were removed
            removed_entities = []
            
            # Remove only legacy format entities
            for legacy_id in legacy_ids:
                entity = registry.async_get_entity_id(domain, DOMAIN, legacy_id)
                if entity:
                    LOGGER.debug(
                        "Removing legacy entity %s (unique_id: %s) in favor of %s", 
                        entity, legacy_id, current_id
                    )
                    registry.async_remove(entity)
                    removed_entities.append(legacy_id)
                    
            if removed_entities:
                LOGGER.info(
                    "Cleaned up %d legacy entities for %s: %s", 
                    len(removed_entities), 
                    current_id,
                    removed_entities
                )
            
        except Exception as e:
            LOGGER.error("Error during legacy entity cleanup: %s", str(e))

    @callback
    def _cleanup_stale_entities(self, platform: str) -> None:
        """Clean up stale entities from the registry."""
        registry = self._get_registry()
        removed = []

        # Get all entities for our domain and platform
        for entity_id, entry in list(registry.entities.items()):
            if entry.domain == DOMAIN and entry.platform == platform:
                if not entry.disabled:  # Only process enabled entities
                    try:
                        # Extract the rule ID from the unique_id
                        rule_id = entry.unique_id.split('_')[-1]
                        
                        # Check if entity exists in any config entry's coordinator
                        exists = False
                        if self.hass and DOMAIN in self.hass.data:
                            for config_entry_data in self.hass.data[DOMAIN].values():
                                if 'coordinator' in config_entry_data:
                                    coordinator = config_entry_data['coordinator']
                                    if coordinator and coordinator.get_rule(rule_id):
                                        exists = True
                                        break
                        
                        if not exists:
                            LOGGER.info("Removing stale entity %s (rule %s not found)", entity_id, rule_id)
                            registry.async_remove(entity_id)
                            removed.append(entity_id)
                            
                    except Exception as e:
                        LOGGER.error("Error processing entity %s: %s", entity_id, str(e))

        if removed:
            LOGGER.info("Cleaned up %d stale entities: %s", len(removed), removed)

class UDMBaseSwitch(CoordinatorEntity, SwitchEntity):
    """Base class for UDM switches."""

    def __init__(self, coordinator, api, item_data: Dict[str, Any], data_key: str, rule_type: str):
        """Initialize the base switch."""
        super().__init__(coordinator)
        self._api = api
        self._item_data = item_data
        self._item_id = item_data['_id']
        self._data_key = data_key
        self._rule_type = rule_type
        self._pending_state = None
        self.entity_category = EntityCategory.CONFIG
        self._entity_loader = None
        self._id_manager = None
        
        # Set a temporary unique_id until we're properly added to HASS
        self._attr_unique_id = f"{self._rule_type}_{self._item_id}"
        
        # Check if this entity type supports websockets
        self._websocket_supported = self._api.supports_websocket(self._data_key)

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        try:
            # Initialize ID manager
            self._id_manager = EntityIDManager(self.hass)
            
            # Update unique_id if needed
            if new_unique_id := self._id_manager.get_current_unique_id(self._rule_type, self._item_data):
                if new_unique_id != self._attr_unique_id:
                    LOGGER.debug(
                        "%s: Updating unique_id from %s to %s",
                        self._attr_name,
                        self._attr_unique_id,
                        new_unique_id
                    )
                    self._attr_unique_id = new_unique_id
            
            # Get entity loader from coordinator data
            if self.coordinator.config_entry and DOMAIN in self.coordinator.hass.data:
                entry_data = self.coordinator.hass.data[DOMAIN].get(self.coordinator.config_entry.entry_id, {})
                self._entity_loader = entry_data.get('entity_loader')
            
            # Start tracking this specific rule
            self.coordinator.track_rule_changes(self._item_id)
            
            # Clean up legacy entities after setting our final unique_id
            await self._id_manager.cleanup_legacy_entities(
                "switch", 
                self._rule_type, 
                self._item_data
            )
            
            # When entity is removed, stop tracking the rule
            self.async_on_remove(
                lambda: self.coordinator.stop_tracking_rule(self._item_id)
            )
            
        except Exception as e:
            LOGGER.error(
                "%s: Error during entity setup: %s",
                self._attr_name,
                str(e)
            )

    def _get_rules_key(self) -> str:
        """Get the key for accessing rules in coordinator data."""
        return self._data_key

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # First check if we have any coordinator data
        if not self.coordinator.data:
            LOGGER.debug("%s: No coordinator data available", self._attr_name)
            return False

        # Get rules from coordinator
        rules = self.coordinator.data.get(self._get_rules_key(), [])
        
        # Legacy rules come in {data: [...]} format
        if isinstance(rules, dict) and 'data' in rules:
            rules = rules['data']

        # Check if rule exists in current data
        rule_exists = any(r for r in rules if r.get('_id') == self._item_id)

        return self.coordinator.last_update_success and rule_exists

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        if self._pending_state is not None:
            return self._pending_state
        return bool(self._item_data.get('enabled', False))
    
    async def async_will_remove_from_hass(self) -> None:
        """Handle entity being removed from Home Assistant."""
        await super().async_will_remove_from_hass()
        
        # Ensure we cleanup when entity is removed
        self.coordinator.stop_tracking_rule(self._item_id)
        
        # Remove from entity loader if available
        if self._entity_loader:
            platform = self.__class__.__name__.lower().replace('udm', '').replace('switch', '')
            self._entity_loader.async_handle_entity_removal(platform, self.unique_id)

    async def _cleanup_old_entities(self) -> None:
        """Clean up old format entity IDs if they exist."""
        if not self.hass:
            return
            
        old_id = self._get_legacy_entity_id()
        if old_id and old_id != self._attr_unique_id:
            registry = self.hass.helpers.entity_registry.async_get()  # Remove hass parameter
            old_entity = registry.async_get_entity_id("switch", DOMAIN, old_id)
            if old_entity:
                LOGGER.debug("Removing old format entity: %s", old_id)
                registry.async_remove(old_entity)

    def _get_legacy_entity_id(self) -> Optional[str]:
        """Get legacy entity ID format if applicable. Override in subclasses if needed."""
        return None

    async def _verify_state_change(self, target_state: bool, get_method, max_attempts: int = 3) -> bool:
        """Verify that the state change was successful."""
        for attempt in range(max_attempts):
            if get_method:
                success, item, error = await get_method(self._item_id)
                if success and item:
                    actual_state = item.get('enabled', False)
                    if actual_state == target_state:
                        self._item_data = item
                        self._pending_state = None
                        self.async_write_ha_state()
                        return True
            # Also check coordinator data as it might be more up-to-date
            if current_rule := self.coordinator.get_rule(self._item_id):
                actual_state = current_rule.get('enabled', False)
                if actual_state == target_state:
                    self._item_data = current_rule
                    self._pending_state = None
                    self.async_write_ha_state()
                    return True
            await asyncio.sleep(1)
        return False

    async def _execute_toggle(self, new_state: bool, toggle_fn, verify_fn, entity_name: str) -> None:
        """Execute toggle with verification using a common method."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()
            success, error = await toggle_fn(self._item_id, new_state)
            
            if success:
                verify_success = await self._verify_state_change(new_state, verify_fn)
                if verify_success:
                    # Force a refresh after successful change to ensure consistent state
                    await self.coordinator.async_refresh_rules(self._data_key)
                    return
                error = "State verification failed"
            
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to toggle {entity_name}: {error if error else 'Unknown error'}")
            
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling {entity_name}: {str(e)}")

    async def _toggle(self, new_state: bool) -> None:
        """Base toggle implementation with websocket support."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()
            
            if self._websocket_supported:
                # Include all current rule data in update
                updated_rule = dict(self._item_data)
                updated_rule['enabled'] = new_state
                
                update_task = self.coordinator._handle_websocket_update(
                    self._data_key,
                    'update',
                    updated_rule
                )
                success = await update_task
                
                if not success:
                    # Fall back to REST API if websocket update fails
                    await self._execute_toggle(
                        new_state,
                        self._get_toggle_method(),
                        self._get_verify_method(),
                        self._get_entity_type_name()
                    )
            else:
                await self._execute_toggle(
                    new_state,
                    self._get_toggle_method(),
                    self._get_verify_method(),
                    self._get_entity_type_name()
                )
            
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling {self._get_entity_type_name()}: {str(e)}")

    def _get_toggle_method(self):
        """Get the appropriate toggle method based on data key."""
        toggle_methods = {
            'port_forward_rules': self._api.toggle_port_forward_rule,
            'traffic_routes': self._api.toggle_traffic_route,
            'firewall_policies': self._api.toggle_firewall_policy,
            'firewall_rules': self._api.toggle_legacy_firewall_rule,
            'traffic_rules': self._api.toggle_legacy_traffic_rule
        }
        return toggle_methods.get(self._data_key)

    def _get_verify_method(self):
        """Get the appropriate verification method based on data key."""
        verify_methods = {
            'port_forward_rules': lambda x: self.coordinator.get_rule(self._item_id),
            'traffic_routes': lambda x: self.coordinator.get_rule(self._item_id),
            'firewall_policies': self._api.get_firewall_policy,
            'firewall_rules': self._api.get_legacy_firewall_rule,
            'traffic_rules': lambda x: (True, self._item_data, None)
        }
        return verify_methods.get(self._data_key)

    def _get_entity_type_name(self) -> str:
        """Get the entity type name based on data key."""
        type_names = {
            'port_forward_rules': 'port forward rule',
            'traffic_routes': 'traffic route',
            'firewall_policies': 'firewall policy',
            'firewall_rules': 'legacy firewall rule',
            'traffic_rules': 'legacy traffic rule'
        }
        return type_names.get(self._data_key, 'rule')

    @log_call
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._toggle(True)

    @log_call
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._toggle(False)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data update."""
        if not self.coordinator.data:
            if self._item_data:
                LOGGER.debug("%s: Clearing item data due to no coordinator data", self._attr_name)
                self._item_data = None
                self._pending_state = None
                self.async_write_ha_state()
            return

        rules = self.coordinator.data.get(self._get_rules_key(), [])
        if isinstance(rules, dict) and 'data' in rules:
            rules = rules['data']
            
        updated_item = next(
            (item for item in rules if item.get('_id') == self._item_id), 
            None
        )
        
        if updated_item:
            old_state = self._item_data.get('enabled', False) if self._item_data else None
            new_state = updated_item.get('enabled', False)
            
            # Only clear pending state if the new state matches what we were expecting
            if self._pending_state is not None and new_state == self._pending_state:
                self._pending_state = None
                
            self._item_data = updated_item
            
            if old_state != new_state:
                LOGGER.debug(
                    "%s state changed from %s to %s (pending: %s)", 
                    self._attr_name, old_state, new_state, self._pending_state
                )
                
            self.async_write_ha_state()
            return
            
        # If we get here, the item no longer exists
        if self._item_data:
            LOGGER.debug("%s: Rule no longer exists in coordinator data", self._attr_name)
            self._item_data = None
            self._pending_state = None
            self.async_write_ha_state()
            
            # Remove entity if entity loader is available
            if self._entity_loader:
                self._entity_loader.async_remove_entity('switch', self.unique_id)

class UDMPortForwardRuleSwitch(UDMBaseSwitch):
    """Representation of a UDM Port Forward Rule Switch."""

    def __init__(self, coordinator, api, rule: Dict[str, Any]):
        """Initialize the UDM Port Forward Rule Switch."""
        super().__init__(coordinator, api, rule, 'port_forward_rules', 'port_forward')
        name = rule.get('name', 'Unnamed')
        fwd_ip = rule.get('fwd', '')
        self._attr_name = f"Port Forward: {name} ({fwd_ip})"

class UDMTrafficRouteSwitch(UDMBaseSwitch):
    """Representation of a UDM Traffic Route Switch."""

    def __init__(self, coordinator, api, route: Dict[str, Any]):
        """Initialize the UDM Traffic Route Switch."""
        super().__init__(coordinator, api, route, 'traffic_routes', 'traffic_route')
        desc = route.get('description', 'Unnamed')
        self._attr_name = f"Network Route: {desc}"

class UDMFirewallPolicySwitch(UDMBaseSwitch):
    """Representation of a UDM Firewall Policy Switch."""

    def __init__(self, coordinator, api, policy: Dict[str, Any]):
        """Initialize the UDM Firewall Policy Switch."""
        super().__init__(coordinator, api, policy, 'firewall_policies', 'firewall_policy')
        base_name = policy.get('name', 'Unnamed')
        self._attr_name = f"Network Policy: {base_name} ({policy['_id'][-4:]})"

class UDMLegacyRuleSwitch(UDMBaseSwitch):
    """Base class for legacy rule switches."""

    def __init__(self, coordinator, api, rule: Dict[str, Any], rule_type: str, data_key: str):
        """Initialize the legacy rule switch."""
        super().__init__(coordinator, api, rule, data_key, rule_type)
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
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    """Set up the UniFi Network Rules switches."""
    try:
        coordinator = hass.data[DOMAIN][entry.entry_id]['coordinator']
        api = hass.data[DOMAIN][entry.entry_id]['api']
        entity_loader = hass.data[DOMAIN][entry.entry_id]['entity_loader']

        # Register switch platform first
        entity_loader.async_setup_platform('switch', async_add_entities)

        # Ensure we have coordinator data before proceeding
        if not coordinator.data:
            LOGGER.warning("No coordinator data available for switch setup")
            return False

        def process_rule(rule_type: str, data: dict, data_key: str) -> None:
            """Process a single rule for entity creation."""
            if not data or '_id' not in data:
                LOGGER.debug("Invalid data for rule type %s: %s", rule_type, data)
                return

            try:
                def create_entity(cfg=data, r_type=rule_type, d_key=data_key):
                    """Create entity with closure variables."""
                    if r_type == 'firewall_policy':
                        return UDMFirewallPolicySwitch(coordinator, api, cfg)
                    elif r_type == 'traffic_route':
                        return UDMTrafficRouteSwitch(coordinator, api, cfg)
                    elif r_type == 'port_forward':
                        return UDMPortForwardRuleSwitch(coordinator, api, cfg)
                    elif r_type == 'legacy_firewall':
                        return UDMLegacyFirewallRuleSwitch(coordinator, api, cfg)
                    elif r_type == 'legacy_traffic':
                        return UDMLegacyTrafficRuleSwitch(coordinator, api, cfg)
                    return None

                # Let entity_loader handle unique IDs and tracking
                entity_loader.async_add_entity(
                    platform='switch',
                    unique_id=f"{rule_type}_{data['_id']}",
                    entity_factory=create_entity,
                    data_key=data_key
                )

            except Exception as e:
                LOGGER.error("Error processing %s: %s", rule_type, str(e))

        def log_and_process_rules(rules, rule_type, data_key):
            """Process rules with count logging."""
            if isinstance(rules, dict) and 'data' in rules:
                rules = rules['data']
            count = len(rules)
            LOGGER.info("Processing %d %s rules", count, rule_type)
            for rule in rules:
                process_rule(rule_type, rule, data_key)

        # Process all rule types
        if api.capabilities.zone_based_firewall:
            policies = [p for p in coordinator.data.get('firewall_policies', []) if not p.get('predefined', False)]
            log_and_process_rules(policies, 'firewall_policy', 'firewall_policies')

        if api.capabilities.traffic_routes:
            log_and_process_rules(coordinator.data.get('traffic_routes', []), 'traffic_route', 'traffic_routes')

        log_and_process_rules(coordinator.data.get('port_forward_rules', []), 'port_forward', 'port_forward_rules')

        if api.capabilities.legacy_firewall:
            legacy_rules = coordinator.data.get('firewall_rules', {}).get('data', [])
            log_and_process_rules(legacy_rules, 'legacy_firewall', 'firewall_rules')
            log_and_process_rules(coordinator.data.get('traffic_rules', []), 'legacy_traffic', 'traffic_rules')

        return True

    except Exception as e:
        LOGGER.error("Error in switch setup: %s", str(e))
        raise