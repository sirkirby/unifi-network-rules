"""Typed model for UniFi NAT rule configuration (V2 API)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional


NatType = Literal["SNAT", "DNAT"]
IPVersion = Literal["IPV4", "IPV6"]
FilterType = Literal["NONE", "ADDRESS_AND_PORT", "ADDRESS", "PORT"]


@dataclass
class NATAddressPortFilter:
    """Filter object for NAT source/destination conditions."""

    filter_type: FilterType
    address: Optional[str] = None
    firewall_group_ids: Optional[List[str]] = None
    invert_address: bool = False
    invert_port: bool = False


class NATRule:
    """Typed wrapper for a UniFi NAT rule with helpers for HA integration."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        # Store a shallow copy of raw
        self.raw: Dict[str, Any] = dict(raw or {})

        # Ensure required defaults
        self.raw.setdefault("enabled", False)
        self.raw.setdefault("exclude", False)
        self.raw.setdefault("logging", False)
        self.raw.setdefault("ip_version", "IPV4")

    # --- Core properties ---
    @property
    def id(self) -> str:
        return self.raw.get("_id", "")

    @property
    def description(self) -> str:
        return self.raw.get("description", "")

    @property
    def enabled(self) -> bool:
        return bool(self.raw.get("enabled", False))

    @property
    def is_predefined(self) -> bool:
        return bool(self.raw.get("is_predefined", False))

    @property
    def type(self) -> Optional[NatType]:
        val = self.raw.get("type")
        return val if val in ("SNAT", "DNAT") else None

    @property
    def ip_version(self) -> IPVersion:
        val = self.raw.get("ip_version", "IPV4")
        return "IPV6" if str(val).upper() == "IPV6" else "IPV4"

    @property
    def ip_address(self) -> Optional[str]:
        return self.raw.get("ip_address")

    @property
    def out_interface(self) -> Optional[str]:
        return self.raw.get("out_interface")

    @property
    def rule_index(self) -> Optional[int]:
        return self.raw.get("rule_index")

    # --- Filters ---
    def _parse_filter(self, key: str) -> NATAddressPortFilter | None:
        f = self.raw.get(key)
        if not isinstance(f, dict):
            return None
        return NATAddressPortFilter(
            filter_type=f.get("filter_type", "NONE"),
            address=f.get("address"),
            firewall_group_ids=f.get("firewall_group_ids"),
            invert_address=bool(f.get("invert_address", False)),
            invert_port=bool(f.get("invert_port", False)),
        )

    @property
    def destination_filter(self) -> NATAddressPortFilter | None:
        return self._parse_filter("destination_filter")

    @property
    def source_filter(self) -> NATAddressPortFilter | None:
        return self._parse_filter("source_filter")

    # --- Helpers ---
    def is_custom(self) -> bool:
        """Return True if rule is user-defined (not predefined/system)."""
        return not self.is_predefined

    def to_api_dict(self) -> Dict[str, Any]:
        """Return a dict suitable for sending back to the API."""
        return dict(self.raw)

    def display_suffix(self) -> str:
        """Build a succinct suffix for names and IDs using description/IP/ports when available."""
        pieces: List[str] = []
        if self.description:
            pieces.append(self.description)
        # Add IP address info if present
        if self.ip_address:
            pieces.append(self.ip_address.replace("/", "_").replace(".", "_"))
        # Try to include port hints from filters if set to PORT or ADDRESS_AND_PORT
        def extract_port_label(f: NATAddressPortFilter | None) -> Optional[str]:
            if not f:
                return None
            if f.filter_type in ("PORT", "ADDRESS_AND_PORT"):
                # UniFi NAT filter payloads can include port lists; we don't have explicit fields here.
                # Keep naming conservative to avoid leaking too much detail; callers can extend later.
                return "port"
            return None

        pf = extract_port_label(self.destination_filter) or extract_port_label(self.source_filter)
        if pf:
            pieces.append(pf)

        # Fallback to ID hash segment if nothing else
        if not pieces:
            rid = self.id or "unknown"
            pieces.append(rid[:8])
        return "_".join(x for x in pieces if x)


