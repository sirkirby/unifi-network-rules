"""Test UniFi Network Rules services."""
import pytest
from unittest.mock import patch, MagicMock, mock_open, AsyncMock
import json
import os
from homeassistant.core import HomeAssistant
from custom_components.unifi_network_rules.services import (
    async_refresh_service,
    async_backup_rules_service,
    async_restore_rules_service,
)
from custom_components.unifi_network_rules.const import DOMAIN
import asyncio
import warnings

@pytest.fixture
def mock_data():
    """Fixture with test data."""
    return {
        "firewall_policies": [{
            "_id": "1",
            "name": "Test Policy",
            "enabled": True,
            "action": "allow",
            "predefined": False
        }],
        "traffic_routes": [{
            "_id": "2",
            "description": "Test Route",
            "enabled": True,
            "matching_target": "INTERNET"
        }],
        "firewall_rules": [{
            "_id": "3",
            "name": "Test Rule",
            "enabled": True,
            "action": "accept"
        }],
        "traffic_rules": [{
            "_id": "4",
            "description": "Test Traffic Rule",
            "enabled": True
        }]
    }

@pytest.fixture
async def mock_coordinator():
    """Mock coordinator fixture."""
    coordinator = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator

@pytest.fixture
async def mock_api():
    """Mock API fixture."""
    api = MagicMock()
    api.capabilities.zone_based_firewall = True
    api.capabilities.legacy_firewall = True
    api.capabilities.traffic_routes = True
    api.update_firewall_policy = AsyncMock(return_value=(True, None))
    api.update_traffic_route = AsyncMock(return_value=(True, None))
    api.update_legacy_firewall_rule = AsyncMock(return_value=(True, None))
    api.update_legacy_traffic_rule = AsyncMock(return_value=(True, None))
    return api

@pytest.fixture
def mock_successful_api():
    """Fixture for API with all successful operations."""
    api = MagicMock()
    api.update_firewall_policy = AsyncMock(return_value=(True, None))
    api.update_traffic_route = AsyncMock(return_value=(True, None))
    api.update_legacy_firewall_rule = AsyncMock(return_value=(True, None))
    api.update_legacy_traffic_rule = AsyncMock(return_value=(True, None))
    api.capabilities.zone_based_firewall = True
    api.capabilities.legacy_firewall = True
    api.capabilities.traffic_routes = True
    return api

@pytest.fixture
def mock_failed_api():
    """Fixture for API with all failed operations."""
    api = MagicMock()
    api.update_firewall_policy = AsyncMock(return_value=(False, "API Error"))
    api.update_traffic_route = AsyncMock(return_value=(False, "API Error"))
    api.update_legacy_firewall_rule = AsyncMock(return_value=(False, "API Error"))
    api.update_legacy_traffic_rule = AsyncMock(return_value=(False, "API Error"))
    api.capabilities.zone_based_firewall = True
    api.capabilities.legacy_firewall = True
    api.capabilities.traffic_routes = True
    return api

@pytest.mark.asyncio
async def test_refresh_service_with_multiple_entries(hass: HomeAssistant, mock_coordinator):
    """Test the refresh service with multiple config entries."""
    mock_coordinator2 = MagicMock()
    mock_coordinator2.async_request_refresh = AsyncMock()

    hass.data[DOMAIN] = {
        "entry1": {"coordinator": mock_coordinator},
        "entry2": {"coordinator": mock_coordinator2}
    }

    await async_refresh_service(hass, MagicMock())
    mock_coordinator.async_request_refresh.assert_called_once()
    mock_coordinator2.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_refresh_service_no_coordinator(hass: HomeAssistant):
    """Test refresh service when no coordinator is available."""
    hass.data[DOMAIN] = {
        "test_entry": {}  # Empty entry without coordinator
    }

    await async_refresh_service(hass, MagicMock())
    # Should handle gracefully without error

@pytest.mark.asyncio
async def test_backup_rules_service_full(hass: HomeAssistant, mock_coordinator, mock_data):
    """Test complete backup of all rule types."""
    mock_coordinator.data = mock_data
    hass.data[DOMAIN] = {
        "test_entry": {
            "coordinator": mock_coordinator
        }
    }

    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    # Mock config.path to return a fixed path
    hass.config.path = MagicMock(return_value="/test/path/test_backup.json")

    # Create a StringIO to capture the written data
    file_mock = mock_open()
    with patch("builtins.open", file_mock):
        await async_backup_rules_service(hass, mock_call)
        
        # Verify file was opened correctly
        file_mock.assert_called_once_with("/test/path/test_backup.json", 'w')
        
        # Get the write call arguments
        handle = file_mock()
        write_call_args = handle.write.call_args_list
        
        # Combine all written data (in case of multiple writes)
        written_data_str = "".join(call.args[0] for call in write_call_args)
        written_data = json.loads(written_data_str)
        
        # Verify the data structure
        assert "test_entry" in written_data
        assert written_data["test_entry"]["firewall_policies"] == mock_data["firewall_policies"]
        assert written_data["test_entry"]["traffic_routes"] == mock_data["traffic_routes"]
        assert written_data["test_entry"]["firewall_rules"] == mock_data["firewall_rules"]
        assert written_data["test_entry"]["traffic_rules"] == mock_data["traffic_rules"]

@pytest.mark.asyncio
async def test_backup_rules_service_no_data(hass: HomeAssistant, mock_coordinator):
    """Test backup service when no data is available."""
    mock_coordinator.data = None
    hass.data[DOMAIN] = {
        "test_entry": {
            "coordinator": mock_coordinator
        }
    }

    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    with patch("builtins.open", mock_open()) as mock_file:
        await async_backup_rules_service(hass, mock_call)
        mock_file.assert_not_called()

@pytest.mark.asyncio
async def test_restore_rules_service_file_not_found(hass: HomeAssistant):
    """Test restore service with missing backup file."""
    mock_call = MagicMock()
    mock_call.data = {"filename": "nonexistent.json"}

    with patch("os.path.exists", return_value=False):
        await async_restore_rules_service(hass, mock_call)

@pytest.mark.asyncio
async def test_restore_rules_service_full_success(hass: HomeAssistant, mock_api, mock_coordinator, mock_data):
    """Test successful restore of all rule types."""
    hass.data[DOMAIN] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    # Mock config.path
    hass.config.path = MagicMock(return_value="/test/path/test_backup.json")
    backup_data = {"test_entry": mock_data}
    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(backup_data))):
        await async_restore_rules_service(hass, mock_call)
        
        mock_api.update_firewall_policy.assert_called_once()
        mock_api.update_traffic_route.assert_called_once()
        mock_api.update_legacy_firewall_rule.assert_called_once()
        mock_api.update_legacy_traffic_rule.assert_called_once()
        mock_coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_restore_rules_service_skip_predefined(hass: HomeAssistant, mock_api, mock_coordinator):
    """Test that restore service skips predefined policies."""
    hass.data[DOMAIN] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    predefined_policy = {
        "_id": "1",
        "name": "Predefined Policy",
        "predefined": True,
        "enabled": True
    }

    backup_data = {
        "test_entry": {
            "firewall_policies": [predefined_policy]
        }
    }

    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(backup_data))):
        await async_restore_rules_service(hass, mock_call)
        
        # Verify predefined policy was not updated
        mock_api.update_firewall_policy.assert_not_called()
        mock_coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_restore_rules_service_capabilities_check(hass: HomeAssistant, mock_api, mock_coordinator, mock_data):
    """Test restore service respects UDM capabilities."""
    # Set all capabilities to False
    mock_api.capabilities.zone_based_firewall = False
    mock_api.capabilities.legacy_firewall = False
    mock_api.capabilities.traffic_routes = False
    
    hass.data[DOMAIN] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    backup_data = {"test_entry": mock_data}
    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(backup_data))):
        await async_restore_rules_service(hass, mock_call)

        # Verify no updates were attempted due to capabilities
        mock_api.update_firewall_policy.assert_not_called()
        mock_api.update_traffic_route.assert_not_called()
        mock_api.update_legacy_firewall_rule.assert_not_called()
        mock_api.update_legacy_traffic_rule.assert_not_called()
        mock_coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_restore_rules_service_mixed_errors(hass: HomeAssistant, mock_api, mock_coordinator, mock_data):
    """Test restore service continues despite some failures."""
    # Make some updates fail
    mock_api.update_firewall_policy = AsyncMock(return_value=(False, "API Error"))
    mock_api.update_traffic_route = AsyncMock(return_value=(True, None))
    mock_api.update_legacy_firewall_rule = AsyncMock(return_value=(False, "API Error"))
    mock_api.update_legacy_traffic_rule = AsyncMock(return_value=(True, None))
    
    hass.data[DOMAIN] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    backup_data = {"test_entry": mock_data}
    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(backup_data))):
        await async_restore_rules_service(hass, mock_call)

        # Verify all updates were attempted regardless of failures
        assert mock_api.update_firewall_policy.call_count == 1
        assert mock_api.update_traffic_route.call_count == 1
        assert mock_api.update_legacy_firewall_rule.call_count == 1
        assert mock_api.update_legacy_traffic_rule.call_count == 1
        # Verify coordinator was still refreshed
        mock_coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_backup_rules_service_invalid_path(hass: HomeAssistant, mock_coordinator):
    """Test backup service with invalid file path."""
    mock_coordinator.data = {"test_data": "value"}
    hass.data[DOMAIN] = {
        "test_entry": {
            "coordinator": mock_coordinator
        }
    }

    mock_call = MagicMock()
    mock_call.data = {"filename": "/invalid/path/test.json"}

    with patch("builtins.open") as mock_file:
        mock_file.side_effect = PermissionError("Permission denied")
        await async_backup_rules_service(hass, mock_call)
        # Service should handle the error gracefully

@pytest.mark.asyncio
async def test_restore_rules_service_invalid_json(hass: HomeAssistant, mock_api, mock_coordinator):
    """Test restore service with invalid JSON in backup file."""
    hass.data[DOMAIN] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data="invalid json content")):
        await async_restore_rules_service(hass, mock_call)
        # Service should handle the JSON parsing error gracefully
        mock_coordinator.async_request_refresh.assert_not_called()

@pytest.mark.asyncio
async def test_restore_rules_service_partial_failure(hass: HomeAssistant, mock_api, mock_coordinator, mock_data):
    """Test restore service with partial failures."""
    # Make some API calls fail
    mock_api.update_firewall_policy.side_effect = Exception("API Error")
    mock_api.update_traffic_route.return_value = (True, None)
    
    hass.data[DOMAIN] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    backup_data = {"test_entry": mock_data}
    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(backup_data))):
        await async_restore_rules_service(hass, mock_call)
        
        # Verify that successful updates still occurred
        mock_api.update_traffic_route.assert_called_once()
        # Verify coordinator was still refreshed despite partial failure
        mock_coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_restore_rules_service_missing_entry(hass: HomeAssistant, mock_api, mock_coordinator):
    """Test restore service with backup data for non-existent entry."""
    hass.data[DOMAIN] = {
        "existing_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    backup_data = {"non_existent_entry": {"some": "data"}}
    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(backup_data))):
        await async_restore_rules_service(hass, mock_call)
        
        # Verify no updates were attempted
        mock_api.update_firewall_policy.assert_not_called()
        mock_api.update_traffic_route.assert_not_called()
        mock_api.update_legacy_firewall_rule.assert_not_called()
        mock_api.update_legacy_traffic_rule.assert_not_called()

@pytest.mark.asyncio
async def test_refresh_service_coordinator_error(hass: HomeAssistant, mock_coordinator):
    """Test refresh service when coordinator update fails."""
    mock_coordinator.async_request_refresh.side_effect = Exception("Update failed")
    
    hass.data[DOMAIN] = {
        "test_entry": {"coordinator": mock_coordinator}
    }

    # The service should handle the error gracefully
    try:
        await async_refresh_service(hass, MagicMock())
    except Exception:
        pytest.fail("Service should handle coordinator errors gracefully")
    
    mock_coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_backup_rules_service_empty_data(hass: HomeAssistant, mock_coordinator):
    """Test backup service with empty data structures."""
    mock_coordinator.data = {
        "firewall_policies": [],
        "traffic_routes": [],
        "firewall_rules": [],  # Changed to match the list structure
        "traffic_rules": []
    }
    
    hass.data[DOMAIN] = {
        "test_entry": {
            "coordinator": mock_coordinator
        }
    }

    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}
    
    # Mock config.path
    hass.config.path = MagicMock(return_value="/test/path/test_backup.json")

    # Create a StringIO to capture the written data
    file_mock = mock_open()
    with patch("builtins.open", file_mock):
        await async_backup_rules_service(hass, mock_call)
        
        # Verify file was opened correctly
        file_mock.assert_called_once_with("/test/path/test_backup.json", 'w')
        
        # Get the write call arguments
        handle = file_mock()
        write_call_args = handle.write.call_args_list
        
        # Combine all written data (in case of multiple writes)
        written_data_str = "".join(call.args[0] for call in write_call_args)
        written_data = json.loads(written_data_str)
        
        # Verify empty data structure
        assert "test_entry" in written_data
        assert written_data["test_entry"]["firewall_rules"] == []
        assert written_data["test_entry"]["firewall_policies"] == []
        assert written_data["test_entry"]["traffic_routes"] == []
        assert written_data["test_entry"]["traffic_rules"] == []

@pytest.mark.asyncio
async def test_something():
    """Test with suppressed warnings."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        # Test code here