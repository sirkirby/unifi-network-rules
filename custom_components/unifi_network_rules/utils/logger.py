import asyncio
import logging
from functools import wraps

_LOGGER = logging.getLogger(__name__)

def log_call(func):
    """Decorator to log function entry and exit."""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        _LOGGER.debug("Entering: %s", func.__name__)
        try:
            result = await func(*args, **kwargs)
            _LOGGER.debug("Exiting: %s", func.__name__)
            return result
        except Exception as e:
            _LOGGER.exception("Error in %s: %s", func.__name__, str(e))
            raise

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        _LOGGER.debug("Entering: %s", func.__name__)
        try:
            result = func(*args, **kwargs)
            _LOGGER.debug("Exiting: %s", func.__name__)
            return result
        except Exception as e:
            _LOGGER.exception("Error in %s: %s", func.__name__, str(e))
            raise

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

def debug(msg: str, *args, **kwargs):
    """Log a debug message."""
    _LOGGER.debug(msg, *args, **kwargs)

def info(msg: str, *args, **kwargs):
    """Log an info message."""
    _LOGGER.info(msg, *args, **kwargs)

def error(msg: str, *args, **kwargs):
    """Log an error message."""
    _LOGGER.error(msg, *args, **kwargs)

def warning(msg: str, *args, **kwargs):
    """Log a warning message."""
    _LOGGER.warning(msg, *args, **kwargs)

def exception(msg: str, *args, **kwargs):
    """Log an exception with traceback."""
    _LOGGER.exception(msg, *args, **kwargs)
