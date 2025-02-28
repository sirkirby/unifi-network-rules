"""Helper functions for UniFi Network rule handling."""
from typing import Any
import logging

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward
from aiounifi.models.firewall_zone import FirewallZone
from aiounifi.models.wlan import Wlan

# Import our custom FirewallRule model
from ..models.firewall_rule import FirewallRule

LOGGER = logging.getLogger(__name__)

def get_rule_id(rule: Any) -> str | None:
    """Get the consistent ID from a rule object with type prefix."""
    # Handle properly typed objects
    if hasattr(rule, "id"):
        # Get the base ID from the object
        base_id = rule.id
        
        # Add the appropriate type prefix based on object type
        if isinstance(rule, TrafficRoute):
            return f"unr_route_{base_id}"
        if isinstance(rule, FirewallPolicy):
            return f"unr_policy_{base_id}"
        if isinstance(rule, TrafficRule):
            return f"unr_rule_{base_id}"
        if isinstance(rule, PortForward):
            return f"unr_pf_{base_id}"
        if isinstance(rule, FirewallRule):
            return f"unr_fw_{base_id}"
        if isinstance(rule, FirewallZone):
            return f"unr_zone_{base_id}"
        if isinstance(rule, Wlan):
            return f"unr_wlan_{base_id}"
        
        # Fallback for other typed objects with ID
        rule_type = type(rule).__name__
        LOGGER.warning(
            "Encountered unhandled typed object %s with ID %s - using generic prefix",
            rule_type,
            base_id
        )
        return f"unr_other_{base_id}"
        
    # Dictionary fallback - this should not happen with properly typed data
    if isinstance(rule, dict):
        _id = rule.get("_id")
        if _id is not None:
            # Log warning about untyped data
            LOGGER.warning(
                "Encountered dictionary instead of typed object: %s", 
                {k: v for k, v in rule.items() if k in ["_id", "type", "name"]}
            )
            type_prefix = rule.get("type", "unknown")
            return f"unr_{type_prefix}_{_id}"
    
    LOGGER.error("Rule object has no ID attribute or is not a recognized type: %s", type(rule))
    return None

def get_rule_name(rule: Any) -> str | None:
    """Get the descriptive name from a rule object."""
    # Common naming pattern for all rule types
    if hasattr(rule, "id"):
        # Build rule name based on object type
        if isinstance(rule, TrafficRoute):
            prefix = "Network Route"
            descriptor = getattr(rule, "description", None) or getattr(rule, "name", rule.id)
            return f"{prefix} {descriptor}"
            
        if isinstance(rule, FirewallPolicy):
            action = getattr(rule, "action", "").title()
            name = getattr(rule, "name", rule.id)
            return f"Network {action} Policy {name}"
            
        if isinstance(rule, TrafficRule):
            action = getattr(rule, "action", "").title()
            descriptor = getattr(rule, "description", None) or getattr(rule, "name", rule.id)
            return f"Network {action} Rule {descriptor}"
            
        if isinstance(rule, PortForward):
            name = getattr(rule, "name", "")
            src_port = getattr(rule, "source_port", "")
            dst_port = getattr(rule, "destination_port", "")
            ports = f"{src_port}:{dst_port}" if src_port and dst_port else ""
            return f"Network Forward {name} {ports}".strip()
            
        if isinstance(rule, FirewallRule):
            action = getattr(rule, "action", "").title()
            name = getattr(rule, "name", rule.id)
            return f"Network {action} Rule {name}"
            
        if isinstance(rule, FirewallZone):
            return f"Network Zone {getattr(rule, 'name', rule.id)}"
            
        if isinstance(rule, Wlan):
            return f"WLAN {getattr(rule, 'name', rule.id)}"
        
        # Fallback for other object types with common properties
        name = getattr(rule, "name", None)
        description = getattr(rule, "description", None)
        return name or description or f"Rule {rule.id}"
        
    # Dictionary fallback - this should not happen with properly typed data
    if isinstance(rule, dict):
        LOGGER.warning(
            "Encountered dictionary instead of typed object when getting rule name: %s", 
            {k: v for k, v in rule.items() if k in ["_id", "type", "name"]}
        )
        return rule.get("name") or rule.get("description")
        
    LOGGER.error("Rule object has no ID attribute or is not a recognized type: %s", type(rule))
    return None

def get_rule_enabled(rule: Any) -> bool:
    """Get the enabled state from a rule object."""
    # For properly typed objects
    if hasattr(rule, "enabled"):
        return rule.enabled
        
    # Dictionary fallback - this should not happen with properly typed data
    if isinstance(rule, dict):
        LOGGER.warning(
            "Encountered dictionary instead of typed object when checking enabled state: %s", 
            {k: v for k, v in rule.items() if k in ["_id", "type", "name"]}
        )
        return rule.get("enabled", False)
        
    LOGGER.error("Rule object has no enabled attribute or is not a recognized type: %s", type(rule))
    return False 