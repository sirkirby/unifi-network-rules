"""Template services for UniFi Network Rules integration."""
from __future__ import annotations

from typing import Dict

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError

from ..const import DOMAIN, LOGGER
from .constants import (
    SERVICE_APPLY_TEMPLATE, 
    SERVICE_SAVE_TEMPLATE,
    CONF_TEMPLATE_ID,
    CONF_VARIABLES,
    CONF_RULE_ID,
    CONF_RULE_TYPE,
)
from ..helpers.id_parser import parse_rule_id

# Schema for apply_template service
APPLY_TEMPLATE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TEMPLATE_ID): cv.string,
        vol.Optional(CONF_VARIABLES): dict,
    }
)

# Schema for save_template service
SAVE_TEMPLATE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_RULE_ID): cv.string,
        vol.Required(CONF_TEMPLATE_ID): cv.string,
        vol.Optional(CONF_RULE_TYPE): cv.string,
    }
)

async def async_apply_template(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Handle applying a rule template."""
    template_id = call.data.get(CONF_TEMPLATE_ID)
    _variables = call.data.get(CONF_VARIABLES, {})  # Will be used when template feature is implemented
    
    if not template_id:
        raise HomeAssistantError("Template ID is required")
        
    # TODO: Implement template application
    LOGGER.warning("The apply_template service is not fully implemented yet.")
    
    # Refresh all coordinators after applying template
    for coordinator in coordinators.values():
        await coordinator.async_refresh()

async def async_save_template(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Handle saving a rule as a template."""
    rule_id = call.data.get(CONF_RULE_ID)
    rule_type = call.data.get(CONF_RULE_TYPE)
    template_id = call.data.get(CONF_TEMPLATE_ID)
    
    if not rule_id or not template_id:
        raise HomeAssistantError("Rule ID and Template ID are required")
    
    # Parse and normalize the rule ID using helper
    original_rule_id = rule_id
    rule_id, detected_rule_type = parse_rule_id(rule_id, rule_type)
    
    # Use detected rule type if none was provided
    if not rule_type and detected_rule_type:
        rule_type = detected_rule_type
    
    LOGGER.debug("Save template service: parsed rule_id %s -> %s (type: %s)", 
                original_rule_id, rule_id, rule_type)
        
    # TODO: Implement template saving
    LOGGER.warning("The save_template service is not fully implemented yet.")

async def async_setup_template_services(hass: HomeAssistant, coordinators: Dict) -> None:
    """Set up template-related services."""
    
    # Handle the apply template service  
    async def handle_apply_template(call: ServiceCall) -> None:
        await async_apply_template(hass, coordinators, call)
        
    # Handle the save template service
    async def handle_save_template(call: ServiceCall) -> None:
        await async_save_template(hass, coordinators, call)
    
    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_APPLY_TEMPLATE, handle_apply_template, schema=APPLY_TEMPLATE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_SAVE_TEMPLATE, handle_save_template, schema=SAVE_TEMPLATE_SCHEMA
    ) 