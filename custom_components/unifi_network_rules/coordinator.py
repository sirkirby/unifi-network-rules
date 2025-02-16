from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed

from .udm_api import UDMAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class UDMUpdateCoordinator(DataUpdateCoordinator):
    """Data update coordinator for UniFi Network Rules."""

    def __init__(self, hass: HomeAssistant, api: UDMAPI, name: str, update_interval: int) -> None:
        """Initialize the UDM coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(minutes=update_interval),
        )
        self.api = api

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API."""
        _LOGGER.debug("Coordinator: Starting data update")
        data = {}
        
        try:
            if not hasattr(self.api, 'capabilities'):
                _LOGGER.error("API capabilities not initialized. Cannot fetch data.")
                return data

            _LOGGER.debug(
                "Updating with capabilities - Traffic Routes: %s, Zone Firewall: %s, Legacy Firewall: %s",
                self.api.capabilities.traffic_routes,
                self.api.capabilities.zone_based_firewall,
                self.api.capabilities.legacy_firewall
            )

            # Only proceed if we have at least one capability
            if not any([
                self.api.capabilities.traffic_routes,
                self.api.capabilities.zone_based_firewall,
                self.api.capabilities.legacy_firewall
            ]):
                _LOGGER.error("No capabilities available. Cannot fetch any data.")
                raise UpdateFailed("No capabilities detected on the device")

            # Fetch port forwarding rules
            _LOGGER.debug("Fetching port forwarding rules")
            try:
                port_fwd_success, port_fwd_rules, port_fwd_error = await self.api.get_port_forward_rules()
                if not port_fwd_success:
                    _LOGGER.error("Failed to fetch port forwarding rules: %s", port_fwd_error)
                else:
                    data['port_forward_rules'] = port_fwd_rules or []
            except Exception as e:
                _LOGGER.error("Error fetching port forwarding rules: %s", str(e))

            # Always try traffic routes if capability is present
            if self.api.capabilities.traffic_routes:
                _LOGGER.debug("Fetching traffic routes")
                try:
                    routes_success, routes, routes_error = await self.api.get_traffic_routes()
                    if not routes_success:
                        _LOGGER.error("Failed to fetch traffic routes: %s", routes_error)
                    else:
                        data['traffic_routes'] = routes or []
                except Exception as e:
                    _LOGGER.error("Error fetching traffic routes: %s", str(e))

            # Fetch firewall data based on detected capabilities
            if self.api.capabilities.zone_based_firewall:
                _LOGGER.debug("Fetching zone-based firewall policies")
                try:
                    policies_success, policies, policies_error = await self.api.get_firewall_policies()
                    if not policies_success:
                        _LOGGER.error("Failed to fetch policies: %s", policies_error)
                    else:
                        data['firewall_policies'] = policies or []
                except Exception as e:
                    _LOGGER.error("Error fetching firewall policies: %s", str(e))
            elif self.api.capabilities.legacy_firewall:
                _LOGGER.debug("Fetching legacy firewall rules")
                try:
                    rules_success, rules, rules_error = await self.api.get_legacy_firewall_rules()
                    if not rules_success:
                        _LOGGER.error("Failed to fetch legacy firewall rules: %s", rules_error)
                    else:
                        data['firewall_rules'] = {'data': rules or []}

                    traffic_success, traffic, traffic_error = await self.api.get_legacy_traffic_rules()
                    if not traffic_success:
                        _LOGGER.error("Failed to fetch legacy traffic rules: %s", traffic_error)
                    else:
                        data['traffic_rules'] = traffic or []
                except Exception as e:
                    _LOGGER.error("Error fetching legacy rules: %s", str(e))

            # Verify we got at least some data
            if not data:
                _LOGGER.error("No data was successfully retrieved from any endpoint")
                raise UpdateFailed("Failed to retrieve any data from the device")

            _LOGGER.debug("Successfully retrieved data for: %s", list(data.keys()))
            return data

        except Exception as e:
            _LOGGER.exception("Unexpected error in coordinator update: %s", str(e))
            raise UpdateFailed(f"Data update failed: {str(e)}")
