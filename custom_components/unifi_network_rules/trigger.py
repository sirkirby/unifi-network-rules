"""UniFi Network Rules trigger platform."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional
import voluptuous as vol

from homeassistant.const import CONF_TYPE, CONF_PLATFORM
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, LOGGER, LOG_TRIGGERS

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
TRIGGER_DEVICE_CHANGED = "device_changed"

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

# Configuration schema for platform triggers
TRIGGER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PLATFORM): DOMAIN,
        vol.Required(CONF_TYPE): vol.In([
            TRIGGER_RULE_ENABLED,
            TRIGGER_RULE_DISABLED,
            TRIGGER_RULE_CHANGED,
            TRIGGER_RULE_DELETED,
            TRIGGER_DEVICE_CHANGED,
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
        vol.Optional("device_id"): cv.string,  # For device_changed triggers (LED-capable devices only)
        vol.Optional("change_type"): cv.string,  # For device_changed triggers (currently only "led_toggled")
    }
)

# Add trigger type descriptions for better UI display
TRIGGER_TYPE_DESCRIPTIONS = {
    TRIGGER_RULE_ENABLED: "When a UniFi rule is enabled",
    TRIGGER_RULE_DISABLED: "When a UniFi rule is disabled", 
    TRIGGER_RULE_CHANGED: "When a UniFi rule is modified",
    TRIGGER_RULE_DELETED: "When a UniFi rule is deleted",
    TRIGGER_DEVICE_CHANGED: "When a UniFi device LED is changed",
}

def get_rule_name_from_data(rule_data: Dict[str, Any], rule_id: str, rule_type: str = None) -> str:
    """Extract a meaningful rule name from rule data."""
    # Try to get the name field first
    if "name" in rule_data and rule_data["name"]:
        return rule_data["name"]
    
    # Try common alternative name fields
    for name_field in ["description", "label", "title"]:
        if name_field in rule_data and rule_data[name_field]:
            return rule_data[name_field]
    
    # For different rule types, try to construct a meaningful name
    if rule_type == RULE_TYPE_PORT_FORWARD:
        if "dst_port" in rule_data and "fwd" in rule_data:
            return f"Port Forward {rule_data.get('dst_port', '')} → {rule_data.get('fwd', '')}"
        elif "name" not in rule_data:
            return f"Port Forward {rule_id[:8]}"
    
    elif rule_type == RULE_TYPE_FIREWALL_POLICY:
        if "action" in rule_data:
            action = rule_data["action"].upper() if isinstance(rule_data["action"], str) else str(rule_data["action"])
            return f"Firewall {action} Rule {rule_id[:8]}"
    
    elif rule_type == RULE_TYPE_QOS_RULE:
        # QoS rules often have different name fields - try more options
        qos_name_fields = ["name", "description", "label", "title", "target", "app", "category"]
        for field in qos_name_fields:
            if field in rule_data and rule_data[field]:
                return f"QoS Rule: {rule_data[field]}"
        
        # Try to build name from QoS specifics
        if "bandwidth_limit" in rule_data:
            bandwidth = rule_data.get('bandwidth_limit', 'N/A')
            return f"QoS Rule {rule_id[:8]} ({bandwidth})"
        elif "rate_limit" in rule_data:
            rate = rule_data.get('rate_limit', 'N/A')
            return f"QoS Rule {rule_id[:8]} (Rate: {rate})"
        else:
            return f"QoS Rule {rule_id[:8]}"
    
    elif rule_type == RULE_TYPE_WLAN:
        if "ssid" in rule_data:
            return f"WLAN: {rule_data['ssid']}"
    
    # For device configuration changes (cfgversion events), extract device info
    if rule_id.startswith("device_config_"):
        device_part = rule_id.replace("device_config_", "")
        return f"Device Config ({device_part[:8]})"
    
    # Fallback to a generic name with shortened rule ID
    return f"Rule {rule_id[:8] if len(rule_id) > 8 else rule_id}"

# Add function to get available triggers (for device automation style integration)


async def async_validate_trigger_config(hass: HomeAssistant, config: dict) -> dict:
    """Validate trigger configuration."""
    result = TRIGGER_SCHEMA(config)
    LOGGER.debug("🔍 TRIGGER VALIDATION: input=%s, output=%s, type=%s", 
                config, result, type(result))
    return result



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
        LOGGER.info("🔧 SETTING UP TRIGGER: type=%s, rule_type_filter=%s, rule_id_filter=%s, name_filter=%s", 
                   config[CONF_TYPE], config.get("rule_type"), config.get("rule_id"), config.get("name_filter"))
    
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
        # Each trigger instance tracks its own processed cfgversions
        self._processed_cfgversions: set = set()
        # Global coordinator refresh coordination (prevent multiple simultaneous refreshes)
        if not hasattr(UnifiRuleTrigger, '_coordinator_refresh_tasks'):
            UnifiRuleTrigger._coordinator_refresh_tasks = {}
        # Store old rule states for each cfgversion so all trigger instances can access them
        if not hasattr(UnifiRuleTrigger, '_cfgversion_old_states'):
            UnifiRuleTrigger._cfgversion_old_states = {}
        # Global initial state to prevent empty→populated transitions from firing triggers
        if not hasattr(UnifiRuleTrigger, '_global_initial_state_captured'):
            UnifiRuleTrigger._global_initial_state_captured = False
        if not hasattr(UnifiRuleTrigger, '_global_initial_rule_state'):
            UnifiRuleTrigger._global_initial_rule_state = {}

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
            # Enhanced debug logging for all messages (reduced to prevent rate limiting)
            if LOG_TRIGGERS:
                meta = msg.get("meta", {})
                msg_type = meta.get("message", "")
                msg_data = msg.get("data", {})
                
                # Only log detailed info for messages with actual rule data or specific events
                has_rule_data = (isinstance(msg_data, dict) and "_id" in msg_data) or \
                               (isinstance(msg_data, list) and any(isinstance(item, dict) and "_id" in item for item in msg_data))
                
                if has_rule_data:
                    LOGGER.info("🎯 RULE MSG: type=%s, data_type=%s", msg_type, type(msg_data))
                    if isinstance(msg_data, list) and len(msg_data) > 0:
                        first_item = msg_data[0] if msg_data else {}
                        LOGGER.info("📋 RULE DATA: count=%d, first_item_keys=%s", 
                                   len(msg_data),
                                   list(first_item.keys()) if isinstance(first_item, dict) else "not_dict")
                    elif isinstance(msg_data, dict):
                        LOGGER.info("📋 RULE DATA: keys=%s", list(msg_data.keys()))
                    LOGGER.info("📄 RULE CONTENT: %s", str(msg)[:300] + "..." if len(str(msg)) > 300 else str(msg))
                elif msg_type == "device:update" and isinstance(msg_data, list):
                    # Very limited logging for device updates to avoid spam
                    first_item = msg_data[0] if msg_data else {}
                    if isinstance(first_item, dict) and "cfgversion" in first_item:
                        LOGGER.debug("📱 CFGVERSION UPDATE: %s", first_item.get("cfgversion"))
            try:
                # Extract message type and data from UniFi OS websocket structure
                meta = msg.get("meta", {})
                msg_type = meta.get("message", "")
                msg_data = msg.get("data", {})
                
                if not msg_type or not msg_data:
                    if LOG_TRIGGERS:
                        LOGGER.debug("❌ SKIP: No msg_type (%s) or msg_data (%s)", msg_type, bool(msg_data))
                    return

                # Determine rule type based on message content and keywords
                detected_rule_type = None
                rule_data = None

                # FIXED: Check for actual rule data FIRST (more specific than cfgversion)
                if isinstance(msg_data, dict) and "_id" in msg_data:
                    rule_data = msg_data
                elif isinstance(msg_data, list) and len(msg_data) > 0:
                    # Take the first item that has an _id
                    for item in msg_data:
                        if isinstance(item, dict) and "_id" in item:
                            rule_data = item
                            break

                # Check for cfgversion changes (but only refresh if we have active rule triggers)
                has_cfgversion_change = False
                cfgversion = None
                if msg_type == "device:update" and isinstance(msg_data, list):
                    for item in msg_data:
                        if isinstance(item, dict) and "cfgversion" in item:
                            cfgversion = item.get("cfgversion")
                            # Check if this trigger instance has already processed this cfgversion
                            if cfgversion not in getattr(self, '_processed_cfgversions', set()):
                                has_cfgversion_change = True
                                # Track processed cfgversions per trigger instance
                                if not hasattr(self, '_processed_cfgversions'):
                                    self._processed_cfgversions = set()
                                self._processed_cfgversions.add(cfgversion)
                                # Keep only recent cfgversions (limit memory usage)
                                if len(self._processed_cfgversions) > 50:
                                    self._processed_cfgversions = set(list(self._processed_cfgversions)[-25:])
                                
                                if LOG_TRIGGERS:
                                    LOGGER.info("🔄 CFGVERSION CHANGE DETECTED: %s - Will check for rule changes (trigger: %s)", cfgversion, self.config[CONF_TYPE])
                                break  # Only process one cfgversion per message

                # If we found actual rule data, process it (preferred path)
                if rule_data:
                    if LOG_TRIGGERS:
                        LOGGER.info("🎯 PROCESSING ACTUAL RULE DATA: rule_id=%s, rule_data_keys=%s", 
                                   rule_data.get("_id"), list(rule_data.keys()))
                else:
                    # SIMPLIFIED STATE-DIFF APPROACH: Always refresh and trigger for cfgversion changes
                    if has_cfgversion_change:
                        if LOG_TRIGGERS:
                            LOGGER.info("🧠 SIMPLE PROCESSING: cfgversion change detected, refreshing coordinator and checking for triggers")
                        
                        # Schedule state-diff check to run after current message processing  
                        self.hass.async_create_task(
                            self._check_rule_changes_and_trigger(cfgversion, meta.get("mac", "unknown"))
                        )
                        return
                    
                    # No rule data and no cfgversion - nothing to process
                    if LOG_TRIGGERS:
                        LOGGER.debug("❌ NO RULE DATA: No _id found and no cfgversion, skipping")
                    return

                # FIXED: Detect rule type using data structure FIRST (more reliable)
                detected_rule_type = None
                
                # Primary detection: Check rule data fields (most reliable)
                if "dst_port" in rule_data or "fwd_port" in rule_data or "fwd" in rule_data:
                    detected_rule_type = RULE_TYPE_PORT_FORWARD
                elif "purpose" in rule_data:
                    purpose = rule_data.get("purpose", "").lower()
                    if "vpn-client" in purpose:
                        detected_rule_type = RULE_TYPE_VPN_CLIENT
                    elif "vpn-server" in purpose:
                        detected_rule_type = RULE_TYPE_VPN_SERVER
                elif "objective" in rule_data or "bandwidth_limit" in rule_data or "rate_limit" in rule_data:
                    detected_rule_type = RULE_TYPE_QOS_RULE
                elif "action" in rule_data and "ruleset" in rule_data:
                    detected_rule_type = RULE_TYPE_FIREWALL_POLICY
                elif "next_hop" in rule_data or "gateway" in rule_data:
                    detected_rule_type = RULE_TYPE_TRAFFIC_ROUTE
                elif "ssid" in rule_data:
                    detected_rule_type = RULE_TYPE_WLAN
                
                # Fallback: Keyword matching with SPECIFIC order (most specific first)
                if not detected_rule_type:
                    message_str = str(msg).lower()
                    rule_data_str = str(rule_data).lower()
                    
                    # Check most specific keywords first
                    if any(keyword in rule_data_str for keyword in ["dst_port", "fwd_port", "port_forward"]):
                        detected_rule_type = RULE_TYPE_PORT_FORWARD
                    elif any(keyword in rule_data_str for keyword in ["objective", "bandwidth", "rate_limit"]):
                        detected_rule_type = RULE_TYPE_QOS_RULE
                    elif any(keyword in rule_data_str for keyword in ["vpn-client", "openvpn-client"]):
                        detected_rule_type = RULE_TYPE_VPN_CLIENT
                    elif any(keyword in rule_data_str for keyword in ["vpn-server", "openvpn-server"]):
                        detected_rule_type = RULE_TYPE_VPN_SERVER
                    elif any(keyword in rule_data_str for keyword in ["firewall", "ruleset"]):
                        detected_rule_type = RULE_TYPE_FIREWALL_POLICY
                    elif any(keyword in rule_data_str for keyword in ["route", "gateway"]):
                        detected_rule_type = RULE_TYPE_TRAFFIC_ROUTE
                    elif any(keyword in rule_data_str for keyword in ["wlan", "ssid"]):
                        detected_rule_type = RULE_TYPE_WLAN

                if not detected_rule_type:
                    if LOG_TRIGGERS:
                        LOGGER.debug("Trigger: Could not detect rule type for message, skipping")
                    return

                if LOG_TRIGGERS:
                    LOGGER.info("🎯 TRIGGER DETECTION: rule_id=%s, detected_type=%s, trigger_config=%s", 
                               rule_data.get("_id"), detected_rule_type, self.config[CONF_TYPE])

                # Apply filters with detailed logging
                if "rule_type" in event_filter and event_filter["rule_type"] != detected_rule_type:
                    if LOG_TRIGGERS:
                        LOGGER.info("❌ FILTER BLOCKED: rule_type filter %s != detected %s", 
                                   event_filter["rule_type"], detected_rule_type)
                    return
                if "rule_id" in event_filter and event_filter["rule_id"] != rule_data["_id"]:
                    if LOG_TRIGGERS:
                        LOGGER.info("❌ FILTER BLOCKED: rule_id filter %s != actual %s", 
                                   event_filter["rule_id"], rule_data["_id"])
                    return
                if name_filter:
                    rule_name = rule_data.get("name", "")
                    if not rule_name or name_filter.lower() not in rule_name.lower():
                        if LOG_TRIGGERS:
                            LOGGER.info("❌ FILTER BLOCKED: name filter '%s' not in '%s'", name_filter, rule_name)
                        return

                # Get previous state from cache
                rule_id = rule_data["_id"]
                old_state = self._rule_cache.get(rule_id)
                
                # Handle different trigger types with enhanced logic
                trigger_type = self.config[CONF_TYPE]
                should_trigger = False

                if trigger_type in [TRIGGER_RULE_ENABLED, TRIGGER_RULE_DISABLED]:
                    old_enabled = old_state.get("enabled", False) if old_state else False
                    new_enabled = rule_data.get("enabled", False)
                    
                    if LOG_TRIGGERS:
                        LOGGER.info("🔄 ENABLED CHECK: old=%s, new=%s, trigger_type=%s", 
                                   old_enabled, new_enabled, trigger_type)
                    
                    if old_enabled != new_enabled:
                        should_trigger = (
                            (trigger_type == TRIGGER_RULE_ENABLED and new_enabled) or
                            (trigger_type == TRIGGER_RULE_DISABLED and not new_enabled)
                        )
                        if LOG_TRIGGERS:
                            LOGGER.info("✅ ENABLED TRIGGER: should_trigger=%s", should_trigger)

                elif trigger_type == TRIGGER_RULE_CHANGED:
                    if old_state is not None:
                        # FIXED: Include enabled field in change detection
                        old_copy = {k: v for k, v in old_state.items() 
                                  if not k.startswith('_')}  # Keep enabled field!
                        new_copy = {k: v for k, v in rule_data.items() 
                                  if not k.startswith('_')}  # Keep enabled field!
                        should_trigger = old_copy != new_copy
                        
                        if LOG_TRIGGERS:
                            LOGGER.info("🔄 CHANGE CHECK: old_state_exists=%s, should_trigger=%s", 
                                       True, should_trigger)
                            if should_trigger:
                                # Show what changed
                                changed_fields = []
                                for key in set(old_copy.keys()) | set(new_copy.keys()):
                                    if old_copy.get(key) != new_copy.get(key):
                                        changed_fields.append(f"{key}: {old_copy.get(key)} → {new_copy.get(key)}")
                                LOGGER.info("📝 CHANGED FIELDS: %s", ", ".join(changed_fields))
                    else:
                        # New rule detected
                        should_trigger = True
                        if LOG_TRIGGERS:
                            LOGGER.info("✅ NEW RULE DETECTED: should_trigger=%s", should_trigger)

                elif trigger_type == TRIGGER_RULE_DELETED:
                    if old_state is not None and meta.get('deleted'):
                        should_trigger = True
                        # Remove from cache
                        self._rule_cache.pop(rule_id, None)
                        if LOG_TRIGGERS:
                            LOGGER.info("🗑️ DELETE TRIGGER: should_trigger=%s", should_trigger)

                # Update cache unless deleted
                if trigger_type != TRIGGER_RULE_DELETED:
                    self._rule_cache[rule_id] = rule_data

                # Trigger action if conditions met
                if should_trigger:
                    # Extract rule name using helper function
                    rule_name = get_rule_name_from_data(rule_data, rule_id, detected_rule_type)
                    
                    # Debug logging for ALL rule types to understand the data structure
                    if LOG_TRIGGERS:
                        LOGGER.info("🏷️ RULE NAME EXTRACTION: rule_id=%s, detected_type=%s, extracted_name='%s'", 
                                   rule_id, detected_rule_type, rule_name)
                        LOGGER.info("📊 RULE DATA FIELDS: %s", 
                                   {k: v for k, v in rule_data.items() if k in ['name', 'description', 'label', 'title', 'dst_port', 'fwd_port', 'fwd', 'enabled']})
                    
                    data = {
                        "rule_id": rule_id,
                        "rule_name": rule_name,
                        "rule_type": detected_rule_type,
                        "old_state": old_state,
                        "new_state": rule_data if trigger_type != TRIGGER_RULE_DELETED else None,
                        "trigger_type": trigger_type
                    }
                    if LOG_TRIGGERS:
                        LOGGER.info("🔥 TRIGGER FIRING: %s for rule %s (%s) - '%s'", trigger_type, rule_id, detected_rule_type, rule_name)
                    try:
                        trigger_vars = {
                            "platform": DOMAIN,
                            "type": trigger_type,
                            "event": data  # Nest the data under 'event' key
                        }
                        if LOG_TRIGGERS:
                            LOGGER.info("Calling action with trigger vars: %s", trigger_vars)
                        # Schedule the action execution
                        result = self.action({"trigger": trigger_vars})
                        if asyncio.iscoroutine(result):
                            self.hass.async_create_task(result)
                        
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
                    
                    # Capture global initial state ONCE to prevent empty→populated false triggers
                    if not UnifiRuleTrigger._global_initial_state_captured:
                        UnifiRuleTrigger._global_initial_rule_state = self._capture_rule_state(coordinator.data)
                        UnifiRuleTrigger._global_initial_state_captured = True
                        if LOG_TRIGGERS:
                            total_rules = sum(len(rules) for rules in UnifiRuleTrigger._global_initial_rule_state.values())
                            LOGGER.info("🌍 GLOBAL INITIAL STATE CAPTURED: %d rules across %d types", 
                                       total_rules, len(UnifiRuleTrigger._global_initial_rule_state))

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
                
                # Register device trigger listener if this is a device_changed trigger
                device_trigger_unsubscribe = None
                if self.config[CONF_TYPE] == TRIGGER_DEVICE_CHANGED:
                    # Listen for device triggers via Home Assistant's dispatcher
                    entry_id = coordinator.config_entry.entry_id if coordinator.config_entry else "unknown"
                    signal_name = f"{DOMAIN}_device_trigger_{entry_id}"
                    
                    device_trigger_unsubscribe = async_dispatcher_connect(
                        self.hass,
                        signal_name,
                        self._handle_device_trigger
                    )
                    
                    if LOG_TRIGGERS:
                        LOGGER.info("✅ Registered device trigger listener for signal: %s", signal_name)
                
                # Store remove function to unregister this specific trigger
                def remove_this_trigger():
                    if hasattr(websocket, '_unr_trigger_handlers') and _handle_websocket_msg in websocket._unr_trigger_handlers:
                        websocket._unr_trigger_handlers.remove(_handle_websocket_msg)
                        
                        # Unregister device trigger listener if applicable
                        if device_trigger_unsubscribe:
                            device_trigger_unsubscribe()
                            if LOG_TRIGGERS:
                                LOGGER.info("✅ Unregistered device trigger listener")
                        
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

    def _capture_rule_state(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Capture current rule state for comparison."""
        rule_state = {}
        for rule_type, rules in data.items():
            if rule_type in RULE_TYPE_KEYWORDS:
                rule_state[rule_type] = {}
                for rule in rules:
                    if isinstance(rule, dict) and "_id" in rule:
                        rule_state[rule_type][rule["_id"]] = rule.copy()
                    elif hasattr(rule, "raw") and isinstance(rule.raw, dict) and "_id" in rule.raw:
                        rule_state[rule_type][rule.raw["_id"]] = rule.raw.copy()
        return rule_state

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

    async def _check_rule_changes_and_trigger(self, cfgversion: str, device_mac: str) -> None:
        """Simplified state-diff approach: Check for actual rule changes and fire appropriate triggers."""
        # --- CQRS Check ---
        # Before we refresh, we'll check if this cfgversion change was likely caused by
        # an operation we initiated. We pass this flag down to the detection logic.
        ha_operations_pending = hasattr(self._coordinator, "_ha_initiated_operations") and self._coordinator._ha_initiated_operations
        if ha_operations_pending:
            LOGGER.debug("[CQRS] State-diff check initiated while HA operations are pending.")

        if not self._coordinator:
            if LOG_TRIGGERS:
                LOGGER.debug("No coordinator available for state-diff check")
            return
            
        try:
            # Coordinate coordinator refresh across all trigger instances for this cfgversion
            refresh_task = None
            
            # Check if a refresh is already in progress for this cfgversion
            if cfgversion in UnifiRuleTrigger._coordinator_refresh_tasks:
                refresh_task = UnifiRuleTrigger._coordinator_refresh_tasks[cfgversion]
                if LOG_TRIGGERS:
                    LOGGER.info("🔄 COORDINATOR REFRESH: Waiting for existing refresh of cfgversion %s (trigger: %s)", cfgversion, self.config[CONF_TYPE])
            else:
                # This trigger instance will handle the coordinator refresh
                if LOG_TRIGGERS:
                    LOGGER.info("🔄 COORDINATOR REFRESH: Starting refresh for cfgversion %s (trigger: %s)", cfgversion, self.config[CONF_TYPE])
                
                # Use current coordinator state as old_rules_state 
                old_rules_state = {}
                if self._coordinator.data:
                    if LOG_TRIGGERS:
                        LOGGER.info("🔍 COORDINATOR DATA KEYS: %s", list(self._coordinator.data.keys())) 
                    old_rules_state = self._capture_rule_state(self._coordinator.data)
                    if LOG_TRIGGERS:
                        total_rules = sum(len(rules) for rules in old_rules_state.values())
                        LOGGER.info("📊 CAPTURED CURRENT STATE: %d rules across %d types", total_rules, len(old_rules_state))
                
                # Store old state for all trigger instances to access
                UnifiRuleTrigger._cfgversion_old_states[cfgversion] = old_rules_state
                
                # Create and start the refresh task
                async def _do_coordinator_refresh():
                    # Always perform coordinator refresh for consistency
                    await self._coordinator.async_refresh()
                    # Wait a bit for API calls to complete
                    await asyncio.sleep(0.5)
                    return old_rules_state
                
                refresh_task = self.hass.async_create_task(_do_coordinator_refresh())
                UnifiRuleTrigger._coordinator_refresh_tasks[cfgversion] = refresh_task
            
            # Wait for the coordinator refresh to complete and get the old state
            await refresh_task
            old_rules_state = UnifiRuleTrigger._cfgversion_old_states.get(cfgversion, {})
            
            # CRITICAL FIX: If no cfgversion-specific old state exists, wait a bit for other triggers to complete
            # then skip processing to avoid false triggers from stale state comparisons
            if not old_rules_state:
                if LOG_TRIGGERS:
                    LOGGER.info("⚠️  NO CFGVERSION STATE: Old state not available, skipping to avoid false triggers (trigger: %s)", self.config[CONF_TYPE])
                return  # Skip processing this cfgversion for this trigger to avoid false triggers
            
            if LOG_TRIGGERS:
                LOGGER.info("✅ Coordinator refresh completed, comparing states... (trigger: %s)", self.config[CONF_TYPE])
            
            # Compare new state with old state to detect actual changes
            new_rules_state = {}
            if self._coordinator.data:
                new_rules_state = self._capture_rule_state(self._coordinator.data)
                if LOG_TRIGGERS:
                    for rule_type in new_rules_state:
                        LOGGER.info("🔍 AFTER REFRESH - RULE TYPE: %s with %d rules (trigger: %s)", rule_type, len(new_rules_state[rule_type]), self.config[CONF_TYPE])
                
                # Log comparison summary
                if LOG_TRIGGERS:
                    for rule_type in set(old_rules_state.keys()) | set(new_rules_state.keys()):
                        old_count = len(old_rules_state.get(rule_type, {}))
                        new_count = len(new_rules_state.get(rule_type, {}))
                        if old_count != new_count:
                            LOGGER.info("📊 COUNT CHANGE: %s rules: %d → %d (trigger: %s)", rule_type, old_count, new_count, self.config[CONF_TYPE])
                        else:
                            LOGGER.debug("📊 COUNT SAME: %s rules: %d (trigger: %s)", rule_type, old_count, self.config[CONF_TYPE])
            
            # Detect actual changes and fire appropriate triggers for THIS trigger instance
            changes_detected = await self._detect_and_fire_rule_changes(old_rules_state, new_rules_state, cfgversion, device_mac, ha_operations_pending)
            
            if LOG_TRIGGERS:
                if changes_detected:
                    LOGGER.info("🎯 STATE-DIFF COMPLETE: Rule changes detected and appropriate triggers fired (trigger: %s)", self.config[CONF_TYPE])
                else:
                    LOGGER.info("📭 STATE-DIFF COMPLETE: No rule changes detected (cfgversion was likely non-rule related) (trigger: %s)", self.config[CONF_TYPE])
                    
        except Exception as err:
            LOGGER.error("Error in state-diff check (trigger: %s): %s", self.config[CONF_TYPE], err)
        finally:
            # Clean up the refresh task but KEEP old state data for other trigger instances
            if cfgversion in UnifiRuleTrigger._coordinator_refresh_tasks:
                task = UnifiRuleTrigger._coordinator_refresh_tasks[cfgversion]
                if task.done():
                    del UnifiRuleTrigger._coordinator_refresh_tasks[cfgversion]
                    
                    # Schedule cleanup of old state data after a delay to allow other triggers to access it
                    async def cleanup_old_state():
                        await asyncio.sleep(2.0)  # Give other triggers time to complete
                        if cfgversion in UnifiRuleTrigger._cfgversion_old_states:
                            del UnifiRuleTrigger._cfgversion_old_states[cfgversion]
                            if LOG_TRIGGERS:
                                LOGGER.debug("🗑️ Cleaned up old state data for cfgversion %s", cfgversion)
                    
                    # Don't await this - let it run in background
                    self.hass.async_create_task(cleanup_old_state())

    async def _detect_and_fire_rule_changes(self, old_state: Dict, new_state: Dict, cfgversion: str, device_mac: str, ha_initiated: bool) -> bool:
        """Detect specific rule changes and fire appropriate triggers with accurate data."""
        changes_detected = False
        
        try:
            # Check all rule types for changes
            all_rule_types = set(old_state.keys()) | set(new_state.keys())
            
            for rule_type in all_rule_types:
                old_rules = old_state.get(rule_type, {})
                new_rules = new_state.get(rule_type, {})
                
                # Check for deleted rules
                for rule_id in old_rules:
                    if rule_id not in new_rules:
                        changes_detected = True
                        await self._handle_potential_trigger(
                            expected_trigger_type=TRIGGER_RULE_DELETED,
                            rule_id=rule_id,
                            rule_type=rule_type,
                            rule_data_for_filter=old_rules[rule_id],
                            old_state=old_rules[rule_id],
                            new_state=None,
                            cqrs_log_message="DELETION"
                        )
                
                # Check for new rules  
                for rule_id in new_rules:
                    if rule_id not in old_rules:
                        changes_detected = True
                        await self._handle_potential_trigger(
                            expected_trigger_type=TRIGGER_RULE_CHANGED,
                            rule_id=rule_id,
                            rule_type=rule_type,
                            rule_data_for_filter=new_rules[rule_id],
                            old_state=None,
                            new_state=new_rules[rule_id],
                            cqrs_log_message="NEW RULE"
                        )
                
                # Check for modified rules
                for rule_id in old_rules:
                    if rule_id in new_rules:
                        old_rule = old_rules[rule_id]
                        new_rule = new_rules[rule_id]
                        
                        # Check for enabled/disabled changes
                        new_enabled = new_rule.get("enabled", False)
                        
                        # Check for ANY changes first (including enabled field)
                        old_copy = {k: v for k, v in old_rule.items() if not k.startswith('_')}
                        new_copy = {k: v for k, v in new_rule.items() if not k.startswith('_')}
                        
                        rule_has_changes = old_copy != new_copy
                        enabled_changed = old_rule.get("enabled", False) != new_rule.get("enabled", False)
                        
                        if enabled_changed:
                            changes_detected = True
                            trigger_type = TRIGGER_RULE_ENABLED if new_enabled else TRIGGER_RULE_DISABLED
                            await self._handle_potential_trigger(
                                expected_trigger_type=trigger_type,
                                rule_id=rule_id,
                                rule_type=rule_type,
                                rule_data_for_filter=new_rule,
                                old_state=old_rule,
                                new_state=new_rule,
                                cqrs_log_message="ENABLE/DISABLE"
                            )

                        if rule_has_changes:
                            changes_detected = True
                            await self._handle_potential_trigger(
                                expected_trigger_type=TRIGGER_RULE_CHANGED,
                                rule_id=rule_id,
                                rule_type=rule_type,

                                rule_data_for_filter=new_rule,
                                old_state=old_rule,
                                new_state=new_rule,
                                cqrs_log_message="CHANGE"
                            )
            
            return changes_detected
            
        except Exception as err:
            LOGGER.error("Error detecting rule changes: %s", err)
            return False

    async def _handle_potential_trigger(self, expected_trigger_type: str, rule_id: str, rule_type: str, rule_data_for_filter: Dict, old_state: Optional[Dict], new_state: Optional[Dict], cqrs_log_message: str) -> None:
        """DRY helper to check filters and fire a trigger if conditions are met."""
        # Only proceed if this trigger instance is configured for this type of event
        if self.config[CONF_TYPE] != expected_trigger_type:
            return

        # --- CQRS Check ---
        is_ha_change = self._coordinator.check_and_consume_ha_initiated_operation(rule_id)
        if is_ha_change:
            LOGGER.debug("[CQRS] HA-initiated %s detected for %s. Firing trigger, but refresh was already suppressed.", cqrs_log_message, rule_id)
        
        # --- Filter and Fire ---
        if self._matches_filters(rule_type, rule_id, rule_data_for_filter):
            # Log specific changes for better debugging
            if LOG_TRIGGERS:
                if expected_trigger_type == TRIGGER_RULE_DELETED:
                    LOGGER.info("🗑️ FIRING DELETION: %s rule %s", rule_type, rule_id)
                elif expected_trigger_type == TRIGGER_RULE_CHANGED and old_state is None:
                    LOGGER.info("🆕 FIRING NEW RULE: %s rule %s", rule_type, rule_id)
                elif expected_trigger_type in [TRIGGER_RULE_ENABLED, TRIGGER_RULE_DISABLED]:
                    LOGGER.info("🔄 FIRING ENABLE/DISABLE: %s rule %s (%s → %s)",
                                rule_type, rule_id, old_state.get("enabled", "N/A"), new_state.get("enabled", "N/A"))
                elif expected_trigger_type == TRIGGER_RULE_CHANGED:
                    changed_fields = []
                    old_copy = {k: v for k, v in old_state.items() if not k.startswith('_')}
                    new_copy = {k: v for k, v in new_state.items() if not k.startswith('_')}
                    for key in set(old_copy.keys()) | set(new_copy.keys()):
                        if old_copy.get(key) != new_copy.get(key):
                            changed_fields.append(f"{key}: {old_copy.get(key)} → {new_copy.get(key)}")
                    LOGGER.info("📝 FIRING CHANGE: %s rule %s modified (%s)", 
                                rule_type, rule_id, ", ".join(changed_fields[:3]) + ("..." if len(changed_fields) > 3 else ""))

            await self._fire_trigger(expected_trigger_type, rule_id, rule_type, rule_data_for_filter, old_state, new_state)

    def _matches_filters(self, rule_type: str, rule_id: str, rule_data: Dict) -> bool:
        """Check if rule matches the trigger's filters."""
        # Check rule_type filter
        if "rule_type" in self.config and self.config["rule_type"] != rule_type:
            return False
            
        # Check rule_id filter
        if "rule_id" in self.config and self.config["rule_id"] != rule_id:
            return False
            
        # Check name filter
        if "name_filter" in self.config:
            name_filter = self.config["name_filter"]
            rule_name = rule_data.get("name", "")
            if not rule_name or name_filter.lower() not in rule_name.lower():
                return False
        
        return True

    async def _fire_trigger(self, trigger_type: str, rule_id: str, rule_type: str, rule_data: Dict, old_state: Dict, new_state: Dict) -> None:
        """Fire a trigger with accurate rule information."""
        try:
            # Extract rule name using helper function
            rule_name = get_rule_name_from_data(rule_data, rule_id, rule_type)
            
            data = {
                "rule_id": rule_id,
                "rule_name": rule_name,
                "rule_type": rule_type,
                "old_state": old_state,
                "new_state": new_state,
                "trigger_type": trigger_type
            }
            
            if LOG_TRIGGERS:
                LOGGER.info("🔥 ACCURATE TRIGGER FIRING: %s for %s rule %s - '%s'", 
                           trigger_type, rule_type, rule_id, rule_name)
            
            trigger_vars = {
                "platform": DOMAIN,
                "type": trigger_type,
                "event": data
            }
            
            # Schedule the action execution
            result = self.action({"trigger": trigger_vars})
            if asyncio.iscoroutine(result):
                await result
            
        except Exception as err:
            LOGGER.error("Error firing trigger: %s", err)

    async def fire_device_trigger(self, device_id: str, device_name: str, change_type: str, old_state: Any = None, new_state: Any = None) -> None:
        """Fire a device_changed trigger manually (not from websocket)."""
        # Only proceed if this trigger instance is configured for device_changed events
        if self.config[CONF_TYPE] != TRIGGER_DEVICE_CHANGED:
            return

        # Apply device-specific filters
        if "device_id" in self.config and self.config["device_id"] != device_id:
            if LOG_TRIGGERS:
                LOGGER.info("❌ DEVICE FILTER BLOCKED: device_id filter %s != actual %s", 
                           self.config["device_id"], device_id)
            return
            
        if "change_type" in self.config and self.config["change_type"] != change_type:
            if LOG_TRIGGERS:
                LOGGER.info("❌ DEVICE FILTER BLOCKED: change_type filter %s != actual %s", 
                           self.config["change_type"], change_type)
            return

        try:
            data = {
                "device_id": device_id,
                "device_name": device_name,
                "change_type": change_type,
                "old_state": old_state,
                "new_state": new_state,
                "trigger_type": TRIGGER_DEVICE_CHANGED
            }
            
            if LOG_TRIGGERS:
                LOGGER.info("🔥 DEVICE TRIGGER FIRING: %s for device %s (%s) - '%s'", 
                           TRIGGER_DEVICE_CHANGED, device_id, change_type, device_name)
            
            trigger_vars = {
                "platform": DOMAIN,
                "type": TRIGGER_DEVICE_CHANGED,
                "event": data
            }
            
            # Schedule the action execution
            result = self.action({"trigger": trigger_vars})
            if asyncio.iscoroutine(result):
                await result
            
        except Exception as err:
            LOGGER.error("Error firing device trigger: %s", err)

    @callback
    def _handle_device_trigger(self, trigger_data: Dict[str, Any]) -> None:
        """Handle device trigger dispatched via Home Assistant's dispatcher system."""
        try:
            device_id = trigger_data.get("device_id")
            device_name = trigger_data.get("device_name")
            change_type = trigger_data.get("change_type")
            old_state = trigger_data.get("old_state")
            new_state = trigger_data.get("new_state")
            
            if LOG_TRIGGERS:
                LOGGER.info("🎯 DEVICE TRIGGER RECEIVED: %s (%s) - %s: %s → %s", 
                           device_name, device_id, change_type, old_state, new_state)
            
            # Apply device-specific filters
            if "device_id" in self.config and self.config["device_id"] != device_id:
                if LOG_TRIGGERS:
                    LOGGER.info("❌ DEVICE FILTER BLOCKED: device_id filter %s != actual %s", 
                               self.config["device_id"], device_id)
                return
                
            if "change_type" in self.config and self.config["change_type"] != change_type:
                if LOG_TRIGGERS:
                    LOGGER.info("❌ DEVICE FILTER BLOCKED: change_type filter %s != actual %s", 
                               self.config["change_type"], change_type)
                return

            # Fire the trigger action
            trigger_vars = {
                "platform": DOMAIN,
                "type": TRIGGER_DEVICE_CHANGED,
                "event": trigger_data
            }
            
            if LOG_TRIGGERS:
                LOGGER.info("🔥 DEVICE TRIGGER FIRING: %s for device %s (%s) - '%s'", 
                           TRIGGER_DEVICE_CHANGED, device_id, change_type, device_name)
            
            # Schedule the action execution
            result = self.action({"trigger": trigger_vars})
            if asyncio.iscoroutine(result):
                self.hass.async_create_task(result)
                
        except Exception as err:
            LOGGER.error("Error handling device trigger: %s", err)

    def async_detach(self) -> None:
        """Detach trigger."""
        if self.remove_handler:
            self.remove_handler()
            self.remove_handler = None
            
        if LOG_TRIGGERS:
            LOGGER.info("🧹 TRIGGER DETACHED: %s", self.config[CONF_TYPE])