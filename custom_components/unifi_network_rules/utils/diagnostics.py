"""Diagnostics module for UniFi Network Rules."""
from __future__ import annotations

import logging
from typing import Any, Dict

from ..const import LOGGER, DOMAIN

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

def async_get_config_entry_diagnostics(hass, entry):
    """Return diagnostics for a config entry."""
    # Get coordinator from entry data
    coordinator = hass.data[DOMAIN].get(entry.entry_id, {}).get("coordinator")
    
    if not coordinator:
        return {"error": "Coordinator not found"}
    
    # Get the UDM API instance
    api = getattr(coordinator, "api", None)
    
    # Get a subset of important diagnostics data
    diagnostics = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "domain": entry.domain,
        },
        "controller": analyze_controller(getattr(api, "controller", None) if api else None),
        "data_stats": {
            "firewall_policy_count": len(getattr(coordinator, "data", {}).get("firewall_policies", [])),
            "traffic_route_count": len(getattr(coordinator, "data", {}).get("traffic_routes", [])),
            "refresh_timestamp": str(getattr(coordinator, "last_update_success", "unknown")),
        }
    }
    
    return diagnostics 