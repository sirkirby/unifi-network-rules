"""Rule services for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError

from ..const import DOMAIN, LOGGER
from .constants import (
    SERVICE_TOGGLE_RULE,
    SERVICE_DELETE_RULE,
    SERVICE_BULK_UPDATE,
    CONF_RULE_ID,
    CONF_RULE_TYPE,
    CONF_NAME_FILTER,
    CONF_STATE,
)

# Schema for toggle_rule service
TOGGLE_RULE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_RULE_ID): cv.string,
        vol.Required("enabled"): cv.boolean,
        vol.Optional(CONF_RULE_TYPE): cv.string,
    }
)

# Schema for bulk_update_rules service
BULK_UPDATE_RULES_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME_FILTER): cv.string,
        vol.Required(CONF_STATE): cv.boolean,
    }
)

# Schema for delete_rule service
DELETE_RULE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_RULE_ID): cv.string,
        vol.Optional(CONF_RULE_TYPE): cv.string,
    }
)

async def async_toggle_rule(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Handle the toggle_rule service call."""
    rule_id = call.data[CONF_RULE_ID]
    enabled = call.data["enabled"]
    rule_type = call.data.get(CONF_RULE_TYPE)

    LOGGER.info("Toggling rule %s to %s", rule_id, enabled)

    # Find the correct coordinator/API
    success = False
    for coordinator in coordinators.values():
        api = coordinator.api
        try:
            if rule_type:
                # If rule_type is specified, use it directly
                if await api.update_rule_state(rule_type, rule_id, enabled):
                    success = True
                    break
            else:
                # If rule_type is not specified, try all types
                for type_name in ["firewall_policies", "traffic_rules", "port_forwards", "traffic_routes", "legacy_firewall_rules"]:
                    try:
                        if await api.update_rule_state(type_name, rule_id, enabled):
                            success = True
                            LOGGER.info("Successfully toggled rule using type: %s", type_name)
                            break
                    except Exception:
                        # Continue trying other types
                        pass
                if success:
                    break
        except Exception as err:
            LOGGER.error("Error toggling rule with coordinator: %s", err)

    if not success:
        raise HomeAssistantError(f"Failed to toggle rule {rule_id}")
    
    # Force a refresh on all coordinators
    for coordinator in coordinators.values():
        await coordinator.async_refresh()

async def async_delete_rule(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Handle deleting a rule by ID."""
    rule_id = call.data.get(CONF_RULE_ID)
    rule_type = call.data.get(CONF_RULE_TYPE)
    
    if not rule_id:
        raise HomeAssistantError("Rule ID is required")
    
    success = False
    for entry_data in hass.data[DOMAIN].values():
        if "api" not in entry_data:
            continue
            
        api = entry_data["api"]
        try:
            # Try to delete rule based on rule_type
            if rule_type:
                if await api.delete_rule(rule_type, rule_id):
                    success = True
                    LOGGER.info("Successfully deleted rule %s of type %s", rule_id, rule_type)
                    break
            else:
                # Try all rule types
                for type_name in ["firewall_policies", "traffic_rules", "port_forwards", "traffic_routes", "legacy_firewall_rules"]:
                    try:
                        if await api.delete_rule(type_name, rule_id):
                            success = True
                            LOGGER.info("Successfully deleted rule %s using type: %s", rule_id, type_name)
                            break
                    except Exception:
                        # Continue trying other types
                        pass
                if success:
                    break
        except Exception as err:
            LOGGER.error("Error deleting rule with API: %s", err)
    
    if not success:
        raise HomeAssistantError(f"Failed to delete rule {rule_id}")
        
    # Refresh all coordinators after deletion
    for coordinator in coordinators.values():
        await coordinator.async_refresh()

async def async_bulk_update_rules(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Service to enable/disable multiple rules based on name matching."""
    name_filter = call.data[CONF_NAME_FILTER].lower()
    desired_state = call.data[CONF_STATE]

    for coordinator in coordinators.values():
        api = coordinator.api
        if not api or not coordinator.data:
            continue

        # Find and update matching rules
        for rule_type, rules in coordinator.data.items():
            rule_list = rules if isinstance(rules, list) else rules.get("data", [])
            for rule in rule_list:
                if name_filter in rule.get("name", "").lower():
                    rule_copy = rule.copy()
                    rule_copy["enabled"] = desired_state
                    await api.update_rule_state(rule_type, rule["_id"], desired_state)

        # Refresh after updates
        await coordinator.async_refresh()

async def async_setup_rule_services(hass: HomeAssistant, coordinators: Dict) -> None:
    """Set up rule-related services."""
    
    # Handle the toggle_rule service
    async def handle_toggle_rule(call: ServiceCall) -> None:
        await async_toggle_rule(hass, coordinators, call)
        
    # Handle the delete_rule service
    async def handle_delete_rule(call: ServiceCall) -> None:
        await async_delete_rule(hass, coordinators, call)
        
    # Handle the bulk update rules service
    async def handle_bulk_update_rules(call: ServiceCall) -> None:
        await async_bulk_update_rules(hass, coordinators, call)
    
    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_TOGGLE_RULE, handle_toggle_rule, schema=TOGGLE_RULE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_RULE, handle_delete_rule, schema=DELETE_RULE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_BULK_UPDATE, handle_bulk_update_rules, schema=BULK_UPDATE_RULES_SCHEMA
    ) 