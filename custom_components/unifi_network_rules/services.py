"""Services for UniFi Network Rules integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol
import json
import os
import asyncio

from homeassistant.core import HomeAssistant, ServiceCall, HomeAssistantError, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, LOGGER

# Service names
SERVICE_REFRESH = "refresh"
SERVICE_BACKUP = "backup_rules"
SERVICE_RESTORE = "restore_rules"
SERVICE_BULK_UPDATE = "bulk_update_rules"
SERVICE_DELETE_RULE = "delete_rule"
SERVICE_APPLY_TEMPLATE = "apply_template"
SERVICE_SAVE_TEMPLATE = "save_template"

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
            backup_data[entry_id] = {
                rule_type: rules
                for rule_type, rules in coordinator.data.items()
                if rules  # Only include non-empty data
            }

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
                    await api.update_port_forward_rule(rule["_id"], rule)

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
    """Set up services."""
    
    # Refresh service
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        async_refresh_service,
        schema=vol.Schema({})
    )
    
    # Backup service
    hass.services.async_register(
        DOMAIN,
        SERVICE_BACKUP,
        async_backup_rules_service,
        schema=vol.Schema({
            vol.Required(CONF_FILENAME): cv.string
        })
    )
    
    # Restore service
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESTORE,
        async_restore_rules_service,
        schema=vol.Schema({
            vol.Required(CONF_FILENAME): cv.string,
            vol.Optional(CONF_RULE_IDS): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional(CONF_NAME_FILTER): cv.string,
            vol.Optional(CONF_RULE_TYPES): vol.All(cv.ensure_list, 
                [vol.In(["policy", "route", "firewall", "traffic", "port_forward"])])
        })
    )
    
    # Bulk update service
    hass.services.async_register(
        DOMAIN,
        SERVICE_BULK_UPDATE,
        async_bulk_update_rules_service,
        schema=vol.Schema({
            vol.Required(CONF_NAME_FILTER): cv.string,
            vol.Required(CONF_STATE): cv.boolean
        })
    )
