"""Cleanup services for UniFi Network Rules integration."""
from __future__ import annotations

from typing import Dict

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from ..const import DOMAIN, LOGGER
from ..helpers.rule import is_our_entity
from .constants import (
    SERVICE_FORCE_CLEANUP,
    SERVICE_FORCE_REMOVE_STALE,
    SIGNAL_ENTITIES_CLEANUP,
)

# Schema for force_remove_stale service
FORCE_REMOVE_STALE_SCHEMA = vol.Schema(
    {
        vol.Optional("remove_all"): cv.boolean,
    }
)

async def async_force_cleanup(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Handle force cleanup service call."""
    # Clean up all entities
    LOGGER.debug("Sending %s signal for all entities", SIGNAL_ENTITIES_CLEANUP)
    async_dispatcher_send(hass, SIGNAL_ENTITIES_CLEANUP, None)
    LOGGER.info("Force cleanup signal sent to all entities")

async def async_force_remove_stale(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Handle force removal of stale entities."""
    remove_all = call.data.get("remove_all", False)
    
    # Get the entity registry
    entity_registry = async_get_entity_registry(hass)
    entities_removed = 0
    
    # Find entities from this integration using the reliable helper
    for entity_id, entity in list(entity_registry.entities.items()):
        # Use our reliable helper function to check if entity belongs to this integration
        if is_our_entity(entity, DOMAIN):
            # Only process entities from our integration
            try:
                unique_id = entity.unique_id
                # Check if entity should be removed
                if remove_all or entity.disabled or hass.states.get(entity_id) is None or hass.states.get(entity_id).state == "unavailable":
                    # Remove entity from registry
                    LOGGER.info("Removing entity %s (unique_id: %s) from registry", 
                            entity_id, unique_id)
                    entity_registry.async_remove(entity_id)
                    entities_removed += 1
            except Exception as err:
                LOGGER.warning("Error processing entity %s: %s", entity_id, err)
    
    LOGGER.info("Removed %d entities from registry", entities_removed)
    return {"entities_removed": entities_removed}

async def async_setup_cleanup_services(hass: HomeAssistant, coordinators: Dict) -> None:
    """Set up cleanup-related services."""
    
    # Handle the force cleanup service
    async def handle_force_cleanup(call: ServiceCall) -> None:
        await async_force_cleanup(hass, coordinators, call)
        
    # Handle the force remove stale service  
    async def handle_force_remove_stale(call: ServiceCall) -> None:
        return await async_force_remove_stale(hass, coordinators, call)
    
    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_FORCE_CLEANUP, handle_force_cleanup, schema=vol.Schema({})
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_FORCE_REMOVE_STALE, handle_force_remove_stale, schema=FORCE_REMOVE_STALE_SCHEMA
    )