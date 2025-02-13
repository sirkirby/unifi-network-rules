from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import ATTR_ENTITY_ID
from .utils import logger
import asyncio
import json
import os
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

SERVICE_FILENAME = "filename"

BACKUP_SCHEMA = vol.Schema({
    vol.Required(SERVICE_FILENAME): cv.string,
})

RESTORE_SCHEMA = vol.Schema({
    vol.Required(SERVICE_FILENAME): cv.string,
})

async def async_refresh_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to refresh UniFi data."""
    domain_data = hass.data.get("unifi_network_rules", {})
    tasks = []

    for entry in domain_data.values():
        coordinator = entry.get("coordinator")
        if coordinator:
            try:
                tasks.append(coordinator.async_request_refresh())
            except Exception as e:
                logger.error(f"Error scheduling coordinator refresh: {str(e)}")

    if tasks:
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.debug(f"Coordinator refresh triggered via service for {len(tasks)} coordinator(s)")
        except Exception as e:
            logger.error(f"Error during coordinator refresh: {str(e)}")
    else:
        logger.debug("Coordinator not found during service call")

async def async_backup_rules_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to backup rules to a file."""
    filename = call.data[SERVICE_FILENAME]
    domain_data = hass.data.get("unifi_network_rules", {})
    backup_data = {}

    for entry_id, entry_data in domain_data.items():
        coordinator = entry_data.get("coordinator")
        if coordinator and coordinator.data:
            firewall_rules = coordinator.data.get("firewall_rules", [])
            # Handle both list and dict structures
            if isinstance(firewall_rules, dict):
                firewall_rules = firewall_rules.get("data", [])

            backup_data[entry_id] = {
                "firewall_policies": coordinator.data.get("firewall_policies", []),
                "traffic_routes": coordinator.data.get("traffic_routes", []),
                "firewall_rules": firewall_rules,
                "traffic_rules": coordinator.data.get("traffic_rules", [])
            }

    if not backup_data:
        logger.error("No data available to backup")
        return

    try:
        backup_path = hass.config.path(filename)
        with open(backup_path, 'w') as f:
            json.dump(backup_data, f, indent=2)
        logger.info(f"Rules backup created successfully at {backup_path}")
    except Exception as e:
        logger.error(f"Failed to create backup: {str(e)}")

async def async_restore_rules_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to restore rules from a file."""
    filename = call.data[SERVICE_FILENAME]
    domain_data = hass.data.get("unifi_network_rules", {})
    backup_path = hass.config.path(filename)

    if not os.path.exists(backup_path):
        logger.error(f"Backup file not found: {backup_path}")
        return

    try:
        with open(backup_path, 'r') as f:
            backup_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read backup file: {str(e)}")
        return

    for entry_id, entry_data in domain_data.items():
        if entry_id not in backup_data:
            logger.warning(f"No backup data found for entry {entry_id}")
            continue

        api = entry_data.get("api")
        if not api:
            logger.error(f"No API instance found for entry {entry_id}")
            continue

        backup_entry = backup_data[entry_id]

        # Restore firewall policies if available
        if api.capabilities.zone_based_firewall and "firewall_policies" in backup_entry:
            for policy in backup_entry["firewall_policies"]:
                if not policy.get("predefined", False):  # Skip predefined policies
                    try:
                        success, error = await api.update_firewall_policy(policy["_id"], policy)
                        if not success:
                            logger.error(f"Failed to restore firewall policy {policy['_id']}: {error}")
                    except Exception as e:
                        logger.error(f"Error restoring firewall policy {policy['_id']}: {str(e)}")

        # Restore traffic routes if available
        if api.capabilities.traffic_routes and "traffic_routes" in backup_entry:
            for route in backup_entry["traffic_routes"]:
                try:
                    success, error = await api.update_traffic_route(route["_id"], route)
                    if not success:
                        logger.error(f"Failed to restore traffic route {route['_id']}: {error}")
                except Exception as e:
                    logger.error(f"Error restoring traffic route {route['_id']}: {str(e)}")

        # Restore legacy firewall rules if available
        if api.capabilities.legacy_firewall:
            if "firewall_rules" in backup_entry:
                rules = backup_entry["firewall_rules"]
                # Handle both data structures
                if isinstance(rules, dict) and "data" in rules:
                    rules = rules["data"]
                for rule in rules:
                    try:
                        success, error = await api.update_legacy_firewall_rule(rule["_id"], rule)
                        if not success:
                            logger.error(f"Failed to restore legacy firewall rule {rule['_id']}: {error}")
                    except Exception as e:
                        logger.error(f"Error restoring legacy firewall rule {rule['_id']}: {str(e)}")

            if "traffic_rules" in backup_entry:
                for rule in backup_entry["traffic_rules"]:
                    try:
                        success, error = await api.update_legacy_traffic_rule(rule["_id"], rule)
                        if not success:
                            logger.error(f"Failed to restore legacy traffic rule {rule['_id']}: {error}")
                    except Exception as e:
                        logger.error(f"Error restoring legacy traffic rule {rule['_id']}: {str(e)}")

        # Refresh the coordinator after restore
        coordinator = entry_data.get("coordinator")
        if coordinator:
            await coordinator.async_request_refresh()

    logger.info("Rules restore completed")

async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the UniFi Network Rules integration."""
    async def wrapped_refresh_service(call: ServiceCall) -> None:
        """Wrapped refresh service that ensures proper call argument."""
        await async_refresh_service(hass, call)

    async def wrapped_backup_service(call: ServiceCall) -> None:
        """Wrapped backup service that ensures proper call argument."""
        await async_backup_rules_service(hass, call)

    async def wrapped_restore_service(call: ServiceCall) -> None:
        """Wrapped restore service that ensures proper call argument."""
        await async_restore_rules_service(hass, call)

    hass.services.async_register(
        "unifi_network_rules",
        "refresh",
        wrapped_refresh_service,
        schema=None,
    )
    
    hass.services.async_register(
        "unifi_network_rules",
        "backup_rules",
        wrapped_backup_service,
        schema=BACKUP_SCHEMA,
    )
    
    hass.services.async_register(
        "unifi_network_rules",
        "restore_rules",
        wrapped_restore_service,
        schema=RESTORE_SCHEMA,
    )
