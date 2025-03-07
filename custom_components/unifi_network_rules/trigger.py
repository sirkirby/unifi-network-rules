"""UniFi Network Rules trigger platform."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import voluptuous as vol

from homeassistant.const import CONF_TYPE, CONF_PLATFORM
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo, TriggerProtocol

from .const import DOMAIN, LOGGER
from .rule_template import RuleType

# Trigger types
TRIGGER_RULE_ENABLED = "rule_enabled"
TRIGGER_RULE_DISABLED = "rule_disabled"
TRIGGER_RULE_CHANGED = "rule_changed"
TRIGGER_RULE_DELETED = "rule_deleted"

# Message types from aiounifi websocket
WS_MSG_FIREWALL = "firewall"
WS_MSG_PORT_FORWARD = "portForward"
WS_MSG_ROUTING = "routing"
WS_MSG_DPI = "dpi"

# Mapping of websocket message types to rule types
WS_MSG_TYPE_MAP = {
    WS_MSG_FIREWALL: RuleType.FIREWALL_POLICY.value,
    WS_MSG_PORT_FORWARD: RuleType.PORT_FORWARD.value,
    WS_MSG_ROUTING: RuleType.TRAFFIC_ROUTE.value,
}

# Configuration schema
TRIGGER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PLATFORM): DOMAIN,
        vol.Required(CONF_TYPE): vol.In([
            TRIGGER_RULE_ENABLED,
            TRIGGER_RULE_DISABLED,
            TRIGGER_RULE_CHANGED,
            TRIGGER_RULE_DELETED,
        ]),
        vol.Optional("rule_id"): cv.string,
        vol.Optional("rule_type"): vol.In([
            RuleType.FIREWALL_POLICY.value,
            RuleType.TRAFFIC_ROUTE.value,
            RuleType.PORT_FORWARD.value,
        ]),
        vol.Optional("name_filter"): cv.string,
    }
)

async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Set up a trigger."""
    trigger_data = {
        "platform": DOMAIN,
        "type": config[CONF_TYPE],
    }

    if "rule_id" in config:
        trigger_data["rule_id"] = config["rule_id"]
    if "rule_type" in config:
        trigger_data["rule_type"] = config["rule_type"]
    if "name_filter" in config:
        trigger_data["name_filter"] = config["name_filter"]

    trigger = UnifiRuleTriggerProtocol(
        hass,
        config,
        action,
        trigger_info,
        trigger_data,
    )
    return await trigger.async_attach()

class UnifiRuleTriggerProtocol(TriggerProtocol):
    """Trigger protocol for UniFi Network Rules."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict,
        action: TriggerActionType,
        trigger_info: TriggerInfo,
        trigger_data: Dict[str, Any],
    ) -> None:
        """Initialize trigger protocol."""
        self.hass = hass
        self.config = config
        self.action = action
        self.trigger_info = trigger_info
        self.trigger_data = trigger_data
        self.remove_handler: Optional[CALLBACK_TYPE] = None
        self._rule_cache: Dict[str, Dict[str, Any]] = {}

    async def async_attach(self) -> CALLBACK_TYPE:
        """Attach trigger."""
        event_filter = {}
        name_filter = self.config.get("name_filter")

        # Add rule_id filter if specified
        if "rule_id" in self.config:
            event_filter["rule_id"] = self.config["rule_id"]
        if "rule_type" in self.config:
            event_filter["rule_type"] = self.config["rule_type"]

        @callback
        def _handle_websocket_msg(msg: Dict[str, Any]) -> None:
            """Handle websocket message."""
            try:
                msg_type = None
                rule_data = None

                # Determine message type and extract rule data
                for ws_type, payload in msg.items():
                    if ws_type in WS_MSG_TYPE_MAP:
                        msg_type = WS_MSG_TYPE_MAP[ws_type]
                        rule_data = payload
                        break

                if not msg_type or not rule_data or "_id" not in rule_data:
                    return

                # Apply filters
                if "rule_type" in event_filter and event_filter["rule_type"] != msg_type:
                    return
                if "rule_id" in event_filter and event_filter["rule_id"] != rule_data["_id"]:
                    return
                if name_filter:
                    rule_name = rule_data.get("name", "")
                    if not rule_name or name_filter.lower() not in rule_name.lower():
                        return

                # Get previous state from cache
                rule_id = rule_data["_id"]
                old_state = self._rule_cache.get(rule_id)
                
                # Handle different trigger types
                trigger_type = self.config[CONF_TYPE]
                should_trigger = False

                if trigger_type in [TRIGGER_RULE_ENABLED, TRIGGER_RULE_DISABLED]:
                    old_enabled = old_state.get("enabled", False) if old_state else False
                    new_enabled = rule_data.get("enabled", False)
                    if old_enabled != new_enabled:
                        should_trigger = (
                            (trigger_type == TRIGGER_RULE_ENABLED and new_enabled) or
                            (trigger_type == TRIGGER_RULE_DISABLED and not new_enabled)
                        )

                elif trigger_type == TRIGGER_RULE_CHANGED:
                    if old_state is not None:
                        # Compare states excluding metadata
                        old_copy = {k: v for k, v in old_state.items() 
                                  if not k.startswith('_') and k != 'enabled'}
                        new_copy = {k: v for k, v in rule_data.items() 
                                  if not k.startswith('_') and k != 'enabled'}
                        should_trigger = old_copy != new_copy

                elif trigger_type == TRIGGER_RULE_DELETED:
                    if old_state is not None and msg.get('meta', {}).get('deleted'):
                        should_trigger = True
                        # Remove from cache
                        self._rule_cache.pop(rule_id, None)

                # Update cache unless deleted
                if trigger_type != TRIGGER_RULE_DELETED:
                    self._rule_cache[rule_id] = rule_data

                # Trigger action if conditions met
                if should_trigger:
                    data = {
                        "rule_id": rule_id,
                        "rule_type": msg_type,
                        "old_state": old_state,
                        "new_state": rule_data if trigger_type != TRIGGER_RULE_DELETED else None,
                        "trigger_type": trigger_type
                    }
                    self.hass.async_run_job(
                        self.action, {"trigger": {**self.trigger_data, "event": data}}
                    )

            except Exception as err:
                LOGGER.error("Error handling websocket message: %s", str(err))

        # Get initial state for the rules we're watching
        entry_data = self.hass.data[DOMAIN]
        for config_entry_data in entry_data.values():
            if "coordinator" in config_entry_data:
                coordinator = config_entry_data["coordinator"]
                if coordinator.data:
                    self._update_rule_cache(coordinator.data)

            if "websocket" in config_entry_data:
                websocket = config_entry_data["websocket"]
                # Store the previous callback if it exists
                previous_callback = websocket._message_handler
                
                @callback
                def combined_callback(msg: Dict[str, Any]) -> None:
                    """Handle both our trigger and any previous callback."""
                    _handle_websocket_msg(msg)
                    if previous_callback:
                        self.hass.async_create_task(previous_callback(msg))
                
                websocket.set_callback(combined_callback)
                # Store remove function to restore previous callback
                self.remove_handler = lambda: websocket.set_callback(previous_callback)
                break

        return self.async_detach

    def _update_rule_cache(self, data: Dict[str, Any]) -> None:
        """Update rule cache from coordinator data."""
        for rule_type, rules in data.items():
            if rule_type in WS_MSG_TYPE_MAP.values():
                for rule in rules:
                    if isinstance(rule, dict) and "_id" in rule:
                        self._rule_cache[rule["_id"]] = rule

    async def async_detach(self) -> None:
        """Detach trigger."""
        if self.remove_handler:
            self.remove_handler()
            self.remove_handler = None