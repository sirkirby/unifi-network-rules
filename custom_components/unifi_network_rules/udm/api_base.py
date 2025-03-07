"""Base API module for UniFi Dream Machine."""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import aiohttp
from http.cookies import SimpleCookie

from ..const import (
    DEFAULT_SITE,
    LOGGER
)

# Error classes
class UnifiNetworkRulesError(HomeAssistantError):
    """Base exception for UniFi Network Rules errors."""

class CannotConnect(UnifiNetworkRulesError):
    """Exception for connection errors."""

class InvalidAuth(UnifiNetworkRulesError):
    """Exception for authentication errors."""

class UDMAPI:
    """Base class for UniFi Dream Machine API."""
    
    def __init__(self, host: str, username: str, password: str, site: str = DEFAULT_SITE, 
                 verify_ssl: bool | str = False):
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
        
        # Authentication lock to prevent parallel login attempts
        self._login_lock = None
        self._last_successful_login = 0
        self._min_login_interval = 15  # seconds
    
    # Import the necessary methods here to maintain interface compatibility
    # These will be overridden by mixin classes
    
    @property
    def initialized(self) -> bool:
        """Return True if API is initialized."""
        return self._initialized
    
    @property
    def capabilities(self):
        """Return API capabilities."""
        from .capabilities import _Capabilities
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
            
    def _create_api_request(self, method: str, path: str, data: dict = None, is_v2: bool = False):
        """Create an API request object for the controller.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API endpoint path
            data: Optional data payload for POST/PUT requests
            is_v2: Whether to use the V2 API request format
            
        Returns:
            ApiRequest or ApiRequestV2 object that can be passed to controller.request()
        """
        if is_v2:
            from aiounifi.models.api import ApiRequestV2
            return ApiRequestV2(method=method, path=path, data=data)
        else:
            from aiounifi.models.api import ApiRequest
            return ApiRequest(method=method, path=path, data=data) 