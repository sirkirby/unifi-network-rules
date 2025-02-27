"""Support for UniFi Network Rules."""
from __future__ import annotations
from typing import Any
from datetime import timedelta
import logging

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
    CONF_SITE,
    DEFAULT_SITE,
    LOGGER
)

# Try to import required modules
try:
    from .udm_api import UDMAPI, CannotConnect, InvalidAuth
    from .websocket import UnifiRuleWebsocket
    from .coordinator import UnifiRuleUpdateCoordinator
    from .services import async_setup_services, async_unload_services
except ImportError as err:
    LOGGER.error(
        "Failed to import required modules. This may happen if an older version of "
        "aiounifi is already loaded. Error: %s", err
    )
    LOGGER.warning(
        "If this is the first restart after installation, try restarting Home Assistant "
        "again to resolve dependency conflicts. This integration requires aiounifi >= 82.0.0"
    )
    raise

PLATFORMS: list[Platform] = [Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up UniFi Network Rules component."""
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize the services dictionary to store coordinator registration functions
    hass.data[DOMAIN]["services"] = {}
    
    # Set up services
    await async_setup_services(hass)
    
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi Network Rules from a config entry."""
    try:
        # Initialize API
        api = UDMAPI(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            site=entry.data.get(CONF_SITE, DEFAULT_SITE),
            verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
        )
        
        # Initialize API with required interfaces
        await api.async_init(hass)
        
        # Register required interfaces after initialization
        if hasattr(api.controller, "register_interface"):
            # Register interfaces based on UniFi OS version
            from aiounifi.interfaces.firewall_policies import FirewallPolicies
            from aiounifi.interfaces.firewall_zones import FirewallZones
            from aiounifi.interfaces.port_forwarding import PortForwarding
            from aiounifi.interfaces.traffic_rules import TrafficRules
            from aiounifi.interfaces.traffic_routes import TrafficRoutes
            from aiounifi.interfaces.wlans import Wlans
            
            api.controller.register_interface(FirewallPolicies)
            api.controller.register_interface(FirewallZones)
            api.controller.register_interface(PortForwarding)
            api.controller.register_interface(TrafficRules)
            api.controller.register_interface(TrafficRoutes)
            api.controller.register_interface(Wlans)
            
            # Initialize interfaces
            await api.controller.initialize()

        # Create websocket
        websocket = UnifiRuleWebsocket(hass, api, entry.entry_id)
        
        # Get update interval from config entry data or options
        update_interval = entry.options.get(
            CONF_UPDATE_INTERVAL, 
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
        
        # Create coordinator and initialize it
        coordinator = UnifiRuleUpdateCoordinator(
            hass,
            api,
            websocket,
            update_interval=update_interval,
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

        # DO NOT overwrite the entry data dictionary with just the coordinator
        # hass.data[DOMAIN][entry.entry_id] = coordinator
        
        # Register coordinator with services
        if "services" in hass.data[DOMAIN] and "register_coordinator" in hass.data[DOMAIN]["services"]:
            LOGGER.debug("Registering coordinator with services")
            register_coordinator = hass.data[DOMAIN]["services"]["register_coordinator"]
            register_coordinator(entry.entry_id, coordinator)
        else:
            LOGGER.warning("Could not register coordinator with services - register_coordinator method missing")
        
        # Register async_unload_entry for cleanup
        async def async_unload_entry_wrapper(entry):
            # Unregister coordinator from services
            if "services" in hass.data[DOMAIN] and "unregister_coordinator" in hass.data[DOMAIN]["services"]:
                unregister_coordinator = hass.data[DOMAIN]["services"]["unregister_coordinator"]
                unregister_coordinator(entry.entry_id)
            
            return await async_unload_entry(hass, entry)
        
        entry.async_on_unload(lambda: async_unload_entry_wrapper(entry))
        
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
        
        # Clean up additional listeners if they exist
        if "unsub_listeners" in entry_data:
            for unsub in entry_data["unsub_listeners"]:
                unsub()
        
        # Clean up everything
        coordinator.shutdown()
        await websocket.stop_and_wait()
        await api.cleanup()

    return unload_ok