"""Tests for the UniFi Network Rules WebSocket functionality."""
import asyncio
import pytest
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from aiohttp import WSMsgType, ClientWebSocketResponse

from custom_components.unifi_network_rules.udm.websocket import CustomUnifiWebSocket, WebSocketMixin
from custom_components.unifi_network_rules.udm.api import UDMAPI

@pytest.fixture
def ws_client():
    """Return a CustomUnifiWebSocket instance."""
    session = AsyncMock()
    client = CustomUnifiWebSocket(
        host="unifi.local",
        site="default",
        session=session,
        headers={"Cookie": "auth=token", "X-CSRF-Token": "csrf_token"},
        ssl=False
    )
    return client

@pytest.fixture
def api() -> UDMAPI:
    """Return a UDMAPI instance with mocked controller."""
    api = UDMAPI(
        host="unifi.local",
        username="admin",
        password="password",
        site="default",
        verify_ssl=False,
    )
    api.controller = AsyncMock()
    api._initialized = True
    api._session = AsyncMock()
    return api

@pytest.mark.asyncio
async def test_websocket_build_url(ws_client):
    """Test building the WebSocket URL."""
    url = ws_client._build_url()
    assert url == "wss://unifi.local:443/proxy/network/wss/s/default/events"

@pytest.mark.asyncio
async def test_websocket_get_all_url_variants(ws_client):
    """Test getting all WebSocket URL variants."""
    variants = ws_client._get_all_url_variants()
    # Check that we have the expected number of variants
    assert len(variants) == 3
    # Check that all variants contain the host and site
    for variant in variants:
        assert "unifi.local" in variant
        assert "/default/" in variant or "namespace" in variant

@pytest.mark.asyncio
async def test_websocket_set_callbacks(ws_client):
    """Test setting WebSocket callbacks."""
    callback = Mock()
    
    # Test setting message callback
    ws_client.set_message_callback(callback)
    assert ws_client._message_callback == callback
    
    # Test setting compatibility callback
    compatibility_callback = Mock()
    ws_client.set_callback(compatibility_callback)
    assert ws_client._callback == compatibility_callback

@pytest.mark.asyncio
async def test_websocket_connect_and_handle_messages(ws_client):
    """Test WebSocket connection and message handling."""
    # Create a mock WebSocket
    mock_ws = AsyncMock()
    
    # Set up the mock session's ws_connect to return the mock WebSocket
    ws_client._session.ws_connect = AsyncMock(return_value=mock_ws)
    
    # Set up a message handler that we can test directly
    test_message = {
        "meta": {"message": "firewall.update"},  # Use a rule-related message that will not be filtered
        "data": {"key": "value"}
    }
    
    # Set up a callback with a regular Mock (not AsyncMock)
    # The code in CustomUnifiWebSocket doesn't await the callback
    callback = Mock()
    ws_client._message_callback = callback
    
    # Verify the URL is constructed correctly
    url = ws_client._build_url()
    assert "unifi.local" in url
    assert "/proxy/network/wss/s/default/events" in url
    
    # Call the message handler directly
    await ws_client._handle_message(json.dumps(test_message))
    
    # Verify the callback was called with the parsed message
    callback.assert_called_once()
    call_args = callback.call_args[0][0]
    assert call_args["meta"]["message"] == "firewall.update"
    assert call_args["data"]["key"] == "value"

@pytest.mark.asyncio
async def test_websocket_handle_message(ws_client):
    """Test handling WebSocket messages."""
    # Create a test message with rule-related content (should trigger callback)
    rule_message = json.dumps({
        "meta": {"message": "firewall.update"},
        "data": {"rule_id": "123", "enabled": True}
    })
    
    # Set up a callback that we'll manually check was called 
    mock_callback = Mock()
    # Use a normal Mock for simple assertion
    ws_client._message_callback = mock_callback
    
    # Call the handle_message method directly
    await ws_client._handle_message(rule_message)
    
    # Verify the callback was called with the parsed message
    mock_callback.assert_called_once()
    call_args = mock_callback.call_args[0][0]
    assert call_args["meta"]["message"] == "firewall.update"
    assert call_args["data"]["rule_id"] == "123"

@pytest.mark.asyncio
async def test_websocket_message_filtering(ws_client):
    """Test WebSocket message filtering for non-rule updates."""
    # Set up a callback
    callback = AsyncMock()
    ws_client.set_message_callback(callback)
    
    # Create a test message for device status (should be filtered)
    device_status_message = json.dumps({
        "meta": {"message": "device.status"},
        "data": {"some": "data"}
    })
    
    # Call the handle_message method
    await ws_client._handle_message(device_status_message)
    
    # Verify the callback was NOT called since device.status should be filtered
    callback.assert_not_called()

@pytest.mark.asyncio
async def test_start_websocket_mixin(api):
    """Test starting WebSocket with the WebSocketMixin."""
    # Mock _get_auth_headers
    api._get_auth_headers = AsyncMock(return_value={"Cookie": "auth=token", "X-CSRF-Token": "csrf_token"})
    
    # Mock the CustomUnifiWebSocket class
    with patch("custom_components.unifi_network_rules.udm.websocket.CustomUnifiWebSocket") as mock_ws_class:
        # Create a mock instance
        mock_ws = AsyncMock()
        mock_ws.connect = AsyncMock()
        mock_ws_class.return_value = mock_ws
        
        # Call start_websocket
        await api.start_websocket()
        
        # Verify that CustomUnifiWebSocket was created with the right params
        mock_ws_class.assert_called_once()
        call_args = mock_ws_class.call_args
        assert call_args[1]["host"] == "unifi.local"
        assert call_args[1]["site"] == "default"
        assert call_args[1]["headers"] == {"Cookie": "auth=token", "X-CSRF-Token": "csrf_token"}
        
        # Verify that connect was called
        mock_ws.connect.assert_called_once()
        
        # Verify that the custom WebSocket was stored
        assert api._custom_websocket == mock_ws

@pytest.mark.asyncio
async def test_set_websocket_callback_mixin(api):
    """Test setting WebSocket callback with the WebSocketMixin."""
    # Create a callback function
    callback = AsyncMock()
    
    # Create mock objects
    api._custom_websocket = AsyncMock()
    api._custom_websocket.set_message_callback = AsyncMock()
    api.controller.ws_handler = None
    
    # Call set_websocket_callback
    api.set_websocket_callback(callback)
    
    # Verify the callback was set correctly
    assert api._ws_message_handler == callback
    assert api.controller.ws_handler == callback
    api._custom_websocket.set_message_callback.assert_called_once_with(callback)

@pytest.mark.asyncio
async def test_stop_websocket_mixin(api):
    """Test stopping WebSocket with the WebSocketMixin."""
    # Create mock objects
    api._custom_websocket = AsyncMock()
    api._custom_websocket.close = AsyncMock()
    api.controller.stop_websocket = AsyncMock()
    
    # Call stop_websocket
    await api.stop_websocket()
    
    # Verify both WebSockets were stopped
    api.controller.stop_websocket.assert_called_once()
    api._custom_websocket.close.assert_called_once()

@pytest.mark.asyncio
async def test_get_auth_headers(api):
    """Test getting authentication headers for WebSocket."""
    # Create mock session with cookies
    cookie_jar = MagicMock()
    cookie1 = MagicMock()
    cookie1.value = "value1"
    cookies = {"cookie1": cookie1}
    cookie_jar.filter_cookies.return_value = cookies
    api._session.cookie_jar = cookie_jar
    
    # Set CSRF token
    api._csrf_token = "csrf_token"
    
    # Call _get_auth_headers
    headers = await api._get_auth_headers()
    
    # Verify the headers
    assert "Cookie" in headers
    assert "cookie1=value1" in headers["Cookie"]
    assert headers["X-CSRF-Token"] == "csrf_token"