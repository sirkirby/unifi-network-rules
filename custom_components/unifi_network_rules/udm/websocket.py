"""WebSocket module for UniFi API."""

import asyncio
import logging
import json
from datetime import datetime
import ssl
from typing import Any, Callable, Dict, Optional, Set, Union, List
from http.cookies import SimpleCookie

import aiohttp
from aiohttp import ClientWebSocketResponse, WSMsgType, ClientResponseError, client_exceptions

# Try to import orjson for better performance if available
try:
    import orjson
    USE_ORJSON = True
except ImportError:
    USE_ORJSON = False

from ..const import LOGGER, DEFAULT_SITE
from ..utils.logger import log_websocket
from .api_base import CannotConnect

class CustomUnifiWebSocket:
    """Custom WebSocket handler for UniFi devices."""
    
    def __init__(
        self,
        ws_url: str = None,
        session: aiohttp.ClientSession = None,
        host: str = None,
        site: str = DEFAULT_SITE,
        port: int = 443,
        headers: Dict[str, str] = None,
        ssl_context: Union[bool, ssl.SSLContext] = False,
        ssl: Union[bool, ssl.SSLContext] = None,  # Add 'ssl' parameter for backward compatibility
    ) -> None:
        """Initialize the WebSocket handler.
        
        Can be initialized either with a direct ws_url or with host/site parameters.
        """
        self._session = session
        self._host = host
        self._site = site if site else DEFAULT_SITE
        self._port = port
        self._headers = headers or {}
        
        # Handle ssl parameter coming from both places
        self._ssl = ssl if ssl is not None else ssl_context
        
        # If a direct WebSocket URL is provided, use it
        if ws_url:
            self._url = ws_url
        else:
            # Auto detect URL format on creation
            self._url = self._build_url(is_unifi_os=True)  # Try UniFi OS URL first
        
        # Connection management
        self._ws = None
        self._task = None
        self._connected = False
        self._callback = None
        self._message_callback = None
        self._closing = False
        self._reconnect_task = None
        self._last_message_time = None
        
    def _build_url(self, is_unifi_os: bool = True) -> str:
        """Build WebSocket URL based on device type."""
        base_url = f"wss://{self._host}:{self._port}"
        
        # For UniFi OS devices (UDM, UDM Pro, UDM SE), add the proxy path
        if is_unifi_os:
            return f"{base_url}/proxy/network/wss/s/{self._site}/events?clients=v2"
        
        # For classic UniFi controllers
        return f"{base_url}/wss/s/{self._site}/events?clients=v2"
    
    def _get_all_url_variants(self) -> List[str]:
        """Get all possible URL variants for different UniFi devices."""
        if not self._host:
            # If we don't have a host, we can't generate variants
            return [self._url] if self._url else []
            
        base_url = f"wss://{self._host}:{self._port}"
        
        # Return an ordered list of URLs to try
        return [
            # UniFi OS URL (UDM, UDM Pro)
            f"{base_url}/proxy/network/wss/s/{self._site}/events?clients=v2",
            
            # Classic Controller URL
            f"{base_url}/wss/s/{self._site}/events?clients=v2",
            
            # Direct WebSocket URL for some devices
            f"{base_url}/api/ws/sock",
            
            # USG/UXG specific URL format 
            f"{base_url}/wss/api/s/{self._site}/events"
        ]
        
    def set_message_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set the message callback."""
        self._message_callback = callback
        LOGGER.debug("WebSocket message callback set")
        
    def set_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set a callback for compatibility with older code."""
        self._callback = callback
        LOGGER.debug("WebSocket callback set")
        
    def is_connected(self) -> bool:
        """Return if socket is connected."""
        return self._connected and self._ws is not None and not self._ws.closed
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed connection status."""
        status = {
            "connected": self.is_connected(),
            "closing": self._closing,
            "url": self._url,
            "last_message_time": self._last_message_time,
        }
        
        if self._task:
            status["task_running"] = not self._task.done()
            if self._task.done():
                status["task_exception"] = str(self._task.exception()) if self._task.exception() else None
                
        return status
    
    async def connect(self) -> None:
        """Connect to the WebSocket and start listening."""
        if self._closing:
            LOGGER.debug("Not connecting as WebSocket is closing")
            return
            
        if self.is_connected():
            LOGGER.debug("Already connected, skipping connection")
            return
            
        await self._connect()
        
    async def _connect(self) -> None:
        """Connect to the WebSocket."""
        # Get list of URLs to try if we have host information
        url_variants = self._get_all_url_variants() if self._host else [self._url]
        tried_urls = set()
        
        for ws_url in url_variants:
            # Skip already tried URLs
            if ws_url in tried_urls:
                continue
                
            tried_urls.add(ws_url)
            self._url = ws_url
            
            try:
                LOGGER.debug("Connecting to WebSocket: %s", self._url)
                self._ws = await self._session.ws_connect(
                    self._url,
                    headers=self._headers,
                    ssl=self._ssl,
                    heartbeat=30,
                )
                LOGGER.debug("Connected to WebSocket")
                self._connected = True
                
                # Start listening for messages
                self._task = asyncio.create_task(self._listen())
                
                # Successfully connected, return
                return
                
            except (client_exceptions.ClientConnectorError, client_exceptions.WSServerHandshakeError) as err:
                LOGGER.warning("Connection error with URL %s: %s", self._url, err)
                # Continue to next URL
                
            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionRefusedError) as err:
                LOGGER.error("Failed to connect to WebSocket: %s", err)
                # Continue to next URL
        
        # If we get here, all URLs failed
        LOGGER.error("Failed to connect to any WebSocket URL. Tried %d URLs: %s", 
                  len(tried_urls), ", ".join(tried_urls))
        self._connected = False
        await self._schedule_reconnect()
            
    async def _listen(self) -> None:
        """Listen for WebSocket messages."""
        LOGGER.debug("Starting WebSocket listener")
        try:
            async for msg in self._ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == WSMsgType.CLOSED:
                    LOGGER.debug("WebSocket closed")
                    break
                elif msg.type == WSMsgType.ERROR:
                    LOGGER.error("WebSocket error: %s", msg.data)
                    break
        except (
            asyncio.CancelledError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
            ConnectionResetError,
        ) as exc:
            if not self._closing:
                LOGGER.error("WebSocket listener error: %s", exc)
        finally:
            self._connected = False
            if not self._closing:
                LOGGER.debug("WebSocket disconnected, scheduling reconnect")
                await self._schedule_reconnect()
            else:
                LOGGER.debug("WebSocket disconnected (closing=True)")
                
    async def _handle_message(self, data: str) -> None:
        """Handle a WebSocket message."""
        try:
            # Parse message using orjson if available for better performance
            if USE_ORJSON:
                message = orjson.loads(data)
            else:
                message = json.loads(data)
            
            # Record message time for connection health monitoring
            self._last_message_time = datetime.now()
            
            # Check if this is a rule-related message
            meta = message.get("meta", {})
            msg_type = meta.get("message", "unknown")
            
            relevant_keywords = ["firewall", "rule", "policy", "traffic", "route", "port-forward", 
                                "delete", "update", "insert", "events"]
                                
            # Look for keywords in message type or full message text
            is_rule_related = any(keyword in msg_type.lower() for keyword in relevant_keywords) or \
                            any(keyword in str(message).lower() for keyword in relevant_keywords)
            
            if is_rule_related:
                # For rule-related messages, log with more detail
                log_websocket("Rule message (%s): %s", msg_type, str(message)[:150] + "..." if len(str(message)) > 150 else str(message))
            else:
                # For non-rule messages, just log the type
                log_websocket("WebSocket message: %s", msg_type)
            
            # Call message handler if set
            if self._message_callback:
                self._message_callback(message)
            elif self._callback:
                # Fallback to legacy callback
                self._callback(message)
            else:
                LOGGER.debug("WebSocket message received but no callback set: %s", message.get("meta", {}).get("message", ""))
                
        except json.JSONDecodeError as err:
            LOGGER.error("Failed to parse message: %s", err)
            
    async def _schedule_reconnect(self) -> None:
        """Schedule a reconnect."""
        if self._closing:
            LOGGER.debug("Not scheduling reconnect as WebSocket is closing")
            return
            
        # Cancel any existing reconnect task
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            
        # Schedule reconnect with 10 second delay
        LOGGER.debug("Scheduling WebSocket reconnect in 10 seconds")
        self._reconnect_task = asyncio.create_task(self._delayed_reconnect(10))
        
    async def _delayed_reconnect(self, delay: int) -> None:
        """Wait for the specified delay and then reconnect."""
        if self._closing:
            return
            
        try:
            await asyncio.sleep(delay)
            await self.connect()
        except asyncio.CancelledError:
            pass
            
    async def close(self) -> None:
        """Close the WebSocket connection."""
        self._closing = True
        
        # Cancel the reconnect task if it exists
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            
        # Cancel the listener task if it exists
        if self._task and not self._task.done():
            self._task.cancel()
            
        # Close the WebSocket if it exists
        if self._ws and not self._ws.closed:
            await self._ws.close()
            
        self._connected = False
        self._closing = False
        LOGGER.debug("WebSocket connection closed")
        
    async def stop(self) -> None:
        """Stop the WebSocket connection (alias for close)."""
        await self.close()


class WebSocketMixin:
    """Mixin to add WebSocket functionality to the API."""

    def set_websocket_path_prefix(self, prefix: str) -> None:
        """Set the websocket path prefix for UniFi OS compatibility."""
        self._websocket_path_prefix = prefix
        LOGGER.debug("Set websocket path prefix to: %s", prefix)

    async def start_websocket(self) -> None:
        """Start WebSocket connection."""
        # Don't proceed if we're currently rate limited
        if self._rate_limited:
            current_time = asyncio.get_event_loop().time()
            if current_time < self._rate_limit_until:
                wait_time = int(self._rate_limit_until - current_time)
                LOGGER.warning(
                    "Rate limit in effect. Cannot start WebSocket for %d more seconds.",
                    wait_time
                )
                raise CannotConnect(f"Rate limited. Try again in {wait_time} seconds")
                
        # Log the attempt with more details
        LOGGER.info("Starting WebSocket connection for real-time event notifications")
        
        # Allow only one active WebSocket attempt at a time
        if hasattr(self, "_websocket_attempt_lock"):
            if self._websocket_attempt_lock.locked():
                LOGGER.warning("Another WebSocket connection attempt is already in progress, skipping")
                return
        else:
            self._websocket_attempt_lock = asyncio.Lock()
            
        # Acquire lock to ensure only one WebSocket attempt at a time
        async with self._websocket_attempt_lock:
            try:
                # If we have a controller and WebSocket, try the built-in WebSocket first
                if self.controller and hasattr(self.controller, "start_websocket"):
                    LOGGER.debug("Attempting to use built-in WebSocket connection")
                    try:
                        # This will use the aiounifi built-in WebSocket
                        await self.controller.start_websocket()
                        LOGGER.info("Successfully connected using built-in WebSocket")
                        
                        # Set the WebSocket message handler if available
                        if self._ws_message_handler and hasattr(self.controller, "ws_handler"):
                            self.controller.ws_handler = self._ws_message_handler
                            LOGGER.debug("WebSocket message handler set on controller")
                        elif not hasattr(self.controller, "ws_handler"):
                            LOGGER.warning("Controller doesn't have ws_handler attribute, "
                                        "WebSocket messages might not be processed correctly")
                        
                        return
                    except Exception as err:
                        LOGGER.warning("Built-in WebSocket failed with %s: %s. Will try custom handler.", 
                                    type(err).__name__, err)
                        # Continue to custom handler
                else:
                    LOGGER.debug("No built-in WebSocket available, using custom handler")
                
                # If we get here, the built-in WebSocket failed or doesn't exist
                
                # Clear previous custom websocket if any
                if hasattr(self, "_custom_websocket") and self._custom_websocket:
                    await self._custom_websocket.close()
                    self._custom_websocket = None
                
                # Get authentication headers and cookies before starting the WebSocket
                auth_headers = await self._get_auth_headers()
                
                # Set up headers
                headers = {}
                if auth_headers:
                    headers.update(auth_headers)
                    
                LOGGER.debug("Creating custom WebSocket with %d headers", len(headers))
                
                # Get site from property or default
                site = getattr(self, "site", DEFAULT_SITE)
                
                # Extract base host without port
                base_host = self.host.split(":")[0]
                
                # Create custom WebSocket with support for multiple URL formats
                self._custom_websocket = CustomUnifiWebSocket(
                    host=base_host,
                    site=site,
                    port=443,
                    session=self._session,
                    headers=headers,
                    ssl=False if "localhost" in base_host else True
                )
                
                # Set message handler if available
                if self._ws_message_handler:
                    LOGGER.debug("Setting message handler on new custom WebSocket")
                    self._custom_websocket.set_message_callback(self._ws_message_handler)
                    
                LOGGER.debug("WebSocket callback set for %s", base_host)
                
                # Start the WebSocket connection
                self._ws_connect_task = asyncio.create_task(self._custom_websocket.connect())
                LOGGER.info("Created custom WebSocket handler for %s", base_host)
                
                # Monitor the WebSocket health
                self._ws_health_monitor = asyncio.create_task(
                    self._monitor_websocket_health()
                )
                
                # We successfully started the WebSocket connection task
                LOGGER.info("Custom WebSocket started successfully")
                return
            
            except Exception as err:
                self._consecutive_failures += 1
                LOGGER.error("Error starting WebSocket: %s", str(err))
                if not self._rate_limited and self._consecutive_failures >= 3:
                    backoff = min(30 * (2 ** (self._consecutive_failures - 1)), self._max_backoff)
                    self._rate_limited = True
                    self._rate_limit_until = asyncio.get_event_loop().time() + backoff
                    LOGGER.warning(
                        "Multiple consecutive WebSocket failures. Rate limiting for %d seconds.",
                        backoff
                    )
                raise

    async def _monitor_websocket_health(self) -> None:
        """Monitor WebSocket health and attempt to reconnect if issues are detected."""
        LOGGER.debug("Starting WebSocket health monitoring")
        check_interval = 60  # Check every 60 seconds
        
        try:
            while True:
                await asyncio.sleep(check_interval)
                
                # Check if our custom WebSocket is connected
                if hasattr(self, "_custom_websocket") and self._custom_websocket:
                    if not self._custom_websocket.is_connected():
                        LOGGER.warning("WebSocket connection appears to be disconnected, attempting to reconnect")
                        try:
                            # Close existing connection
                            await self._custom_websocket.close()
                            self._custom_websocket = None
                            
                            # Attempt to reconnect
                            await self.start_websocket()
                            LOGGER.info("Successfully reconnected WebSocket after health check")
                        except Exception as err:
                            LOGGER.error("Failed to reconnect WebSocket: %s", err)
                else:
                    # No custom WebSocket, check built-in
                    if hasattr(self.controller, "websocket") and hasattr(self.controller.websocket, "state"):
                        if self.controller.websocket.state != "running":
                            LOGGER.warning("Built-in WebSocket not in running state, attempting to reconnect")
                            try:
                                await self.controller.stop_websocket()
                                await self.controller.start_websocket()
                                LOGGER.info("Successfully reconnected built-in WebSocket after health check")
                            except Exception as err:
                                LOGGER.error("Failed to reconnect built-in WebSocket: %s", err)
        except asyncio.CancelledError:
            LOGGER.debug("WebSocket health monitor task cancelled")
        except Exception as err:
            LOGGER.error("Error in WebSocket health monitor: %s", err)

    async def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers through direct authentication.
        
        This is a fallback method when normal authentication headers are not available.
        It attempts to authenticate directly with the UniFi controller to get valid tokens.
        """
        headers = {}
        try:
            LOGGER.debug("Attempting direct authentication to get WebSocket tokens")
            
            # Extract base host without port
            base_host = self.host.split(":")[0]
            
            # Different UniFi controller versions use different auth endpoints
            # Try the UniFi OS authentication endpoint first
            login_url = f"https://{base_host}:443/api/auth/login"
            LOGGER.debug("Attempting authentication using URL: %s with SSL verify: %s", 
                        login_url, self.verify_ssl)
            
            login_data = {
                "username": self.username,
                "password": self.password,
                "remember": True
            }
            
            # Use our session to make the request
            try:
                async with self._session.post(
                    login_url, 
                    json=login_data, 
                    ssl=self.verify_ssl,
                    allow_redirects=True
                ) as response:
                    if response.status == 200:
                        LOGGER.debug("Direct UniFi OS authentication successful")
                        
                        # Extract cookies from response
                        if response.cookies:
                            cookies = SimpleCookie()
                            for key, cookie in response.cookies.items():
                                cookies[key] = cookie.value
                                
                            cookie_header = cookies.output(header="", sep=";").strip()
                            if cookie_header:
                                headers["Cookie"] = cookie_header
                                LOGGER.debug("Got authentication cookies")
                        
                        # Extract CSRF token if available
                        csrf_token = response.headers.get('X-CSRF-Token')
                        if csrf_token:
                            headers["X-CSRF-Token"] = csrf_token
                            LOGGER.debug("Got X-CSRF-Token from response")
                            
                    else:
                        LOGGER.warning("UniFi OS authentication failed: %s", response.status)
            except Exception as err:
                LOGGER.debug("Error with UniFi OS authentication: %s", err)
            
            # If that failed (no cookies), try the classic controller endpoint
            if "Cookie" not in headers:
                login_url = f"https://{base_host}:443/api/login"
                LOGGER.debug("Attempting classic authentication using URL: %s", login_url)
                
                login_data = {
                    "username": self.username,
                    "password": self.password,
                    "strict": True
                }
                
                try:
                    async with self._session.post(
                        login_url, 
                        json=login_data, 
                        ssl=self.verify_ssl
                    ) as response:
                        if response.status == 200:
                            LOGGER.debug("Direct classic controller authentication successful")
                            
                            # Extract cookies from response
                            if response.cookies:
                                cookies = SimpleCookie()
                                for key, cookie in response.cookies.items():
                                    cookies[key] = cookie.value
                                    
                                cookie_header = cookies.output(header="", sep=";").strip()
                                if cookie_header:
                                    headers["Cookie"] = cookie_header
                                    LOGGER.debug("Got authentication cookies from classic endpoint")
                        else:
                            LOGGER.warning("Classic controller authentication failed: %s", response.status)
                except Exception as err:
                    LOGGER.debug("Error with classic controller authentication: %s", err)
            
            # Report success or failure
            if headers:
                LOGGER.debug("Direct authentication successful, got %d headers", len(headers))
                return headers
            else:
                LOGGER.warning("All direct authentication methods failed")
                return {}
                
        except Exception as err:
            LOGGER.error("Error in direct authentication: %s", err)
            return {}

    def set_websocket_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set callback to be used by controller on websocket events."""
        LOGGER.debug("Setting WebSocket callback")
        self._ws_message_handler = callback
        
        # Set on controller if available
        if self.controller and hasattr(self.controller, "ws_handler"):
            LOGGER.debug("Setting callback on controller ws_handler")
            self.controller.ws_handler = callback
        else:
            LOGGER.debug("Controller doesn't have ws_handler attribute, will use custom handler")
        
        # Set on custom WebSocket if it exists
        if hasattr(self, "_custom_websocket") and self._custom_websocket:
            LOGGER.debug("Setting callback on custom WebSocket")
            self._custom_websocket.set_message_callback(callback)

    async def stop_websocket(self) -> None:
        """Stop websocket connection."""
        if self.controller and hasattr(self.controller, "stop_websocket"):
            try:
                await self.controller.stop_websocket()
            except Exception as err:
                LOGGER.warning("Error stopping built-in WebSocket: %s", err)
                
        # Also stop our custom WebSocket if it exists
        if hasattr(self, "_custom_websocket") and self._custom_websocket:
            try:
                await self._custom_websocket.close()
                LOGGER.debug("Custom WebSocket stopped")
            except Exception as err:
                LOGGER.warning("Error stopping custom WebSocket: %s", err)