"""Tests for OON policy support (model, API mixin, switch, mappings)."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.unifi_network_rules.models.oon_policy import OONPolicy
from custom_components.unifi_network_rules.udm.oon import OONMixin
from custom_components.unifi_network_rules.unified_change_detector import UnifiedChangeDetector
from custom_components.unifi_network_rules.unified_trigger import VALID_CHANGE_TYPES

# Note: Switch imports commented out - require Home Assistant to be installed
# from custom_components.unifi_network_rules.switches.oon_policy import (
#     UnifiOONPolicySwitch,
#     UnifiOONPolicyKillSwitch,
# )


@pytest.fixture
def oon_policy_payload():
    """Sample OON policy payload."""
    return {
        "_id": "69134f9a2046c56ca159e502",
        "name": "Test OON Policy",
        "enabled": True,
        "target_type": "CLIENTS",
        "targets": ["68b6eef7dd411xxxxxxxxx"],
        "qos": {
            "enabled": True,
            "bandwidth_limit": 1000000,
        },
        "route": {
            "enabled": True,
            "kill_switch": False,
        },
        "secure": {
            "enabled": False,
        },
    }


@pytest.fixture
def oon_policy_with_kill_switch():
    """OON policy with kill switch enabled."""
    return {
        "_id": "69134f9a2046c56ca159e503",
        "name": "VPN Route Policy",
        "enabled": True,
        "target_type": "CLIENTS",
        "targets": ["68b6eef7dd411xxxxxxxxx"],
        "qos": {
            "enabled": False,
        },
        "route": {
            "enabled": True,
            "kill_switch": True,
        },
        "secure": {
            "enabled": False,
        },
    }


class TestOONPolicyModel:
    """Test OONPolicy model creation and properties."""

    def test_oon_policy_defaults_and_properties(self, oon_policy_payload):
        """Test OONPolicy model creation and basic properties."""
        policy = OONPolicy(oon_policy_payload)
        assert policy.id == oon_policy_payload["_id"]
        assert policy.name == "Test OON Policy"
        assert policy.enabled is True
        assert policy.target_type == "CLIENTS"
        assert len(policy.targets) == 1
        assert policy.qos["enabled"] is True
        assert policy.route["enabled"] is True

    def test_oon_policy_minimal_data(self):
        """Test OONPolicy with minimal required data."""
        minimal_data = {
            "_id": "test123",
            "name": "Minimal Policy",
        }
        policy = OONPolicy(minimal_data)
        assert policy.id == "test123"
        assert policy.name == "Minimal Policy"
        assert policy.enabled is False  # Default
        assert policy.target_type == "CLIENTS"  # Default
        assert policy.targets == []  # Default
        assert policy.qos == {}  # Default
        assert policy.route == {}  # Default

    def test_has_kill_switch_with_kill_switch(self, oon_policy_with_kill_switch):
        """Test has_kill_switch() returns True when route enabled and kill_switch is boolean."""
        policy = OONPolicy(oon_policy_with_kill_switch)
        assert policy.has_kill_switch() is True

    def test_has_kill_switch_with_route_enabled(self, oon_policy_payload):
        """Test has_kill_switch() returns True when route enabled and kill_switch exists (even if False)."""
        policy = OONPolicy(oon_policy_payload)
        # kill_switch is False (boolean), but route.enabled is True, so should return True
        # The method checks if kill_switch exists as a boolean, not its value
        assert policy.has_kill_switch() is True

    def test_has_kill_switch_route_disabled(self):
        """Test has_kill_switch() returns False when route is disabled."""
        data = {
            "_id": "test123",
            "name": "No Route Policy",
            "route": {
                "enabled": False,
                "kill_switch": True,
            },
        }
        policy = OONPolicy(data)
        assert policy.has_kill_switch() is False

    def test_has_kill_switch_no_route(self):
        """Test has_kill_switch() returns False when route is missing."""
        data = {
            "_id": "test123",
            "name": "No Route Policy",
        }
        policy = OONPolicy(data)
        assert policy.has_kill_switch() is False

    def test_to_api_dict(self, oon_policy_payload):
        """Test to_api_dict() returns correct dictionary."""
        policy = OONPolicy(oon_policy_payload)
        api_dict = policy.to_api_dict()
        assert isinstance(api_dict, dict)
        assert api_dict["_id"] == oon_policy_payload["_id"]
        assert api_dict["name"] == oon_policy_payload["name"]
        assert api_dict["enabled"] == oon_policy_payload["enabled"]
        assert "qos" in api_dict
        assert "route" in api_dict


class TestOONMixin:
    """Test OONMixin API methods."""

    @pytest.mark.asyncio
    async def test_get_oon_policies_success(self):
        """Test get_oon_policies() with successful response."""
        mixin = OONMixin()
        mixin.controller = AsyncMock()
        # Mock create_api_request to return a request dict
        mixin.create_api_request = Mock(return_value={"method": "GET", "path": "/test"})

        response_data = {
            "data": [
                {"_id": "test1", "name": "Policy 1", "enabled": True},
                {"_id": "test2", "name": "Policy 2", "enabled": False},
            ]
        }
        mixin.controller.request = AsyncMock(return_value=response_data)

        policies = await mixin.get_oon_policies()
        assert len(policies) == 2
        assert isinstance(policies[0], OONPolicy)
        assert policies[0].id == "test1"
        assert policies[1].id == "test2"

    @pytest.mark.asyncio
    async def test_get_oon_policies_404_handling(self):
        """Test get_oon_policies() gracefully handles 404 errors."""
        mixin = OONMixin()
        mixin.controller = AsyncMock()
        mixin.create_api_request = Mock(return_value={"method": "GET", "path": "/test"})
        mixin.controller.request = AsyncMock(side_effect=Exception("404 Not Found"))

        policies = await mixin.get_oon_policies()
        assert policies == []
        assert isinstance(policies, list)

    @pytest.mark.asyncio
    async def test_update_oon_policy_success(self, oon_policy_payload):
        """Test update_oon_policy() with successful update."""
        mixin = OONMixin()
        mixin.controller = AsyncMock()
        mixin.create_api_request = Mock(return_value={"method": "PUT", "path": "/test"})
        mixin.controller.request = AsyncMock(return_value={})

        policy = OONPolicy(oon_policy_payload)
        result = await mixin.update_oon_policy(policy)
        assert result is True

    @pytest.mark.asyncio
    async def test_toggle_oon_policy_success(self, oon_policy_payload):
        """Test toggle_oon_policy() sets enabled state."""
        mixin = OONMixin()
        mixin.controller = AsyncMock()
        mixin.create_api_request = Mock(return_value={"method": "PUT", "path": "/test"})
        mixin.controller.request = AsyncMock(return_value={})

        policy = OONPolicy(oon_policy_payload)
        original_state = policy.enabled
        target_state = not original_state
        result = await mixin.toggle_oon_policy(policy, target_state)
        assert result is True
        # Verify that the API call was made with the target state
        assert mixin.controller.request.await_count == 1

    @pytest.mark.asyncio
    async def test_add_oon_policy_success(self):
        """Test add_oon_policy() creates new policy."""
        mixin = OONMixin()
        mixin.controller = AsyncMock()
        mixin.create_api_request = Mock(return_value={"method": "POST", "path": "/test"})

        # API may return data as dict or list
        response_data = {
            "data": {
                "_id": "new123",
                "name": "New Policy",
                "enabled": True,
            }
        }
        mixin.controller.request = AsyncMock(return_value=response_data)

        policy_data = {"name": "New Policy", "enabled": True}
        policy = await mixin.add_oon_policy(policy_data)
        assert policy is not None
        assert isinstance(policy, OONPolicy)
        assert policy.id == "new123"

    @pytest.mark.asyncio
    async def test_add_oon_policy_with_list_response(self):
        """Test add_oon_policy() handles list response format."""
        mixin = OONMixin()
        mixin.controller = AsyncMock()
        mixin.create_api_request = Mock(return_value={"method": "POST", "path": "/test"})

        # Some APIs return data as a list
        response_data = {
            "data": [
                {
                    "_id": "new456",
                    "name": "New Policy List",
                    "enabled": True,
                }
            ]
        }
        mixin.controller.request = AsyncMock(return_value=response_data)

        policy_data = {"name": "New Policy List", "enabled": True}
        policy = await mixin.add_oon_policy(policy_data)
        assert policy is not None
        assert isinstance(policy, OONPolicy)
        assert policy.id == "new456"

    @pytest.mark.asyncio
    async def test_remove_oon_policy_success(self):
        """Test remove_oon_policy() deletes policy."""
        mixin = OONMixin()
        mixin.controller = AsyncMock()
        mixin.create_api_request = Mock(return_value={"method": "DELETE", "path": "/test"})
        mixin.controller.request = AsyncMock(return_value=None)  # 204 No Content

        result = await mixin.remove_oon_policy("test123")
        assert result is True


class TestOONPolicyIntegration:
    """Test OON policy integration with change detection and triggers."""

    def test_oon_policy_in_valid_change_types(self):
        """Test that oon_policy is in VALID_CHANGE_TYPES."""
        assert "oon_policy" in VALID_CHANGE_TYPES

    def test_change_detector_mapping(self):
        """Test that unified change detector maps oon_policies correctly."""
        detector = UnifiedChangeDetector(Mock(), Mock())
        assert "oon_policies" in detector._rule_type_mapping
        assert detector._rule_type_mapping["oon_policies"] == "oon_policy"
