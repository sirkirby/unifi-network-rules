"""UniFi Network Rules entity loader and management."""
from __future__ import annotations

import logging
from typing import Any, Callable, Generic, TypeVar
from collections.abc import Mapping
from dataclasses import dataclass

from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, LOGGER
from .coordinator import UDMUpdateCoordinator

T = TypeVar("T", bound=Entity)

@dataclass
class EntityDefinition:
    """Definition for entity creation."""
    unique_id: str
    platform: str
    factory: Callable[[], T]
    data_key: str  # Add data_key to track which data type this entity uses

class UnifiRuleEntityLoader(Generic[T]):
    """Handles loading and unloading of UniFi rule entities."""
    
    def __init__(self, hass: HomeAssistant, coordinator: UDMUpdateCoordinator) -> None:
        """Initialize the entity loader."""
        self.hass = hass
        self.coordinator = coordinator
        self.entities: dict[str, set[str]] = {}
        self._entity_definitions: dict[str, EntityDefinition] = {}
        self._async_add_entities: dict[str, AddEntitiesCallback] = {}
        self._pending_entities: dict[str, list[T]] = {}
        self._data_subscriptions: dict[str, set[str]] = {}  # Track entities by data type
        self._initialized = False
        
    @callback
    def async_setup_platform(
        self,
        platform: str,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        """Set up an entity platform."""
        self._async_add_entities[platform] = async_add_entities
        
        # Add any pending entities for this platform
        if platform in self._pending_entities and self._pending_entities[platform]:
            async_add_entities(self._pending_entities.pop(platform))
        self._initialized = True
            
    @callback
    def async_add_entity(
        self,
        platform: str,
        unique_id: str,
        entity_factory: Callable[[], T],
        data_key: str,
    ) -> None:
        """Add an entity to a platform with data key tracking."""
        # Don't add entities if coordinator isn't ready
        if not self.coordinator.data:
            LOGGER.debug("Skipping entity add, coordinator not ready: %s", unique_id)
            return

        if not self._initialized:
            LOGGER.debug("Entity loader not initialized yet, queueing entity: %s", unique_id)
            if platform not in self._pending_entities:
                self._pending_entities[platform] = []
            self._pending_entities[platform].append(entity_factory())
            return
            
        if platform not in self.entities:
            self.entities[platform] = set()
            
        if unique_id in self.entities[platform]:
            return
            
        LOGGER.debug("Adding entity %s for platform %s", unique_id, platform)
        self.entities[platform].add(unique_id)
        entity_def = EntityDefinition(
            unique_id=unique_id,
            platform=platform,
            factory=entity_factory,
            data_key=data_key
        )
        self._entity_definitions[unique_id] = entity_def
        
        # Track entity by its data type
        if data_key not in self._data_subscriptions:
            self._data_subscriptions[data_key] = set()
        self._data_subscriptions[data_key].add(unique_id)
        
        entity = entity_factory()
        
        if platform in self._async_add_entities:
            self._async_add_entities[platform]([entity])
        else:
            if platform not in self._pending_entities:
                self._pending_entities[platform] = []
            self._pending_entities[platform].append(entity)
            
    @callback
    def async_remove_entity(
        self,
        platform: str,
        unique_id: str,
    ) -> None:
        """Remove an entity from a platform."""
        if platform in self.entities:
            self.entities[platform].discard(unique_id)
            
            # Remove from data type tracking
            entity_def = self._entity_definitions.get(unique_id)
            if entity_def and entity_def.data_key in self._data_subscriptions:
                self._data_subscriptions[entity_def.data_key].discard(unique_id)
                if not self._data_subscriptions[entity_def.data_key]:
                    del self._data_subscriptions[entity_def.data_key]
            
            self._entity_definitions.pop(unique_id, None)
            
    async def async_handle_coordinator_update(self, data: dict) -> None:
        """Handle coordinator data updates."""
        if not data:
            return

        LOGGER.debug("Handling coordinator update with data keys: %s", list(data.keys()))
        
        update_stats = {
            'total': 0,
            'removed': 0,
            'updated': 0
        }
        
        # Process updates for each data type
        for data_key, rules in data.items():
            if data_key not in self._data_subscriptions:
                continue
                
            update_stats['total'] += 1
            
            # Get the actual rules list, handling nested data structures
            if isinstance(rules, dict) and 'data' in rules:
                rules = rules['data']
            elif not isinstance(rules, list):
                LOGGER.warning("Unexpected data format for %s: %s", data_key, type(rules))
                continue

            # Build set of current rule IDs
            current_rule_ids = {rule.get('_id') for rule in rules if rule.get('_id')}
            
            # Check entities subscribed to this data type
            for unique_id in list(self._data_subscriptions[data_key]):
                entity_def = self._entity_definitions.get(unique_id)
                if not entity_def:
                    continue
                    
                # Extract rule ID from unique_id
                rule_id = self._extract_rule_id(unique_id)
                if not rule_id:
                    continue
                
                # Remove entity if its rule no longer exists
                if rule_id not in current_rule_ids:
                    LOGGER.debug("Removing entity %s as rule %s no longer exists", 
                               unique_id, rule_id)
                    self.async_remove_entity(entity_def.platform, unique_id)
                    update_stats['removed'] += 1
                else:
                    update_stats['updated'] += 1

        LOGGER.debug(
            "Coordinator update complete - Total: %d, Updated: %d, Removed: %d",
            update_stats['total'],
            update_stats['updated'],
            update_stats['removed']
        )

    def _extract_rule_id(self, unique_id: str) -> str | None:
        """Extract rule ID from entity unique_id."""
        if 'network_policy_' in unique_id:
            return unique_id.replace('network_policy_', '')
        elif 'network_route_' in unique_id:
            return unique_id.replace('network_route_', '')
        elif 'network_rule_firewall_' in unique_id:
            return unique_id.replace('network_rule_firewall_', '')
        elif 'network_rule_traffic_' in unique_id:
            return unique_id.replace('network_rule_traffic_', '')
        elif 'port_forward_' in unique_id:
            parts = unique_id.split('_')
            if len(parts) > 1:
                return parts[-1]
        return None

    async def async_load_entities(self) -> None:
        """Load all entities."""
        data = self.coordinator.data
        if not data:
            LOGGER.warning("No data available from coordinator")
            return
            
        for platform, async_add_entities in self._async_add_entities.items():
            if platform not in self.entities:
                continue
                
            # Create new entities based on coordinator data
            new_entities = []
            for unique_id in self.entities[platform]:
                entity_def = self._entity_definitions.get(unique_id)
                if entity_def:
                    new_entities.append(entity_def.factory())
                    
            if new_entities:
                async_add_entities(new_entities)
                
    async def async_unload_entities(self) -> None:
        """Unload all entities."""
        # Clear all tracking dictionaries
        self.entities.clear()
        self._entity_definitions.clear()
        self._pending_entities.clear()
        self._data_subscriptions.clear()
        
    def async_register_platform_entities(
        self,
        platform: str,
        async_add_entities: AddEntitiesCallback,
        entity_configs: list[Mapping[str, Any]],
        entity_factory: Callable[[Mapping[str, Any]], T],
    ) -> None:
        """Register entities for a platform based on configurations."""
        self.async_setup_platform(platform, async_add_entities)
        
        for config in entity_configs:
            unique_id = config["unique_id"]
            data_key = config.get("data_key", "default")
            self.async_add_entity(
                platform,
                unique_id,
                lambda: entity_factory(config),
                data_key
            )