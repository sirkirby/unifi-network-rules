"""Support for UniFi Network Rules."""
import json
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
    DEFAULT_UPDATE_INTERVAL,
    LOGGER
)
from .udm_api import UDMAPI
from .websocket import UnifiRuleWebsocket
from .coordinator import UDMUpdateCoordinator
from . import services
from .utils.logger import log_call
from .entity_loader import UnifiRuleEntityLoader

PLATFORMS: list[str] = ["switch"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up UniFi Network Rules component."""
    hass.data.setdefault(DOMAIN, {})
    return True

@log_call
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi Network Rules from a config entry."""
    LOGGER.debug("Starting async_setup_entry")
    
    # Initialize the domain data if not already done
    hass.data.setdefault(DOMAIN, {})
    
    # If coordinator is already set up for this entry, skip reinitialization
    if entry.entry_id in hass.data[DOMAIN]:
        LOGGER.debug("Coordinator already exists for entry %s, skipping setup_entry", entry.entry_id)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True
    
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    LOGGER.debug("Creating UDMAPI instance")
    api = UDMAPI(host, username, password)
    api.hass = hass  # Set the hass instance
    
    try:
        LOGGER.debug("Attempting initial login")
        success, error = await api.authenticate_session()
        if not success:
            LOGGER.error(f"Initial login failed: {error}")
            await api.cleanup()
            raise ConfigEntryNotReady(f"Login failed: {error}")
        LOGGER.debug("Detecting UDM capabilities")
        if not await api.detect_capabilities():
            LOGGER.error("Failed to detect UDM capabilities")
            await api.cleanup()
            raise ConfigEntryNotReady("Failed to detect UDM capabilities")
    except Exception as e:
        LOGGER.exception("Exception during setup")
        await api.cleanup()
        raise ConfigEntryNotReady(f"Setup failed: {str(e)}") from e

    LOGGER.debug("Creating coordinator")
    coordinator = UDMUpdateCoordinator(
        hass,
        api,
        f"UniFi Network Rules ({host})",
        update_interval
    )
    coordinator.config_entry = entry  # Set config entry before first refresh

    # Create entity loader
    entity_loader = UnifiRuleEntityLoader(hass, coordinator)
    
    # Initialize the entry's data structure
    hass.data[DOMAIN][entry.entry_id] = {
        'api': api,
        'coordinator': coordinator,
        'entity_loader': entity_loader,
    }

    # Perform initial data fetch
    LOGGER.debug("Performing initial data fetch")
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        error_msg = f"Failed to fetch initial data: {str(e)}"
        LOGGER.error(error_msg)
        await api.cleanup()
        raise ConfigEntryNotReady(error_msg)

    if not coordinator.data:
        error_msg = "No data received from UniFi Network during setup"
        LOGGER.error(error_msg)
        await api.cleanup()
        raise ConfigEntryNotReady(error_msg)

    # Create websocket handler with message callback
    websocket = UnifiRuleWebsocket(
        hass,
        api,
        f"unifi_rules-reachable-{entry.entry_id}"
    )
    # Store websocket handler in hass.data
    hass.data[DOMAIN][entry.entry_id]['websocket'] = websocket
    
    # Register coordinator as websocket message handler to the websocket handler itself
    websocket.coordinator_callback = coordinator.handle_websocket_message

    LOGGER.debug("Initial coordinator data:")
    if api.capabilities.zone_based_firewall:
        LOGGER.debug("Firewall Policies: %d", len(coordinator.data.get("firewall_policies", [])))
    if api.capabilities.legacy_firewall:
        LOGGER.debug("Legacy Firewall Rules: %d", len(coordinator.data.get("firewall_rules", {}).get("data", [])))
        LOGGER.debug("Legacy Traffic Rules: %d", len(coordinator.data.get("traffic_rules", [])))

    # Start websocket
    websocket.start()
    await services.async_setup_services(hass)
    
    LOGGER.debug("Setting up platform")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    LOGGER.debug("Registering WebSocket cleanup")
    entry.async_on_unload(
        lambda: hass.loop.create_task(websocket.stop_and_wait())
    )
    
    LOGGER.debug("Registering cleanup")
    entry.async_on_unload(cleanup_api(hass, entry))
    return True

def cleanup_api(hass: HomeAssistant, entry: ConfigEntry):
    @log_call
    async def _async_cleanup():
        """Clean up API resources."""
        LOGGER.debug("Starting cleanup")
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            entry_data = hass.data[DOMAIN][entry.entry_id]
            
            # Clean up entity loader
            if 'entity_loader' in entry_data:
                await entry_data['entity_loader'].async_unload_entities()
            
            # Clean up API
            api = entry_data.get('api')
            if api is not None:
                await api.cleanup()
                
        LOGGER.debug("Cleanup complete")

    return _async_cleanup

@log_call
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    LOGGER.debug("Starting unload")
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            entry_data = hass.data[DOMAIN][entry.entry_id]
            
            # Stop websocket
            if websocket := entry_data.get('websocket'):
                await websocket.stop_and_wait()
            
            # Clean up entity loader
            if 'entity_loader' in entry_data:
                await entry_data['entity_loader'].async_unload_entities()
            
            # Clean up API
            api = entry_data.get('api')
            if api is not None:
                await api.cleanup()
                
            hass.data[DOMAIN].pop(entry.entry_id)
    
    LOGGER.debug("Unload complete")
    return unload_ok