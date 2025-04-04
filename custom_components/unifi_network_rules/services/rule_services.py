"""Rule services for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

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

def find_entity_by_unique_id(hass: HomeAssistant, unique_id: str) -> str | None:
    """Find entity ID by its unique ID.
    
    Args:
        hass: Home Assistant instance
        unique_id: The unique ID to look for
        
    Returns:
        The entity ID if found, None otherwise
    """
    entity_registry = async_get_entity_registry(hass)
    entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, unique_id)
    if entity_id:
        return entity_id
    return None

async def async_toggle_rule(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Handle toggling a rule by ID."""
    rule_id = call.data[CONF_RULE_ID]
    enabled = call.data["enabled"]
    rule_type = call.data.get(CONF_RULE_TYPE)
    
    # Check if we have any coordinators
    if not coordinators:
        LOGGER.error("No UniFi Network Rules coordinators available")
        return {"error": "No coordinators available"}
    
    # Get the rule based on its ID and type (from any coordinator)
    if not rule_id:
        raise HomeAssistantError("Rule ID is required")
    
    # The rule_id might be prefixed with our custom prefix (e.g., unr_route_abc123)
    # Extract just the real ID if needed
    if "_" in rule_id:
        parts = rule_id.split("_", 2)
        if len(parts) == 3 and parts[0] == "unr":
            # This appears to be our prefixed ID format
            # parts[1] would be the type hint (route, policy, etc)
            real_id = parts[2]
            LOGGER.debug("Extracted ID %s from prefixed ID %s", real_id, rule_id)
            rule_id = real_id
    
    success = False
    
    # Function to get rule by ID for a specific rule type
    async def get_rule_by_id(api, rule_type, rule_id):
        if rule_type == "firewall_policies":
            policies = await api.get_firewall_policies(include_predefined=True)
            return next((p for p in policies if p.id == rule_id), None)
        elif rule_type == "traffic_rules":
            rules = await api.get_traffic_rules()
            return next((r for r in rules if r.id == rule_id), None)
        elif rule_type == "port_forwards":
            forwards = await api.get_port_forwards()
            return next((f for f in forwards if f.id == rule_id), None)
        elif rule_type == "traffic_routes":
            routes = await api.get_traffic_routes()
            return next((r for r in routes if r.id == rule_id), None)
        elif rule_type == "legacy_firewall_rules":
            rules = await api.get_legacy_firewall_rules()
            return next((r for r in rules if r.id == rule_id), None)
        elif rule_type == "qos_rules":
            rules = await api.get_qos_rules()
            return next((r for r in rules if r.id == rule_id), None)
        elif rule_type == "wlans":
            wlans = await api.get_wlans()
            return next((w for w in wlans if w.id == rule_id), None)
        return None
        
    # Function to toggle rule based on its type
    async def toggle_rule(api, rule_type, rule_obj):
        if rule_type == "firewall_policies":
            return await api.queue_api_operation(api.toggle_firewall_policy, rule_obj)
        elif rule_type == "traffic_rules":
            return await api.queue_api_operation(api.toggle_traffic_rule, rule_obj)
        elif rule_type == "port_forwards":
            return await api.queue_api_operation(api.toggle_port_forward, rule_obj)
        elif rule_type == "traffic_routes":
            return await api.queue_api_operation(api.toggle_traffic_route, rule_obj)
        elif rule_type == "legacy_firewall_rules":
            return await api.queue_api_operation(api.toggle_legacy_firewall_rule, rule_obj)
        elif rule_type == "qos_rules":
            return await api.queue_api_operation(api.toggle_qos_rule, rule_obj)
        elif rule_type == "wlans":
            return await api.queue_api_operation(api.toggle_wlan, rule_obj)
        return False

    for coordinator in coordinators.values():
        api = coordinator.api
        try:
            if rule_type:
                # If rule_type is specified, use it directly
                rule_obj = await get_rule_by_id(api, rule_type, rule_id)
                if rule_obj:
                    if await toggle_rule(api, rule_type, rule_obj):
                        success = True
                        break
            else:
                # If rule_type is not specified, try all types
                for type_name in ["firewall_policies", "traffic_rules", "port_forwards", "traffic_routes", "legacy_firewall_rules", "qos_rules", "wlans"]:
                    try:
                        rule_obj = await get_rule_by_id(api, type_name, rule_id)
                        if rule_obj:
                            if await toggle_rule(api, type_name, rule_obj):
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
    
    return {"status": "success", "rule_id": rule_id, "enabled": enabled}

async def async_delete_rule(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Handle deleting a rule by ID."""
    rule_id = call.data[CONF_RULE_ID]
    rule_type = call.data.get(CONF_RULE_TYPE)
    
    # Check if we have any coordinators
    if not coordinators:
        LOGGER.error("No UniFi Network Rules coordinators available")
        return {"error": "No coordinators available"}
    
    # Get the rule based on its ID and type (from any coordinator)
    if not rule_id:
        raise HomeAssistantError("Rule ID is required")
    
    # The rule_id might be prefixed with our custom prefix (e.g., unr_route_abc123)
    # Extract just the real ID if needed
    if "_" in rule_id:
        parts = rule_id.split("_", 2)
        if len(parts) == 3 and parts[0] == "unr":
            # This appears to be our prefixed ID format
            # parts[1] would be the type hint (route, policy, etc)
            real_id = parts[2]
            LOGGER.debug("Extracted ID %s from prefixed ID %s", real_id, rule_id)
            rule_id = real_id
    
    success = False
    for coordinator in coordinators.values():
        api = coordinator.api
        try:
            # Try to delete rule based on rule_type
            if rule_type:
                if await api.delete_rule(rule_type, rule_id):
                    success = True
                    LOGGER.info("Successfully deleted rule %s of type %s", rule_id, rule_type)
                    break
            else:
                # Try all rule types
                for type_name in ["firewall_policies", "traffic_rules", "port_forwards", "traffic_routes", "legacy_firewall_rules", "qos_rules"]:
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
        
    return {"status": "success", "rule_id": rule_id}

async def async_bulk_update_rules(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Service to enable/disable multiple rules based on name matching."""
    name_filter = call.data[CONF_NAME_FILTER].lower()
    desired_state = call.data[CONF_STATE]
    updated_count = 0
    
    # Check if we have any coordinators
    if not coordinators:
        LOGGER.error("No UniFi Network Rules coordinators available")
        return {"error": "No coordinators available", "updated_count": 0}

    # Function to toggle rule based on its type and current state
    async def toggle_rule_if_needed(api, rule_type, rule_obj, desired_state):
        # Check if the rule is already in the desired state
        current_state = getattr(rule_obj, "enabled", None)
        if current_state is None and isinstance(rule_obj, dict):
            current_state = rule_obj.get("enabled", False)
            
        # Only toggle if the current state is different from desired state
        if current_state != desired_state:
            if rule_type == "firewall_policies":
                return await api.queue_api_operation(api.toggle_firewall_policy, rule_obj)
            elif rule_type == "traffic_rules":
                return await api.queue_api_operation(api.toggle_traffic_rule, rule_obj)
            elif rule_type == "port_forwards":
                return await api.queue_api_operation(api.toggle_port_forward, rule_obj)
            elif rule_type == "traffic_routes":
                return await api.queue_api_operation(api.toggle_traffic_route, rule_obj)
            elif rule_type == "legacy_firewall_rules":
                return await api.queue_api_operation(api.toggle_legacy_firewall_rule, rule_obj)
            elif rule_type == "qos_rules":
                return await api.queue_api_operation(api.toggle_qos_rule, rule_obj)
            elif rule_type == "wlans":
                return await api.queue_api_operation(api.toggle_wlan, rule_obj)
        return True  # Already in desired state

    entity_registry = async_get_entity_registry(hass)
    
    # First check entity registry for entities with matching names
    for entity_id, entity in entity_registry.entities.items():
        if entity.platform == DOMAIN and entity.domain == "switch":
            # Get the entity state to access its name
            state = hass.states.get(entity_id)
            if state and state.name and name_filter in state.name.lower():
                LOGGER.debug("Found matching entity: %s (%s)", state.name, entity_id)
                # Find the corresponding rule in coordinators data
                for coordinator in coordinators.values():
                    api = coordinator.api
                    if not api or not coordinator.data:
                        continue
                    
                    # Get unique_id without domain prefix (entity registry format)
                    unique_id = entity.unique_id
                    
                    # Look through rule collections to find matching unique_id
                    for rule_type, rules in coordinator.data.items():
                        if not rules:
                            continue
                            
                        for rule in rules:
                            # Check if this rule's ID matches our entity's unique_id
                            from ..helpers.rule import get_rule_id
                            rule_unique_id = get_rule_id(rule)
                            
                            if rule_unique_id == unique_id:
                                try:
                                    if await toggle_rule_if_needed(api, rule_type, rule, desired_state):
                                        updated_count += 1
                                        LOGGER.info(
                                            "Updated rule %s (%s) to state: %s via entity %s",
                                            state.name, rule_type, desired_state, entity_id
                                        )
                                except Exception as err:
                                    LOGGER.error(
                                        "Failed to update entity %s rule: %s", 
                                        entity_id, err
                                    )

    # Also ensure we check directly in coordinator data for rules that might not have entities
    for coordinator in coordinators.values():
        api = coordinator.api
        if not api or not coordinator.data:
            continue

        # Find and update matching rules by name
        for rule_type, rules in coordinator.data.items():
            if not rules:
                continue
                
            for rule in rules:
                # Get rule name consistently whether it's an API object or dict
                rule_name = ""
                if hasattr(rule, "name"):
                    rule_name = rule.name
                elif isinstance(rule, dict) and "name" in rule:
                    rule_name = rule["name"]
                    
                if rule_name and name_filter in rule_name.lower():
                    # Check if we already processed this via entity lookup
                    from ..helpers.rule import get_rule_id
                    rule_unique_id = get_rule_id(rule)
                    entity_id = find_entity_by_unique_id(hass, rule_unique_id)
                    
                    # Skip if we already processed this via an entity
                    if entity_id and hass.states.get(entity_id) is not None:
                        continue
                        
                    try:
                        if await toggle_rule_if_needed(api, rule_type, rule, desired_state):
                            updated_count += 1
                            LOGGER.info(
                                "Updated rule %s (%s) to state: %s directly from API data",
                                rule_name, rule_type, desired_state
                            )
                    except Exception as err:
                        LOGGER.error(
                            "Failed to update rule %s: %s", 
                            rule_name, err
                        )

        # Refresh after updates
        await coordinator.async_refresh()
        
    if updated_count == 0:
        LOGGER.warning("No rules found matching filter: %s", name_filter)
    else:
        LOGGER.info("Updated %s rules matching filter: %s", updated_count, name_filter)
    
    return {"status": "success", "updated_count": updated_count, "filter": name_filter}

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