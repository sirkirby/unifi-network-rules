"""Tests for the UniFi Network Rules Unified Change Detector."""
import pytest
import sys
import os
from unittest.mock import Mock, AsyncMock, patch

# Add the custom_components path to sys.path for imports
test_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(test_dir)
custom_components_path = os.path.join(project_root, 'custom_components')
if custom_components_path not in sys.path:
    sys.path.insert(0, custom_components_path)

# Import with full package path to maintain relative import context
import unifi_network_rules.unified_change_detector

# Get the class we need
UnifiedChangeDetector = unifi_network_rules.unified_change_detector.UnifiedChangeDetector


@pytest.fixture
def mock_coordinator():
    """Return a mocked coordinator."""
    coordinator = Mock()
    coordinator._initial_update_done = True
    coordinator.hass = Mock()
    return coordinator


@pytest.fixture
def change_detector(mock_coordinator):
    """Return a UnifiedChangeDetector instance with mocked coordinator."""
    # Mock HomeAssistant instance
    mock_hass = Mock()
    mock_hass.data = {}
    mock_hass.states = Mock()
    mock_hass.bus = Mock()
    
    return UnifiedChangeDetector(mock_hass, mock_coordinator)


class TestLEDChangeDetection:
    """Test LED change detection logic."""

    def test_led_on_to_off_returns_disabled(self, change_detector):
        """Test LED change from on to off returns disabled."""
        old_state = {"led_override": "on"}
        new_state = {"led_override": "off"}
        
        result = change_detector._determine_led_change_action(old_state, new_state)
        assert result == "disabled"

    def test_led_off_to_on_returns_enabled(self, change_detector):
        """Test LED change from off to on returns enabled."""
        old_state = {"led_override": "off"}
        new_state = {"led_override": "on"}
        
        result = change_detector._determine_led_change_action(old_state, new_state)
        assert result == "enabled"

    def test_led_to_default_returns_modified(self, change_detector):
        """Test LED change to default returns modified."""
        old_state = {"led_override": "on"}
        new_state = {"led_override": "default"}
        
        result = change_detector._determine_led_change_action(old_state, new_state)
        assert result == "modified"

    def test_led_no_change_returns_none(self, change_detector):
        """Test LED with no change returns None."""
        old_state = {"led_override": "on"}
        new_state = {"led_override": "on"}
        
        result = change_detector._determine_led_change_action(old_state, new_state)
        assert result is None

    def test_led_both_none_returns_none(self, change_detector):
        """Test LED with both states None returns None."""
        old_state = {"led_override": None}
        new_state = {"led_override": None}
        
        result = change_detector._determine_led_change_action(old_state, new_state)
        assert result is None

    def test_led_missing_field_returns_none(self, change_detector):
        """Test LED with missing field returns None."""
        old_state = {}
        new_state = {}
        
        result = change_detector._determine_led_change_action(old_state, new_state)
        assert result is None


class TestKillSwitchChangeDetection:
    """Test kill switch change detection logic."""

    def test_kill_switch_enabled_returns_enabled(self, change_detector):
        """Test kill switch enabling returns enabled."""
        old_state = {"kill_switch_enabled": False}
        new_state = {"kill_switch_enabled": True}
        
        result = change_detector._determine_kill_switch_change_action(old_state, new_state)
        assert result == "enabled"

    def test_kill_switch_disabled_returns_disabled(self, change_detector):
        """Test kill switch disabling returns disabled."""
        old_state = {"kill_switch_enabled": True}
        new_state = {"kill_switch_enabled": False}
        
        result = change_detector._determine_kill_switch_change_action(old_state, new_state)
        assert result == "disabled"

    def test_kill_switch_no_change_returns_none(self, change_detector):
        """Test kill switch with no change returns None."""
        old_state = {"kill_switch_enabled": True}
        new_state = {"kill_switch_enabled": True}
        
        result = change_detector._determine_kill_switch_change_action(old_state, new_state)
        assert result is None

    def test_kill_switch_both_none_returns_none(self, change_detector):
        """Test kill switch with both states None returns None."""
        old_state = {"kill_switch_enabled": None}
        new_state = {"kill_switch_enabled": None}
        
        result = change_detector._determine_kill_switch_change_action(old_state, new_state)
        assert result is None

    def test_kill_switch_missing_field_returns_none(self, change_detector):
        """Test kill switch with missing field returns None."""
        old_state = {}
        new_state = {}
        
        result = change_detector._determine_kill_switch_change_action(old_state, new_state)
        assert result is None


class TestChangeActionDetermination:
    """Test overall change action determination logic."""

    def test_enabled_change_takes_priority(self, change_detector):
        """Test that enabled field changes take priority over other changes."""
        old_state = {"enabled": False, "name": "Old Name"}
        new_state = {"enabled": True, "name": "New Name"}
        
        result = change_detector._determine_change_action(old_state, new_state)
        assert result == "enabled"

    def test_disabled_change_takes_priority(self, change_detector):
        """Test that disabled field changes take priority over other changes."""
        old_state = {"enabled": True, "description": "Old Description"}
        new_state = {"enabled": False, "description": "New Description"}
        
        result = change_detector._determine_change_action(old_state, new_state)
        assert result == "disabled"

    def test_led_change_detected_for_device_entities(self, change_detector):
        """Test LED changes are detected for device entities."""
        old_state = {"led_override": "off", "enabled": True}
        new_state = {"led_override": "on", "enabled": True}
        
        result = change_detector._determine_change_action(old_state, new_state)
        assert result == "enabled"

    def test_kill_switch_change_detected_for_child_entities(self, change_detector):
        """Test kill switch changes are detected for kill switch child entities."""
        old_state = {"_id": "route_123_kill_switch", "kill_switch_enabled": False}
        new_state = {"_id": "route_123_kill_switch", "kill_switch_enabled": True}
        
        result = change_detector._determine_change_action(old_state, new_state)
        assert result == "enabled"

    def test_kill_switch_change_ignored_for_parent_entities(self, change_detector):
        """Test kill switch changes are ignored for parent entities."""
        old_state = {"_id": "route_123", "enabled": True, "kill_switch_enabled": False}
        new_state = {"_id": "route_123", "enabled": True, "kill_switch_enabled": True}
        
        result = change_detector._determine_change_action(old_state, new_state)
        assert result is None

    def test_significant_field_change_returns_modified(self, change_detector):
        """Test significant field changes return modified."""
        old_state = {"enabled": True, "name": "Old Name"}
        new_state = {"enabled": True, "name": "New Name"}
        
        result = change_detector._determine_change_action(old_state, new_state)
        assert result == "modified"

    def test_insignificant_field_change_returns_none(self, change_detector):
        """Test insignificant field changes return None."""
        old_state = {"enabled": True, "internal_field": "old_value"}
        new_state = {"enabled": True, "internal_field": "new_value"}
        
        result = change_detector._determine_change_action(old_state, new_state)
        assert result is None

    def test_no_changes_returns_none(self, change_detector):
        """Test no changes returns None."""
        state = {"enabled": True, "name": "Test Name"}
        
        result = change_detector._determine_change_action(state, state)
        assert result is None


class TestEntityNaming:
    """Test entity naming logic."""

    def test_entity_name_from_name_field(self, change_detector):
        """Test entity name extraction from name field."""
        state = {"name": "Test Entity"}
        
        result = change_detector._get_entity_name("firewall_policies", None, state, "rule_123")
        assert result == "Test Entity"

    def test_entity_name_from_description_field(self, change_detector):
        """Test entity name extraction from description field."""
        state = {"description": "Test Description"}
        
        result = change_detector._get_entity_name("firewall_policies", None, state, "rule_123")
        assert result == "Test Description"

    def test_firewall_policy_specific_naming(self, change_detector):
        """Test firewall policy specific naming."""
        state = {"action": "accept"}
        
        result = change_detector._get_entity_name("firewall_policies", None, state, "rule_123")
        assert result == "Firewall ACCEPT Rule rule_123"

    def test_port_forward_specific_naming(self, change_detector):
        """Test port forward specific naming."""
        state = {"dst_port": "80", "fwd_port": "8080"}
        
        result = change_detector._get_entity_name("port_forwards", None, state, "rule_123")
        assert result == "Port Forward 80 → 8080"

    def test_wlan_specific_naming(self, change_detector):
        """Test WLAN specific naming."""
        state = {"ssid": "MyNetwork"}
        
        result = change_detector._get_entity_name("wlans", None, state, "rule_123")
        assert result == "WLAN: MyNetwork"

    def test_device_specific_naming(self, change_detector):
        """Test device specific naming."""
        state = {"name": "My Device"}
        
        result = change_detector._get_entity_name("devices", None, state, "device_123")
        assert result == "My Device"  # Implementation returns name directly

    def test_traffic_route_parent_naming(self, change_detector):
        """Test traffic route parent naming."""
        state = {"name": "Games Route"}
        
        result = change_detector._get_entity_name("traffic_routes", None, state, "route_123")
        assert result == "Games Route"  # Implementation returns name directly

    def test_traffic_route_kill_switch_naming(self, change_detector):
        """Test traffic route kill switch naming."""
        state = {"name": "Games Route Kill Switch"}
        
        result = change_detector._get_entity_name("traffic_routes", None, state, "route_123_kill_switch")
        assert result == "Games Route Kill Switch"

    def test_generic_fallback_naming(self, change_detector):
        """Test generic fallback naming."""
        state = {}
        
        result = change_detector._get_entity_name("unknown_type", None, state, "rule_123456789")
        assert result == "Unknown unknown_type rule_123"  # Implementation uses entity_type directly

    def test_name_preference_over_old_state(self, change_detector):
        """Test that new state is preferred over old state for naming."""
        old_state = {"name": "Old Name"}
        new_state = {"name": "New Name"}
        
        result = change_detector._get_entity_name("firewall_policies", old_state, new_state, "rule_123")
        assert result == "New Name"

    def test_fallback_to_old_state_when_new_state_none(self, change_detector):
        """Test fallback to old state when new state is None."""
        old_state = {"name": "Old Name"}
        
        result = change_detector._get_entity_name("firewall_policies", old_state, None, "rule_123")
        assert result == "Old Name"


class TestStateSnapshotBuilding:
    """Test state snapshot building logic."""

    def test_traffic_route_with_kill_switch_creates_child_entity(self, change_detector):
        """Test that traffic routes with kill switches create child entities in snapshot."""
        with patch('unifi_network_rules.helpers.rule.get_child_unique_id') as mock_get_child_id:
            mock_get_child_id.return_value = "route_123_kill_switch"
            
            # Mock entity with kill switch - set up both raw and direct property access
            mock_entity = Mock()
            mock_entity.raw = {
                "_id": "route_123",
                "name": "Games Route",
                "enabled": True,
                "kill_switch_enabled": True
            }
            # Also set up direct property access for state snapshot building
            mock_entity.enabled = True
            mock_entity.kill_switch_enabled = True
            
            data = {
                "traffic_routes": [mock_entity]
            }
            
            snapshot = change_detector._build_state_snapshot(data)
            
            # Check parent entity exists
            assert "route_123" in snapshot["traffic_routes"]
            parent_data = snapshot["traffic_routes"]["route_123"]
            assert parent_data["_id"] == "route_123"
            assert parent_data["name"] == "Games Route"
            assert parent_data["enabled"] is True
            assert parent_data["kill_switch_enabled"] is True
            
            # Check kill switch child entity exists
            assert "route_123_kill_switch" in snapshot["traffic_routes"]
            kill_switch_data = snapshot["traffic_routes"]["route_123_kill_switch"]
            assert kill_switch_data["_id"] == "route_123_kill_switch"
            assert kill_switch_data["parent_id"] == "route_123"
            assert kill_switch_data["enabled"] is True  # Should match kill_switch_enabled
            assert kill_switch_data["kill_switch_enabled"] is True
            assert kill_switch_data["name"] == "Games Route Kill Switch"

    def test_device_entity_attributes_captured(self, change_detector):
        """Test that device entities have proper attributes captured."""
        # Mock device entity
        mock_device = Mock()
        mock_device.id = "device_123"
        mock_device.name = "My Device"
        mock_device.model = "U6-Pro"
        mock_device.led_override = "on"
        
        # Mock that the entity doesn't have .raw attribute (direct attribute access)
        mock_device.configure_mock(spec=['id', 'name', 'model', 'led_override'])
        
        data = {
            "devices": [mock_device]
        }
        
        snapshot = change_detector._build_state_snapshot(data)
        
        assert "device_123" in snapshot["devices"]
        device_data = snapshot["devices"]["device_123"]
        assert device_data["id"] == "device_123"
        assert device_data["name"] == "My Device"
        assert device_data["model"] == "U6-Pro"
        assert device_data["led_override"] == "on"

    def test_typed_object_with_computed_properties(self, change_detector):
        """Test that typed objects with computed properties are handled correctly."""
        # Mock typed object (like PortProfile)
        mock_entity = Mock()
        mock_entity.raw = {
            "_id": "profile_123",
            "name": "Test Profile"
        }
        mock_entity.enabled = True  # Computed property
        
        data = {
            "port_profiles": [mock_entity]
        }
        
        snapshot = change_detector._build_state_snapshot(data)
        
        assert "profile_123" in snapshot["port_profiles"]
        profile_data = snapshot["port_profiles"]["profile_123"]
        assert profile_data["_id"] == "profile_123"
        assert profile_data["name"] == "Test Profile"
        assert profile_data["enabled"] is True  # Should capture computed property

    def test_raw_dictionary_entities(self, change_detector):
        """Test that raw dictionary entities are handled correctly."""
        data = {
            "firewall_policies": [
                {
                    "_id": "rule_123",
                    "name": "Test Rule",
                    "enabled": True,
                    "action": "accept"
                }
            ]
        }
        
        snapshot = change_detector._build_state_snapshot(data)
        
        assert "rule_123" in snapshot["firewall_policies"]
        rule_data = snapshot["firewall_policies"]["rule_123"]
        assert rule_data["_id"] == "rule_123"
        assert rule_data["name"] == "Test Rule"
        assert rule_data["enabled"] is True
        assert rule_data["action"] == "accept"

    def test_unknown_rule_types_skipped(self, change_detector):
        """Test that unknown rule types are skipped."""
        data = {
            "unknown_type": [{"_id": "unknown_123"}],
            "firewall_policies": [{"_id": "rule_123", "name": "Test Rule"}]
        }
        
        snapshot = change_detector._build_state_snapshot(data)
        
        # Unknown type should be skipped
        assert "unknown_type" not in snapshot
        # Known type should be included
        assert "firewall_policies" in snapshot
        assert "rule_123" in snapshot["firewall_policies"]

    def test_entities_without_id_skipped(self, change_detector):
        """Test that entities without ID are skipped."""
        data = {
            "firewall_policies": [
                {"_id": "rule_123", "name": "Valid Rule"},
                {"name": "Invalid Rule"}  # No ID
            ]
        }
        
        snapshot = change_detector._build_state_snapshot(data)
        
        # Only entity with ID should be included
        assert len(snapshot["firewall_policies"]) == 1
        assert "rule_123" in snapshot["firewall_policies"]


@pytest.mark.asyncio
class TestChangeDetectionIntegration:
    """Integration tests for change detection."""

    async def test_kill_switch_only_change_fires_single_trigger(self, mock_coordinator):
        """Test that only kill switch changes fire single trigger."""
        with patch('unifi_network_rules.helpers.rule.get_child_unique_id') as mock_get_child_id:
            mock_get_child_id.return_value = "route_123_kill_switch"
        
        # Mock HomeAssistant instance
        mock_hass = Mock()
        mock_hass.data = {}
        mock_hass.states = Mock()
        mock_hass.bus = Mock()
        
        detector = UnifiedChangeDetector(mock_hass, mock_coordinator)
        
        # Set up initial state
        initial_mock = Mock()
        initial_mock.raw = {
            "_id": "route_123",
            "name": "Games Route", 
            "enabled": True,
            "kill_switch_enabled": True
        }
        initial_mock.enabled = True
        initial_mock.kill_switch_enabled = True
        
        initial_data = {
            "traffic_routes": [initial_mock]
        }
        
        # Build initial snapshot
        initial_snapshot = detector._build_state_snapshot(initial_data)
        detector._previous_state = initial_snapshot
        
        # Change only kill switch
        updated_mock = Mock()
        updated_mock.raw = {
            "_id": "route_123",
            "name": "Games Route",
            "enabled": True,  # Parent unchanged
            "kill_switch_enabled": False  # Kill switch changed
        }
        updated_mock.enabled = True
        updated_mock.kill_switch_enabled = False
        
        updated_data = {
            "traffic_routes": [updated_mock]
        }
        
        with patch.object(detector, '_fire_unified_trigger', new_callable=AsyncMock) as mock_fire:
            changes = await detector.detect_and_fire_changes(updated_data)
            
            # Should detect exactly one change (kill switch)
            assert len(changes) == 1
            assert changes[0].change_action == "disabled"
            assert "kill_switch" in changes[0].unique_id
            
            # Should fire exactly one trigger
            assert mock_fire.call_count == 1

    async def test_led_change_fires_trigger(self, mock_coordinator):
        """Test that LED changes fire triggers correctly."""
        # Mock HomeAssistant instance
        mock_hass = Mock()
        mock_hass.data = {}
        mock_hass.states = Mock()
        mock_hass.bus = Mock()
        
        detector = UnifiedChangeDetector(mock_hass, mock_coordinator)
        
        # Set up initial state with LED on
        mock_device = Mock()
        mock_device.id = "device_123"
        mock_device.name = "Test Device"
        mock_device.led_override = "on"
        mock_device.configure_mock(spec=['id', 'name', 'led_override'])  # Direct attribute access
        
        initial_data = {"devices": [mock_device]}
        initial_snapshot = detector._build_state_snapshot(initial_data)
        detector._previous_state = initial_snapshot
        
        # Change LED to off
        mock_device_updated = Mock()
        mock_device_updated.id = "device_123"
        mock_device_updated.name = "Test Device"
        mock_device_updated.led_override = "off"
        mock_device_updated.configure_mock(spec=['id', 'name', 'led_override'])
        
        updated_data = {"devices": [mock_device_updated]}
        
        with patch.object(detector, '_fire_unified_trigger', new_callable=AsyncMock) as mock_fire:
            changes = await detector.detect_and_fire_changes(updated_data)
            
            # Should detect LED change
            assert len(changes) == 1
            assert changes[0].change_action == "disabled"
            assert changes[0].change_type == "device"
            
            # Should fire trigger
            assert mock_fire.call_count == 1
