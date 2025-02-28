"""Support for UniFi Network Rules."""
from __future__ import annotations
from typing import Any, Dict, List
from datetime import timedelta
import logging
import importlib
import asyncio
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_VERIFY_SSL, Platform
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

# Import aiounifi interfaces at module level from specific modules
from aiounifi.interfaces.firewall_policies import FirewallPolicies
from aiounifi.interfaces.firewall_zones import FirewallZones
from aiounifi.interfaces.port_forwarding import PortForwarding
from aiounifi.interfaces.traffic_rules import TrafficRules
from aiounifi.interfaces.traffic_routes import TrafficRoutes
from aiounifi.interfaces.wlans import Wlans

from .const import (
    DOMAIN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    CONF_SITE,
    DEFAULT_SITE,
    LOGGER
)

# Import the modular API implementation
from .udm import UDMAPI, CannotConnect, InvalidAuth

# Import local modules at the module level
from .websocket import UnifiRuleWebsocket
from .coordinator import UnifiRuleUpdateCoordinator
from .services import async_setup_services, async_unload_services

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
            # Register interfaces
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
        
        # Create the coordinator for updates
        coordinator = UnifiRuleUpdateCoordinator(
            hass,
            api,
            websocket,
            update_interval=update_interval,
        )

        # Register on_entity_create callback
        async def async_create_entity(rule_type: str, rule: Any) -> None:
            """Create a new entity for a newly discovered rule."""
            platform = entity_platform.async_get_current_platform()
            if not platform:
                LOGGER.warning("No platform available for entity creation")
                return
            
            # Create the appropriate entity type based on the rule type
            entity = None
            if rule_type == "port_forwards":
                from .switch import UnifiPortForwardSwitch
                entity = UnifiPortForwardSwitch(hass, coordinator, rule, entry.entry_id)
            elif rule_type == "traffic_routes":
                from .switch import UnifiTrafficRouteSwitch
                entity = UnifiTrafficRouteSwitch(hass, coordinator, rule, entry.entry_id)
            elif rule_type == "firewall_policies":
                from .switch import UnifiFirewallPolicySwitch
                entity = UnifiFirewallPolicySwitch(hass, coordinator, rule, entry.entry_id)
            elif rule_type == "traffic_rules":
                from .switch import UnifiTrafficRuleSwitch
                entity = UnifiTrafficRuleSwitch(hass, coordinator, rule, entry.entry_id)
            elif rule_type == "legacy_firewall_rules":
                from .switch import UnifiLegacyFirewallRuleSwitch
                entity = UnifiLegacyFirewallRuleSwitch(hass, coordinator, rule, entry.entry_id)
            elif rule_type == "wlans":
                from .switch import UnifiWlanSwitch
                entity = UnifiWlanSwitch(hass, coordinator, rule, entry.entry_id)
            
            if entity:
                await platform.async_add_entities([entity])
            else:
                LOGGER.warning("Could not create entity for rule type: %s", rule_type)
        
        coordinator.on_create_entity = async_create_entity

        # Start websocket after coordinator is ready
        websocket.start()

        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "api": api,
            "coordinator": coordinator,
            "websocket": websocket,
            "loaded_platforms": set(PLATFORMS),  # Assume all platforms will be loaded
        }
        
        # Set up platforms using the new method
        try:
            LOGGER.debug("Setting up platforms: %s", PLATFORMS)
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
            LOGGER.debug("All platforms setup completed successfully")
        except Exception as platform_error:
            LOGGER.exception("Error setting up platforms: %s", platform_error)
            # Since we can't tell which specific platforms failed with async_forward_entry_setups,
            # we'll keep all platforms in loaded_platforms and let the unload handle any errors
        
        # Register coordinator with services
        if "services" in hass.data[DOMAIN] and "register_coordinator" in hass.data[DOMAIN]["services"]:
            LOGGER.debug("Registering coordinator with services")
            register_coordinator = hass.data[DOMAIN]["services"]["register_coordinator"]
            register_coordinator(entry.entry_id, coordinator)
        else:
            LOGGER.warning("Could not register coordinator with services - register_coordinator method missing")
        
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
    # Only unload platforms that were successfully loaded
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        entry_data = hass.data[DOMAIN][entry.entry_id]
        loaded_platforms = entry_data.get("loaded_platforms", set())
        
        LOGGER.debug("Unloading entry: %s with loaded platforms: %s", entry.entry_id, loaded_platforms)
        
        # Unregister coordinator from services
        if "services" in hass.data[DOMAIN] and "unregister_coordinator" in hass.data[DOMAIN]["services"]:
            LOGGER.debug("Unregistering coordinator for entry: %s", entry.entry_id)
            unregister_coordinator = hass.data[DOMAIN]["services"]["unregister_coordinator"]
            unregister_coordinator(entry.entry_id)
        
        # Attempt to unload all platforms at once
        try:
            unload_ok = await hass.config_entries.async_unload_platforms(entry, loaded_platforms)
            if not unload_ok:
                LOGGER.warning("Failed to unload one or more platforms: %s", loaded_platforms)
        except Exception as unload_error:
            LOGGER.exception("Error unloading platforms: %s", unload_error)
            unload_ok = False
        
        if unload_ok:
            # Clean up data if unload was successful
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
            
            # Remove entry from hass.data
            hass.data[DOMAIN].pop(entry.entry_id)

        return unload_ok
    
    LOGGER.warning("Entry %s not found in hass.data[%s]", entry.entry_id, DOMAIN)
    return False

async def async_refresh(self) -> bool:
    """Refresh data from API.
    
    This should now just request a coordinator refresh, which will
    call _async_update_data() and handle everything.
    """
    LOGGER.debug("Manual refresh requested")
    await self.async_request_refresh()
    return True