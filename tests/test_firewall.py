"""Tests for the UniFi Network Rules Firewall API functionality."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.unifi_network_rules.models.firewall_rule import FirewallRule
from custom_components.unifi_network_rules.udm.api import UDMAPI


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
    return api


@pytest.fixture
def firewall_policy_data():
    """Return example firewall policy data."""
    return {
        "id": "123456789",
        "_id": "123456789",
        "name": "Test Policy",
        "description": "Test firewall policy",
        "enabled": True,
        "action": "accept",
        "protocol": "all",
        "ruleset": "WAN_IN",
        "dst_address": "10.0.0.0/8",
        "src_address": "any",
        "position": 2000,
        "predefined": False,
    }


@pytest.fixture
def firewall_rule_data():
    """Return example legacy firewall rule data."""
    return {
        "id": "987654321",
        "_id": "987654321",
        "name": "Legacy Rule",
        "description": "Test legacy rule",
        "enabled": True,
        "action": "accept",
        "protocol": "tcp",
        "protocol_match_excepted": False,
        "dst_address": "192.168.1.0/24",
        "src_address": "any",
        "rule_index": 2000,
        "src_firewall_group_ids": [],
        "dst_firewall_group_ids": [],
    }


@pytest.mark.asyncio
async def test_get_firewall_policies(api, firewall_policy_data):
    """Test retrieving firewall policies."""
    # Mock the controller request method
    api.controller.request = AsyncMock(return_value={"data": [firewall_policy_data]})

    # Call the method
    policies = await api.get_firewall_policies()

    # Verify controller request was called
    assert api.controller.request.called

    # Verify the policies are returned correctly
    assert len(policies) == 1
    policy = policies[0]
    assert policy.id == "123456789"
    assert policy.name == "Test Policy"
    assert policy.enabled is True


@pytest.mark.asyncio
async def test_get_firewall_policies_excludes_predefined(api):
    """Test that predefined policies are excluded by default."""
    # Sample data with both predefined and custom policies
    policies_data = [
        {"_id": "123", "name": "Custom Policy", "predefined": False, "enabled": True},
        {"_id": "456", "name": "Predefined Policy", "predefined": True, "enabled": True},
    ]

    # Mock the controller request method
    api.controller.request = AsyncMock(return_value={"data": policies_data})

    # Call the method with default parameters (exclude predefined)
    policies = await api.get_firewall_policies()

    # Verify only custom policies are returned
    assert len(policies) == 1
    assert policies[0].name == "Custom Policy"

    # Now include predefined policies
    policies = await api.get_firewall_policies(include_predefined=True)

    # Verify both types are returned
    assert len(policies) == 2
    policy_names = [p.name for p in policies]
    assert "Custom Policy" in policy_names
    assert "Predefined Policy" in policy_names


@pytest.mark.asyncio
async def test_add_firewall_policy(api, firewall_policy_data):
    """Test adding a firewall policy."""
    # Mock the controller request method
    api.controller.request = AsyncMock(return_value={"data": [firewall_policy_data]})

    # Mock create_api_request
    api.create_api_request = Mock(return_value="mock_request")

    # Call the method
    policy = await api.add_firewall_policy(firewall_policy_data)

    # Verify create_api_request was called correctly
    api.create_api_request.assert_called_once()
    args = api.create_api_request.call_args[0]
    assert args[0] == "POST"  # Method is first arg
    assert "is_v2" in api.create_api_request.call_args[1]
    assert api.create_api_request.call_args[1]["is_v2"] is True

    # Verify controller request was called
    api.controller.request.assert_called_once_with("mock_request")

    # Verify the policy is returned correctly
    assert policy.id == "123456789"
    assert policy.name == "Test Policy"
    assert policy.enabled is True


@pytest.mark.asyncio
async def test_update_firewall_policy(api, firewall_policy_data):
    """Test updating a firewall policy."""
    # Create a firewall policy object
    from aiounifi.models.firewall_policy import FirewallPolicy

    policy = FirewallPolicy(firewall_policy_data)

    # Mock the controller request method
    api.controller.request = AsyncMock(return_value={"data": [firewall_policy_data]})

    # Call the method
    result = await api.update_firewall_policy(policy)

    # Verify controller request was called
    assert api.controller.request.called

    # Verify the result is True
    assert result is True


@pytest.mark.asyncio
async def test_remove_firewall_policy(api):
    """Test removing a firewall policy."""
    # Mock the create_api_request method
    api.create_api_request = Mock(return_value="mock_request")

    # Mock the controller request method
    api.controller.request = AsyncMock(return_value={"meta": {"rc": "ok"}})

    # Call the method
    result = await api.remove_firewall_policy("123456789")

    # Verify create_api_request was called correctly
    api.create_api_request.assert_called_once()
    args = api.create_api_request.call_args[0]
    assert args[0] == "POST"  # Method is first arg
    assert "is_v2" in api.create_api_request.call_args[1]
    assert api.create_api_request.call_args[1]["is_v2"] is True

    # Verify controller request was called
    api.controller.request.assert_called_once_with("mock_request")

    # Verify the result is True
    assert result is True


@pytest.mark.asyncio
async def test_toggle_firewall_policy(api, firewall_policy_data):
    """Test toggling a firewall policy."""
    # Create a firewall policy object
    from aiounifi.models.firewall_policy import FirewallPolicy

    policy = FirewallPolicy(firewall_policy_data)
    original_state = policy.enabled
    target_state = not original_state

    # Mock the controller request method
    api.controller.request = AsyncMock(return_value={"meta": {"rc": "ok"}})

    # Call the method with explicit target state
    result = await api.toggle_firewall_policy(policy, target_state)

    # Verify controller request was called
    assert api.controller.request.called

    # Get the request that was passed to controller.request
    request = api.controller.request.call_args[0][0]

    # Verify the request has the target enabled value
    assert hasattr(request, "data")
    assert request.data["enabled"] is target_state

    # Verify the result is True
    assert result is True


@pytest.mark.asyncio
async def test_get_legacy_firewall_rules(api, firewall_rule_data):
    """Test retrieving legacy firewall rules."""
    # Mock the controller request method
    api.controller.request = AsyncMock(return_value={"data": [firewall_rule_data]})

    # Mock the create_api_request method
    api.create_api_request = Mock(return_value="mock_request")

    # Call the method
    rules = await api.get_legacy_firewall_rules()

    # Verify create_api_request was called correctly
    api.create_api_request.assert_called_once()

    # Verify controller request was called
    api.controller.request.assert_called_once_with("mock_request")

    # Verify the rules are returned correctly
    assert len(rules) == 1
    rule = rules[0]
    assert isinstance(rule, FirewallRule)
    assert rule.id == "987654321"
    assert rule.name == "Legacy Rule"
    assert rule.enabled is True


@pytest.mark.asyncio
async def test_add_legacy_firewall_rule(api, firewall_rule_data):
    """Test adding a legacy firewall rule."""
    # Mock the controller request method
    api.controller.request = AsyncMock(return_value=firewall_rule_data)

    # Mock create_api_request
    api.create_api_request = Mock(return_value="mock_request")

    # Call the method
    rule = await api.add_legacy_firewall_rule(firewall_rule_data)

    # Verify create_api_request was called correctly
    api.create_api_request.assert_called_once()

    # Verify controller request was called
    api.controller.request.assert_called_once_with("mock_request")

    # Verify the rule is returned correctly
    assert isinstance(rule, FirewallRule)
    assert rule.id == "987654321"
    assert rule.name == "Legacy Rule"
    assert rule.enabled is True
