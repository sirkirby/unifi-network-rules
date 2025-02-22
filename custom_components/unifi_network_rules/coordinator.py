"""UniFi Network Rules Coordinator."""
from __future__ import annotations

from datetime import timedelta
import asyncio
from typing import Any, Dict, Callable, List

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward

from .const import DOMAIN, LOGGER
from .udm_api import UDMAPI
from .websocket import SIGNAL_WEBSOCKET_MESSAGE, UnifiRuleWebsocket

SCAN_INTERVAL = timedelta(seconds=30)

def _log_rule_info(rule: Any) -> None:
    """Log detailed information about a rule object."""
    try:
        LOGGER.debug(
            "Rule info - Type: %s, Dir: %s, Dict: %s", 
            type(rule),
            dir(rule) if not isinstance(rule, dict) else "N/A",
            rule if isinstance(rule, dict) else "Not a dict"
        )
    except Exception as err:
        LOGGER.error("Error logging rule info: %s", err)

class UnifiRuleUpdateCoordinator(DataUpdateCoordinator[Dict[str, List[Any]]]):
    """Coordinator to manage data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UDMAPI,
        websocket: UnifiRuleWebsocket,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.websocket = websocket

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

        # Set up websocket message handler
        self.websocket.set_message_handler(self._handle_websocket_message)

        # Subscribe to websocket messages
        self._cleanup_callbacks: list[Callable[[], None]] = []
        self._cleanup_callbacks.append(
            async_dispatcher_connect(
                hass,
                SIGNAL_WEBSOCKET_MESSAGE,
                self._handle_websocket_message
            )
        )

    async def _async_update_data(self) -> Dict[str, List[Any]]:
        """Fetch data from API endpoint."""
        try:
            # Initialize with empty lists for each rule type
            rules_data: Dict[str, List[Any]] = {
                "firewall_policies": [],
                "traffic_rules": [],
                "port_forwards": [],
                "traffic_routes": [],
                "firewall_zones": [],
                "wlans": []
            }
            
            # Gather all rule types in parallel
            tasks = [
                self._update_firewall_policies(rules_data),
                self._update_traffic_rules(rules_data),
                self._update_port_forwards(rules_data),
                self._update_traffic_routes(rules_data),
                self._update_firewall_zones(rules_data),
                self._update_wlans(rules_data)
            ]
            
            await asyncio.gather(*tasks)
            
            # Log detailed info for traffic routes
            LOGGER.debug("Traffic routes received: %d items", len(rules_data["traffic_routes"]))
            for route in rules_data["traffic_routes"]:
                _log_rule_info(route)
                
            return rules_data
            
        except Exception as err:
            LOGGER.error("Error updating coordinator data: %s", err)
            raise UpdateFailed(f"Error updating data: {err}")

    async def _update_firewall_policies(self, data: Dict[str, List[Any]]) -> None:
        """Update firewall policies."""
        try:
            policies = await self.api.get_firewall_policies()
            # Log policy details for debugging
            for policy in policies:
                LOGGER.debug(
                    "Firewall policy details - ID: %s, Attrs: %s",
                    getattr(policy, "id", "unknown"),
                    dir(policy)
                )
            data["firewall_policies"] = list(policies)
        except Exception as err:
            LOGGER.error("Error fetching firewall policies: %s", err)
            data["firewall_policies"] = []

    async def _update_traffic_rules(self, data: Dict[str, List[Any]]) -> None:
        """Update traffic rules."""
        try:
            rules = await self.api.get_traffic_rules()
            # Log rule details for debugging
            for rule in rules:
                LOGGER.debug(
                    "Traffic rule details - ID: %s, Attrs: %s",
                    getattr(rule, "id", "unknown"),
                    dir(rule)
                )
            data["traffic_rules"] = list(rules)
        except Exception as err:
            LOGGER.error("Error fetching traffic rules: %s", err)
            data["traffic_rules"] = []

    async def _update_port_forwards(self, data: Dict[str, List[Any]]) -> None:
        """Update port forwards."""
        try:
            forwards = await self.api.get_port_forwards()
            # Log forward details for debugging
            for forward in forwards:
                LOGGER.debug(
                    "Port forward details - ID: %s, Attrs: %s",
                    getattr(forward, "id", "unknown"),
                    dir(forward)
                )
            data["port_forwards"] = list(forwards)
        except Exception as err:
            LOGGER.error("Error fetching port forwards: %s", err)
            data["port_forwards"] = []

    async def _update_traffic_routes(self, data: Dict[str, List[Any]]) -> None:
        """Update traffic routes."""
        try:
            routes = await self.api.get_traffic_routes()
            if routes:
                LOGGER.debug("Retrieved traffic routes: %d items", len(routes))
                for route in routes:
                    _log_rule_info(route)
                data["traffic_routes"] = list(routes)
            else:
                data["traffic_routes"] = []
        except Exception as err:
            LOGGER.error("Error fetching traffic routes: %s", err)
            data["traffic_routes"] = []

    async def _update_firewall_zones(self, data: Dict[str, List[Any]]) -> None:
        """Update firewall zones."""
        try:
            zones = await self.api.get_firewall_zones()
            data["firewall_zones"] = list(zones) if zones else []
        except Exception as err:
            LOGGER.error("Error fetching firewall zones: %s", err)
            data["firewall_zones"] = []

    async def _update_wlans(self, data: Dict[str, List[Any]]) -> None:
        """Update WLANs."""
        try:
            wlans = await self.api.get_wlans()
            data["wlans"] = list(wlans) if wlans else []
        except Exception as err:
            LOGGER.error("Error fetching WLANs: %s", err)
            data["wlans"] = []

    @callback
    def _handle_websocket_message(self, message: dict[str, Any]) -> None:
        """Handle incoming websocket message."""
        try:
            if not message:
                return

            LOGGER.debug("Processing websocket message: %s", message)
            
            # Determine if we need to refresh data based on message type
            should_refresh = False
            
            # Check message type and update accordingly
            if "firewall" in message:
                should_refresh = True
                LOGGER.debug("Firewall change detected")
            elif "portForward" in message:
                should_refresh = True
                LOGGER.debug("Port forward change detected")
            elif "routing" in message:
                should_refresh = True
                LOGGER.debug("Routing change detected")
            elif "wlan" in message:
                should_refresh = True
                LOGGER.debug("WLAN change detected")
                
            if should_refresh:
                self.hass.async_create_task(self.async_refresh())

        except Exception as err:
            LOGGER.error("Error handling websocket message: %s", err)

    @callback
    def shutdown(self) -> None:
        """Clean up resources."""
        for cleanup_callback in self._cleanup_callbacks:
            cleanup_callback()
