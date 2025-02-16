"""Test services module."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
import json
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from custom_components.unifi_network_rules.switch import UDMPortForwardRuleSwitch
from custom_components.unifi_network_rules.udm_api import UDMAPI

from custom_components.unifi_network_rules.services import (
    async_refresh_service,
    async_backup_rules_service,
    async_restore_rules_service,
    async_bulk_update_rules_service,
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
    api.delete_firewall_policies = AsyncMock(return_value=(True, None))
    api.update_legacy_firewall_rule = AsyncMock(return_value=(True, None))
    api.update_legacy_traffic_rule = AsyncMock(return_value=(True, None))
    api.get_legacy_firewall_rules = AsyncMock(return_value=(True, [], None))
    api.get_legacy_traffic_rules = AsyncMock(return_value=(True, [], None))
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
        "firewall_rules": [
            {
                "_id": "rule1",
                "name": "Rule 1",
                "enabled": True
            }
        ],
        "traffic_rules": [
            {
                "_id": "traffic1",
                "name": "Traffic 1",
                "enabled": True
            }
        ],
        "port_forward_rules": [
            {
                "_id": "port1",
                "name": "Minecraft",
                "enabled": False
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
async def test_backup_rules_service_full(hass: HomeAssistant, mock_coordinator, mock_data):
    """Test backup service with full data."""
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
async def test_backup_rules_service_empty_data(hass: HomeAssistant, mock_coordinator):
    """Test backup service with no data."""
    mock_coordinator.data = {}
    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "coordinator": mock_coordinator
        }
    }

    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    result = await async_backup_rules_service(hass, mock_call)
    assert result is None

@pytest.mark.asyncio
async def test_restore_rules_service_success(hass: HomeAssistant, mock_api, mock_coordinator, mock_data):
    """Test successful restore operation."""
    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    backup_data = {"test_entry": mock_data}
    mock_call = MagicMock()
    mock_call.data = {
        "filename": "test_backup.json",
        "name_filter": "Policy"
    }

    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(backup_data))):
        await async_restore_rules_service(hass, mock_call)
        mock_api.update_firewall_policy.assert_called_once()
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
                "enabled": True
            }
        ],
        "traffic_routes": [
            {
                "_id": "route1",
                "name": "Route 1",
                "enabled": True
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
        "name_filter": "Policy",
        "state": False
    }

    await async_bulk_update_rules_service(hass, mock_call)

    mock_api.update_firewall_policy.assert_called_once()
    mock_api.update_traffic_route.assert_not_called()
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
async def test_restore_rules_service_file_not_found(hass: HomeAssistant, mock_api, mock_coordinator):
    """Test restore service when backup file doesn't exist."""
    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    mock_call = MagicMock()
    mock_call.data = {"filename": "nonexistent.json"}

    with patch("os.path.exists", return_value=False):
        await async_restore_rules_service(hass, mock_call)
        mock_api.update_firewall_policy.assert_not_called()
        mock_api.update_traffic_route.assert_not_called()
        mock_coordinator.async_request_refresh.assert_not_called()

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

@pytest.mark.asyncio
async def test_port_forward_rule_switch_initialization():
    """Test port forward rule switch initialization."""
    coordinator = MagicMock()
    api = MagicMock()
    rule = {
        "pfwd_interface": "wan",
        "src": "any",
        "log": True,
        "enabled": False,
        "fwd": "10.29.13.235",
        "proto": "tcp_udp",
        "name": "Minecraft",
        "dst_port": "25565",
        "_id": "test123",
        "fwd_port": "25565"
    }

    switch = UDMPortForwardRuleSwitch(coordinator, api, rule)
    assert switch.name == "Port Forward: Minecraft (10.29.13.235) (t123)"
    assert switch.unique_id == "pf_minecraft_t123"
    assert switch.is_on is False

@pytest.mark.asyncio
async def test_port_forward_rule_switch_different_ports():
    """Test port forward rule switch name with different source and destination ports."""
    coordinator = MagicMock()
    api = MagicMock()
    rule = {
        "pfwd_interface": "wan",
        "src": "any",
        "log": True,
        "enabled": False,
        "fwd": "10.29.13.235",
        "proto": "tcp",
        "name": "Web",
        "dst_port": "80",
        "_id": "test456",
        "fwd_port": "8080"
    }

    switch = UDMPortForwardRuleSwitch(coordinator, api, rule)
    assert switch.name == "Port Forward: Web (10.29.13.235) (t456)"
    assert switch.unique_id == "pf_web_t456"

@pytest.mark.asyncio
async def test_port_forward_rule_switch_toggle_on():
    """Test turning on a port forward rule switch."""
    coordinator = MagicMock()
    api = MagicMock()
    api.toggle_port_forward_rule = AsyncMock(return_value=(True, None))
    api.get_port_forward_rules = AsyncMock(return_value=(True, [{"_id": "test123", "enabled": True}], None))
    coordinator.async_request_refresh = AsyncMock()

    rule = {
        "pfwd_interface": "wan",
        "src": "any",
        "enabled": False,
        "fwd": "10.29.13.235",
        "proto": "tcp",
        "name": "Test",
        "_id": "test123",
        "dst_port": "80",
        "fwd_port": "80"
    }

    switch = UDMPortForwardRuleSwitch(coordinator, api, rule)
    await switch.async_turn_on()
    
    api.toggle_port_forward_rule.assert_called_once_with("test123", True)
    api.get_port_forward_rules.assert_called()
    coordinator.async_request_refresh.assert_called_once()

@pytest.mark.asyncio
async def test_port_forward_rule_switch_toggle_failure():
    """Test handling of toggle failure for port forward rule switch."""
    coordinator = MagicMock()
    api = MagicMock()
    api.toggle_port_forward_rule = AsyncMock(return_value=(False, "API Error"))

    rule = {
        "pfwd_interface": "wan",
        "src": "any",
        "enabled": False,
        "fwd": "10.29.13.235",
        "proto": "tcp",
        "name": "Test",
        "_id": "test123",
        "dst_port": "80",
        "fwd_port": "80"
    }

    switch = UDMPortForwardRuleSwitch(coordinator, api, rule)
    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()

@pytest.mark.asyncio
async def test_port_forward_rule_switch_coordinator_update():
    """Test coordinator update handling for port forward rule switch."""
    coordinator = MagicMock()
    api = MagicMock()
    rule_id = "test123"
    
    rule = {
        "pfwd_interface": "wan",
        "src": "any",
        "enabled": False,
        "fwd": "10.29.13.235",
        "proto": "tcp",
        "name": "Test",
        "_id": rule_id,
        "dst_port": "80",
        "fwd_port": "80"
    }

    switch = UDMPortForwardRuleSwitch(coordinator, api, rule)
    
    # Test update with new data
    coordinator.data = {
        "port_forward_rules": [
            {**rule, "enabled": True}
        ]
    }
    switch._handle_coordinator_update()
    assert switch.is_on is True

    # Test update with missing rule
    coordinator.data = {"port_forward_rules": []}
    switch._handle_coordinator_update()
    assert switch.available is False

    # Test update with no data
    coordinator.data = None
    switch._handle_coordinator_update()
    assert switch.available is False

@pytest.mark.asyncio
async def test_backup_restore_port_forward_rules(hass: HomeAssistant, mock_api, mock_coordinator, mock_data):
    """Test backup and restore of port forward rules."""
    mock_coordinator.data = mock_data
    hass.data["unifi_network_rules"] = {
        "test_entry": {
            "api": mock_api,
            "coordinator": mock_coordinator
        }
    }

    # Test backup
    mock_call = MagicMock()
    mock_call.data = {"filename": "test_backup.json"}

    with patch("builtins.open", mock_open()) as mock_file:
        backup_data = await async_backup_rules_service(hass, mock_call)
        assert "port_forward_rules" in backup_data["test_entry"]
        assert len(backup_data["test_entry"]["port_forward_rules"]) == 1
        assert backup_data["test_entry"]["port_forward_rules"][0]["name"] == "Minecraft"

    # Test restore
    mock_call.data.update({
        "rule_types": ["port_forward"],
        "name_filter": "Minecraft"
    })

    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps({"test_entry": mock_data}))):
        await async_restore_rules_service(hass, mock_call)
        mock_api.update_port_forward_rule.assert_called_once()
        assert mock_api.update_port_forward_rule.call_args[0][1]["name"] == "Minecraft"