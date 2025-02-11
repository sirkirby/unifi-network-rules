import asyncio
import logging
from functools import wraps

_LOG = logging.getLogger(__name__)

def log_call(func):
    """Decorator to log function entry and exit."""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        _LOG.debug("Entering: %s", func.__name__)
        result = await func(*args, **kwargs)
        _LOG.debug("Exiting: %s", func.__name__)
        return result

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        _LOG.debug("Entering: %s", func.__name__)
        result = func(*args, **kwargs)
        _LOG.debug("Exiting: %s", func.__name__)
        return result

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

def debug(msg, *args, **kwargs):
    """Simple wrapper for _LOG.debug."""
    _LOG.debug(msg, *args, **kwargs)
