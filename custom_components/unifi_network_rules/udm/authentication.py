"""Authentication and session management for UniFi API."""

import asyncio
import time
from typing import Any, Callable, Dict, Optional, Tuple

import aiohttp
from http.cookies import SimpleCookie
import logging

from ..const import LOGGER
from .api_base import CannotConnect, InvalidAuth

class AuthenticationMixin:
    """Mixin class for authentication operations."""
    
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
        
        # For debugging - always log the exact host and port we're using
        LOGGER.debug("Using base_host=%s and port=%d for UniFi connection", base_host, port)
        
        # Important: Store base_host (without port) in self.host to avoid port duplication issues
        # This ensures any code that appends a port later won't create "host:443:8443" errors
        self.host = base_host
        
        # Create Configuration object for controller
        controller_initialized = False
        try:
            # Try to create a Configuration object directly
            self._config = self._create_controller_configuration(base_host, port)
            
            LOGGER.debug("Created Configuration object with host %s and port %d", 
                         base_host, port)
                         
            # Now create the Controller with the Configuration object
            self.controller = self._create_controller(self._config)
            LOGGER.debug("Successfully created Controller with Configuration object")
            controller_initialized = True
            
        except (TypeError, ValueError) as config_err:
            LOGGER.warning("Could not create Controller with Configuration object: %s", config_err)
            LOGGER.debug("Falling back to direct Controller initialization")
            
            # Try direct Controller initialization
            try:
                self.controller = self._create_controller_direct(base_host, port)
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
                
                # Try to login
                await self.controller.login()
                
                # Success - reset attempt counter
                self._login_attempt_count = 0
                if hasattr(self, "_last_successful_login"):
                    self._last_successful_login = current_time
                    
                LOGGER.info("Successfully logged in to controller")
                return True
                
            except Exception as err:
                LOGGER.error("Login attempt failed: %s", err)
                
                # Check for auth failure vs connectivity error
                error_str = str(err).lower()
                if "unauthorized" in error_str or "forbidden" in error_str:
                    LOGGER.error("Authentication failure detected")
                    if hasattr(self, "_auth_failure_callback") and self._auth_failure_callback:
                        try:
                            LOGGER.debug("Calling authentication failure callback")
                            await self._auth_failure_callback(self)
                        except Exception as callback_err:
                            LOGGER.error("Error in auth failure callback: %s", callback_err)
                    raise InvalidAuth(f"Authentication failed: {err}")
                else:
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

    async def refresh_session(self) -> bool:
        """Refresh the controller session."""
        try:
            # Check if we need to login again
            need_login = False
            
            # Detect if session is expired or missing
            if hasattr(self.controller, "session") and not self.controller.session:
                need_login = True
            
            # If login is needed, try it
            if need_login:
                LOGGER.info("Refreshing expired session...")
                return await self._try_login()
            
            # Session looks valid
            return True
        except Exception as err:
            LOGGER.error("Error refreshing session: %s", err)
            return False

    async def async_connect(self) -> bool:
        """Connect to the UniFi controller.
        
        This is a wrapper around _try_login to enable reconnection in async_refresh.
        """
        try:
            return await self._try_login()
        except Exception as err:
            LOGGER.error("Error connecting to UniFi controller: %s", err)
            return False

    # Helper methods that would be defined in implementation
    def _create_controller_configuration(self, base_host, port):
        """Create controller configuration.
        Note: This is a stub that would be replaced by the actual implementation.
        """
        from aiounifi.models.configuration import Configuration
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
    
    def _create_controller_direct(self, base_host, port):
        """Create controller directly.
        Note: This is a stub that would be replaced by the actual implementation.
        """
        from aiounifi.controller import Controller
        return Controller(
            session=self._session,
            host=base_host,
            port=port,
            username=self.username, 
            password=self.password,
            site=self.site,
            verify_ssl=self.verify_ssl
        ) 