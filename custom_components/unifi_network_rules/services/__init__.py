"""Services for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant, ServiceCall

from ..const import DOMAIN, LOGGER

# Import services from service modules
from .rule_services import (
    async_setup_rule_services,
    async_toggle_rule,
    async_delete_rule,
    async_bulk_update_rules,
)
from .template_services import (
    async_setup_template_services,
    async_apply_template,
    async_save_template,
)
from .backup_services import (
    async_setup_backup_services,
    async_backup_rules_service,
    async_restore_rules_service,
)
from .system_services import (
    async_setup_system_services,
    async_refresh_service,
    async_websocket_diagnostics,
)
from .cleanup_services import (
    async_setup_cleanup_services,
    async_force_cleanup,
    async_force_remove_stale,
)

# Centralized service name constants
from .constants import (
    SERVICE_REFRESH,
    SERVICE_REFRESH_DATA,
    SERVICE_BACKUP,
    SERVICE_RESTORE,
    SERVICE_BULK_UPDATE,
    SERVICE_DELETE_RULE,
    SERVICE_APPLY_TEMPLATE,
    SERVICE_SAVE_TEMPLATE,
    SERVICE_FORCE_CLEANUP,
    SERVICE_FORCE_REMOVE_STALE,
    SERVICE_WEBSOCKET_DIAGNOSTICS,
    SERVICE_TOGGLE_RULE,
)

# Store for entry_id -> coordinator mappings
coordinators = {}

# Register a coordinator for a config entry
def register_coordinator(entry_id: str, coordinator: Any) -> None:
    """Register a coordinator for a config entry."""
    coordinators[entry_id] = coordinator
    LOGGER.debug("Registered coordinator for entry %s", entry_id)

# Unregister a coordinator for a config entry
def unregister_coordinator(entry_id: str) -> None:
    """Unregister a coordinator for a config entry."""
    if entry_id in coordinators:
        del coordinators[entry_id]
        LOGGER.debug("Unregistered coordinator for entry %s", entry_id)

async def async_setup_services(hass: HomeAssistant) -> bool:
    """Set up services for UniFi Network Rules."""
    
    # Set up services from each module
    await async_setup_rule_services(hass, coordinators)
    await async_setup_template_services(hass, coordinators)
    await async_setup_backup_services(hass, coordinators)
    await async_setup_system_services(hass, coordinators)
    await async_setup_cleanup_services(hass, coordinators)
    
    # Store the register/unregister functions in the services dictionary
    if "services" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["services"] = {}
    
    hass.data[DOMAIN]["services"]["register_coordinator"] = register_coordinator
    hass.data[DOMAIN]["services"]["unregister_coordinator"] = unregister_coordinator
    
    LOGGER.debug("Services initialized and registration functions stored in services dictionary")

    return True

async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload UniFi Network Rules services."""
    services_to_remove = [
        SERVICE_TOGGLE_RULE,
        SERVICE_REFRESH_DATA,
        SERVICE_REFRESH,
        SERVICE_BACKUP,
        SERVICE_RESTORE,
        SERVICE_BULK_UPDATE,
        SERVICE_DELETE_RULE,
        SERVICE_APPLY_TEMPLATE,
        SERVICE_SAVE_TEMPLATE,
        SERVICE_FORCE_CLEANUP,
        SERVICE_FORCE_REMOVE_STALE,
        SERVICE_WEBSOCKET_DIAGNOSTICS
    ]
    
    for service in services_to_remove:
        hass.services.async_remove(DOMAIN, service) 