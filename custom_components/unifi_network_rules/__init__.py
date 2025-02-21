"""Support for UniFi Network Rules."""
from __future__ import annotations
from typing import Any
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_VERIFY_SSL, Platform
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    LOGGER
)
from .udm_api import UDMAPI, CannotConnect, InvalidAuth
from .websocket import UnifiRuleWebsocket
from .coordinator import UnifiRuleUpdateCoordinator
from . import services

PLATFORMS: list[Platform] = [Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up UniFi Network Rules component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi Network Rules from a config entry."""
    try:
        # Initialize API
        api = UDMAPI(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
        )
        await api.async_init(hass)

        # Create and start websocket
        websocket = UnifiRuleWebsocket(hass, api, entry.entry_id)
        
        # Create coordinator and initialize it
        coordinator = UnifiRuleUpdateCoordinator(
            hass,
            api,
            websocket,
        )

        # Start websocket after coordinator is ready
        websocket.start()

        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "api": api,
            "coordinator": coordinator,
            "websocket": websocket,
        }

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Register cleanup using callback directly
        entry.async_on_unload(coordinator.shutdown)
        
        return True

    except CannotConnect as err:
        raise ConfigEntryNotReady("Cannot connect to host") from err
    except InvalidAuth as err:
        raise ConfigEntryNotReady("Invalid authentication") from err
    except Exception as err:
        LOGGER.error("Failed to setup UniFi Network Rules: %s", err)
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        api: UDMAPI = entry_data["api"]
        websocket: UnifiRuleWebsocket = entry_data["websocket"]
        coordinator: UnifiRuleUpdateCoordinator = entry_data["coordinator"]
        
        # Clean up everything
        await coordinator.shutdown()
        await websocket.stop_and_wait()
        await api.cleanup()

    return unload_ok