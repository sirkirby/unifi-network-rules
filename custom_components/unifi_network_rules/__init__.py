import asyncio
import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, CONF_MAX_RETRIES, CONF_RETRY_DELAY, DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
from .udm_api import UDMAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["switch"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
   """Set up the UDM Rule Manager component."""
   hass.data.setdefault(DOMAIN, {})
   return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
   """Set up UDM Rule Manager from a config entry."""
   host = entry.data[CONF_HOST]
   username = entry.data[CONF_USERNAME]
   password = entry.data[CONF_PASSWORD]
   update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
   max_retries = entry.data.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES)
   retry_delay = entry.data.get(CONF_RETRY_DELAY, DEFAULT_RETRY_DELAY)

   api = UDMAPI(host, username, password, max_retries=max_retries, retry_delay=retry_delay)
   
   # Test the connection
   success, error_message = await api.login()
   if not success:
       raise ConfigEntryNotReady(f"Failed to connect to UDM: {error_message}")

   async def async_update_data():
    """Fetch data from API."""
    try:
        policies_success, policies, policies_error = await api.get_firewall_policies()
        routes_success, traffic_routes, routes_error = await api.get_traffic_routes()

        if not policies_success:
            raise Exception(f"Failed to fetch firewall policies: {policies_error}")
        if not routes_success:
            raise Exception(f"Failed to fetch traffic routes: {routes_error}")

        return {
            "firewall_policies": policies,
            "traffic_routes": traffic_routes
        }
    except Exception as e:
        _LOGGER.error(f"Error updating data: {str(e)}")
        raise

   coordinator = DataUpdateCoordinator(
       hass,
       _LOGGER,
       name="udm_rule_manager",
       update_method=async_update_data,
       update_interval=timedelta(minutes=update_interval),
   )

   # Fetch initial data
   await coordinator.async_config_entry_first_refresh()

   hass.data[DOMAIN][entry.entry_id] = {
       'api': api,
       'coordinator': coordinator
   }

   await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

   return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        api = hass.data[DOMAIN][entry.entry_id]['api']
        await api.cleanup()  # Cleanup API session
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok