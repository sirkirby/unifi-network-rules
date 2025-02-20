"""UniFi Network Rules Coordinator."""
from __future__ import annotations

from datetime import timedelta
import asyncio
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LOGGER
from .udm_api import UDMAPI

class UnifiRuleUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinator to manage data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UDMAPI,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.api = api
        self._data: Dict[str, Any] = {}

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API endpoint."""
        try:
            rules_data = {}
            
            # Fetch all rule types
            await asyncio.gather(
                self._update_firewall_policies(rules_data),
                self._update_traffic_rules(rules_data),
                self._update_port_forwards(rules_data),
                self._update_traffic_routes(rules_data),
                self._update_firewall_zones(rules_data),
                self._update_wlans(rules_data)
            )
            
            self._data = rules_data
            return rules_data
        except Exception as err:
            LOGGER.error("Error updating coordinator data: %s", err)
            raise

    async def _update_firewall_policies(self, data: Dict[str, Any]) -> None:
        """Update firewall policies."""
        try:
            data["firewall_policies"] = await self.api.get_firewall_policies()
        except Exception as err:
            LOGGER.error("Error fetching firewall policies: %s", err)
            data["firewall_policies"] = []

    async def _update_traffic_rules(self, data: Dict[str, Any]) -> None:
        """Update traffic rules."""
        try:
            data["traffic_rules"] = await self.api.get_traffic_rules()
        except Exception as err:
            LOGGER.error("Error fetching traffic rules: %s", err)
            data["traffic_rules"] = []

    async def _update_port_forwards(self, data: Dict[str, Any]) -> None:
        """Update port forwards."""
        try:
            data["port_forwards"] = await self.api.get_port_forwards()
        except Exception as err:
            LOGGER.error("Error fetching port forwards: %s", err)
            data["port_forwards"] = []

    async def _update_traffic_routes(self, data: Dict[str, Any]) -> None:
        """Update traffic routes."""
        try:
            data["traffic_routes"] = await self.api.get_traffic_routes()
        except Exception as err:
            LOGGER.error("Error fetching traffic routes: %s", err)
            data["traffic_routes"] = []

    async def _update_firewall_zones(self, data: Dict[str, Any]) -> None:
        """Update firewall zones."""
        try:
            data["firewall_zones"] = await self.api.get_firewall_zones()
        except Exception as err:
            LOGGER.error("Error fetching firewall zones: %s", err)
            data["firewall_zones"] = []

    async def _update_wlans(self, data: Dict[str, Any]) -> None:
        """Update WLANs."""
        try:
            data["wlans"] = await self.api.get_wlans()
        except Exception as err:
            LOGGER.error("Error fetching WLANs: %s", err)
            data["wlans"] = []

    async def handle_websocket_message(self, message: dict[str, Any]) -> None:
        """Handle incoming websocket message."""
        try:
            if not message:
                return

            LOGGER.debug("Received websocket message: %s", message)
            
            # Message format might be different based on the type of update
            msg_type = message.get("type", "")
            
            # Schedule a data update if we receive relevant messages
            if msg_type in ["fw", "netconf", "network"]:
                await self.async_refresh()
                
        except Exception as err:
            LOGGER.error("Error handling websocket message: %s", err)
