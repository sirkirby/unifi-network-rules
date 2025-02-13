from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import ATTR_ENTITY_ID
from .utils import logger
import asyncio
import json
import os
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

SERVICE_FILENAME = "filename"
SERVICE_NAME_FILTER = "name_filter"
SERVICE_STATE = "state"
SERVICE_TEMPLATE = "template"
SERVICE_RULE_TYPE = "rule_type"
SERVICE_RULE_ID = "rule_id"

BACKUP_SCHEMA = vol.Schema({
    vol.Required(SERVICE_FILENAME): cv.string,
})

RESTORE_SCHEMA = vol.Schema({
    vol.Required(SERVICE_FILENAME): cv.string,
    vol.Optional("rule_ids"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("name_filter"): cv.string,
    vol.Optional("rule_types"): vol.All(cv.ensure_list, [vol.In(["policy", "route", "firewall", "traffic"])])
})

BULK_UPDATE_SCHEMA = vol.Schema({
    vol.Required(SERVICE_NAME_FILTER): cv.string,
    vol.Required(SERVICE_STATE): cv.boolean,
})

CREATE_FROM_TEMPLATE_SCHEMA = vol.Schema({
    vol.Required(SERVICE_TEMPLATE): dict,
    vol.Required(SERVICE_RULE_TYPE): vol.In(["policy"]),
})

DELETE_RULE_SCHEMA = vol.Schema({
    vol.Required(SERVICE_RULE_ID): cv.string,
    vol.Required(SERVICE_RULE_TYPE): vol.In(["policy"]),
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
            entry_backup = {}
            
            # Only include non-empty data in backup
            if firewall_policies := coordinator.data.get("firewall_policies"):
                entry_backup["firewall_policies"] = firewall_policies
            
            if traffic_routes := coordinator.data.get("traffic_routes"):
                entry_backup["traffic_routes"] = traffic_routes
            
            if firewall_rules := coordinator.data.get("firewall_rules", {}).get("data"):
                entry_backup["firewall_rules"] = firewall_rules
            
            if traffic_rules := coordinator.data.get("traffic_rules"):
                entry_backup["traffic_rules"] = traffic_rules
            
            if entry_backup:
                backup_data[entry_id] = entry_backup

    if not backup_data:
        logger.error("No data available to backup")
        return None

    try:
        backup_path = hass.config.path(filename)
        json_data = json.dumps(backup_data, indent=2, ensure_ascii=False)
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(json_data)
        logger.info(f"Rules backup created successfully at {backup_path}")
        return backup_data
    except Exception as e:
        logger.error(f"Failed to create backup: {str(e)}")
        return None

async def async_restore_rules_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to restore rules from a file."""
    filename = call.data[SERVICE_FILENAME]
    rule_ids = call.data.get("rule_ids", [])
    name_filter = call.data.get("name_filter", "")
    rule_types = call.data.get("rule_types", ["policy", "route", "firewall", "traffic"])
    
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

    def should_restore_rule(rule, rule_type):
        """Check if a rule should be restored based on filters."""
        if rule_ids and rule["_id"] not in rule_ids:
            return False
        if name_filter and name_filter.lower() not in rule.get("name", "").lower():
            return False
        if rule_type not in rule_types:
            return False
        return True

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
                if not policy.get("predefined", False) and should_restore_rule(policy, "policy"):
                    try:
                        success, error = await api.update_firewall_policy(policy["_id"], policy)
                        if not success:
                            logger.error(f"Failed to restore firewall policy {policy['_id']}: {error}")
                    except Exception as e:
                        logger.error(f"Error restoring firewall policy {policy['_id']}: {str(e)}")

        # Restore traffic routes if available
        if api.capabilities.traffic_routes and "traffic_routes" in backup_entry:
            for route in backup_entry["traffic_routes"]:
                if should_restore_rule(route, "route"):
                    try:
                        success, error = await api.update_traffic_route(route["_id"], route)
                        if not success:
                            logger.error(f"Failed to restore traffic route {route['_id']}: {error}")
                    except Exception as e:
                        logger.error(f"Error restoring traffic route {route['_id']}: {str(e)}")

        # Restore legacy firewall rules if available
        if "firewall_rules" in backup_entry:
            for rule in backup_entry["firewall_rules"]:
                if should_restore_rule(rule, "firewall"):
                    try:
                        success, error = await api.update_legacy_firewall_rule(rule["_id"], rule)
                        if not success:
                            logger.error(f"Failed to restore legacy firewall rule {rule['_id']}: {error}")
                    except Exception as e:
                        logger.error(f"Error restoring legacy firewall rule {rule['_id']}: {str(e)}")

        # Restore legacy traffic rules if available
        if "traffic_rules" in backup_entry:
            for rule in backup_entry["traffic_rules"]:
                if should_restore_rule(rule, "traffic"):
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

async def async_bulk_update_rules_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to enable/disable multiple rules based on name matching."""
    name_filter = call.data[SERVICE_NAME_FILTER].lower()
    desired_state = call.data[SERVICE_STATE]
    domain_data = hass.data.get("unifi_network_rules", {})
    
    for entry_id, entry_data in domain_data.items():
        coordinator = entry_data.get("coordinator")
        api = entry_data.get("api")
        if not coordinator or not api:
            continue
            
        # Get all rules that match the name filter
        matched_rules = []
        if coordinator.data:
            # Check firewall policies
            if api.capabilities.zone_based_firewall:
                for policy in coordinator.data.get("firewall_policies", []):
                    if name_filter in policy.get("name", "").lower():
                        matched_rules.append(("policy", policy))
                    
            # Check traffic routes
            if api.capabilities.traffic_routes:
                for route in coordinator.data.get("traffic_routes", []):
                    if name_filter in route.get("name", "").lower():
                        matched_rules.append(("route", route))
        
        # Update each matched rule
        for rule_type, rule in matched_rules:
            try:
                rule_copy = rule.copy()
                rule_copy["enabled"] = desired_state
                
                if rule_type == "policy":
                    success, error = await api.update_firewall_policy(rule["_id"], rule_copy)
                else:  # route
                    success, error = await api.update_traffic_route(rule["_id"], rule_copy)
                    
                if not success:
                    logger.error(f"Failed to update {rule_type} rule {rule['_id']}: {error}")
                else:
                    logger.info(f"Successfully updated {rule_type} rule '{rule.get('name')}' to {desired_state}")
                    
            except Exception as e:
                logger.error(f"Error updating {rule_type} rule {rule['_id']}: {str(e)}")
        
        # Refresh the coordinator after updates
        await coordinator.async_request_refresh()

async def async_create_from_template_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to create a new rule from a template."""
    template_data = call.data[SERVICE_TEMPLATE]
    rule_type = call.data[SERVICE_RULE_TYPE]
    domain_data = hass.data.get("unifi_network_rules", {})
    
    for entry_id, entry_data in domain_data.items():
        api = entry_data.get("api")
        if not api:
            continue
            
        try:
            if rule_type == "policy":
                success, error = await api.create_firewall_policy(template_data)
                if not success:
                    logger.error(f"Failed to create firewall policy: {error}")
                else:
                    logger.info("Successfully created firewall policy from template")
            else:
                logger.error(f"Unsupported rule type for template creation: {rule_type}")
                continue
                
            # Refresh the coordinator
            coordinator = entry_data.get("coordinator")
            if coordinator:
                await coordinator.async_request_refresh()
                
        except Exception as e:
            logger.error(f"Error creating rule from template: {str(e)}")

async def async_delete_rule_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to delete a rule."""
    rule_id = call.data[SERVICE_RULE_ID]
    rule_type = call.data[SERVICE_RULE_TYPE]
    domain_data = hass.data.get("unifi_network_rules", {})
    
    for entry_id, entry_data in domain_data.items():
        api = entry_data.get("api")
        if not api:
            continue
            
        try:
            if rule_type == "policy":
                success, error = await api.delete_firewall_policies([rule_id])
                if not success:
                    logger.error(f"Failed to delete firewall policy: {error}")
                else:
                    logger.info(f"Successfully deleted firewall policy {rule_id}")
            else:
                logger.error(f"Unsupported rule type for deletion: {rule_type}")
                continue
                
            # Refresh the coordinator
            coordinator = entry_data.get("coordinator")
            if coordinator:
                await coordinator.async_request_refresh()
                
        except Exception as e:
            logger.error(f"Error deleting rule: {str(e)}")

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

    async def wrapped_bulk_update_service(call: ServiceCall) -> None:
        """Wrapped bulk update service that ensures proper call argument."""
        await async_bulk_update_rules_service(hass, call)

    async def wrapped_create_from_template_service(call: ServiceCall) -> None:
        """Wrapped create from template service that ensures proper call argument."""
        await async_create_from_template_service(hass, call)
        
    async def wrapped_delete_rule_service(call: ServiceCall) -> None:
        """Wrapped delete rule service that ensures proper call argument."""
        await async_delete_rule_service(hass, call)

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
    
    hass.services.async_register(
        "unifi_network_rules",
        "bulk_update_rules",
        wrapped_bulk_update_service,
        schema=BULK_UPDATE_SCHEMA,
    )
    
    hass.services.async_register(
        "unifi_network_rules",
        "create_from_template",
        wrapped_create_from_template_service,
        schema=CREATE_FROM_TEMPLATE_SCHEMA,
    )
    
    hass.services.async_register(
        "unifi_network_rules",
        "delete_rule",
        wrapped_delete_rule_service,
        schema=DELETE_RULE_SCHEMA,
    )
