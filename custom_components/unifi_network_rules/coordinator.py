"""UniFi Network Application Rule Update Coordinator."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, LOGGER

class UnifiRuleUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching UniFi Network data."""

    def __init__(self, hass: HomeAssistant, api: Any, update_interval: timedelta) -> None:
        """Initialize."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.api = api
        self._known_rules: Dict[str, List[str]] = {}
        self._setup_auto_cleanup()
        
        # Set up websocket handler
        if hasattr(api, 'websocket') and api.websocket:
            api.websocket.set_message_handler(self.handle_websocket_message)

    def _setup_auto_cleanup(self) -> None:
        """Set up automatic entity cleanup."""
        @callback
        async def cleanup_on_updated(*_) -> None:
            """Clean up entities when data is updated."""
            await self._track_and_cleanup_rules(self.data if self.data else {})

        # Clean up after each update
        self.async_add_listener(cleanup_on_updated)

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API endpoint."""
        data = {}
        
        # Fetch policies if available
        if self.api.capabilities.zone_based_firewall:
            policies = await self.api.get_firewall_policies()
            if policies:
                data["firewall_policies"] = policies

        # Fetch routes if available
        if self.api.capabilities.traffic_routes:
            routes = await self.api.get_traffic_routes()
            if routes:
                data["traffic_routes"] = routes

        # Fetch port forwards
        port_forwards = await self.api.get_port_forward_rules()
        if port_forwards:
            data["port_forward_rules"] = port_forwards

        # Fetch legacy firewall rules
        if self.api.capabilities.legacy_firewall:
            firewall_rules = await self.api.get_legacy_firewall_rules()
            if firewall_rules:
                data["legacy_firewall_rules"] = firewall_rules

        # Only attempt to fetch legacy traffic rules if the capability exists
        if self.api.capabilities.legacy_traffic:
            traffic_rules = await self.api.get_legacy_traffic_rules()
            if traffic_rules:
                data["legacy_traffic_rules"] = traffic_rules

        return data

    def get_rule(self, rule_id: str) -> Optional[dict]:
        """Get a specific rule by ID."""
        if not self.data:
            return None
            
        for rules in self.data.values():
            rule_list = rules if isinstance(rules, list) else rules.get("data", [])
            for rule in rule_list:
                if rule["_id"] == rule_id:
                    return rule
        return None

    async def handle_websocket_message(self, msg: Any) -> None:
        """Handle websocket message."""
        try:
            msg_type = msg.get('type')
            if msg_type in ["rules", "policies", "routes"]:
                await self.async_refresh()
        except Exception as e:
            LOGGER.error("Error handling websocket message: %s", str(e))

    async def _track_and_cleanup_rules(self, current_data: Dict[str, Any]) -> None:
        """Track current rules and clean up removed ones."""
        current_rules: Dict[str, List[str]] = {}
        
        # Build current rules mapping
        for rule_type, rules in current_data.items():
            rule_list = rules if isinstance(rules, list) else rules.get("data", [])
            current_rules[rule_type] = [rule["_id"] for rule in rule_list]

        # If we have previous data to compare against
        if self._known_rules:
            # Find deleted rules
            for rule_type, rule_ids in self._known_rules.items():
                current_ids = current_rules.get(rule_type, [])
                deleted_ids = set(rule_ids) - set(current_ids)
                
                if deleted_ids:
                    LOGGER.debug("Detected deleted rules in %s: %s", rule_type, deleted_ids)
                    async_dispatcher_send(self.hass, f"{DOMAIN}_cleanup")

        # Update known rules
        self._known_rules = current_rules
