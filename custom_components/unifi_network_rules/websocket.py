"""UniFi Network Rules websocket implementation."""
from __future__ import annotations

from typing import Any, Callable, Dict
import asyncio
from datetime import datetime, timedelta
import logging
import re

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    LOGGER,
    SIGNAL_WEBSOCKET_EVENT,
    DEBUG_WEBSOCKET,  # Keep for backward compatibility
)
from .udm_api import UDMAPI
from .utils.diagnostics import log_controller_diagnostics
from .utils.logger import log_websocket

SIGNAL_WEBSOCKET_CONNECTION_LOST = "unifi_network_rules_websocket_connection_lost"
SIGNAL_WEBSOCKET_MESSAGE = "unifi_network_rules_websocket_message"

class UnifiRuleWebsocket:
    """UniFi Network Rules websocket handler."""

    def __init__(self, hass: HomeAssistant, api: UDMAPI, entry_id: str) -> None:
        """Initialize the websocket handler."""
        self.hass = hass
        self.api = api
        self.entry_id = entry_id
        self._task = None
        self._message_handler: Callable[[dict[str, Any]], None] | None = None
        self._ws_connection_attempts = 0
        self._connection_lost_dispatched = False

    def start(self) -> None:
        """Start listening to the websocket."""
        log_websocket("Starting UniFi Network Rules websocket %s", self.entry_id)
        try:
            # First check if the API has the necessary method for setting the callback
            if hasattr(self.api, "set_websocket_callback"):
                # Set our message handler callback
                self.api.set_websocket_callback(self._handle_message)
                
                # Run diagnostics if websocket debugging is enabled
                if (DEBUG_WEBSOCKET or hasattr(self.api, "controller") and self.api.controller):
                    log_websocket("Logging WebSocket controller diagnostics")
                    log_controller_diagnostics(self.api.controller, self.api)
                
                # Start the websocket connection
                self._task = asyncio.create_task(self._websocket_connect())
                self._ws_connection_attempts = 1
                self._connection_lost_dispatched = False
            else:
                LOGGER.error(
                    "WebSocket functionality not available - API missing required methods. "
                    "This may indicate a module version conflict."
                )
        except Exception as err:
            LOGGER.error("Error starting websocket handler: %s", str(err))

    async def _websocket_connect(self) -> None:
        """Start websocket connection."""
        try:
            log_websocket("Attempting WebSocket connection (attempt #%s)", self._ws_connection_attempts)
            
            # Log controller diagnostics before attempting connection if websocket debugging is enabled
            if (DEBUG_WEBSOCKET and self._ws_connection_attempts == 1):
                if hasattr(self.api, "controller") and self.api.controller:
                    log_websocket("Logging pre-connection WebSocket diagnostics")
                    log_controller_diagnostics(self.api.controller, self.api)
            
            # Add a minimum delay between attempts to prevent rate limiting
            if self._ws_connection_attempts > 1:
                # Fixed minimum delay of 5 seconds between attempts
                min_delay = 5
                log_websocket("Enforcing minimum %s second delay between WebSocket attempts", min_delay)
                await asyncio.sleep(min_delay)
            
            # Start WebSocket - our enhanced start_websocket will try both built-in and custom
            if hasattr(self.api, "start_websocket"):
                await self.api.start_websocket()
                
                # Reset counter on successful connection
                self._ws_connection_attempts = 0
                self._connection_lost_dispatched = False
                LOGGER.info("WebSocket connected successfully (entry %s)", self.entry_id)
            else:
                raise RuntimeError("API doesn't have start_websocket method")
            
        except Exception as err:
            error_str = str(err)
            LOGGER.error("Error connecting to WebSocket (attempt #%s): %s", 
                       self._ws_connection_attempts, error_str)
            
            # Log additional diagnostics on error
            if (DEBUG_WEBSOCKET and hasattr(self.api, "controller") and self.api.controller):
                log_websocket("Logging WebSocket diagnostics after error")
                log_controller_diagnostics(self.api.controller, self.api)
            
            # Schedule reconnection with backoff - increased maximum backoff
            self._ws_connection_attempts += 1
            # Change backoff calculation to be more aggressive and hit maximum earlier
            backoff = min(5 * (2 ** (self._ws_connection_attempts - 1)), 600)  # Max 10 minutes
            
            # Signal to HA if connection was lost after being established
            if self._ws_connection_attempts > 1 and not self._connection_lost_dispatched:
                self._connection_lost_dispatched = True
                LOGGER.warning("Websocket connection lost, will reconnect in %s seconds", backoff)
                async_dispatcher_send(self.hass, f"{SIGNAL_WEBSOCKET_CONNECTION_LOST}_{self.entry_id}")
            else:
                log_websocket("Scheduling websocket reconnection in %s seconds", backoff)
                
            # After multiple failed attempts, inform the user
            if self._ws_connection_attempts >= 5:
                LOGGER.warning(
                    "WebSocket connection failed after %s attempts. Will continue trying, but "
                    "real-time updates may be delayed. Check logs for details.", 
                    self._ws_connection_attempts
                )
                
            self._task = asyncio.create_task(self._schedule_reconnect(backoff))

    async def _schedule_reconnect(self, delay: int) -> None:
        """Schedule a reconnection attempt with delay."""
        await asyncio.sleep(delay)
        if not self._connection_lost_dispatched:
            log_websocket("Reconnecting to websocket after %s second delay", delay)
        self._task = asyncio.create_task(self._websocket_connect())

    def stop(self) -> None:
        """Close websocket connection."""
        log_websocket("Closing UniFi Network Rules websocket %s", self.entry_id)
        
        # Cancel any pending reconnection tasks
        if self._task is not None and not self._task.done():
            self._task.cancel()
            self._task = None
            
        # Stop the API WebSocket
        if hasattr(self.api, "stop_websocket"):
            asyncio.create_task(self.api.stop_websocket())
            
        self._ws_connection_attempts = 0
        self._connection_lost_dispatched = False

    def _handle_message(self, message: dict[str, Any]) -> None:
        """Process websocket message."""
        # Get message type for logging
        meta = message.get("meta", {})
        msg_type = meta.get("message", "")
        
        # Only log full details for rule-related messages
        if DEBUG_WEBSOCKET:
            if any(keyword in msg_type.lower() for keyword in [
                "firewall", "rule", "policy", "traffic", "route", "port-forward", 
                "delete", "update", "insert", "events"
            ]):
                log_websocket("WebSocket rule-related message received: %s - %s", 
                           msg_type, str(message)[:150])
            else:
                # For other messages just log the type
                log_websocket("WebSocket message received: %s", msg_type)
            
        # In case we get any reconnection message, reset counters
        if message.get("meta", {}).get("message") == "reconnect":
            self._ws_connection_attempts = 0
            self._connection_lost_dispatched = False
            
        # Call message handler if registered
        if self._message_handler:
            try:
                self._message_handler(message)
            except Exception as err:
                LOGGER.error("Error in message handler: %s", err)
        
        # Send signal to entities
        self.hass.loop.call_soon_threadsafe(
            async_dispatcher_send,
            self.hass,
            f"{SIGNAL_WEBSOCKET_MESSAGE}_{self.entry_id}",
            message,
        )
        
        # Also dispatch the general event signal for debug purposes
        self.hass.loop.call_soon_threadsafe(
            async_dispatcher_send,
            self.hass,
            SIGNAL_WEBSOCKET_EVENT,
            {"entry_id": self.entry_id, "message": message},
        )

    def set_message_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Set the message handler."""
        self._message_handler = handler

    async def stop_and_wait(self) -> None:
        """Stop listening to the websocket and wait for it to close."""
        log_websocket("Stopping UniFi Network Rules websocket %s", self.entry_id)
        try:
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                
            if hasattr(self.api, "stop_websocket"):
                await self.api.stop_websocket()
        except Exception as err:
            LOGGER.error("Error stopping websocket: %s", str(err))