"""Support for UniFi Network Rules."""
from __future__ import annotations
from typing import Any
import json
from datetime import timedelta
import os

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
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    api = UDMAPI(host, username, password)
    api.hass = hass

    try:
        if not await api.authenticate_session():
            raise ConfigEntryNotReady("Failed to authenticate")
        if not await api.detect_capabilities():
            raise ConfigEntryNotReady("Failed to detect capabilities")

        coordinator = UnifiRuleUpdateCoordinator(
            hass,
            api,
            timedelta(seconds=update_interval)
        )

        await coordinator.async_config_entry_first_refresh()

        websocket = UnifiRuleWebsocket(hass, api, f"unifi_rules-{entry.entry_id}")
        websocket.coordinator = coordinator  # Store coordinator reference
        websocket.set_message_handler(coordinator.handle_websocket_message)

        hass.data[DOMAIN][entry.entry_id] = {
            'api': api,
            'coordinator': coordinator,
            'websocket': websocket
        }

        websocket.start()
        await services.async_setup_services(hass)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        return True

    except Exception as err:
        await api.cleanup()
        raise ConfigEntryNotReady(f"Failed to setup: {err}") from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle unload of an entry."""
    try:
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            entry_data = hass.data[DOMAIN][entry.entry_id]
            
            if 'websocket' in entry_data:
                await entry_data['websocket'].stop_and_wait()
            
            if 'api' in entry_data:
                await entry_data['api'].cleanup()
        
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        
        if unload_ok:
            hass.data[DOMAIN].pop(entry.entry_id)
            
        return unload_ok
        
    except Exception as e:
        LOGGER.error("Error unloading entry: %s", str(e))
        return False