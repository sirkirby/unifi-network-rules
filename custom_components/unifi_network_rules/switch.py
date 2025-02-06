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
        self._pending_state = None
        _LOGGER.info("Initialized traffic route switch: %s (ID: %s)", self._attr_name, self._route_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        routes = self.coordinator.data.get('traffic_routes', [])
        new_route = next((r for r in routes if r.get('_id') == self._route_id), None)
        
        if new_route:
            if self._route.get('enabled') != new_route.get('enabled'):
                _LOGGER.info(
                    "State change detected for %s: %s -> %s", 
                    self._attr_name, 
                    self._route.get('enabled'), 
                    new_route.get('enabled')
                )
            self._route = new_route
            self._pending_state = None
        else:
            _LOGGER.warning("Route %s not found in coordinator data", self._route_id)
            
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
        if self._pending_state is not None:
            return self._pending_state
        return bool(self._route.get('enabled', False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.info("Turning on switch: %s", self._attr_name)
        await self._toggle(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.info("Turning off switch: %s", self._attr_name)
        await self._toggle(False)

    async def _verify_state_change(self, target_state: bool, max_attempts: int = 3) -> bool:
        """Verify that the state change was successful."""
        for attempt in range(max_attempts):
            try:
                # Get fresh data directly from the API instead of coordinator
                success, routes, error = await self._api.get_traffic_routes()
                if not success:
                    _LOGGER.error("Failed to fetch routes for verification: %s", error)
                    await asyncio.sleep(2)
                    continue

                current_route = next((r for r in routes if r['_id'] == self._route_id), None)
                if not current_route:
                    _LOGGER.error("Route not found during verification")
                    await asyncio.sleep(2)
                    continue

                current_state = current_route.get('enabled', False)
                if current_state == target_state:
                    # Update the coordinator data to reflect the new state
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

    async def _toggle(self, new_state: bool) -> None:
        """Toggle the route state."""
        try:
            if self._route.get('enabled') == new_state:
                _LOGGER.info("%s is already in desired state: %s", self._attr_name, new_state)
                return

            self._pending_state = new_state
            self.async_write_ha_state()

            success, error_message = await self._api.toggle_traffic_route(self._route_id, new_state)
            
            if success:
                _LOGGER.info("API reports successful toggle for %s", self._attr_name)
                
                # Add a small delay before verification to allow for API propagation
                await asyncio.sleep(1)
                
                if await self._verify_state_change(new_state):
                    _LOGGER.info("Successfully verified state change for %s", self._attr_name)
                else:
                    self._pending_state = None
                    raise HomeAssistantError(
                        f"Failed to verify state change for {self._attr_name}. "
                        f"Target state: {new_state}, Current state: {self._route.get('enabled')}"
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

class UDMFirewallPolicySwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a UDM Firewall Policy Switch."""

    def __init__(self, coordinator, api, policy):
        """Initialize the UDM Firewall Policy Switch."""
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"firewall_policy_{policy['_id']}"
        self._attr_name = f"Firewall Policy: {policy.get('name', 'Unnamed')}"
        self._policy_id = policy['_id']
        self._policy = policy
        self._pending_state = None
        _LOGGER.info("Initialized firewall policy switch: %s (ID: %s)", self._attr_name, self._policy_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        policies = self.coordinator.data.get('firewall_policies', [])
        new_policy = next((p for p in policies if p['_id'] == self._policy_id), None)
        
        if new_policy:
            if self._policy.get('enabled') != new_policy.get('enabled'):
                _LOGGER.info(
                    "State change detected for %s: %s -> %s", 
                    self._attr_name, 
                    self._policy.get('enabled'), 
                    new_policy.get('enabled')
                )
            self._policy = new_policy
            self._pending_state = None
        else:
            _LOGGER.warning("Policy %s not found in coordinator data", self._policy_id)
            
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
        if self._pending_state is not None:
            return self._pending_state
        return bool(self._policy.get('enabled', False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.info("Turning on switch: %s", self._attr_name)
        await self._toggle(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.info("Turning off switch: %s", self._attr_name)
        await self._toggle(False)

    async def _verify_state_change(self, target_state: bool, max_attempts: int = 3) -> bool:
        """Verify that the state change was successful."""
        for attempt in range(max_attempts):
            try:
                # Get fresh data directly from the API instead of coordinator
                success, policies, error = await self._api.get_firewall_policies()
                if not success:
                    _LOGGER.error("Failed to fetch policies for verification: %s", error)
                    await asyncio.sleep(2)
                    continue

                current_policy = next((p for p in policies if p['_id'] == self._policy_id), None)
                if not current_policy:
                    _LOGGER.error("Policy not found during verification")
                    await asyncio.sleep(2)
                    continue

                current_state = current_policy.get('enabled', False)
                if current_state == target_state:
                    # Update the coordinator data to reflect the new state
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

    async def _toggle(self, new_state: bool) -> None:
        """Toggle the policy state."""
        try:
            if self._policy.get('enabled') == new_state:
                _LOGGER.info("%s is already in desired state: %s", self._attr_name, new_state)
                return

            self._pending_state = new_state
            self.async_write_ha_state()

            success, error_message = await self._api.toggle_firewall_policy(self._policy_id, new_state)
            
            if success:
                _LOGGER.info("API reports successful toggle for %s", self._attr_name)
                
                # Add a small delay before verification to allow for API propagation
                await asyncio.sleep(1)
                
                if await self._verify_state_change(new_state):
                    _LOGGER.info("Successfully verified state change for %s", self._attr_name)
                else:
                    self._pending_state = None
                    raise HomeAssistantError(
                        f"Failed to verify state change for {self._attr_name}. "
                        f"Target state: {new_state}, Current state: {self._policy.get('enabled')}"
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