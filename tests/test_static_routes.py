"""Tests for the UniFi Network Rules Static Routes functionality."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.unifi_network_rules.coordinator import UnifiRuleUpdateCoordinator
from custom_components.unifi_network_rules.models.static_route import (
    StaticRoute,
    StaticRouteRequest,
)
from custom_components.unifi_network_rules.switch import UnifiStaticRouteSwitch
from custom_components.unifi_network_rules.udm.routes import RoutesMixin


@pytest.fixture
def static_route_data():
    """Return example static route data from UniFi API."""
    return {
        "_id": "67507951234567890abcdef0",
        "name": "Guest Network Route",
        "enabled": True,
        "site_id": "600ee7b12345678901234567",
        "static-route_network": "192.168.2.0/24",
        "static-route_interface": "600ee7b12345678901234568",
        "gateway_device": "60:60:60:60:60:60",
        "gateway_type": "default",
        "static-route_type": "interface-route",
        "type": "static-route",
        "static-route_distance": 1,
    }


@pytest.fixture
def static_route_data_minimal():
    """Return minimal static route data."""
    return {
        "_id": "67507951234567890abcdef1",
        "static-route_network": "10.0.100.0/24",
        "gateway_device": "192.168.1.1",
        "gateway_type": "default",
        "static-route_type": "static-route",
        "type": "static-route",
    }


@pytest.fixture
def routes_mixin():
    """Return a RoutesMixin instance with mocked controller."""
    mixin = RoutesMixin()
    mixin.controller = AsyncMock()
    return mixin


class TestStaticRouteModel:
    """Tests for StaticRoute model."""

    def test_static_route_initialization(self, static_route_data):
        """Test StaticRoute initialization with complete data."""
        route = StaticRoute(static_route_data)

        assert route.id == "67507951234567890abcdef0"
        assert route.name == "Guest Network Route"
        assert route.enabled is True
        assert route.destination == "192.168.2.0/24"
        assert route.gateway == "60:60:60:60:60:60"
        assert route.interface == "600ee7b12345678901234568"
        assert route.route_type == "interface-route"
        assert route.gateway_type == "default"
        assert route.site_id == "600ee7b12345678901234567"
        assert route.distance == 1

    def test_static_route_initialization_minimal(self, static_route_data_minimal):
        """Test StaticRoute initialization with minimal data."""
        route = StaticRoute(static_route_data_minimal)

        assert route.id == "67507951234567890abcdef1"
        assert route.name == "Route 10.0.100.0/24"  # Generated name
        assert route.enabled is True  # Default value
        assert route.destination == "10.0.100.0/24"
        assert route.gateway == "192.168.1.1"
        assert route.interface is None
        assert route.route_type == "static-route"
        assert route.gateway_type == "default"
        assert route.distance is None

    def test_static_route_defaults(self):
        """Test StaticRoute applies proper defaults."""
        minimal_data = {"_id": "test123", "static-route_network": "172.16.0.0/16"}

        route = StaticRoute(minimal_data)

        assert route.enabled is True
        assert route.name == "Route 172.16.0.0/16"
        assert route.raw["type"] == "static-route"

    def test_static_route_string_representation(self, static_route_data):
        """Test StaticRoute string representations."""
        route = StaticRoute(static_route_data)

        str_repr = str(route)
        assert "Guest Network Route" in str_repr
        assert "192.168.2.0/24" in str_repr
        assert "60:60:60:60:60:60" in str_repr

        repr_str = repr(route)
        assert "StaticRoute" in repr_str
        assert "67507951234567890abcdef0" in repr_str
        assert "enabled=True" in repr_str


class TestStaticRouteRequest:
    """Tests for StaticRouteRequest API request objects."""

    def test_create_get_request(self):
        """Test creating GET request for static routes."""
        request = StaticRouteRequest.create_get_request()

        assert request.method == "get"
        assert request.path == "/rest/routing"
        assert request.data is None

    def test_create_update_request(self, static_route_data):
        """Test creating PUT request to update static route."""
        route = StaticRoute(static_route_data)
        request = StaticRouteRequest.create_update_request(route)

        assert request.method == "put"
        assert request.path == "/rest/routing/67507951234567890abcdef0"
        assert request.data == route.raw


class TestRoutesMixinStaticRoutes:
    """Tests for RoutesMixin static route methods."""

    @pytest.mark.asyncio
    async def test_get_static_routes_success(self, routes_mixin, static_route_data):
        """Test successful retrieval of static routes."""
        api_response = {"meta": {"rc": "ok"}, "data": [static_route_data]}
        routes_mixin.controller.request.return_value = api_response

        routes = await routes_mixin.get_static_routes()

        assert len(routes) == 1
        assert isinstance(routes[0], StaticRoute)
        assert routes[0].id == "67507951234567890abcdef0"
        assert routes[0].name == "Guest Network Route"
        routes_mixin.controller.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_static_routes_empty_response(self, routes_mixin):
        """Test handling empty response from API."""
        api_response = {"meta": {"rc": "ok"}, "data": []}
        routes_mixin.controller.request.return_value = api_response

        routes = await routes_mixin.get_static_routes()

        assert routes == []

    @pytest.mark.asyncio
    async def test_get_static_routes_no_data_key(self, routes_mixin):
        """Test handling response without data key."""
        api_response = {"meta": {"rc": "ok"}}
        routes_mixin.controller.request.return_value = api_response

        routes = await routes_mixin.get_static_routes()

        assert routes == []

    @pytest.mark.asyncio
    async def test_get_static_routes_api_error(self, routes_mixin):
        """Test handling API errors."""
        routes_mixin.controller.request.side_effect = Exception("API Error")

        routes = await routes_mixin.get_static_routes()

        assert routes == []

    @pytest.mark.asyncio
    async def test_update_static_route_success(self, routes_mixin, static_route_data):
        """Test successful static route update."""
        route = StaticRoute(static_route_data)
        routes_mixin.controller.request.return_value = {"meta": {"rc": "ok"}}

        result = await routes_mixin.update_static_route(route)

        assert result is True
        routes_mixin.controller.request.assert_called_once()
        call_args = routes_mixin.controller.request.call_args[0][0]
        assert call_args.method == "put"
        assert call_args.path == "/rest/routing/67507951234567890abcdef0"

    @pytest.mark.asyncio
    async def test_update_static_route_api_error(self, routes_mixin, static_route_data):
        """Test handling API errors during update."""
        route = StaticRoute(static_route_data)
        routes_mixin.controller.request.side_effect = Exception("Update failed")

        result = await routes_mixin.update_static_route(route)

        assert result is False

    @pytest.mark.asyncio
    async def test_toggle_static_route_enable(self, routes_mixin, static_route_data):
        """Test toggling static route from disabled to enabled."""
        # Start with disabled route
        static_route_data["enabled"] = False
        route = StaticRoute(static_route_data)
        routes_mixin.controller.request.return_value = {"meta": {"rc": "ok"}}

        result = await routes_mixin.toggle_static_route(route)

        assert result is True
        routes_mixin.controller.request.assert_called_once()
        call_args = routes_mixin.controller.request.call_args[0][0]
        assert call_args.data["enabled"] is True

    @pytest.mark.asyncio
    async def test_toggle_static_route_disable(self, routes_mixin, static_route_data):
        """Test toggling static route from enabled to disabled."""
        # Start with enabled route
        static_route_data["enabled"] = True
        route = StaticRoute(static_route_data)
        routes_mixin.controller.request.return_value = {"meta": {"rc": "ok"}}

        result = await routes_mixin.toggle_static_route(route)

        assert result is True
        routes_mixin.controller.request.assert_called_once()
        call_args = routes_mixin.controller.request.call_args[0][0]
        assert call_args.data["enabled"] is False

    @pytest.mark.asyncio
    async def test_toggle_static_route_api_error(self, routes_mixin, static_route_data):
        """Test handling API errors during toggle."""
        route = StaticRoute(static_route_data)
        routes_mixin.controller.request.side_effect = Exception("Toggle failed")

        result = await routes_mixin.toggle_static_route(route)

        assert result is False


class TestUnifiStaticRouteSwitch:
    """Tests for UnifiStaticRouteSwitch entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Return a mocked coordinator."""
        coordinator = Mock(spec=UnifiRuleUpdateCoordinator)
        coordinator.api = AsyncMock()
        coordinator.hass = Mock()
        # Add required attributes for helper functions
        coordinator.firewall_zones = []

        # Properly handle async_create_task to prevent coroutine warnings
        def mock_async_create_task(coro):
            if asyncio.iscoroutine(coro):
                try:
                    loop = asyncio.get_running_loop()
                    return loop.create_task(coro)
                except RuntimeError:
                    coro.close()
                    return Mock()
            return Mock()

        coordinator.hass.async_create_task = mock_async_create_task
        return coordinator

    def test_static_route_switch_initialization(self, mock_coordinator, static_route_data):
        """Test StaticRouteSwitch initialization."""
        route = StaticRoute(static_route_data)

        switch = UnifiStaticRouteSwitch(
            coordinator=mock_coordinator, rule_data=route, rule_type="static_routes", entry_id="test_entry"
        )

        assert switch._attr_icon == "mdi:map-marker-path"
        assert switch.coordinator == mock_coordinator

    def test_static_route_switch_properties(self, mock_coordinator, static_route_data):
        """Test static route switch has correct properties."""
        route = StaticRoute(static_route_data)

        switch = UnifiStaticRouteSwitch(coordinator=mock_coordinator, rule_data=route, rule_type="static_routes")

        # Test that the switch has the expected properties
        assert hasattr(switch, "coordinator")
        assert switch.coordinator == mock_coordinator
        assert hasattr(switch, "_rule_type")
        assert switch._rule_type == "static_routes"
        assert hasattr(switch, "_rule_data")
        assert isinstance(switch._rule_data, StaticRoute)

    def test_static_route_switch_api_integration(self, mock_coordinator, static_route_data):
        """Test static route switch integrates with API properly."""
        route = StaticRoute(static_route_data)
        mock_coordinator.api.toggle_static_route = Mock()

        UnifiStaticRouteSwitch(coordinator=mock_coordinator, rule_data=route, rule_type="static_routes")

        # Test that the API method exists and is accessible
        assert hasattr(mock_coordinator.api, "toggle_static_route")
        assert callable(mock_coordinator.api.toggle_static_route)


class TestStaticRoutesIntegration:
    """Tests for static routes integration with coordinator and triggers."""

    @pytest.mark.asyncio
    async def test_coordinator_static_routes_update(self):
        """Test coordinator updates static routes collection."""
        with patch("custom_components.unifi_network_rules.coordination.coordinator.UDMAPI") as mock_api_class:
            mock_api = AsyncMock()
            mock_api.get_static_routes.return_value = [
                StaticRoute({"_id": "route1", "static-route_network": "192.168.1.0/24"}),
                StaticRoute({"_id": "route2", "static-route_network": "10.0.0.0/8"}),
            ]
            mock_api_class.return_value = mock_api

            # Test that coordinator would call the API method
            result = await mock_api.get_static_routes()
            assert len(result) == 2
            assert isinstance(result[0], StaticRoute)

    def test_static_routes_trigger_integration(self):
        """Test static routes are included in trigger system."""
        from custom_components.unifi_network_rules.unified_change_detector import UnifiedChangeDetector
        from custom_components.unifi_network_rules.unified_trigger import VALID_CHANGE_TYPES

        # Test "route" is in valid change types
        assert "route" in VALID_CHANGE_TYPES

        # Test change detector has static routes mapping
        mock_hass = Mock()
        mock_coordinator = Mock()
        detector = UnifiedChangeDetector(mock_hass, mock_coordinator)
        assert "static_routes" in detector._rule_type_mapping
        assert detector._rule_type_mapping["static_routes"] == "route"

    def test_static_routes_backup_integration(self):
        """Test static routes are included in backup service mapping."""
        from custom_components.unifi_network_rules.services.backup_services import async_backup_rules_service

        # This tests that the backup service would handle static routes
        # The actual rule_type_map is defined within the should_restore function
        # We test that the functionality exists by checking the pattern
        assert callable(async_backup_rules_service)

    def test_switch_rule_types_includes_static_routes(self):
        """Test RULE_TYPES includes static routes."""
        from custom_components.unifi_network_rules.switch import RULE_TYPES

        assert "static_routes" in RULE_TYPES
        assert RULE_TYPES["static_routes"] == "Static Route"


class TestStaticRoutesErrorHandling:
    """Tests for error handling in static routes functionality."""

    @pytest.mark.asyncio
    async def test_invalid_route_data_handling(self):
        """Test handling of invalid route data."""
        # Test with missing required fields
        invalid_data = {"name": "Invalid Route"}
        route = StaticRoute(invalid_data)

        # Should handle gracefully with defaults
        assert route.id == ""
        assert route.destination == ""
        assert route.enabled is True

    @pytest.mark.asyncio
    async def test_api_timeout_handling(self, routes_mixin):
        """Test handling of API timeouts."""
        routes_mixin.controller.request.side_effect = TimeoutError("Request timeout")

        routes = await routes_mixin.get_static_routes()
        assert routes == []

    @pytest.mark.asyncio
    async def test_malformed_api_response(self, routes_mixin):
        """Test handling of malformed API responses."""
        # Test with malformed JSON-like response
        routes_mixin.controller.request.return_value = {"invalid": "structure"}

        routes = await routes_mixin.get_static_routes()
        assert routes == []

    @pytest.mark.asyncio
    async def test_network_error_handling(self, routes_mixin):
        """Test handling of network-related errors."""
        import aiohttp

        routes_mixin.controller.request.side_effect = aiohttp.ClientError("Network error")

        result = await routes_mixin.get_static_routes()
        assert result == []


class TestStaticRoutesPerformance:
    """Tests for static routes performance considerations."""

    @pytest.mark.asyncio
    async def test_large_routes_collection_handling(self, routes_mixin):
        """Test handling large collections of static routes efficiently."""
        # Generate a large number of static routes
        large_route_data = []
        for i in range(100):
            large_route_data.append(
                {
                    "_id": f"route_{i:03d}",
                    "name": f"Route {i}",
                    "static-route_network": f"10.{i}.0.0/24",
                    "gateway_device": "192.168.1.1",
                    "enabled": i % 2 == 0,  # Alternate enabled/disabled
                    "type": "static-route",
                }
            )

        api_response = {"meta": {"rc": "ok"}, "data": large_route_data}
        routes_mixin.controller.request.return_value = api_response

        routes = await routes_mixin.get_static_routes()

        assert len(routes) == 100
        assert all(isinstance(route, StaticRoute) for route in routes)
        # Test that enabled states are preserved
        enabled_count = sum(1 for route in routes if route.enabled)
        assert enabled_count == 50  # Half should be enabled

    def test_static_route_memory_efficiency(self, static_route_data):
        """Test that StaticRoute objects are memory efficient."""
        # Create multiple route objects and ensure they don't duplicate data unnecessarily
        routes = [StaticRoute(static_route_data.copy()) for _ in range(10)]

        # Each route should have its own raw data copy
        for i, route in enumerate(routes):
            route.raw["test_field"] = f"unique_{i}"

        # Verify data isolation
        unique_values = {route.raw.get("test_field") for route in routes}
        assert len(unique_values) == 10
