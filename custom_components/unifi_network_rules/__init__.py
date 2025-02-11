"""Support for UniFi Network Rules."""
import json
import logging
from datetime import timedelta
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL
)
from .udm_api import UDMAPI
from .coordinator import UDMUpdateCoordinator
from . import services
from .utils import logger
from .utils.logger import log_call

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["switch"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

@log_call
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the UniFi Network Rules component."""
    logger.debug("Starting async_setup")
    hass.data.setdefault(DOMAIN, {})
    try:
        import functools
        strings_path = os.path.join(os.path.dirname(__file__), "custom_strings.json")
        def read_json_file(path: str):
            with open(path, "r") as f:
                return json.load(f)

        hass.data[DOMAIN]["strings"] = await hass.async_add_executor_job(read_json_file, strings_path)
    except Exception as e:
        _LOGGER.error("Error loading strings: %s", e)
    return True

@log_call
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi Network Rules from a config entry."""
    logger.debug("Starting async_setup_entry")
    
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    logger.debug("Creating UDMAPI instance")
    api = UDMAPI(host, username, password)
    
    try:
        logger.debug("Attempting initial login")
        success, error = await api.authenticate_session()
        if not success:
            _LOGGER.error(f"Initial login failed: {error}")
            await api.cleanup()
            raise ConfigEntryNotReady(f"Login failed: {error}")

        logger.debug("Detecting UDM capabilities")
        if not await api.detect_capabilities():
            _LOGGER.error("Failed to detect UDM capabilities")
            await api.cleanup()
            raise ConfigEntryNotReady("Failed to detect UDM capabilities")

    except Exception as e:
        _LOGGER.exception("Exception during setup")
        await api.cleanup()
        raise ConfigEntryNotReady(f"Setup failed: {str(e)}") from e

    logger.debug("Creating coordinator")
    coordinator = UDMUpdateCoordinator(hass, api, update_interval)

    logger.debug("Performing initial data fetch")
    await coordinator.async_config_entry_first_refresh()

    if coordinator.data is None:
        error_msg = "No data received from UniFi Network during setup"
        _LOGGER.error(error_msg)
        await api.cleanup()
        raise ConfigEntryNotReady(error_msg)

    logger.debug("Initial coordinator data:")
    if api.capabilities.zone_based_firewall:
        logger.debug("Firewall Policies: %d", len(coordinator.data.get("firewall_policies", [])))
    if api.capabilities.legacy_firewall:
        logger.debug("Legacy Firewall Rules: %d", len(coordinator.data.get("firewall_rules", {}).get("data", [])))
        logger.debug("Legacy Traffic Rules: %d", len(coordinator.data.get("traffic_rules", [])))

    logger.debug("Storing API and coordinator")
    hass.data[DOMAIN][entry.entry_id] = {
        'api': api,
        'coordinator': coordinator,
    }

    await services.async_setup_services(hass)

    logger.debug("Setting up platform")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    logger.debug("Registering cleanup")
    entry.async_on_unload(cleanup_api(hass, entry))

    return True

def cleanup_api(hass: HomeAssistant, entry: ConfigEntry):
    @log_call
    async def _async_cleanup():
        """Clean up API resources."""
        logger.debug("Starting cleanup")
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            api = hass.data[DOMAIN][entry.entry_id].get('api')
            if api is not None:
                await api.cleanup()
        logger.debug("Cleanup complete")

    return _async_cleanup

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    logger.debug("Starting unload")
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            api = hass.data[DOMAIN][entry.entry_id].get('api')
            if api is not None:
                await api.cleanup()
            hass.data[DOMAIN].pop(entry.entry_id)
    
    logger.debug("Unload complete")
    return unload_ok