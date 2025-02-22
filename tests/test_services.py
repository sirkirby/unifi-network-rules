"""Test services module."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
import json
import os
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from custom_components.unifi_network_rules.services import (
    async_refresh_service,
    async_backup_rules_service,
    async_restore_rules_service,
    async_bulk_update_rules_service,
    async_setup_services
)

@pytest.fixture
def mock_api():
    """Create a mock API instance."""
    api = MagicMock()
    api.capabilities.zone_based_firewall = True
    api.capabilities.traffic_routes = True
    api.capabilities.legacy_firewall = True
    api.capabilities.legacy_traffic = True
    api.update_firewall_policy = AsyncMock(return_value=(True, None))
    api.update_traffic_route = AsyncMock(return_value=(True, None))
    api.update_port_forward_rule = AsyncMock(return_value=(True, None))
    api.update_legacy_firewall_rule = AsyncMock(return_value=(True, None))
    api.update_legacy_traffic_rule = AsyncMock(return_value=(True, None))
    api.update_rule_state = AsyncMock(return_value=(True, None))
    return api

@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator instance."""
    coordinator = MagicMock()
    coordinator.async_refresh = AsyncMock()
    coordinator.data = {}
    return coordinator

@pytest.fixture
def mock_data():
    """Create mock data for backup/restore tests."""
    return {
        "firewall_policies": [
            {
                "_id": "policy1",
                "name": "Policy 1",
                "enabled": True,
                "predefined": False
            }
        ],
        "traffic_routes": [
            {
                "_id": "route1",
                "name": "Route 1",
                "enabled": True
            }
        ],
        "port_forward_rules": [
            {
                "_id": "port1",
                "name": "Minecraft",
                "enabled": True
            }
        ],
        "legacy_firewall_rules": [
            {
                "_id": "fw1",
                "name": "Legacy FW Rule",
                "enabled": True
            }
        ],
        "legacy_traffic_rules": [
            {
                "_id": "tr1",
                "name": "Legacy Traffic Rule",
                "enabled": True
            }
        ]
    }

@pytest.mark.asyncio
async def test_async_setup_services(hass: HomeAssistant):
    """Test service registration."""
    mock_services = MagicMock()
    hass.services = mock_services
    await async_setup_services(hass)
    assert mock_services.async_register.call_count == 4
    registered_services = [call[0][1] for call in mock_services.async_register.call_args_list]
    assert "refresh" in registered_services
    assert "backup_rules" in registered_services
    assert "restore_rules" in registered_services
    assert "bulk_update_rules" in registered_services

@pytest.mark.asyncio
async def test_refresh_service(hass: HomeAssistant, mock_coordinator):
    """Test refresh service."""
    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "coordinator": mock_coordinator
        }
    }

    await async_refresh_service(hass, MagicMock())
    mock_coordinator.async_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_backup_rules_service(hass: HomeAssistant, mock_coordinator, mock_data):
    """Test backup service."""
    mock_coordinator.data = mock_data
    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "coordinator": mock_coordinator
        }
    }

    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    # Create a StringIO to capture the written data
    from io import StringIO
    string_io = StringIO()
    
    with patch("builtins.open", mock_open()) as mock_file:
        mock_file.return_value.__enter__.return_value = string_io
        await async_backup_rules_service(hass, mock_call)
        mock_file.assert_called_once_with(hass.config.path("test_backup.json"), 'w', encoding='utf-8')
        
        # Get the written data directly from our StringIO object
        string_io.seek(0)
        written_data = json.loads(string_io.getvalue())
        assert "test_entry" in written_data
        assert all(key in written_data["test_entry"] for key in mock_data.keys())

@pytest.mark.asyncio
async def test_backup_rules_service_no_data(hass: HomeAssistant, mock_coordinator):
    """Test backup service with no data."""
    mock_coordinator.data = {}
    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "coordinator": mock_coordinator
        }
    }

    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    with pytest.raises(HomeAssistantError, match="No data available to backup"):
        await async_backup_rules_service(hass, mock_call)

@pytest.mark.asyncio
async def test_restore_rules_service(hass: HomeAssistant, mock_api, mock_coordinator, mock_data):
    """Test restore service with various filters."""
    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    backup_data = {"test_entry": mock_data}
    
    test_cases = [
        # Test case with name filter
        {
            "call_data": {"filename": "test.json", "name_filter": "Policy"},
            "expected_calls": {"update_firewall_policy": 1}
        },
        # Test case with rule type filter
        {
            "call_data": {"filename": "test.json", "rule_types": ["port_forward"]},
            "expected_calls": {"update_port_forward_rule": 1}
        },
        # Test case with rule IDs
        {
            "call_data": {"filename": "test.json", "rule_ids": ["policy1"]},
            "expected_calls": {"update_firewall_policy": 1}
        }
    ]

    for test_case in test_cases:
        mock_call = MagicMock()
        mock_call.data = test_case["call_data"]

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(backup_data))):
            await async_restore_rules_service(hass, mock_call)
            
            for method, count in test_case["expected_calls"].items():
                assert getattr(mock_api, method).call_count == count

        # Reset mock call counts
        mock_api.reset_mock()

@pytest.mark.asyncio
async def test_restore_rules_service_file_not_found(hass: HomeAssistant, mock_api):
    """Test restore service with missing backup file."""
    hass.data["unifi_network_rules"] = {
        "test_entry": {"api": mock_api}
    }

    mock_call = MagicMock()
    mock_call.data = {"filename": "nonexistent.json"}

    with patch("os.path.exists", return_value=False):
        with pytest.raises(HomeAssistantError, match="Backup file not found"):
            await async_restore_rules_service(hass, mock_call)

@pytest.mark.asyncio
async def test_bulk_update_rules_service(hass: HomeAssistant, mock_api, mock_coordinator):
    """Test bulk update service."""
    mock_coordinator.data = {
        "firewall_policies": [
            {"_id": "policy1", "name": "Test Policy", "enabled": True},
            {"_id": "policy2", "name": "Other Policy", "enabled": True}
        ],
        "traffic_routes": [
            {"_id": "route1", "name": "Test Route", "enabled": True}
        ]
    }

    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    mock_call = MagicMock()
    mock_call.data = {
        "name_filter": "Test",
        "state": False
    }

    await async_bulk_update_rules_service(hass, mock_call)

    # Should update both the policy and route with "Test" in the name
    assert mock_api.update_rule_state.call_count == 2
    mock_coordinator.async_refresh.assert_called_once()