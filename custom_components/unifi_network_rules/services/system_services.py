"""System services for UniFi Network Rules integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import voluptuous as vol
import re

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import DOMAIN, LOGGER
from .constants import (
    SERVICE_REFRESH,
    SERVICE_REFRESH_DATA,
    SERVICE_WEBSOCKET_DIAGNOSTICS,
    SERVICE_SYNC_REMOTE_CURATED,
)
from ..utils.remote_lists import parse_curated_text

# Schema for refresh service
REFRESH_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
    }
)

async def async_refresh_service(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Service to refresh UniFi data."""
    # Refresh all coordinators
    for coordinator in coordinators.values():
        await coordinator.async_refresh()

async def async_refresh_data(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Handle the refresh service call."""
    entry_id = call.data.get("entry_id")
    
    if entry_id:
        # Refresh specific coordinator
        if entry_id in coordinators:
            LOGGER.info("Manually refreshing data for entry %s", entry_id)
            await coordinators[entry_id].async_refresh()
        else:
            raise HomeAssistantError(f"No coordinator found for entry_id {entry_id}")
    else:
        # Refresh all coordinators
        LOGGER.info("Manually refreshing data for all coordinators")
        for entry_id, coordinator in coordinators.items():
            LOGGER.debug("Refreshing coordinator for entry %s", entry_id)
            await coordinator.async_refresh()

async def async_websocket_diagnostics(hass: HomeAssistant, coordinators: Dict, call: ServiceCall) -> None:
    """Run diagnostics on WebSocket connections and try to repair if needed."""
    results = {}
    
    # Check all entries and their WebSocket connections
    for entry_id, entry_data in hass.data[DOMAIN].items():
        entry_result = {
            "status": "unknown",
            "details": {},
            "actions_taken": []
        }
        
        # Check if API exists
        if "api" not in entry_data:
            entry_result["status"] = "error"
            entry_result["details"]["error"] = "No API found for this entry"
            results[entry_id] = entry_result
            continue
            
        api = entry_data["api"]
        websocket = entry_data.get("websocket")
        
        # Collect API information
        entry_result["details"]["initialized"] = api.initialized if hasattr(api, "initialized") else False
        entry_result["details"]["connection_url"] = api.host if hasattr(api, "host") else "unknown"
        
        # Check controller information
        if hasattr(api, "controller") and api.controller:
            entry_result["details"]["controller_available"] = True
            entry_result["details"]["is_unifi_os"] = getattr(api.controller, "is_unifi_os", False)
            
            # Check controller WebSocket state
            if hasattr(api.controller, "websocket"):
                ws = api.controller.websocket
                entry_result["details"]["controller_websocket"] = {
                    "state": getattr(ws, "state", "unknown"),
                    "url": getattr(ws, "url", "unknown"),
                }
        else:
            entry_result["details"]["controller_available"] = False
        
        # Check custom WebSocket state
        if hasattr(api, "_custom_websocket") and api._custom_websocket:
            try:
                custom_ws = api._custom_websocket
                entry_result["details"]["custom_websocket"] = {
                    "connected": custom_ws.is_connected(),
                    "url": custom_ws.url,
                }
                
                # Get detailed status if available
                if hasattr(custom_ws, "get_connection_status"):
                    entry_result["details"]["custom_websocket_status"] = custom_ws.get_connection_status()
            except Exception as err:
                entry_result["details"]["custom_websocket_error"] = str(err)
        else:
            entry_result["details"]["custom_websocket"] = None
        
        # Check if WebSocket handler exists
        if websocket:
            entry_result["details"]["websocket_handler_exists"] = True
        else:
            entry_result["details"]["websocket_handler_exists"] = False
        
        # Check coordinator
        if "coordinator" in entry_data:
            coordinator = entry_data["coordinator"]
            entry_result["details"]["coordinator_exists"] = True
            entry_result["details"]["coordinator_last_update_success"] = coordinator.last_update_success
            
            # Check how many data sources have data
            if hasattr(coordinator, "data") and coordinator.data:
                data_sources = {k: len(v) for k, v in coordinator.data.items() if v}
                entry_result["details"]["data_sources"] = data_sources
        
        # Attempt repairs if problems detected
        try:
            # If WebSocket isn't connected, try to restart it
            if not entry_result["details"].get("custom_websocket", {}).get("connected", False) and \
               not entry_result["details"].get("controller_websocket", {}).get("state") == "running":
                
                LOGGER.info("Attempting to restart WebSocket for entry %s", entry_id)
                entry_result["actions_taken"].append("Restarting WebSocket connection")
                
                # Stop current WebSocket if any
                if websocket:
                    await websocket.stop_and_wait()
                
                # Also stop API WebSocket
                if hasattr(api, "stop_websocket"):
                    await api.stop_websocket()
                
                # Clear cache to ensure fresh data
                if hasattr(api, "clear_cache"):
                    await api.clear_cache()
                    entry_result["actions_taken"].append("Cleared API cache")
                
                # Try to refresh session
                if hasattr(api, "refresh_session"):
                    success = await api.refresh_session()
                    if success:
                        entry_result["actions_taken"].append("Refreshed API session")
                
                # Start WebSocket
                if websocket:
                    websocket.start()
                    entry_result["actions_taken"].append("Started WebSocket handler")
                
                # Refresh data
                if "coordinator" in entry_data:
                    await entry_data["coordinator"].async_refresh()
                    entry_result["actions_taken"].append("Refreshed coordinator data")
                
                # Update status based on actions taken
                entry_result["status"] = "repaired"
            else:
                # If everything seems fine
                entry_result["status"] = "healthy"
                
                # Still refresh data to ensure it's current
                if "coordinator" in entry_data:
                    await entry_data["coordinator"].async_refresh()
                    entry_result["actions_taken"].append("Refreshed coordinator data")
        except Exception as repair_err:
            entry_result["status"] = "repair_failed"
            entry_result["details"]["repair_error"] = str(repair_err)
        
        # Store results for this entry
        results[entry_id] = entry_result
    
    # Log summary of results
    summary = {entry_id: result["status"] for entry_id, result in results.items()}
    LOGGER.info("WebSocket diagnostics summary: %s", summary)
    
    # Return to service caller
    return results

async def async_setup_system_services(hass: HomeAssistant, coordinators: Dict) -> None:
    """Set up system-related services."""
    
    # Handle the refresh service
    async def handle_refresh(call: ServiceCall) -> None:
        await async_refresh_service(hass, coordinators, call)
        
    # Handle the refresh data service
    async def handle_refresh_data(call: ServiceCall) -> None:
        await async_refresh_data(hass, coordinators, call)
        
    # Handle the websocket diagnostics service
    async def handle_websocket_diagnostics(call: ServiceCall) -> None:
        return await async_websocket_diagnostics(hass, coordinators, call)
    
    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH, handle_refresh, schema=REFRESH_DATA_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH_DATA, handle_refresh_data, schema=REFRESH_DATA_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, SERVICE_WEBSOCKET_DIAGNOSTICS, handle_websocket_diagnostics, schema=vol.Schema({})
    )

    # Remote curated file sync
    async def handle_sync_remote_curated(call: ServiceCall) -> None:
        entry_id = call.data.get("entry_id")
        urls_input = call.data.get("urls")
        url_list: list[str] = []
        if isinstance(urls_input, list):
            # Flatten any strings that might contain multiple URLs
            for item in urls_input:
                if isinstance(item, str):
                    found = re.findall(r"https?://\S+", item)
                    url_list.extend(found if found else [item])
        elif isinstance(urls_input, str):
            # Extract all http(s) URLs from the string (handles spaces, newlines)
            url_list = re.findall(r"https?://\S+", urls_input)
        if not url_list:
            raise HomeAssistantError("'urls' must contain at least one valid http(s) URL")

        targets = (
            {entry_id: coordinators.get(entry_id)} if entry_id and entry_id in coordinators else coordinators
        )
        for _entry, coord in targets.items():
            if not coord:
                continue
            api = getattr(coord, "api", None) or getattr(coord, "_api", None)
            if not api:
                continue
            for raw_url in url_list:
                try:
                    session = async_get_clientsession(hass)
                    async with session.get(raw_url) as resp:
                        if resp.status != 200:
                            raise HomeAssistantError(f"Failed to fetch remote list '{raw_url}': {resp.status} {await resp.text()}")
                        content = await resp.text()

                    payload = parse_curated_text(content)
                    # Enforce type-specific members
                    obj_type = payload.get("type", "address-group")
                    if obj_type == "port-group":
                        filtered = [m for m in payload.get("members", []) if m.get("type") == "port"]
                    elif obj_type == "ipv6-address-group":
                        filtered = [m for m in payload.get("members", []) if m.get("type", "").startswith("ipv6")]
                    else:
                        filtered = [m for m in payload.get("members", []) if m.get("type", "").startswith("ipv4")]
                    payload = {**payload, "members": filtered}

                    existing = await api.get_objects()
                    existing_by_name = {o.name: o for o in existing}
                    name = payload.get("name")
                    if name in existing_by_name:
                        obj = existing_by_name[name]
                        to_update = obj.to_dict()
                        to_update.update({
                            "description": payload.get("description", to_update.get("description")),
                            "type": obj_type,
                            "members": payload.get("members", to_update.get("members", [])),
                        })
                        await api.update_object(to_update)
                    else:
                        await api.add_object(payload)
                except Exception as err:
                    LOGGER.error("Remote curated sync failed for '%s': %s", raw_url, err)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_REMOTE_CURATED,
        handle_sync_remote_curated,
        schema=vol.Schema({
            vol.Optional("entry_id"): cv.string,
            vol.Required("urls"): vol.Any(cv.ensure_list(cv.string), cv.string),
        }),
    )