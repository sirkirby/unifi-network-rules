"""UniFi Network Rules switch platform."""
from __future__ import annotations

from typing import Any, Final
from collections import defaultdict

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward

from .const import DOMAIN, LOGGER
from .coordinator import UnifiRuleUpdateCoordinator
from .utils import get_rule_id, get_rule_name, get_rule_enabled

PARALLEL_UPDATES = 1
RULE_TYPES: Final = {
    "firewall_policies": "Firewall Policy",
    "traffic_rules": "Traffic Rule",
    "port_forwards": "Port Forward",
    "traffic_routes": "Traffic Route"
}

# Track entities across the platform
_ENTITY_CACHE = defaultdict(set)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator: UnifiRuleUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    entry_id = config_entry.entry_id

    @callback
    def _add_new_rules() -> None:
        """Add new rules as switches."""
        data = coordinator.data
        if not data:
            return

        entities = []
        current_entities = _ENTITY_CACHE[entry_id]

        # Process each rule type
        for rule_type, rules in data.items():
            if rule_type not in RULE_TYPES:
                continue
                
            for rule in rules:
                try:
                    # Log detailed information about the rule object
                    LOGGER.debug(
                        "Processing rule - Type: %s, Attrs: %s", 
                        type(rule),
                        dir(rule) if not isinstance(rule, dict) else list(rule.keys())
                    )
                    
                    rule_id = get_rule_id(rule)
                    if not rule_id:
                        LOGGER.warning(
                            "Rule without ID found in %s: %s (type: %s)", 
                            rule_type, rule, type(rule)
                        )
                        continue
                        
                    unique_id = f"{rule_type}_{rule_id}"
                    if unique_id not in current_entities:
                        entities.append(UnifiRuleSwitch(coordinator, rule, rule_type))
                        current_entities.add(unique_id)
                except Exception as err:
                    LOGGER.error(
                        "Error processing rule in %s: %s (rule: %s)", 
                        rule_type, err, rule
                    )

        if entities:
            async_add_entities(entities)

    # Add currently existing rules
    _add_new_rules()

    # Register listener for future updates
    config_entry.async_on_unload(
        coordinator.async_add_listener(_add_new_rules)
    )

    # Register cleanup
    config_entry.async_on_unload(lambda: _ENTITY_CACHE.pop(entry_id, None))

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._get_current_rule() is not None

    @property
    def is_on(self) -> bool:
        """Return the enabled state of the rule."""
        rule = self._get_current_rule()
        if rule is None:
            return False
            
        return get_rule_enabled(rule)

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
        base_data = {
            "_id": getattr(obj, "id", None),
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
        """Enable the rule."""
        try:
            current_rule = self._get_current_rule()
            if not current_rule:
                LOGGER.error("Cannot enable rule - current rule data not found")
                return
                
            # Convert rule to dict while preserving all properties
            rule_data = self._to_dict(current_rule)
            rule_data["enabled"] = True
            
            success = False
            if self._rule_type == "firewall_policies":
                success = await self.coordinator.api.update_firewall_policy(self._rule_id, rule_data)
            elif self._rule_type == "traffic_rules":
                success = await self.coordinator.api.update_traffic_rule(self._rule_id, rule_data)
            elif self._rule_type == "port_forwards":
                success = await self.coordinator.api.update_port_forward(self._rule_id, rule_data)
            elif self._rule_type == "traffic_routes":
                success = await self.coordinator.api.update_traffic_route(self._rule_id, rule_data)
                
            if success:
                await self.coordinator.async_refresh()
            else:
                LOGGER.error("Failed to enable %s %s", self._rule_type, self._rule_id)
                
        except Exception as err:
            LOGGER.error("Error enabling rule: %s", err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the rule."""
        try:
            current_rule = self._get_current_rule()
            if not current_rule:
                LOGGER.error("Cannot disable rule - current rule data not found")
                return
                
            # Convert rule to dict while preserving all properties
            rule_data = self._to_dict(current_rule)
            rule_data["enabled"] = False
            
            success = False
            if self._rule_type == "firewall_policies":
                success = await self.coordinator.api.update_firewall_policy(self._rule_id, rule_data)
            elif self._rule_type == "traffic_rules":
                success = await self.coordinator.api.update_traffic_rule(self._rule_id, rule_data)
            elif self._rule_type == "port_forwards":
                success = await self.coordinator.api.update_port_forward(self._rule_id, rule_data)
            elif self._rule_type == "traffic_routes":
                success = await self.coordinator.api.update_traffic_route(self._rule_id, rule_data)
                
            if success:
                await self.coordinator.async_refresh()
            else:
                LOGGER.error("Failed to disable %s %s", self._rule_type, self._rule_id)
                
        except Exception as err:
            LOGGER.error("Error disabling rule: %s", err)