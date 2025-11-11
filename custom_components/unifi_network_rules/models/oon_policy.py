"""OON policy model for UniFi Network Rules integration."""
from __future__ import annotations

from typing import Any, Dict


class OONPolicy:
    """Representation of a UniFi Object-Oriented Network policy."""

    def __init__(self, data: Dict[str, Any]) -> None:
        """Initialize OON policy from raw API data."""
        self.raw = data.copy()  # Store raw data for API updates

        # Core properties
        # UniFi API uses "_id" but some responses may use "id"
        self._id = data.get("_id") or data.get("id")
        self.name = data.get("name", "")
        self.enabled = data.get("enabled", False)
        self.target_type = data.get("target_type", "CLIENTS")
        self.targets = data.get("targets", [])

        # Nested configurations stored as dicts (can be parsed if needed)
        self.qos = data.get("qos", {})
        self.route = data.get("route", {})
        self.secure = data.get("secure", {})

    @property
    def id(self) -> str:
        """Get the policy ID."""
        return self._id or ""

    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API updates."""
        return dict(self.raw)

    def has_kill_switch(self) -> bool:
        """Check if policy has routing enabled with kill switch."""
        route = self.route
        return (
            route.get("enabled", False) is True
            and isinstance(route.get("kill_switch"), bool)
        )

