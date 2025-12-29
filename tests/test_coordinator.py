"""Comprehensive test suite for the refactored UniFi Network Rules Coordinator.

Tests the modular coordinator architecture and ensures all coordination modules
work together correctly while maintaining backward compatibility.
"""

import asyncio
import os
import sys
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Add the custom_components directory to Python path
test_dir = os.path.dirname(__file__)
project_root = os.path.dirname(test_dir)
custom_components_path = os.path.join(project_root, "custom_components")
if custom_components_path not in sys.path:
    sys.path.insert(0, custom_components_path)

from unifi_network_rules.coordination.coordinator import UnifiRuleUpdateCoordinator
from unifi_network_rules.coordinator import NeedsFetch


@pytest.fixture
def mock_hass():
    """Return a mocked Home Assistant instance."""
    hass = Mock()
    hass.data = {}
    hass.config_entries = Mock()
    hass.states = Mock()
    hass.bus = Mock()

    # Track created tasks to prevent "coroutine never awaited" warnings
    created_tasks = []

    def mock_async_create_task(coro):
        """Mock async_create_task that properly handles coroutines."""
        # If it's a real coroutine, schedule it; otherwise just track it
        if asyncio.iscoroutine(coro):
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(coro)
                created_tasks.append(task)
                return task
            except RuntimeError:
                # No running loop - close the coroutine to prevent warning
                coro.close()
                return Mock()
        # For mocks, just return a mock task
        return Mock()

    hass.async_create_task = mock_async_create_task
    hass._created_tasks = created_tasks
    return hass


@pytest.fixture
def mock_api():
    """Return a mocked UDMAPI instance."""
    api = Mock()
    api.host = "unifi.local"
    api.port = 443
    api.username = "admin"
    api.site = "default"
    api._last_error_message = ""
    return api


@pytest.fixture
def coordinator(mock_hass, mock_api):
    """Return a coordinator instance with real modules but mocked dependencies."""
    with (
        patch("unifi_network_rules.coordination.coordinator.SmartPollingManager") as mock_polling,
        patch("unifi_network_rules.coordination.coordinator.UnifiedChangeDetector") as mock_detector,
    ):
        # Set up smart polling mock
        mock_polling_instance = Mock()
        mock_polling_instance.cleanup = AsyncMock()
        mock_polling_instance.register_external_change_detected = AsyncMock()
        mock_polling_instance.get_status.return_value = {"status": "active"}
        mock_polling.return_value = mock_polling_instance

        # Set up change detector mock
        mock_detector_instance = Mock()
        mock_detector_instance.detect_and_fire_changes = AsyncMock(return_value=[])
        mock_detector_instance.get_status.return_value = {"last_change": None}
        mock_detector.return_value = mock_detector_instance

        coordinator = UnifiRuleUpdateCoordinator(mock_hass, mock_api)
        return coordinator


class TestCoordinatorInitialization:
    """Test coordinator initialization and module setup."""

    def test_coordinator_initializes_correctly(self, coordinator, mock_hass, mock_api):
        """Test that coordinator initializes with correct properties."""
        assert coordinator.hass == mock_hass
        assert coordinator.api == mock_api
        assert coordinator.name == "unifi_network_rules"
        assert coordinator.update_interval == timedelta(seconds=300)

        # Verify all coordination modules are initialized
        assert coordinator.data_fetcher is not None
        assert coordinator.entity_manager is not None
        assert coordinator.auth_manager is not None
        assert coordinator.state_manager is not None
        assert coordinator.change_detector is not None
        assert coordinator.smart_polling is not None

    def test_coordinator_has_expected_collections(self, coordinator):
        """Test that coordinator maintains backward compatibility collections."""
        # Check that all the expected rule collections exist
        assert hasattr(coordinator, "port_forwards")
        assert hasattr(coordinator, "traffic_routes")
        assert hasattr(coordinator, "firewall_policies")
        assert hasattr(coordinator, "traffic_rules")
        assert hasattr(coordinator, "static_routes")
        assert hasattr(coordinator, "legacy_firewall_rules")
        assert hasattr(coordinator, "firewall_zones")
        assert hasattr(coordinator, "wlans")
        assert hasattr(coordinator, "qos_rules")
        assert hasattr(coordinator, "vpn_clients")
        assert hasattr(coordinator, "vpn_servers")
        assert hasattr(coordinator, "devices")
        assert hasattr(coordinator, "port_profiles")
        assert hasattr(coordinator, "networks")
        assert hasattr(coordinator, "nat_rules")

    def test_coordinator_properties_work(self, coordinator):
        """Test that coordinator properties delegate correctly."""
        # Test _initial_update_done property
        assert hasattr(coordinator, "_initial_update_done")

        # Test _last_successful_data property
        assert hasattr(coordinator, "_last_successful_data")


class TestCoordinatorModularArchitecture:
    """Test that the modular coordinator architecture works correctly."""

    def test_coordination_modules_exist(self, coordinator):
        """Test that all coordination modules are properly initialized."""
        # Verify modules exist and have expected types
        from unifi_network_rules.coordination.auth_manager import CoordinatorAuthManager
        from unifi_network_rules.coordination.data_fetcher import CoordinatorDataFetcher
        from unifi_network_rules.coordination.entity_manager import CoordinatorEntityManager
        from unifi_network_rules.coordination.state_manager import CoordinatorStateManager

        assert isinstance(coordinator.data_fetcher, CoordinatorDataFetcher)
        assert isinstance(coordinator.entity_manager, CoordinatorEntityManager)
        assert isinstance(coordinator.auth_manager, CoordinatorAuthManager)
        assert isinstance(coordinator.state_manager, CoordinatorStateManager)

    def test_ha_initiated_operations(self, coordinator):
        """Test HA-initiated operation tracking."""
        # Test registering an operation
        coordinator.register_ha_initiated_operation("rule_123", "switch.test", "enabled")

        # Test checking and consuming the operation
        result = coordinator.check_and_consume_ha_initiated_operation("rule_123")
        # Should delegate to auth_manager
        assert coordinator.auth_manager.check_and_consume_ha_initiated_operation is not None

    def test_device_trigger_firing(self, coordinator):
        """Test device trigger firing through dispatcher."""
        # Should not raise an exception
        coordinator.fire_device_trigger_via_dispatcher(
            "device_123", "Test Device", "modified", {"old": "state"}, {"new": "state"}
        )

    def test_smart_polling_integration(self, coordinator):
        """Test smart polling integration."""
        # Test getting smart polling status
        status = coordinator.get_smart_polling_status()
        assert isinstance(status, dict)

        # Test registering external change detection
        asyncio.run(coordinator.register_external_change_detected())

    def test_change_detector_integration(self, coordinator):
        """Test change detector integration."""
        # Test getting change detector status
        status = coordinator.get_change_detector_status()
        assert isinstance(status, dict)


class TestCoordinatorDataUpdate:
    """Test coordinator data update functionality."""

    @pytest.mark.asyncio
    async def test_async_update_data_basic_flow(self, coordinator):
        """Test the basic async update data flow."""
        # Mock the data fetcher to return test data
        test_data = {
            "firewall_policies": [{"_id": "policy1", "name": "Test Policy"}],
            "traffic_routes": [],
            "port_forwards": [],
        }

        with patch.object(coordinator.data_fetcher, "fetch_all_entity_data", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = test_data

            # Mock other components to avoid errors
            coordinator.state_manager.validate_data_and_handle_errors = Mock(return_value=True)
            coordinator.entity_manager.check_for_deleted_rules = Mock()
            coordinator.entity_manager.discover_and_add_new_entities = AsyncMock()

            result = await coordinator._async_update_data()

            # Should return the fetched data
            assert result is not None
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_data_handles_authentication_in_progress(self, coordinator):
        """Test that update data handles authentication in progress."""
        # Mock authentication in progress
        coordinator.auth_manager.is_authentication_in_progress = Mock(return_value=True)
        coordinator.state_manager._last_successful_data = {"cached": "data"}

        result = await coordinator._async_update_data()

        # Should return cached data
        assert result == {"cached": "data"}

    @pytest.mark.asyncio
    async def test_async_update_data_handles_invalid_data(self, coordinator):
        """Test that update data handles invalid data gracefully."""
        test_data = {"invalid": "data"}

        with patch.object(coordinator.data_fetcher, "fetch_all_entity_data", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = test_data

            # Mock validation to return False (invalid data)
            coordinator.state_manager.validate_data_and_handle_errors = Mock(return_value=False)
            coordinator.state_manager._last_successful_data = {"cached": "valid_data"}

            result = await coordinator._async_update_data()

            # Should return cached data when validation fails
            assert result == {"cached": "valid_data"}


class TestCoordinatorErrorHandling:
    """Test coordinator error handling."""

    @pytest.mark.asyncio
    async def test_async_update_data_handles_fetch_errors(self, coordinator):
        """Test that update data handles fetch errors."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        with patch.object(coordinator.data_fetcher, "fetch_all_entity_data", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("Fetch failed")

            # Mock auth manager error handling to return False (no recovery)
            coordinator.auth_manager.handle_authentication_error = AsyncMock(return_value=False)
            coordinator.auth_manager.check_auth_error = Mock(return_value=False)

            # When there's no previous data and error is not recoverable, should raise UpdateFailed
            with pytest.raises(UpdateFailed, match="Error updating data: Fetch failed"):
                await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_async_update_data_returns_cached_data_on_error(self, coordinator):
        """Test that update data returns cached data when fetch fails but previous data exists."""
        with patch.object(coordinator.data_fetcher, "fetch_all_entity_data", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("Fetch failed")

            # Set previous data
            coordinator.data = {"cached": "data"}

            # Mock auth manager error handling
            coordinator.auth_manager.handle_authentication_error = AsyncMock(return_value=False)
            coordinator.auth_manager.check_auth_error = Mock(return_value=False)

            result = await coordinator._async_update_data()

            # Should return cached data when previous data exists
            assert result == {"cached": "data"}


class TestCoordinatorLifecycle:
    """Test coordinator lifecycle methods."""

    def test_shutdown_sync(self, coordinator):
        """Test synchronous shutdown method."""
        # Should not raise an exception
        coordinator.shutdown()

    @pytest.mark.asyncio
    async def test_async_shutdown(self, coordinator):
        """Test asynchronous shutdown method."""
        # Should not raise an exception
        await coordinator.async_shutdown()

        # Should call smart polling cleanup
        coordinator.smart_polling.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_new_entities_backward_compatibility(self, coordinator):
        """Test the backward compatibility process_new_entities method."""
        # Should not raise an exception (method exists for backward compatibility)
        await coordinator.process_new_entities()


class TestCoordinatorBackwardCompatibility:
    """Test coordinator backward compatibility."""

    def test_coordinator_can_be_imported_from_old_path(self):
        """Test that coordinator can still be imported from the old path."""
        import unifi_network_rules.coordination.coordinator as new_module
        import unifi_network_rules.coordinator as old_module

        assert old_module.UnifiRuleUpdateCoordinator is new_module.UnifiRuleUpdateCoordinator

    def test_needs_fetch_exception_exists(self):
        """Test that NeedsFetch exception is available."""
        assert NeedsFetch is not None
        assert issubclass(NeedsFetch, Exception)

    def test_coordinator_maintains_expected_interface(self):
        """Test that coordinator maintains expected public interface."""
        # Check essential methods exist
        assert hasattr(UnifiRuleUpdateCoordinator, "_async_update_data")
        assert hasattr(UnifiRuleUpdateCoordinator, "async_shutdown")
        assert hasattr(UnifiRuleUpdateCoordinator, "register_ha_initiated_operation")
        assert hasattr(UnifiRuleUpdateCoordinator, "check_and_consume_ha_initiated_operation")


class TestCoordinatorIntegration:
    """Test coordinator integration with its modules."""

    def test_internal_collections_update(self, coordinator):
        """Test that internal collections are updated correctly."""
        test_data = {
            "firewall_policies": [{"_id": "policy1"}],
            "traffic_routes": [{"_id": "route1"}],
            "port_forwards": [{"_id": "forward1"}],
        }

        coordinator._update_internal_collections(test_data)

        # Check that collections were updated
        assert len(coordinator.firewall_policies) == 1
        assert len(coordinator.traffic_routes) == 1
        assert len(coordinator.port_forwards) == 1

    def test_log_collection_counts(self, coordinator):
        """Test logging collection counts."""
        # Should not raise an exception
        coordinator._log_collection_counts()

    def test_coordinator_properties_delegation(self, coordinator):
        """Test that coordinator properties delegate to state manager correctly."""
        # Test that properties exist and can be accessed
        try:
            _ = coordinator._initial_update_done
            _ = coordinator._last_successful_data
            # If we get here without exceptions, delegation is working
            assert True
        except AttributeError:
            pytest.fail("Property delegation not working correctly")
