"""Tests for the UniFi Network Rules API functionality."""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from custom_components.unifi_network_rules.udm.api import UDMAPI
from custom_components.unifi_network_rules.udm.api_base import InvalidAuth

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
    api.controller = MagicMock()
    api._initialized = True
    return api

@pytest.mark.asyncio
async def test_init_creates_controller():
    """Test init creates a controller."""
    with patch(
        "custom_components.unifi_network_rules.udm.authentication.AuthenticationMixin._create_controller_configuration"
    ) as mock_create_config, patch(
        "custom_components.unifi_network_rules.udm.authentication.AuthenticationMixin._create_controller"
    ) as mock_create_controller, patch(
        "custom_components.unifi_network_rules.udm.authentication.AuthenticationMixin._try_login",
        return_value=True
    ) as mock_login, patch(
        "custom_components.unifi_network_rules.udm.api.UDMAPI.refresh_all"
    ) as mock_refresh:
        
        mock_config = MagicMock()
        mock_create_config.return_value = mock_config
        mock_controller = MagicMock()
        mock_create_controller.return_value = mock_controller
        
        api = UDMAPI(host="unifi.local", username="admin", password="password")
        await api.async_init()
        
        mock_create_config.assert_called_once()
        mock_create_controller.assert_called_once_with(mock_config)
        mock_login.assert_called_once()
        mock_refresh.assert_called_once()
        assert api.controller == mock_controller
        assert api.initialized

@pytest.mark.asyncio
async def test_login_failure_raises_invalid_auth():
    """Test that login failure raises InvalidAuth."""
    with patch(
        "custom_components.unifi_network_rules.udm.authentication.AuthenticationMixin._create_controller_configuration"
    ) as mock_create_config, patch(
        "custom_components.unifi_network_rules.udm.authentication.AuthenticationMixin._create_controller"
    ) as mock_create_controller, patch(
        "custom_components.unifi_network_rules.udm.authentication.AuthenticationMixin._try_login",
        side_effect=InvalidAuth("Authentication failed")
    ) as mock_login:
        
        mock_config = MagicMock()
        mock_create_config.return_value = mock_config
        mock_controller = MagicMock()
        mock_create_controller.return_value = mock_controller
        
        api = UDMAPI(host="unifi.local", username="admin", password="password")
        with pytest.raises(InvalidAuth):
            await api.async_init()

@pytest.mark.asyncio
async def test_cleanup(api):
    """Test the cleanup method closes resources."""
    # Mock API queue and controller
    api.api_queue = AsyncMock()
    api.api_queue.stop = AsyncMock()
    api.controller = AsyncMock()
    
    await api.cleanup()
    
    api.api_queue.stop.assert_called_once()
    # The controller itself isn't called, just used in the cleanup process
    assert api.controller is None  # Controller should be set to None after cleanup

@pytest.mark.asyncio
async def test_queue_api_operation(api):
    """Test that operations are properly queued."""
    # Create the API queue mock
    api.api_queue = AsyncMock()
    api.api_queue.add_operation = AsyncMock()
    
    # Create a mock operation function
    mock_operation = AsyncMock(return_value="success")
    
    # Queue the operation
    future = await api.queue_api_operation(mock_operation, "arg1", kwarg1="value1")
    
    # Verify that add_operation was called
    api.api_queue.add_operation.assert_called_once()
    
    # Complete the future to simulate the operation completing
    # Extract the wrapper function that was passed to add_operation
    wrapper_func = api.api_queue.add_operation.call_args[0][0]
    
    # Call the wrapper function to trigger the future completion
    await wrapper_func()
    
    # Verify the mock was called with the arguments
    mock_operation.assert_called_once_with("arg1", kwarg1="value1")
    
    # Check that the future was completed with the correct result
    assert await future == "success"

@pytest.mark.asyncio
async def test_create_api_request(api):
    """Test creating API requests."""
    # Mock the internal _create_api_request method
    api._create_api_request = Mock(return_value="api_request")
    
    # Test with standard parameters
    result = api.create_api_request("GET", "/api/endpoint", data={"key": "value"})
    
    api._create_api_request.assert_called_once_with("GET", "/api/endpoint", {"key": "value"}, False)
    assert result == "api_request"
    
    # Test with v2 API
    api._create_api_request.reset_mock()
    result = api.create_api_request("POST", "/api/v2/endpoint", data={"key": "value"}, is_v2=True)
    
    api._create_api_request.assert_called_once_with("POST", "/api/v2/endpoint", {"key": "value"}, True)
    assert result == "api_request"

@pytest.mark.asyncio
async def test_sanitize_data_for_logging():
    """Test that sensitive data is properly sanitized for logging."""
    api = UDMAPI(host="unifi.local", username="admin", password="password")
    
    # Test with sensitive data
    data = {
        "username": "admin",
        "password": "secret_password",
        "token": "secret_token",
        "key": "encryption_key",
        "psk": "pre_shared_key",
        "secret": "top_secret",
        "auth": "auth_token",
        "safe_field": "visible_data",
    }
    
    sanitized = api._sanitize_data_for_logging(data)
    
    # Sensitive fields should be redacted
    assert sanitized["password"] == "***REDACTED***"
    assert sanitized["token"] == "***REDACTED***"
    assert sanitized["key"] == "***REDACTED***"
    assert sanitized["psk"] == "***REDACTED***"
    assert sanitized["secret"] == "***REDACTED***"
    assert sanitized["auth"] == "***REDACTED***"
    
    # Safe fields should be unchanged
    assert sanitized["username"] == "admin"
    assert sanitized["safe_field"] == "visible_data"
    
    # Original data should be unchanged
    assert data["password"] == "secret_password"
    
    # Test with non-dict data
    assert api._sanitize_data_for_logging("string_data") == "string_data"
    assert api._sanitize_data_for_logging(None) is None