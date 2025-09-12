"""Logging utilities for UniFi Network Rules."""
from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import Any, Callable, TypeVar

from ..const import (
    LOGGER, 
    LOG_WEBSOCKET, 
    LOG_API_CALLS, 
    LOG_DATA_UPDATES,
    LOG_ENTITY_CHANGES
)

F = TypeVar("F", bound=Callable[..., Any])

def _is_debug_enabled() -> bool:
    """Check if debug logging is enabled through Home Assistant."""
    return LOGGER.isEnabledFor(logging.DEBUG)

def log_websocket(msg: str, *args: Any, **kwargs: Any) -> None:
    """DEPRECATED - WebSocket support removed. This function is kept for backward compatibility."""
    # Check if the message contains indication that it's rule-related
    is_rule_related = False
    if "rule event" in msg.lower() or "rule message" in msg.lower() or "rule-related" in msg.lower():
        is_rule_related = True
    
    # Always log rule events as INFO, use DEBUG for everything else
    if is_rule_related:
        LOGGER.info(f"[WEBSOCKET] {msg}", *args, **kwargs)
    elif LOG_WEBSOCKET or _is_debug_enabled():
        LOGGER.debug(f"[WEBSOCKET] {msg}", *args, **kwargs)

def log_api(msg: str, *args: Any, **kwargs: Any) -> None:
    """Log API-related debug messages if API debugging is enabled."""
    if LOG_API_CALLS or _is_debug_enabled():
        LOGGER.debug(f"[API] {msg}", *args, **kwargs)

def log_data(msg: str, *args: Any, **kwargs: Any) -> None:
    """Log data update debug messages if data debugging is enabled."""
    if LOG_DATA_UPDATES or _is_debug_enabled():
        LOGGER.debug(f"[DATA] {msg}", *args, **kwargs)

def log_entity(msg: str, *args: Any, **kwargs: Any) -> None:
    """Log entity-related debug messages if entity debugging is enabled."""
    if LOG_ENTITY_CHANGES or _is_debug_enabled():
        LOGGER.debug(f"[ENTITY] {msg}", *args, **kwargs)

def debug(msg: str, *args: Any, **kwargs: Any) -> None:
    """Log debug messages if debug is enabled."""
    if _is_debug_enabled():
        LOGGER.debug(msg, *args, **kwargs)

def log_execution_time(func: Callable) -> Callable:
    """Log execution time of the decorated function."""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        debug("Calling %s", func.__name__)
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        debug("Completed %s in %.3f seconds", func.__name__, end_time - start_time)
        return result
    return wrapper

def async_log_execution_time(func: Callable) -> Callable:
    """Log execution time of the decorated async function."""
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        debug("Calling %s", func.__name__)
        start_time = time.time()
        result = await func(*args, **kwargs)
        end_time = time.time()
        debug("Completed %s in %.3f seconds", func.__name__, end_time - start_time)
        return result
    return wrapper

# Provide a sanitizer function to clean sensitive data from logs
def sanitize_auth_data(data: dict) -> dict:
    """Remove sensitive authentication data for logging."""
    if not data or not isinstance(data, dict):
        return data
        
    sanitized = data.copy()
    sensitive_keys = ["password", "token", "apiKey", "api_key", "secret", "auth", "credentials", "cookie"]
    
    for key in sensitive_keys:
        if key in sanitized:
            sanitized[key] = "***REDACTED***"
            
    return sanitized

def log_call(func: F) -> F:
    """Log when a function is called."""
    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        """Wrap async function."""
        LOGGER.debug("Calling %s", func.__name__)
        try:
            result = await func(*args, **kwargs)
            LOGGER.debug("Completed %s", func.__name__)
            return result
        except Exception as err:
            LOGGER.error("Error in %s: %s", func.__name__, str(err))
            raise

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """Wrap sync function."""
        LOGGER.debug("Calling %s", func.__name__)
        try:
            result = func(*args, **kwargs)
            LOGGER.debug("Completed %s", func.__name__)
            return result
        except Exception as err:
            LOGGER.error("Error in %s: %s", func.__name__, str(err))
            raise

    if asyncio.iscoroutinefunction(func):
        return async_wrapper  # type: ignore[return-value]
    return wrapper  # type: ignore[return-value]

def info(msg: str, *args, **kwargs):
    """Log an info message."""
    LOGGER.info(msg, *args, **kwargs)

def error(msg: str, *args, **kwargs):
    """Log an error message."""
    LOGGER.error(msg, *args, **kwargs)

def warning(msg: str, *args, **kwargs):
    """Log a warning message."""
    LOGGER.warning(msg, *args, **kwargs)

def exception(msg: str, *args, **kwargs):
    """Log an exception with traceback."""
    LOGGER.exception(msg, *args, **kwargs)
