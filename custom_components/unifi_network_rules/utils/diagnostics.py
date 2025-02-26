"""Diagnostics module for UniFi Network Rules."""
from __future__ import annotations

import logging
import json
import inspect
from typing import Any, Dict, List

from ..const import LOGGER

def analyze_controller(controller: Any) -> Dict[str, Any]:
    """Analyze controller object structure for diagnostics."""
    result = {
        "class": controller.__class__.__name__,
        "attributes": [],
        "methods": [],
        "has_websocket": False,
        "has_is_unifi_os": False
    }
    
    # Get all attributes and methods
    for attr_name in dir(controller):
        # Skip private attributes
        if attr_name.startswith("_") and attr_name not in ["__class__"]:
            continue
            
        try:
            attr = getattr(controller, attr_name)
            
            # Check if it's a method
            if callable(attr):
                result["methods"].append(attr_name)
                
                # Check for important WebSocket methods
                if attr_name == "start_websocket":
                    result["has_start_websocket_method"] = True
                elif attr_name == "stop_websocket":
                    result["has_stop_websocket_method"] = True
            else:
                result["attributes"].append(attr_name)
                
                # Track specific important attributes
                if attr_name == "websocket":
                    result["has_websocket"] = True
                elif attr_name == "is_unifi_os":
                    result["has_is_unifi_os"] = True
                    result["is_unifi_os_value"] = attr
                elif attr_name == "ws_handler":
                    result["has_ws_handler"] = True
        except Exception as e:
            LOGGER.debug("Error accessing attribute %s: %s", attr_name, e)
    
    # Analyze websocket if present
    if result["has_websocket"]:
        try:
            ws = getattr(controller, "websocket")
            result["websocket"] = {
                "class": ws.__class__.__name__,
                "attributes": [a for a in dir(ws) if not a.startswith("_") or a == "__class__"],
                "has_build_url": hasattr(ws, "_build_url"),
                "has_url": hasattr(ws, "url"),
            }
            
            if hasattr(ws, "url"):
                result["websocket"]["url"] = ws.url
        except Exception as e:
            LOGGER.debug("Error analyzing websocket: %s", e)
            
    # Analyze connectivity if present
    if hasattr(controller, "connectivity"):
        try:
            conn = getattr(controller, "connectivity")
            result["connectivity"] = {
                "class": conn.__class__.__name__,
                "has_websocket_method": hasattr(conn, "websocket") and callable(getattr(conn, "websocket")),
                "has_is_unifi_os": hasattr(conn, "is_unifi_os"),
            }
            
            if hasattr(conn, "is_unifi_os"):
                result["connectivity"]["is_unifi_os_value"] = getattr(conn, "is_unifi_os")
        except Exception as e:
            LOGGER.debug("Error analyzing connectivity: %s", e)
    
    return result

def log_controller_diagnostics(controller: Any, api_instance: Any = None) -> None:
    """Log diagnostic information about the controller structure."""
    try:
        LOGGER.info("========== CONTROLLER DIAGNOSTICS ==========")
        
        if controller is None:
            LOGGER.info("Controller is None!")
            return
            
        analysis = analyze_controller(controller)
        LOGGER.info("Controller class: %s", analysis["class"])
        LOGGER.info("Has websocket: %s", analysis["has_websocket"])
        LOGGER.info("Has is_unifi_os: %s", analysis["has_is_unifi_os"])
        
        if analysis["has_is_unifi_os"]:
            LOGGER.info("is_unifi_os value: %s", analysis.get("is_unifi_os_value"))
            
        # Log WebSocket method availability
        LOGGER.info("Has start_websocket method: %s", analysis.get("has_start_websocket_method", False))
        LOGGER.info("Has stop_websocket method: %s", analysis.get("has_stop_websocket_method", False))
        LOGGER.info("Has ws_handler attribute: %s", analysis.get("has_ws_handler", False))
            
        if analysis["has_websocket"]:
            ws_info = analysis.get("websocket", {})
            LOGGER.info("WebSocket class: %s", ws_info.get("class"))
            LOGGER.info("WebSocket has _build_url: %s", ws_info.get("has_build_url"))
            LOGGER.info("WebSocket has url: %s", ws_info.get("has_url"))
            
            if ws_info.get("has_url"):
                LOGGER.info("Current WebSocket URL: %s", ws_info.get("url"))
                
        # Log connectivity information if available
        if "connectivity" in analysis:
            conn_info = analysis["connectivity"]
            LOGGER.info("Connectivity class: %s", conn_info.get("class"))
            LOGGER.info("Connectivity has websocket method: %s", conn_info.get("has_websocket_method"))
            LOGGER.info("Connectivity has is_unifi_os: %s", conn_info.get("has_is_unifi_os"))
            
            if conn_info.get("has_is_unifi_os"):
                LOGGER.info("Connectivity is_unifi_os value: %s", conn_info.get("is_unifi_os_value"))
        
        # Also log API instance info if provided
        if api_instance:
            LOGGER.info("========== API INSTANCE DIAGNOSTICS ==========")
            
            # Basic info
            LOGGER.info("API Host: %s", getattr(api_instance, "host", "unknown"))
            LOGGER.info("API Site: %s", getattr(api_instance, "site", "unknown"))
            
            # Session information
            has_session = hasattr(api_instance, "_session") and getattr(api_instance, "_session") is not None
            LOGGER.info("Has session: %s", has_session)
            
            # Check if the API has important attributes and methods
            has_controller = hasattr(api_instance, "controller") and getattr(api_instance, "controller") is not None
            LOGGER.info("Has controller: %s", has_controller)
            
            has_check_udm = hasattr(api_instance, "_check_udm_device")
            LOGGER.info("Has _check_udm_device method: %s", has_check_udm)
            
            has_manual_ws = hasattr(api_instance, "_manual_websocket_connect")
            LOGGER.info("Has _manual_websocket_connect method: %s", has_manual_ws)
            
            has_config = hasattr(api_instance, "_config") and getattr(api_instance, "_config") is not None
            LOGGER.info("Has config: %s", has_config)
            
            initialized = getattr(api_instance, "_initialized", False)
            LOGGER.info("Is initialized: %s", initialized)
            
            # Check custom WebSocket handler
            has_custom_ws = hasattr(api_instance, "_custom_websocket") and getattr(api_instance, "_custom_websocket") is not None
            LOGGER.info("Has custom WebSocket handler: %s", has_custom_ws)
            
            if has_custom_ws:
                custom_ws = getattr(api_instance, "_custom_websocket")
                LOGGER.info("Custom WebSocket URL: %s", getattr(custom_ws, "url", "unknown"))
                has_callback = getattr(custom_ws, "callback", None) is not None
                LOGGER.info("Custom WebSocket has callback: %s", has_callback)
            
            # Check WebSocket callback status
            has_ws_message_handler = hasattr(api_instance, "_ws_message_handler") and getattr(api_instance, "_ws_message_handler") is not None
            LOGGER.info("Has _ws_message_handler: %s", has_ws_message_handler)
        
        LOGGER.info("============================================")
    except Exception as e:
        LOGGER.error("Error generating diagnostics: %s", e) 