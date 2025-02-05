"""Support for UniFi Network Rules switches."""
import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the UniFi Network Rules switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]['coordinator']
    api = hass.data[DOMAIN][entry.entry_id]['api']

    _LOGGER.debug("Setting up switches with coordinator data: %s", coordinator.data)

    # Check if we have data
    if not coordinator.data:
        _LOGGER.debug("No data available yet, waiting for coordinator refresh")
        await coordinator.async_refresh()

    entities = []

    # Add firewall policy switches
    policies = coordinator.data.get('firewall_policies', []) if coordinator.data else []
    for policy in policies:
        entities.append(UDMFirewallPolicySwitch(coordinator, api, policy))

    # Add traffic route switches
    routes = coordinator.data.get('traffic_routes', []) if coordinator.data else []
    for route in routes:
        entities.append(UDMTrafficRouteSwitch(coordinator, api, route))

    _LOGGER.debug("Adding %d entities", len(entities))
    async_add_entities(entities, True)

class UDMTrafficRouteSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a UDM Traffic Route Switch."""

    def __init__(self, coordinator, api, route):
        """Initialize the UDM Traffic Route Switch."""
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"traffic_route_{route['_id']}"
        self._attr_name = f"Traffic Route: {route.get('description', 'Unnamed')}"
        self._route_id = route['_id']

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._get_route() is not None

    @property
    def is_on(self):
        """Return true if the switch is on."""
        route = self._get_route()
        return route['enabled'] if route else False

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._toggle(True)

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._toggle(False)

    async def _toggle(self, new_state):
        """Toggle the route state."""
        try:
            success, error_message = await self._api.toggle_traffic_route(self._route_id, new_state)
            if success:
                await self.coordinator.async_request_refresh()
            else:
                raise HomeAssistantError(f"Failed to toggle traffic route: {error_message}")
        except Exception as e:
            raise HomeAssistantError(f"Error toggling traffic route: {str(e)}")

    def _get_route(self):
        """Get the current route from the coordinator data."""
        if not self.coordinator.data:
            return None
        routes = self.coordinator.data.get('traffic_routes', [])
        return next((r for r in routes if r['_id'] == self._route_id), None)

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        route = self._get_route()
        if not route:
            return {}

        attributes = {
            "description": route.get("description", ""),
            "matching_target": route.get("matching_target", ""),
            "network_id": route.get("network_id", ""),
            "kill_switch_enabled": route.get("kill_switch_enabled", False),
        }

        if route.get("domains"):
            attributes["domains"] = [d.get("domain") for d in route["domains"]]

        if route.get("target_devices"):
            devices = []
            for device in route["target_devices"]:
                if device.get("type") == "ALL_CLIENTS":
                    devices.append("ALL_CLIENTS")
                elif device.get("type") == "NETWORK":
                    devices.append(f"NETWORK: {device.get('network_id')}")
                else:
                    devices.append(device.get("client_mac", ""))
            attributes["target_devices"] = devices

        return attributes

class UDMFirewallPolicySwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a UDM Firewall Policy Switch."""

    def __init__(self, coordinator, api, policy):
        """Initialize the UDM Firewall Policy Switch."""
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"firewall_policy_{policy['_id']}"
        self._attr_name = f"Firewall Policy: {policy.get('name', 'Unnamed')}"
        self._policy_id = policy['_id']

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._get_policy() is not None

    @property
    def is_on(self):
        """Return true if the switch is on."""
        policy = self._get_policy()
        return policy['enabled'] if policy else False

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._toggle(True)

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._toggle(False)

    async def _toggle(self, new_state):
        """Toggle the policy state."""
        try:
            success, error_message = await self._api.toggle_firewall_policy(self._policy_id, new_state)
            if success:
                await self.coordinator.async_request_refresh()
            else:
                raise HomeAssistantError(f"Failed to toggle firewall policy: {error_message}")
        except Exception as e:
            raise HomeAssistantError(f"Error toggling firewall policy: {str(e)}")

    def _get_policy(self):
        """Get the current policy from the coordinator data."""
        if not self.coordinator.data:
            return None
        policies = self.coordinator.data.get('firewall_policies', [])
        return next((p for p in policies if p['_id'] == self._policy_id), None)

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        policy = self._get_policy()
        if not policy:
            return {}

        return {
            "name": policy.get("name", ""),
            "action": policy.get("action", ""),
            "predefined": policy.get("predefined", False),
            "protocol": policy.get("protocol", ""),
            "schedule_mode": policy.get("schedule", {}).get("mode", ""),
            "source_zone": policy.get("source", {}).get("zone_id", ""),
            "destination_zone": policy.get("destination", {}).get("zone_id", ""),
            "index": policy.get("index", 0),
            "matching_target": policy.get("source", {}).get("matching_target", ""),
            "ip_version": policy.get("ip_version", "")
        }