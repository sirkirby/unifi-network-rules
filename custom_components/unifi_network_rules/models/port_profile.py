"""Typed model for UniFi Ethernet Port Profile used by UNR.

Keeps raw dict from controller but exposes typed accessors for id, name,
and computed enabled state that we use for switch entities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PortProfile:
    """Represents a UniFi Port Profile with helper accessors.

    Enabled is a computed concept for UNR: a profile is considered "enabled"
    when it has a native network assigned and management VLAN is not blocked.
    """

    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.raw.get("_id") or self.raw.get("id") or "")

    @property
    def name(self) -> str:
        return str(self.raw.get("name") or self.raw.get("description") or f"Port Profile {self.id}")

    @property
    def enabled(self) -> bool:
        native = self.raw.get("native_networkconf_id")
        tagged_mgmt = self.raw.get("tagged_vlan_mgmt")
        # Treat as enabled if a native network is configured and mgmt VLANs are not blocked
        return bool(native) and tagged_mgmt not in {"block_all", "block-custom"}

    def to_dict(self) -> dict[str, Any]:
        """Return a shallow copy of the raw dict suitable for updates."""
        return dict(self.raw)
