from dataclasses import dataclass
from typing import Self

from aiounifi.models.api import ApiRequestV2
from aiounifi.models.traffic_route import (
    TrafficRoute as AioUnifiTrafficRoute,
)
from aiounifi.models.traffic_route import (
    TypedTrafficRoute as AioUnifiTypedTrafficRoute,
)


class TypedTrafficRoute(AioUnifiTypedTrafficRoute):
    """Extended traffic route type definition with kill switch support."""

    # Add the kill_switch_enabled field to the type definition
    kill_switch_enabled: bool


@dataclass
class TrafficRouteKillSwitchRequest(ApiRequestV2):
    """Request object for toggling kill switch on a traffic route."""

    @classmethod
    def create(cls, traffic_route: TypedTrafficRoute, enable_kill_switch: bool) -> Self:
        """Create traffic route kill switch toggle request."""
        # Make a copy of the raw data to avoid modifying the original
        updated_route = traffic_route.copy()
        updated_route["kill_switch_enabled"] = enable_kill_switch

        return cls(
            method="put",
            path=f"/trafficroutes/{updated_route['_id']}",
            data=updated_route,
        )


class TrafficRoute(AioUnifiTrafficRoute):
    """Extended traffic route with kill switch support."""

    raw: TypedTrafficRoute

    def __init__(self, raw: dict) -> None:
        """Initialize the TrafficRoute with kill switch support."""
        # Ensure the raw dictionary has the kill_switch_enabled property
        if "kill_switch_enabled" not in raw:
            # Default to False if not present
            raw["kill_switch_enabled"] = False
        super().__init__(raw)

    @property
    def kill_switch_enabled(self) -> bool:
        """Return if kill switch is enabled."""
        return self.raw.get("kill_switch_enabled", False)
