"""Support for UniFi Network Rules."""
import asyncio
import logging
from datetime import timedelta, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    CONF_MAX_RETRIES,
    CONF_RETRY_DELAY,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL
)
from .udm_api import UDMAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["switch"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the UniFi Network Rules component."""
    _LOGGER.debug("Starting async_setup")
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi Network Rules from a config entry."""
    _LOGGER.debug("Starting async_setup_entry")
    
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    _LOGGER.debug("Creating UDMAPI instance")
    api = UDMAPI(host, username, password)
    
    # Basic login check
    try:
        _LOGGER.debug("Attempting initial login")
        success, error = await api.authenticate_session()
        if not success:
            _LOGGER.error(f"Initial login failed: {error}")
            await api.cleanup()
            raise ConfigEntryNotReady(f"Login failed: {error}")
    except Exception as e:
        _LOGGER.exception("Exception during login")
        await api.cleanup()
        raise ConfigEntryNotReady(f"Login failed: {str(e)}") from e

    async def async_update_data():
        """Fetch data from API."""
        _LOGGER.debug("Starting data update")
        try:
            # Get firewall policies
            policies_success, policies, policies_error = await api.get_firewall_policies()
            if not policies_success:
                _LOGGER.error(f"Failed to fetch policies: {policies_error}")
                raise UpdateFailed(f"Failed to fetch policies: {policies_error}")
            
            _LOGGER.debug(f"Retrieved {len(policies) if policies else 0} firewall policies")

            # Get traffic routes
            routes_success, routes, routes_error = await api.get_traffic_routes()
            if not routes_success:
                _LOGGER.error(f"Failed to fetch routes: {routes_error}")
                raise UpdateFailed(f"Failed to fetch routes: {routes_error}")
            
            _LOGGER.debug(f"Retrieved {len(routes) if routes else 0} traffic routes")

            return {
                "firewall_policies": policies or [],
                "traffic_routes": routes or []
            }
        except Exception as e:
            _LOGGER.exception("Error in update_data")
            raise UpdateFailed(f"Data update failed: {str(e)}")

    _LOGGER.debug("Creating coordinator")
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="udm_rule_manager",
        update_method=async_update_data,
        update_interval=timedelta(minutes=update_interval),
    )

    # Perform initial data fetch
    _LOGGER.debug("Performing initial data fetch")
    await coordinator.async_config_entry_first_refresh()

    # Verify we have data before proceeding
    if not coordinator.data:
        error_msg = "No data received from UniFi Network during setup"
        _LOGGER.error(error_msg)
        await api.cleanup()
        raise ConfigEntryNotReady(error_msg)

    # Log the initial data for debugging
    _LOGGER.debug("Initial coordinator data:")
    _LOGGER.debug("Firewall Policies: %d", len(coordinator.data.get("firewall_policies", [])))
    _LOGGER.debug("Traffic Routes: %d", len(coordinator.data.get("traffic_routes", [])))

    # Store API and coordinator
    _LOGGER.debug("Storing API and coordinator")
    hass.data[DOMAIN][entry.entry_id] = {
        'api': api,
        'coordinator': coordinator,
    }

    # Set up platform
    _LOGGER.debug("Setting up platform")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register cleanup
    _LOGGER.debug("Registering cleanup")
    entry.async_on_unload(cleanup_api(hass, entry))

    return True

def cleanup_api(hass: HomeAssistant, entry: ConfigEntry):
    """Create cleanup callback that can be used as an on_unload handler."""
    async def _async_cleanup():
        """Clean up API resources."""
        _LOGGER.debug("Starting cleanup")
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            api = hass.data[DOMAIN][entry.entry_id].get('api')
            if api is not None:
                await api.cleanup()
        _LOGGER.debug("Cleanup complete")

    return _async_cleanup

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Starting unload")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            api = hass.data[DOMAIN][entry.entry_id].get('api')
            if api is not None:
                await api.cleanup()
            hass.data[DOMAIN].pop(entry.entry_id)
    
    _LOGGER.debug("Unload complete")
    return unload_ok