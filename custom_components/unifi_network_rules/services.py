"""Services for UniFi Network Rules integration."""
from __future__ import annotations

import logging
import json
import re
import os
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.const import CONF_NAME, CONF_TYPE
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, LOGGER
from .udm_api import UDMAPI
from .coordinator import UnifiRuleUpdateCoordinator

# Service names
SERVICE_REFRESH = "refresh"
SERVICE_BACKUP = "backup_rules"
SERVICE_RESTORE = "restore_rules"
SERVICE_BULK_UPDATE = "bulk_update_rules"
SERVICE_DELETE_RULE = "delete_rule"
SERVICE_APPLY_TEMPLATE = "apply_template"
SERVICE_SAVE_TEMPLATE = "save_template"
SERVICE_FORCE_CLEANUP = "force_cleanup"
SERVICE_RESET_RATE_LIMIT = "reset_rate_limit"
SERVICE_WEBSOCKET_DIAGNOSTICS = "websocket_diagnostics"

# Schema fields
CONF_FILENAME = "filename"
CONF_RULE_IDS = "rule_ids"
CONF_NAME_FILTER = "name_filter"
CONF_RULE_TYPES = "rule_types"
CONF_TEMPLATE_ID = "template_id"
CONF_TEMPLATE = "template"
CONF_VARIABLES = "variables"
CONF_STATE = "state"
CONF_RULE_ID = "rule_id"
CONF_RULE_TYPE = "rule_type"

# Signal for entity cleanup
SIGNAL_ENTITIES_CLEANUP = f"{DOMAIN}_cleanup"

# Schema for toggle_rule service
TOGGLE_RULE_SCHEMA = vol.Schema(
    {
        vol.Required("rule_id"): cv.string,
        vol.Required("enabled"): cv.boolean,
        vol.Optional("rule_type"): cv.string,
    }
)

# Schema for refresh service
REFRESH_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
    }
)

async def async_refresh_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to refresh UniFi data."""
    for entry_data in hass.data[DOMAIN].values():
        coordinator = entry_data.get("coordinator")
        if coordinator:
            await coordinator.async_refresh()

async def async_backup_rules_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to backup rules to a file."""
    filename = call.data[CONF_FILENAME]
    backup_data = {}

    for entry_id, entry_data in hass.data[DOMAIN].items():
        coordinator = entry_data.get("coordinator")
        if coordinator and coordinator.data:
            entry_backup = {}
            for rule_type, rules in coordinator.data.items():
                if not rules:  # Skip empty data
                    continue
                    
                # Convert API objects to serializable dicts
                serialized_rules = []
                for rule in rules:
                    if hasattr(rule, 'raw'):
                        serialized_rules.append(rule.raw)
                    elif isinstance(rule, dict):
                        serialized_rules.append(rule)
                    else:
                        # Fallback if neither raw nor dict
                        LOGGER.warning("Unexpected rule type for %s: %s", rule_type, type(rule))
                        continue
                
                if serialized_rules:
                    entry_backup[rule_type] = serialized_rules
            
            if entry_backup:  # Only include non-empty backups
                backup_data[entry_id] = entry_backup

    if not backup_data:
        raise HomeAssistantError("No data available to backup")

    try:
        backup_path = hass.config.path(filename)
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
        LOGGER.info("Rules backup created at %s", backup_path)
    except Exception as e:
        raise HomeAssistantError(f"Failed to create backup: {str(e)}")

async def async_restore_rules_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to restore rules from a file."""
    filename = call.data[CONF_FILENAME]
    rule_ids = call.data.get(CONF_RULE_IDS, [])
    name_filter = call.data.get(CONF_NAME_FILTER, "").lower()
    rule_types = call.data.get(CONF_RULE_TYPES, [])

    backup_path = hass.config.path(filename)
    if not os.path.exists(backup_path):
        raise HomeAssistantError(f"Backup file not found: {backup_path}")

    try:
        with open(backup_path, 'r') as f:
            backup_data = json.load(f)
    except Exception as e:
        raise HomeAssistantError(f"Failed to read backup file: {str(e)}")

    for entry_id, entry_data in hass.data[DOMAIN].items():
        if entry_id not in backup_data:
            continue

        api = entry_data.get("api")
        if not api:
            continue

        backup_entry = backup_data[entry_id]

        # Helper to check if a rule should be restored
        def should_restore(rule: dict, rule_type: str) -> bool:
            if rule_ids and rule["_id"] not in rule_ids:
                return False
            if name_filter and name_filter not in rule.get("name", "").lower():
                return False
            if rule_types and rule_type not in rule_types:
                return False
            return True

        # Restore firewall policies
        if "firewall_policies" in backup_entry and api.capabilities.zone_based_firewall:
            for policy in backup_entry["firewall_policies"]:
                if should_restore(policy, "policy"):
                    await api.update_firewall_policy(policy["_id"], policy)

        # Restore traffic routes
        if "traffic_routes" in backup_entry and api.capabilities.traffic_routes:
            for route in backup_entry["traffic_routes"]:
                if should_restore(route, "route"):
                    await api.update_traffic_route(route["_id"], route)

        # Restore port forward rules
        if "port_forward_rules" in backup_entry:
            for rule in backup_entry["port_forward_rules"]:
                if should_restore(rule, "port_forward"):
                    await api.update_port_forward(rule["_id"], rule)

        # Restore legacy firewall rules
        if "legacy_firewall_rules" in backup_entry and api.capabilities.legacy_firewall:
            for rule in backup_entry["legacy_firewall_rules"]:
                if should_restore(rule, "legacy_firewall"):
                    await api.update_legacy_firewall_rule(rule["_id"], rule)

        # Restore legacy traffic rules
        if "legacy_traffic_rules" in backup_entry and api.capabilities.legacy_traffic:
            for rule in backup_entry["legacy_traffic_rules"]:
                if should_restore(rule, "legacy_traffic"):
                    await api.update_legacy_traffic_rule(rule["_id"], rule)

        # Refresh coordinator after restore
        coordinator = entry_data.get("coordinator")
        if coordinator:
            await coordinator.async_refresh()

async def async_bulk_update_rules_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to enable/disable multiple rules based on name matching."""
    name_filter = call.data[CONF_NAME_FILTER].lower()
    desired_state = call.data[CONF_STATE]

    for entry_data in hass.data[DOMAIN].values():
        coordinator = entry_data.get("coordinator")
        api = entry_data.get("api")
        if not coordinator or not api or not coordinator.data:
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

async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for UniFi Network Rules."""
    
    # Store for entry_id -> coordinator mappings
    coordinators: Dict[str, UnifiRuleUpdateCoordinator] = {}

    # Register a coordinator for a config entry
    def register_coordinator(entry_id: str, coordinator: UnifiRuleUpdateCoordinator) -> None:
        """Register a coordinator for a config entry."""
        coordinators[entry_id] = coordinator
        LOGGER.debug("Registered coordinator for entry %s", entry_id)

    # Unregister a coordinator for a config entry
    def unregister_coordinator(entry_id: str) -> None:
        """Unregister a coordinator for a config entry."""
        if entry_id in coordinators:
            del coordinators[entry_id]
            LOGGER.debug("Unregistered coordinator for entry %s", entry_id)

    # Set up the toggle_rule service
    async def handle_toggle_rule(call: ServiceCall) -> None:
        """Handle the toggle_rule service call."""
        rule_id = call.data["rule_id"]
        enabled = call.data["enabled"]
        rule_type = call.data.get("rule_type")

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

    # Set up the refresh service
    async def handle_refresh(call: ServiceCall) -> None:
        """Handle the refresh service call."""
        entry_id = call.data.get("entry_id")
        
        if entry_id:
            # Refresh specific coordinator
            if entry_id in coordinators:
                LOGGER.info("Manually refreshing data for entry %s", entry_id)
                await coordinators[entry_id].async_refresh()
            else:
                raise HomeAssistantError(f"No coordinator found for entry_id {entry_id}")
        else:
            # Refresh all coordinators
            LOGGER.info("Manually refreshing data for all coordinators")
            for entry_id, coordinator in coordinators.items():
                LOGGER.debug("Refreshing coordinator for entry %s", entry_id)
                await coordinator.async_refresh()

    # Register services
    hass.services.async_register(
        DOMAIN, "toggle_rule", handle_toggle_rule, schema=TOGGLE_RULE_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, "refresh_data", handle_refresh, schema=REFRESH_DATA_SCHEMA
    )

    # Store the register/unregister functions in the services dictionary
    if "services" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["services"] = {}
    
    hass.data[DOMAIN]["services"]["register_coordinator"] = register_coordinator
    hass.data[DOMAIN]["services"]["unregister_coordinator"] = unregister_coordinator
    
    LOGGER.debug("Services initialized and registration functions stored in services dictionary")

    return True

async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload UniFi Network Rules services."""
    for service in ["toggle_rule", "refresh_data"]:
        hass.services.async_remove(DOMAIN, service)

async def async_register_services(hass):
    """Register all services for UniFi Network Rules."""
    async def handle_force_cleanup(call):
        """Handle force cleanup service call."""
        # Clean up all entities
        async_dispatcher_send(hass, f"{DOMAIN}_force_entity_cleanup", None)
        LOGGER.info("Force cleanup signal sent to all entities")

    async def handle_reset_rate_limit(call):
        """Handle reset rate limit service call."""
        # Reset rate limit for all APIs
        for entry_data in hass.data[DOMAIN].values():
            if "api" in entry_data:
                api = entry_data["api"]
                if hasattr(api, "reset_rate_limit"):
                    try:
                        success = await api.reset_rate_limit()
                        if success:
                            LOGGER.info("Rate limit reset successful")
                        else:
                            LOGGER.warning("Rate limit reset failed")
                    except Exception as e:
                        LOGGER.error("Error resetting rate limit: %s", e)

    async def handle_websocket_diagnostics(call):
        """Run diagnostics on WebSocket connections and try to repair if needed."""
        results = {}
        
        # Check all entries and their WebSocket connections
        for entry_id, entry_data in hass.data[DOMAIN].items():
            entry_result = {
                "status": "unknown",
                "details": {},
                "actions_taken": []
            }
            
            # Check if API exists
            if "api" not in entry_data:
                entry_result["status"] = "error"
                entry_result["details"]["error"] = "No API found for this entry"
                results[entry_id] = entry_result
                continue
                
            api = entry_data["api"]
            websocket = entry_data.get("websocket")
            
            # Collect API information
            entry_result["details"]["initialized"] = api.initialized if hasattr(api, "initialized") else False
            entry_result["details"]["connection_url"] = api.host if hasattr(api, "host") else "unknown"
            
            # Check controller information
            if hasattr(api, "controller") and api.controller:
                entry_result["details"]["controller_available"] = True
                entry_result["details"]["is_unifi_os"] = getattr(api.controller, "is_unifi_os", False)
                
                # Check controller WebSocket state
                if hasattr(api.controller, "websocket"):
                    ws = api.controller.websocket
                    entry_result["details"]["controller_websocket"] = {
                        "state": getattr(ws, "state", "unknown"),
                        "url": getattr(ws, "url", "unknown"),
                    }
            else:
                entry_result["details"]["controller_available"] = False
            
            # Check custom WebSocket state
            if hasattr(api, "_custom_websocket") and api._custom_websocket:
                try:
                    custom_ws = api._custom_websocket
                    entry_result["details"]["custom_websocket"] = {
                        "connected": custom_ws.is_connected(),
                        "url": custom_ws.url,
                    }
                    
                    # Get detailed status if available
                    if hasattr(custom_ws, "get_connection_status"):
                        entry_result["details"]["custom_websocket_status"] = custom_ws.get_connection_status()
                except Exception as err:
                    entry_result["details"]["custom_websocket_error"] = str(err)
            else:
                entry_result["details"]["custom_websocket"] = None
            
            # Check if WebSocket handler exists
            if websocket:
                entry_result["details"]["websocket_handler_exists"] = True
            else:
                entry_result["details"]["websocket_handler_exists"] = False
            
            # Check coordinator
            if "coordinator" in entry_data:
                coordinator = entry_data["coordinator"]
                entry_result["details"]["coordinator_exists"] = True
                entry_result["details"]["coordinator_last_update_success"] = coordinator.last_update_success
                
                # Check how many data sources have data
                if hasattr(coordinator, "data") and coordinator.data:
                    data_sources = {k: len(v) for k, v in coordinator.data.items() if v}
                    entry_result["details"]["data_sources"] = data_sources
            
            # Attempt repairs if problems detected
            try:
                # If WebSocket isn't connected, try to restart it
                if not entry_result["details"].get("custom_websocket", {}).get("connected", False) and \
                   not entry_result["details"].get("controller_websocket", {}).get("state") == "running":
                    
                    LOGGER.info("Attempting to restart WebSocket for entry %s", entry_id)
                    entry_result["actions_taken"].append("Restarting WebSocket connection")
                    
                    # Stop current WebSocket if any
                    if websocket:
                        await websocket.stop_and_wait()
                    
                    # Also stop API WebSocket
                    if hasattr(api, "stop_websocket"):
                        await api.stop_websocket()
                    
                    # Clear cache to ensure fresh data
                    if hasattr(api, "clear_cache"):
                        await api.clear_cache()
                        entry_result["actions_taken"].append("Cleared API cache")
                    
                    # Try to refresh session
                    if hasattr(api, "refresh_session"):
                        success = await api.refresh_session()
                        if success:
                            entry_result["actions_taken"].append("Refreshed API session")
                    
                    # Start WebSocket
                    if websocket:
                        websocket.start()
                        entry_result["actions_taken"].append("Started WebSocket handler")
                    
                    # Refresh data
                    if "coordinator" in entry_data:
                        await entry_data["coordinator"].async_refresh()
                        entry_result["actions_taken"].append("Refreshed coordinator data")
                    
                    # Update status based on actions taken
                    entry_result["status"] = "repaired"
                else:
                    # If everything seems fine
                    entry_result["status"] = "healthy"
                    
                    # Still refresh data to ensure it's current
                    if "coordinator" in entry_data:
                        await entry_data["coordinator"].async_refresh()
                        entry_result["actions_taken"].append("Refreshed coordinator data")
            except Exception as repair_err:
                entry_result["status"] = "repair_failed"
                entry_result["details"]["repair_error"] = str(repair_err)
            
            # Store results for this entry
            results[entry_id] = entry_result
        
        # Log summary of results
        summary = {entry_id: result["status"] for entry_id, result in results.items()}
        LOGGER.info("WebSocket diagnostics summary: %s", summary)
        
        # Return to service caller
        return results

    # Register all the services
    hass.services.async_register(
        DOMAIN, SERVICE_FORCE_CLEANUP, handle_force_cleanup, schema=vol.Schema({})
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_RESET_RATE_LIMIT, handle_reset_rate_limit, schema=vol.Schema({})
    )
    
    # Register the WebSocket diagnostics service
    hass.services.async_register(
        DOMAIN, SERVICE_WEBSOCKET_DIAGNOSTICS, handle_websocket_diagnostics, schema=vol.Schema({})
    )
