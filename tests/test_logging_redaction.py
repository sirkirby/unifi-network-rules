"""Tests for log redaction helpers."""

import logging

from custom_components.unifi_network_rules.utils.logger import (
    RedactingLogFilter,
    sanitize_auth_data,
    sanitize_log_value,
)


def test_sanitize_auth_data_redacts_nested_sensitive_values():
    """Test nested authentication and identity fields are redacted."""
    payload = {
        "Username": "admin",
        "password": "secret",
        "headers": {
            "Set-Cookie": "TOKEN=abc",
            "X-Csrf-Token": "csrf-token",
        },
        "devices": [
            {
                "mac": "aa:bb:cc:dd:ee:ff",
                "ip": "192.168.1.10",
                "name": "switch-office",
            }
        ],
    }

    redacted = sanitize_auth_data(payload)

    assert redacted["Username"] == "***REDACTED***"
    assert redacted["password"] == "***REDACTED***"
    assert redacted["headers"]["Set-Cookie"] == "***REDACTED***"
    assert redacted["headers"]["X-Csrf-Token"] == "***REDACTED***"
    assert redacted["devices"][0]["mac"] == "***REDACTED***"
    assert redacted["devices"][0]["ip"] == "***REDACTED***"
    assert redacted["devices"][0]["name"] == "switch-office"

    assert payload["password"] == "secret"
    assert payload["devices"][0]["ip"] == "192.168.1.10"


def test_sanitize_log_value_redacts_controller_url():
    """Test URLs logged by dependencies do not expose controller addresses."""
    assert sanitize_log_value("https://192.168.1.1:443/api/auth/login") == "https://***REDACTED***/api/auth/login"


def test_sanitize_log_value_redacts_unifi_entity_ids():
    """Test entity IDs derived from user rule names are redacted."""
    assert sanitize_log_value("switch.unr_traffic_route_personal_laptop_to_fiber") == "***REDACTED***"


def test_sanitize_log_value_redacts_json_websocket_payload():
    """Test JSON websocket payloads are sanitized when logged as strings."""
    payload = (
        '{"meta":{"message":"sta:sync","mac":"aa:bb:cc:dd:ee:ff"},'
        '"data":[{"hostname":"laptop","last_ip":"192.168.1.20",'
        '"user":"11:22:33:44:55:66","url":"https://192.168.1.1/fingerprint",'
        '"msg":"User[11:22:33:44:55:66] connected"}]}'
    )

    redacted = sanitize_log_value(payload)

    assert "aa:bb:cc:dd:ee:ff" not in redacted
    assert "11:22:33:44:55:66" not in redacted
    assert "192.168.1.20" not in redacted
    assert "192.168.1.1" not in redacted
    assert "laptop" not in redacted
    assert "***REDACTED***" in redacted
    assert "sta:sync" in redacted


def test_redacting_log_filter_sanitizes_aiounifi_debug_record():
    """Test aiounifi-style debug records are redacted before formatting."""
    record = logging.LogRecord(
        name="aiounifi.interfaces.connectivity",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg="sending (to %s) %s, %s, %s",
        args=(
            "https://192.168.1.1:443/api/auth/login",
            "post",
            {"username": "admin", "password": "secret", "rememberMe": True},
            True,
        ),
        exc_info=None,
    )

    RedactingLogFilter().filter(record)
    message = record.getMessage()

    assert "192.168.1.1" not in message
    assert "admin" not in message
    assert "secret" not in message
    assert "***REDACTED***" in message
    assert "rememberMe" in message


def test_redacting_log_filter_sanitizes_integration_child_logger_record():
    """Test integration child logger records are redacted before formatting."""
    record = logging.LogRecord(
        name="custom_components.unifi_network_rules.switches.base",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg="Entity %s updated from %s",
        args=("switch.unr_traffic_route_personal_laptop_to_fiber", "aa:bb:cc:dd:ee:ff"),
        exc_info=None,
    )

    RedactingLogFilter().filter(record)
    message = record.getMessage()

    assert "personal_laptop" not in message
    assert "aa:bb:cc:dd:ee:ff" not in message
    assert message == "Entity ***REDACTED*** updated from ***REDACTED***"


def test_redacting_log_filter_sanitizes_stringified_response_objects():
    """Test response-like objects cannot leak URLs through stringification."""

    class ResponseLike:
        def __str__(self) -> str:
            return "<ClientResponse(https://192.168.1.1/api) [200 None]>"

    record = logging.LogRecord(
        name="aiounifi.interfaces.connectivity",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg="received %s",
        args=(ResponseLike(),),
        exc_info=None,
    )

    RedactingLogFilter().filter(record)
    message = record.getMessage()

    assert "192.168.1.1" not in message
    assert "https://***REDACTED***/api" in message


def test_redacting_log_filter_summarizes_bytes():
    """Test raw response bodies are summarized rather than logged."""
    record = logging.LogRecord(
        name="aiounifi.interfaces.connectivity",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg="data (from %s) %s",
        args=("https://192.168.1.1:443/api/auth/login", b'{"username":"admin"}'),
        exc_info=None,
    )

    RedactingLogFilter().filter(record)
    message = record.getMessage()

    assert "192.168.1.1" not in message
    assert "admin" not in message
    assert "<20 bytes>" in message
