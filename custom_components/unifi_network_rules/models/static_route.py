"""Typed model for UniFi static route configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiounifi.models.api import ApiRequest


@dataclass
class TypedStaticRoute:
    """Type definition for static route from UniFi Network."""

    # Core route properties
    _id: str  # Route ID from UniFi
    name: str  # User-defined route name
    enabled: bool  # Route enabled status
    site_id: str  # UniFi site identifier

    # Route configuration
    static_route_network: str  # Network CIDR (e.g., "192.168.2.0/24")
    static_route_interface: str | None  # Interface name/ID
    gateway_device: str | None  # Gateway device MAC or ID
    gateway_type: str  # "default", "interface", or custom
    static_route_type: str  # "interface-route" or "static-route"
    type: str  # Always "static-route"

    # Optional properties
    static_route_distance: int | None = None  # Routing distance/metric


class StaticRoute:
    """Extended static route model with Home Assistant integration."""

    def __init__(self, raw: dict[str, Any]) -> None:
        """Initialize StaticRoute from raw API data."""
        self.raw = raw.copy()

        # Ensure required properties exist with defaults
        if "enabled" not in self.raw:
            self.raw["enabled"] = True
        if "name" not in self.raw:
            self.raw["name"] = f"Route {self.destination}"
        if "type" not in self.raw:
            self.raw["type"] = "static-route"

    @property
    def id(self) -> str:
        """Return route ID."""
        return self.raw.get("_id", "")

    @property
    def name(self) -> str:
        """Return route name."""
        return self.raw.get("name", f"Route {self.destination}")

    @property
    def enabled(self) -> bool:
        """Return if route is enabled."""
        return self.raw.get("enabled", True)

    @property
    def destination(self) -> str:
        """Return destination network CIDR."""
        return self.raw.get("static-route_network", "")

    @property
    def gateway(self) -> str | None:
        """Return gateway IP or device ID."""
        return self.raw.get("gateway_device")

    @property
    def interface(self) -> str | None:
        """Return interface name/ID."""
        return self.raw.get("static-route_interface")

    @property
    def route_type(self) -> str:
        """Return route type."""
        return self.raw.get("static-route_type", "static-route")

    @property
    def gateway_type(self) -> str:
        """Return gateway type."""
        return self.raw.get("gateway_type", "default")

    @property
    def site_id(self) -> str:
        """Return site ID."""
        return self.raw.get("site_id", "")

    @property
    def distance(self) -> int | None:
        """Return route distance/metric."""
        return self.raw.get("static-route_distance")

    def __str__(self) -> str:
        """Return string representation."""
        return f"StaticRoute({self.name}: {self.destination} via {self.gateway})"

    def __repr__(self) -> str:
        """Return detailed representation."""
        return f"StaticRoute(id={self.id}, name={self.name}, destination={self.destination}, enabled={self.enabled})"


@dataclass
class StaticRouteRequest(ApiRequest):
    """Base request for static route operations."""

    @classmethod
    def create_get_request(cls) -> StaticRouteRequest:
        """Create GET request for all static routes."""
        return cls(
            method="get",
            path="/rest/routing",
        )

    @classmethod
    def create_update_request(cls, route: StaticRoute) -> StaticRouteRequest:
        """Create PUT request to update a static route."""
        return cls(
            method="put",
            path=f"/rest/routing/{route.id}",
            data=route.raw,
        )
