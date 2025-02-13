"""Test services module."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
import json
from homeassistant.core import HomeAssistant

from custom_components.unifi_network_rules.services import (
    async_refresh_service,
    async_backup_rules_service,
    async_restore_rules_service,
    async_bulk_update_rules_service,
    async_create_from_template_service,
    async_delete_rule_service
)

@pytest.fixture
def mock_api():
    """Create a mock API instance."""
    api = MagicMock()
    api.capabilities.zone_based_firewall = True
    api.capabilities.traffic_routes = True
    api.get_firewall_policies = AsyncMock(return_value=(True, [], None))
    api.get_traffic_routes = AsyncMock(return_value=(True, [], None))
    api.update_firewall_policy = AsyncMock(return_value=(True, None))
    api.update_traffic_route = AsyncMock(return_value=(True, None))
    api.create_firewall_policy = AsyncMock(return_value=(True, None))
    api.delete_firewall_policies = AsyncMock(return_value=(True, None))
    return api

@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator instance."""
    coordinator = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
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
                "tags": ["test"],
                "predefined": False
            }
        ],
        "traffic_routes": [
            {
                "_id": "route1",
                "description": "Route 1",
                "enabled": True,
                "tags": ["test"]
            }
        ]
    }

@pytest.mark.asyncio
async def test_refresh_service(hass: HomeAssistant, mock_coordinator):
    """Test refresh service."""
    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "coordinator": mock_coordinator
        }
    }

    await async_refresh_service(hass, MagicMock())
    mock_coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_refresh_service_no_coordinator(hass: HomeAssistant):
    """Test refresh service with no coordinator."""
    hass.data["unifi_network_rules"] = {
        "test_entry": {}
    }

    await async_refresh_service(hass, MagicMock())
    # Should not raise an error

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

    with patch("builtins.open", mock_open()) as mock_file:
        result = await async_backup_rules_service(hass, mock_call)
        mock_file.assert_called_once_with(hass.config.path("test_backup.json"), 'w', encoding='utf-8')
        assert result == {"test_entry": mock_data}
        handle = mock_file()
        written_data = handle.write.call_args[0][0]
        assert isinstance(written_data, str)
        assert json.loads(written_data) == {"test_entry": mock_data}

@pytest.mark.asyncio
async def test_restore_rules_service_capabilities_check(hass: HomeAssistant, mock_api, mock_coordinator, mock_data):
    """Test restore service respects UDM capabilities."""
    # Set capabilities
    mock_api.capabilities.zone_based_firewall = False
    mock_api.capabilities.traffic_routes = False
    
    hass.data["unifi_network_rules"] = {
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
        mock_coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_bulk_update_rules_service(hass: HomeAssistant, mock_api, mock_coordinator):
    """Test bulk update service."""
    mock_coordinator.data = {
        "firewall_policies": [
            {
                "_id": "policy1",
                "name": "Policy 1",
                "enabled": True,
                "tags": ["test"]
            }
        ],
        "traffic_routes": [
            {
                "_id": "route1",
                "description": "Route 1",
                "enabled": True,
                "tags": ["test"]
            }
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
        "tags": ["test"],
        "state": False
    }

    await async_bulk_update_rules_service(hass, mock_call)

    mock_api.update_firewall_policy.assert_called_once()
    mock_api.update_traffic_route.assert_called_once()
    mock_coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_create_from_template_service(hass: HomeAssistant, mock_api, mock_coordinator):
    """Test create from template service."""
    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    template_data = {
        "name": "Test Policy",
        "enabled": True,
        "action": "BLOCK",
        "source": {
            "zone_id": "test_zone_1"
        },
        "destination": {
            "zone_id": "test_zone_2"
        }
    }

    mock_call = MagicMock()
    mock_call.data = {
        "template": template_data,
        "rule_type": "policy"
    }

    await async_create_from_template_service(hass, mock_call)

    mock_api.create_firewall_policy.assert_called_once_with(template_data)
    mock_coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_delete_rule_service(hass: HomeAssistant, mock_api, mock_coordinator):
    """Test delete rule service."""
    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    mock_call = MagicMock()
    mock_call.data = {
        "rule_id": "test_policy_id",
        "rule_type": "policy"
    }

    await async_delete_rule_service(hass, mock_call)

    mock_api.delete_firewall_policies.assert_called_once_with(["test_policy_id"])
    mock_coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_restore_rules_service_mixed_errors(hass: HomeAssistant, mock_api, mock_coordinator, mock_data):
    """Test restore service continues despite some failures."""
    mock_api.update_firewall_policy.side_effect = [(False, "Error updating policy"), (True, None)]
    mock_api.update_traffic_route.side_effect = [(False, "Error updating route"), (True, None)]

    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    mock_data["firewall_policies"].append(mock_data["firewall_policies"][0].copy())
    mock_data["traffic_routes"].append(mock_data["traffic_routes"][0].copy())

    backup_data = {"test_entry": mock_data}
    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(backup_data))):
        await async_restore_rules_service(hass, mock_call)

        assert mock_api.update_firewall_policy.call_count == 2
        assert mock_api.update_traffic_route.call_count == 2
        mock_coordinator.async_request_refresh.assert_called_once()