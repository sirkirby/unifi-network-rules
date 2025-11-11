"""Unified Trigger System for UniFi Network Rules."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant.const import CONF_TYPE, CONF_PLATFORM
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, LOGGER


# Unified trigger type
TRIGGER_UNR_CHANGED = "unr_changed"

# Valid change types (entity types)
VALID_CHANGE_TYPES = [
    "firewall_policy",
    "traffic_rule", 
    "traffic_route",
    "port_forward",
    "firewall_zone",
    "wlan",
    "qos_rule",
    "vpn_client", 
    "vpn_server",
    "device",
    "port_profile",
    "network",
    "route",
    "nat",
    "oon_policy"
]

# Valid change actions
VALID_CHANGE_ACTIONS = [
    "created",
    "deleted", 
    "enabled",
    "disabled",
    "modified"
]

# Configuration schema for unified triggers
UNIFIED_TRIGGER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PLATFORM): DOMAIN,
        vol.Required(CONF_TYPE): TRIGGER_UNR_CHANGED,
        vol.Optional("entity_id"): cv.string,  # Specific entity filter
        vol.Optional("change_type"): vol.In(VALID_CHANGE_TYPES),  # Entity type filter
        vol.Optional("change_action"): vol.Any(
            vol.In(VALID_CHANGE_ACTIONS),
            vol.All(cv.ensure_list, [vol.In(VALID_CHANGE_ACTIONS)])
        ),  # Action filter - can be single or list
        vol.Optional("name_filter"): cv.string,  # Name pattern filter
    }
)


async def async_validate_trigger_config(hass: HomeAssistant, config: dict) -> dict:
    """Validate unified trigger configuration."""
    result = UNIFIED_TRIGGER_SCHEMA(config)
    LOGGER.debug("[UNIFIED_TRIGGER] Trigger validation: input=%s, output=%s", config, result)
    return result


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Set up a unified trigger."""
    trigger_data = {
        "platform": DOMAIN,
        "type": TRIGGER_UNR_CHANGED,
    }

    # Copy optional filters
    for key in ["entity_id", "change_type", "change_action", "name_filter"]:
        if key in config:
            trigger_data[key] = config[key]

    LOGGER.info("[UNIFIED_TRIGGER] Setting up unified trigger: %s", 
               {k: v for k, v in config.items() if k not in ["platform"]})
    
    trigger = UnifiedRuleTrigger(
        hass,
        config,
        action,
        trigger_info,
        trigger_data,
    )
    return await trigger.async_attach()


class UnifiedRuleTrigger:
    """Unified trigger handler for all UniFi Network Rules changes."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict,
        action: TriggerActionType,
        trigger_info: TriggerInfo,
        trigger_data: Dict[str, Any],
    ) -> None:
        """Initialize unified trigger."""
        self.hass = hass
        self.config = config
        self.action = action
        self.trigger_info = trigger_info
        self.trigger_data = trigger_data
        self.remove_handler: Optional[CALLBACK_TYPE] = None

    async def async_attach(self) -> CALLBACK_TYPE:
        """Attach the unified trigger."""
        @callback
        def _handle_trigger_event(trigger_event_data: Dict[str, Any]) -> None:
            """Handle incoming trigger event."""
            try:
                # Apply filters
                if not self._matches_filters(trigger_event_data):
                    LOGGER.debug("[UNIFIED_TRIGGER] Event filtered out: %s", 
                               {k: v for k, v in trigger_event_data.items() if k in ["entity_id", "change_type", "change_action", "entity_name"]})
                    return

                LOGGER.debug("[UNIFIED_TRIGGER] Trigger firing for: %s (%s) - %s", 
                           trigger_event_data.get("entity_name", "unknown"),
                           trigger_event_data.get("change_type", "unknown"),
                           trigger_event_data.get("change_action", "unknown"))
                
                # Fire the trigger action
                trigger_vars = {
                    "trigger": {
                        "platform": DOMAIN,
                        "type": TRIGGER_UNR_CHANGED,
                        **trigger_event_data
                    }
                }
                
                # Execute the action
                result = self.action(trigger_vars)
                if asyncio.iscoroutine(result):
                    self.hass.async_create_task(result)
                    
            except Exception as err:
                LOGGER.error("[UNIFIED_TRIGGER] Error handling trigger event: %s", err)

        # Connect to the unified trigger signal
        signal_name = f"{DOMAIN}_trigger_unr_changed"
        self.remove_handler = async_dispatcher_connect(
            self.hass, signal_name, _handle_trigger_event
        )
        
        LOGGER.info("[UNIFIED_TRIGGER] Unified trigger attached and listening for signal: %s", signal_name)
        return self.async_detach

    def _matches_filters(self, event_data: Dict[str, Any]) -> bool:
        """Check if event matches the trigger's filters.
        
        Args:
            event_data: The trigger event data
            
        Returns:
            True if the event matches all configured filters
        """
        # Entity ID filter
        if "entity_id" in self.config:
            if self.config["entity_id"] != event_data.get("entity_id"):
                return False

        # Change type filter
        if "change_type" in self.config:
            if self.config["change_type"] != event_data.get("change_type"):
                return False

        # Change action filter (can be single value or list)
        if "change_action" in self.config:
            configured_actions = self.config["change_action"]
            event_action = event_data.get("change_action")
            
            # Handle both single action and list of actions
            if isinstance(configured_actions, list):
                if event_action not in configured_actions:
                    return False
            else:
                if event_action != configured_actions:
                    return False

        # Name filter (substring match, case insensitive)
        if "name_filter" in self.config:
            name_filter = self.config["name_filter"].lower()
            entity_name = event_data.get("entity_name", "").lower()
            if name_filter not in entity_name:
                return False

        return True

    def async_detach(self) -> None:
        """Detach the trigger."""
        if self.remove_handler:
            self.remove_handler()
            self.remove_handler = None
            
        LOGGER.debug("[UNIFIED_TRIGGER] Unified trigger detached")


# Legacy trigger compatibility mapping for migration purposes
LEGACY_TRIGGER_MAPPING = {
    "rule_enabled": {
        "type": TRIGGER_UNR_CHANGED,
        "change_action": "enabled"
    },
    "rule_disabled": {
        "type": TRIGGER_UNR_CHANGED,
        "change_action": "disabled"
    },
    "rule_changed": {
        "type": TRIGGER_UNR_CHANGED,
        "change_action": ["enabled", "disabled", "modified"]
    },
    "rule_deleted": {
        "type": TRIGGER_UNR_CHANGED,
        "change_action": "deleted"
    },
    "device_changed": {
        "type": TRIGGER_UNR_CHANGED,
        "change_type": "device"
    }
}
