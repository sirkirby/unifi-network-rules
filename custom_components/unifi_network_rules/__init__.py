"""Support for UniFi Network Rules."""
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
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi Network Rules from a config entry."""
    _LOGGER.debug("Setting up UniFi Network Rules config entry")
    
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    max_retries = entry.data.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES)
    retry_delay = entry.data.get(CONF_RETRY_DELAY, DEFAULT_RETRY_DELAY)

    api = UDMAPI(host, username, password, max_retries=max_retries, retry_delay=retry_delay)
    
    # Test the connection with quick auth check
    try:
        success, error = await api.quick_auth_check()
        if not success:
            await api.cleanup()
            _LOGGER.error(f"Failed to connect to UDM: {error}")
            raise ConfigEntryNotReady(f"Failed to connect to UDM: {error}")
    except Exception as e:
        await api.cleanup()
        _LOGGER.exception("Error during setup")
        raise ConfigEntryNotReady(f"Setup failed: {str(e)}") from e

    async def async_update_data():
        """Fetch data from API."""
        try:
            # Add delay between requests
            policies_success, policies, policies_error = await api.get_firewall_policies()
            if not policies_success:
                raise Exception(f"Failed to fetch firewall policies: {policies_error}")
                
            await asyncio.sleep(2)  # Wait between requests
            
            routes_success, traffic_routes, routes_error = await api.get_traffic_routes()
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
        update_interval=timedelta(minutes=max(update_interval, 15)),
    )

    # Store api and coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        'api': api,
        'coordinator': coordinator,
    }

    # Register cleanup for config entry
    entry.async_on_unload(
        lambda: hass.async_create_task(cleanup_api(hass, entry))
    )

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Initial data fetch
    try:
        _LOGGER.debug("Performing initial data refresh")
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error(f"Initial data refresh failed: {err}")
        await cleanup_api(hass, entry)
        raise ConfigEntryNotReady from err

    return True

async def cleanup_api(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up API resources."""
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        api = hass.data[DOMAIN][entry.entry_id].get('api')
        if api is not None:
            try:
                await api.cleanup()
            except Exception as e:
                _LOGGER.error(f"Error during API cleanup: {e}")

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading UniFi Network Rules config entry")
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Clean up API
        await cleanup_api(hass, entry)
        # Remove entry data
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)