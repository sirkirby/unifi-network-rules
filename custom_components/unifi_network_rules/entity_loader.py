"""UniFi Network Rules entity loader and management."""
from __future__ import annotations
from typing import Any, Callable, Generic, TypeVar, TYPE_CHECKING
from collections.abc import Mapping
from dataclasses import dataclass

from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, LOGGER
from .coordinator import UDMUpdateCoordinator
from .utils.registry import async_get_registry

if TYPE_CHECKING:
    from homeassistant.helpers.entity_registry import EntityRegistry

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
        
    def _get_registry(self) -> EntityRegistry:
        """Get the entity registry."""
        return async_get_registry(self.hass)

    @callback
    def async_setup_platform(
        self,
        platform: str,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        """Set up an entity platform."""
        self._async_add_entities[platform] = async_add_entities
        self._initialized = True
        
        # Add any pending entities
        if platform in self._pending_entities and self._pending_entities[platform]:
            async_add_entities(self._pending_entities.pop(platform))
            
    def _cleanup_stale_entities(self, platform: str) -> None:
        """Clean up stale entities from the registry."""
        registry = self._get_registry()
        removed = []

        # Get all entities for our domain
        for entity_id, entry in registry.entities.items():
            if entry.domain == DOMAIN and entry.platform == platform:
                # Check if entity is still valid
                if entry.unique_id not in self._entity_definitions:
                    registry.async_remove(entity_id)
                    removed.append(entity_id)
                    LOGGER.debug("Removed stale entity %s", entity_id)

        if removed:
            LOGGER.info("Cleaned up %d stale entities: %s", len(removed), removed)
            
    @callback
    def async_add_entity(
        self,
        platform: str,
        unique_id: str,
        entity_factory: Callable[[], T],
        data_key: str,
    ) -> None:
        """Add an entity to a platform with data key tracking."""
        try:
            # Don't add entities if coordinator isn't ready
            if not self.coordinator.data:
                LOGGER.debug("Skipping entity add, coordinator not ready: %s", unique_id)
                return

            # If this is our first entity, clean up any stale ones
            if not self._entity_definitions:
                self._cleanup_stale_entities(platform)

            # Check if entity is already tracked
            if unique_id in self._entity_definitions:
                LOGGER.debug("Entity %s already tracked", unique_id)
                return

            # Create and validate entity
            entity = entity_factory()
            if not hasattr(entity, 'unique_id') or entity.unique_id != unique_id:
                LOGGER.error(
                    "Entity factory created entity with mismatched unique_id. Expected: %s, Got: %s",
                    unique_id,
                    getattr(entity, 'unique_id', None)
                )
                return

            # Store entity definition
            entity_def = EntityDefinition(
                unique_id=unique_id,
                platform=platform,
                factory=entity_factory,
                data_key=data_key
            )
            self._entity_definitions[unique_id] = entity_def

            # Track by platform
            if platform not in self.entities:
                self.entities[platform] = set()
            self.entities[platform].add(unique_id)
            
            # Track by data type
            if data_key not in self._data_subscriptions:
                self._data_subscriptions[data_key] = set()
            self._data_subscriptions[data_key].add(unique_id)

            # Add entity to HA
            if self._initialized and platform in self._async_add_entities:
                LOGGER.debug("Adding entity %s to Home Assistant", unique_id)
                self._async_add_entities[platform]([entity])
            else:
                LOGGER.debug("Queueing entity %s for later addition", unique_id)
                if platform not in self._pending_entities:
                    self._pending_entities[platform] = []
                self._pending_entities[platform].append(entity)

        except Exception as e:
            LOGGER.error("Error adding entity %s: %s", unique_id, str(e))
            
    @callback
    def async_remove_entity(
        self,
        platform: str,
        unique_id: str,
    ) -> None:
        """Remove an entity from a platform."""
        try:
            if platform in self.entities:
                self.entities[platform].discard(unique_id)
                
                # Remove from data type tracking
                entity_def = self._entity_definitions.get(unique_id)
                if entity_def and entity_def.data_key in self._data_subscriptions:
                    self._data_subscriptions[entity_def.data_key].discard(unique_id)
                    if not self._data_subscriptions[entity_def.data_key]:
                        del self._data_subscriptions[entity_def.data_key]
                
                self._entity_definitions.pop(unique_id, None)

            # Remove from entity registry if it exists
            registry = self._get_registry()
            entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
            if entity_id:
                registry.async_remove(entity_id)
                LOGGER.debug("Removed entity %s from registry", entity_id)

        except Exception as e:
            LOGGER.error("Error removing entity %s: %s", unique_id, str(e))
            
    async def async_handle_coordinator_update(self, data: dict) -> None:
        """Handle coordinator data updates."""
        if not data:
            LOGGER.warning("No data in coordinator update")
            return

        LOGGER.debug("Handling coordinator update with data keys: %s", list(data.keys()))

        # Build set of valid rule IDs from all data types
        valid_rule_ids = set()
        for data_key, rules in data.items():
            # Handle nested data structures
            if isinstance(rules, dict) and 'data' in rules:
                rules = rules['data']
            if isinstance(rules, list):
                for rule in rules:
                    if isinstance(rule, dict) and '_id' in rule:
                        valid_rule_ids.add(rule['_id'])

        # Check all tracked entities against valid rules
        removed_entities = []
        for data_key, subscriptions in list(self._data_subscriptions.items()):
            for unique_id in list(subscriptions):
                entity_def = self._entity_definitions.get(unique_id)
                if not entity_def:
                    continue

                # Extract rule ID from unique_id
                rule_id = self._extract_rule_id(unique_id)
                if not rule_id:
                    LOGGER.warning("Could not extract rule ID from unique_id: %s", unique_id)
                    continue

                # Remove entity if rule no longer exists
                if rule_id not in valid_rule_ids:
                    LOGGER.debug("Removing entity for non-existent rule: %s (rule_id: %s)", 
                               unique_id, rule_id)
                    self.async_remove_entity(entity_def.platform, unique_id)
                    removed_entities.append(unique_id)

        if removed_entities:
            LOGGER.info("Removed %d stale entities: %s", len(removed_entities), removed_entities)

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