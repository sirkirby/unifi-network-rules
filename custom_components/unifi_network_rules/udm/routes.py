"""Module for UniFi traffic routes operations."""

from typing import Any

# Import directly from specific module
from aiounifi.models.traffic_route import (
    TrafficRouteListRequest,
    TrafficRouteSaveRequest,
)

from ..const import API_PATH_TRAFFIC_ROUTE_DETAIL, API_PATH_TRAFFIC_ROUTES, LOGGER
from ..models.static_route import StaticRoute, StaticRouteRequest

# Import our custom extended models
from ..models.traffic_route import TrafficRoute, TrafficRouteKillSwitchRequest


class RoutesMixin:
    """Mixin class for traffic routes operations."""

    async def get_traffic_routes(self) -> list[TrafficRoute]:
        """Get all traffic routes."""
        try:
            # Using TrafficRouteListRequest for proper instantiation
            request = TrafficRouteListRequest.create()
            data = await self.controller.request(request)

            if data and "data" in data:
                # Return typed TrafficRoute objects instead of raw dictionaries
                result = []
                for route_data in data["data"]:
                    # Explicitly create TrafficRoute objects from the raw dictionary data
                    # Our custom TrafficRoute model will handle the kill_switch_enabled property
                    route = TrafficRoute(route_data)
                    result.append(route)
                LOGGER.debug("Converted %d traffic routes to typed objects", len(result))
                return result
            return []
        except Exception as err:
            LOGGER.error("Failed to get traffic routes: %s", str(err))
            return []

    async def add_traffic_route(self, route_data: dict[str, Any]) -> TrafficRoute | None:
        """Add a new traffic route."""
        LOGGER.debug("Adding traffic route: %s", route_data)
        try:
            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("POST", API_PATH_TRAFFIC_ROUTES, data=route_data, is_v2=True)
            response = await self.controller.request(request)

            if response and "data" in response:
                # Return a typed TrafficRoute object
                return TrafficRoute(response["data"])
            return None
        except Exception as err:
            LOGGER.error("Failed to add traffic route: %s", str(err))
            return None

    async def update_traffic_route(self, route: TrafficRoute) -> bool:
        """Update a traffic route.

        Args:
            route: The TrafficRoute object to update

        Returns:
            bool: True if the update was successful, False otherwise
        """
        route_id = route.id
        LOGGER.debug("Updating traffic route %s", route_id)
        try:
            # Convert the TrafficRoute object to a dictionary that TrafficRouteSaveRequest can use
            route_dict = route.raw.copy()

            # Using TrafficRouteSaveRequest for proper instantiation
            request = TrafficRouteSaveRequest.create(route_dict)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Traffic route %s updated successfully", route_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to update traffic route: %s", str(err))
            return False

    async def toggle_traffic_route(self, route: Any, target_state: bool) -> bool:
        """Set a traffic route to a specific enabled/disabled state.

        Args:
            route: The TrafficRoute object to modify
            target_state: The desired state (True=enabled, False=disabled)

        Returns:
            bool: True if the operation was successful, False otherwise
        """
        LOGGER.debug("Setting traffic route state")
        try:
            # Ensure the route is a proper TrafficRoute object
            if not isinstance(route, TrafficRoute):
                LOGGER.error("Expected TrafficRoute object but got %s", type(route))
                return False

            LOGGER.debug("Setting route %s to %s", route.id, target_state)

            # Create a route dictionary with updated state - this is needed because TrafficRouteSaveRequest
            # operates on the dictionary directly, not on the TrafficRoute object
            route_dict = route.raw.copy()

            # The TrafficRouteSaveRequest.create method can take both the dictionary and an enable flag
            request = TrafficRouteSaveRequest.create(route_dict, target_state)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Traffic route %s set successfully to %s", route.id, target_state)
            return True
        except Exception as err:
            LOGGER.error("Failed to set traffic route state: %s", str(err))
            return False

    async def remove_traffic_route(self, route_id: str) -> bool:
        """Remove a traffic route."""
        LOGGER.debug("Removing traffic route: %s", route_id)
        try:
            path = API_PATH_TRAFFIC_ROUTE_DETAIL.format(route_id=route_id)
            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("DELETE", path, is_v2=True)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Traffic route %s removed successfully", route_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove traffic route: %s", str(err))
            return False

    async def toggle_traffic_route_kill_switch(self, route: Any, target_state: bool) -> bool:
        """Set a traffic route's kill switch to a specific enabled/disabled state.

        Args:
            route: The TrafficRoute object to modify
            target_state: The desired state (True=enabled, False=disabled)

        Returns:
            bool: True if the operation was successful, False otherwise
        """
        LOGGER.debug("Setting traffic route kill switch state")
        try:
            # Ensure the route is a proper TrafficRoute object
            if not isinstance(route, TrafficRoute):
                LOGGER.error("Expected TrafficRoute object but got %s", type(route))
                return False

            LOGGER.debug("Setting kill switch for route %s to %s", route.id, target_state)

            # Create a new TrafficRoute with updated kill switch state
            updated_route = TrafficRoute(route.raw.copy())
            updated_route.raw["kill_switch_enabled"] = target_state

            # Send the request to update the route
            request = TrafficRouteKillSwitchRequest.create(updated_route.raw, target_state)
            result = await self.controller.request(request)

            if result:
                LOGGER.debug("Traffic route %s kill switch set successfully to %s", route.id, target_state)
            else:
                LOGGER.error("Failed to set kill switch for traffic route %s", route.id)
            return bool(result)
        except Exception as err:
            LOGGER.error("Failed to set traffic route kill switch state: %s", str(err))
            return False

    # Static Routes Methods

    async def get_static_routes(self) -> list[StaticRoute]:
        """Get all static routes."""
        try:
            # Use V1 API for static routes
            request = StaticRouteRequest.create_get_request()
            data = await self.controller.request(request)

            if data and "data" in data:
                # Return typed StaticRoute objects
                result = []
                for route_data in data["data"]:
                    route = StaticRoute(route_data)
                    result.append(route)
                LOGGER.debug("Converted %d static routes to typed objects", len(result))
                return result
            return []
        except Exception as err:
            LOGGER.error("Failed to get static routes: %s", str(err))
            return []

    async def update_static_route(self, route: StaticRoute) -> bool:
        """Update a static route.

        Args:
            route: The StaticRoute object to update

        Returns:
            bool: True if the update was successful, False otherwise
        """
        route_id = route.id
        LOGGER.debug("Updating static route %s", route_id)
        try:
            # Use StaticRouteRequest for proper API call
            request = StaticRouteRequest.create_update_request(route)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Static route %s updated successfully", route_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to update static route: %s", str(err))
            return False

    async def toggle_static_route(self, route: StaticRoute, target_state: bool) -> bool:
        """Set a static route to a specific enabled/disabled state.

        Args:
            route: The StaticRoute object to modify
            target_state: The desired state (True=enabled, False=disabled)

        Returns:
            bool: True if the operation was successful, False otherwise
        """
        LOGGER.debug("Setting static route state")
        try:
            LOGGER.debug("Setting static route %s to %s", route.id, target_state)

            # Create updated route with new state
            updated_route = StaticRoute(route.raw.copy())
            updated_route.raw["enabled"] = target_state

            # Use the update method to apply the change
            success = await self.update_static_route(updated_route)

            if success:
                LOGGER.debug("Static route %s set successfully to %s", route.id, target_state)
            else:
                LOGGER.error("Failed to set static route %s", route.id)
            return success
        except Exception as err:
            LOGGER.error("Failed to set static route state: %s", str(err))
            return False
