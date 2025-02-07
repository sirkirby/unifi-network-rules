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

    def _get_zone_name(self, zone_id: str) -> str:
        """Get zone name from zone ID."""
        if not self._zones_data or not zone_id:
            return "Unknown"
        
        zone = next((z for z in self._zones_data if z['_id'] == zone_id), None)
        return zone['name'] if zone else "Unknown"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        is_available = self.coordinator.last_update_success and self._item_data is not None
        _LOGGER.debug("Switch %s availability: %s", self._attr_name, is_available)
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
                    _LOGGER.info("State change verified for %s", self._attr_name)
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

    def __init__(self, coordinator, api, policy: Dict[str, Any], zones_data: List[Dict[str, Any]]):
        """Initialize the UDM Firewall Policy Switch."""
        super().__init__(coordinator, api, policy, zones_data)
        
        # Skip predefined policies
        if policy.get('predefined', False):
            _LOGGER.debug("Skipping predefined policy: %s", policy.get('name'))
            return

        source_zone = self._get_zone_name(policy.get('source', {}).get('zone_id'))
        dest_zone = self._get_zone_name(policy.get('destination', {}).get('zone_id'))
        
        self._attr_unique_id = f"firewall_policy_{policy['_id']}"
        self._attr_name = f"Firewall: {source_zone}->{dest_zone}: {policy.get('name', 'Unnamed')}"
        _LOGGER.info("Initialized firewall policy switch: %s (ID: %s)", self._attr_name, self._item_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.info("Turning on switch: %s", self._attr_name)
        await self._toggle(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.info("Turning off switch: %s", self._attr_name)
        await self._toggle(False)

    async def _toggle(self, new_state: bool) -> None:
        """Toggle the policy state."""
        try:
            if self._item_data.get('enabled') == new_state:
                _LOGGER.info("%s is already in desired state: %s", self._attr_name, new_state)
                return

            self._pending_state = new_state
            self.async_write_ha_state()

            success, error_message = await self._api.toggle_firewall_policy(self._item_id, new_state)
            
            if success:
                _LOGGER.info("API reports successful toggle for %s", self._attr_name)
                await asyncio.sleep(1)
                
                if await self._verify_state_change(new_state, self._api.get_firewall_policies):
                    _LOGGER.info("Successfully verified state change for %s", self._attr_name)
                else:
                    self._pending_state = None
                    raise HomeAssistantError(
                        f"Failed to verify state change for {self._attr_name}. "
                        f"Target state: {new_state}"
                    )
            else:
                self._pending_state = None
                self.async_write_ha_state()
                raise HomeAssistantError(f"Failed to toggle firewall policy: {error_message}")
                
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            _LOGGER.exception("Error toggling %s", self._attr_name)
            raise HomeAssistantError(f"Error toggling firewall policy: {str(e)}")

class UDMTrafficRouteSwitch(UDMBaseSwitch):
    """Representation of a UDM Traffic Route Switch."""

    def __init__(self, coordinator, api, route):
        """Initialize the UDM Traffic Route Switch."""
        super().__init__(coordinator, api, route)
        self._attr_unique_id = f"traffic_route_{route['_id']}"
        self._attr_name = f"Traffic Route: {route.get('description', 'Unnamed')}"
        _LOGGER.info("Initialized traffic route switch: %s (ID: %s)", self._attr_name, self._item_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.info("Turning on switch: %s", self._attr_name)
        await self._toggle(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.info("Turning off switch: %s", self._attr_name)
        await self._toggle(False)

    async def _toggle(self, new_state: bool) -> None:
        """Toggle the route state."""
        try:
            if self._item_data.get('enabled') == new_state:
                _LOGGER.info("%s is already in desired state: %s", self._attr_name, new_state)
                return

            self._pending_state = new_state
            self.async_write_ha_state()

            success, error_message = await self._api.toggle_traffic_route(self._item_id, new_state)
            
            if success:
                _LOGGER.info("API reports successful toggle for %s", self._attr_name)
                await asyncio.sleep(1)
                
                if await self._verify_state_change(new_state, self._api.get_traffic_routes):
                    _LOGGER.info("Successfully verified state change for %s", self._attr_name)
                else:
                    self._pending_state = None
                    raise HomeAssistantError(
                        f"Failed to verify state change for {self._attr_name}. "
                        f"Target state: {new_state}"
                    )
            else:
                self._pending_state = None
                self.async_write_ha_state()
                raise HomeAssistantError(f"Failed to toggle traffic route: {error_message}")
                
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            _LOGGER.exception("Error toggling %s", self._attr_name)
            raise HomeAssistantError(f"Error toggling traffic route: {str(e)}")

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the UniFi Network Rules switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]['coordinator']
    api = hass.data[DOMAIN][entry.entry_id]['api']

    _LOGGER.info("Setting up switches with coordinator data: %s", coordinator.data)
    
    # Get zone matrix data for better naming
    success, zones_data, error = await api.get_firewall_zone_matrix()
    if not success:
        _LOGGER.error("Failed to fetch zone matrix: %s", error)
        zones_data = []

    # Get entity registry
    entity_registry = async_get(hass)
    
    @callback
    def async_update_items():
        """Update entities."""
        new_entities = []
        existing_ids = set()
        
        # Track entities that should exist
        valid_entity_ids = set()
        
        # Handle firewall policies
        if coordinator.data and 'firewall_policies' in coordinator.data:
            policies = coordinator.data['firewall_policies']
            for policy in policies:
                if not policy.get('predefined', False):  # Skip predefined policies
                    entity_id = f"firewall_policy_{policy['_id']}"
                    valid_entity_ids.add(f"{DOMAIN}.{entity_id}")
                    if entity_id not in existing_ids:
                        new_entities.append(UDMFirewallPolicySwitch(coordinator, api, policy, zones_data))
                        existing_ids.add(entity_id)

        # Handle traffic routes
        if coordinator.data and 'traffic_routes' in coordinator.data:
            routes = coordinator.data['traffic_routes']
            for route in routes:
                entity_id = f"traffic_route_{route['_id']}"
                valid_entity_ids.add(f"{DOMAIN}.{entity_id}")
                if entity_id not in existing_ids:
                    new_entities.append(UDMTrafficRouteSwitch(coordinator, api, route))
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