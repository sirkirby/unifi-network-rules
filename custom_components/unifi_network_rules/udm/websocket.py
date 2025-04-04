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

from ..const import LOGGER, DEFAULT_SITE, LOG_WEBSOCKET
from ..utils.logger import log_websocket
from .api_base import CannotConnect

class CustomUnifiWebSocket:
    """WebSocket handler for modern UniFi OS consoles.
    
    Specialized for UDM, UDM Pro, UDM SE, Dream Machine, and other UniFi OS devices.
    Handles the WebSocket connection to receive real-time events from the UniFi Network
    application running on these devices.
    """
    
    def __init__(
        self,
        ws_url: str = None,
        session: aiohttp.ClientSession = None,
        host: str = None,
        site: str = DEFAULT_SITE,
        port: int = 443,
        headers: Dict[str, str] = None,
        ssl_context: Union[bool, ssl.SSLContext] = False,
        ssl: Union[bool, ssl.SSLContext] = None,
    ) -> None:
        """Initialize the UniFi OS WebSocket handler.
        
        Args:
            ws_url: Direct WebSocket URL if known (optional)
            session: Existing aiohttp session to reuse
            host: UniFi OS console hostname or IP address
            site: UniFi Network site name (default: "default")
            port: HTTPS port (default: 443)
            headers: Authentication headers including cookies and CSRF token
            ssl_context/ssl: SSL verification settings
        """
        self._session = session or aiohttp.ClientSession()
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
            # Use the primary UniFi OS WebSocket URL
            self._url = self._build_url()
        
        # Connection management
        self._ws = None
        self._task = None
        self._connected = False
        self._callback = None
        self._message_callback = None
        self._closing = False
        self._reconnect_task = None
        self._last_message_time = None
        self._should_stop = False  # Flag to control the connection loop
        self._connection_error_count = 0
        
    def _build_url(self) -> str:
        """Build WebSocket URL for UniFi OS console."""
        base_url = f"wss://{self._host}:{self._port}"
        return f"{base_url}/proxy/network/wss/s/{self._site}/events"
    
    def _get_all_url_variants(self) -> List[str]:
        """Get possible WebSocket URL variants for modern UniFi OS consoles."""
        if not self._host:
            # If we don't have a host, we can't generate variants
            return [self._url] if self._url else []
            
        base_url = f"wss://{self._host}:{self._port}"
        
        # Return a focused list of only modern UniFi OS console URLs
        return [
            # Modern UniFi OS Console (UDM, UDM Pro, UDM SE, UDR, Dream Machine, etc.)
            f"{base_url}/proxy/network/wss/s/{self._site}/events",
            
            # Alternative format with client version parameter, also for modern consoles
            f"{base_url}/proxy/network/wss/s/{self._site}/events?clients=v2",
            
            # New WebSocket format with namespace for recent UniFi OS versions
            f"{base_url}/api/ws/namespace/network"
        ]
        
    def set_message_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set the message callback."""
        self._message_callback = callback
        if LOG_WEBSOCKET:
            LOGGER.debug("WebSocket message callback set")
        
    def set_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set a callback for compatibility with older code."""
        self._callback = callback
        if LOG_WEBSOCKET:
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
        """Connect to the websocket and start receiving messages."""
        if self._connected:
            if LOG_WEBSOCKET:
                LOGGER.debug("WebSocket is already connected, skipping connect")
            return

        # Set up reconnect backoff
        reconnect_delay = 0
        max_reconnect_delay = 300  # 5 minutes
        reconnect_attempt = 0
        
        while not self._should_stop:
            try:
                # Clear previous websocket connection if any
                if self._ws and not self._ws.closed:
                    await self._ws.close()
                    self._ws = None
                
                # Sleep for reconnect delay if not the first attempt
                if reconnect_attempt > 0:
                    LOGGER.info("WebSocket reconnecting in %d seconds (attempt #%d)...", 
                               reconnect_delay, reconnect_attempt)
                    await asyncio.sleep(reconnect_delay)
                
                # Build WS URL with varying strategies based on reconnect attempt
                if reconnect_attempt < 3:
                    ws_url = self._build_url()
                    if LOG_WEBSOCKET:
                        LOGGER.debug("Connecting to WebSocket using primary URL: %s", ws_url)
                else:
                    urls = self._get_all_url_variants()
                    url_index = min(reconnect_attempt - 3, len(urls) - 1)
                    ws_url = urls[url_index % len(urls)]
                    if LOG_WEBSOCKET:
                        LOGGER.debug("Connecting to WebSocket using fallback URL (#%d): %s", 
                                    url_index + 1, ws_url)
                
                # Log connection headers for debugging (redacting sensitive info)
                if LOG_WEBSOCKET and LOGGER.isEnabledFor(logging.DEBUG):
                    safe_headers = {k: v if k.lower() not in ("cookie", "x-csrf-token") else "[REDACTED]" 
                                for k, v in self._headers.items()}
                    LOGGER.debug("WebSocket connection headers: %s", safe_headers)
                
                # Connect to the WebSocket with timeout
                try:
                    connect_timeout = aiohttp.ClientTimeout(total=30)
                    async with asyncio.timeout(30):
                        self._ws = await self._session.ws_connect(
                            ws_url,
                            headers=self._headers,
                            ssl=self._ssl,
                            timeout=connect_timeout,
                            heartbeat=30
                        )
                        LOGGER.info("WebSocket connected successfully to %s", ws_url)
                except asyncio.TimeoutError:
                    LOGGER.warning("WebSocket connection timed out after 30 seconds")
                    raise ConnectionError("WebSocket connection timeout")
                
                # Reset reconnect parameters on successful connection
                reconnect_attempt = 0
                reconnect_delay = 0
                self._connected = True
                self._connection_error_count = 0
                self._last_message_time = asyncio.get_event_loop().time()
                
                # Process messages until connection is closed
                async for msg in self._ws:
                    # Track most recent message time
                    self._last_message_time = asyncio.get_event_loop().time()
                    
                    # Process message based on type
                    if msg.type == WSMsgType.TEXT:
                        await self._handle_message(msg.data)
                    elif msg.type == WSMsgType.BINARY:
                        if LOG_WEBSOCKET:
                            LOGGER.debug("Received binary WebSocket message (len: %d bytes)", len(msg.data))
                    elif msg.type == WSMsgType.CLOSED:
                        LOGGER.info("WebSocket connection closed by server, will reconnect")
                        break
                    elif msg.type == WSMsgType.ERROR:
                        LOGGER.error("WebSocket connection error: %s", msg.data)
                        break
                    elif msg.type == WSMsgType.CLOSING:
                        if LOG_WEBSOCKET:
                            LOGGER.debug("WebSocket closing")
                        break
                    elif msg.type == WSMsgType.CLOSE:
                        if LOG_WEBSOCKET:
                            LOGGER.debug("WebSocket close frame received")
                        break
                
                # If we get here, the connection is closed
                LOGGER.info("WebSocket connection closed, reconnecting...")
                
            except asyncio.CancelledError:
                if LOG_WEBSOCKET:
                    LOGGER.debug("WebSocket connect task cancelled")
                self._should_stop = True
                break
            
            except (ConnectionError, ClientResponseError) as conn_err:
                # Log specific error types with details to help diagnose
                err_type = type(conn_err).__name__
                self._connection_error_count += 1
                LOGGER.error("WebSocket %s: %s (attempt #%d)", 
                            err_type, str(conn_err), reconnect_attempt + 1)
                
                # Try to provide more diagnostic information for common errors
                if isinstance(conn_err, ClientResponseError):
                    LOGGER.error("HTTP error status: %d, message: %s", 
                               getattr(conn_err, "status", 0), getattr(conn_err, "message", "Unknown"))
                    
                    # Specific handling for authentication errors
                    if getattr(conn_err, "status", 0) in (401, 403):
                        LOGGER.warning("Authentication error detected. Will try to refresh authentication.")
                        # Force attempt to refresh auth on next iteration
                        reconnect_attempt = 2  # This will make next attempt refresh auth
                
            except (aiohttp.ClientError, client_exceptions.WSServerHandshakeError) as client_err:
                # These are network-level errors
                err_type = type(client_err).__name__
                self._connection_error_count += 1
                LOGGER.error("WebSocket client error: %s - %s (attempt #%d)", 
                            err_type, str(client_err), reconnect_attempt + 1)
                
            except Exception as err:
                # Unexpected error
                err_type = type(err).__name__
                self._connection_error_count += 1
                LOGGER.exception("Unexpected WebSocket error: %s - %s (attempt #%d)", 
                               err_type, str(err), reconnect_attempt + 1)
                
            finally:
                # Clean up WebSocket for this iteration
                self._connected = False
                if self._ws and not self._ws.closed:
                    await self._ws.close()
                    self._ws = None
                
                # Increase reconnect parameters
                reconnect_attempt += 1
                reconnect_delay = min(2 ** min(reconnect_attempt, 8), max_reconnect_delay)
                
        # Final cleanup
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        self._connected = False
        if LOG_WEBSOCKET:
            LOGGER.debug("WebSocket connection task ended")
        
    async def _handle_message(self, data: str) -> None:
        """Handle a WebSocket message."""
        # Check for empty messages
        if not data or not data.strip():
            if LOG_WEBSOCKET:
                LOGGER.debug("Received empty WebSocket message, ignoring")
            return
        
        try:
            # Parse message using orjson if available for better performance
            if USE_ORJSON:
                message = orjson.loads(data)
            else:
                message = json.loads(data)
            
            # Verify we have a valid message
            if not message or not isinstance(message, dict):
                if LOG_WEBSOCKET:
                    LOGGER.debug("Received invalid WebSocket message format: %s", type(message))
                return
            
            # Record message time for connection health monitoring
            self._last_message_time = datetime.now()
            
            # Extract message metadata
            meta = message.get("meta", {})
            msg_type = meta.get("message", "unknown")
            
            # Define keywords for rule-related messages
            rule_keywords = [
                "firewall", "rule", "policy", "traffic", "route", "port-forward", 
                "nat", "action", "ipgroup", "dnat", "snat", "drop", "reject", "accept",
                "delete", "update", "insert", "add"
            ]
            
            # Variables for efficient checking
            msg_type_lower = msg_type.lower()
            
            # Skip device status and client updates that come in at high frequency
            if "device.status" in msg_type_lower or "device-state" in msg_type_lower:
                if LOG_WEBSOCKET:
                    log_websocket("Ignoring high-frequency device status update: %s", msg_type)
                return
            
            if "client" in msg_type_lower and not any(kw in msg_type_lower for kw in rule_keywords):
                if LOG_WEBSOCKET:
                    log_websocket("Ignoring client update: %s", msg_type)
                return
            
            # Look for keywords in message type 
            is_rule_related = any(keyword in msg_type_lower for keyword in rule_keywords)
            
            # If not found in message type, check specific data fields that would indicate rule relevance
            if not is_rule_related:
                # Extract data section for deeper inspection
                data_section = message.get("data", {})
                
                # Check data keys for rule-related terms
                if isinstance(data_section, dict):
                    data_keys = " ".join(data_section.keys()).lower()
                    is_rule_related = any(keyword in data_keys for keyword in rule_keywords)
                    
                    # Also check key values if they are strings
                    if not is_rule_related:
                        for k, v in data_section.items():
                            if isinstance(v, str) and any(keyword in v.lower() for keyword in rule_keywords):
                                is_rule_related = True
                                break
            
            # Log based on message type and relevance
            callback_exists = self._message_callback or self._callback
            
            if is_rule_related:
                # For rule-related messages, log type if callback exists, full details if LOG_WEBSOCKET is on
                if callback_exists:
                    LOGGER.info("WebSocket rule message processed: %s", msg_type)
                if LOG_WEBSOCKET:
                    log_websocket("Rule message details (%s): %s", 
                               msg_type, str(message)[:150] + "..." if len(str(message)) > 150 else str(message))
            else:
                # For non-rule messages, log only if LOG_WEBSOCKET is on
                if LOG_WEBSOCKET:
                    log_websocket("Other WebSocket message: %s", msg_type)
            
            # Call message handler if set
            if self._message_callback:
                # Pass the message to callback only if it's rule-related or a system-level message
                if is_rule_related or "system" in msg_type_lower or "event" in msg_type_lower:
                    self._message_callback(message)
            elif self._callback:
                # Fallback to legacy callback
                self._callback(message)
            elif LOG_WEBSOCKET: # Only log if no callback and debug enabled
                 LOGGER.debug("WebSocket message received but no callback set: %s", msg_type)
                
        except json.JSONDecodeError as err:
            if not data or data.strip() == "":
                if LOG_WEBSOCKET:
                    LOGGER.debug("Received empty or whitespace-only WebSocket message")
            else:
                LOGGER.error("Failed to parse message: %s - Data: %s", err, data[:100] if len(data) > 100 else data)
        except Exception as err:
            LOGGER.error("Error processing WebSocket message: %s", err)
            
    async def _schedule_reconnect(self) -> None:
        """Schedule a reconnect."""
        if self._closing:
            if LOG_WEBSOCKET:
                 LOGGER.debug("Not scheduling reconnect as WebSocket is closing")
            return
            
        # Cancel any existing reconnect task
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            
        # Schedule reconnect with 10 second delay
        if LOG_WEBSOCKET:
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
        """Close WebSocket connection."""
        # Set flags to stop the connection loop
        self._closing = True
        self._should_stop = True
        
        # Close WebSocket connection if connected
        if self._ws and not self._ws.closed:
            if LOG_WEBSOCKET:
                LOGGER.debug("Closing active WebSocket connection")
            await self._ws.close()
            self._ws = None
        
        # Cancel any pending tasks
        if self._task and not self._task.done():
            if LOG_WEBSOCKET:
                LOGGER.debug("Cancelling WebSocket task")
            self._task.cancel()
        
        if self._reconnect_task and not self._reconnect_task.done():
            if LOG_WEBSOCKET:
                LOGGER.debug("Cancelling reconnect task")
            self._reconnect_task.cancel()
        
        self._connected = False
        if LOG_WEBSOCKET:
            LOGGER.debug("WebSocket connection closed")
        
    async def stop(self) -> None:
        """Stop the WebSocket connection (alias for close)."""
        await self.close()


class WebSocketMixin:
    """Mixin to add WebSocket functionality to the API."""

    def set_websocket_path_prefix(self, prefix: str) -> None:
        """Set the websocket path prefix for UniFi OS compatibility."""
        self._websocket_path_prefix = prefix
        if LOG_WEBSOCKET:
            LOGGER.debug("Set websocket path prefix to: %s", prefix)

    async def start_websocket(self) -> None:
        """Start WebSocket connection for real-time event notifications."""
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
                    
                if LOG_WEBSOCKET:
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
                    if LOG_WEBSOCKET:
                        LOGGER.debug("Setting message handler on new custom WebSocket")
                    self._custom_websocket.set_message_callback(self._ws_message_handler)
                    
                if LOG_WEBSOCKET:
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
                # If our custom implementation fails, try the built-in as a last resort
                if self.controller and hasattr(self.controller, "start_websocket"):
                    try:
                        if LOG_WEBSOCKET:
                             LOGGER.debug("Custom WebSocket failed, attempting to use built-in WebSocket as fallback")
                        # Set timeout to avoid hanging
                        async with asyncio.timeout(30):
                            await self.controller.start_websocket()
                        LOGGER.info("Successfully connected using built-in WebSocket fallback")
                        
                        # Set the WebSocket message handler if available
                        if self._ws_message_handler and hasattr(self.controller, "ws_handler"):
                            self.controller.ws_handler = self._ws_message_handler
                            if LOG_WEBSOCKET:
                                LOGGER.debug("WebSocket message handler set on controller")
                        return
                    except (asyncio.TimeoutError, Exception) as fallback_err:
                        LOGGER.warning("Built-in WebSocket fallback also failed: %s", fallback_err)
                        raise
                else:
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
        if LOG_WEBSOCKET:
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
            if LOG_WEBSOCKET:
                LOGGER.debug("WebSocket health monitor task cancelled")
        except Exception as err:
            LOGGER.error("Error in WebSocket health monitor: %s", err)

    async def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for the WebSocket connection.
        
        For modern UniFi OS consoles, this requires obtaining session cookies
        and a valid CSRF token from the existing session.
        """
        headers = {}
        try:
            if LOG_WEBSOCKET:
                LOGGER.debug("Attempting to get authentication headers for WebSocket")
            
            # First, try to extract headers from the existing session
            if hasattr(self, "_session") and self._session:
                try:
                    # Get cookies from the client session
                    session_cookies = self._session.cookie_jar.filter_cookies(f"https://{self.host}")
                    if session_cookies:
                        cookies = SimpleCookie()
                        for name, cookie in session_cookies.items():
                            cookies[name] = cookie.value
                        cookie_header = cookies.output(header="", sep=";").strip()
                        if cookie_header:
                            headers["Cookie"] = cookie_header
                            if LOG_WEBSOCKET:
                                LOGGER.debug("Using %d cookies from existing session", len(session_cookies))
                            
                    # Check if there's a CSRF token in session (required for UniFi OS)
                    if hasattr(self, "_csrf_token") and self._csrf_token:
                        headers["X-CSRF-Token"] = self._csrf_token
                        if LOG_WEBSOCKET:
                            LOGGER.debug("Using cached CSRF token")
                    
                    # If we got both cookies and CSRF token, we're done
                    if "Cookie" in headers and "X-CSRF-Token" in headers:
                        if LOG_WEBSOCKET:
                            LOGGER.debug("Successfully obtained authentication headers from session")
                        return headers
                except Exception as session_err:
                    if LOG_WEBSOCKET:
                         LOGGER.debug("Could not get cookies from session: %s", session_err)
            
            # ========== Direct Authentication Attempt ==========
            # If we couldn't extract from session, try direct authentication
            
            # Extract base host without port
            base_host = self.host.split(":")[0]
            
            # Modern UniFi OS authentication endpoint
            login_url = f"https://{base_host}:443/api/auth/login"
            if LOG_WEBSOCKET:
                LOGGER.debug("Attempting authentication using UniFi OS URL: %s", login_url)
            
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
                        if LOG_WEBSOCKET:
                            LOGGER.debug("UniFi OS authentication successful")
                        
                        # Extract cookies from response
                        if response.cookies:
                            cookies = SimpleCookie()
                            for key, cookie in response.cookies.items():
                                cookies[key] = cookie.value
                                
                            cookie_header = cookies.output(header="", sep=";").strip()
                            if cookie_header:
                                headers["Cookie"] = cookie_header
                                if LOG_WEBSOCKET:
                                    LOGGER.debug("Got %d cookies from auth response", len(response.cookies))
                        
                        # Extract CSRF token if available (critical for UniFi OS)
                        csrf_token = response.headers.get('X-CSRF-Token')
                        if csrf_token:
                            headers["X-CSRF-Token"] = csrf_token
                            # Cache it for future use
                            self._csrf_token = csrf_token
                            if LOG_WEBSOCKET:
                                LOGGER.debug("Got X-CSRF-Token: %s", csrf_token[:5] + "..." if len(csrf_token) > 5 else csrf_token)
                    else:
                        LOGGER.warning("UniFi OS authentication failed with status %s", response.status)
                        
                        # Log more details in debug mode
                        try:
                            response_text = await response.text()
                            if LOG_WEBSOCKET:
                                LOGGER.debug("Auth response: %s", response_text[:100])
                        except Exception:
                            pass
            except Exception as err:
                LOGGER.error("Error with UniFi OS authentication: %s", err)
            
            # ========== Final Result ==========
            # Report success or failure
            if headers:
                if LOG_WEBSOCKET:
                    LOGGER.debug("Authentication successful, got headers: %s", 
                               ", ".join(headers.keys()))
                return headers
            else:
                LOGGER.warning("UniFi OS authentication failed")
                return {}
                
        except Exception as err:
            LOGGER.error("Error in authentication process: %s", err)
            return {}

    def set_websocket_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set callback to be used by controller on websocket events."""
        if LOG_WEBSOCKET:
            LOGGER.debug("Setting WebSocket callback")
        self._ws_message_handler = callback
        
        # Set on controller if available
        if self.controller and hasattr(self.controller, "ws_handler"):
            if LOG_WEBSOCKET:
                LOGGER.debug("Setting callback on controller ws_handler")
            self.controller.ws_handler = callback
        elif LOG_WEBSOCKET:
             LOGGER.debug("Controller doesn't have ws_handler attribute, will use custom handler")
        
        # Set on custom WebSocket if it exists
        if hasattr(self, "_custom_websocket") and self._custom_websocket:
            if LOG_WEBSOCKET:
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
                if LOG_WEBSOCKET:
                    LOGGER.debug("Custom WebSocket stopped")
            except Exception as err:
                LOGGER.warning("Error stopping custom WebSocket: %s", err)