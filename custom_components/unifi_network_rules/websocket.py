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
from .udm import UDMAPI
from .utils.diagnostics import log_controller_diagnostics
from .utils.logger import log_websocket

SIGNAL_WEBSOCKET_CONNECTION_LOST = "unifi_network_rules_websocket_connection_lost"
SIGNAL_WEBSOCKET_MESSAGE = "unifi_network_rules_websocket_message"

class UnifiRuleWebsocket:
    """Websocket component for UniFi Network Rules integration."""

    def __init__(self, hass, api, entry_id) -> None:
        """Initialize the websocket handler."""
        self.hass = hass
        self.entry_id = entry_id
        self.api = api

        # Callback for handling messages
        self._message_handler = None
        
        # WebSocket connection state tracking
        self._ws_connected = False
        self._ws_connection_attempts = 0
        self._ws_reconnect_error_count = 0
        self._ws_reconnection_task = None
        self._ws_monitoring_task = None
        self._connection_lost_dispatched = False
        
        # Tasks
        self._task = None

    def set_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register callback for WebSocket messages."""
        self._message_handler = callback
        if DEBUG_WEBSOCKET:
            LOGGER.debug("WebSocket callback registered")

    def start(self) -> None:
        """Start the websocket handler."""
        try:
            # Cancel any existing task
            if self._task and not self._task.done():
                self._task.cancel()

            # Start WebSocket connection
            self._ws_connection_attempts = 1
            self._task = asyncio.create_task(self._websocket_connect())
        except Exception as err:
            LOGGER.error("Error starting websocket handler: %s", str(err))

    async def _websocket_connect(self) -> bool:
        """Start websocket connection."""
        try:
            if DEBUG_WEBSOCKET:
                 log_websocket("Attempting WebSocket connection (attempt #%s)", self._ws_connection_attempts)
            
            # Log controller diagnostics before attempting connection if websocket debugging is enabled
            if (DEBUG_WEBSOCKET and self._ws_connection_attempts == 1):
                if hasattr(self.api, "controller") and self.api.controller:
                    log_websocket("Logging pre-connection WebSocket diagnostics")
                    log_controller_diagnostics(self.api.controller, self.api)
            
            # Add a minimum delay between attempts to prevent rate limiting
            if self._ws_connection_attempts > 1:
                # Adaptive delay based on number of attempts
                min_delay = min(5 * self._ws_connection_attempts, 30)
                if DEBUG_WEBSOCKET:
                     log_websocket("Enforcing minimum %s second delay between WebSocket attempts", min_delay)
                await asyncio.sleep(min_delay)
            
            # Ensure we have current session cookies before starting
            if hasattr(self.api, "controller") and self.api.controller:
                # Check if controller seems to be logged in
                try:
                    if not hasattr(self.api.controller.connectivity, "session_cookie") or \
                       not self.api.controller.connectivity.session_cookie:
                        if DEBUG_WEBSOCKET:
                             LOGGER.debug("Controller session appears invalid, re-authenticating")
                        await self.api.controller.login()
                        if DEBUG_WEBSOCKET:
                             LOGGER.debug("Re-authenticated controller before WebSocket connection")
                except Exception as login_err:
                    LOGGER.warning("Error refreshing authentication before WebSocket: %s", login_err)
            
            # Set callback before connecting
            if self._message_handler:
                if DEBUG_WEBSOCKET:
                     LOGGER.debug("Setting WebSocket callback")
                
                # Set WebSocket callback - API will handle this through the WebSocketMixin
                if hasattr(self.api, "set_websocket_callback"):
                    # Check if controller has ws_handler attribute which indicates native ws support
                    has_ws_handler = False
                    if hasattr(self.api, "controller") and self.api.controller:
                        has_ws_handler = hasattr(self.api.controller, "ws_handler")
                        
                    if not has_ws_handler and DEBUG_WEBSOCKET:
                        LOGGER.debug("Controller doesn't have ws_handler attribute, will use custom handler")
                    
                    # Set the callback at API level regardless - our implementation handles both
                    self.api.set_websocket_callback(self._handle_message)  # Use _handle_message as wrapper
                    if DEBUG_WEBSOCKET:
                         LOGGER.debug("Set WebSocket callback on API")
                else:
                    LOGGER.warning("API missing set_websocket_callback method, callback not set")
            
            # Start WebSocket with custom error handling and timeout
            if hasattr(self.api, "start_websocket"):
                try:
                    LOGGER.info("Starting WebSocket connection for real-time event notifications")
                    
                    # Create task with timeout to avoid hanging forever
                    async with asyncio.timeout(30):
                        await self.api.start_websocket()
                    
                    # If we get here, connection succeeded
                    LOGGER.info("WebSocket connection established successfully")
                    self._ws_connected = True
                    self._ws_connection_attempts = 0  # Reset counter on success
                    self._ws_reconnect_error_count = 0  # Reset error counter
                    self._connection_lost_dispatched = False
                    
                    # Signal successful connection to HA
                    async_dispatcher_send(self.hass, f"{SIGNAL_WEBSOCKET_MESSAGE}_{self.entry_id}", 
                                      {"meta": {"message": "connected"}})
                    
                    # Schedule reconnection health check
                    self._start_monitoring()
                    return True
                    
                except asyncio.TimeoutError:
                    LOGGER.warning("WebSocket connection attempt timed out after 30 seconds")
                    raise ConnectionError("WebSocket connection timeout")
                    
                except Exception as err:
                    LOGGER.error("WebSocket connection error: %s", str(err))
                    raise ConnectionError(f"WebSocket connection error: {str(err)}")
            else:
                LOGGER.error(
                    "WebSocket functionality not available - API missing required methods. "
                    "This may indicate a module version conflict."
                )
                
        except Exception as err:
            self._ws_connected = False
            self._ws_reconnect_error_count += 1
            LOGGER.error("Error connecting to WebSocket (attempt #%s): %s", 
                         self._ws_connection_attempts, str(err))
            
            # Schedule reconnection with exponential backoff
            reconnect_delay = min(10 * (2 ** min(self._ws_reconnect_error_count - 1, 5)), 300)
            log_websocket("Scheduling websocket reconnection in %s seconds", reconnect_delay)
            
            # Signal to HA if connection was lost after being established
            if self._ws_connection_attempts > 1 and not self._connection_lost_dispatched:
                self._connection_lost_dispatched = True
                LOGGER.warning("Websocket connection lost, will reconnect in %s seconds", reconnect_delay)
                async_dispatcher_send(self.hass, f"{SIGNAL_WEBSOCKET_CONNECTION_LOST}_{self.entry_id}")
            
            # If multiple failed attempts, show warning
            if self._ws_connection_attempts >= 5 and self._ws_connection_attempts % 5 == 0:
                LOGGER.warning(
                    "WebSocket connection failed after %s attempts. Will continue trying, "
                    "but real-time updates may be delayed. Check logs for details.", 
                    self._ws_connection_attempts
                )
            
            # Schedule next attempt
            self._ws_connection_attempts += 1
            self._ws_reconnection_task = asyncio.create_task(self._schedule_reconnect(reconnect_delay))
            return False

    async def _schedule_reconnect(self, delay: int) -> None:
        """Schedule a websocket reconnection with backoff."""
        try:
            await asyncio.sleep(delay)
            # Start a new connection attempt
            self._task = asyncio.create_task(self._websocket_connect())
        except asyncio.CancelledError:
            # Task was cancelled, this is expected during shutdown
            pass
        except Exception as err:
            LOGGER.exception("Error in websocket reconnection: %s", err)

    def stop(self) -> None:
        """Stop the websocket handler."""
        try:
            # Cancel all tasks
            for task in [self._task, self._ws_reconnection_task, self._ws_monitoring_task]:
                if task and not task.done():
                    task.cancel()
                    
            # Stop the WebSocket connection
            if hasattr(self.api, "stop_websocket"):
                self.api.stop_websocket()
                
            if DEBUG_WEBSOCKET:
                LOGGER.debug("WebSocket handler stopped")
        except Exception as err:
            LOGGER.error("Error stopping websocket: %s", str(err))

    async def async_stop(self) -> None:
        """Stop the websocket handler and wait for tasks to complete."""
        # Call the synchronous stop first
        self.stop()
        
        # Wait a short time for tasks to properly cancel
        await asyncio.sleep(0.5)
        
        # Wait for any remaining tasks to complete
        tasks_to_wait = []
        for task in [self._task, self._ws_reconnection_task, self._ws_monitoring_task]:
            if task and not task.done():
                tasks_to_wait.append(task)
                
        if tasks_to_wait:
            try:
                # Wait with a timeout to avoid hanging forever
                await asyncio.wait(tasks_to_wait, timeout=2.0)
            except (asyncio.CancelledError, Exception) as err:
                if DEBUG_WEBSOCKET:
                    LOGGER.debug("Error waiting for WebSocket tasks to complete: %s", err)
                
        if DEBUG_WEBSOCKET:
            LOGGER.debug("WebSocket handler async stop completed")

    def _start_monitoring(self) -> None:
        """Start monitoring the WebSocket connection."""
        if self._ws_monitoring_task and not self._ws_monitoring_task.done():
            self._ws_monitoring_task.cancel()
            
        self._ws_monitoring_task = asyncio.create_task(self._monitor_connection())
        if DEBUG_WEBSOCKET:
            LOGGER.debug("Started WebSocket connection monitoring task")
        
    async def _monitor_connection(self) -> None:
        """Monitor the WebSocket connection and restart if needed."""
        try:
            while True:
                # Check connection status every 60 seconds
                await asyncio.sleep(60)
                
                if not self._ws_connected:
                    if DEBUG_WEBSOCKET:
                        LOGGER.debug("WebSocket connection lost during monitoring, attempting to reconnect")
                    # If not connected, try to reconnect
                    if not self._task or self._task.done():
                        self._ws_connection_attempts += 1
                        self._task = asyncio.create_task(self._websocket_connect())
                        
                # Check the API connection as well if available
                if hasattr(self.api, "_custom_websocket") and self.api._custom_websocket:
                    if not self.api._custom_websocket.is_connected():
                        if DEBUG_WEBSOCKET:
                            LOGGER.debug("Custom WebSocket disconnected, attempting to reconnect")
                        self._ws_connected = False
                        if not self._task or self._task.done():
                            self._ws_connection_attempts += 1
                            self._task = asyncio.create_task(self._websocket_connect())
                    
        except asyncio.CancelledError:
            # Task was cancelled, this is expected during shutdown
            pass
        except Exception as err:
            LOGGER.exception("Error in WebSocket monitoring: %s", err)

    def _handle_message(self, message: dict[str, Any]) -> None:
        """Process websocket messages and dispatch updates."""
        if not message or not isinstance(message, dict):
            return
        
        # Define keywords for rule-related messages
        rule_keywords = [
            "firewall", "rule", "policy", "network", "port", "route", "forward",
            "nat", "security", "update", "change", "cfgversion", "provision",
            "qos", "quality", "service", "vpn"  # Add QoS-related keywords
        ]
        
        # Extract message type for filtering
        msg_type = message.get("meta", {}).get("message", "")
        msg_type_lower = msg_type.lower()
        
        # Skip common high-frequency events that aren't rule-related
        if any(skip in msg_type_lower for skip in ["device.status", "health", "client"]):
            return
            
        # Log all messages for debugging - device:update messages are especially important
        if msg_type_lower == "device:update" and DEBUG_WEBSOCKET:
            log_websocket("Rule message received (%s): %s", 
                       msg_type, str(message)[:300] + "..." if len(str(message)) > 300 else str(message))
        
        # Check if message type is rule-related
        is_rule_related = any(keyword in msg_type_lower for keyword in rule_keywords)
        
        # Special case for device:update messages - IMPORTANT for rule changes
        if msg_type_lower == "device:update":
            data_list = message.get("data", [])
            if isinstance(data_list, list):
                for item in data_list:
                    # Any device:update with cfgversion is almost always rule-related
                    if isinstance(item, dict) and "cfgversion" in item:
                        is_rule_related = True
                        log_websocket("Detected config version change in device:update: %s", item.get("cfgversion", ""))
                        break
                    # Provisioning events also indicate rule changes
                    elif isinstance(item, dict) and "provisioned" in str(item).lower():
                        is_rule_related = True
                        log_websocket("Detected provisioning event in device:update")
                        break
                    # State changes can indicate rule application
                    elif isinstance(item, dict) and "state" in item:
                        is_rule_related = True
                        log_websocket("Detected state change in device:update: %s", item.get("state", ""))
                        break
        
        # If not found in message type, check data payload for UniFi OS rule identifiers
        if not is_rule_related and "data" in message:
            data = message.get("data", {})
            
            # Check for rule-specific attributes in UniFi OS event data
            if isinstance(data, dict):
                # Check for rule identifiers
                if any(key in data for key in ["_id", "rule_id", "type", "action", "enabled"]):
                    data_str = str(data).lower()
                    is_rule_related = any(keyword in data_str for keyword in rule_keywords)
            # Check list data
            elif isinstance(data, list) and len(data) > 0:
                for item in data:
                    if isinstance(item, dict):
                        # If any item has rule-related keys, mark as rule-related
                        if any(key in item for key in ["_id", "rule_id", "type", "action", "enabled", "firewall"]):
                            is_rule_related = True
                            break
        
        # Log message details based on relevance
        if is_rule_related:
            # For rule-related messages, log with more detail
            log_websocket("Rule event received: %s - %s", 
                       msg_type, str(message)[:150] + "..." if len(str(message)) > 150 else str(message))
        elif DEBUG_WEBSOCKET:
            # Only log other messages when debug is enabled
            log_websocket("Other WebSocket message: %s", msg_type)
        
        # In case we get a reconnect message, reset connection status
        if message.get("meta", {}).get("message") == "reconnect":
            self._ws_connection_attempts = 0
            self._connection_lost_dispatched = False
            log_websocket("Received reconnect message, reset connection status")
        
        # Call message handler if registered (only for rule-related or system messages)
        if self._message_handler and (is_rule_related or "system" in msg_type_lower):
            try:
                self._message_handler(message)
            except Exception as err:
                LOGGER.error("Error in message handler: %s", err)
        
        # Only dispatch rule-related messages to avoid overwhelming Home Assistant
        if is_rule_related:
            # Dispatch message to entities
            try:
                async_dispatcher_send(self.hass, f"{SIGNAL_WEBSOCKET_MESSAGE}_{self.entry_id}", message)
            except Exception as err:
                LOGGER.error("Error dispatching WebSocket message: %s", err)