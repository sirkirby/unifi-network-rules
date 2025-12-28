"""Backup services for UniFi Network Rules integration."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import voluptuous as vol
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.port_forward import PortForward

# Import the typed model classes for conversion
from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.traffic_rule import TrafficRule
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ..const import BACKUP_FILE_PREFIX, BACKUP_LOCATION, DOMAIN, LOGGER
from ..helpers.id_parser import parse_rule_id
from ..models.firewall_rule import FirewallRule
from ..models.qos_rule import QoSRule
from ..models.static_route import StaticRoute
from ..models.vpn_config import VPNConfig
from .constants import (
    CONF_FILENAME,
    CONF_NAME_FILTER,
    CONF_RULE_IDS,
    CONF_RULE_TYPES,
    SERVICE_BACKUP,
    SERVICE_RESTORE,
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
        vol.Optional(CONF_RULE_TYPES): vol.All(
            cv.ensure_list,
            [
                vol.In(
                    [
                        "policy",
                        "port_forward",
                        "route",
                        "qos_rule",
                        "vpn_client",
                        "port_profile",
                        "network",
                        "nat",
                        "oon_policy",
                    ]
                )
            ],
            description="Types of rules to restore: policy (firewall), port_forward, route (traffic routes), qos_rule (QoS rules), vpn_client (VPN clients), port_profile (switch port configurations), network (network configurations), nat (NAT rules), oon_policy (Object-Oriented Network policies)",
        ),
    }
)


def create_backup_from_coordinator(coordinator, filename: str, hostname: str = None) -> dict:
    """Create a backup data structure from a coordinator's data.

    Args:
        coordinator: The coordinator containing the rule data
        filename: The filename for the backup
        hostname: Optional hostname override (will use coordinator's api.host if not provided)

    Returns:
        Dict containing the backup data structure
    """
    if not hostname and hasattr(coordinator.api, "host"):
        hostname = coordinator.api.host

    # Create backup data structure
    backup_data = {"hostname": hostname, "timestamp": datetime.now().isoformat(), "rules": {}}

    # Track which rule types we've backed up
    available_rules = []

    # Collect all rules from the coordinator data
    for rule_type, rules in coordinator.data.items():
        if not rules:
            continue

        # Serialize rules for backup (data is now pre-filtered in coordinator)
        serialized_rules = []
        for rule in rules:
            if hasattr(rule, "raw"):
                # API objects usually have a raw property with the dict representation
                serialized_rules.append(rule.raw)
            elif isinstance(rule, dict):
                # Some rules might already be dictionaries
                serialized_rules.append(rule)

        if serialized_rules:
            backup_data["rules"][rule_type] = serialized_rules
            available_rules.append(rule_type)

    return backup_data, available_rules


async def async_backup_rules_service(hass: HomeAssistant, coordinators: dict, call: ServiceCall) -> None:
    """Back up rules to a file."""
    entry_id = call.data.get("config_entry_id")
    filename = call.data.get("filename")

    # Get coordinator and API for the specified entry or use the first available one
    if entry_id and entry_id in coordinators:
        coordinator = coordinators[entry_id]
    else:
        # If no specific entry_id is provided or it's invalid, use the first available coordinator
        if not coordinators:
            raise ValueError("No UniFi Network Rules coordinators available")
        entry_id = next(iter(coordinators))
        coordinator = coordinators[entry_id]
        LOGGER.info("Using default coordinator for entry_id: %s", entry_id)

    api = coordinator.api

    # Generate backup filename
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hostname = api.host.replace(".", "_")
        filename = f"{BACKUP_FILE_PREFIX}_{hostname}_{timestamp}.json"
    elif not filename.endswith(".json"):
        filename = f"{filename}.json"

    # Get rules data using helper function
    backup_data, available_rules = create_backup_from_coordinator(coordinator, filename)

    # Save backup file
    backup_path = hass.config.path(BACKUP_LOCATION, filename)

    # Ensure the backup directory exists
    Path(os.path.dirname(backup_path)).mkdir(parents=True, exist_ok=True)

    # Use aiofiles for async file operations
    async with aiofiles.open(backup_path, "w") as f:
        await f.write(json.dumps(backup_data, indent=2))

    LOGGER.info("Backed up %d rule types to %s", len(available_rules), backup_path)

    return {
        "status": "success",
        "filename": filename,
        "path": backup_path,
        "rule_types": available_rules,
        "rule_count": sum(len(backup_data["rules"].get(rule_type, [])) for rule_type in available_rules),
    }


async def async_restore_rules_service(hass: HomeAssistant, coordinators: dict, call: ServiceCall) -> None:
    """Restore rules from a file."""
    entry_id = call.data.get("config_entry_id")
    filename = call.data.get("filename")
    force_restore = call.data.get("force_restore", False)
    rule_ids = call.data.get("rule_ids", [])

    # Normalize rule_ids to handle entity IDs and unique IDs
    if rule_ids:
        normalized_rule_ids = []
        for rid in rule_ids:
            normalized_id, _ = parse_rule_id(rid)  # Extract clean UniFi ID
            normalized_rule_ids.append(normalized_id)
        rule_ids = normalized_rule_ids
        LOGGER.debug("Normalized rule_ids for restore: %s", rule_ids)
    name_filter = call.data.get("name_filter", "")
    rule_types = call.data.get("rule_types", [])

    if rule_types:
        LOGGER.info("Filtering restore to only include rule types: %s", rule_types)
    if rule_ids:
        LOGGER.info("Filtering restore to only include rule IDs: %s", rule_ids)
    if name_filter:
        LOGGER.info("Filtering restore to only include rules with names containing: %s", name_filter)

    # Helper function to robustly check if a rule exists
    def rule_exists_in_collection(rule_dict: dict, collection: list[Any]) -> bool:
        """Check if a rule exists in a collection, using primarily ID matching.

        First checks by ID, then falls back to minimal attribute matching only for specific cases.
        """
        rule_id = rule_dict.get("_id", "")

        # If we have an ID, use that as the primary comparison method
        if rule_id:
            for existing_rule in collection:
                existing_id = getattr(existing_rule, "id", None)
                if existing_id is None and isinstance(existing_rule, dict):
                    existing_id = existing_rule.get("_id", None)

                if existing_id == rule_id:
                    LOGGER.debug("Rule ID match found: %s", rule_id)
                    return True

        return False

    # Get coordinator and API for the specified entry or use the first available one
    if entry_id and entry_id in coordinators:
        coordinator = coordinators[entry_id]
    else:
        # If no specific entry_id is provided or it's invalid, use the first available coordinator
        if not coordinators:
            raise ValueError("No UniFi Network Rules coordinators available")
        entry_id = next(iter(coordinators))
        coordinator = coordinators[entry_id]
        LOGGER.info("Using default coordinator for entry_id: %s", entry_id)

    api = coordinator.api

    # Validate parameters
    if not filename:
        raise ValueError("Filename is required")

    # Make sure filename has .json extension
    if not filename.endswith(".json"):
        filename = f"{filename}.json"

    # Load backup file
    backup_path = hass.config.path(BACKUP_LOCATION, filename)

    # Ensure the backup directory exists
    Path(os.path.dirname(backup_path)).mkdir(parents=True, exist_ok=True)

    try:
        # Use aiofiles for async file operations
        async with aiofiles.open(backup_path) as f:
            backup_data = json.loads(await f.read())
    except FileNotFoundError:
        raise ValueError(f"Backup file {filename} not found") from None
    except json.JSONDecodeError:
        raise ValueError(f"Backup file {filename} is not valid JSON") from None

    # Get rules from backup
    if "rules" not in backup_data:
        raise ValueError("Invalid backup file: 'rules' section not found")

    backup_entry = backup_data["rules"]

    # Ensure we have fresh data before processing
    LOGGER.info("Refreshing coordinator data to ensure we have the latest state...")
    await coordinator.async_refresh()

    # Create an automatic backup of the current state before restoring
    # This serves as a safety net in case anything goes wrong during restore
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    auto_backup_filename = f"auto_backup_before_restore_{timestamp}.json"
    LOGGER.info("Creating automatic backup of current state before restoration: %s", auto_backup_filename)

    # Use the helper function to create the backup data
    auto_backup_data, auto_backup_rule_types = create_backup_from_coordinator(coordinator, auto_backup_filename)

    # Save the automatic backup file
    auto_backup_path = hass.config.path(BACKUP_LOCATION, auto_backup_filename)
    Path(os.path.dirname(auto_backup_path)).mkdir(parents=True, exist_ok=True)

    # Use aiofiles for async file operations
    async with aiofiles.open(auto_backup_path, "w") as f:
        await f.write(json.dumps(auto_backup_data, indent=2))

    LOGGER.info("Automatic backup created at %s with %d rule types", auto_backup_path, len(auto_backup_rule_types))

    # Log restore mode
    if force_restore:
        LOGGER.info("Force restore mode enabled - all rules will be restored/overwritten")
    else:
        LOGGER.info("Selective restore mode - only restoring rules that don't already exist")

    # Define a function to determine if a rule should be restored (handles filtering)
    async def should_restore(rule_dict: dict, rule_type: str) -> bool:
        """Determine if a rule should be restored based on filters.

        Applies rule_ids, name_filter, and rule_types filters.
        Does NOT check if the rule exists - that's handled separately.

        Returns True if the rule passes all filters and should be restored.
        """
        # Check if rule has required fields
        if "_id" not in rule_dict:
            return False

        rule_id = rule_dict["_id"]

        # Apply rule_ids filter if specified
        if rule_ids and rule_id not in rule_ids:
            LOGGER.debug("Rule %s not in specified rule_ids list, skipping", rule_id)
            return False

        # Apply name_filter if specified
        if name_filter:
            rule_name = rule_dict.get("name", "")
            if not rule_name or name_filter.lower() not in rule_name.lower():
                LOGGER.debug("Rule name '%s' doesn't match filter '%s', skipping", rule_name, name_filter)
                return False

        # Apply rule_types filter if specified
        if rule_types:
            # Map rule_type to the corresponding type in rule_types
            rule_type_map = {
                # Standard selectable types in service schema
                "firewall_policy": "policy",  # Newer version of rules
                "port_forward": "port_forward",
                "traffic_route": "route",
                "static_route": "route",  # Static routes
                "nat": "nat",
                # Legacy types - older controllers will have these instead of firewall_policy
                "legacy_firewall": "policy",  # Maps to policy as it's the older version
                "traffic_rule": "policy",  # Maps to policy as it's the older version of firewall rules
                "legacy_traffic": "policy",  # Maps to policy as it's the older version of firewall rules
                "qos_rule": "qos_rule",  # Maps to qos_rule as it's the newer version of QoS rules
                "vpn_client": "vpn_client",  # Maps to vpn_client as it's the newer version of VPN clients
                "port_profile": "port_profile",  # Switch port profiles
                "network": "network",  # Network configurations
                "oon_policy": "oon_policy",  # Object-Oriented Network policies
            }
            mapped_type = rule_type_map.get(rule_type)

            # Only apply rule_types filter if it's specified
            if rule_types and mapped_type not in rule_types:
                LOGGER.debug(
                    "Rule type %s (mapped to %s) not in specified rule_types list, skipping", rule_type, mapped_type
                )
                return False

        # All filters passed
        return True

    # Using queue_api_operation for all API calls to prevent rate limiting
    # and avoid overwhelming the UniFi controller with too many concurrent requests.
    # This queues operations and executes them at a controlled rate.

    # Restore firewall policies
    restore_counts = {}
    skip_counts = {}
    if "firewall_policies" in backup_entry and hasattr(api, "update_firewall_policy"):
        restore_counts["firewall_policies"] = 0
        skip_counts["firewall_policies"] = 0
        LOGGER.info("Restoring firewall policies...")
        for rule_dict in backup_entry["firewall_policies"]:
            rule_id = rule_dict.get("_id", "")

            # Apply filters first
            should_restore_rule = await should_restore(rule_dict, "firewall_policy")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "firewall_policies" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["firewall_policies"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug("Rule %s exists and force_restore is True, updating existing rule", rule_id)
                        # Convert to typed object for update
                        rule_obj = FirewallPolicy(rule_dict)
                        await api.queue_api_operation(api.update_firewall_policy, rule_obj)
                    elif rule_exists:
                        # Rule exists but force_restore is False, so skip it
                        LOGGER.debug(
                            "Rule %s already exists, skipping (use force_restore=True to update existing rules)",
                            rule_id,
                        )
                        skip_counts["firewall_policies"] += 1
                    else:
                        # Use add method when the rule doesn't exist
                        LOGGER.debug("Creating new firewall policy based on %s", rule_id)
                        # For adding new rules, create a copy without the _id field
                        # to let the API assign a new ID
                        add_rule_dict = rule_dict.copy()
                        if "_id" in add_rule_dict:
                            del add_rule_dict["_id"]  # Remove ID to avoid InvalidObject errors

                        await api.queue_api_operation(api.add_firewall_policy, add_rule_dict)

                    restore_counts["firewall_policies"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring firewall policy %s: %s", rule_id, err)
            else:
                skip_counts["firewall_policies"] += 1

        LOGGER.info(
            "Processed %d firewall policies (restored: %d, skipped: %d)",
            restore_counts["firewall_policies"] + skip_counts["firewall_policies"],
            restore_counts["firewall_policies"],
            skip_counts["firewall_policies"],
        )

    # Restore traffic rules
    if "traffic_rules" in backup_entry and hasattr(api, "update_traffic_rule"):
        restore_counts["traffic_rules"] = 0
        skip_counts["traffic_rules"] = 0
        LOGGER.info("Restoring traffic rules...")
        for rule_dict in backup_entry["traffic_rules"]:
            rule_id = rule_dict.get("_id", "")

            # Apply filters first
            should_restore_rule = await should_restore(rule_dict, "traffic_rule")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "traffic_rules" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["traffic_rules"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug("Rule %s exists and force_restore is True, updating existing rule", rule_id)
                        # Convert to typed object for update
                        rule_obj = TrafficRule(rule_dict)
                        await api.queue_api_operation(api.update_traffic_rule, rule_obj)
                    elif rule_exists:
                        # Rule exists but force_restore is False, so skip it
                        LOGGER.debug(
                            "Rule %s already exists, skipping (use force_restore=True to update existing rules)",
                            rule_id,
                        )
                        skip_counts["traffic_rules"] += 1
                    else:
                        # Use add method when the rule doesn't exist
                        LOGGER.debug("Creating new traffic rule based on %s", rule_id)
                        # For adding new rules, create a copy without the _id field
                        # to let the API assign a new ID
                        add_rule_dict = rule_dict.copy()
                        if "_id" in add_rule_dict:
                            del add_rule_dict["_id"]  # Remove ID to avoid InvalidObject errors

                        await api.queue_api_operation(api.add_traffic_rule, add_rule_dict)

                    restore_counts["traffic_rules"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring traffic rule %s: %s", rule_id, err)
            else:
                skip_counts["traffic_rules"] += 1

        LOGGER.info(
            "Processed %d traffic rules (restored: %d, skipped: %d)",
            restore_counts["traffic_rules"] + skip_counts["traffic_rules"],
            restore_counts["traffic_rules"],
            skip_counts["traffic_rules"],
        )

    # Restore port forwards
    if "port_forwards" in backup_entry and hasattr(api, "update_port_forward"):
        restore_counts["port_forwards"] = 0
        skip_counts["port_forwards"] = 0
        LOGGER.info("Restoring port forwards...")
        for rule_dict in backup_entry["port_forwards"]:
            rule_id = rule_dict.get("_id", "")

            # Apply filters first
            should_restore_rule = await should_restore(rule_dict, "port_forward")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "port_forwards" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["port_forwards"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug("Rule %s exists and force_restore is True, updating existing rule", rule_id)
                        # Convert to typed object for update
                        rule_obj = PortForward(rule_dict)
                        await api.queue_api_operation(api.update_port_forward, rule_obj)
                    elif rule_exists:
                        # Rule exists but force_restore is False, so skip it
                        LOGGER.debug(
                            "Rule %s already exists, skipping (use force_restore=True to update existing rules)",
                            rule_id,
                        )
                        skip_counts["port_forwards"] += 1
                    else:
                        # Use add method when the rule doesn't exist
                        LOGGER.debug("Creating new port forward rule based on %s", rule_id)
                        # For adding new rules, create a copy without the _id field
                        # to let the API assign a new ID
                        add_rule_dict = rule_dict.copy()
                        if "_id" in add_rule_dict:
                            del add_rule_dict["_id"]  # Remove ID to avoid InvalidObject errors

                        # Let the UniFi API handle validation itself
                        await api.queue_api_operation(api.add_port_forward, add_rule_dict)

                    restore_counts["port_forwards"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring port forward %s: %s", rule_id, err)
            else:
                skip_counts["port_forwards"] += 1

        LOGGER.info(
            "Processed %d port forwards (restored: %d, skipped: %d)",
            restore_counts["port_forwards"] + skip_counts["port_forwards"],
            restore_counts["port_forwards"],
            skip_counts["port_forwards"],
        )

    # Restore legacy firewall rules
    if "legacy_firewall_rules" in backup_entry and api.capabilities.legacy_firewall:
        restore_counts["legacy_firewall_rules"] = 0
        skip_counts["legacy_firewall_rules"] = 0
        LOGGER.info("Restoring legacy firewall rules...")
        for rule_dict in backup_entry["legacy_firewall_rules"]:
            rule_id = rule_dict.get("_id", "")

            # Apply filters first
            should_restore_rule = await should_restore(rule_dict, "legacy_firewall")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "legacy_firewall_rules" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["legacy_firewall_rules"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug("Rule %s exists and force_restore is True, updating existing rule", rule_id)
                        # Convert to typed object for update
                        rule_obj = FirewallRule(rule_dict)
                        await api.queue_api_operation(api.update_legacy_firewall_rule, rule_obj)
                    elif rule_exists:
                        # Rule exists but force_restore is False, so skip it
                        LOGGER.debug(
                            "Rule %s already exists, skipping (use force_restore=True to update existing rules)",
                            rule_id,
                        )
                        skip_counts["legacy_firewall_rules"] += 1
                    else:
                        # Use add method when the rule doesn't exist
                        LOGGER.debug("Creating new firewall rule based on %s", rule_id)
                        # For adding new rules, create a copy without the _id field
                        # to let the API assign a new ID
                        add_rule_dict = rule_dict.copy()
                        if "_id" in add_rule_dict:
                            del add_rule_dict["_id"]  # Remove ID to avoid InvalidObject errors

                        await api.queue_api_operation(api.add_legacy_firewall_rule, add_rule_dict)

                    restore_counts["legacy_firewall_rules"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring legacy firewall rule %s: %s", rule_id, err)
            else:
                skip_counts["legacy_firewall_rules"] += 1

        LOGGER.info(
            "Processed %d legacy firewall rules (restored: %d, skipped: %d)",
            restore_counts["legacy_firewall_rules"] + skip_counts["legacy_firewall_rules"],
            restore_counts["legacy_firewall_rules"],
            skip_counts["legacy_firewall_rules"],
        )

    # Restore legacy traffic rules
    if "legacy_traffic_rules" in backup_entry and api.capabilities.legacy_traffic:
        restore_counts["legacy_traffic_rules"] = 0
        skip_counts["legacy_traffic_rules"] = 0
        LOGGER.info("Restoring legacy traffic rules...")
        for rule_dict in backup_entry["legacy_traffic_rules"]:
            rule_id = rule_dict.get("_id", "")

            # Apply filters first
            should_restore_rule = await should_restore(rule_dict, "legacy_traffic")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "legacy_traffic_rules" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["legacy_traffic_rules"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug("Rule %s exists and force_restore is True, updating existing rule", rule_id)
                        # Convert to typed object for update
                        rule_obj = TrafficRule(rule_dict)
                        await api.queue_api_operation(api.update_legacy_traffic_rule, rule_obj)
                    else:
                        # Use add method when the rule doesn't exist
                        LOGGER.debug("Creating new legacy traffic rule based on %s", rule_id)
                        # For adding new rules, create a copy without the _id field
                        # to let the API assign a new ID
                        add_rule_dict = rule_dict.copy()
                        if "_id" in add_rule_dict:
                            del add_rule_dict["_id"]  # Remove ID to avoid InvalidObject errors

                        await api.queue_api_operation(api.add_legacy_traffic_rule, add_rule_dict)

                    restore_counts["legacy_traffic_rules"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring legacy traffic rule %s: %s", rule_id, err)
            else:
                skip_counts["legacy_traffic_rules"] += 1

        LOGGER.info(
            "Processed %d legacy traffic rules (restored: %d, skipped: %d)",
            restore_counts["legacy_traffic_rules"] + skip_counts["legacy_traffic_rules"],
            restore_counts["legacy_traffic_rules"],
            skip_counts["legacy_traffic_rules"],
        )

    # Restore traffic routes
    if "traffic_routes" in backup_entry and hasattr(api, "update_traffic_route"):
        restore_counts["traffic_routes"] = 0
        skip_counts["traffic_routes"] = 0
        LOGGER.info("Restoring traffic routes...")
        for rule_dict in backup_entry["traffic_routes"]:
            rule_id = rule_dict.get("_id", "")

            # Apply filters first
            should_restore_rule = await should_restore(rule_dict, "traffic_route")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "traffic_routes" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["traffic_routes"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug("Rule %s exists and force_restore is True, updating existing rule", rule_id)
                        # Convert to typed object for update
                        rule_obj = TrafficRoute(rule_dict)
                        await api.queue_api_operation(api.update_traffic_route, rule_obj)
                    elif rule_exists:
                        # Rule exists but force_restore is False, so skip it
                        LOGGER.debug(
                            "Rule %s already exists, skipping (use force_restore=True to update existing rules)",
                            rule_id,
                        )
                        skip_counts["traffic_routes"] += 1
                    else:
                        # Use add method when the rule doesn't exist
                        LOGGER.debug("Creating new traffic route based on %s", rule_id)
                        # For adding new rules, create a copy without the _id field
                        # to let the API assign a new ID
                        add_rule_dict = rule_dict.copy()
                        if "_id" in add_rule_dict:
                            del add_rule_dict["_id"]  # Remove ID to avoid InvalidObject errors

                        # Let the UniFi API handle validation itself
                        await api.queue_api_operation(api.add_traffic_route, add_rule_dict)

                    restore_counts["traffic_routes"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring traffic route %s: %s", rule_id, err)
            else:
                skip_counts["traffic_routes"] += 1

        LOGGER.info(
            "Processed %d traffic routes (restored: %d, skipped: %d)",
            restore_counts["traffic_routes"] + skip_counts["traffic_routes"],
            restore_counts["traffic_routes"],
            skip_counts["traffic_routes"],
        )

    # Restore NAT rules (custom)
    if "nat_rules" in backup_entry and hasattr(api, "update_nat_rule"):
        restore_counts["nat_rules"] = 0
        skip_counts["nat_rules"] = 0
        LOGGER.info("Restoring NAT rules...")
        for rule_dict in backup_entry["nat_rules"]:
            rule_id = rule_dict.get("_id", "")

            should_restore_rule = await should_restore(rule_dict, "nat")

            if should_restore_rule:
                rule_exists = False
                if "nat_rules" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["nat_rules"])

                try:
                    from ..models.nat_rule import NATRule

                    if rule_exists and force_restore:
                        rule_obj = NATRule(rule_dict)
                        await api.queue_api_operation(api.update_nat_rule, rule_obj)
                    elif rule_exists:
                        skip_counts["nat_rules"] += 1
                    else:
                        # Creation of NAT rules via API is not supported by this integration
                        LOGGER.warning(
                            "Skipping creation of NAT rule %s - creating new NAT rules is not supported via restore.",
                            rule_id,
                        )
                        skip_counts["nat_rules"] += 1

                    restore_counts["nat_rules"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring NAT rule %s: %s", rule_id, err)
            else:
                skip_counts["nat_rules"] += 1

        LOGGER.info(
            "Processed %d NAT rules (restored: %d, skipped: %d)",
            restore_counts["nat_rules"] + skip_counts["nat_rules"],
            restore_counts["nat_rules"],
            skip_counts["nat_rules"],
        )

    # Restore static routes
    if "static_routes" in backup_entry and hasattr(api, "update_static_route"):
        restore_counts["static_routes"] = 0
        skip_counts["static_routes"] = 0
        LOGGER.info("Restoring static routes...")
        for rule_dict in backup_entry["static_routes"]:
            rule_id = rule_dict.get("_id", "")

            # Apply filters first
            should_restore_rule = await should_restore(rule_dict, "static_route")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "static_routes" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["static_routes"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug("Rule %s exists and force_restore is True, updating existing rule", rule_id)
                        # Convert to typed object for update
                        rule_obj = StaticRoute(rule_dict)
                        await api.queue_api_operation(api.update_static_route, rule_obj)
                    elif rule_exists:
                        # Rule exists but force_restore is False, so skip it
                        LOGGER.debug(
                            "Rule %s already exists, skipping (use force_restore=True to update existing rules)",
                            rule_id,
                        )
                        skip_counts["static_routes"] += 1
                    else:
                        # Use add method when the rule doesn't exist
                        LOGGER.debug("Creating new static route based on %s", rule_id)
                        # For adding new rules, create a copy without the _id field
                        # to let the API assign a new ID
                        add_rule_dict = rule_dict.copy()
                        if "_id" in add_rule_dict:
                            del add_rule_dict["_id"]  # Remove ID to avoid InvalidObject errors

                        # Let the UniFi API handle validation itself
                        await api.queue_api_operation(api.add_static_route, add_rule_dict)

                    restore_counts["static_routes"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring static route %s: %s", rule_id, err)
            else:
                skip_counts["static_routes"] += 1

        LOGGER.info(
            "Processed %d static routes (restored: %d, skipped: %d)",
            restore_counts["static_routes"] + skip_counts["static_routes"],
            restore_counts["static_routes"],
            skip_counts["static_routes"],
        )

    # Restore QoS rules
    if "qos_rules" in backup_entry and hasattr(api, "update_qos_rule"):
        restore_counts["qos_rules"] = 0
        skip_counts["qos_rules"] = 0
        LOGGER.info("Restoring QoS rules...")
        for rule_dict in backup_entry["qos_rules"]:
            rule_id = rule_dict.get("_id", "")

            # Apply filters first
            should_restore_rule = await should_restore(rule_dict, "qos_rule")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "qos_rules" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["qos_rules"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug("Rule %s exists and force_restore is True, updating existing rule", rule_id)
                        # Convert to typed object for update
                        rule_obj = QoSRule(rule_dict)
                        await api.queue_api_operation(api.update_qos_rule, rule_obj)
                    elif rule_exists:
                        # Rule exists but force_restore is False, so skip it
                        LOGGER.debug(
                            "Rule %s already exists, skipping (use force_restore=True to update existing rules)",
                            rule_id,
                        )
                        skip_counts["qos_rules"] += 1
                    else:
                        # Use add method when the rule doesn't exist
                        LOGGER.debug("Creating new QoS rule based on %s", rule_id)
                        # For adding new rules, create a copy without the _id field
                        # to let the API assign a new ID
                        add_rule_dict = rule_dict.copy()
                        if "_id" in add_rule_dict:
                            del add_rule_dict["_id"]  # Remove ID to avoid InvalidObject errors

                        # Let the UniFi API handle validation itself
                        await api.queue_api_operation(api.add_qos_rule, add_rule_dict)

                    restore_counts["qos_rules"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring QoS rule %s: %s", rule_id, err)
            else:
                skip_counts["qos_rules"] += 1

        LOGGER.info(
            "Processed %d QoS rules (restored: %d, skipped: %d)",
            restore_counts["qos_rules"] + skip_counts["qos_rules"],
            restore_counts["qos_rules"],
            skip_counts["qos_rules"],
        )

    # Restore VPN clients
    if "vpn_clients" in backup_entry and hasattr(api, "update_vpn_client"):
        restore_counts["vpn_clients"] = 0
        skip_counts["vpn_clients"] = 0
        LOGGER.info("Restoring VPN clients...")
        for rule_dict in backup_entry["vpn_clients"]:
            rule_id = rule_dict.get("_id", "")

            # Apply filters first
            should_restore_rule = await should_restore(rule_dict, "vpn_client")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "vpn_clients" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["vpn_clients"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug("Rule %s exists and force_restore is True, updating existing rule", rule_id)
                        # Convert to typed object for update
                        rule_obj = VPNConfig(rule_dict)
                        await api.queue_api_operation(api.update_vpn_client, rule_obj)
                    elif rule_exists:
                        # Rule exists but force_restore is False, so skip it
                        LOGGER.debug(
                            "Rule %s already exists, skipping (use force_restore=True to update existing rules)",
                            rule_id,
                        )
                        skip_counts["vpn_clients"] += 1
                    else:
                        # Use add method when the rule doesn't exist
                        LOGGER.debug("Creating new VPN client based on %s", rule_id)
                        # For adding new rules, create a copy without the _id field
                        # to let the API assign a new ID
                        add_rule_dict = rule_dict.copy()
                        if "_id" in add_rule_dict:
                            del add_rule_dict["_id"]  # Remove ID to avoid InvalidObject errors

                        # Let the UniFi API handle validation itself
                        await api.queue_api_operation(api.add_vpn_client, add_rule_dict)

                    restore_counts["vpn_clients"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring VPN client %s: %s", rule_id, err)
            else:
                skip_counts["vpn_clients"] += 1

        LOGGER.info(
            "Processed %d VPN clients (restored: %d, skipped: %d)",
            restore_counts["vpn_clients"] + skip_counts["vpn_clients"],
            restore_counts["vpn_clients"],
            skip_counts["vpn_clients"],
        )

    # Restore port profiles
    if "port_profiles" in backup_entry and hasattr(api, "update_port_profile"):
        restore_counts["port_profiles"] = 0
        skip_counts["port_profiles"] = 0
        LOGGER.info("Restoring port profiles...")
        for rule_dict in backup_entry["port_profiles"]:
            rule_id = rule_dict.get("_id", "")

            # Apply filters first
            should_restore_rule = await should_restore(rule_dict, "port_profile")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "port_profiles" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["port_profiles"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug("Rule %s exists and force_restore is True, updating existing rule", rule_id)
                        await api.queue_api_operation(api.update_port_profile, rule_dict)
                    elif rule_exists:
                        # Rule exists but force_restore is False, so skip it
                        LOGGER.debug(
                            "Rule %s already exists, skipping (use force_restore=True to update existing rules)",
                            rule_id,
                        )
                        skip_counts["port_profiles"] += 1
                    else:
                        # Use add method when the rule doesn't exist
                        LOGGER.debug("Creating new port profile based on %s", rule_id)
                        # For adding new rules, create a copy without the _id field
                        # to let the API assign a new ID
                        add_rule_dict = rule_dict.copy()
                        if "_id" in add_rule_dict:
                            del add_rule_dict["_id"]  # Remove ID to avoid InvalidObject errors

                        await api.queue_api_operation(api.add_port_profile, add_rule_dict)

                    restore_counts["port_profiles"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring port profile %s: %s", rule_id, err)
            else:
                skip_counts["port_profiles"] += 1

        LOGGER.info(
            "Processed %d port profiles (restored: %d, skipped: %d)",
            restore_counts["port_profiles"] + skip_counts["port_profiles"],
            restore_counts["port_profiles"],
            skip_counts["port_profiles"],
        )

    # Restore networks
    if "networks" in backup_entry and hasattr(api, "update_network"):
        restore_counts["networks"] = 0
        skip_counts["networks"] = 0
        LOGGER.info("Restoring networks...")
        for rule_dict in backup_entry["networks"]:
            rule_id = rule_dict.get("_id", "")

            # Apply filters first (networks are now pre-filtered during backup)
            should_restore_rule = await should_restore(rule_dict, "network")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "networks" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["networks"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug("Rule %s exists and force_restore is True, updating existing rule", rule_id)
                        # Create NetworkConf object for update
                        from ..models.network import NetworkConf

                        network_obj = NetworkConf(rule_dict)
                        await api.queue_api_operation(api.update_network, network_obj)
                    elif rule_exists:
                        # Rule exists but force_restore is False, so skip it
                        LOGGER.debug(
                            "Rule %s already exists, skipping (use force_restore=True to update existing rules)",
                            rule_id,
                        )
                        skip_counts["networks"] += 1
                    else:
                        # Networks are typically infrastructure - adding new ones should be rare
                        # Log this as a warning since it might be unexpected
                        LOGGER.warning("Creating new network based on %s - this may affect infrastructure", rule_id)
                        # For adding new networks, we typically don't remove the ID as they might need specific IDs
                        # But we should be careful about this operation
                        add_rule_dict = rule_dict.copy()
                        if "_id" in add_rule_dict:
                            del add_rule_dict["_id"]  # Remove ID to let UniFi assign one

                        # Note: There might not be an add_network method - networks are often pre-existing
                        # Check if the method exists before calling
                        if hasattr(api, "add_network"):
                            await api.queue_api_operation(api.add_network, add_rule_dict)
                        else:
                            LOGGER.warning("API does not support adding new networks, skipping creation of %s", rule_id)
                            skip_counts["networks"] += 1
                            continue

                    restore_counts["networks"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring network %s: %s", rule_id, err)
            else:
                skip_counts["networks"] += 1

        LOGGER.info(
            "Processed %d networks (restored: %d, skipped: %d)",
            restore_counts["networks"] + skip_counts["networks"],
            restore_counts["networks"],
            skip_counts["networks"],
        )

    # Restore OON policies
    if "oon_policies" in backup_entry and hasattr(api, "update_oon_policy"):
        restore_counts["oon_policies"] = 0
        skip_counts["oon_policies"] = 0
        LOGGER.info("Restoring OON policies...")
        for rule_dict in backup_entry["oon_policies"]:
            rule_id = rule_dict.get("_id") or rule_dict.get("id", "")

            # Apply filters first
            should_restore_rule = await should_restore(rule_dict, "oon_policy")

            if should_restore_rule:
                # Check if this rule already exists in the system
                rule_exists = False
                if "oon_policies" in coordinator.data:
                    rule_exists = rule_exists_in_collection(rule_dict, coordinator.data["oon_policies"])

                try:
                    if rule_exists and force_restore:
                        # Use update method when the rule exists and we're forcing an update
                        LOGGER.debug(
                            "OON policy %s exists and force_restore is True, updating existing policy", rule_id
                        )
                        from ..models.oon_policy import OONPolicy

                        policy_obj = OONPolicy(rule_dict)
                        await api.queue_api_operation(api.update_oon_policy, policy_obj)
                    elif rule_exists:
                        # Rule exists but force_restore is False, so skip it
                        LOGGER.debug(
                            "OON policy %s already exists, skipping (use force_restore=True to update existing policies)",
                            rule_id,
                        )
                        skip_counts["oon_policies"] += 1
                    else:
                        # Use add method when the policy doesn't exist
                        LOGGER.debug("Creating new OON policy based on %s", rule_id)
                        # For adding new policies, create a copy without the _id field
                        # to let the API assign a new ID
                        add_policy_dict = rule_dict.copy()
                        if "_id" in add_policy_dict:
                            del add_policy_dict["_id"]  # Remove ID to avoid InvalidObject errors
                        if "id" in add_policy_dict:
                            del add_policy_dict["id"]  # Remove ID to avoid InvalidObject errors

                        # Create the new policy
                        await api.queue_api_operation(api.add_oon_policy, add_policy_dict)

                    restore_counts["oon_policies"] += 1
                except Exception as err:
                    LOGGER.error("Error restoring OON policy %s: %s", rule_id, err)
            else:
                skip_counts["oon_policies"] += 1

        LOGGER.info(
            "Processed %d OON policies (restored: %d, skipped: %d)",
            restore_counts["oon_policies"] + skip_counts["oon_policies"],
            restore_counts["oon_policies"],
            skip_counts["oon_policies"],
        )

    # Refresh data after restore
    await coordinator.async_refresh()

    total_restored = sum(restore_counts.values())
    total_skipped = sum(skip_counts.values())
    total_processed = total_restored + total_skipped
    LOGGER.info(
        "Completed restoring rules from %s (processed: %d, restored: %d, skipped: %d)",
        backup_path,
        total_processed,
        total_restored,
        total_skipped,
    )

    return {
        "status": "success",
        "filename": filename,
        "path": backup_path,
        "rule_types_restored": list(backup_data["rules"].keys()),
        "restore_counts": restore_counts,
        "skip_counts": skip_counts,
        "total_restored": total_restored,
        "total_skipped": total_skipped,
        "mode": "force" if force_restore else "selective",
        "automatic_backup": {
            "filename": auto_backup_filename,
            "path": auto_backup_path,
            "rule_types": auto_backup_rule_types,
            "rule_count": sum(
                len(auto_backup_data["rules"].get(rule_type, [])) for rule_type in auto_backup_rule_types
            ),
        },
    }


async def async_setup_backup_services(hass: HomeAssistant, coordinators: dict) -> None:
    """Set up backup services."""

    async def handle_backup_rules(call: ServiceCall) -> None:
        """Handle backup rules service call."""
        return await async_backup_rules_service(hass, coordinators, call)

    async def handle_restore_rules(call: ServiceCall) -> None:
        """Handle restore rules service call."""
        return await async_restore_rules_service(hass, coordinators, call)

    # Register services with the improved schema
    hass.services.async_register(
        DOMAIN,
        SERVICE_BACKUP,
        handle_backup_rules,
        schema=vol.Schema(
            {
                vol.Optional("config_entry_id"): cv.string,
                vol.Optional("filename"): cv.string,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESTORE,
        handle_restore_rules,
        schema=vol.Schema(
            {
                vol.Optional("config_entry_id"): cv.string,
                vol.Required("filename"): cv.string,
                vol.Optional("force_restore"): cv.boolean,
                vol.Optional("rule_ids"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("name_filter"): cv.string,
                vol.Optional("rule_types"): vol.All(
                    cv.ensure_list,
                    [
                        vol.In(
                            [
                                "policy",
                                "port_forward",
                                "route",
                                "qos_rule",
                                "vpn_client",
                                "port_profile",
                                "network",
                                "nat",
                                "oon_policy",
                            ]
                        )
                    ],
                    description="Types of rules to restore: policy (firewall), port_forward, route (traffic routes), qos_rule (QoS rules), vpn_client (VPN clients), port_profile (switch port configurations), network (network configurations), nat (NAT rules), oon_policy (Object-Oriented Network policies)",
                ),
            }
        ),
    )

    async def _queue_backup_operation(self, target_path: str, rule_types: list[str]) -> bool:
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
            future = await self.api.queue_api_operation(self._create_backup, target_path, rule_types)
            result = await future
            return result
        except Exception as err:
            LOGGER.error("Error in queued backup operation: %s", err)
            return False

    async def _queue_restore_operation(self, source_path: str, rule_types: list[str]) -> bool:
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
            future = await self.api.queue_api_operation(self._restore_from_backup, source_path, rule_types)
            result = await future
            return result
        except Exception as err:
            LOGGER.error("Error in queued restore operation: %s", err)
            return False
