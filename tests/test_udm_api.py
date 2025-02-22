"""Test UDM API module."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import ssl
import aiohttp
import asyncio
from aiohttp import ClientSession, CookieJar, WSMsgType
from aiounifi.models.api import ApiRequest, ApiRequestV2
from aiounifi.errors import (
    AiounifiException,
    BadGateway,
    LoginRequired,
    RequestError,
    ResponseError,
    ServiceUnavailable,
    Unauthorized,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.unifi_network_rules.udm_api import (
    UDMAPI,
    CannotConnect,
    InvalidAuth,
    UnifiNetworkRulesError
)

@pytest.fixture(autouse=True)
async def cleanup_event_loop():
    """Ensure event loop is clean before and after each test."""
    # Store the current loop
    loop = asyncio.get_running_loop()
    yield
    
    # Cancel all running tasks
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()
    
    # Allow tasks to complete their cancellation
    if pending:
        await asyncio.wait(pending, timeout=1)

@pytest.fixture
async def mock_session():
    """Create a mock aiohttp session."""
    session = MagicMock()
    session.close = AsyncMock(return_value=True)
    return session

@pytest.fixture
async def mock_controller():
    """Create a mock UniFi controller."""
    controller = MagicMock()
    # Mock successful login by default
    controller.login = AsyncMock()
    controller.login.return_value = None
    
    controller.sites = MagicMock()
    controller.sites.update = AsyncMock()
    controller.sites.update.return_value = None

    # Mock interfaces with AsyncMock update methods
    interfaces = [
        'firewall_policies',
        'traffic_rules',
        'port_forwarding',
        'traffic_routes',
        'wlans',
        'system_information',
        'firewall_zones'
    ]

    for interface in interfaces:
        interface_mock = MagicMock()
        interface_mock.update = AsyncMock()
        interface_mock.update.return_value = None
        interface_mock.values = MagicMock(return_value=[])
        interface_mock.toggle = AsyncMock()
        interface_mock.toggle.return_value = True
        interface_mock.remove_item = AsyncMock()
        interface_mock.remove_item.return_value = None
        setattr(controller, interface, interface_mock)

    controller.request = AsyncMock()
    controller.request.return_value = {}
    controller.start_websocket = AsyncMock()
    controller.start_websocket.return_value = None
    controller.stop_websocket = AsyncMock()
    controller.stop_websocket.return_value = None
    
    return controller

@pytest.fixture
async def api(mock_session):
    """Create a UDMAPI instance for testing."""
    api_instance = UDMAPI(
        host="192.168.1.1",
        username="admin",
        password="password",
        verify_ssl=False
    )
    api_instance._session = mock_session
    yield api_instance
    # Ensure cleanup happens
    await api_instance.cleanup()

@pytest.mark.asyncio
async def test_async_init_success(api, mock_controller):
    """Test successful initialization."""
    with patch('aiounifi.Controller', return_value=mock_controller):
        async with asyncio.timeout(2):  # Add timeout
            await api.async_init()
            assert api.initialized
            assert api.controller == mock_controller
            mock_controller.login.assert_called_once()
            mock_controller.sites.update.assert_called_once()

@pytest.mark.asyncio
async def test_async_init_cannot_connect(api, mock_controller):
    """Test initialization with connection failure."""
    mock_controller.login.side_effect = BadGateway()
    with patch('aiounifi.Controller', return_value=mock_controller):
        async with asyncio.timeout(2):  # Add timeout
            with pytest.raises(CannotConnect):
                await api.async_init()
            assert not api.initialized

@pytest.mark.asyncio
async def test_async_init_invalid_auth(api, mock_controller):
    """Test initialization with invalid authentication."""
    mock_controller.login.side_effect = LoginRequired()
    with patch('aiounifi.Controller', return_value=mock_controller):
        async with asyncio.timeout(2):  # Add timeout
            with pytest.raises(InvalidAuth):
                await api.async_init()
            assert not api.initialized

@pytest.mark.asyncio
async def test_firewall_policies(api, mock_controller):
    """Test firewall policy operations."""
    mock_policies = [
        {"_id": "1", "name": "Policy1", "enabled": True, "predefined": False},
        {"_id": "2", "name": "Policy2", "enabled": False, "predefined": True}
    ]
    mock_controller.firewall_policies.values.return_value = mock_policies

    with patch('aiounifi.Controller', return_value=mock_controller):
        async with asyncio.timeout(2):  # Add timeout
            await api.async_init()
            
            # Default should exclude predefined
            policies = await api.get_firewall_policies()
            assert len(policies) == 1
            assert not policies[0]["predefined"]
            
            # With include_predefined=True, should get all policies
            all_policies = await api.get_firewall_policies(include_predefined=True)
            assert len(all_policies) == 2
            
            new_policy = {"name": "NewPolicy", "enabled": True}
            await api.add_firewall_policy(new_policy)
            mock_controller.request.assert_called_with(
                ApiRequestV2("POST", "firewall-policies", new_policy)
            )
            
            # Verify update was called:
            # 1. During init refresh_all
            # 2. During first get_firewall_policies
            # 3. During second get_firewall_policies
            assert mock_controller.firewall_policies.update.call_count == 3

@pytest.mark.asyncio
async def test_traffic_rules(api, mock_controller):
    """Test traffic rule operations."""
    mock_rules = [
        {"_id": "1", "name": "Rule1", "enabled": True},
        {"_id": "2", "name": "Rule2", "enabled": False}
    ]
    mock_controller.traffic_rules.values.return_value = mock_rules
    
    with patch('aiounifi.Controller', return_value=mock_controller):
        async with asyncio.timeout(2):  # Add timeout
            await api.async_init()
            
            rules = await api.get_traffic_rules()
            assert len(rules) == 2
            
            await api.toggle_traffic_rule("1", True)
            mock_controller.traffic_rules.toggle.assert_called_with("1", True)

@pytest.mark.asyncio
async def test_port_forwards(api, mock_controller):
    """Test port forward operations."""
    mock_forwards = [
        {"_id": "1", "name": "Forward1", "enabled": True},
        {"_id": "2", "name": "Forward2", "enabled": False}
    ]
    mock_controller.port_forwarding.values.return_value = mock_forwards
    
    with patch('aiounifi.Controller', return_value=mock_controller):
        async with asyncio.timeout(2):  # Add timeout
            await api.async_init()
            
            forwards = await api.get_port_forwards()
            assert len(forwards) == 2
            
            new_forward = {"name": "NewForward", "enabled": True}
            await api.add_port_forward(new_forward)
            mock_controller.request.assert_called_with(
                ApiRequest("POST", "portforward", new_forward)
            )

@pytest.mark.asyncio
async def test_wlan_operations(api, mock_controller):
    """Test WLAN operations."""
    mock_wlans = [
        {"_id": "1", "name": "WLAN1", "enabled": True},
        {"_id": "2", "name": "WLAN2", "enabled": False}
    ]
    mock_controller.wlans.values.return_value = mock_wlans
    mock_controller.wlans.__getitem__.return_value = mock_wlans[0]
    
    with patch('aiounifi.Controller', return_value=mock_controller):
        await api.async_init()
        
        wlans = await api.get_wlans()
        assert len(wlans) == 2

@pytest.mark.asyncio
async def test_websocket_operations(api, mock_controller):
    """Test websocket operations."""
    with patch('aiounifi.Controller', return_value=mock_controller):
        await api.async_init()
        
        await api.start_websocket()
        mock_controller.start_websocket.assert_called_once()
        
        await api.stop_websocket()
        mock_controller.stop_websocket.assert_called_once()
        
        callback = AsyncMock()
        api.set_websocket_callback(callback)
        assert mock_controller.ws_handler == callback

@pytest.mark.asyncio
async def test_cleanup(api, mock_controller):
    """Test cleanup operations."""
    with patch('aiounifi.Controller', return_value=mock_controller):
        async with asyncio.timeout(2):  # Add timeout
            await api.async_init()
            await api.cleanup()
            assert not api.initialized
            assert api.controller is None

@pytest.mark.asyncio
async def test_refresh_all(api, mock_controller):
    """Test refresh all operation."""
    with patch('aiounifi.Controller', return_value=mock_controller):
        async with asyncio.timeout(2):  # Add timeout
            await api.async_init()
            await api.refresh_all()
            
            # Each update method should be called twice:
            # - Once during init
            # - Once during explicit refresh_all
            assert mock_controller.firewall_policies.update.call_count == 2
            assert mock_controller.traffic_rules.update.call_count == 2
            assert mock_controller.port_forwarding.update.call_count == 2
            assert mock_controller.traffic_routes.update.call_count == 2
            assert mock_controller.wlans.update.call_count == 2

@pytest.mark.asyncio
async def test_get_rule_status(api, mock_controller):
    """Test getting rule status."""
    mock_rule = {
        "_id": "test_rule",
        "enabled": True,
        "last_modified": "2024-01-01T00:00:00Z"
    }
    mock_controller.firewall_policies.__contains__.return_value = True
    mock_controller.firewall_policies.__getitem__.return_value = mock_rule
    
    with patch('aiounifi.Controller', return_value=mock_controller):
        async with asyncio.timeout(2):  # Add timeout
            await api.async_init()
            
            status = await api.get_rule_status("test_rule")
            assert status["active"] is True
            assert status["type"] == "firewall_policy"
            assert status["last_modified"] == "2024-01-01T00:00:00Z"