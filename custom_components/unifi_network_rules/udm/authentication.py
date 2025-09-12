"""Authentication and session management for UniFi API."""

import asyncio
import time
import aiohttp

from ..const import LOGGER
from .api_base import CannotConnect, InvalidAuth

class AuthenticationMixin:
    """Mixin class for authentication operations."""
    
    def __init__(self, *args, **kwargs):
        """Initialize AuthenticationMixin attributes."""
        # Initialize attributes, potentially overriding if called via super()
        # Rate Limiting for _try_login
        self._login_attempt_count = getattr(self, '_login_attempt_count', 0)
        self._max_login_attempts = getattr(self, '_max_login_attempts', 5) # e.g., 5 attempts
        self._login_cooldown = getattr(self, '_login_cooldown', 60) # e.g., 60 seconds cooldown
        self._last_login_attempt = getattr(self, '_last_login_attempt', 0)
        self._login_lock = getattr(self, '_login_lock', None)
        self._last_successful_login = getattr(self, '_last_successful_login', 0)
        self._min_login_interval = getattr(self, '_min_login_interval', 30)
        
        # Call super().__init__ if this mixin isn't the first in MRO
        # Check if super() provides an __init__ method before calling
        if hasattr(super(), '__init__'):
             super().__init__(*args, **kwargs)

    async def async_init(self, hass=None):
        """Initialize the UDM API."""
        LOGGER.debug("Initializing UDMAPI")

        # Store hass for later use
        self._hass = hass
        
        # Create session if not already provided
        if self._session is None:
            if hass is not None:
                from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
        
        LOGGER.debug("Using base_host=%s and port=%d for UniFi connection", base_host, port)
        
        # Important: Store base_host (without port) in self.host to avoid port duplication issues
        # This ensures any code that appends a port later won't create "host:443:8443" errors
        self.host = base_host
        
        # Create Configuration object for controller
        try:
            # Try to create a Configuration object directly
            self._config = self._create_controller_configuration(base_host, port)
            
            LOGGER.debug("Created Configuration object with host %s and port %d", 
                         base_host, port)
                         
            # Now create the Controller with the Configuration object
            self.controller = self._create_controller(self._config)
            LOGGER.debug("Successfully created Controller with Configuration object")
        except Exception as unknown_err:
            LOGGER.error("Unexpected error creating Configuration object: %s", unknown_err)
        
        # Verify controller was initialized
        if not self.controller:
            LOGGER.error("Failed to initialize controller. Cannot continue.")
            raise CannotConnect("Failed to initialize UniFi controller")
        
        # Always set UniFi OS detection to True
        self._apply_unifi_os_setting(True)
        LOGGER.info("Setting device type to UniFi OS for %s", self.host)
        
        # Try to login
        await self._try_login()
        
        self._initialized = True
        
        # Initialize and check capabilities
        if self._capabilities is None:
            from .capabilities import _Capabilities
            self._capabilities = _Capabilities(self)
        
        # Check legacy firewall capability
        await self._capabilities.check_legacy_firewall()
        
        # Initial refresh of all data
        await self.refresh_all()

    def _force_unifi_os_detection(self) -> None:
        """Force the UniFi OS detection flag if needed."""
        # Skip if controller isn't initialized yet
        if not self.controller:
            LOGGER.debug("Controller not initialized, skipping UniFi OS detection")
            return

        # Always set is_unifi_os to True for this integration
        LOGGER.debug("Setting is_unifi_os=True for UniFi OS device compatibility")
        self._apply_unifi_os_setting(True)

    async def _try_login(self) -> bool:
        """Attempt to log in to the controller."""
        # Create login lock if needed
        if not hasattr(self, "_login_lock") or self._login_lock is None:
            self._login_lock = asyncio.Lock()
        
        # Get current time for rate limiting
        current_time = time.time()
        
        # Check if we've exceeded login attempt limits
        if self._login_attempt_count >= self._max_login_attempts:
            # Check if we need to wait
            if current_time - self._last_login_attempt < self._login_cooldown:
                # Wait time remaining
                wait_time = self._login_cooldown - (current_time - self._last_login_attempt)
                LOGGER.warning(
                    "Login rate limited. Max attempts (%d) reached. Try again in %d seconds", 
                    self._max_login_attempts, int(wait_time)
                )
                raise CannotConnect(f"Login rate limited. Try again in {int(wait_time)} seconds")
            else:
                # Cooldown period passed, reset counter
                self._login_attempt_count = 0
        
        # Check minimum interval between login attempts
        if hasattr(self, "_last_successful_login"):
            if (current_time - self._last_successful_login < self._min_login_interval and 
                    self._last_successful_login > 0):
                LOGGER.debug(
                    "Skipping login attempt - less than %d seconds since last successful login",
                    self._min_login_interval
                )
                return True
        
        async with self._login_lock:
            # Prevent concurrent logins
            LOGGER.debug("Attempting login to controller")
            
            try:
                # Record the attempt
                self._last_login_attempt = current_time
                self._login_attempt_count += 1
                
                # Ensure the base path includes proxy prefix before login
                if hasattr(self.controller, "_base_path"):
                    original_path = self.controller._base_path
                    # Always set the base path to include /proxy/network/ for UDM devices
                    if not original_path.startswith("/proxy/network/"):
                        normalized_path = original_path.lstrip("/")
                        self.controller._base_path = f"/proxy/network/{normalized_path}"
                        LOGGER.debug("Updated base path before login: %s", self.controller._base_path)
                
                # Try to login
                await self.controller.login()
                
                # Success - reset attempt counter
                self._login_attempt_count = 0
                if hasattr(self, "_last_successful_login"):
                    self._last_successful_login = current_time
                    
                # Ensure the proxy prefix is correct after login
                self._ensure_proxy_prefix_in_path()
                    
                LOGGER.info("Successfully logged in to controller")
                return True
                
            except Exception as err:
                LOGGER.error("Login attempt failed: %s", err)
                
                # Check for auth failure vs connectivity error
                error_str = str(err).lower()
                status_code = getattr(err, 'status', None) # Try to get status code if it's an aiohttp error
                
                # --- Specific 429 Handling ---
                if status_code == 429 or "limit_reached" in error_str:
                    LOGGER.warning("Login failed due to rate limiting (429). Triggering cooldown.")
                    # Force cooldown by setting attempt count to max
                    self._login_attempt_count = self._max_login_attempts
                    self._last_login_attempt = time.time() # Ensure cooldown timer starts now
                    # Raise CannotConnect to prevent immediate retry by refresh_session
                    raise CannotConnect(f"Login rate limited (429): {err}")
                
                # --- General Auth Failure (401/403) ---
                elif "unauthorized" in error_str or "forbidden" in error_str or status_code in [401, 403]:
                    LOGGER.error("Authentication failure detected")
                    if hasattr(self, "_auth_failure_callback") and self._auth_failure_callback:
                        try:
                            LOGGER.debug("Calling authentication failure callback")
                            # Pass self if the callback expects it, adjust if needed
                            await self._auth_failure_callback(self) 
                        except Exception as callback_err:
                            LOGGER.error("Error in auth failure callback: %s", callback_err)
                    raise InvalidAuth(f"Authentication failed: {err}")
                else:
                    # Assume other errors are connectivity issues
                    raise CannotConnect(f"Connection failed: {err}")

    async def _check_udm_device(self, authenticated: bool = False) -> bool:
        """Check if the device is a UDM and set detection properly.
        
        In this integration, we always assume we're connecting to a UniFi OS device.
        """
        LOGGER.debug("Setting device type to UniFi OS for %s", self.host)
        self._apply_unifi_os_setting(True)
        return True

    def _apply_unifi_os_setting(self, value: bool) -> None:
        """Apply UniFi OS setting to controller and connectivity."""
        if self.controller:
            # Set on controller
            setattr(self.controller, "is_unifi_os", value)
            LOGGER.debug("Set controller.is_unifi_os = %s", value)
            
            # Set on connectivity if present
            if hasattr(self.controller, "connectivity"):
                conn = self.controller.connectivity
                setattr(conn, "is_unifi_os", value)
                LOGGER.debug("Set connectivity.is_unifi_os = %s", value)

    def set_auth_failure_callback(self, callback):
        """Set a callback to be called on authentication failure."""
        self._auth_failure_callback = callback

    async def refresh_session(self, force: bool = False) -> bool:
        """Refresh the authentication session to prevent expiration.
        
        Args:
            force: Force refresh even if recently refreshed
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Skip if we've refreshed recently (less than 5 minutes ago) unless forced
        current_time = time.time()
        min_refresh_interval = 300  # 5 minutes
        
        if not force and hasattr(self, "_last_session_refresh"):
            elapsed = current_time - self._last_session_refresh
            if elapsed < min_refresh_interval:
                LOGGER.debug(
                    "Skipping session refresh as it was refreshed %d seconds ago (interval: %d)", 
                    elapsed, min_refresh_interval
                )
                return True
                
        LOGGER.info("Refreshing authentication session")
        
        # Save existing path configuration before refresh
        original_base_path = getattr(self.controller, "_base_path", "")
        original_site_path = getattr(self.controller, "_site_path", "")
        
        # Log current path configuration
        LOGGER.debug("Current path config before refresh - base: %s, site: %s", 
                   original_base_path, original_site_path)
        
        try:
            # Check for session token using a more compatible approach
            # Instead of relying on is_logged_in attribute which doesn't exist in some versions
            has_session = (
                hasattr(self.controller, "session") and 
                self.controller.session is not None and
                getattr(self.controller, "headers", {}).get("Cookie") is not None
            )
            
            if not has_session:
                LOGGER.warning("No valid session token, performing full login")
                login_success = await self._try_login()
                
                # After login, ensure proxy prefix is in base path
                self._ensure_proxy_prefix_in_path()
                
                return login_success
                
            # For a refresh, we'll use a special endpoint that keeps the session alive
            LOGGER.debug("Attempting to refresh existing session")
            
            # Different controllers use different methods to refresh a session
            # Check if there's a refresh endpoint available
            refresh_endpoint = "api/auth/refresh" 
            
            # Create the refresh request - without payload for refresh requests
            req = self._create_api_request("POST", refresh_endpoint, None)
            
            # Make the request
            async with asyncio.timeout(10):
                resp = await self.controller.request(req)
                
            if resp.status == 200:
                LOGGER.info("Session refresh successful")
                self._last_session_refresh = current_time
                
                # Ensure the proxy prefix is in base path
                self._ensure_proxy_prefix_in_path()
                
                return True
            else:
                # If refresh fails, try a full login
                LOGGER.warning(
                    "Session refresh failed (status %d), falling back to full login", 
                    resp.status
                )
                login_success = await self._try_login()
                
                # After login, ensure proxy prefix is in base path
                self._ensure_proxy_prefix_in_path()
                
                return login_success
                
        except Exception as err:
            LOGGER.error("Error refreshing session: %s", err)
            
            # Restore original paths if needed
            if original_base_path != getattr(self.controller, "_base_path", ""):
                LOGGER.debug("Restoring original base path: %s", original_base_path)
                self.controller._base_path = original_base_path
                
            if original_site_path != getattr(self.controller, "_site_path", ""):
                LOGGER.debug("Restoring original site path: %s", original_site_path)
                self.controller._site_path = original_site_path
                
            # Try full login if refresh fails
            try:
                LOGGER.warning("Session refresh failed, attempting full login")
                login_success = await self._try_login()
                
                # After login, ensure proxy prefix is in base path
                self._ensure_proxy_prefix_in_path()
                
                return login_success
            except Exception as login_err:
                LOGGER.error("Full login failed after session refresh error: %s", login_err)
                return False
                
    def _ensure_proxy_prefix_in_path(self) -> None:
        """Ensure the proxy prefix is in the base path."""
        if not hasattr(self.controller, "_base_path"):
            return
            
        # Always use the proxy prefix for UDM controllers
        current_path = self.controller._base_path
        
        # If proxy prefix is missing, add it
        if not current_path.startswith("/proxy/network/"):
            # Normalize the path by removing any leading slashes
            normalized_path = current_path.lstrip("/")
            # Add the prefix
            self.controller._base_path = f"/proxy/network/{normalized_path}"
            LOGGER.debug("Updated base path with proxy prefix: %s", self.controller._base_path)

    # Helper methods that would be defined in implementation
    def _create_controller_configuration(self, base_host, port):
        """Create controller configuration.
        Note: This is a stub that would be replaced by the actual implementation.
        """
        from aiounifi.models.configuration import Configuration
        
        # Ensure we have a valid session
        if not hasattr(self, "_session") or self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession()
            LOGGER.debug("Created new aiohttp ClientSession for controller configuration")
            
        return Configuration(
            session=self._session,
            host=base_host, 
            port=port,
            username=self.username,
            password=self.password,
            site=self.site,
            ssl_context=self.verify_ssl
        )
    
    def _create_controller(self, config):
        """Create controller with configuration.
        Note: This is a stub that would be replaced by the actual implementation.
        """
        from aiounifi.controller import Controller
        return Controller(config)
