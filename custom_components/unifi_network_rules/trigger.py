"""UniFi Network Rules trigger platform."""
from __future__ import annotations

from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo

from .const import LOGGER

# Import unified trigger system
from .unified_trigger import (
    TRIGGER_UNR_CHANGED,
    async_validate_trigger_config as unified_validate_trigger_config,
    async_attach_trigger as unified_attach_trigger,
)

# Trigger type description for UI display
TRIGGER_TYPE_DESCRIPTIONS = {
    TRIGGER_UNR_CHANGED: "When any UniFi Network Rules entity changes",
}


async def async_validate_trigger_config(hass: HomeAssistant, config: dict) -> dict:
    """Validate trigger configuration."""
    return await unified_validate_trigger_config(hass, config)


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Set up a trigger."""
    LOGGER.info("[UNIFIED_TRIGGER] Setting up unified trigger: %s", 
               {k: v for k, v in config.items() if k not in ["platform"]})
    return await unified_attach_trigger(hass, config, action, trigger_info)


# All legacy trigger classes removed - only unified triggers supported
