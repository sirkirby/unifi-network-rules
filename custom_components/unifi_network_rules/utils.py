"""Utility functions for UniFi Network Rules."""
from typing import Any

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward

def get_rule_id(rule: Any) -> str | None:
    """Get the ID from a rule object."""
    if isinstance(rule, TrafficRoute):
        return rule.id
    if isinstance(rule, (FirewallPolicy, TrafficRule, PortForward)):
        return getattr(rule, "id", None)
    if isinstance(rule, dict):
        return rule.get("_id")
    return None

def get_rule_name(rule: Any) -> str | None:
    """Get the name/description from a rule object."""
    if isinstance(rule, TrafficRoute):
        return rule.description
    if isinstance(rule, (FirewallPolicy, TrafficRule, PortForward)):
        return getattr(rule, "name", None) or getattr(rule, "description", None)
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