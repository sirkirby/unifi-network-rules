"""Support for UniFi Network Rules."""
from __future__ import annotations
from typing import Any
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    LOGGER
)
from .udm_api import UDMAPI
from .websocket import UnifiRuleWebsocket
from .coordinator import UnifiRuleUpdateCoordinator
from . import services

PLATFORMS: list[str] = ["switch"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up UniFi Network Rules component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi Network Rules from a config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    if entry.entry_id in hass.data[DOMAIN]:
        LOGGER.debug("Entry %s already setup, cleaning up first", entry.entry_id)
        await async_unload_entry(hass, entry)
    
    LOGGER.debug("Setting up UniFi Network Rules integration")
    
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    api = UDMAPI(host, username, password)

    try:
        # Initialize the API first
        await api.async_init(hass)

        # Initialize coordinator
        coordinator = UnifiRuleUpdateCoordinator(
            hass,
            api,
            timedelta(seconds=update_interval)
        )

        # Initialize websocket connection
        websocket = UnifiRuleWebsocket(hass, api, f"{DOMAIN}-{entry.entry_id}")
        websocket.set_message_handler(coordinator.handle_websocket_message)
        
        # Store references in hass.data
        hass.data[DOMAIN][entry.entry_id] = {
            "api": api,
            "coordinator": coordinator,
            "websocket": websocket
        }

        # Set up services first
        await services.async_setup_services(hass)
        
        # Perform initial data refresh before platform setup
        await coordinator.async_config_entry_first_refresh()

        # Set up the platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Start websocket last after everything is set up
        websocket.start()

        return True

    except Exception as err:
        LOGGER.exception("Failed to setup UniFi Network Rules: %s", str(err))
        if entry.entry_id in hass.data[DOMAIN]:
            await async_unload_entry(hass, entry)
        raise ConfigEntryNotReady(f"Setup failed: {err}") from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle unload of an entry."""
    try:
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            entry_data = hass.data[DOMAIN][entry.entry_id]
            
            unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
            
            if "websocket" in entry_data:
                await entry_data["websocket"].stop_and_wait()
            
            if "api" in entry_data:
                await entry_data["api"].cleanup()
            
            if unload_ok:
                hass.data[DOMAIN].pop(entry.entry_id)
            
            return unload_ok
        
        return True
        
    except Exception as e:
        LOGGER.error("Error unloading entry: %s", str(e))
        return False