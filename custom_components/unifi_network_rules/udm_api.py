"""UDM API for controlling UniFi Dream Machine."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple, Callable, Union
import asyncio
import ssl
import importlib.util
from aiohttp import CookieJar, WSMsgType, ClientResponseError
import aiohttp
import re
from datetime import datetime, timedelta
from http.cookies import SimpleCookie
import json

# Try to import from aiounifi with version checking and fallbacks
try:
    from aiounifi import Controller
    from aiounifi.models.configuration import Configuration
    from aiounifi.models.api import ApiRequest, ApiRequestV2
    from aiounifi.models.firewall_policy import FirewallPolicy, FirewallPolicyUpdateRequest
    
    # Check if the needed model files exist before importing
    try:
        from aiounifi.models.traffic_route import TrafficRoute, TrafficRouteSaveRequest
    except ImportError:
        # Create a more helpful error message
        raise ImportError(
            "Your aiounifi version is missing TrafficRoute models. "
            "Please make sure you're using a version that supports UniFi Network Rules."
        )
    
    try:
        from aiounifi.models.firewall_policy import FirewallPolicy, FirewallPolicyUpdateRequest
    except ImportError:
        # Create a more helpful error message
        raise ImportError(
            "Your aiounifi version is missing FirewallPolicy models. "
            "This happens when the built-in UniFi integration loads an older version first. "
            "Try restarting Home Assistant or update to the latest aiounifi version."
        )
    
    try:
        from aiounifi.models.traffic_rule import TrafficRule, TrafficRuleEnableRequest
    except ImportError:
        # Create a more helpful error message
        raise ImportError(
            "Your aiounifi version is missing TrafficRule models. "
            "Please make sure you're using a version that supports UniFi Network Rules."
        )
    
    try:
        from aiounifi.models.port_forward import PortForward, PortForwardEnableRequest
    except ImportError:
        # Create a more helpful error message
        raise ImportError(
            "Your aiounifi version is missing PortForward models. "
            "Please make sure you're using a version that supports UniFi Network Rules."
        )
    
    from aiounifi.errors import (
        AiounifiException,
        BadGateway,
        LoginRequired,
        RequestError,
        ResponseError,
        ServiceUnavailable,
        Unauthorized,
    )
except ImportError as err:
    raise ImportError(
        f"Failed to import required aiounifi modules: {err}. "
        "This integration requires a version of aiounifi that supports "
        "firewall policies, traffic rules, port forwarding and traffic routes. "
        "If you're seeing this after the first restart, try restarting Home Assistant again."
    ) from err

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.const import CONF_VERIFY_SSL
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    LOGGER, 
    DEFAULT_SITE, 
    LEGACY_FIREWALL_RULES_ENDPOINT,
    SDN_STATUS_ENDPOINT,
    DEBUG_WEBSOCKET,  # Keep for compatibility
    API_ENDPOINT_FIREWALL_POLICIES,
    API_ENDPOINT_FIREWALL_POLICIES_BATCH_DELETE,
    API_ENDPOINT_TRAFFIC_RULES,
    API_ENDPOINT_TRAFFIC_RULE_DETAIL,
    API_ENDPOINT_TRAFFIC_ROUTES,
    API_ENDPOINT_TRAFFIC_ROUTE_DETAIL,
)
from .helpers.rule import get_rule_id
from .utils.diagnostics import log_controller_diagnostics
from .utils.websocket_handler import CustomUnifiWebSocket
from .utils.logger import log_websocket, log_api

class UnifiNetworkRulesError(HomeAssistantError):
    """Base error for UniFi Network Rules."""

class CannotConnect(UnifiNetworkRulesError):
    """Error to indicate we cannot connect."""

class InvalidAuth(UnifiNetworkRulesError):
    """Error to indicate there is invalid auth."""

class UDMAPI:
    """Class to interact with UniFi Dream Machine API."""
    def __init__(self, host: str, username: str, password: str, site: str = DEFAULT_SITE, verify_ssl: bool | str = False):
        """Initialize the UDMAPI."""
        self.host = host
        self.username = username
        self.password = password
        self.site = site
        
        # Ensure verify_ssl is properly set
        if isinstance(verify_ssl, str) and verify_ssl.lower() in ("false", "no", "0"):
            verify_ssl = False
        elif isinstance(verify_ssl, str) and verify_ssl.lower() in ("true", "yes", "1"):
            verify_ssl = True
            
        self.verify_ssl = verify_ssl
        LOGGER.debug("SSL verification setting: %s", self.verify_ssl)
        
        self._session = None
        self.controller = None
        self._initialized = False
        self._hass_session = False
        self._ws_callback = None
        self._last_login_attempt = 0
        self._login_attempt_count = 0
        self._max_login_attempts = 3
        self._login_cooldown = 60
        self._config = None  # Store config for delayed controller creation
        self._capabilities = None  # Store capabilities
        # WebSocket path customization
        self._websocket_path_prefix = ""
        self._custom_websocket = None
        self._ws_message_handler = None
        
        # Rate limiting protection
        self._rate_limited = False
        self._rate_limit_until = 0  # Time when we can try again
        self._consecutive_failures = 0
        self._max_backoff = 300  # Maximum backoff in seconds (5 minutes)
        
        # Track last error message for authentication issue detection
        self._last_error_message = ""
        
        # Force unifi os detection
        self._force_unifi_os_detection()

    def _force_unifi_os_detection(self) -> None:
        """Force the UniFi OS detection flag if needed."""
        # Skip if controller isn't initialized yet
        if not self.controller:
            LOGGER.debug("Controller not initialized, skipping UniFi OS detection")
            return

        # Check if controller has the is_unifi_os attribute
        if hasattr(self.controller, "is_unifi_os"):
            current_value = self.controller.is_unifi_os
            
            # If it's already detected as UniFi OS, we're done
            if current_value:
                LOGGER.debug("Controller already detected as UniFi OS (is_unifi_os=True)")
                return
            else:
                # If not UniFi OS, force it to True for compatibility
                LOGGER.info("Setting is_unifi_os=True for best compatibility")
                self._apply_unifi_os_setting(True)
        else:
            # If controller doesn't have the attribute, add it
            LOGGER.info("Controller missing is_unifi_os attribute, adding it with value True")
            self._apply_unifi_os_setting(True)

    async def async_init(self, hass: HomeAssistant | None = None) -> None:
        """Initialize the UDM API."""
        LOGGER.debug("Initializing UDMAPI")

        # Store hass for later use
        self._hass = hass
        
        # Create session if not already provided
        if self._session is None:
            if hass is not None:
                self._session = async_get_clientsession(hass, verify_ssl=self.verify_ssl)
                self._hass_session = True
            else:
                connector = aiohttp.TCPConnector(verify_ssl=self.verify_ssl)
                self._session = aiohttp.ClientSession(connector=connector)
                self._hass_session = False
        
        # Extract base host without port if specified
        base_host = self.host.split(":")[0]
        
        # We'll use port 443 explicitly for all UniFi connections
        port = 443
        
        # For debugging - always log the exact host and port we're using
        LOGGER.debug("Using base_host=%s and port=%d for UniFi connection", base_host, port)
        
        # Important: Store base_host (without port) in self.host to avoid port duplication issues
        # This ensures any code that appends a port later won't create "host:443:8443" errors
        self.host = base_host
        
        # Create Configuration object for controller
        controller_initialized = False
        try:
            # Try to create a Configuration object directly
            self._config = Configuration(
                session=self._session,
                host=base_host,  # Use base host WITHOUT port
                port=port,  # Explicitly provide port as separate parameter
                username=self.username,
                password=self.password,
                site=self.site,
                ssl_context=self.verify_ssl
            )
            LOGGER.debug("Created Configuration object with host %s and port %d", 
                         base_host, port)
                         
            # Now create the Controller with the Configuration object
            self.controller = Controller(self._config)
            LOGGER.debug("Successfully created Controller with Configuration object")
            controller_initialized = True
            
        except (TypeError, ValueError) as config_err:
            LOGGER.warning("Could not create Controller with Configuration object: %s", config_err)
            LOGGER.debug("Falling back to direct Controller initialization")
            
            # Try direct Controller initialization
            try:
                self.controller = Controller(
                    session=self._session,
                    host=base_host,
                    port=port,
                    username=self.username,
                    password=self.password,
                    site=self.site,
                    verify_ssl=self.verify_ssl
                )
                LOGGER.debug("Initialized Controller directly with host %s and port %d", base_host, port)
                controller_initialized = True
                
                # Store config for reference
                self._config = {
                    "host": base_host,
                    "port": port,
                    "username": self.username,
                    "password": self.password,
                    "site": self.site,
                    "verify_ssl": self.verify_ssl
                }
            except Exception as controller_err:
                LOGGER.error("Failed to directly initialize Controller: %s", controller_err)
        except Exception as unknown_err:
            LOGGER.error("Unexpected error creating Configuration object: %s", unknown_err)
        
        # Verify controller was initialized
        if not self.controller:
            LOGGER.error("Failed to initialize controller. Cannot continue.")
            raise CannotConnect("Failed to initialize UniFi controller")
        
        # Set UniFi OS detection
        if "localhost" in base_host or "127.0.0.1" in base_host:
            self._apply_unifi_os_setting(False)
        else:
            self._apply_unifi_os_setting(True)
        
        # Log diagnostic info about the controller
        log_websocket("Logging controller diagnostics before login")
        log_controller_diagnostics(self.controller, self)
        
        # Check if this is a UDM device using SDN status endpoint before login
        await self._check_udm_device()
        
        # Diagnostic logging of current detection status
        if hasattr(self.controller, "is_unifi_os"):
            LOGGER.info("Before login - UniFi OS detection: %s", self.controller.is_unifi_os)
        else:
            LOGGER.warning("Controller doesn't have is_unifi_os attribute")
            # Add the attribute if it doesn't exist
            self._apply_unifi_os_setting(True)

        # Initialize
        try:
            await self.controller.login()
            LOGGER.debug("Successfully logged in to controller")
        except Exception as login_err:
            LOGGER.error("Failed to login to controller: %s", login_err)
            raise CannotConnect(f"Login failed: {login_err}")
        
        # Log diagnostic info after login
        log_websocket("Logging controller diagnostics after login")
        log_controller_diagnostics(self.controller, self)
        
        # Final check for UniFi OS detection
        if hasattr(self.controller, "is_unifi_os"):
            LOGGER.info("After login - UniFi OS detection: %s", self.controller.is_unifi_os)
            
            # If detection still failed, we can try again with SDN status 
            # now that we have an authenticated session
            if not self.controller.is_unifi_os:
                LOGGER.debug("UniFi OS detection initially failed, trying with authenticated session")
                await self._check_udm_device(authenticated=True)
        else:
            LOGGER.warning("Controller still doesn't have is_unifi_os attribute after login")
            # Try to add it using our helper
            self._apply_unifi_os_setting(True)
        
        # Ensure connectivity has the right properties for WebSocket support
        if hasattr(self.controller, "connectivity"):
            conn = self.controller.connectivity
            if hasattr(conn, "is_unifi_os") and hasattr(self.controller, "is_unifi_os"):
                # Make sure both flags are aligned
                conn.is_unifi_os = self.controller.is_unifi_os
                
        self._initialized = True
        
        # Initial refresh of all data
        await self.refresh_all()
        
        # Initialize and check capabilities
        if self._capabilities is None:
            self._capabilities = _Capabilities(self)
        # Check legacy firewall capability
        await self._capabilities.check_legacy_firewall()

    @property
    def initialized(self) -> bool:
        """Return True if API is initialized."""
        return self._initialized

    @property
    def capabilities(self):
        """Return API capabilities."""
        if self._capabilities is None:
            self._capabilities = _Capabilities(self)
        return self._capabilities

    async def cleanup(self) -> None:
        """Cleanup resources."""
        try:
            if self._session and not self._hass_session:
                await self._session.close()
        except Exception as err:
            LOGGER.error("Error during cleanup: %s", str(err))
        finally:
            self._session = None
            self.controller = None
            self._initialized = False
            self._config = None

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
        else:
            self._websocket_attempt_lock = asyncio.Lock()
            
        # List of URLs to try, ordered by preference
        ws_urls_to_try = []
        used_urls = set()
        
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
                
                # Instead of trying multiple URLs in parallel, let's try them in sequence
                # with a delay between attempts if they fail
                
                # Clear previous custom websocket if any
                if self._custom_websocket:
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
                
                # Generate URLs to try in order of most likely to work
                # First try the correct URL path with the proxy path for UniFi OS
                # This is the path that works in recent UniFi OS versions
                ws_url = f"wss://{base_host}:443/proxy/network/wss/s/{site}/events?clients=v2"
                LOGGER.info("Trying primary WebSocket URL: %s", ws_url)
                ws_urls_to_try.append(ws_url)
                
                # Then try another common variation
                ws_url = f"wss://{base_host}:443/wss/s/{site}/events?clients=v2"
                ws_urls_to_try.append(ws_url)
                
                # Then try the UniFi OS socket
                ws_url = f"wss://{base_host}:443/api/ws/sock"
                ws_urls_to_try.append(ws_url)
                
                # Lastly try the older format
                ws_url = f"wss://{base_host}:443/wss/api/s/{site}/events"
                ws_urls_to_try.append(ws_url)
                
                # Rate limit protection - maximum number of URLs to try in one session
                max_urls_to_try = 2  # Reduced from 4 to 2
                actual_urls_to_try = ws_urls_to_try[:max_urls_to_try]
                
                # Try each URL with a delay between attempts
                for i, ws_url in enumerate(actual_urls_to_try):
                    # Skip already tried URLs
                    if ws_url in used_urls:
                        continue
                        
                    used_urls.add(ws_url)
                    
                    # Add delay between attempts
                    if i > 0:
                        delay = 10  # 10 second delay between URL attempts
                        LOGGER.debug("Waiting %d seconds before trying next WebSocket URL", delay)
                        await asyncio.sleep(delay)
                    
                    try:
                        LOGGER.info("Connecting to WebSocket URL: %s", ws_url)
                        
                        # Create custom WebSocket
                        self._custom_websocket = CustomUnifiWebSocket(
                            ws_url=ws_url,
                            session=self._session,
                            headers=headers,
                            ssl=False if "localhost" in base_host else True
                        )
                        
                        # Set message handler if available
                        if self._ws_message_handler:
                            LOGGER.debug("Setting message handler on new custom WebSocket")
                            self._custom_websocket.set_message_callback(self._ws_message_handler)
                            
                        LOGGER.debug("WebSocket callback set for %s", ws_url)
                        
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
                        status_code = getattr(err, "status", None)
                        error_text = str(err)
                        
                        # If we get a 429, we're rate limited - don't try more URLs
                        if status_code == 429 or "429" in error_text:
                            LOGGER.error("Hit rate limit (429) when connecting to WebSocket. Waiting before retrying.")
                            # Start backoff period
                            self._rate_limited = True
                            self._consecutive_failures += 1
                            backoff = min(30 * (2 ** (self._consecutive_failures - 1)), self._max_backoff)
                            self._rate_limit_until = asyncio.get_event_loop().time() + backoff
                            raise CannotConnect(f"Rate limited. Try again in {backoff} seconds.")
                        
                        LOGGER.warning("%s error with URL %s: %s", 
                                    status_code or "Unknown", ws_url, error_text)
                        
                        # Continue to the next URL
                        continue
                
                # If we get here, all URLs failed
                LOGGER.error("All WebSocket URL variants failed. Tried %d URLs: %s", 
                        len(used_urls), ", ".join(used_urls))
                
                # Set a rate limit if we've had multiple consecutive failures
                if self._consecutive_failures >= 2:
                    self._rate_limited = True
                    backoff = min(30 * (2 ** (self._consecutive_failures - 1)), self._max_backoff)
                    self._rate_limit_until = asyncio.get_event_loop().time() + backoff
                    LOGGER.warning(
                        "Multiple consecutive WebSocket failures. Rate limiting for %d seconds.",
                        backoff
                    )
                
                self._consecutive_failures += 1
                raise CannotConnect("All WebSocket URL variants failed")
                
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
                if self._custom_websocket:
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
            self._custom_websocket.set_callback(callback)

    # Authentication lock to prevent parallel login attempts
    _login_lock = None
    _last_successful_login = 0
    _min_login_interval = 15  # seconds

    async def _try_login(self) -> bool:
        """Try to log in to the UniFi controller."""
        # Initialize login lock if not already done
        if self._login_lock is None:
            self.__class__._login_lock = asyncio.Lock()

        # Check if we're rate limited before attempting
        if self._rate_limited:
            current_time = asyncio.get_event_loop().time()
            if current_time < self._rate_limit_until:
                wait_time = int(self._rate_limit_until - current_time)
                LOGGER.warning(
                    "Rate limit in effect. Login attempt blocked for %d more seconds.",
                    wait_time
                )
                return False
            
        # Prevent login attempts too close together
        current_time = asyncio.get_event_loop().time()
        time_since_last_login = current_time - self._last_successful_login
        
        if time_since_last_login < self._min_login_interval:
            wait_time = self._min_login_interval - time_since_last_login
            LOGGER.debug(
                "Throttling login: Last successful login was %0.2f seconds ago. "
                "Waiting %0.2f more seconds before attempting again.",
                time_since_last_login, wait_time
            )
            await asyncio.sleep(wait_time)
            
        # Use lock to prevent parallel login attempts
        async with self._login_lock:
            try:
                # Try logging in through the controller
                LOGGER.debug("Attempting controller login with lock acquired")
                await self.controller.login()
                
                # Add a small delay to allow the session to propagate
                # This helps ensure the new authentication is used in subsequent requests
                await asyncio.sleep(0.5)
                
                # Perform a lightweight verification request to confirm authentication
                # This ensures the session is fully established
                LOGGER.debug("Verifying authentication propagation with test request")
                try:
                    # Pick a lightweight endpoint that should always succeed if authentication is good
                    # Get system stats is typically a small and fast request
                    await self.get_system_stats()
                    LOGGER.debug("Authentication verification successful")
                except Exception as verify_err:
                    LOGGER.warning("Authentication verification failed: %s - trying once more", verify_err)
                    # Give the system a bit more time and try again
                    await asyncio.sleep(1.0)
                    try:
                        await self.get_system_stats()
                        LOGGER.debug("Second authentication verification successful")
                    except Exception as second_verify_err:
                        LOGGER.error("Second authentication verification failed: %s", second_verify_err)
                        # We'll still consider login successful but log the issue
                
                self._consecutive_failures = 0  # Reset on success
                self._last_successful_login = asyncio.get_event_loop().time()
                LOGGER.debug("Login successful, lock released")
                return True
            except ClientResponseError as err:
                # Handle rate limiting
                if err.status == 429:
                    # Implement exponential backoff for rate limiting
                    self._consecutive_failures += 1
                    backoff_time = min(2 ** self._consecutive_failures, self._max_backoff)
                    self._rate_limited = True
                    current_time = asyncio.get_event_loop().time()
                    self._rate_limit_until = current_time + backoff_time
                    
                    LOGGER.error(
                        "Rate limit hit (429). Backing off for %d seconds. "
                        "Consider reducing your API calls or checking for issues with your UniFi device.",
                        backoff_time
                    )
                    return False
                elif err.status == 401:
                    LOGGER.error("Failed to authenticate to UniFi controller: Invalid credentials")
                    return False
                else:
                    LOGGER.error("Failed to authenticate to UniFi controller: %s", err)
                    return False
            except Exception as err:
                LOGGER.error("Unexpected error authenticating to UniFi controller: %s", err)
                return False

    async def reset_rate_limit(self) -> bool:
        """Reset the rate limit status to allow immediate retries."""
        self._rate_limited = False
        self._consecutive_failures = 0
        self._rate_limit_until = 0
        LOGGER.info("Rate limit status has been manually reset")
        
        # Try to refresh the session immediately
        try:
            return await self.refresh_session()
        except Exception as err:
            LOGGER.error("Failed to refresh session after rate limit reset: %s", err)
            return False

    # Firewall Policy Methods
    async def get_firewall_policies(self, include_predefined: bool = False, force_refresh: bool = False) -> List[Any]:
        """Get firewall policies.
        
        Args:
            include_predefined: Whether to include predefined policies in the results
            force_refresh: If True, forces a direct API fetch to bypass any caching
        """
        if not self.controller or not self._initialized:
            return []
            
        try:
            if not hasattr(self.controller, "firewall_policies"):
                LOGGER.error(
                    "Controller missing firewall_policies attribute. This indicates "
                    "a module version conflict. Try restarting Home Assistant again."
                )
                return []
            
            # If force_refresh is True, make a direct API request instead of using cached data
            if force_refresh:
                LOGGER.debug("Performing direct API request for firewall policies")
                try:
                    # Use the API directly to get the latest data
                    request = ApiRequestV2("GET", API_ENDPOINT_FIREWALL_POLICIES)
                    response = await self.controller.request(request)
                    # Parse the response into policy objects
                    if response and "data" in response:
                        policies = [FirewallPolicy(policy_data) for policy_data in response["data"]]
                        LOGGER.debug("Direct API fetch returned %d policies", len(policies))
                    else:
                        LOGGER.warning("Direct API request returned unexpected format: %s", response)
                        # Fall back to normal update if direct request fails
                        await self.controller.firewall_policies.update()
                        policies = list(self.controller.firewall_policies.values())
                except Exception as direct_err:
                    LOGGER.warning("Direct API request failed, falling back to controller: %s", direct_err)
                    # Fall back to normal update
                    await self.controller.firewall_policies.update()
                    policies = list(self.controller.firewall_policies.values())
            else:
                # Use the normal controller update mechanism
                await self.controller.firewall_policies.update()
                policies = list(self.controller.firewall_policies.values())
                
            if not include_predefined:
                return [policy for policy in policies if not (policy.get("predefined", False) if isinstance(policy, dict) else getattr(policy, "predefined", False))]
            return policies
        except Exception as err:
            LOGGER.error("Failed to get firewall policies: %s", str(err))
            return []

    async def add_firewall_policy(self, policy_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new firewall policy."""
        LOGGER.debug("Adding firewall policy: %s", policy_data)
        try:
            request = ApiRequestV2 ("POST", API_ENDPOINT_FIREWALL_POLICIES, policy_data)
            policy = await self.controller.request(request)
            return policy
        except Exception as err:
            LOGGER.error("Failed to add firewall policy: %s", str(err))
            return None

    async def update_firewall_policy(self, policy_id: str, policy_data: Dict[str, Any]) -> bool:
        """Update an existing firewall policy."""
        LOGGER.debug("Updating firewall policy %s: %s", policy_id, policy_data)
        try:
            # Ensure policy_id is set in the data
            if "_id" not in policy_data:
                policy_data["_id"] = policy_id
            
            # Use the proper request to update the policy
            request = FirewallPolicyUpdateRequest.create(policy_data)
            
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Update firewall policy",
                lambda: self.controller.request(request)
            )
            
            if not success:
                LOGGER.error("Failed to update firewall policy: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to update firewall policy: %s", str(err))
            return False

    async def remove_firewall_policy(self, policy_id: str) -> bool:
        """Remove a firewall policy."""
        LOGGER.debug("Removing firewall policy: %s", policy_id)
        try:
            request = ApiRequestV2.create("POST", API_ENDPOINT_FIREWALL_POLICIES_BATCH_DELETE, f"['{policy_id}']")
            
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Remove firewall policy",
                lambda: self.controller.request(request)
            )
            
            if not success:
                LOGGER.error("Failed to remove firewall policy: %s", error)
                return False
                
            # Remove from local cache after successful API call
            await self.controller.firewall_policies.remove_item(policy_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove firewall policy: %s", str(err))
            return False

    async def toggle_firewall_policy(self, policy_id: str, enabled: bool) -> bool:
        """Enable or disable a firewall policy."""
        LOGGER.debug("Setting firewall policy %s enabled state to: %s", policy_id, enabled)
        try:
            # Get current policy
            current_policies = await self.get_firewall_policies()
            policy = next((p for p in current_policies if get_rule_id(p) == policy_id), None)
            
            if not policy:
                LOGGER.error("Firewall policy %s not found", policy_id)
                return False
                
            # Update policy data
            if isinstance(policy, dict):
                policy_data = policy.copy()
            else:
                policy_data = policy.raw.copy()
                
            policy_data["enabled"] = enabled
            
            # Use proper update method
            request = FirewallPolicyUpdateRequest.create(policy_data)
            
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Toggle firewall policy",
                lambda: self.controller.request(request)
            )
            
            if not success:
                error_message = error or "Unknown error"
                if "401 Unauthorized" in error_message or "403 Forbidden" in error_message:
                    LOGGER.warning("Authentication issue when toggling firewall policy: %s", error_message)
                    # Force a coordinator update to refresh all data properly
                    if hasattr(self, "_on_auth_failure_callback") and self._on_auth_failure_callback:
                        LOGGER.info("Triggering auth failure callback for data refresh")
                        await self._on_auth_failure_callback()
                else:
                    LOGGER.error("Failed to toggle firewall policy: %s", error_message)
                return False
                
            # After successful toggle, add a small delay to allow the change to propagate
            # This helps prevent immediate refresh race conditions
            await asyncio.sleep(0.5)
            
            return True
        except Exception as err:
            LOGGER.error("Failed to toggle firewall policy: %s", str(err))
            return False
            
    # Method to set a callback for authentication failures
    def set_auth_failure_callback(self, callback):
        """Set a callback to be called on authentication failures during operations."""
        self._on_auth_failure_callback = callback

    # Traffic Rules Methods
    async def get_traffic_rules(self) -> List[Any]:
        """Get all traffic rules."""
        if not self.controller:
            return []
            
        try:
            await self.controller.traffic_rules.update()
            return list(self.controller.traffic_rules.values())
        except Exception as err:
            LOGGER.error("Failed to get traffic rules: %s", str(err))
            return []

    async def add_traffic_rule(self, rule_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new traffic rule."""
        LOGGER.debug("Adding traffic rule: %s", rule_data)
        try:
            request = ApiRequestV2 ("POST", API_ENDPOINT_TRAFFIC_RULES, rule_data)
            rule = await self.controller.request(request)
            return rule
        except Exception as err:
            LOGGER.error("Failed to add traffic rule: %s", str(err))
            return None

    async def toggle_traffic_rule(self, rule_id: str, enabled: bool) -> bool:
        """Enable or disable a traffic rule."""
        LOGGER.debug("Setting traffic rule %s enabled state to: %s", rule_id, enabled)
        try:
            # Get current rule
            current_rules = await self.get_traffic_rules()
            rule = next((r for r in current_rules if get_rule_id(r) == rule_id), None)
            
            if not rule:
                LOGGER.error("Traffic rule %s not found", rule_id)
                return False
                
            # Create proper request for enabling/disabling
            if isinstance(rule, dict):
                rule_data = rule.copy()
                rule_data["enabled"] = enabled
                endpoint = API_ENDPOINT_TRAFFIC_RULE_DETAIL.format(rule_id=rule_id)
                request = ApiRequestV2("PUT", endpoint, rule_data)
            else:
                # Use the proper model request if available
                request = TrafficRuleEnableRequest.create(rule.raw, enable=enabled)
            
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Toggle traffic rule",
                lambda: self.controller.request(request)
            )
            
            if not success:
                LOGGER.error("Failed to toggle traffic rule: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to toggle traffic rule: %s", str(err))
            return False
    
    async def update_traffic_rule(self, rule_id: str, rule_data: Dict[str, Any]) -> bool:
        """Update an existing traffic rule."""
        LOGGER.debug("Updating traffic rule %s: %s", rule_id, rule_data)
        try:
            # Ensure rule_id is set in the data
            if "_id" not in rule_data:
                rule_data["_id"] = rule_id
            
            # Create a proper request for updating the rule
            endpoint = API_ENDPOINT_TRAFFIC_RULE_DETAIL.format(rule_id=rule_id)
            request = ApiRequestV2("PUT", endpoint, rule_data)
            
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Update traffic rule",
                lambda: self.controller.request(request)
            )
            
            if not success:
                LOGGER.error("Failed to update traffic rule: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to update traffic rule: %s", str(err))
            return False

    async def remove_traffic_rule(self, rule_id: str) -> bool:
        """Remove a traffic rule."""
        LOGGER.debug("Removing traffic rule: %s", rule_id)
        try:
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Remove traffic rule",
                lambda: self.controller.traffic_rules.remove_item(rule_id)
            )
            
            if not success:
                LOGGER.error("Failed to remove traffic rule: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to remove traffic rule: %s", str(err))
            return False

    # Port Forward Methods
    async def get_port_forwards(self) -> List[Any]:
        """Get all port forwards."""
        if not self.controller:
            return []
            
        LOGGER.debug("Fetching port forwards")
        try:
            await self.controller.port_forwarding.update()
            return list(self.controller.port_forwarding.values())
        except Exception as err:
            LOGGER.error("Failed to get port forwards: %s", str(err))
            return []

    async def add_port_forward(self, forward_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new port forward."""
        LOGGER.debug("Adding port forward: %s", forward_data)
        try:
            request = ApiRequest ("POST", "portforward", forward_data)
            forward = await self.controller.request(request)
            return forward
        except Exception as err:
            LOGGER.error("Failed to add port forward: %s", str(err))
            return None

    async def update_port_forward(self, forward_id: str, forward_data: Dict[str, Any]) -> bool:
        """Update an existing port forward."""
        LOGGER.debug("Updating port forward %s: %s", forward_id, forward_data)
        try:
            # Ensure forward_id is set in the data
            if "_id" not in forward_data:
                forward_data["_id"] = forward_id
            
            # Create a proper request for updating the port forward
            request = ApiRequest("PUT", "portforward", forward_data)
            
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Update port forward",
                lambda: self.controller.request(request)
            )
            
            if not success:
                LOGGER.error("Failed to update port forward: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to update port forward: %s", str(err))
            return False

    async def toggle_port_forward(self, forward_id: str, enabled: bool) -> bool:
        """Enable or disable a port forward."""
        LOGGER.debug("Setting port forward %s enabled state to: %s", forward_id, enabled)
        try:
            # Get current forward
            current_forwards = await self.get_port_forwards()
            forward = next((f for f in current_forwards if get_rule_id(f) == forward_id), None)
            
            if not forward:
                LOGGER.error("Port forward %s not found", forward_id)
                return False
                
            # Create proper request for enabling/disabling
            if isinstance(forward, dict):
                forward_data = forward.copy()
                forward_data["enabled"] = enabled
                request = ApiRequest("PUT", "portforward", forward_data)
            else:
                # Use the proper model request if available
                request = PortForwardEnableRequest.create(forward, enable=enabled)
            
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Toggle port forward",
                lambda: self.controller.request(request)
            )
            
            if not success:
                LOGGER.error("Failed to toggle port forward: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to toggle port forward: %s", str(err))
            return False

    async def remove_port_forward(self, forward_id: str) -> bool:
        """Remove a port forward."""
        LOGGER.debug("Removing port forward: %s", forward_id)
        try:
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Remove port forward",
                lambda: self.controller.port_forwarding.remove_item(forward_id)
            )
            
            if not success:
                LOGGER.error("Failed to remove port forward: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to remove port forward: %s", str(err))
            return False

    # Traffic Routes Methods
    async def get_traffic_routes(self) -> List[Any]:
        """Get all traffic routes."""
        LOGGER.debug("Fetching traffic routes")
        try:
            await self.controller.traffic_routes.update()
            return list(self.controller.traffic_routes.values())
        except Exception as err:
            LOGGER.error("Failed to get traffic routes: %s", str(err))
            return []

    async def add_traffic_route(self, route_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new traffic route."""
        LOGGER.debug("Adding traffic route: %s", route_data)
        try:
            request = ApiRequestV2 ("POST", API_ENDPOINT_TRAFFIC_ROUTES, route_data)
            route = await self.controller.request(request)
            return route
        except Exception as err:
            LOGGER.error("Failed to add traffic route: %s", str(err))
            return None

    async def update_traffic_route(self, route_id: str, route_data: Dict[str, Any]) -> bool:
        """Update an existing traffic route."""
        LOGGER.debug("Updating traffic route %s: %s", route_id, route_data)
        try:
            # Ensure route_id is set in the data
            if "_id" not in route_data:
                route_data["_id"] = route_id
            
            # Create a proper request for updating the route
            request = TrafficRouteSaveRequest.create(route_data)
            
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Update traffic route",
                lambda: self.controller.request(request)
            )
            
            if not success:
                LOGGER.error("Failed to update traffic route: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to update traffic route: %s", str(err))
            return False

    async def toggle_traffic_route(self, route_id: str, enabled: bool) -> bool:
        """Enable or disable a traffic route."""
        LOGGER.debug("Setting traffic route %s enabled state to: %s", route_id, enabled)
        try:
            # Get current route
            current_routes = await self.get_traffic_routes()
            route = next((r for r in current_routes if get_rule_id(r) == route_id), None)
            
            if not route:
                LOGGER.error("Traffic route %s not found", route_id)
                return False
                
            # Create proper request for enabling/disabling
            if isinstance(route, dict):
                route_data = route.copy()
                route_data["enabled"] = enabled
                endpoint = API_ENDPOINT_TRAFFIC_ROUTE_DETAIL.format(route_id=route_id)
                request = ApiRequestV2("PUT", endpoint, route_data)
            else:
                # Use the proper model request if available
                request = TrafficRouteSaveRequest.create(route.raw, enable=enabled)
            
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Toggle traffic route",
                lambda: self.controller.request(request)
            )
            
            if not success:
                LOGGER.error("Failed to toggle traffic route: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to toggle traffic route: %s", str(err))
            return False

    async def remove_traffic_route(self, route_id: str) -> bool:
        """Remove a traffic route."""
        LOGGER.debug("Removing traffic route: %s", route_id)
        try:
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Remove traffic route",
                lambda: self.controller.traffic_routes.remove_item(route_id)
            )
            
            if not success:
                LOGGER.error("Failed to remove traffic route: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to remove traffic route: %s", str(err))
            return False

    # Firewall Zone Methods
    async def get_firewall_zones(self) -> List[Dict[str, Any]]:
        """Get all firewall zones."""
        LOGGER.debug("Fetching firewall zones")
        try:
            if not hasattr(self.controller, "firewall_zones"):
                LOGGER.error(
                    "Controller missing firewall_zones attribute. This indicates "
                    "a module version conflict. Try restarting Home Assistant again."
                )
                return []
            
            await self.controller.firewall_zones.update()
            return list(self.controller.firewall_zones.values())
        except Exception as err:
            LOGGER.error("Failed to get firewall zones: %s", str(err))
            return []

    # WLAN Management Methods
    async def get_wlans(self) -> List[Dict[str, Any]]:
        """Get all WLANs."""
        if not self.controller:
            return []
            
        LOGGER.debug("Fetching WLANs")
        try:
            await self.controller.wlans.update()
            return list(self.controller.wlans.values())
        except Exception as err:
            LOGGER.error("Failed to get WLANs: %s", str(err))
            return []

    async def toggle_wlan(self, wlan_id: str, enabled: bool) -> bool:
        """Enable or disable a WLAN."""
        LOGGER.debug("Setting WLAN %s enabled state to: %s", wlan_id, enabled)
        try:
            wlan = self.controller.wlans[wlan_id]
            if not wlan:
                raise KeyError(f"WLAN {wlan_id} not found")
            
            wlan_data = dict(wlan)
            wlan_data['enabled'] = enabled
            return await self.update_wlan(wlan_id, wlan_data)
        except Exception as err:
            LOGGER.error("Failed to toggle WLAN: %s", str(err))
            return False

    # System Status Methods
    async def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics and status."""
        LOGGER.debug("Fetching system statistics")
        try:
            stats = {}
            # Get system info
            system_information = await self.controller.system_information.update()
            if system_information:
                stats.update(system_information)
            
            return stats
        except Exception as err:
            LOGGER.error("Failed to get system stats: %s", str(err))
            return {}

    # Legacy Firewall Rules Methods
    async def get_legacy_firewall_rules(self) -> List[Dict[str, Any]]:
        """Get all legacy firewall rules."""
        LOGGER.debug("Fetching legacy firewall rules")
        try:
            endpoint = LEGACY_FIREWALL_RULES_ENDPOINT.format(site=self.site)
            request = ApiRequest("GET", endpoint)
            response = await self.controller.request(request)
            
            # Check for the specific error response format first
            if isinstance(response, dict) and "meta" in response:
                # Case 1: Error response with InvalidObject
                if response["meta"].get("rc") == "error" and response["meta"].get("msg") == "api.err.InvalidObject":
                    LOGGER.debug("Legacy firewall rules not supported on this UniFi OS version - expected for some hardware/firmware")
                    return []
                
                # Case 2: Success response with "rc": "ok" but empty data - likely migrated to zone-based firewall
                if response["meta"].get("rc") == "ok" and "data" in response and len(response["data"]) == 0:
                    LOGGER.debug("No legacy firewall rules found - device likely migrated to zone-based firewall")
                    return []
                    
                # Case 3: Success with actual data
                if response["meta"].get("rc") == "ok" and "data" in response:
                    return response["data"]
            
            # Fallback check for data
            if response and isinstance(response, dict) and "data" in response:
                return response["data"]
                
            LOGGER.debug("Unexpected response format from legacy firewall rules endpoint: %s", response)
            return []
            
        except Exception as err:
            # Only log as error if it's not the known InvalidObject error
            error_str = str(err)
            if "api.err.InvalidObject" in error_str:
                LOGGER.debug("Legacy firewall rules not supported: %s", error_str)
            else:
                LOGGER.error("Failed to get legacy firewall rules: %s", error_str)
            return []

    async def add_legacy_firewall_rule(self, rule_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new legacy firewall rule."""
        LOGGER.debug("Adding legacy firewall rule: %s", rule_data)
        try:
            endpoint = LEGACY_FIREWALL_RULES_ENDPOINT.format(site=self.site)
            request = ApiRequest("POST", endpoint, rule_data)
            rule = await self.controller.request(request)
            return rule
        except Exception as err:
            LOGGER.error("Failed to add legacy firewall rule: %s", str(err))
            return None

    async def update_legacy_firewall_rule(self, rule_id: str, rule_data: Dict[str, Any]) -> bool:
        """Update an existing legacy firewall rule."""
        LOGGER.debug("Updating legacy firewall rule %s: %s", rule_id, rule_data)
        try:
            # Ensure rule_id is in the data
            if "_id" not in rule_data:
                rule_data["_id"] = rule_id
                
            endpoint = LEGACY_FIREWALL_RULES_ENDPOINT.format(site=self.site)
            request = ApiRequest("PUT", endpoint, rule_data)
            
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Update legacy firewall rule",
                lambda: self.controller.request(request)
            )
            
            if not success:
                LOGGER.error("Failed to update legacy firewall rule: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to update legacy firewall rule: %s", str(err))
            return False

    async def toggle_legacy_firewall_rule(self, rule_id: str, enabled: bool) -> bool:
        """Enable or disable a legacy firewall rule."""
        LOGGER.debug("Setting legacy firewall rule %s enabled state to: %s", rule_id, enabled)
        try:
            # Get current rule
            rules = await self.get_legacy_firewall_rules()
            rule = next((r for r in rules if r.get("_id") == rule_id), None)
            
            if not rule:
                LOGGER.error("Legacy firewall rule %s not found", rule_id)
                return False
                
            # Update rule data
            rule_data = rule.copy()
            rule_data["enabled"] = enabled
            
            return await self.update_legacy_firewall_rule(rule_id, rule_data)
        except Exception as err:
            LOGGER.error("Failed to toggle legacy firewall rule: %s", str(err))
            return False

    async def remove_legacy_firewall_rule(self, rule_id: str) -> bool:
        """Remove a legacy firewall rule."""
        LOGGER.debug("Removing legacy firewall rule: %s", rule_id)
        try:
            endpoint = f"{LEGACY_FIREWALL_RULES_ENDPOINT.format(site=self.site)}/{rule_id}"
            request = ApiRequest("DELETE", endpoint)
            
            # Use our error handling method
            success, error = await self._handle_api_request(
                "Remove legacy firewall rule",
                lambda: self.controller.request(request)
            )
            
            if not success:
                LOGGER.error("Failed to remove legacy firewall rule: %s", error)
                return False
                
            return True
        except Exception as err:
            LOGGER.error("Failed to remove legacy firewall rule: %s", str(err))
            return False

    # Bulk Operations and Updates
    async def refresh_all(self) -> None:
        """Refresh all data from the UniFi controller."""
        LOGGER.debug("Refreshing all data from UniFi controller")
        if not self.controller or not self._initialized:
            return
            
        try:
            update_tasks = []
            
            # Check for each attribute before adding to update tasks
            if hasattr(self.controller, "firewall_policies"):
                update_tasks.append(self.controller.firewall_policies.update())
            else:
                LOGGER.warning("Controller missing firewall_policies attribute - module version conflict likely")
            
            if hasattr(self.controller, "traffic_rules"):
                update_tasks.append(self.controller.traffic_rules.update())
            else:
                LOGGER.warning("Controller missing traffic_rules attribute - module version conflict likely")
            
            if hasattr(self.controller, "port_forwarding"):
                update_tasks.append(self.controller.port_forwarding.update())
            else:
                LOGGER.warning("Controller missing port_forwarding attribute - module version conflict likely")
            
            if hasattr(self.controller, "traffic_routes"):
                update_tasks.append(self.controller.traffic_routes.update())
            else:
                LOGGER.warning("Controller missing traffic_routes attribute - module version conflict likely")
            
            if hasattr(self.controller, "wlans"):
                update_tasks.append(self.controller.wlans.update())
            else:
                LOGGER.warning("Controller missing wlans attribute - module version conflict likely")
            
            # Always try to get legacy firewall rules as it uses a direct API call
            update_tasks.append(self.get_legacy_firewall_rules())
            
            if not update_tasks:
                LOGGER.error(
                    "No controller attributes found for refreshing data. This likely indicates a module "
                    "version conflict. Try restarting Home Assistant again."
                )
                return
            
            results = await asyncio.gather(*update_tasks, return_exceptions=True)
            for task_result in results:
                if isinstance(task_result, Exception):
                    # Skip logging errors related to legacy firewall rules
                    error_str = str(task_result)
                    if "api.err.InvalidObject" in error_str:
                        continue
                    LOGGER.warning("Error during refresh: %s", error_str)
                    
        except Exception as err:
            LOGGER.error("Failed to refresh all data: %s", str(err))

    async def bulk_update_firewall_policies(self, policies: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
        """Bulk update firewall policies. Returns (success_count, failed_ids)."""
        LOGGER.debug("Performing bulk update of %d firewall policies", len(policies))
        success_count = 0
        failed_ids = []
        
        for policy in policies:
            policy_id = policy.get('_id')
            if not policy_id:
                LOGGER.error("Policy missing _id field: %s", policy)
                continue
                
            success, error = await self._handle_api_request(
                "Update firewall policy",
                lambda: self.controller.request(FirewallPolicyUpdateRequest.create(policy))
            )
            
            if success:
                success_count += 1
            else:
                LOGGER.error("Failed to update policy %s: %s", policy_id, error)
                failed_ids.append(policy_id)
        
        return success_count, failed_ids

    async def get_rule_status(self, rule_id: str) -> Dict[str, Any]:
        """Get detailed status for a specific rule."""
        if not self.controller:
            return {
                "active": False,
                "dependencies": [],
                "conflicts": [],
                "last_modified": None,
                "type": None
            }
            
        LOGGER.debug("Getting detailed status for rule: %s", rule_id)
        try:
            status = {
                "active": False,
                "dependencies": [],
                "conflicts": [],
                "last_modified": None,
                "type": None
            }
            
            rules_map = {
                "firewall_policy": self.controller.firewall_policies,
                "traffic_rule": self.controller.traffic_rules,
                "port_forward": self.controller.port_forwarding,
                "traffic_route": self.controller.traffic_routes
            }
            
            for rule_type, rules in rules_map.items():
                if rule_id in rules:
                    rule = rules[rule_id]
                    if isinstance(rule, dict):
                        rule_data = rule
                    else:
                        rule_data = dict(rule)
                    
                    status["active"] = rule_data.get("enabled", False)
                    status["last_modified"] = rule_data.get("last_modified")
                    status["type"] = rule_type
                    break
            
            return status
        except Exception as err:
            LOGGER.error("Failed to get rule status: %s", str(err))
            return status

    async def update_rule_state(self, rule_type: str, rule_id: str, enabled: bool) -> bool:
        """Update the state of a rule based on its type.
        
        This is a convenience method used by services to toggle rule states.
        """
        LOGGER.debug("Updating rule state for %s(%s) to %s", rule_type, rule_id, enabled)
        
        try:
            # Map rule_type to appropriate toggle method
            if rule_type == "firewall_policies":
                return await self.toggle_firewall_policy(rule_id, enabled)
            elif rule_type == "traffic_rules":
                return await self.toggle_traffic_rule(rule_id, enabled)
            elif rule_type == "port_forwards":
                return await self.toggle_port_forward(rule_id, enabled)
            elif rule_type == "traffic_routes":
                return await self.toggle_traffic_route(rule_id, enabled)
            elif rule_type == "legacy_firewall_rules":
                return await self.toggle_legacy_firewall_rule(rule_id, enabled)
            else:
                LOGGER.error("Unknown rule type: %s", rule_type)
                return False
        except Exception as err:
            LOGGER.error("Failed to update rule state: %s", str(err))
            return False

    # Error handling helper
    async def _handle_api_request(self, request_type: str, action_coroutine) -> Tuple[bool, Optional[str]]:
        """Handle an API request with proper error handling.
        
        Args:
            request_type: A description of the request type for logging
            action_coroutine: A callable that returns a fresh coroutine when called
                             (not an awaitable coroutine object itself)
        """
        # Prepare request timestamp to detect throttling needs
        request_time = asyncio.get_event_loop().time()
        
        # Rate limiting check before making request
        if self._rate_limited:
            current_time = request_time
            if current_time < self._rate_limit_until:
                wait_time = int(self._rate_limit_until - current_time)
                LOGGER.warning(
                    "Rate limit in effect. %s request blocked for %d more seconds.",
                    request_type, wait_time
                )
                error_msg = f"Rate limited for {wait_time} more seconds"
                self._last_error_message = error_msg
                return False, error_msg
                
        try:
            await action_coroutine()
            
            # Update last successful login time based on successful API calls
            # This helps keep track of when the session is proven to be healthy
            # Only do this if the last update was at least 60 seconds ago to avoid excessive updates
            current_time = asyncio.get_event_loop().time()
            if current_time - self._last_successful_login > 60:
                LOGGER.debug("Updating last successful login time based on successful API call")
                self._last_successful_login = current_time
                
            # Clear last error message on success
            self._last_error_message = ""
            return True, None
        except LoginRequired:
            error_msg = "Session expired"
            LOGGER.warning("%s failed: %s, attempting to reconnect", request_type, error_msg)
            self._last_error_message = error_msg
            return await self._handle_authentication_retry(request_type, action_coroutine, error_msg)
        except RequestError as err:
            # Check for 403 Forbidden error which might indicate expired session
            error_message = str(err)
            self._last_error_message = error_message
            if "403 Forbidden" in error_message:
                LOGGER.warning("%s failed with 403 Forbidden, attempting to re-authenticate", request_type)
                return await self._handle_authentication_retry(request_type, action_coroutine, "403 Forbidden")
            # Check for rate limiting errors
            elif "429" in error_message:
                # Update rate limit tracking
                self._consecutive_failures += 1
                backoff_time = min(2 ** self._consecutive_failures, self._max_backoff)
                self._rate_limited = True
                current_time = asyncio.get_event_loop().time()
                self._rate_limit_until = current_time + backoff_time
                
                error_msg = f"Rate limited for {backoff_time} seconds"
                LOGGER.error(
                    "Rate limit hit (429) during %s. Backing off for %d seconds.",
                    request_type, backoff_time
                )
                return False, error_msg
            
            return False, f"Request failed: {err}"
        except (BadGateway, ServiceUnavailable) as err:
            error_msg = f"Service unavailable: {err}"
            self._last_error_message = error_msg
            return False, error_msg
        except ResponseError as err:
            # Check for 403 Forbidden error in response errors as well
            error_message = str(err) 
            self._last_error_message = error_message
            if "403 Forbidden" in error_message:
                LOGGER.warning("%s failed with 403 Forbidden in response, attempting to re-authenticate", request_type)
                return await self._handle_authentication_retry(request_type, action_coroutine, "403 Forbidden in response")
            return False, f"Invalid response: {err}"
        except Unauthorized as err:
            error_msg = f"Unauthorized error: {err}"
            self._last_error_message = error_msg
            LOGGER.warning("%s failed with Unauthorized error, attempting to re-authenticate", request_type)
            return await self._handle_authentication_retry(request_type, action_coroutine, "Unauthorized error")
        except AiounifiException as err:
            # Check for 403 Forbidden in AiounifiException as well
            error_message = str(err)
            self._last_error_message = error_message
            if "403 Forbidden" in error_message:
                LOGGER.warning("%s failed with 403 Forbidden in AiounifiException, attempting to re-authenticate", request_type)
                return await self._handle_authentication_retry(request_type, action_coroutine, "403 Forbidden in AiounifiException")
            elif "401 Unauthorized" in error_message:
                LOGGER.warning("%s failed with 401 Unauthorized in AiounifiException, attempting to re-authenticate", request_type)
                return await self._handle_authentication_retry(request_type, action_coroutine, "401 Unauthorized in AiounifiException")
            return False, f"API error: {err}"
        except Exception as err:
            error_msg = f"Unexpected error: {err}"
            self._last_error_message = error_msg
            return False, error_msg

    async def _handle_authentication_retry(self, request_type: str, action_coroutine, error_context: str) -> Tuple[bool, Optional[str]]:
        """Common handler for authentication retry logic.
        
        Args:
            request_type: A description of the request type for logging
            action_coroutine: A callable that returns a fresh coroutine when called
            error_context: Context about the error that triggered the retry
        """
        # Only attempt login if not too recent
        current_time = asyncio.get_event_loop().time()
        time_since_last_login = current_time - self._last_successful_login
        
        if time_since_last_login < self._min_login_interval:
            LOGGER.warning(
                "Login throttled: Last login was %0.2f seconds ago. "
                "Returning failure rather than attempting another login so soon.",
                time_since_last_login
            )
            return False, "Login throttled: Too many recent login attempts"
        
        try:
            login_success = await self._try_login()
            # Check if login was rate limited
            if self._rate_limited:
                return False, f"Request failed due to rate limiting during login after {error_context}"
                
            # Exit early if login failed
            if not login_success:
                return False, f"Login attempt failed after {error_context}"
                
            # Add a longer delay after successful login to allow session to propagate
            # This is critical to ensure session is fully established
            LOGGER.debug("Authentication successful, waiting for session propagation")
            await asyncio.sleep(1.5)  # Increased from 0.5 to 1.5 seconds
            
            # Verify session is fully propagated with a lightweight API call
            try:
                LOGGER.debug("Verifying session is fully established")
                await self.get_system_stats()  # This is a lightweight API call
                LOGGER.debug("Session verification successful, proceeding with original request")
            except Exception as verify_err:
                LOGGER.warning("Session verification failed: %s - waiting longer", verify_err)
                # Give more time for session to propagate
                await asyncio.sleep(2.0)
                try:
                    await self.get_system_stats()
                    LOGGER.debug("Second session verification successful")
                except Exception as second_verify_err:
                    LOGGER.error("Second session verification failed: %s - proceeding anyway", second_verify_err)
                    # Continue anyway - at least we tried
                
            # Create a fresh coroutine for the retry
            try:
                await action_coroutine()
                return True, None
            except Exception as retry_err:
                LOGGER.error("Re-attempt failed after %s authentication: %s", error_context, retry_err)
                # If the retry failed immediately after login, wait a bit longer and try one more time
                await asyncio.sleep(1.5)  # Increased from 1.0 to 1.5 seconds
                try:
                    await action_coroutine()
                    return True, None
                except Exception as second_retry_err:
                    return False, f"Second retry failed after {error_context} authentication: {second_retry_err}"
        except Exception as login_err:
            return False, f"Failed to re-authenticate after {error_context}: {login_err}"

    async def refresh_session(self) -> bool:
        """Refresh the session to prevent expiration.
        
        This method should be called periodically to keep the session alive.
        """
        # Check if we're currently rate limited
        if self._rate_limited:
            current_time = asyncio.get_event_loop().time()
            if current_time < self._rate_limit_until:
                wait_time = int(self._rate_limit_until - current_time)
                LOGGER.warning(
                    "Rate limit in effect. Skipping session refresh for %d more seconds.",
                    wait_time
                )
                return False
            else:
                # Reset rate limit if the time has passed
                LOGGER.info("Rate limit period has expired, resetting rate limit status")
                self._rate_limited = False
                self._consecutive_failures = 0
                
        if not self._initialized or not self.controller:
            LOGGER.warning("Cannot refresh session - API not initialized")
            return False
        
        # Initialize login lock if not already done
        if self._login_lock is None:
            self.__class__._login_lock = asyncio.Lock()
            
        # Prevent refresh attempts too close together
        current_time = asyncio.get_event_loop().time()
        time_since_last_login = current_time - self._last_successful_login
        
        if time_since_last_login < self._min_login_interval:
            LOGGER.debug(
                "Skipping refresh: Last successful login was %0.2f seconds ago, "
                "which is less than minimum interval of %d seconds.",
                time_since_last_login, self._min_login_interval
            )
            return True  # Return success as we're considering this "good enough"
            
        # Use lock to prevent parallel login attempts during refresh
        async with self._login_lock:
            try:
                LOGGER.debug("Proactively refreshing UniFi session (with lock)")
                await self.controller.login()
                self._consecutive_failures = 0  # Reset on success
                self._last_successful_login = asyncio.get_event_loop().time()
                return True
            except ClientResponseError as err:
                # Handle rate limiting
                if err.status == 429:
                    # Implement exponential backoff for rate limiting
                    self._consecutive_failures += 1
                    backoff_time = min(2 ** self._consecutive_failures, self._max_backoff)
                    self._rate_limited = True
                    current_time = asyncio.get_event_loop().time()
                    self._rate_limit_until = current_time + backoff_time
                    
                    LOGGER.error(
                        "Rate limit hit (429) during session refresh. Backing off for %d seconds. "
                        "Consider reducing your API calls or checking for issues with your UniFi device.",
                        backoff_time
                    )
                    return False
                elif err.status == 401:
                    LOGGER.error("Authentication failed (401) during session refresh. Credentials may be invalid.")
                    return False
                else:
                    LOGGER.warning("Session refresh failed with HTTP error %d: %s", err.status, err)
                    return False
            except Exception as err:
                LOGGER.warning("Session refresh failed: %s", str(err))
                return False

    async def _check_udm_device(self, authenticated: bool = False) -> bool:
        """Check if device is a UDM using the SDN status endpoint."""
        LOGGER.debug("Checking if device is a UDM via SDN status endpoint")
        
        # Skip if controller not initialized yet
        if not self.controller:
            LOGGER.debug("Controller not initialized, skipping UDM detection")
            return False
            
        # If already detected as UniFi OS, no need to check again
        if getattr(self.controller, "is_unifi_os", False):
            LOGGER.debug("Controller already detected as UniFi OS")
            return True
            
        try:
            data = None
            if authenticated and self._session:
                # Try authenticated request first if we have a session
                LOGGER.debug("Attempting authenticated SDN status check")
                headers = {}
                try:
                    headers = await self._get_auth_headers()
                    headers.update({
                        "accept": "application/json, text/plain, */*",
                        "user-agent": "Mozilla/5.0 (Home Assistant Integration)",
                    })
                    
                    site = getattr(self, "site", DEFAULT_SITE)
                    endpoint = f"/proxy/network/api/s/{site}/stat/sdn"
                    
                    # Extract host without port
                    base_host = self.host.split(":")[0]
                    url = f"https://{base_host}:443{endpoint}"
                    
                    LOGGER.debug("Requesting SDN status from: %s", url)
                    async with self._session.get(
                        url, headers=headers, ssl=self.verify_ssl, timeout=10
                    ) as resp:
                        if resp.status == 200:
                            response = await resp.json()
                            if "data" in response and len(response["data"]) > 0:
                                data = response["data"][0]
                                LOGGER.debug("SDN status authenticated response: %s", data)
                        else:
                            LOGGER.debug("SDN status endpoint returned %s", resp.status)
                except Exception as ex:
                    LOGGER.debug("Error during authenticated SDN check: %s", str(ex))
            
            # If authenticated request failed or wasn't attempted, try direct request
            if not data:
                LOGGER.debug("Attempting direct SDN status check")
                
                # Create a proper URL for the SDN endpoint exactly as in the curl example
                site = getattr(self, "site", DEFAULT_SITE)
                
                # Extract host without port
                base_host = self.host.split(":")[0]
                url = f"https://{base_host}:443/proxy/network/api/s/{site}/stat/sdn"
                
                LOGGER.debug("Using direct SDN status URL: %s with SSL verification: %s", url, self.verify_ssl)
                
                # Build proper headers like in the curl example
                headers = {
                    "accept": "application/json, text/plain, */*",
                    "user-agent": "Mozilla/5.0 (Home Assistant Integration)"
                }
                
                LOGGER.debug("Requesting direct SDN status from: %s", url)
                
                # Use a fresh session for this specific request
                connector = aiohttp.TCPConnector(verify_ssl=self.verify_ssl)
                async with aiohttp.ClientSession(connector=connector) as session:
                    try:
                        async with session.get(
                            url, headers=headers, timeout=10
                        ) as resp:
                            if resp.status == 200:
                                response = await resp.json()
                                LOGGER.debug("SDN response: %s", response)
                                if "data" in response and len(response["data"]) > 0:
                                    data = response["data"][0]
                                    LOGGER.debug("SDN status direct response: %s", data)
                            else:
                                LOGGER.debug("Direct SDN status endpoint returned %s", resp.status)
                    except Exception as ex:
                        LOGGER.debug("Error during direct SDN check: %s", str(ex))
            
            # Process the data from either authenticated or direct request
            if data:
                # Check for is_udm field in response
                if "is_udm" in data:
                    is_udm = data["is_udm"]
                    LOGGER.debug("SDN endpoint reports is_udm: %s", is_udm)
                    
                    # Log additional device information if available
                    if "enabled" in data:
                        LOGGER.debug("Device enabled: %s", data["enabled"])
                    if "connected" in data:
                        LOGGER.debug("Device connected: %s", data["connected"])
                    if "is_cloud_key" in data:
                        LOGGER.debug("Device is_cloud_key: %s", data["is_cloud_key"])
                    
                    if is_udm:
                        LOGGER.info("Device confirmed as UniFi OS through SDN endpoint")
                        self._apply_unifi_os_setting(True)
                        return True
            
            # If we've reached this point and didn't get a positive is_udm value,
            # we'll assume this is a UDM for compatibility with older firmware
            LOGGER.debug("Assuming device is UniFi OS for compatibility")
            self._apply_unifi_os_setting(True)
            return True
            
        except Exception as err:
            LOGGER.error("Error checking UDM status: %s", str(err))
            # Fall back to assuming it's a UDM
            LOGGER.debug("Falling back to assuming device is UniFi OS")
            self._apply_unifi_os_setting(True)
            return True

    def _apply_unifi_os_setting(self, value: bool) -> None:
        """Apply the is_unifi_os setting to the controller."""
        try:
            if self.controller:
                # Try to set attribute directly
                self.controller.is_unifi_os = value
                LOGGER.debug("Successfully set controller.is_unifi_os = %s", value)
        except Exception as err:
            LOGGER.error("Error setting is_unifi_os: %s", err)

    async def _manual_websocket_connect(self) -> None:
        """Attempt a manual WebSocket connection when the library's method fails."""
        try:
            # First, check if we have the controller
            if not hasattr(self, "controller") or not self.controller:
                LOGGER.error("No controller attribute available, cannot use manual connection")
                raise RuntimeError("No controller attribute available")
            
            # Use site value, defaulting to "default" if not set
            site = self.site or "default"
            
            # Create the correct WebSocket URL for UniFi OS devices
            correct_url = f"wss://{self.host}/proxy/network/wss/s/{site}/events?clients=v2"
            LOGGER.info("Using manual WebSocket URL for UniFi OS device: %s", correct_url)
            
            # Different controller versions might have different WebSocket implementations
            # Try all known patterns:
            
            # Pattern 1: Controller has websocket attribute
            if hasattr(self.controller, "websocket"):
                ws = self.controller.websocket
                
                # Set the URL directly if possible
                if hasattr(ws, "url"):
                    ws.url = correct_url
                    LOGGER.debug("Set WebSocket URL to %s", correct_url)
                
                # Try to start the connection
                if hasattr(ws, "start"):
                    await ws.start()
                    LOGGER.info("Manual WebSocket connection started successfully via websocket.start()")
                    return
                elif hasattr(ws, "connect"):
                    await ws.connect()
                    LOGGER.info("Manual WebSocket connection started successfully via websocket.connect()")
                    return
            
            # Pattern 2: Controller has connectivity.websocket method
            if hasattr(self.controller, "connectivity") and hasattr(self.controller.connectivity, "websocket"):
                # Store the original URL construction method
                conn = self.controller.connectivity
                
                # Ensure is_unifi_os is set
                if hasattr(conn, "is_unifi_os"):
                    conn.is_unifi_os = True
                    LOGGER.debug("Set connectivity.is_unifi_os to True")
                
                # Define a callback function to handle the data
                async def manual_ws_callback(data):
                    if self._ws_callback:
                        self._ws_callback(data)
                        LOGGER.debug("WebSocket message forwarded to callback")
                    else:
                        LOGGER.debug("WebSocket message received but no callback set")
                
                # Call the websocket method with our callback
                LOGGER.info("Using connectivity.websocket method with manual callback")
                await conn.websocket(manual_ws_callback)
                LOGGER.info("Manual WebSocket connection established via connectivity.websocket")
                return
            
            # If none of those methods worked, we can't establish a WebSocket connection
            LOGGER.error("No viable WebSocket connection method found on controller")
            raise RuntimeError("No viable WebSocket connection method found on controller")
                
        except Exception as err:
            LOGGER.error("Error in manual WebSocket connection: %s", err)
            raise RuntimeError(f"Manual WebSocket connection failed: {err}") from err

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
                await self._custom_websocket.stop()
                LOGGER.debug("Custom WebSocket stopped")
            except Exception as err:
                LOGGER.warning("Error stopping custom WebSocket: %s", err)

    async def clear_cache(self) -> None:
        """Clear the controller's cache to ensure fresh data is fetched."""
        LOGGER.debug("Clearing API cache to ensure fresh data")
        try:
            # First check if controller exists
            if not self.controller:
                LOGGER.warning("Cannot clear cache - controller not initialized")
                return
                
            # Check if the controller has a cache to clear
            if hasattr(self.controller, "cache"):
                # Some aiounifi versions have a cache with a clear method
                if hasattr(self.controller.cache, "clear"):
                    self.controller.cache.clear()
                    LOGGER.debug("Successfully cleared controller cache")
                # Others might store cache as a dictionary
                elif isinstance(self.controller.cache, dict):
                    self.controller.cache = {}
                    LOGGER.debug("Reset controller cache dictionary")
                else:
                    LOGGER.debug("Controller has cache attribute but not clearable: %s", 
                               type(self.controller.cache))
            else:
                # If no cache attribute, we might need to reset data attributes directly
                LOGGER.debug("Controller has no cache attribute, trying data attribute reset")
                
                # Reset any data attributes that might be cached
                if hasattr(self.controller, "data"):
                    if isinstance(self.controller.data, dict):
                        # Only clear specific endpoints that we use
                        for key in list(self.controller.data.keys()):
                            if any(endpoint in key for endpoint in [
                                "firewall-policies", 
                                "firewall/rules", 
                                "port-forward", 
                                "routing", 
                                "network/traffic-rules"
                            ]):
                                LOGGER.debug("Clearing cached data for endpoint: %s", key)
                                self.controller.data.pop(key, None)
                                
                LOGGER.debug("Cache clearing operations completed")
        
        except Exception as err:
            LOGGER.warning("Error clearing controller cache: %s", err)

class _Capabilities:
    """Store API capabilities."""

    def __init__(self, api: UDMAPI):
        """Initialize capabilities."""
        self.api = api
        self._legacy_firewall_checked = False
        self._has_legacy_firewall = False
        self._zone_based_firewall_checked = False
        self._has_zone_based_firewall = False
        self._legacy_traffic_checked = False
        self._has_legacy_traffic = False

    @property
    def legacy_firewall(self) -> bool:
        """Return if legacy firewall is supported.
        
        Note: This is based on the cached value. Call check_legacy_firewall() first
        to properly detect capability.
        """
        return self._has_legacy_firewall
    
    async def check_legacy_firewall(self) -> bool:
        """Check if legacy firewall is supported and cache the result."""
        if not self._legacy_firewall_checked:
            # Actually check if legacy firewall has rules instead of assuming
            try:
                legacy_rules = await self.api.get_legacy_firewall_rules()
                self._has_legacy_firewall = len(legacy_rules) > 0
                LOGGER.debug("Legacy firewall capability detected: %s", self._has_legacy_firewall)
            except Exception:
                self._has_legacy_firewall = False
            self._legacy_firewall_checked = True
        return self._has_legacy_firewall

    @property
    def zone_based_firewall(self) -> bool:
        """Return if zone based firewall is supported."""
        if not self._zone_based_firewall_checked:
            self._has_zone_based_firewall = self.api.controller is not None and hasattr(self.api.controller, "firewall_policies")
            LOGGER.debug("Zone-based firewall capability detected: %s", self._has_zone_based_firewall)
            self._zone_based_firewall_checked = True
        return self._has_zone_based_firewall

    @property
    def legacy_traffic(self) -> bool:
        """Return if legacy traffic rules are supported."""
        if not self._legacy_traffic_checked:
            self._has_legacy_traffic = True  # Assume supported until proven otherwise
            self._legacy_traffic_checked = True
        return self._has_legacy_traffic