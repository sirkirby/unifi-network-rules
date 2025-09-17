"""Module for UniFi traffic routes operations."""

from typing import Any, Dict, List, Optional

# Import directly from specific module
from aiounifi.models.traffic_route import (
    TrafficRouteListRequest,
    TrafficRouteSaveRequest,
)

from ..const import (
    LOGGER,
    API_PATH_TRAFFIC_ROUTES,
    API_PATH_TRAFFIC_ROUTE_DETAIL
)

# Import our custom extended models
from ..models.traffic_route import TrafficRoute, TrafficRouteKillSwitchRequest

class RoutesMixin:
    """Mixin class for traffic routes operations."""

    async def get_traffic_routes(self) -> List[TrafficRoute]:
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

    async def add_traffic_route(self, route_data: Dict[str, Any]) -> Optional[TrafficRoute]:
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

    async def toggle_traffic_route(self, route: Any) -> bool:
        """Toggle a traffic route on/off."""
        LOGGER.debug("Toggling traffic route state")
        try:
            # Ensure the route is a proper TrafficRoute object
            if not isinstance(route, TrafficRoute):
                LOGGER.error("Expected TrafficRoute object but got %s", type(route))
                return False
            
            # Toggle the current state
            new_state = not route.enabled
            LOGGER.debug("Toggling route %s to %s", route.id, new_state)
            
            # Create a route dictionary with updated state - this is needed because TrafficRouteSaveRequest
            # operates on the dictionary directly, not on the TrafficRoute object
            route_dict = route.raw.copy()
            
            # The TrafficRouteSaveRequest.create method can take both the dictionary and an enable flag
            request = TrafficRouteSaveRequest.create(route_dict, new_state)
            
            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Traffic route %s toggled successfully to %s", route.id, new_state)
            return True
        except Exception as err:
            LOGGER.error("Failed to toggle traffic route: %s", str(err))
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

    async def toggle_traffic_route_kill_switch(self, route: Any) -> bool:
        """Toggle a traffic route's kill switch on/off."""
        LOGGER.debug("Toggling traffic route kill switch state")
        try:
            # Ensure the route is a proper TrafficRoute object
            if not isinstance(route, TrafficRoute):
                LOGGER.error("Expected TrafficRoute object but got %s", type(route))
                return False
            
            # Toggle the current kill switch state
            new_state = not route.kill_switch_enabled
            LOGGER.debug("Toggling kill switch for route %s to %s", route.id, new_state)
            
            # Create a new TrafficRoute with updated kill switch state
            updated_route = TrafficRoute(route.raw.copy())
            updated_route.raw["kill_switch_enabled"] = new_state
            
            # Send the request to update the route
            request = TrafficRouteKillSwitchRequest.create(updated_route.raw, new_state)
            result = await self.controller.request(request)
            
            if result:
                LOGGER.debug("Traffic route %s kill switch toggled successfully to %s", route.id, new_state)
            else:
                LOGGER.error("Failed to toggle kill switch for traffic route %s", route.id)
            return bool(result)
        except Exception as err:
            LOGGER.error("Failed to toggle traffic route kill switch: %s", str(err))
            return False 
