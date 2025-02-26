"""Custom WebSocket handler for UniFi Network Rules."""
from __future__ import annotations

import asyncio
from datetime import datetime
import logging
import ssl
from typing import Any, Callable, Dict, Optional, Union, List

import aiohttp
from aiohttp import WSMsgType, client_exceptions
import orjson

from ..const import LOGGER, DEBUG_WEBSOCKET

class CustomUnifiWebSocket:
    """Custom WebSocket handler for UniFi devices.
    
    This handler provides WebSocket functionality when the controller
    doesn't have built-in WebSocket support or when the built-in support
    doesn't work properly with certain UniFi devices.
    """

    def __init__(
        self,
        ws_url: str = None,
        session: aiohttp.ClientSession = None,
        host: str = None,
        site: str = "default",
        port: int = 443,
        headers: Dict[str, str] = None,
        ssl_context: Union[bool, ssl.SSLContext] = False,
        ssl: Union[bool, ssl.SSLContext] = None,  # Add 'ssl' parameter for backward compatibility
    ) -> None:
        """Initialize the WebSocket handler.
        
        Can be initialized either with a direct ws_url or with host/site parameters.
        """
        self.session = session
        self.host = host
        self.site = site
        self.port = port
        self.headers = headers or {}
        
        # Handle ssl parameter coming from both places
        self.ssl_context = ssl if ssl is not None else ssl_context
        
        # If a direct WebSocket URL is provided, use it
        if ws_url:
            self.url = ws_url
        else:
            # Auto detect URL format on creation
            self.url = self._build_url(is_unifi_os=True)  # Try UniFi OS URL first
        
        self.callback = None
        self._task = None
        self._close_requested = False
        self._last_message_time = None
        self._connection = None
        
    def _build_url(self, is_unifi_os: bool = True) -> str:
        """Build WebSocket URL based on device type."""
        base_url = f"wss://{self.host}:{self.port}"
        
        # For UniFi OS devices (UDM, UDM Pro, UDM SE), add the proxy path
        if is_unifi_os:
            return f"{base_url}/proxy/network/wss/s/{self.site}/events?clients=v2"
        
        # For classic UniFi controllers
        return f"{base_url}/wss/s/{self.site}/events?clients=v2"
    
    def _get_all_url_variants(self) -> List[str]:
        """Get all possible URL variants for different UniFi devices."""
        base_url = f"wss://{self.host}:{self.port}"
        
        # Return an ordered list of URLs to try
        return [
            # UniFi OS URL (UDM, UDM Pro)
            f"{base_url}/proxy/network/wss/s/{self.site}/events?clients=v2",
            
            # Classic Controller URL
            f"{base_url}/wss/s/{self.site}/events?clients=v2",
            
            # Direct WebSocket URL for some devices
            f"{base_url}/api/ws/sock",
            
            # USG/UXG specific URL format 
            f"{base_url}/wss/api/s/{self.site}/events"
        ]
    
    def set_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set callback for WebSocket messages."""
        self.callback = callback
        LOGGER.debug("WebSocket callback set for %s", self.url)
    
    async def start(self) -> None:
        """Start WebSocket connection."""
        if not self.callback:
            LOGGER.error("WebSocket callback not set, cannot start connection")
            return
            
        if self._task and not self._task.done():
            LOGGER.debug("WebSocket connection already running")
            return
            
        self._close_requested = False
        self._task = asyncio.create_task(self._connect())
        LOGGER.debug("Started WebSocket connection task")
        
    async def stop(self) -> None:
        """Stop WebSocket connection."""
        self._close_requested = True
        
        if self._connection:
            await self._connection.close()
            
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
                
        self._task = None
        self._connection = None
        LOGGER.debug("WebSocket connection stopped")
        
    async def _connect(self) -> None:
        """Connect to WebSocket and handle messages."""
        # If no URL is set, start with UniFi OS URL (most common for UDM devices)
        if not self.url:
            self.url = self._build_url(is_unifi_os=True)
        
        # Keep track of tried URLs to avoid duplicates
        tried_urls = set()
        
        # Get all URL variants if we're using the auto-detection approach
        if not self.url.startswith("wss://"):
            url_variants = self._get_all_url_variants()
            current_variant_index = 0
        else:
            # If we have a specific URL provided, just use that
            url_variants = [self.url]
            current_variant_index = 0
        
        # Check if we need to create a temporary session
        need_temp_session = self.session is None
        temp_session = None
        
        try:
            # Create temporary session if needed
            if need_temp_session:
                LOGGER.debug("Creating temporary session for WebSocket connection")
                temp_session = aiohttp.ClientSession()
                self.session = temp_session
            
            while current_variant_index < len(url_variants):
                # Get the next URL to try
                self.url = url_variants[current_variant_index]
                current_variant_index += 1
                
                # Skip if we've already tried this URL
                if self.url in tried_urls:
                    continue
                    
                tried_urls.add(self.url)
                
                try:
                    LOGGER.debug("Connecting to WebSocket URL: %s", self.url)
                    
                    # Add extra logging for connection attempt
                    LOGGER.debug("Connection details - Host: %s, Site: %s, Headers count: %d", 
                                self.host or "direct-url", self.site, len(self.headers) if self.headers else 0)
                    
                    # Log some of the headers (sanitizing auth values)
                    sanitized_headers = {}
                    for key, value in self.headers.items():
                        if key.lower() in ('authorization', 'cookie'):
                            sanitized_headers[key] = f"{value[:10]}...REDACTED..." if value else None
                        else:
                            sanitized_headers[key] = value
                    LOGGER.debug("Using headers: %s", sanitized_headers)
                    
                    async with self.session.ws_connect(
                        self.url,
                        headers=self.headers,
                        ssl=self.ssl_context,
                        heartbeat=15,
                        compress=12,
                    ) as ws:
                        self._connection = ws
                        LOGGER.info("Connected to UniFi WebSocket: %s", self.url)
                        
                        async for msg in ws:
                            if self._close_requested:
                                break
                                
                            self._last_message_time = datetime.now()
                            
                            if msg.type == WSMsgType.TEXT:
                                try:
                                    data = orjson.loads(msg.data)
                                    # Log messages based on DEBUG_WEBSOCKET
                                    if DEBUG_WEBSOCKET:
                                        # Get message type if available
                                        meta = data.get("meta", {})
                                        msg_type = meta.get("message", "unknown")
                                        
                                        # Check if this is a rule-related message
                                        relevant_keywords = ["firewall", "rule", "policy", "traffic", "route", "port-forward", 
                                                            "delete", "update", "insert", "events"]
                                                            
                                        # Look for keywords in message type or full message text
                                        is_rule_related = any(keyword in msg_type.lower() for keyword in relevant_keywords) or \
                                                        any(keyword in str(data).lower() for keyword in relevant_keywords)
                                        
                                        if is_rule_related:
                                            # For rule-related messages, log with more detail
                                            LOGGER.debug("Received rule-related WebSocket message (%s): %s", 
                                                msg_type, str(data)[:150] + "..." if len(str(data)) > 150 else str(data))
                                        else:
                                            # For non-rule messages, just log the type
                                            LOGGER.debug("Received WebSocket message: %s", msg_type)
                                    
                                    # Important rule messages always get logged at info level regardless of DEBUG_WEBSOCKET
                                    message_str = str(data).lower()
                                    meta = data.get("meta", {})
                                    msg_type = meta.get("message", "")
                                    if any(keyword in message_str for keyword in ["firewall", "rule", "policy", "delete"]) or \
                                       any(keyword in msg_type.lower() for keyword in ["firewall", "rule", "policy", "delete"]):
                                        LOGGER.info("Important rule-related WebSocket message (%s)", msg_type)
                                    
                                    if self.callback:
                                        self.callback(data)
                                    else:
                                        LOGGER.warning("Received WebSocket message but no callback is set")
                                except Exception as err:
                                    LOGGER.error("Error processing WebSocket message: %s", err)
                            
                            elif msg.type == WSMsgType.CLOSED:
                                LOGGER.warning("WebSocket connection closed: %s", msg.data)
                                break
                                
                            elif msg.type == WSMsgType.ERROR:
                                LOGGER.error("WebSocket error: %s", msg.data)
                                break
                                
                except client_exceptions.ClientConnectorError as err:
                    LOGGER.warning("Connection error with URL %s: %s", self.url, err)
                    # Continue to next URL
                    continue
                    
                except aiohttp.WSServerHandshakeError as err:
                    # Log the actual response to help diagnose
                    LOGGER.debug("WebSocket handshake error response: %s", getattr(err, 'message', 'No message'))
                    
                    # Continue to the next URL
                    LOGGER.warning("%s error with URL %s: %s", err.status, self.url, err)
                    continue
                    
                except Exception as err:
                    LOGGER.exception("Unexpected error with URL %s: %s", self.url, err)
                    # Continue to next URL
                    continue
                    
                finally:
                    self._connection = None
        finally:
            # Clean up temporary session if we created one
            if need_temp_session and temp_session:
                await temp_session.close()
                if self.session == temp_session:  # Only reset if it hasn't been changed
                    self.session = None
            
        # If we've tried all URLs and none worked
        LOGGER.error("All WebSocket URL variants failed. Tried %d URLs: %s", 
                  len(tried_urls), ", ".join(tried_urls))
                
        # Schedule a reconnection after a delay
        if not self._close_requested and not asyncio.current_task().cancelled():
            LOGGER.debug("WebSocket disconnected, reconnecting in 10 seconds...")
            await asyncio.sleep(10)
            if not self._close_requested:
                try:
                    await self.start()
                except Exception as restart_err:
                    LOGGER.error("Error restarting WebSocket: %s", restart_err)

    # Alias for set_callback to maintain compatibility
    def set_message_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set callback for WebSocket messages (alias for set_callback)."""
        self.set_callback(callback)
    
    def is_connected(self) -> bool:
        """Check if the WebSocket is currently connected."""
        # Check if we have an active connection
        return self._connection is not None and not self._connection.closed
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed connection status."""
        status = {
            "connected": self.is_connected(),
            "close_requested": self._close_requested,
            "url": self.url,
            "last_message_time": self._last_message_time,
        }
        
        if self._task:
            status["task_running"] = not self._task.done()
            if self._task.done():
                status["task_exception"] = str(self._task.exception()) if self._task.exception() else None
                
        return status
    
    async def connect(self) -> None:
        """Connect to WebSocket (alias for _connect)."""
        await self._connect()

    async def close(self) -> None:
        """Close the WebSocket connection (alias for stop)."""
        await self.stop()