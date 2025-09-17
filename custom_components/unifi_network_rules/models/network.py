"""Typed model for UniFi network (networkconf) entries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class NetworkConf:
    raw: Dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.raw.get("_id") or self.raw.get("id") or "")

    @property
    def name(self) -> str:
        return str(self.raw.get("name") or self.raw.get("attr_hidden_id") or f"Network {self.id}")

    @property
    def purpose(self) -> str:
        return str(self.raw.get("purpose") or "")

    @property
    def enabled(self) -> bool:
        # Some networkconfs may not have enabled; treat presence of ip_subnet or WAN purpose as enabled
        if "enabled" in self.raw:
            return bool(self.raw.get("enabled"))
        return True
