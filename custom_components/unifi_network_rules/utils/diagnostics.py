"""Diagnostics module for UniFi Network Rules."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from copy import deepcopy

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import LOGGER, DOMAIN

# Regular expressions for detecting token-like strings
HEX_TOKEN_PATTERN = re.compile(r'^[0-9a-fA-F]{32,}$')
ALNUM_TOKEN_PATTERN = re.compile(r'^[a-zA-Z0-9]{32,}$')

def sanitize_sensitive_data(data: Any) -> Any:
    """Sanitize sensitive data for diagnostics.
    
    Auto-masks passwords, tokens, keys, and other sensitive fields.
    """
    if data is None:
        return None
    
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            key_lower = key.lower()
            # List of sensitive field patterns
            if any(pattern in key_lower for pattern in [
                'password', 'token', 'key', 'secret', 'auth', 'credential',
                'pass', 'pwd', 'psk', 'private', 'cert', 'signature'
            ]):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = sanitize_sensitive_data(value)
        return sanitized
    
    elif isinstance(data, list):
        return [sanitize_sensitive_data(item) for item in data]
    
    elif isinstance(data, str) and len(data) > 20:
        # Check if string looks like a token or key (long alphanumeric strings)
        if HEX_TOKEN_PATTERN.match(data) or ALNUM_TOKEN_PATTERN.match(data):
            return "***REDACTED***"
    
    return data


def get_coordinator_stats(coordinator) -> Dict[str, Any]:
    """Get comprehensive coordinator statistics for diagnostics."""
    if not coordinator:
        return {"error": "Coordinator not found"}
    
    stats = {
        "update_interval": str(getattr(coordinator, "update_interval", "unknown")),
        "last_update_success": str(getattr(coordinator, "last_update_success", "unknown")),
        "last_exception": str(getattr(coordinator, "last_exception", None)),
        "available": getattr(coordinator, "available", False),
        "data_size": len(getattr(coordinator, "data", {})),
    }
    
    # Add custom coordinator stats
    if hasattr(coordinator, '_consecutive_errors'):
        stats["consecutive_errors"] = coordinator._consecutive_errors
    
    if hasattr(coordinator, '_authentication_in_progress'):
        stats["authentication_in_progress"] = coordinator._authentication_in_progress
    
    if hasattr(coordinator, '_has_data'):
        stats["has_data"] = coordinator._has_data
    
    if hasattr(coordinator, '_initial_update_done'):
        stats["initial_update_done"] = coordinator._initial_update_done
    
    if hasattr(coordinator, '_api_errors'):
        stats["api_errors"] = coordinator._api_errors
    
    if hasattr(coordinator, '_in_error_state'):
        stats["in_error_state"] = coordinator._in_error_state
    
    # WebSocket stats
    if hasattr(coordinator, 'websocket'):
        websocket = coordinator.websocket
        stats["websocket"] = {
            "available": websocket is not None,
            "active": getattr(websocket, '_active', False) if websocket else False,
            "last_message": str(getattr(websocket, '_last_message_time', "unknown")) if websocket else "N/A",
        }
    
    # Rule collection sizes
    if hasattr(coordinator, 'data') and coordinator.data:
        data = coordinator.data
        stats["rule_counts"] = {
            "port_forwards": len(data.get("port_forwards", [])),
            "traffic_routes": len(data.get("traffic_routes", [])),
            "firewall_policies": len(data.get("firewall_policies", [])),
            "traffic_rules": len(data.get("traffic_rules", [])),
            "legacy_firewall_rules": len(data.get("legacy_firewall_rules", [])),
            "wlans": len(data.get("wlans", [])),
            "qos_rules": len(data.get("qos_rules", [])),
            "vpn_clients": len(data.get("vpn_clients", [])),
            "devices": len(data.get("devices", [])),
        }
    
    return stats


def get_recent_websocket_events(coordinator, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent WebSocket events for diagnostics."""
    events = []
    
    if not coordinator or not hasattr(coordinator, 'websocket'):
        return events
    
    websocket = coordinator.websocket
    if not websocket or not hasattr(websocket, '_recent_messages'):
        return events
    
    # Get recent messages (if the websocket tracks them)
    recent_messages = getattr(websocket, '_recent_messages', [])
    
    # Format recent messages for diagnostics
    for msg in recent_messages[-limit:]:
        if isinstance(msg, dict):
            # Sanitize the message data
            sanitized_msg = sanitize_sensitive_data(msg)
            events.append({
                "timestamp": sanitized_msg.get("timestamp", "unknown"),
                "type": sanitized_msg.get("type", "unknown"),
                "data": sanitized_msg.get("data", {}),
            })
    
    return events
def analyze_controller(controller: Any) -> Dict[str, Any]:
    """Analyze controller object structure for diagnostics.
    
    Returns a focused subset of controller information relevant for troubleshooting.
    """
    if controller is None:
        return {"status": "error", "message": "Controller is None"}
        
    result = {
        "class": controller.__class__.__name__,
        "websocket": {
            "available": False,
            "connected": False,
            "url": None
        },
        "connectivity": {
            "is_unifi_os": None
        },
        "capabilities": []
    }
    
    # Check for websocket capability
    if hasattr(controller, "websocket"):
        ws = getattr(controller, "websocket")
        result["websocket"]["available"] = True
        
        # Only include most important websocket properties
        if hasattr(ws, "url"):
            result["websocket"]["url"] = ws.url
        
        # Check websocket connection state without doing deep inspection
        if hasattr(ws, "state") and getattr(ws, "state", None) is not None:
            result["websocket"]["connected"] = True
    
    # Check for method capabilities in a simplified way
    capabilities = []
    for method in ["start_websocket", "stop_websocket"]:
        if hasattr(controller, method) and callable(getattr(controller, method)):
            capabilities.append(method)
    result["capabilities"] = capabilities
    
    # Check UniFi OS detection
    if hasattr(controller, "is_unifi_os"):
        result["connectivity"]["is_unifi_os"] = getattr(controller, "is_unifi_os")
    
    return result

def log_controller_diagnostics(controller: Any, api_instance: Any = None) -> None:
    """Log focused diagnostic information about the controller structure.
    
    Logs only the most relevant information for troubleshooting.
    """
    try:
        LOGGER.info("=== UNIFI NETWORK RULES DIAGNOSTICS SUMMARY ===")
        
        if controller is None:
            LOGGER.info("Controller is None - unable to connect to UniFi Network")
            return
            
        analysis = analyze_controller(controller)
        LOGGER.info("Controller type: %s", analysis["class"])
        
        # Log websocket status
        ws_info = analysis.get("websocket", {})
        LOGGER.info("WebSocket: available=%s, connected=%s, url=%s", 
                    ws_info.get("available"), ws_info.get("connected"), ws_info.get("url"))
        
        # Log connectivity information
        conn_info = analysis.get("connectivity", {})
        LOGGER.info("UniFi OS detected: %s", conn_info.get("is_unifi_os"))
        
        # Log capabilities
        LOGGER.info("Controller capabilities: %s", ", ".join(analysis.get("capabilities", [])))
        
        # API instance status (minimal info)
        if api_instance:
            LOGGER.info("API connection: %s@%s (site: %s)", 
                        getattr(api_instance, "username", "unknown"),
                        getattr(api_instance, "host", "unknown"),
                        getattr(api_instance, "site", "unknown"))
            
            # Session information (just status, not details)
            has_session = hasattr(api_instance, "_session") and getattr(api_instance, "_session") is not None
            LOGGER.info("API session established: %s", has_session)
        
        LOGGER.info("=============================================")
    except Exception as e:
        LOGGER.error("Error generating diagnostics: %s", e)

async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> Dict[str, Any]:
    """Return diagnostics for a config entry.
    
    Provides comprehensive diagnostics including:
    - Config entry information (sanitized)
    - Coordinator statistics and health
    - Controller connectivity status
    - Recent WebSocket events
    - API session status
    - Rule counts and data statistics
    """
    # Get coordinator from entry data
    coordinator = hass.data[DOMAIN].get(entry.entry_id, {}).get("coordinator")
    
    if not coordinator:
        return {"error": "Coordinator not found"}
    
    # Get the UDM API instance
    api = getattr(coordinator, "api", None)
    
    # Build comprehensive diagnostics
    diagnostics = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "domain": entry.domain,
            "version": entry.version,
            "state": str(entry.state),
            "unique_id": entry.unique_id,
            # Sanitize config data
            "data": sanitize_sensitive_data(dict(entry.data)),
            "options": sanitize_sensitive_data(dict(entry.options)),
        },
        "coordinator": get_coordinator_stats(coordinator),
        "controller": analyze_controller(getattr(api, "controller", None) if api else None),
        "recent_websocket_events": get_recent_websocket_events(coordinator, limit=10),
        "timestamp": datetime.now().isoformat(),
    }
    
    # Add API session information if available
    if api:
        api_info = {
            "host": getattr(api, "host", "unknown"),
            "site": getattr(api, "site", "unknown"),
            "username": getattr(api, "username", "unknown"),
            "verify_ssl": getattr(api, "verify_ssl", None),
        }
        
        # Add session status without sensitive details
        session_info = {
            "has_session": hasattr(api, "_session") and getattr(api, "_session") is not None,
            "rate_limited": getattr(api, "_rate_limited", False),
            "consecutive_auth_failures": getattr(api, "_consecutive_auth_failures", 0),
            "last_auth_time": str(getattr(api, "_last_auth_time", "unknown")),
        }
        
        # Rate limiting information
        if hasattr(api, "_rate_limit_until"):
            rate_limit_until = getattr(api, "_rate_limit_until", 0)
            if rate_limit_until > 0:
                session_info["rate_limit_expires"] = str(datetime.fromtimestamp(rate_limit_until))
        
        api_info["session"] = session_info
        diagnostics["api"] = api_info
    
    # Add Home Assistant integration data
    domain_data = hass.data.get(DOMAIN, {})
    integration_info = {
        "total_config_entries": len([k for k in domain_data.keys() if k != "shared" and k != "services"]),
        "shared_data_available": "shared" in domain_data,
        "services_available": "services" in domain_data,
    }
    diagnostics["integration"] = integration_info
    
    return diagnostics 