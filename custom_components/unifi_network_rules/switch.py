"""Support for UniFi Network Rules switches."""
import logging
import asyncio
from typing import Any
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the UniFi Network Rules switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]['coordinator']
    api = hass.data[DOMAIN][entry.entry_id]['api']

    _LOGGER.info("Setting up switches with coordinator data: %s", coordinator.data)
    await coordinator.async_config_entry_first_refresh()

    entities = []
    if coordinator.data:
        policies = coordinator.data.get('firewall_policies', [])
        for policy in policies:
            entities.append(UDMFirewallPolicySwitch(coordinator, api, policy))

        routes = coordinator.data.get('traffic_routes', [])
        for route in routes:
            entities.append(UDMTrafficRouteSwitch(coordinator, api, route))

    async_add_entities(entities)

class UDMTrafficRouteSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a UDM Traffic Route Switch."""

    def __init__(self, coordinator, api, route):
        """Initialize the UDM Traffic Route Switch."""
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"traffic_route_{route['_id']}"
        self._attr_name = f"Traffic Route: {route.get('description', 'Unnamed')}"
        self._route_id = route['_id']
        self._route = route
        _LOGGER.info("Initialized traffic route switch: %s (ID: %s)", self._attr_name, self._route_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        routes = self.coordinator.data.get('traffic_routes', [])
        self._route = next((r for r in routes if r['_id'] == self._route_id), None)
        _LOGGER.debug("Updated route data for %s: %s", self._attr_name, self._route)
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        is_available = self.coordinator.last_update_success and self._route is not None
        _LOGGER.debug("Switch %s availability: %s", self._attr_name, is_available)
        return is_available

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        if not self._route:
            _LOGGER.warning("No route data available for %s", self._attr_name)
            return False
        return bool(self._route.get('enabled', False))

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
            _LOGGER.info("Attempting to toggle %s to %s", self._attr_name, new_state)
            success, error_message = await self._api.toggle_traffic_route(self._route_id, new_state)
            
            if success:
                _LOGGER.info("Successfully toggled %s to %s", self._attr_name, new_state)
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to toggle %s: %s", self._attr_name, error_message)
                raise HomeAssistantError(f"Failed to toggle traffic route: {error_message}")
        except Exception as e:
            _LOGGER.exception("Error toggling %s", self._attr_name)
            raise HomeAssistantError(f"Error toggling traffic route: {str(e)}")

class UDMFirewallPolicySwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a UDM Firewall Policy Switch."""

    def __init__(self, coordinator, api, policy):
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"firewall_policy_{policy['_id']}"
        self._attr_name = f"Firewall Policy: {policy.get('name', 'Unnamed')}"
        self._policy_id = policy['_id']
        self._policy = policy
        _LOGGER.info("Initialized firewall policy switch: %s (ID: %s)", self._attr_name, self._policy_id)

    def get_policy(self):
        """Get the current policy from coordinator data."""
        if not self.coordinator.data:
            _LOGGER.debug("No coordinator data available for %s", self._attr_name)
            return None
        policies = self.coordinator.data.get('firewall_policies', [])
        policy = next((p for p in policies if p['_id'] == self._policy_id), None)
        if policy is None:
            _LOGGER.debug("Policy not found in coordinator data for %s", self._attr_name)
        return policy

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._policy = self.get_policy()
        _LOGGER.debug("Updated policy data for %s: %s", self._attr_name, self._policy)
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        is_available = self.coordinator.last_update_success and self._policy is not None
        _LOGGER.debug("Switch %s availability: %s", self._attr_name, is_available)
        return is_available

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        if not self._policy:
            _LOGGER.warning("No policy data available for %s", self._attr_name)
            return False
        return bool(self._policy.get('enabled', False))

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
            _LOGGER.info("Current policy state: %s", self._policy)
            _LOGGER.info("Attempting to toggle %s to %s", self._attr_name, new_state)
            success, error_message = await self._api.toggle_firewall_policy(self._policy_id, new_state)
            
            if success:
                _LOGGER.info("Successfully toggled %s to %s", self._attr_name, new_state)
                await self.coordinator.async_request_refresh()
                
                await asyncio.sleep(1)  # Give time for refresh
                updated_policy = self.get_policy()
                _LOGGER.info("Post-refresh policy state: %s", updated_policy)
                
                if not updated_policy or updated_policy.get('enabled') != new_state:
                    _LOGGER.error("State mismatch after coordinator refresh")
                    raise HomeAssistantError(f"State verification failed for {self._attr_name}")
            else:
                _LOGGER.error("Failed to toggle %s: %s", self._attr_name, error_message)
                raise HomeAssistantError(f"Failed to toggle firewall policy: {error_message}")
        except Exception as e:
            _LOGGER.exception("Error toggling %s", self._attr_name)
            raise HomeAssistantError(f"Error toggling firewall policy: {str(e)}")