"""Utility functions for UniFi Network Rules."""
from typing import Any

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward

def get_rule_id(rule: Any) -> str | None:
    """Get the ID from a rule object with type prefix."""
    if isinstance(rule, TrafficRoute):
        return f"unr_route_{rule.id}"
    if isinstance(rule, FirewallPolicy):
        return f"unr_policy_{rule.id}"
    if isinstance(rule, TrafficRule):
        return f"unr_rule_{rule.id}"
    if isinstance(rule, PortForward):
        return f"unr_pf_{rule.id}"
    if isinstance(rule, dict):
        _id = rule.get("_id")
        # Optionally, use a type from the dict if available
        type_prefix = rule.get("type", "unknown")
        return f"unr_{type_prefix}_{_id}" if _id is not None else None
    return None

def get_rule_name(rule: Any) -> str | None:
    """Get the descriptive name from a rule object."""
    if isinstance(rule, TrafficRoute):
        return f"Network Route {rule.description}"
    if isinstance(rule, FirewallPolicy):
        return f"Network {rule.action} Policy {rule.name}"
    if isinstance(rule, TrafficRule):
        return f"Network {rule.action} Rule {rule.description}"
    if isinstance(rule, PortForward):
        return f"Network Forward {rule.name} {rule.destination_port}:{rule.destination_port}"
    if isinstance(rule, dict):
        return rule.get("name") or rule.get("description")
    return None

def get_rule_enabled(rule: Any) -> bool:
    """Get the enabled state from a rule object."""
    if isinstance(rule, (TrafficRoute, FirewallPolicy, TrafficRule, PortForward)):
        return rule.enabled
    if isinstance(rule, dict):
        return rule.get("enabled", False)
    return False 