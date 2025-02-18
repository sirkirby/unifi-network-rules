"""Support for UniFi Network Rules switches."""
from __future__ import annotations

from typing import Any, Dict, Optional
import asyncio

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .entity_loader import UnifiRuleEntityLoader
from .utils.logger import log_call
from .rule_template import RuleType

class UDMBaseSwitch(CoordinatorEntity, SwitchEntity):
    """Base class for UDM switches."""

    def __init__(self, coordinator, api, item_data: Dict[str, Any], data_key: str):
        """Initialize the base switch."""
        super().__init__(coordinator)
        self._api = api
        self._item_data = item_data
        self._item_id = item_data['_id']
        self._data_key = data_key
        self._pending_state = None
        self.entity_category = EntityCategory.CONFIG
        self._entity_loader = None
        
        # Check if this entity type supports websockets
        self._websocket_supported = self._api.supports_websocket(self._data_key)
        if self._websocket_supported:
            LOGGER.debug("Websocket updates supported for %s", self._data_key)
        else:
            LOGGER.debug("Falling back to REST API for %s updates", self._data_key)

    def _get_rules_key(self) -> str:
        """Get the key for accessing rules in coordinator data."""
        return self._data_key

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        rules = self.coordinator.data.get(self._get_rules_key(), [])
        if isinstance(rules, dict) and 'data' in rules:
            rules = rules['data']
        return (
            self.coordinator.last_update_success and
            any(rule.get('_id') == self._item_id for rule in rules)
        )

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        if self._pending_state is not None:
            return self._pending_state
        return bool(self._item_data.get('enabled', False))
    
    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # Get entity loader from coordinator data after entity is added to hass
        if self.coordinator.config_entry and DOMAIN in self.coordinator.hass.data:
            entry_data = self.coordinator.hass.data[DOMAIN].get(self.coordinator.config_entry.entry_id, {})
            self._entity_loader = entry_data.get('entity_loader')
        
        # Start tracking this specific rule in the coordinator
        self.coordinator.track_rule_changes(self._item_id)
        
        # When entity is removed, stop tracking the rule
        self.async_on_remove(
            lambda: self.coordinator.stop_tracking_rule(self._item_id)
        )

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity being removed from Home Assistant."""
        await super().async_will_remove_from_hass()
        
        # Ensure we cleanup when entity is removed
        self.coordinator.stop_tracking_rule(self._item_id)
        
        # Remove from entity loader if available
        if self._entity_loader:
            platform = self.__class__.__name__.lower().replace('udm', '').replace('switch', '')
            self._entity_loader.async_handle_entity_removal(platform, self.unique_id)

    async def _verify_state_change(self, target_state: bool, get_method, max_attempts: int = 3) -> bool:
        """Verify that the state change was successful."""
        for attempt in range(max_attempts):
            success, item, error = await get_method(self._item_id)
            if success and item and item.get('enabled') == target_state:
                self._item_data = item
                return True
            await asyncio.sleep(1)
        return False

    async def _execute_toggle(self, new_state: bool, toggle_fn, verify_fn, entity_name: str) -> None:
        """Execute toggle with verification using a common method."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()
            success, error = await toggle_fn(self._item_id, new_state)
            if success and await self._verify_state_change(new_state, verify_fn):
                return
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to toggle {entity_name}: {error}")
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling {entity_name}: {str(e)}")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data update."""
        rules = self.coordinator.data.get(self._get_rules_key(), [])
        if isinstance(rules, dict) and 'data' in rules:
            rules = rules['data']
        updated_item = next(
            (item for item in rules if item.get('_id') == self._item_id), 
            None
        )
        if updated_item:
            self._item_data = updated_item
            self.async_write_ha_state()
            return
        # If we get here, the item no longer exists
        self._item_data = None
        self.async_write_ha_state()
        
        # Remove entity if entity loader is available
        if self._entity_loader:
            self._entity_loader.async_remove_entity('switch', self.unique_id)

class UDMFirewallPolicySwitch(UDMBaseSwitch):
    """Representation of a UDM Firewall Policy Switch."""

    def __init__(self, coordinator, api, policy: Dict[str, Any]):
        """Initialize the UDM Firewall Policy Switch."""
        super().__init__(coordinator, api, policy, 'firewall_policies')
        
        self._attr_unique_id = f"network_policy_{policy['_id']}"
        base_name = policy.get('name', 'Unnamed')
        self._attr_name = f"Network Policy: {base_name} ({policy['_id'][-4:]})"

    @log_call
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._toggle(True)

    @log_call
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._toggle(False)

    @log_call
    async def _toggle(self, new_state: bool) -> None:
        """Toggle the firewall policy state."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()
            
            if self._websocket_supported:
                # Create update task and wait for result
                update_task = self.coordinator._handle_websocket_update(
                    'firewall_policies',
                    'update',
                    {**self._item_data, 'enabled': new_state}
                )
                success = await update_task
                
                if not success:
                    # Fall back to REST API if websocket update fails
                    await self._execute_toggle(
                        new_state,
                        self._api.toggle_firewall_policy,
                        self._api.get_firewall_policy,
                        "firewall policy"
                    )
            else:
                # Use REST API directly
                await self._execute_toggle(
                    new_state,
                    self._api.toggle_firewall_policy,
                    self._api.get_firewall_policy,
                    "firewall policy"
                )
                
            self._pending_state = None
            self.async_write_ha_state()
            
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling firewall policy: {str(e)}")

class UDMTrafficRouteSwitch(UDMBaseSwitch):
    """Representation of a UDM Traffic Route Switch."""

    def __init__(self, coordinator, api, route: Dict[str, Any]):
        """Initialize the UDM Traffic Route Switch."""
        super().__init__(coordinator, api, route, 'traffic_routes')
        self._attr_unique_id = f"network_route_{route['_id']}"
        desc = route.get('description', 'Unnamed')
        self._attr_name = f"Network Route: {desc} ({route['_id'][-4:]})"

    @log_call
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._toggle(True)

    @log_call
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._toggle(False)

    @log_call
    async def _toggle(self, new_state: bool) -> None:
        """Toggle the traffic route state."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()
            
            if self._websocket_supported:
                # Create a copy of current state for verification
                original_data = dict(self._item_data)
                
                # Create update task
                update_task = self.coordinator._handle_websocket_update(
                    'traffic_routes',
                    'update',
                    {**self._item_data, 'enabled': new_state}
                )
                success = await update_task
                
                if not success:
                    # Fall back to REST API
                    await self._execute_toggle(
                        new_state,
                        self._api.toggle_traffic_route,
                        lambda x: self.coordinator.get_rule(self._item_id),  # Use coordinator's cached data
                        "traffic route"
                    )
            else:
                await self._execute_toggle(
                    new_state,
                    self._api.toggle_traffic_route,
                    lambda x: self.coordinator.get_rule(self._item_id),  # Use coordinator's cached data
                    "traffic route"
                )
            
            # Wait briefly for state to propagate
            await asyncio.sleep(0.5)
            
            # Verify state change using coordinator data
            current_rule = self.coordinator.get_rule(self._item_id)
            if current_rule and current_rule.get('enabled') == new_state:
                self._item_data = current_rule
            
            self._pending_state = None
            self.async_write_ha_state()
            
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling traffic route: {str(e)}")

class UDMLegacyRuleSwitch(UDMBaseSwitch):
    """Base class for legacy rule switches."""

    def __init__(self, coordinator, api, rule: Dict[str, Any], rule_type: str, data_key: str):
        """Initialize the legacy rule switch."""
        super().__init__(coordinator, api, rule, data_key)
        self._rule_type = rule_type
        rule_name = rule.get('name', rule.get('description', 'Unnamed'))
        self._attr_unique_id = f"network_rule_{rule_type}_{rule['_id']}"
        self._attr_name = f"Network Rule: {rule_name} ({rule['_id'][-4:]})"

class UDMLegacyFirewallRuleSwitch(UDMLegacyRuleSwitch):
    """Representation of a UDM Legacy Firewall Rule Switch."""

    def __init__(self, coordinator, api, rule: Dict[str, Any]):
        """Initialize the UDM Legacy Firewall Rule Switch."""
        super().__init__(coordinator, api, rule, "firewall", "firewall_rules")

    @log_call
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the rule."""
        await self._toggle(True)

    @log_call
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the rule."""
        await self._toggle(False)

    @log_call
    async def _toggle(self, new_state: bool) -> None:
        """Toggle the rule state."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()
            
            if self._websocket_supported:
                update_task = self.coordinator._handle_websocket_update(
                    'firewall_rules',
                    'update',
                    {**self._item_data, 'enabled': new_state}
                )
                success = await update_task
                
                if not success:
                    await self._execute_toggle(
                        new_state,
                        self._api.toggle_legacy_firewall_rule,
                        self._api.get_legacy_firewall_rule,
                        "legacy firewall rule"
                    )
            else:
                await self._execute_toggle(
                    new_state,
                    self._api.toggle_legacy_firewall_rule,
                    self._api.get_legacy_firewall_rule,
                    "legacy firewall rule"
                )
                
            self._pending_state = None
            self.async_write_ha_state()
            
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling legacy firewall rule: {str(e)}")

class UDMLegacyTrafficRuleSwitch(UDMLegacyRuleSwitch):
    """Representation of a UDM Legacy Traffic Rule Switch."""

    def __init__(self, coordinator, api, rule: Dict[str, Any]):
        """Initialize the UDM Legacy Traffic Rule Switch."""
        super().__init__(coordinator, api, rule, "traffic", "traffic_rules")

    @log_call
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the rule."""
        await self._toggle(True)

    @log_call
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the rule."""
        await self._toggle(False)

    @log_call
    async def _toggle(self, new_state: bool) -> None:
        """Toggle the rule state."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()
            
            if self._websocket_supported:
                update_task = self.coordinator._handle_websocket_update(
                    'traffic_rules',
                    'update',
                    {**self._item_data, 'enabled': new_state}
                )
                success = await update_task
                
                if not success:
                    await self._execute_toggle(
                        new_state,
                        self._api.toggle_legacy_traffic_rule,
                        lambda x: (True, self._item_data, None),
                        "legacy traffic rule"
                    )
            else:
                await self._execute_toggle(
                    new_state,
                    self._api.toggle_legacy_traffic_rule,
                    lambda x: (True, self._item_data, None),
                    "legacy traffic rule"
                )
                
            self._pending_state = None
            self.async_write_ha_state()
            
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling legacy traffic rule: {str(e)}")

class UDMPortForwardRuleSwitch(UDMBaseSwitch):
    """Representation of a UDM Port Forward Rule Switch."""

    def __init__(self, coordinator, api, rule: Dict[str, Any]):
        """Initialize the UDM Port Forward Rule Switch."""
        super().__init__(coordinator, api, rule, 'port_forward_rules')
        
        name = rule.get('name', 'Unnamed')
        self._attr_unique_id = f"port_forward_{name.lower().replace(' ', '_')}_{rule['_id'][-4:]}"
        
        fwd_ip = rule.get('fwd', '')
        self._attr_name = f"Port Forward: {name} ({fwd_ip}) ({rule['_id'][-4:]})"

    @log_call
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._toggle(True)

    @log_call
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._toggle(False)

    @log_call
    async def _toggle(self, new_state: bool) -> None:
        """Toggle the port forward rule state."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()
            
            if self._websocket_supported:
                update_task = self.coordinator._handle_websocket_update(
                    'port_forward_rules',
                    'update',
                    {**self._item_data, 'enabled': new_state}
                )
                success = await update_task
                
                if not success:
                    await self._execute_toggle(
                        new_state,
                        self._api.toggle_port_forward_rule,
                        lambda x: (True, self._item_data, None),
                        "port forward rule"
                    )
            else:
                await self._execute_toggle(
                    new_state,
                    self._api.toggle_port_forward_rule,
                    lambda x: (True, self._item_data, None),
                    "port forward rule"
                )
                
            self._pending_state = None
            self.async_write_ha_state()
            
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling port forward rule: {str(e)}")

@log_call
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    """Set up the UniFi Network Rules switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]['coordinator']
    api = hass.data[DOMAIN][entry.entry_id]['api']
    entity_loader = hass.data[DOMAIN][entry.entry_id]['entity_loader']

    # Register switch platform
    entity_loader.async_setup_platform('switch', async_add_entities)

    # Define entity configs
    entity_configs = []

    # Add firewall policies for zone-based firewall
    if api.capabilities.zone_based_firewall:
        for policy in coordinator.data.get('firewall_policies', []):
            if not policy.get('predefined', False):
                entity_configs.append({
                    'type': 'firewall_policy',
                    'policy': policy,
                    'data_key': 'firewall_policies'
                })

    # Add traffic routes
    if api.capabilities.traffic_routes:
        for route in coordinator.data.get('traffic_routes', []):
            entity_configs.append({
                'type': 'traffic_route',
                'route': route,
                'data_key': 'traffic_routes'
            })

    # Add port forward rules
    for rule in coordinator.data.get('port_forward_rules', []):
        entity_configs.append({
            'type': 'port_forward',
            'rule': rule,
            'data_key': 'port_forward_rules'
        })

    # Add legacy firewall rules if using legacy mode
    if api.capabilities.legacy_firewall:
        legacy_rules = coordinator.data.get('firewall_rules', {}).get('data', [])
        for rule in legacy_rules:
            entity_configs.append({
                'type': 'legacy_firewall',
                'rule': rule,
                'data_key': 'firewall_rules'
            })
        
        # Add legacy traffic rules
        for rule in coordinator.data.get('traffic_rules', []):
            entity_configs.append({
                'type': 'legacy_traffic',
                'rule': rule,
                'data_key': 'traffic_rules'
            })

    # Create entities based on configs
    for config in entity_configs:
        unique_id = _get_unique_id(config)
        if unique_id:
            entity_loader.async_add_entity(
                platform='switch',
                unique_id=unique_id,
                entity_factory=lambda c=config: _create_entity(coordinator, api, c),
                data_key=config['data_key']
            )

    return True

def _get_unique_id(config: dict) -> str:
    """Generate unique ID based on entity config."""
    if config['type'] == 'firewall_policy':
        return f"network_policy_{config['policy']['_id']}"
    elif config['type'] == 'traffic_route':
        return f"network_route_{config['route']['_id']}"
    elif config['type'] == 'port_forward':
        rule = config['rule']
        name = rule.get('name', 'unnamed').lower().replace(' ', '_')
        return f"port_forward_{name}_{rule['_id'][-4:]}"
    elif config['type'] == 'legacy_firewall':
        return f"network_rule_firewall_{config['rule']['_id']}"
    elif config['type'] == 'legacy_traffic':
        return f"network_rule_traffic_{config['rule']['_id']}"
    return None

def _create_entity(coordinator, api, config):
    """Create appropriate entity based on config."""
    if config['type'] == 'firewall_policy':
        return UDMFirewallPolicySwitch(coordinator, api, config['policy'])
    elif config['type'] == 'traffic_route':
        return UDMTrafficRouteSwitch(coordinator, api, config['route'])
    elif config['type'] == 'port_forward':
        return UDMPortForwardRuleSwitch(coordinator, api, config['rule'])
    elif config['type'] == 'legacy_firewall':
        return UDMLegacyFirewallRuleSwitch(coordinator, api, config['rule'])
    elif config['type'] == 'legacy_traffic':
        return UDMLegacyTrafficRuleSwitch(coordinator, api, config['rule'])