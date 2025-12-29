"""QoS rule model for UniFi Network Rules integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class QoSRuleDestination:
    """Destination configuration for QoS rules."""

    app_ids: list[int] = None
    matching_target: Literal["APP", "NETWORK", "PORT", "ANY"] = "ANY"
    port_matching_type: Literal["ANY", "RANGE", "LIST"] = "ANY"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QoSRuleDestination:
        """Create a QoSRuleDestination from a dictionary."""
        return cls(
            app_ids=data.get("app_ids", []),
            matching_target=data.get("matching_target", "ANY"),
            port_matching_type=data.get("port_matching_type", "ANY"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "matching_target": self.matching_target,
            "port_matching_type": self.port_matching_type,
        }
        if self.app_ids:
            result["app_ids"] = self.app_ids
        return result


@dataclass
class QoSRuleSource:
    """Source configuration for QoS rules."""

    matching_target: Literal["ANY", "NETWORK", "GROUP"] = "ANY"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QoSRuleSource:
        """Create a QoSRuleSource from a dictionary."""
        return cls(
            matching_target=data.get("matching_target", "ANY"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "matching_target": self.matching_target,
        }


@dataclass
class QoSRuleSchedule:
    """Schedule configuration for QoS rules."""

    mode: Literal["ALWAYS", "CUSTOM"] = "ALWAYS"
    repeat_on_days: list[str] = None
    time_all_day: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QoSRuleSchedule:
        """Create a QoSRuleSchedule from a dictionary."""
        return cls(
            mode=data.get("mode", "ALWAYS"),
            repeat_on_days=data.get("repeat_on_days", []),
            time_all_day=data.get("time_all_day", False),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mode": self.mode,
            "repeat_on_days": self.repeat_on_days or [],
            "time_all_day": self.time_all_day,
        }


class QoSRule:
    """Representation of a QoS routing rule."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize a QoS rule from raw data."""
        self.raw = data
        self._id = data.get("_id")
        self.enabled = data.get("enabled", False)
        self.name = data.get("name", "")
        self.objective = data.get("objective", "PRIORITIZE")
        self.index = data.get("index", 0)
        self.download_burst = data.get("download_burst", "OFF")
        self.upload_burst = data.get("upload_burst", "OFF")

        # Parse nested objects
        self.destination = QoSRuleDestination.from_dict(data.get("destination", {}))
        self.source = QoSRuleSource.from_dict(data.get("source", {}))
        self.schedule = QoSRuleSchedule.from_dict(data.get("schedule", {}))

    @property
    def id(self) -> str:
        """Get the ID of the QoS rule."""
        return self._id

    def to_dict(self) -> dict[str, Any]:
        """Convert the QoS rule to a dictionary for API requests."""
        result = {
            "_id": self._id,
            "enabled": self.enabled,
            "name": self.name,
            "objective": self.objective,
            "index": self.index,
            "download_burst": self.download_burst,
            "upload_burst": self.upload_burst,
            "destination": self.destination.to_dict(),
            "source": self.source.to_dict(),
            "schedule": self.schedule.to_dict(),
        }

        return result


class QoSRuleBatchToggleRequest:
    """Model for batch QoS rule toggle requests."""

    def __init__(self, rule_ids: list[str], enabled: bool) -> None:
        """Initialize the batch toggle request."""
        self.rule_ids = rule_ids
        self.enabled = enabled

    def to_dict(self) -> list[dict[str, Any]]:
        """Convert to API request payload."""
        return [{"_id": rule_id, "enabled": self.enabled} for rule_id in self.rule_ids]
