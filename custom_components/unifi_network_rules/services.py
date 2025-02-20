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
from .rule_template import RuleType

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

async def async_delete_rule_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to delete a rule."""
    rule_id = call.data[CONF_RULE_ID]
    rule_type = call.data[CONF_RULE_TYPE]
    domain_data = hass.data.get(DOMAIN, {})
    
    for entry_id, entry_data in domain_data.items():
        api = entry_data.get("api")
        if not api:
            continue
            
        try:
            success = False
            error = None
            
            if rule_type == "policy":
                success, error = await api.delete_firewall_policies([rule_id])
            elif rule_type == "route":
                success, error = await api.delete_traffic_routes([rule_id])
            elif rule_type == "port_forward":
                success, error = await api.delete_port_forward_rules([rule_id])
            elif rule_type == "legacy_firewall" and api.capabilities.legacy_firewall:
                success, error = await api.delete_legacy_firewall_rules([rule_id])
            elif rule_type == "legacy_traffic" and api.capabilities.legacy_traffic:
                success, error = await api.delete_legacy_traffic_rules([rule_id])
            else:
                LOGGER.error(f"Deletion not supported for rule type: {rule_type}")
                continue
                
            if not success:
                LOGGER.error(f"Failed to delete {rule_type} rule: {error}")
            else:
                LOGGER.info(f"Successfully deleted {rule_type} rule {rule_id}")
                # Trigger cleanup after successful deletion
                async_dispatcher_send(hass, SIGNAL_ENTITIES_CLEANUP)
                
            # Refresh the coordinator
            coordinator = entry_data.get("coordinator")
            if coordinator:
                await coordinator.async_request_refresh()
                
        except Exception as e:
            LOGGER.error(f"Error deleting rule: {str(e)}")

async def async_apply_template_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to apply a rule template."""
    template_id = call.data[CONF_TEMPLATE_ID]
    variables = call.data.get(CONF_VARIABLES, {})
    
    template_registry = hass.data[DOMAIN].get("template_registry")
    if not template_registry:
        raise HomeAssistantError("Template registry not initialized")
        
    template = template_registry.get_template(template_id)
    if not template:
        raise HomeAssistantError(f"Template {template_id} not found")
        
    try:
        rule = template.to_rule(**variables)
    except (KeyError, ValueError) as e:
        raise HomeAssistantError(f"Error applying template: {str(e)}")

    # Create the rule using the appropriate API method
    for entry_data in hass.data[DOMAIN].values():
        api = entry_data.get("api")
        if not api:
            continue

        if template.rule_type == RuleType.FIREWALL_POLICY and api.capabilities.zone_based_firewall:
            await api.create_firewall_policy(rule)
        elif template.rule_type == RuleType.TRAFFIC_ROUTE and api.capabilities.traffic_routes:
            await api.create_traffic_route(rule)
        elif template.rule_type == RuleType.PORT_FORWARD:
            await api.create_port_forward_rule(rule)

        # Refresh coordinator after creating rule
        coordinator = entry_data.get("coordinator")
        if coordinator:
            await coordinator.async_refresh()
        break

async def async_save_template_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to save a rule template."""
    template_id = call.data[CONF_TEMPLATE_ID]
    rule_type = call.data[CONF_RULE_TYPE]
    template_data = call.data[CONF_TEMPLATE]
    
    template_registry = hass.data[DOMAIN].get("template_registry")
    if not template_registry:
        raise HomeAssistantError("Template registry not initialized")
        
    try:
        template = template_registry.create_template(rule_type, template_data)
        template_registry.register_template(template_id, template)
    except Exception as e:
        raise HomeAssistantError(f"Error saving template: {str(e)}")

async def async_cleanup_unavailable_entities(hass: HomeAssistant, call: ServiceCall = None) -> None:
    """Clean up unavailable entities."""
    registry = async_get_entity_registry(hass)
    removed = []
    
    if DOMAIN not in hass.data:
        LOGGER.warning("No UniFi Network Rules integration data found")
        return

    for entity_id, entry in list(registry.entities.items()):
        if entry.domain == DOMAIN and not entry.disabled:
            try:
                rule_id = entry.unique_id.split('_')[-1]
                config_entry_id = entry.config_entry_id
                
                # Check if rule exists in any coordinator
                exists = False
                for entry_id, config_entry_data in hass.data[DOMAIN].items():
                    coordinator = config_entry_data.get('coordinator')
                    if coordinator and coordinator.get_rule(rule_id):
                        exists = True
                        break
                        
                if not exists:
                    # First disable the entity
                    registry.async_update_entity(
                        entity_id,
                        disabled_by="integration"
                    )
                    
                    # Remove from config entry
                    if config_entry_id:
                        registry.async_update_entity(
                            entity_id,
                            remove_config_entry_id=config_entry_id
                        )
                    
                    # Force remove entity state
                    if hass.states.get(entity_id) is not None:
                        hass.states.async_remove(entity_id)
                    
                    # Finally remove from registry
                    registry.async_remove(entity_id)
                    removed.append(entity_id)
                    
                    LOGGER.info("Removed unavailable entity %s (rule_id: %s)", entity_id, rule_id)
            except Exception as entity_err:
                LOGGER.error("Error processing entity %s: %s", entity_id, str(entity_err))
                
    if removed:
        LOGGER.info("Cleanup completed. Removed %d entities: %s", len(removed), removed)
        # Force reload after cleanup
        await _reload_integration_entities(hass)
        
        # Give Home Assistant a moment to process the changes
        await asyncio.sleep(1)
        
        # Double-check and force remove any remaining states
        for entity_id in removed:
            if hass.states.get(entity_id) is not None:
                hass.states.async_remove(entity_id)
    else:
        LOGGER.info("No unavailable entities found to clean up")

async def _reload_integration_entities(hass: HomeAssistant) -> None:
    """Reload integration entities to ensure clean state."""
    try:
        # Notify the coordinator to refresh
        for config_entry_data in hass.data[DOMAIN].values():
            coordinator = config_entry_data.get('coordinator')
            if coordinator:
                await coordinator.async_refresh()
                
        # Force platform reload
        for platform in hass.data.get("entity_platform", {}).get("switch", []):
            if platform.domain == DOMAIN:
                await platform.async_reset()
    except Exception as err:
        LOGGER.error("Error reloading integration entities: %s", str(err))

@callback
def async_trigger_cleanup(hass: HomeAssistant) -> None:
    """Trigger entity cleanup."""
    async_dispatcher_send(hass, SIGNAL_ENTITIES_CLEANUP)

async def _async_cleanup_task(hass: HomeAssistant) -> None:
    """Run the cleanup task."""
    try:
        await async_cleanup_unavailable_entities(hass)
    except Exception as err:
        LOGGER.error("Error during automatic entity cleanup: %s", str(err))

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
    
    # Delete rule service
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_RULE,
        async_delete_rule_service,
        schema=vol.Schema({
            vol.Required(CONF_RULE_ID): cv.string,
            vol.Required(CONF_RULE_TYPE): vol.In([
                "policy", "route", "port_forward", 
                "legacy_firewall", "legacy_traffic"
            ])
        })
    )
    
    # Template services
    hass.services.async_register(
        DOMAIN,
        SERVICE_APPLY_TEMPLATE,
        async_apply_template_service,
        schema=vol.Schema({
            vol.Required(CONF_TEMPLATE_ID): cv.string,
            vol.Optional(CONF_VARIABLES, default={}): dict
        })
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SAVE_TEMPLATE,
        async_save_template_service,
        schema=vol.Schema({
            vol.Required(CONF_TEMPLATE_ID): cv.string,
            vol.Required(CONF_RULE_TYPE): vol.In([
                RuleType.FIREWALL_POLICY.value,
                RuleType.TRAFFIC_ROUTE.value,
                RuleType.PORT_FORWARD.value
            ]),
            vol.Required(CONF_TEMPLATE): dict
        })
    )
