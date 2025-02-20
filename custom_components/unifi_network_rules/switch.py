"""UniFi Network Rules switch platform."""
from __future__ import annotations

from typing import Any
from collections import defaultdict

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, LOGGER
from .coordinator import UnifiRuleUpdateCoordinator

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

        def _add_rule(rule: dict, rule_type: str) -> None:
            """Add a single rule if not already added."""
            rule_id = rule.get("_id")
            if not rule_id:
                return
            unique_id = f"{rule_type}_{rule_id}"
            if unique_id not in current_entities:
                entities.append(UnifiRuleSwitch(coordinator, rule, rule_type))
                current_entities.add(unique_id)

        # Process each rule type
        for policy in data.get("firewall_policies", []):
            _add_rule(policy, "firewall_policies")
        
        for rule in data.get("traffic_rules", []):
            _add_rule(rule, "traffic_rules")
            
        for forward in data.get("port_forwards", []):
            _add_rule(forward, "port_forwards")

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
        rule_data: dict[str, Any],
        rule_type: str,
    ) -> None:
        """Initialize the rule switch."""
        super().__init__(coordinator)
        self._rule_data = rule_data
        self._rule_type = rule_type
        self._rule_id = rule_data.get("_id", "")
        self._attr_name = rule_data.get("name", f"Rule {self._rule_id}")
        self._attr_unique_id = f"{rule_type}_{self._rule_id}"

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.api.host)},
            name="UniFi Network Rules",
            manufacturer="Ubiquiti",
            model="UniFi Dream Machine",
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        """Return the enabled state of the rule."""
        try:
            # Find current rule data in coordinator
            rules = self.coordinator.data.get(self._rule_type, [])
            for rule in rules:
                if rule.get("_id") == self._rule_id:
                    return rule.get("enabled", False)
            return False
        except Exception as err:
            LOGGER.error("Error getting rule state: %s", err)
            return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the rule."""
        try:
            if self._rule_type == "firewall_policies":
                await self.coordinator.api.update_firewall_policy(self._rule_id, {"enabled": True})
            elif self._rule_type == "traffic_rules":
                await self.coordinator.api.update_traffic_rule(self._rule_id, {"enabled": True})
            elif self._rule_type == "port_forwards":
                await self.coordinator.api.update_port_forward(self._rule_id, {"enabled": True})
            await self.coordinator.async_refresh()
        except Exception as err:
            LOGGER.error("Error enabling rule: %s", err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the rule."""
        try:
            if self._rule_type == "firewall_policies":
                await self.coordinator.api.update_firewall_policy(self._rule_id, {"enabled": False})
            elif self._rule_type == "traffic_rules":
                await self.coordinator.api.update_traffic_rule(self._rule_id, {"enabled": False})
            elif self._rule_type == "port_forwards":
                await self.coordinator.api.update_port_forward(self._rule_id, {"enabled": False})
            await self.coordinator.async_refresh()
        except Exception as err:
            LOGGER.error("Error disabling rule: %s", err)