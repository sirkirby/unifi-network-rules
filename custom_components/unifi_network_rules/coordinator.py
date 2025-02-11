from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .utils import logger

class UDMUpdateCoordinator(DataUpdateCoordinator):
    """Data update coordinator for UniFi Network Rules."""

    def __init__(self, hass, api, update_interval: int):
        self.api = api
        self._update_interval = update_interval
        super().__init__(
            hass,
            logger,  # Pass our unified logger
            name="udm_rule_manager",
            update_interval=timedelta(minutes=update_interval),
            update_method=self.async_update_data,
        )

    async def async_update_data(self):
        """Fetch data from API."""
        logger.debug("Coordinator: Starting data update")
        data = {}
        try:
            if self.api.capabilities.traffic_routes:
                logger.debug("Coordinator: Fetching traffic routes")
                routes_success, routes, routes_error = await self.api.get_traffic_routes()
                if not routes_success:
                    raise UpdateFailed(f"Failed to fetch traffic routes: {routes_error}")
                data['traffic_routes'] = routes or []

            if self.api.capabilities.zone_based_firewall:
                logger.debug("Coordinator: Fetching zone-based firewall policies")
                policies_success, policies, policies_error = await self.api.get_firewall_policies()
                if not policies_success:
                    raise UpdateFailed(f"Failed to fetch policies: {policies_error}")
                data['firewall_policies'] = policies or []

            if self.api.capabilities.legacy_firewall:
                logger.debug("Coordinator: Fetching legacy firewall rules")
                rules_success, rules, rules_error = await self.api.get_legacy_firewall_rules()
                if not rules_success:
                    raise UpdateFailed(f"Failed to fetch legacy firewall rules: {rules_error}")
                data['firewall_rules'] = {'data': rules or []}

                logger.debug("Coordinator: Fetching legacy traffic rules")
                traffic_success, traffic, traffic_error = await self.api.get_legacy_traffic_rules()
                if not traffic_success:
                    raise UpdateFailed(f"Failed to fetch legacy traffic rules: {traffic_error}")
                data['traffic_rules'] = traffic or []

            logger.debug("Coordinator: Final data keys: %s", list(data.keys()))
            return data
        except Exception as e:
            logger.debug("Coordinator: Error in update_data: %s", str(e))
            raise UpdateFailed(f"Data update failed: {str(e)}")
