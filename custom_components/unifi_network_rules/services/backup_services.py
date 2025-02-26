"""Backup services for UniFi Network Rules integration."""
from __future__ import annotations

import json
import os
import logging
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError

from ..const import DOMAIN, LOGGER
from .constants import (
    SERVICE_BACKUP, 
    SERVICE_RESTORE,
    CONF_FILENAME,
    CONF_RULE_IDS,
    CONF_NAME_FILTER,
    CONF_RULE_TYPES,
)

# Schema for backup_rules service
BACKUP_RULES_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_FILENAME): cv.string,
    }
)

# Schema for restore_rules service
RESTORE_RULES_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_FILENAME): cv.string,
        vol.Optional(CONF_RULE_IDS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_NAME_FILTER): cv.string,
        vol.Optional(CONF_RULE_TYPES): vol.All(cv.ensure_list, [cv.string]),
    }
)

async def async_backup_rules_service(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Service to backup rules to a file."""
    filename = call.data[CONF_FILENAME]
    backup_data = {}

    for entry_id, coordinator in coordinators.items():
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

async def async_restore_rules_service(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
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

async def async_setup_backup_services(hass: HomeAssistant, coordinators: Dict) -> None:
    """Set up backup and restore services."""
    
    # Handle the backup rules service
    async def handle_backup_rules(call: ServiceCall) -> None:
        await async_backup_rules_service(hass, coordinators, call)
        
    # Handle the restore rules service
    async def handle_restore_rules(call: ServiceCall) -> None:
        await async_restore_rules_service(hass, coordinators, call)
    
    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_BACKUP, handle_backup_rules, schema=BACKUP_RULES_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_RESTORE, handle_restore_rules, schema=RESTORE_RULES_SCHEMA
    ) 