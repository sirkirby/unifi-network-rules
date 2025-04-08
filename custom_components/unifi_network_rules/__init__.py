"""Support for UniFi Network Rules."""
from __future__ import annotations
from typing import Any, Dict, List
from datetime import timedelta
import logging
import importlib
import asyncio
import async_timeout
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_VERIFY_SSL, Platform, CONF_PORT
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

# Import interface classes from aiounifi
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
    DEFAULT_SITE,
    LOGGER,
    PLATFORMS,
    CONF_SITE
)

# Import the modular API implementation
from .udm.api import UDMAPI

# Import local modules at the module level - ORDER MATTERS HERE
from .websocket import UnifiRuleWebsocket
from .coordinator import UnifiRuleUpdateCoordinator
from .services import async_setup_services, async_unload_services
from .helpers.rule import get_rule_id

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up UniFi Network Rules component."""
    # Initialize domain data if not already done
    hass.data.setdefault(DOMAIN, {})
    # Store shared data
    hass.data[DOMAIN].setdefault("shared", {})
    
    # Initialize services
    await async_setup_services(hass)
    
    # Create a semaphore for entity creation
    hass.data[DOMAIN]["_entity_creation_semaphore"] = asyncio.Semaphore(1)
    
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
        websocket_handler = UnifiRuleWebsocket(hass, api, entry.entry_id)
        
        # Setup the coordinator
        coordinator = UnifiRuleUpdateCoordinator(hass, api, websocket_handler)
        
        # Explicitly set the config_entry reference
        coordinator.config_entry = entry
        
        # Connect the websocket handler to the coordinator
        websocket_handler.set_callback(coordinator._handle_websocket_message)
        LOGGER.debug("Set websocket handler callback to coordinator's message handler")
        
        # Define entity removal callback
        @callback
        def handle_entity_removal(entity_id):
            """Handle entity removal by dispatching a signal."""
            LOGGER.debug("Entity removal callback triggered for: %s", entity_id)
            async_dispatcher_send(hass, f"{DOMAIN}_entity_removed", entity_id)
        
        # Register entity removal callback
        coordinator.set_entity_removal_callback(handle_entity_removal)
        
        # Store shared data for entity creation
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN].setdefault("shared", {})
        hass.data[DOMAIN]["shared"]["coordinator"] = coordinator
        hass.data[DOMAIN]["shared"]["config_entry_id"] = entry.entry_id
        
        # Create a structure to store entity platforms for later use
        hass.data[DOMAIN].setdefault("platforms", {})
        
        # Create a wrapper function to pass hass to async_create_entity
        async def create_entity_wrapper(rule_type: str, rule: Any) -> bool:
            result = await async_create_entity(hass, rule_type, rule)
            return result if result is not None else False
        
        # Store the entity creation function for use by the coordinator
        hass.data[DOMAIN]["async_create_entity"] = create_entity_wrapper
        
        # Store data in hass for component access
        hass.data[DOMAIN][entry.entry_id] = {
            "api": api,
            "coordinator": coordinator,
            "websocket": websocket_handler,
        }
        
        # Start initial data refresh
        await coordinator.async_config_entry_first_refresh()
        
        # Setup platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        # Start the websocket connection
        try:
            websocket_handler.start()
            LOGGER.info("WebSocket connection established successfully")
        except Exception as ws_err:  # pylint: disable=broad-except
            LOGGER.error("Error setting up WebSocket: %s", ws_err)
            # Continue even if WebSocket fails - we can still use polling
        
        # Register the coordinator with the services registry
        if "services" in hass.data[DOMAIN] and "register_coordinator" in hass.data[DOMAIN]["services"]:
            register_func = hass.data[DOMAIN]["services"]["register_coordinator"]
            register_func(entry.entry_id, coordinator)
            LOGGER.debug("Registered coordinator with services for entry_id: %s", entry.entry_id)
        else:
            LOGGER.warning("Could not register coordinator with services - services registry not initialized")
        
        # Capture platforms directly without using async_create_task
        def capture_platforms(*args):
            """Capture entity platforms synchronously."""
            try:
                from homeassistant.helpers import entity_platform
                platforms = entity_platform.async_get_platforms(hass, DOMAIN)
                for platform in platforms:
                    LOGGER.debug("Captured platform: %s for domain: %s", platform.domain, DOMAIN)
                    hass.data[DOMAIN]["platforms"][platform.domain] = platform
            except Exception as err:
                LOGGER.error("Error capturing platforms: %s", err)
        
        # Add this as a job to be run later, not directly during setup
        hass.loop.call_soon(capture_platforms)
        
        # Register entity registry services
        @callback
        def update_entity_registry_service(call):
            """Service to update entity ID in the entity registry."""
            entity_id = call.data.get("entity_id")
            new_entity_id = call.data.get("new_entity_id")
            
            registry = async_get_entity_registry(hass)
            try:
                registry.async_update_entity(entity_id, new_entity_id=new_entity_id)
                LOGGER.info("Updated entity ID from %s to %s", entity_id, new_entity_id)
            except Exception as err:
                LOGGER.error("Failed to update entity ID: %s", err)
        
        hass.services.async_register(
            DOMAIN,
            "update_entity_id",
            update_entity_registry_service,
            schema=vol.Schema({
                vol.Required("entity_id"): cv.entity_id,
                vol.Required("new_entity_id"): cv.string
            })
        )
        
        # Subscribe to entity registry events to handle dynamic entity addition
        @callback
        def _handle_entity_registry_updated(event):
            """Handle entity registry updates."""
            if event.data.get("action") != "create":
                return
                
            entity_id = event.data.get("entity_id", "")
            if not entity_id.startswith("switch.") or not DOMAIN in entity_id:
                return
                
            unique_id = event.data.get("unique_id", "")
            if not unique_id or not unique_id.startswith("unr_"):
                return
                
            LOGGER.info("New entity registered: %s (unique_id: %s)", entity_id, unique_id)
            
            # Force the entity to update its state
            async_dispatcher_send(hass, f"{DOMAIN}_entity_update_{unique_id}")
        
        # Register for entity registry updated events
        hass.bus.async_listen("entity_registry_updated", _handle_entity_registry_updated)
        
        return True
        
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
            await coordinator.async_shutdown()
            await websocket.async_stop()
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

async def async_create_entity(hass: HomeAssistant, rule_type: str, rule: Any) -> bool:
    """Create a new entity for a newly discovered rule.
    
    This streamlined implementation directly uses Home Assistant's entity platform
    to add new entities during runtime, which is more reliable than our previous approaches.
    
    Returns:
        bool: True if entity was successfully created, False otherwise.
    """
    import asyncio
    
    if not hass:
        LOGGER.error("Cannot create entity - Home Assistant instance not available")
        return False
    
    # Get shared data from hass
    if "shared" not in hass.data[DOMAIN]:
        LOGGER.error("Shared data not available for entity creation")
        return False
        
    shared_data = hass.data[DOMAIN]["shared"]
    coordinator = shared_data.get("coordinator")
    config_entry_id = shared_data.get("config_entry_id")
    
    if not coordinator or not config_entry_id:
        LOGGER.error("Required shared data missing for entity creation")
        return False
    
    # Get rule ID for consistent logging
    rule_id = get_rule_id(rule)
    if not rule_id:
        LOGGER.error("Cannot create entity - rule has no valid ID")
        return False
    
    # Check the entity registry first to avoid duplication
    from homeassistant.helpers.entity_registry import async_get as get_entity_registry
    entity_registry = get_entity_registry(hass)
    
    # If entity already exists in the registry, don't create it again
    existing_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, rule_id)
    if existing_entity_id:
        LOGGER.info("Entity already exists for rule with unique_id %s: %s", 
                  rule_id, existing_entity_id)
        # Instead of creating a new entity, dispatch an update event for this specific entity
        from homeassistant.helpers.dispatcher import async_dispatcher_send
        async_dispatcher_send(hass, f"{DOMAIN}_entity_update_{rule_id}")
        return True  # Consider this a success since the entity exists
    
    # Use a semaphore to prevent concurrent entity creation
    if not hasattr(hass.data[DOMAIN], "_entity_creation_semaphore"):
        hass.data[DOMAIN]["_entity_creation_semaphore"] = asyncio.Semaphore(1)
    
    # Only proceed if we can acquire the semaphore
    if hass.data[DOMAIN]["_entity_creation_semaphore"].locked():
        LOGGER.debug("Skipping entity creation as one is already in progress")
        return False
    
    async with hass.data[DOMAIN]["_entity_creation_semaphore"]:
        # Double-check entity doesn't exist after acquiring semaphore
        existing_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, rule_id)
        if existing_entity_id:
            LOGGER.info("Entity already exists for rule with unique_id %s: %s", 
                      rule_id, existing_entity_id)
            return True
            
        # Import appropriate entity class and create the entity
        if rule_type == "port_forwards":
            from .switch import UnifiPortForwardSwitch
            entity = UnifiPortForwardSwitch(coordinator, rule, rule_type, config_entry_id)
        elif rule_type == "traffic_routes":
            from .switch import UnifiTrafficRouteSwitch
            entity = UnifiTrafficRouteSwitch(coordinator, rule, rule_type, config_entry_id)
            
            # Also create the kill switch for traffic routes using the centralized function
            from .switch import create_traffic_route_kill_switch
            await create_traffic_route_kill_switch(
                hass, coordinator, rule, config_entry_id=config_entry_id
            )
        elif rule_type == "firewall_policies":
            from .switch import UnifiFirewallPolicySwitch
            entity = UnifiFirewallPolicySwitch(coordinator, rule, rule_type, config_entry_id)
        elif rule_type == "traffic_rules":
            from .switch import UnifiTrafficRuleSwitch
            entity = UnifiTrafficRuleSwitch(coordinator, rule, rule_type, config_entry_id)
        elif rule_type == "legacy_firewall_rules":
            from .switch import UnifiLegacyFirewallRuleSwitch
            entity = UnifiLegacyFirewallRuleSwitch(coordinator, rule, rule_type, config_entry_id)
        elif rule_type == "wlans":
            from .switch import UnifiWlanSwitch
            entity = UnifiWlanSwitch(coordinator, rule, rule_type, config_entry_id)
        elif rule_type == "qos_rules":
            from .switch import UnifiQoSRuleSwitch
            entity = UnifiQoSRuleSwitch(coordinator, rule, rule_type, config_entry_id)
        elif rule_type == "vpn_clients":
            from .switch import UnifiVPNClientSwitch
            entity = UnifiVPNClientSwitch(coordinator, rule, rule_type, config_entry_id)
        else:
            LOGGER.warning("Unknown rule type for entity creation: %s", rule_type)
            return False
            
        if not entity:
            LOGGER.warning("Could not create entity for rule type: %s", rule_type)
            return False
        
        # Log entity creation attempt
        LOGGER.info("Creating entity for %s %s (attempt 1/3)", 
                  rule_type, entity.name)

        # Get the switch platform from domain data
        try:
            if "platforms" in hass.data[DOMAIN] and "switch" in hass.data[DOMAIN]["platforms"]:
                platform = hass.data[DOMAIN]["platforms"]["switch"]
                
                # Add entity directly to the platform
                LOGGER.debug("Adding entity via platform reference")
                await platform.async_add_entities([entity])
                
                # Wait for entity to be registered and verify
                await asyncio.sleep(1)
                
                # Check registry to confirm entity was added
                entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, rule_id)
                
                if entity_id:
                    LOGGER.info("Successfully created entity: %s", entity_id)
                    return True
                else:
                    LOGGER.warning("Entity creation verification failed - entity not in registry")
            else:
                LOGGER.error("No platform reference available - trying fallback method")
                
                # Fallback: Get platforms dynamically
                from homeassistant.helpers import entity_platform
                platforms = entity_platform.async_get_platforms(hass, DOMAIN)
                
                for platform in platforms:
                    if platform.domain == "switch":
                        LOGGER.debug("Found switch platform dynamically")
                        await platform.async_add_entities([entity])
                        
                        # Wait for entity to be registered
                        await asyncio.sleep(1)
                        
                        # Check registry to confirm entity was added
                        entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, rule_id)
                        
                        if entity_id:
                            LOGGER.info("Successfully created entity via fallback: %s", entity_id)
                            return True
                        else:
                            LOGGER.warning("Entity creation failed via fallback - entity not in registry")
                        break
                
                LOGGER.error("Could not find switch platform for entity creation")
                return False
        except Exception as err:
            LOGGER.error("Error creating entity: %s", err)
            return False
    
    return False