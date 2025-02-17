"""UniFi Network Rules trigger platform."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import voluptuous as vol

from homeassistant.const import CONF_TYPE, CONF_PLATFORM
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo, TriggerProtocol
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, LOGGER, EVENT_RULE_UPDATED, EVENT_RULE_DELETED
from .rule_template import RuleType

# Trigger types
TRIGGER_RULE_ENABLED = "rule_enabled"
TRIGGER_RULE_DISABLED = "rule_disabled"
TRIGGER_RULE_CHANGED = "rule_changed"
TRIGGER_RULE_DELETED = "rule_deleted"

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
    config: ConfigType,
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

    # Create trigger protocol
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
        config: ConfigType,
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
        def _handle_event(event):
            """Handle the event."""
            # Check if event matches all filters
            if not all(
                event.data.get(k) == v
                for k, v in event_filter.items()
            ):
                return

            # Apply name filter if specified
            if name_filter:
                rule_name = event.data.get("new_state", {}).get("name", "")
                if not rule_name or name_filter.lower() not in rule_name.lower():
                    return

            # Check trigger type and rule state
            trigger_type = self.config[CONF_TYPE]
            
            if trigger_type in [TRIGGER_RULE_ENABLED, TRIGGER_RULE_DISABLED]:
                new_state = event.data.get("new_state", {})
                old_state = event.data.get("old_state", {})
                
                # Skip if no state change
                if old_state.get("enabled") == new_state.get("enabled"):
                    return
                
                # Check if state matches trigger type
                if (trigger_type == TRIGGER_RULE_ENABLED and not new_state.get("enabled", False)) or \
                   (trigger_type == TRIGGER_RULE_DISABLED and new_state.get("enabled", False)):
                    return

            elif trigger_type == TRIGGER_RULE_CHANGED:
                # Trigger on any change except enable/disable
                new_state = event.data.get("new_state", {})
                old_state = event.data.get("old_state", {})
                
                if not old_state or not new_state:
                    return
                    
                # Remove enabled state for comparison
                new_state_copy = dict(new_state)
                old_state_copy = dict(old_state)
                new_state_copy.pop("enabled", None)
                old_state_copy.pop("enabled", None)
                
                if new_state_copy == old_state_copy:
                    return

            # Run the trigger action
            self.async_run(event.data)

        # Subscribe to appropriate events based on trigger type
        if self.config[CONF_TYPE] == TRIGGER_RULE_DELETED:
            self.remove_handler = await self.hass.helpers.event.async_track_event(
                self.hass,
                EVENT_RULE_DELETED,
                _handle_event,
            )
        else:
            self.remove_handler = await self.hass.helpers.event.async_track_event(
                self.hass,
                EVENT_RULE_UPDATED,
                _handle_event,
            )

        return self.async_detach

    async def async_detach(self) -> None:
        """Detach trigger."""
        if self.remove_handler:
            self.remove_handler()
            self.remove_handler = None

    @callback
    def async_run(self, event_data: Dict[str, Any]) -> None:
        """Run action when trigger conditions are met."""
        self.hass.async_run_job(
            self.action, {
                "trigger": {
                    **self.trigger_data,
                    "event": event_data,
                },
            },
        )

    @callback
    def async_validate_trigger_config(self, **kwargs) -> bool:
        """Validate trigger configuration."""
        try:
            TRIGGER_SCHEMA(self.config)
            return True
        except vol.Invalid:
            return False