"""UniFi Network Rules trigger platform."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import voluptuous as vol

from homeassistant.const import CONF_TYPE, CONF_PLATFORM
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo

from .const import DOMAIN, LOGGER, LOG_TRIGGERS

# Module-level logging to verify trigger platform loads
LOGGER.info("🚀 UniFi Network Rules trigger platform loading...")

# Rule types as constants - updated to match current codebase
RULE_TYPE_FIREWALL_POLICY = "firewall_policies"
RULE_TYPE_TRAFFIC_ROUTE = "traffic_routes"
RULE_TYPE_PORT_FORWARD = "port_forwards"
RULE_TYPE_QOS_RULE = "qos_rules"
RULE_TYPE_VPN_CLIENT = "vpn_clients"
RULE_TYPE_VPN_SERVER = "vpn_servers"
RULE_TYPE_LEGACY_FIREWALL_RULE = "legacy_firewall_rules"
RULE_TYPE_TRAFFIC_RULE = "traffic_rules"
RULE_TYPE_WLAN = "wlans"

# Trigger types
TRIGGER_RULE_ENABLED = "rule_enabled"
TRIGGER_RULE_DISABLED = "rule_disabled"
TRIGGER_RULE_CHANGED = "rule_changed"
TRIGGER_RULE_DELETED = "rule_deleted"

# Message types from UniFi OS websocket - updated based on actual message structure
WS_MSG_FIREWALL = "firewall"
WS_MSG_PORT_FORWARD = "port_forward"
WS_MSG_ROUTING = "routing"
WS_MSG_DPI = "dpi"
WS_MSG_QOS = "qos"
WS_MSG_VPN = "vpn"
WS_MSG_WLAN = "wlan"
WS_MSG_NETWORK = "network"

# Enhanced mapping based on actual websocket message analysis
# Since UniFi OS doesn't always send consistent message types, we'll use keyword-based detection
RULE_TYPE_KEYWORDS = {
    RULE_TYPE_FIREWALL_POLICY: ["firewall", "policy", "security", "allow", "deny", "drop"],
    RULE_TYPE_TRAFFIC_ROUTE: ["route", "routing", "traffic", "gateway"],
    RULE_TYPE_PORT_FORWARD: ["port", "forward", "nat", "dnat", "snat"],
    RULE_TYPE_QOS_RULE: ["qos", "quality", "service", "bandwidth"],
    RULE_TYPE_VPN_CLIENT: ["vpn", "client", "openvpn-client", "wireguard-client"],
    RULE_TYPE_VPN_SERVER: ["vpn", "server", "openvpn-server", "wireguard-server"],
    RULE_TYPE_LEGACY_FIREWALL_RULE: ["firewallrule", "legacy", "accept", "reject"],
    RULE_TYPE_TRAFFIC_RULE: ["trafficrule", "traffic_rule"],
    RULE_TYPE_WLAN: ["wlan", "wireless", "wifi", "ssid"],
}

# Configuration schema - updated with all supported rule types
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
            RULE_TYPE_FIREWALL_POLICY,
            RULE_TYPE_TRAFFIC_ROUTE,
            RULE_TYPE_PORT_FORWARD,
            RULE_TYPE_QOS_RULE,
            RULE_TYPE_VPN_CLIENT,
            RULE_TYPE_VPN_SERVER,
            RULE_TYPE_LEGACY_FIREWALL_RULE,
            RULE_TYPE_TRAFFIC_RULE,
            RULE_TYPE_WLAN,
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

    if LOG_TRIGGERS:
        LOGGER.info("Setting up UniFi trigger: type=%s, rule_type=%s, rule_id=%s", 
                   config[CONF_TYPE], config.get("rule_type"), config.get("rule_id"))
    
    trigger = UnifiRuleTrigger(
        hass,
        config,
        action,
        trigger_info,
        trigger_data,
    )
    return await trigger.async_attach()

class UnifiRuleTrigger:
    """Trigger handler for UniFi Network Rules."""

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
        self._processed_cfgversions: set = set()

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
            # Only log detailed processing for non-repetitive messages
            if LOG_TRIGGERS and not msg.get("meta", {}).get("message") == "device:update":
                LOGGER.info("🎯 TRIGGER PROCESSING MESSAGE: %s", 
                           str(msg)[:100] + "..." if len(str(msg)) > 100 else str(msg))
            try:
                # Extract message type and data from UniFi OS websocket structure
                meta = msg.get("meta", {})
                msg_type = meta.get("message", "")
                msg_data = msg.get("data", {})
                
                if not msg_type or not msg_data:
                    return

                # Determine rule type based on message content and keywords
                detected_rule_type = None
                rule_data = None

                # Handle UniFi OS device:update messages with cfgversion changes
                if msg_type == "device:update" and isinstance(msg_data, list):
                    # Look for cfgversion changes which indicate rule updates
                    for item in msg_data:
                        if isinstance(item, dict) and "cfgversion" in item:
                            cfgversion = item.get("cfgversion")
                            # Check if we've already processed this cfgversion to avoid duplicates
                            if cfgversion in self._processed_cfgversions:
                                return
                            self._processed_cfgversions.add(cfgversion)
                            
                            # Keep only recent cfgversions (limit memory usage)
                            if len(self._processed_cfgversions) > 100:
                                self._processed_cfgversions = set(list(self._processed_cfgversions)[-50:])
                            
                            if LOG_TRIGGERS:
                                LOGGER.info("Trigger: Detected cfgversion change: %s", cfgversion)
                            # For cfgversion changes, we trigger a general rule_changed event
                            # since we can't determine the specific rule from device:update messages
                            if self.config[CONF_TYPE] == TRIGGER_RULE_CHANGED:
                                # Create a synthetic rule change event
                                data = {
                                    "rule_id": f"device_config_{meta.get('mac', 'unknown')}",
                                    "rule_type": "device_configuration", 
                                    "old_state": None,
                                    "new_state": {"cfgversion": cfgversion},
                                    "trigger_type": TRIGGER_RULE_CHANGED,
                                    "device_mac": meta.get("mac"),
                                    "cfgversion": cfgversion
                                }
                                if LOG_TRIGGERS:
                                    LOGGER.info("🔥 TRIGGER FIRING: %s for device config change %s", 
                                               TRIGGER_RULE_CHANGED, meta.get("mac"))
                                try:
                                    trigger_vars = {
                                        "platform": DOMAIN,
                                        "type": TRIGGER_RULE_CHANGED,
                                        "event": data  # Nest the data under 'event' key
                                    }
                                    if LOG_TRIGGERS:
                                        LOGGER.info("Calling action with trigger vars: %s", trigger_vars)
                                    # Schedule the action execution
                                    self.hass.async_create_task(
                                        self.action({"trigger": trigger_vars})
                                    )
                                    
                                    # Also trigger coordinator refresh since config changed
                                    self._dispatch_coordinator_refresh("Config change detected via cfgversion")
                                except Exception as err:
                                    LOGGER.error("Error executing trigger action: %s", err)
                            return
                
                # Check for direct rule data in message (original logic for direct rule messages)
                if isinstance(msg_data, dict) and "_id" in msg_data:
                    rule_data = msg_data
                elif isinstance(msg_data, list) and len(msg_data) > 0:
                    # Take the first item that has an _id
                    for item in msg_data:
                        if isinstance(item, dict) and "_id" in item:
                            rule_data = item
                            break

                if not rule_data:
                    return

                # Detect rule type using keyword matching
                message_str = str(msg).lower()
                for rule_type, keywords in RULE_TYPE_KEYWORDS.items():
                    if any(keyword in message_str for keyword in keywords):
                        detected_rule_type = rule_type
                        break

                # If we couldn't detect the rule type, try to infer from data structure
                if not detected_rule_type:
                    # Check for specific fields that identify rule types
                    if "purpose" in rule_data:
                        purpose = rule_data.get("purpose", "").lower()
                        if "vpn-client" in purpose:
                            detected_rule_type = RULE_TYPE_VPN_CLIENT
                        elif "vpn-server" in purpose:
                            detected_rule_type = RULE_TYPE_VPN_SERVER
                    elif "objective" in rule_data:
                        detected_rule_type = RULE_TYPE_QOS_RULE
                    elif "action" in rule_data and "ruleset" in rule_data:
                        detected_rule_type = RULE_TYPE_FIREWALL_POLICY
                    elif "dst_port" in rule_data or "fwd_port" in rule_data:
                        detected_rule_type = RULE_TYPE_PORT_FORWARD
                    elif "next_hop" in rule_data or "gateway" in rule_data:
                        detected_rule_type = RULE_TYPE_TRAFFIC_ROUTE

                if not detected_rule_type:
                    if LOG_TRIGGERS:
                        LOGGER.debug("Trigger: Could not detect rule type for message, skipping")
                    return

                if LOG_TRIGGERS:
                    LOGGER.info("Trigger: Detected rule type '%s' for rule %s", detected_rule_type, rule_data.get("_id"))

                # Apply filters
                if "rule_type" in event_filter and event_filter["rule_type"] != detected_rule_type:
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
                    if old_state is not None and meta.get('deleted'):
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
                        "rule_type": detected_rule_type,
                        "old_state": old_state,
                        "new_state": rule_data if trigger_type != TRIGGER_RULE_DELETED else None,
                        "trigger_type": trigger_type
                    }
                    if LOG_TRIGGERS:
                        LOGGER.info("🔥 TRIGGER FIRING: %s for rule %s (%s)", trigger_type, rule_id, detected_rule_type)
                    try:
                        trigger_vars = {
                            "platform": DOMAIN,
                            "type": trigger_type,
                            "event": data  # Nest the data under 'event' key
                        }
                        if LOG_TRIGGERS:
                            LOGGER.info("Calling action with trigger vars: %s", trigger_vars)
                        # Schedule the action execution
                        self.hass.async_create_task(
                            self.action({"trigger": trigger_vars})
                        )
                        
                        # Also trigger coordinator refresh since rule changed
                        self._dispatch_coordinator_refresh(f"Rule change detected: {rule_id} ({detected_rule_type})")
                    except Exception as err:
                        LOGGER.error("Error executing trigger action: %s", err)

            except Exception as err:
                LOGGER.error("Error handling websocket message: %s", str(err))

        # Get initial state for the rules we're watching
        domain_data = self.hass.data.get(DOMAIN, {})
        
        # Look for coordinator and websocket in entry-specific data
        coordinator = None
        websocket = None
        
        # Check each config entry
        for entry_id, entry_data in domain_data.items():
            # Skip non-entry data (like "shared", "services", etc.)
            if not isinstance(entry_data, dict) or entry_id in ["shared", "services", "platforms"]:
                continue
                
            if "coordinator" in entry_data:
                coordinator = entry_data["coordinator"]
                if coordinator and coordinator.data:
                    self._update_rule_cache(coordinator.data)

            if "websocket" in entry_data:
                websocket = entry_data["websocket"]
                break
        
        # Store coordinator reference for triggering refreshes
        self._coordinator = coordinator
        
        # Hook into the websocket handler's callback - but only once per websocket
        if coordinator and websocket:
            # Check if we already have enhanced triggers on this websocket
            if not hasattr(websocket, '_unr_original_handler'):
                # First trigger - store the original callback and create enhanced version
                original_websocket_callback = getattr(websocket, '_message_handler', None)
                
                if LOG_TRIGGERS:
                    LOGGER.info("🔍 TRIGGER DEBUG: First trigger setup - Found coordinator=%s, websocket=%s, original_callback=%s", 
                               coordinator is not None, websocket is not None, original_websocket_callback is not None)
                
                if original_websocket_callback:
                    # Store original for restoration
                    websocket._unr_original_handler = original_websocket_callback
                    websocket._unr_trigger_handlers = []
                    
                    @callback
                    def enhanced_websocket_callback(msg: Dict[str, Any]) -> None:
                        """Handle all trigger detection and original websocket processing."""
                        # Process all registered triggers
                        for trigger_handler in websocket._unr_trigger_handlers:
                            try:
                                trigger_handler(msg)
                            except Exception as err:
                                LOGGER.error("Error in trigger handler: %s", err)
                        
                        # Then call the original websocket callback (coordinator)
                        try:
                            websocket._unr_original_handler(msg)
                        except Exception as err:
                            LOGGER.error("Error in original websocket callback: %s", err)
                    
                    # Replace the websocket's callback with our enhanced version
                    websocket._message_handler = enhanced_websocket_callback
                    
                    if LOG_TRIGGERS:
                        LOGGER.info("✅ Trigger framework initialized on websocket")
                else:
                    LOGGER.warning("Websocket message handler not found for trigger setup")
                    return self.async_detach
            
            # Add this trigger to the handler list
            if hasattr(websocket, '_unr_trigger_handlers'):
                websocket._unr_trigger_handlers.append(_handle_websocket_msg)
                
                # Store remove function to unregister this specific trigger
                def remove_this_trigger():
                    if hasattr(websocket, '_unr_trigger_handlers') and _handle_websocket_msg in websocket._unr_trigger_handlers:
                        websocket._unr_trigger_handlers.remove(_handle_websocket_msg)
                        # If no more triggers, restore original handler
                        if not websocket._unr_trigger_handlers and hasattr(websocket, '_unr_original_handler'):
                            websocket._message_handler = websocket._unr_original_handler
                            delattr(websocket, '_unr_original_handler')
                            delattr(websocket, '_unr_trigger_handlers')
                            if LOG_TRIGGERS:
                                LOGGER.info("Restored original websocket handler after removing last trigger")
                
                self.remove_handler = remove_this_trigger
                
                if LOG_TRIGGERS:
                    LOGGER.info("✅ Trigger registered (total triggers: %d)", len(websocket._unr_trigger_handlers))
            else:
                LOGGER.warning("Trigger framework not initialized on websocket")
        else:
            LOGGER.warning("No coordinator or websocket handler found for UniFi trigger setup")

        return self.async_detach

    def _update_rule_cache(self, data: Dict[str, Any]) -> None:
        """Update rule cache from coordinator data."""
        for rule_type, rules in data.items():
            if rule_type in RULE_TYPE_KEYWORDS:
                for rule in rules:
                    if isinstance(rule, dict) and "_id" in rule:
                        self._rule_cache[rule["_id"]] = rule
                    # Handle typed objects with raw attribute
                    elif hasattr(rule, "raw") and isinstance(rule.raw, dict) and "_id" in rule.raw:
                        self._rule_cache[rule.raw["_id"]] = rule.raw

    def _dispatch_coordinator_refresh(self, reason: str) -> None:
        """Dispatch a coordinator refresh when triggers detect changes."""
        if not self._coordinator:
            if LOG_TRIGGERS:
                LOGGER.debug("No coordinator available for refresh dispatch")
            return
            
        try:
            if LOG_TRIGGERS:
                LOGGER.info("🔄 Dispatching coordinator refresh: %s", reason)
            
            # Schedule coordinator refresh
            self.hass.async_create_task(
                self._coordinator.async_refresh()
            )
        except Exception as err:
            LOGGER.error("Error dispatching coordinator refresh: %s", err)

    def async_detach(self) -> None:
        """Detach trigger."""
        if self.remove_handler:
            self.remove_handler()
            self.remove_handler = None