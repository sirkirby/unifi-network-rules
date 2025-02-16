"""Support for UniFi Network Rules switches."""
from __future__ import annotations
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
from .utils.logger import log_call

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
        # For test environment - allow coordinator to provide hass
        if not hasattr(self, 'hass') and hasattr(coordinator, 'hass'):
            self.hass = coordinator.hass

    def _safe_write_state(self) -> None:
        """Safely write state if we're in a real HA environment."""
        if hasattr(self, 'async_write_ha_state') and hasattr(self, 'hass') and self.hass is not None:
            self.async_write_ha_state()

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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data is None:
            self._item_data = None
            self._safe_write_state()
            return

        # Find the updated item data that matches this entity
        if 'traffic_routes' in self.coordinator.data:
            items = self.coordinator.data['traffic_routes']
            item = next((i for i in items if i.get('_id') == self._item_id), None)
            if item:
                self._item_data = item
                self._safe_write_state()
                return

        if 'firewall_policies' in self.coordinator.data:
            items = self.coordinator.data['firewall_policies']
            item = next((i for i in items if i.get('_id') == self._item_id), None)
            if item:
                self._item_data = item
                self._safe_write_state()
                return

        if 'firewall_rules' in self.coordinator.data:
            items = self.coordinator.data['firewall_rules'].get('data', [])
            item = next((i for i in items if i.get('_id') == self._item_id), None)
            if item:
                self._item_data = item
                self._safe_write_state()
                return

        if 'traffic_rules' in self.coordinator.data:
            items = self.coordinator.data['traffic_rules']
            item = next((i for i in items if i.get('_id') == self._item_id), None)
            if item:
                self._item_data = item
                self._safe_write_state()
                return

        # If we get here, the item no longer exists in the coordinator data
        self._item_data = None
        self._safe_write_state()

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

    async def _execute_toggle(self, new_state: bool, toggle_fn, verify_fn, entity_name: str) -> None:
        """Execute toggle with verification using a common method."""
        try:
            self._pending_state = new_state
            self._safe_write_state()
            success, error = await toggle_fn(self._item_id, new_state)
            if success and await self._verify_state_change(new_state, verify_fn):
                return
            self._pending_state = None
            self._safe_write_state()
            raise HomeAssistantError(f"Failed to toggle {entity_name}: {error}")
        except Exception as e:
            self._pending_state = None
            self._safe_write_state()
            raise HomeAssistantError(f"Error toggling {entity_name}: {str(e)}")

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
        """Toggle the firewall policy state."""
        await self._execute_toggle(new_state, self._api.toggle_firewall_policy, self._api.get_firewall_policies, "firewall policy")

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
        """Toggle the legacy firewall rule state."""
        await self._execute_toggle(new_state, self._api.toggle_legacy_firewall_rule, self._api.get_legacy_firewall_rules, "firewall rule")

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
        """Toggle the legacy traffic rule state."""
        await self._execute_toggle(new_state, self._api.toggle_legacy_traffic_rule, self._api.get_legacy_traffic_rules, "traffic rule")

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
        """Toggle the traffic route state."""
        await self._execute_toggle(new_state, self._api.toggle_traffic_route, self._api.get_traffic_routes, "traffic route")

class UDMPortForwardRuleSwitch(UDMBaseSwitch):
    """Representation of a UDM Port Forward Rule Switch."""

    def __init__(self, coordinator, api, rule: Dict[str, Any]):
        """Initialize the UDM Port Forward Rule Switch."""
        super().__init__(coordinator, api, rule)
        self._attr_unique_id = f"port_forward_rule_{rule['_id']}"
        name = rule.get('name', 'Unnamed')
        proto = rule.get('proto', 'unknown')
        dst_port = rule.get('dst_port', '')
        fwd_port = rule.get('fwd_port', '')
        fwd_ip = rule.get('fwd', '')
        
        # Format name to show forwarding details
        if dst_port == fwd_port:
            port_info = f"port {dst_port}"
        else:
            port_info = f"port {dst_port}->{fwd_port}"
            
        self._attr_name = f"Port Forward: {name} ({proto} {port_info} to {fwd_ip}) ({rule['_id'][-4:]})"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._toggle(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._toggle(False)

    async def _toggle(self, new_state: bool) -> None:
        """Toggle the port forward rule state."""
        await self._execute_toggle(new_state, self._api.toggle_port_forward_rule, self._api.get_port_forward_rules, "port forward rule")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data is None:
            self._item_data = None
            self._safe_write_state()
            return

        if 'port_forward_rules' in self.coordinator.data:
            items = self.coordinator.data['port_forward_rules']
            item = next((i for i in items if i.get('_id') == self._item_id), None)
            if item:
                self._item_data = item
                self._safe_write_state()
                return

        # If we get here, the item no longer exists in the coordinator data
        self._item_data = None
        self._safe_write_state()

@log_call
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the UniFi Network Rules switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]['coordinator']
    api = hass.data[DOMAIN][entry.entry_id]['api']

    _LOGGER.info("Setting up switches with coordinator data: %s", coordinator.data)
    
    # Detect UDM capabilities if not already done
    if not hasattr(api, 'capabilities'):
        if not await api.detect_capabilities():
            _LOGGER.error(
                "Failed to detect any UDM capabilities. No entities will be created. "
                "Please check your network connection, credentials, and device status."
            )
            return

    # Validate that we have at least one working capability
    if not any([
        api.capabilities.traffic_routes,
        api.capabilities.zone_based_firewall,
        api.capabilities.legacy_firewall
    ]):
        _LOGGER.error(
            "No supported capabilities detected on the UniFi device. "
            "This integration requires at least one of: "
            "traffic routes, zone-based firewall, or legacy firewall support."
        )
        return

    # Log detected capabilities for debugging
    _LOGGER.info(
        "Setting up entities with detected capabilities - "
        "Traffic Routes: %s, Zone-based Firewall: %s, Legacy Firewall: %s",
        api.capabilities.traffic_routes,
        api.capabilities.zone_based_firewall,
        api.capabilities.legacy_firewall
    )

    # Get zone matrix data for better naming if using zone-based firewall
    zones_data = []
    if api.capabilities.zone_based_firewall:
        success, zones_data, error = await api.get_firewall_zone_matrix()
        if not success:
            _LOGGER.error(
                "Failed to fetch zone matrix: %s. "
                "Zone-based firewall rules will use generic naming.",
                error
            )

    # Get entity registry
    entity_registry = async_get(hass)
    
    # Track existing entities to prevent duplicates
    existing_entities = {}
    
    @callback
    def async_update_items(now=None):
        """Update entities when coordinator data changes."""
        if not coordinator.data:
            _LOGGER.warning("No data available from coordinator")
            return

        current_entities = set()
        new_entities = []
        
        try:
            # Process traffic routes if capability is available
            if api.capabilities.traffic_routes and 'traffic_routes' in coordinator.data:
                for route in coordinator.data['traffic_routes']:
                    try:
                        entity_id = f"network_route_{route['_id']}"
                        current_entities.add(entity_id)
                        if entity_id not in existing_entities:
                            new_entity = UDMTrafficRouteSwitch(coordinator, api, route)
                            new_entities.append(new_entity)
                            existing_entities[entity_id] = new_entity
                    except Exception as e:
                        _LOGGER.error("Error creating traffic route entity: %s", str(e))
            
            # Process port forward rules
            if 'port_forward_rules' in coordinator.data:
                for rule in coordinator.data['port_forward_rules']:
                    try:
                        entity_id = f"port_forward_rule_{rule['_id']}"
                        current_entities.add(entity_id)
                        if entity_id not in existing_entities:
                            new_entity = UDMPortForwardRuleSwitch(coordinator, api, rule)
                            new_entities.append(new_entity)
                            existing_entities[entity_id] = new_entity
                    except Exception as e:
                        _LOGGER.error("Error creating port forward rule entity: %s", str(e))

            # Process firewall rules based on capabilities
            if api.capabilities.zone_based_firewall:
                # Process zone-based firewall policies
                if 'firewall_policies' in coordinator.data:
                    for policy in coordinator.data['firewall_policies']:
                        try:
                            if not policy.get('predefined', False):
                                entity_id = f"network_policy_{policy['_id']}"
                                current_entities.add(entity_id)
                                if entity_id not in existing_entities:
                                    new_entity = UDMFirewallPolicySwitch(coordinator, api, policy, zones_data)
                                    new_entities.append(new_entity)
                                    existing_entities[entity_id] = new_entity
                        except Exception as e:
                            _LOGGER.error("Error creating firewall policy entity: %s", str(e))
            elif api.capabilities.legacy_firewall:
                # Process legacy firewall rules
                if 'firewall_rules' in coordinator.data:
                    try:
                        for rule in coordinator.data['firewall_rules'].get('data', []):
                            try:
                                entity_id = f"network_rule_firewall_{rule['_id']}"
                                current_entities.add(entity_id)
                                if entity_id not in existing_entities:
                                    new_entity = UDMLegacyFirewallRuleSwitch(coordinator, api, rule)
                                    new_entities.append(new_entity)
                                    existing_entities[entity_id] = new_entity
                            except Exception as e:
                                _LOGGER.error("Error creating legacy firewall rule entity: %s", str(e))

                        # Process legacy traffic rules
                        if 'traffic_rules' in coordinator.data:
                            for rule in coordinator.data['traffic_rules']:
                                try:
                                    entity_id = f"network_rule_traffic_{rule['_id']}"
                                    current_entities.add(entity_id)
                                    if entity_id not in existing_entities:
                                        new_entity = UDMLegacyTrafficRuleSwitch(coordinator, api, rule)
                                        new_entities.append(new_entity)
                                        existing_entities[entity_id] = new_entity
                                except Exception as e:
                                    _LOGGER.error("Error creating legacy traffic rule entity: %s", str(e))
                    except Exception as e:
                        _LOGGER.error("Error processing legacy rules: %s", str(e))

            # Remove entities that no longer exist
            for entity_id in list(existing_entities.keys()):
                if entity_id not in current_entities:
                    entity = existing_entities.pop(entity_id)
                    hass.async_create_task(async_remove_entity(hass, entity_registry, entity))

            # Add new entities
            if new_entities:
                async_add_entities(new_entities)
                _LOGGER.info("Added %d new entities", len(new_entities))

        except Exception as e:
            _LOGGER.exception("Unexpected error during entity update: %s", str(e))

    async def async_remove_entity(hass: HomeAssistant, registry: EntityRegistry, entity: SwitchEntity):
        """Remove entity from Home Assistant."""
        if entity.entity_id:
            registry.async_remove(entity.entity_id)
            _LOGGER.info("Removed entity %s", entity.entity_id)

    # Set up initial entities
    async_update_items()

    # Register update listener
    coordinator.async_add_listener(async_update_items)
    entry.async_on_unload(lambda: coordinator.async_remove_listener(async_update_items))

    return True

def async_entries_for_config_entry(registry: EntityRegistry, config_entry_id: str) -> List[Any]:
    """Get all entities for a config entry."""
    return [
        entry for entry in registry.entities.values()
        if entry.config_entry_id == config_entry_id
    ]