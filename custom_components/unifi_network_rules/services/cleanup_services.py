"""Cleanup services for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from ..const import DOMAIN, LOGGER
from .constants import (
    SERVICE_FORCE_CLEANUP,
    SERVICE_FORCE_REMOVE_STALE,
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
    async_dispatcher_send(hass, f"{DOMAIN}_force_entity_cleanup", None)
    LOGGER.info("Force cleanup signal sent to all entities")

async def async_force_remove_stale(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Handle force removal of stale entities."""
    remove_all = call.data.get("remove_all", False)
    
    # Get the entity registry
    entity_registry = async_get_entity_registry(hass)
    entities_removed = 0
    
    # Find entities from this integration
    for entity_id, entity in list(entity_registry.entities.items()):
        # Check if entity belongs to this integration
        if entity.platform == DOMAIN:
            if remove_all or not entity.disabled_by:
                # Remove entity from registry
                LOGGER.info("Removing entity %s from registry", entity_id)
                entity_registry.async_remove(entity_id)
                entities_removed += 1
    
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