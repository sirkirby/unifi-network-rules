"""Support for UniFi Network Rules switches."""
import logging
import asyncio
from typing import Any, Dict, List
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_registry import EntityRegistry, async_get

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

def _get_zone_name(zone_id: str, zones_data: List[Dict[str, Any]]) -> str:
    """Get zone name from zone ID."""
    if not zones_data or not zone_id:
        return "Unknown"
    
    zone = next((z for z in zones_data if z['_id'] == zone_id), None)
    return zone['name'] if zone else "Unknown"

class UDMBaseSwitch(CoordinatorEntity, SwitchEntity):
    """Base class for UDM switches."""

    def __init__(self, coordinator, api, item_data: Dict[str, Any], zones_data: List[Dict[str, Any]] = None):
        """Initialize the base switch."""
        super().__init__(coordinator)
        self._api = api
        self._item_data = item_data
        self._item_id = item_data['_id']
        self._pending_state = None
        self._zones_data = zones_data
        self.entity_category = EntityCategory.CONFIG

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        is_available = self.coordinator.last_update_success and self._item_data is not None
        return is_available

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        if self._pending_state is not None:
            return self._pending_state
        return bool(self._item_data.get('enabled', False))

    async def _verify_state_change(self, target_state: bool, get_method, max_attempts: int = 3) -> bool:
        """Verify that the state change was successful."""
        for attempt in range(max_attempts):
            try:
                success, items, error = await get_method()
                if not success:
                    _LOGGER.error("Failed to fetch items for verification: %s", error)
                    await asyncio.sleep(2)
                    continue

                current_item = next((i for i in (items or []) if i['_id'] == self._item_id), None)
                if not current_item:
                    _LOGGER.error("Item not found during verification")
                    await asyncio.sleep(2)
                    continue

                current_state = current_item.get('enabled', False)
                if current_state == target_state:
                    await self.coordinator.async_request_refresh()
                    return True

                _LOGGER.warning(
                    "State verification attempt %d/%d failed for %s. Expected: %s, Got: %s",
                    attempt + 1,
                    max_attempts,
                    self._attr_name,
                    target_state,
                    current_state
                )
                await asyncio.sleep(2)
            except Exception as e:
                _LOGGER.error("Error during state verification: %s", str(e))
                await asyncio.sleep(2)

        return False

class UDMFirewallPolicySwitch(UDMBaseSwitch):
    """Representation of a UDM Firewall Policy Switch."""

    def __init__(self, coordinator, api, policy: Dict[str, Any], zones_data: List[Dict[str, Any]], name: str = None):
        """Initialize the UDM Firewall Policy Switch."""
        super().__init__(coordinator, api, policy, zones_data)
        
        if policy.get('predefined', False):
            _LOGGER.debug("Skipping predefined policy: %s", policy.get('name'))
            return

        self._attr_unique_id = f"network_policy_{policy['_id']}"
        if name:
            self._attr_name = name
        else:
            source_zone = _get_zone_name(policy.get('source', {}).get('zone_id'), zones_data)
            dest_zone = _get_zone_name(policy.get('destination', {}).get('zone_id'), zones_data)
            base_name = policy.get('name', 'Unnamed')
            self._attr_name = f"Network Policy: {source_zone}->{dest_zone}: {base_name} ({policy['_id'][-4:]})"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._toggle(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._toggle(False)

    async def _toggle(self, new_state: bool) -> None:
        """Toggle the policy state."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()

            success, error = await self._api.toggle_firewall_policy(self._item_id, new_state)
            
            if success:
                if await self._verify_state_change(new_state, self._api.get_firewall_policies):
                    return
                
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to toggle firewall policy: {error}")
                
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling firewall policy: {str(e)}")

class UDMLegacyRuleSwitch(UDMBaseSwitch):
    """Base class for legacy rule switches."""

    def __init__(self, coordinator, api, rule: Dict[str, Any], rule_type: str):
        """Initialize the legacy rule switch."""
        super().__init__(coordinator, api, rule)
        self._rule_type = rule_type
        rule_name = rule.get('name', rule.get('description', 'Unnamed'))
        self._attr_unique_id = f"network_rule_{rule_type}_{rule['_id']}"
        self._attr_name = f"Network Rule: {rule_name} ({rule['_id'][-4:]})"

class UDMLegacyFirewallRuleSwitch(UDMLegacyRuleSwitch):
    """Representation of a UDM Legacy Firewall Rule Switch."""

    def __init__(self, coordinator, api, rule: Dict[str, Any]):
        """Initialize the UDM Legacy Firewall Rule Switch."""
        super().__init__(coordinator, api, rule, "firewall")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._toggle(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._toggle(False)

    async def _toggle(self, new_state: bool) -> None:
        """Toggle the rule state."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()

            success, error = await self._api.toggle_legacy_firewall_rule(self._item_id, new_state)
            
            if success:
                if await self._verify_state_change(new_state, self._api.get_legacy_firewall_rules):
                    return
                
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to toggle firewall rule: {error}")
                
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling firewall rule: {str(e)}")

class UDMLegacyTrafficRuleSwitch(UDMLegacyRuleSwitch):
    """Representation of a UDM Legacy Traffic Rule Switch."""

    def __init__(self, coordinator, api, rule: Dict[str, Any]):
        """Initialize the UDM Legacy Traffic Rule Switch."""
        super().__init__(coordinator, api, rule, "traffic")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._toggle(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._toggle(False)

    async def _toggle(self, new_state: bool) -> None:
        """Toggle the rule state."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()

            success, error = await self._api.toggle_legacy_traffic_rule(self._item_id, new_state)
            
            if success:
                if await self._verify_state_change(new_state, self._api.get_legacy_traffic_rules):
                    return
                
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to toggle traffic rule: {error}")
                
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling traffic rule: {str(e)}")

class UDMTrafficRouteSwitch(UDMBaseSwitch):
    """Representation of a UDM Traffic Route Switch."""

    def __init__(self, coordinator, api, route: Dict[str, Any]):
        """Initialize the UDM Traffic Route Switch."""
        super().__init__(coordinator, api, route)
        self._attr_unique_id = f"network_route_{route['_id']}"
        desc = route.get('description', 'Unnamed')
        self._attr_name = f"Network Route: {desc} ({route['_id'][-4:]})"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._toggle(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._toggle(False)

    async def _toggle(self, new_state: bool) -> None:
        """Toggle the route state."""
        try:
            self._pending_state = new_state
            self.async_write_ha_state()

            success, error = await self._api.toggle_traffic_route(self._item_id, new_state)
            
            if success:
                if await self._verify_state_change(new_state, self._api.get_traffic_routes):
                    return
                
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to toggle traffic route: {error}")
                
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Error toggling traffic route: {str(e)}")

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the UniFi Network Rules switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]['coordinator']
    api = hass.data[DOMAIN][entry.entry_id]['api']

    _LOGGER.info("Setting up switches with coordinator data: %s", coordinator.data)
    
    # Detect UDM capabilities if not already done
    if not hasattr(api, 'capabilities'):
        if not await api.detect_capabilities():
            _LOGGER.error("Failed to detect UDM capabilities")
            return

    # Get zone matrix data for better naming if using zone-based firewall
    zones_data = []
    if api.capabilities.zone_based_firewall:
        success, zones_data, error = await api.get_firewall_zone_matrix()
        if not success:
            _LOGGER.error("Failed to fetch zone matrix: %s", error)

    # Get entity registry
    entity_registry = async_get(hass)
    
    @callback
    def async_update_items():
        """Update entities."""
        new_entities = []
        existing_ids = set()
        
        # Track entities that should exist
        valid_entity_ids = set()
        
        # Handle traffic routes (available in both modes)
        if coordinator.data and 'traffic_routes' in coordinator.data:
            routes = coordinator.data['traffic_routes']
            for route in routes:
                entity_id = f"network_route_{route['_id']}"
                valid_entity_ids.add(f"{DOMAIN}.{entity_id}")
                if entity_id not in existing_ids:
                    new_entities.append(UDMTrafficRouteSwitch(coordinator, api, route))
                    existing_ids.add(entity_id)
        
        if api.capabilities.zone_based_firewall:
            # Handle firewall policies for zone-based firewall
            if coordinator.data and 'firewall_policies' in coordinator.data:
                policies = coordinator.data['firewall_policies']
                for policy in policies:
                    if not policy.get('predefined', False):
                        entity_id = f"network_policy_{policy['_id']}"
                        valid_entity_ids.add(f"{DOMAIN}.{entity_id}")
                        if entity_id not in existing_ids:
                            new_entities.append(UDMFirewallPolicySwitch(coordinator, api, policy, zones_data))
                            existing_ids.add(entity_id)

        if api.capabilities.legacy_firewall:
            # Handle legacy firewall rules
            if coordinator.data and 'firewall_rules' in coordinator.data:
                rules = coordinator.data['firewall_rules'].get('data', [])
                for rule in rules:
                    entity_id = f"network_rule_firewall_{rule['_id']}"
                    valid_entity_ids.add(f"{DOMAIN}.{entity_id}")
                    if entity_id not in existing_ids:
                        new_entities.append(UDMLegacyFirewallRuleSwitch(coordinator, api, rule))
                        existing_ids.add(entity_id)

            # Handle legacy traffic rules
            if coordinator.data and 'traffic_rules' in coordinator.data:
                rules = coordinator.data['traffic_rules']
                for rule in rules:
                    entity_id = f"network_rule_traffic_{rule['_id']}"
                    valid_entity_ids.add(f"{DOMAIN}.{entity_id}")
                    if entity_id not in existing_ids:
                        new_entities.append(UDMLegacyTrafficRuleSwitch(coordinator, api, rule))
                        existing_ids.add(entity_id)

        # Clean up old entities from the registry
        _LOGGER.debug("Valid entity IDs: %s", valid_entity_ids)
        
        all_entities = async_entries_for_config_entry(entity_registry, entry.entry_id)
        for entity in all_entities:
            if entity.entity_id not in valid_entity_ids:
                _LOGGER.info("Removing old entity: %s", entity.entity_id)
                entity_registry.async_remove(entity.entity_id)

        if new_entities:
            async_add_entities(new_entities)

    # Initial entity setup
    async_update_items()
    
    # Register callback for future updates
    entry.async_on_unload(coordinator.async_add_listener(async_update_items))


def async_entries_for_config_entry(registry: EntityRegistry, config_entry_id: str) -> List[Any]:
    """Get all entities for a config entry."""
    return [
        entry for entry in registry.entities.values()
        if entry.config_entry_id == config_entry_id
    ]