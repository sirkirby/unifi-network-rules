"""API request handling for UniFi API."""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Coroutine

from ..const import LOGGER

class ApiHandlerMixin:
    """Mixin class for API request handling."""
    
    async def _handle_api_request(self, request_type: str, action_coroutine: Callable[[], Coroutine]) -> Tuple[bool, Optional[Any]]:
        """Handle API request with error handling and retry support.
        
        Args:
            request_type: Description of the request for logging
            action_coroutine: Coroutine to call to make the actual request
            
        Returns:
            Tuple of (success, result_or_error_message)
            - If success is True, the second item is the result
            - If success is False, the second item is an error message
        """
        try:
            # Check rate limiting first
            if hasattr(self, "_rate_limited") and self._rate_limited:
                current_time = asyncio.get_event_loop().time()
                if current_time < getattr(self, "_rate_limit_until", 0):
                    wait_time = int(getattr(self, "_rate_limit_until", 0) - current_time)
                    error_msg = f"Rate limited. Try again in {wait_time} seconds."
                    LOGGER.warning("%s: %s", request_type, error_msg)
                    return False, error_msg
            
            # Execute the API request
            LOGGER.debug("Executing API request: %s", request_type)
            response = await action_coroutine()
            
            # Success path
            if hasattr(self, "_consecutive_failures"):
                self._consecutive_failures = 0  # Reset failure counter
                
            return True, response
            
        except Exception as err:
            # Log the error
            LOGGER.error("%s failed: %s", request_type, str(err))
            
            # Try to determine if it's an authentication error
            error_str = str(err).lower()
            auth_keywords = ["auth", "login", "unauthorized", "forbidden", "401", "403"]
            
            is_auth_error = any(keyword in error_str for keyword in auth_keywords)
            
            # Save the last error message for auth detection
            if hasattr(self, "_last_error_message"):
                self._last_error_message = error_str
            
            # Handle based on error type
            if is_auth_error:
                # Handle authentication errors with retry
                LOGGER.warning("Authentication issue detected, attempting to refresh session")
                return await self._handle_authentication_retry(request_type, action_coroutine, error_str)
            else:
                # For non-auth errors, check for rate limiting indicators
                if "429" in error_str or "too many requests" in error_str:
                    # Rate limiting detected
                    if hasattr(self, "_consecutive_failures"):
                        self._consecutive_failures += 1
                    
                    # Calculate backoff
                    if hasattr(self, "_max_backoff"):
                        backoff = min(30 * (2 ** (getattr(self, "_consecutive_failures", 1) - 1)), 
                                    getattr(self, "_max_backoff", 300))
                    else:
                        backoff = 60  # Default backoff
                        
                    # Apply rate limiting
                    if hasattr(self, "_rate_limited"):
                        self._rate_limited = True
                    if hasattr(self, "_rate_limit_until"):
                        self._rate_limit_until = asyncio.get_event_loop().time() + backoff
                        
                    error_msg = f"Rate limited. Try again in {backoff} seconds."
                    LOGGER.warning("%s: %s", request_type, error_msg)
                    return False, error_msg
                else:
                    # Regular error
                    if hasattr(self, "_consecutive_failures"):
                        self._consecutive_failures += 1
                        
                    return False, str(err)

    async def _handle_authentication_retry(self, request_type: str, action_coroutine: Callable[[], Coroutine], 
                                         error_context: str) -> Tuple[bool, Optional[Any]]:
        """Handle authentication retry for API requests.
        
        Args:
            request_type: Description of the request for logging
            action_coroutine: Coroutine to call to make the actual request
            error_context: Original error message for context
            
        Returns:
            Same as _handle_api_request
        """
        # Check if we have a session refresh method
        if not hasattr(self, "refresh_session"):
            LOGGER.error("Cannot retry %s: No refresh_session method available", request_type)
            return False, f"Authentication error: {error_context}"
        
        try:
            # Try to refresh the session
            LOGGER.info("Attempting to refresh session before retrying %s", request_type)
            refresh_success = await self.refresh_session()
            
            if not refresh_success:
                LOGGER.error("Failed to refresh session, cannot retry %s", request_type)
                return False, f"Session refresh failed: {error_context}"
            
            # Session refreshed, now retry the original request
            LOGGER.info("Session refreshed, retrying %s", request_type)
            
            try:
                # Execute the API request again
                response = await action_coroutine()
                
                # Success path on retry
                LOGGER.info("Successfully executed %s after session refresh", request_type)
                if hasattr(self, "_consecutive_failures"):
                    self._consecutive_failures = 0  # Reset failure counter
                    
                return True, response
                
            except Exception as retry_err:
                # Failed again even after refresh
                LOGGER.error("%s failed after session refresh: %s", request_type, str(retry_err))
                if hasattr(self, "_consecutive_failures"):
                    self._consecutive_failures += 1
                    
                return False, f"Failed after session refresh: {str(retry_err)}"
                
        except Exception as refresh_err:
            # Error during refresh attempt
            LOGGER.error("Error during session refresh: %s", str(refresh_err))
            if hasattr(self, "_consecutive_failures"):
                self._consecutive_failures += 1
                
            return False, f"Session refresh error: {str(refresh_err)}"
            
    async def reset_rate_limit(self) -> bool:
        """Reset rate limiting."""
        if hasattr(self, "_rate_limited"):
            self._rate_limited = False
        if hasattr(self, "_rate_limit_until"):
            self._rate_limit_until = 0
        if hasattr(self, "_consecutive_failures"):
            self._consecutive_failures = 0
        LOGGER.info("Rate limiting reset")
        return True 