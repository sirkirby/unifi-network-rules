"""Logging utilities for UniFi Network Rules."""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from typing import Any, TypeVar
from urllib.parse import urlsplit, urlunsplit

from homeassistant.helpers.redact import async_redact_data

from ..const import LOG_API_CALLS, LOG_DATA_UPDATES, LOG_ENTITY_CHANGES, LOG_WEBSOCKET, LOGGER

F = TypeVar("F", bound=Callable[..., Any])
REDACTED = "***REDACTED***"

SENSITIVE_LOG_KEYS = frozenset(
    {
        "adopt_ip",
        "apiKey",
        "api_key",
        "auth",
        "authorization",
        "connect_request_ip",
        "cookie",
        "cookies",
        "credentials",
        "deviceToken",
        "email",
        "gateway",
        "host",
        "hostname",
        "inform_ip",
        "ip",
        "ipv6",
        "key",
        "mac",
        "maskedEmail",
        "nfc_display_id",
        "nfc_token",
        "openvpn_password",
        "openvpn_username",
        "passphrase",
        "password",
        "phone",
        "private_key",
        "psk",
        "secret",
        "serial",
        "service_mac",
        "session",
        "set-cookie",
        "sso_account",
        "sso_username",
        "sso_uuid",
        "token",
        "uid_sso_account",
        "user",
        "user_email",
        "user_id",
        "username",
        "wireguard_private_key",
        "x-auth-token",
        "x-csrf-token",
        "x-updated-csrf-token",
        "x_authkey",
        "x_auth_token",
    }
)

_SENSITIVE_LOG_KEYS_NORMALIZED = {key.replace("-", "_").casefold() for key in SENSITIVE_LOG_KEYS}
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "authkey",
    "cookie",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)
_IP_KEY_SUFFIXES = ("_ip", "_ipv6")
_MAC_KEY_SUFFIXES = ("_mac", "_macs", "mac_address", "mac_addresses")
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_IPV4_PATTERN = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)
_MAC_PATTERN = re.compile(r"\b[0-9A-F]{2}(?::[0-9A-F]{2}){5}\b", re.IGNORECASE)
_UNR_ENTITY_ID_PATTERN = re.compile(r"\b(?:switch\.)?unr_[a-z0-9_]+\b", re.IGNORECASE)
_URL_AUTHORITY_PATTERN = re.compile(r"\b(?P<scheme>https?|wss?)://[^/\s)\]>'\"]+")
_LOG_REDACTION_FILTER: RedactingLogFilter | None = None
_REDACTED_LOGGER_PREFIXES = ("aiounifi", "custom_components.unifi_network_rules")


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


def _redacted(_: Any) -> str:
    """Return the integration's redaction marker."""
    return REDACTED


def _is_sensitive_log_key(key: Any) -> bool:
    """Return whether a mapping key should be redacted in logs."""
    normalized = str(key).replace("-", "_").casefold()
    return (
        normalized in _SENSITIVE_LOG_KEYS_NORMALIZED
        or any(part in normalized for part in _SENSITIVE_KEY_PARTS)
        or normalized.endswith(_IP_KEY_SUFFIXES)
        or normalized.endswith(_MAC_KEY_SUFFIXES)
    )


def _collect_sensitive_keys(data: Any) -> set[Any]:
    """Collect exact sensitive keys so Home Assistant's redactor can redact them."""
    keys: set[Any] = set()

    if isinstance(data, Mapping):
        for key, value in data.items():
            if _is_sensitive_log_key(key):
                keys.add(key)
            else:
                keys.update(_collect_sensitive_keys(value))
    elif isinstance(data, list):
        for item in data:
            keys.update(_collect_sensitive_keys(item))

    return keys


def sanitize_auth_data(data: Any) -> Any:
    """Remove sensitive authentication and identity data before logging."""
    if not data:
        return data

    to_redact = dict.fromkeys(_collect_sensitive_keys(data), _redacted)
    return _sanitize_log_data(async_redact_data(data, to_redact))


def _safe_log_url(value: str) -> str:
    """Redact URL authority while preserving scheme and path for debugging."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value

    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        return value

    return urlunsplit((parsed.scheme, REDACTED, parsed.path, parsed.query, ""))


def _sanitize_log_text(value: str) -> str:
    """Redact common PII shapes from unstructured log text."""
    value = _URL_AUTHORITY_PATTERN.sub(r"\g<scheme>://" + REDACTED, value)
    value = _UNR_ENTITY_ID_PATTERN.sub(REDACTED, value)
    value = _EMAIL_PATTERN.sub(REDACTED, value)
    value = _IPV4_PATTERN.sub(REDACTED, value)
    return _MAC_PATTERN.sub(REDACTED, value)


def _sanitize_log_data(value: Any) -> Any:
    """Recursively sanitize non-keyed string values in structured log data."""
    if isinstance(value, Mapping):
        return {key: _sanitize_log_data(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_sanitize_log_data(item) for item in value]

    if isinstance(value, str):
        return _sanitize_log_text(_safe_log_url(value))

    return value


def _sanitize_json_log_text(value: str) -> str | None:
    """Sanitize a string containing a JSON object or array."""
    stripped = value.strip()
    if not stripped or stripped[0] not in {"{", "["}:
        return None

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None

    return json.dumps(sanitize_auth_data(parsed), separators=(",", ":"), sort_keys=True)


def sanitize_log_value(value: Any) -> Any:
    """Return a logging value with sensitive payloads redacted."""
    if isinstance(value, bytes | bytearray):
        return f"<{len(value)} bytes>"

    if isinstance(value, str):
        return _sanitize_json_log_text(value) or _sanitize_log_text(_safe_log_url(value))

    if isinstance(value, Mapping | list):
        return sanitize_auth_data(value)

    if value.__class__.__name__ == "ClientResponse":
        status = getattr(value, "status", "unknown")
        reason = getattr(value, "reason", "")
        return f"<ClientResponse [{status} {reason}]>"

    if not isinstance(value, bool | int | float | type(None)):
        return _sanitize_log_text(str(value))

    return value


class RedactingLogFilter(logging.Filter):
    """Logging filter that redacts structured values before formatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive log record arguments."""
        if not record.name.startswith(_REDACTED_LOGGER_PREFIXES):
            return True

        record.msg = sanitize_log_value(record.msg)

        if isinstance(record.args, Mapping):
            record.args = sanitize_auth_data(record.args)
        elif isinstance(record.args, tuple):
            record.args = tuple(sanitize_log_value(arg) for arg in record.args)
        elif record.args:
            record.args = sanitize_log_value(record.args)

        return True


def _add_filter_if_missing(target: logging.Handler | logging.Logger) -> None:
    """Add the shared redaction filter to a logger or handler."""
    if _LOG_REDACTION_FILTER is not None and not any(
        existing is _LOG_REDACTION_FILTER for existing in target.filters
    ):
        target.addFilter(_LOG_REDACTION_FILTER)


def install_aiounifi_log_redaction() -> None:
    """Install redaction filters for integration and aiounifi logs."""
    global _LOG_REDACTION_FILTER

    if _LOG_REDACTION_FILTER is None:
        _LOG_REDACTION_FILTER = RedactingLogFilter()

    for logger_name in (*_REDACTED_LOGGER_PREFIXES, "aiounifi.interfaces.connectivity"):
        _add_filter_if_missing(logging.getLogger(logger_name))

    for handler in logging.getLogger().handlers:
        _add_filter_if_missing(handler)


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
