"""Backup services for UniFi Network Rules integration."""
from __future__ import annotations

import json
import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError

from ..const import DOMAIN, LOGGER, BACKUP_FILE_PREFIX, BACKUP_LOCATION
from .constants import (
    SERVICE_BACKUP, 
    SERVICE_RESTORE,
    CONF_FILENAME,
    CONF_RULE_IDS,
    CONF_NAME_FILTER,
    CONF_RULE_TYPES,
)
from ..models.firewall_rule import FirewallRule  # Import FirewallRule

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
    """Back up rules to a file."""
    entry_id = call.data.get("config_entry_id")
    filename = call.data.get("filename")
    
    # Get coordinator and API for the specified entry
    if entry_id not in coordinators:
        raise ValueError(f"Config entry {entry_id} not found")
    
    coordinator = coordinators[entry_id]
    api = coordinator.api
    
    # Generate backup filename
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hostname = api.host.replace(".", "_")
        filename = f"{BACKUP_FILE_PREFIX}_{hostname}_{timestamp}.json"
    elif not filename.endswith(".json"):
        filename = f"{filename}.json"
    
    # Get rules data
    backup_data = {
        "hostname": api.host,
        "timestamp": datetime.now().isoformat(),
        "rules": {}
    }
    
    # Check what types of rules are available
    available_rules = []
    
    # Add available rule types to the backup
    if coordinator.data:
        # Convert each rule to a serializable format
        for rule_type, rules in coordinator.data.items():
            if rules:
                # Convert each rule to a serializable dictionary
                serialized_rules = []
                for rule in rules:
                    # Simplified logic for serializing all API object types
                    # All our API objects now have a consistent .raw property
                    if hasattr(rule, "raw"):
                        serialized_rules.append(rule.raw)
                    # Handle plain dictionaries
                    elif isinstance(rule, dict):
                        serialized_rules.append(rule)
                    # Handle other objects (unlikely with our updates)
                    else:
                        LOGGER.warning("Encountered non-standard rule object type: %s", type(rule).__name__)
                        # Try to convert to dict using __dict__
                        try:
                            rule_dict = rule.__dict__
                            serialized_rules.append(rule_dict)
                        except AttributeError:
                            # Last resort: try to make a dict from properties
                            rule_dict = {}
                            for attr in dir(rule):
                                if not attr.startswith("_") and not callable(getattr(rule, attr)):
                                    rule_dict[attr] = getattr(rule, attr)
                            serialized_rules.append(rule_dict)
                
                backup_data["rules"][rule_type] = serialized_rules
                available_rules.append(rule_type)
    
    # Save backup file
    backup_path = hass.config.path(BACKUP_LOCATION, filename)
    
    with open(backup_path, "w") as f:
        json.dump(backup_data, f, indent=2)
    
    return {"filename": filename, "path": backup_path, "rule_types": available_rules}

async def async_restore_rules_service(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Restore rules from a file."""
    entry_id = call.data.get("config_entry_id")
    filename = call.data.get("filename")
    
    # Validate parameters
    if not filename:
        raise ValueError("Filename is required")
    
    # Get coordinator and API for the specified entry
    if entry_id not in coordinators:
        raise ValueError(f"Config entry {entry_id} not found")
    
    coordinator = coordinators[entry_id]
    api = coordinator.api
    
    # Make sure filename has .json extension
    if not filename.endswith(".json"):
        filename = f"{filename}.json"
    
    # Load backup file
    backup_path = hass.config.path(BACKUP_LOCATION, filename)
    
    try:
        with open(backup_path, "r") as f:
            backup_data = json.load(f)
    except FileNotFoundError:
        raise ValueError(f"Backup file {filename} not found")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in backup file {filename}")
    
    # Get rules from backup
    if "rules" not in backup_data:
        raise ValueError("Invalid backup file: 'rules' section not found")
    
    backup_entry = backup_data["rules"]

    # Define a function to determine if a rule should be restored
    def should_restore(rule: dict, rule_type: str) -> bool:
        """Determine if a rule should be restored."""
        # Check if rule has required fields
        if "_id" not in rule:
            return False
        
        # Allow restore based on rule type
        return True

    # Restore firewall policies
    if "firewall_policies" in backup_entry and hasattr(api, "update_firewall_policy"):
        for rule in backup_entry["firewall_policies"]:
            if should_restore(rule, "firewall_policy"):
                await api.update_firewall_policy(rule["_id"], rule)

    # Restore traffic rules
    if "traffic_rules" in backup_entry and hasattr(api, "update_traffic_rule"):
        for rule in backup_entry["traffic_rules"]:
            if should_restore(rule, "traffic_rule"):
                await api.update_traffic_rule(rule["_id"], rule)

    # Restore port forwards
    if "port_forwards" in backup_entry and hasattr(api, "update_port_forward"):
        for rule in backup_entry["port_forwards"]:
            if should_restore(rule, "port_forward"):
                await api.update_port_forward(rule["_id"], rule)

    # Restore legacy firewall rules
    if "legacy_firewall_rules" in backup_entry and api.capabilities.legacy_firewall:
        for rule in backup_entry["legacy_firewall_rules"]:
            if should_restore(rule, "legacy_firewall"):
                # Rule is already in dictionary format from the backup
                # No need to convert FirewallRule to dictionary here
                await api.update_legacy_firewall_rule(rule["_id"], rule)

    # Restore legacy traffic rules
    if "legacy_traffic_rules" in backup_entry and api.capabilities.legacy_traffic:
        for rule in backup_entry["legacy_traffic_rules"]:
            if should_restore(rule, "legacy_traffic"):
                await api.update_legacy_traffic_rule(rule["_id"], rule)

    # Restore traffic routes
    if "traffic_routes" in backup_entry and hasattr(api, "update_traffic_route"):
        for rule in backup_entry["traffic_routes"]:
            if should_restore(rule, "traffic_route"):
                await api.update_traffic_route(rule["_id"], rule)

    # Refresh data after restore
    await coordinator.async_refresh()

    return {"status": "success", "filename": filename}

async def async_setup_backup_services(hass: HomeAssistant, coordinators: Dict) -> None:
    """Set up backup services."""
    
    async def handle_backup_rules(call: ServiceCall) -> None:
        """Handle backup rules service call."""
        return await async_backup_rules_service(hass, coordinators, call)
    
    async def handle_restore_rules(call: ServiceCall) -> None:
        """Handle restore rules service call."""
        return await async_restore_rules_service(hass, coordinators, call)
    
    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_BACKUP,
        handle_backup_rules,
        schema=vol.Schema({
            vol.Required("config_entry_id"): cv.string,
            vol.Optional("filename"): cv.string,
        })
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESTORE,
        handle_restore_rules,
        schema=vol.Schema({
            vol.Required("config_entry_id"): cv.string,
            vol.Required("filename"): cv.string,
        })
    )

    async def _queue_backup_operation(self, target_path: str, rule_types: List[str]) -> bool:
        """Queue a backup operation to prevent rate limiting.
        
        Args:
            target_path: Path to save the backup file
            rule_types: List of rule types to include in the backup
            
        Returns:
            bool: Success of the backup operation
        """
        LOGGER.debug("Queueing backup operation for rule types: %s", rule_types)
        try:
            # Use the general API queue for potentially intensive operations
            future = await self.api.queue_api_operation(
                self._create_backup, target_path, rule_types
            )
            result = await future
            return result
        except Exception as err:
            LOGGER.error("Error in queued backup operation: %s", err)
            return False

    async def _queue_restore_operation(self, source_path: str, rule_types: List[str]) -> bool:
        """Queue a restore operation to prevent rate limiting.
        
        Args:
            source_path: Path to the backup file
            rule_types: List of rule types to restore
            
        Returns:
            bool: Success of the restore operation
        """
        LOGGER.debug("Queueing restore operation for rule types: %s", rule_types)
        try:
            # Use the general API queue for potentially intensive operations
            future = await self.api.queue_api_operation(
                self._restore_from_backup, source_path, rule_types
            )
            result = await future
            return result
        except Exception as err:
            LOGGER.error("Error in queued restore operation: %s", err)
            return False 