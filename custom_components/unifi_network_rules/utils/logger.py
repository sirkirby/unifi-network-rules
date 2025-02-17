"""Logging utilities for UniFi Network Rules."""
from __future__ import annotations
import asyncio
from functools import wraps
from typing import Any, Callable, TypeVar

from ..const import LOGGER

F = TypeVar("F", bound=Callable[..., Any])

def log_call(func: F) -> F:
    """Log when a function is called."""
    @wraps(func)
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

    @wraps(func)
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

def debug(msg: str, *args, **kwargs):
    """Log a debug message."""
    LOGGER.debug(msg, *args, **kwargs)

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
