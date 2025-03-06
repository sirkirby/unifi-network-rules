"""Helper functions for UniFi Network rule handling."""
from typing import Any
import logging
import re

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
    # Access different rule types and return appropriate ID with type prefix
    if isinstance(rule, PortForward):
        if hasattr(rule, 'id') and rule.id:
            return f"unr_pf_{rule.id}"
        else:
            LOGGER.warning("PortForward without id attribute: %s", rule)
            return None
    
    if isinstance(rule, TrafficRoute):
        if hasattr(rule, 'id') and rule.id:
            return f"unr_route_{rule.id}"
        else:
            LOGGER.warning("TrafficRoute without id attribute: %s", rule)
            return None
    
    if isinstance(rule, FirewallPolicy):
        if hasattr(rule, 'id') and rule.id:
            return f"unr_policy_{rule.id}"
        else:
            LOGGER.warning("FirewallPolicy without id attribute: %s", rule)
            return None
    
    if isinstance(rule, TrafficRule):
        if hasattr(rule, 'id') and rule.id:
            return f"unr_rule_{rule.id}"
        else:
            LOGGER.warning("TrafficRule without id attribute: %s", rule)
            return None

    if isinstance(rule, FirewallRule):
        if hasattr(rule, 'id') and rule.id:
            return f"unr_firewallrule_{rule.id}"
        else:
            LOGGER.warning("FirewallRule without id attribute: %s", rule)
            return None

    if isinstance(rule, FirewallZone):
        if hasattr(rule, 'id') and rule.id:
            return f"unr_zone_{rule.id}"
        else:
            LOGGER.warning("FirewallZone without id attribute: %s", rule)
            return None
    
    if isinstance(rule, Wlan):
        if hasattr(rule, 'id') and rule.id:
            return f"unr_wlan_{rule.id}"
        else:
            LOGGER.warning("Wlan without id attribute: %s", rule)
            return None
    
    # Dictionary fallback - this should not happen with properly typed data
    if isinstance(rule, dict):
        _id = rule.get("_id") or rule.get("id")
        if _id is not None:
            # Log warning about untyped data
            LOGGER.warning(
                "Encountered dictionary instead of typed object: %s", 
                {k: v for k, v in rule.items() if k in ["_id", "id", "type", "name"]}
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

def sanitize_entity_id(text: str) -> str:
    """Sanitize a string to be used as part of an entity ID.
    
    Follows Home Assistant entity ID requirements:
    - Contains only lowercase alphanumeric characters and underscores
    - Cannot start or end with underscore
    - Cannot have consecutive underscores
    """
    if not text:
        return ""
        
    # Convert to lowercase
    text = text.lower()
    
    # Replace apostrophes with empty string (finn's -> finns)
    text = text.replace("'", "")
    
    # Replace hyphens with underscores (traefik-80 -> traefik_80)
    text = text.replace("-", "_")
    
    # Replace all other non-alphanumeric characters with underscores
    text = re.sub(r'[^a-z0-9_]', '_', text)
    
    # Remove consecutive underscores
    text = re.sub(r'_{2,}', '_', text)
    
    # Remove leading and trailing underscores
    text = text.strip('_')
    
    # Ensure we have a valid result (fallback if empty after sanitization)
    if not text:
        return "unknown"
    
    return text

def get_entity_id(rule: Any, rule_type: str) -> str:
    """Get a consistent entity ID for a rule, sanitized for Home Assistant.
    
    This is the canonical source for generating entity IDs and should be used
    throughout the integration for consistency.
    """
    # Extract rule ID directly - this gives us the base ID like "123456789"
    rule_id = None
    if hasattr(rule, "id"):
        rule_id = rule.id
    elif isinstance(rule, dict) and ("id" in rule or "_id" in rule):
        rule_id = rule.get("id") or rule.get("_id")
    
    if not rule_id:
        # Fallback if we can't get a direct ID
        LOGGER.warning("Unable to get raw ID for rule: %s", rule)
        # Try to use the helper function as fallback
        full_rule_id = get_rule_id(rule)
        if full_rule_id and "_" in full_rule_id:
            # Extract the ID part from "unr_type_id"
            rule_id = full_rule_id.split("_", 2)[-1]
        else:
            # Last resort
            rule_id = "unknown"
    
    # Sanitize the rule type suffix
    rule_type_suffix = sanitize_entity_id(rule_type.rstrip('s'))
    
    # Sanitize the ID part
    sanitized_id = sanitize_entity_id(str(rule_id))
    
    # Form the entity ID with pattern: <rule_type>_<sanitized_id>
    # Use "unr" prefix for consistency with get_rule_id
    return f"unr_{rule_type_suffix}_{sanitized_id}"

def get_object_id(rule: Any, rule_type: str) -> str:
    """Get a consistent object ID for a rule.
    
    The object ID is the part of the entity ID after the domain.
    This is used when suggesting IDs to the entity registry.
    """
    # Get the entity ID directly from the canonical source
    # This now returns the pattern "unr_<rule_type>_<id>"
    return get_entity_id(rule, rule_type)

def get_full_entity_id(rule: Any, rule_type: str, domain: str = "switch") -> str:
    """Get the full entity ID including domain.
    
    This returns a complete entity ID in the format: domain.unr_rule-type_id
    For example: switch.unr_route_nas_to_fiber
    
    Args:
        rule: The rule object
        rule_type: The type of rule (traffic_routes, firewall_policies, etc.)
        domain: The domain to use, defaults to "switch"
        
    Returns:
        The full entity ID including domain
    """
    object_id = get_object_id(rule, rule_type)
    return f"{domain}.{object_id}"

def is_our_entity_id(entity_id: str) -> bool:
    """Check if an entity ID matches our naming pattern.
    
    This can be used to identify entities created by this integration,
    either by our custom pattern or by the legacy pattern.
    
    Args:
        entity_id: The entity ID to check
        
    Returns:
        True if the entity ID matches our pattern, False otherwise
    """
    # Check for our new entity ID pattern (unr_*)
    if "unr_" in entity_id:
        return True
    
    # Check for legacy pattern (network_*)
    # This helps with cleanup of old entities
    if "network_" in entity_id:
        # Do some additional checks to ensure it's really one of ours
        legacy_patterns = [
            "network_traffic_route_",
            "network_block_policy_",
            "network_forward_",
            "network_rule_"
        ]
        for pattern in legacy_patterns:
            if pattern in entity_id:
                return True
    
    return False 