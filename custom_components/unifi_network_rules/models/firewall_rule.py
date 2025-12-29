from dataclasses import dataclass
from typing import Any, Self, TypedDict

from aiounifi.models.api import ApiItem, ApiRequestV2


class TypedFirewallRule(TypedDict):
    """Traffic rule type definition."""

    _id: str
    action: str
    dst_address: str
    dst_firewallgroup_ids: list[str]
    dst_networkconf_id: str
    dst_networkconf_type: str
    enabled: bool
    icmp_typename: str
    ipsec: str
    logging: bool
    name: str
    protocol: str
    protocol_match_excepted: bool
    rule_index: int
    ruleset: str
    setting_preference: str
    site_id: str
    src_address: str
    src_firewallgroup_ids: list[str]
    src_mac_address: str
    src_networkconf_id: str
    src_networkconf_type: str
    state_established: bool
    state_invalid: bool
    state_new: bool
    state_related: bool


@dataclass
class FirewallRuleListRequest(ApiRequestV2):
    """Request object for firewall rule list."""

    @classmethod
    def create(cls) -> Self:
        """Create firewall rule request."""
        return cls(method="get", path="/firewall/rules", data=None)


@dataclass
class FirewallRuleEnableRequest(ApiRequestV2):
    """Request object for firewall rule enable."""

    @classmethod
    def create(cls, firewall_rule: TypedFirewallRule, enable: bool) -> Self:
        """Create firewall rule enable request."""
        firewall_rule["enabled"] = enable
        return cls(
            method="put",
            path=f"/firewall/rules/{firewall_rule['_id']}",
            data=firewall_rule,
        )


class FirewallRule(ApiItem):
    """Represent a firewall rule configuration."""

    raw: TypedFirewallRule

    @property
    def id(self) -> str:
        """ID of firewall rule."""
        return self.raw["_id"]

    @property
    def name(self) -> str:
        """Name given by user to firewall rule."""
        return self.raw["name"]

    @property
    def enabled(self) -> bool:
        """Is firewall rule enabled."""
        return self.raw["enabled"]

    @property
    def action(self) -> str:
        """What action is defined by this firewall rule."""
        return self.raw["action"]

    @property
    def ruleset(self) -> str:
        """What ruleset is this firewall rule part of."""
        return self.raw["ruleset"]

    @property
    def description(self) -> str:
        """Get the description or name if no description exists."""
        return self.raw.get("description", self.name)

    # Add helper method to standardize FirewallRule objects to be consistent with aiounifi behavior
    @staticmethod
    def ensure_complete_data(rule_data: dict[str, Any]) -> TypedFirewallRule:
        """Ensure the rule data has all required fields with defaults.

        This prevents errors when converting raw API data to FirewallRule objects.
        """
        # Create a base rule with default values for all required fields
        base_rule = {
            "_id": "",
            "action": "accept",
            "dst_address": "",
            "dst_firewallgroup_ids": [],
            "dst_networkconf_id": "",
            "dst_networkconf_type": "",
            "enabled": False,
            "icmp_typename": "",
            "ipsec": "",
            "logging": False,
            "name": "",
            "protocol": "all",
            "protocol_match_excepted": False,
            "rule_index": 0,
            "ruleset": "LAN_IN",
            "setting_preference": "",
            "site_id": "",
            "src_address": "",
            "src_firewallgroup_ids": [],
            "src_mac_address": "",
            "src_networkconf_id": "",
            "src_networkconf_type": "",
            "state_established": False,
            "state_invalid": False,
            "state_new": False,
            "state_related": False,
        }

        # Update with actual values from the rule_data
        for key, value in rule_data.items():
            base_rule[key] = value

        return base_rule
