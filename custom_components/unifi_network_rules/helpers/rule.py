"""Helper functions for UniFi Network rule handling."""
from typing import Any
import logging
import re
import hashlib

from aiounifi.models.traffic_route import TrafficRoute
from aiounifi.models.firewall_policy import FirewallPolicy
from aiounifi.models.traffic_rule import TrafficRule
from aiounifi.models.port_forward import PortForward
from aiounifi.models.firewall_zone import FirewallZone
from aiounifi.models.wlan import Wlan

# Import our custom models
from ..models.firewall_rule import FirewallRule
from ..models.qos_rule import QoSRule
from ..models.vpn_config import VPNConfig
from ..const import DOMAIN

LOGGER = logging.getLogger(__name__)

# Define redundant terms as a module-level constant
ACTION_TERMS = ["Allow", "Block", "Drop", "Deny"]

def get_rule_enabled(rule: Any) -> bool:
    """Get the enabled status from a rule object.
    
    Args:
        rule: The rule object to check
        
    Returns:
        True if the rule is enabled, False otherwise
    """
    # Check different rule types and return appropriate enabled status
    if isinstance(rule, (PortForward, TrafficRoute, FirewallPolicy, TrafficRule, Wlan, QoSRule, VPNConfig)):
        return getattr(rule, "enabled", False)
    
    # For dictionaries, try common enabled attributes
    if isinstance(rule, dict):
        return rule.get("enabled", False)
    
    # For other types, try common attributes
    if hasattr(rule, "enabled"):
        return rule.enabled
    
    # Default to False if we can't determine
    return False

def remove_action_terms(name, action_terms):
    cleaned_name = name
    for term in action_terms:
        # re.IGNORECASE ensures case-insensitive matching
        cleaned_name = re.sub(re.escape(term), "", cleaned_name, flags=re.IGNORECASE).strip()
    return cleaned_name

def get_rule_id(rule: Any) -> str | None:
    """Get the consistent technical ID from a rule object with type prefix.
    
    This is used as a unique identifier for internal tracking and correlation.
    Unlike get_entity_id, this does NOT include any user-friendly name components.
    The format is simply: unr_<type>_<id>
    
    Examples: 
        - unr_policy_123456
        - unr_route_abcdef
    """
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
            
    if isinstance(rule, QoSRule):
        if hasattr(rule, 'id') and rule.id:
            return f"unr_qos_{rule.id}"
        else:
            LOGGER.warning("QoSRule without id attribute: %s", rule)
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
            LOGGER.warning("Wlan without id: %s", rule)
            return None
    
    if isinstance(rule, VPNConfig):
        if rule.id:
            # Different prefix for clients and servers
            if rule.is_client:
                return f"unr_vpn_client_{rule.id}"
            elif rule.is_server:
                return f"unr_vpn_server_{rule.id}"
            else:
                return f"unr_vpn_{rule.id}"
        else:
            LOGGER.warning("VPNConfig without id: %s", rule)
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

def get_rule_prefix(rule_type: str) -> str:
    """Get the prefix for a given rule type.
    
    Args:
        rule_type: The type of rule
        
    Returns:
        A prefix string for the rule type
    """
    rule_types = {
        "port_forwards": "Port Forward",
        "traffic_routes": "Traffic Route",
        "firewall_policies": "Policy",
        "traffic_rules": "Traffic Rule",
        "legacy_firewall_rules": "Legacy Rule",
        "qos_rules": "QoS",
        "wlans": "WLAN"
    }
    
    return rule_types.get(rule_type, "Rule")

def get_zone_name_by_id(coordinator, zone_id: str) -> str | None:
    """Get a zone name based on its ID.
    
    Args:
        coordinator: The UnifiRuleUpdateCoordinator instance
        zone_id: The zone ID to look up
        
    Returns:
        The zone name or None if not found
    """
    if not coordinator or not hasattr(coordinator, "firewall_zones"):
        return None
        
    for zone in coordinator.firewall_zones:
        if zone.id == zone_id:
            return zone.name
            
    return None

def extract_descriptive_name(rule: Any, coordinator=None) -> str | None:
    """Extract a descriptive name from the rule object.
    
    This function handles different rule types and extracts the most appropriate
    descriptive name from each.
    
    Args:
        rule: The rule object
        coordinator: Optional coordinator for additional context (zone lookups)
        
    Returns:
        The descriptive name, or None if no name could be extracted
    """
    if isinstance(rule, FirewallPolicy):
        # Get base name
        name = getattr(rule, "name", None) or getattr(rule, "description", None)
        
        # Try to enhance with source and destination zone information
        if coordinator is not None:
            try:
                source_zone_id = rule.source["zone_id"] if "zone_id" in rule.source else None
                dest_zone_id = rule.destination["zone_id"] if "zone_id" in rule.destination else None
                
                LOGGER.debug("Attempting to lookup zones - Source ID: %s, Dest ID: %s", 
                             source_zone_id, dest_zone_id)
                
                source_zone_name = get_zone_name_by_id(coordinator, source_zone_id)
                dest_zone_name = get_zone_name_by_id(coordinator, dest_zone_id)
                
                LOGGER.debug("Zone names - Source: %s, Dest: %s", 
                             source_zone_name, dest_zone_name)
                
                # Include zone information in name if both are available
                if source_zone_name and dest_zone_name:
                    action = rule.action.capitalize()
                    
                    # Helps us avoid redundant action terms in the name
                    cleaned_name = remove_action_terms(name, ACTION_TERMS)

                    if cleaned_name:
                        return f"{source_zone_name}->{dest_zone_name} {action} {cleaned_name}".strip()
                    else:
                        # failsafe in case we messed up the name extraction
                        return f"{source_zone_name}->{dest_zone_name} {action} {getattr(rule, "id", None)}".strip()
            except (AttributeError, KeyError) as err:
                # Log but continue with normal name extraction
                LOGGER.debug("Error extracting zone info for policy: %s", err)
        
        return name
        
    elif isinstance(rule, PortForward):
        # For port forwards, use the name directly
        name = getattr(rule, "name", None)
        if name:
            # Add source port (destination_port) and destination port (forward_port) information
            try:
                # Get the port information
                source_port = rule.destination_port
                dest_port = rule.forward_port
                
                # Include port information in the name
                if source_port and dest_port:
                    return f"{name} {source_port}->{dest_port}"
            except (AttributeError, KeyError) as err:
                # Log but continue with normal name extraction
                LOGGER.debug("Error extracting port info for port forward: %s", err)
            
            return name
        return None
        
    elif isinstance(rule, TrafficRoute):
        # For routes, use the description/name
        name = getattr(rule, "description", None) or getattr(rule, "name", None)
        if name:
            return name
        return None
        
    elif isinstance(rule, QoSRule):
        objective = rule.objective if hasattr(rule, "objective") else ""
        if rule.name:
            if objective and objective != "PRIORITIZE":
                return f"{rule.name} ({objective})"
            return rule.name
        return f"QoS Rule {rule.id}"
        
    elif isinstance(rule, FirewallZone):
        # For firewall zones, use the name
        name = getattr(rule, "name", None)
        if name:
            return name
        return None
        
    elif isinstance(rule, Wlan):
        # For wireless networks, use the name
        name = getattr(rule, "name", None)
        if name:
            return name
        return None
        
    elif isinstance(rule, VPNConfig):
        # For VPN configurations, use display_name property which handles different VPN types
        if hasattr(rule, "display_name"):
            return rule.display_name
        # Fallback to name or construct from properties
        name = getattr(rule, "name", None)
        if name:
            return name
        
        # Try to construct from VPN type and configuration
        vpn_type = getattr(rule, "vpn_type", "").replace("-client", "").replace("-server", "").upper()
        if vpn_type:
            # Add server/client distinction
            if rule.is_server:
                vpn_type = f"{vpn_type} Server"
            elif rule.is_client:
                vpn_type = f"{vpn_type} Client"
                
            if rule.id:
                return f"{vpn_type} VPN {rule.id}"
            return f"{vpn_type} VPN"
        
        return None
        
    elif isinstance(rule, dict):
        # For dictionaries, try common name attributes
        return rule.get("name") or rule.get("description")
        
    # For other types, try common attributes
    if hasattr(rule, "name"):
        return rule.name
    elif hasattr(rule, "description"):
        return rule.description
        
    return None

def get_rule_name(rule: Any, coordinator=None) -> str | None:
    """Get the descriptive name from a rule object."""
    # Try to determine the rule type
    rule_type = None
    
    if isinstance(rule, FirewallPolicy):
        rule_type = "firewall_policies"
    elif isinstance(rule, PortForward):
        rule_type = "port_forwards"
    elif isinstance(rule, TrafficRoute):
        rule_type = "traffic_routes"
    elif isinstance(rule, FirewallZone):
        rule_type = "firewall_zones"
    elif isinstance(rule, Wlan):
        rule_type = "wlans"
    elif isinstance(rule, QoSRule):
        rule_type = "qos_rules"
    elif isinstance(rule, dict) and "type" in rule:
        rule_type = rule.get("type")
    
    # Get the prefix based on rule type
    prefix = ""
    if rule_type:
        prefix = get_rule_prefix(rule_type)
    
    # Extract the descriptive name, passing the coordinator if available
    name = extract_descriptive_name(rule, coordinator)
    
    if name:
        # Return the full name with prefix
        return f"{prefix} {name}"
    elif hasattr(rule, "id"):
        # Fallback to ID if available
        return f"{prefix} {rule.id}"
    else:
        # No identifiable information available
        return None

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

def get_object_id(rule: Any, rule_type: str) -> str:
    """Get a consistent object ID for a rule, sanitized for Home Assistant.
    
    The object ID is the part of the entity ID after the domain.
    This is used when suggesting IDs to the entity registry.
    
    Args:
        rule: The rule object
        rule_type: The type of rule (e.g., 'firewall_policies')
        
    Returns:
        A consistent object ID in the format: unr_<type>_<descriptive_name>
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
    
    # Properly singularize rule type suffix
    if rule_type.endswith('ies'):
        # Handle special case for 'policies' → 'policy'
        rule_type_suffix = rule_type[:-3] + 'y'
    elif rule_type.endswith('s'):
        # Regular plural, just remove the 's'
        rule_type_suffix = rule_type[:-1]
    else:
        # Already singular
        rule_type_suffix = rule_type
    
    # Sanitize the rule type suffix
    rule_type_suffix = sanitize_entity_id(rule_type_suffix)
    
    # Extract the descriptive name directly
    descriptive_name = extract_descriptive_name(rule)
    
    # If we have a name, use it to create a descriptive entity ID
    if descriptive_name:
        # Sanitize the descriptive name
        sanitized_name = sanitize_entity_id(descriptive_name)
        
        # Format with descriptive name only: unr_<type>_<sanitized_descriptive_name>
        # No longer including the ID in the entity_id
        return f"unr_{rule_type_suffix}_{sanitized_name}"
    else:
        # Fallback to a simpler format when no name is available
        # We still need some unique identifier, so use a shortened hash of the ID
        short_id = hashlib.md5(str(rule_id).encode()).hexdigest()[:8]
        return f"unr_{rule_type_suffix}_{short_id}"

def get_entity_id(rule: Any, rule_type: str, domain: str = "switch") -> str:
    """Get a complete entity ID for a rule, including the domain.
    
    This builds a complete Home Assistant entity ID in the format:
    domain.unr_<type>_<descriptive_name>
    
    Args:
        rule: The rule object
        rule_type: The type of rule (e.g., 'firewall_policies')
        domain: The entity domain (default: 'switch')
        
    Returns:
        A complete entity ID including domain
    """
    # Get the object_id part
    object_id = get_object_id(rule, rule_type)
    
    # Combine with domain
    return f"{domain}.{object_id}"

def get_child_entity_name(parent_name: str, child_type: str) -> str:
    """Generate a standardized name for a child entity.
    
    Args:
        parent_name: The name of the parent entity
        child_type: The type of child entity (e.g., 'kill_switch')
        
    Returns:
        The standardized name for the child entity
    """
    # Map child types to their display names
    child_display_names = {
        "kill_switch": "Kill Switch",
        # Add more child types as they are implemented
    }
    
    # Get the display name for the child type
    child_display = child_display_names.get(child_type, child_type.replace("_", " ").title())
    
    # Return the combined name
    return f"{parent_name} {child_display}"

def get_child_entity_id(parent_id: str, child_type: str) -> str:
    """Generate a standardized entity ID suffix for a child entity.
    
    Args:
        parent_id: The entity ID of the parent entity
        child_type: The type of child entity (e.g., 'kill_switch')
        
    Returns:
        The standardized entity ID suffix for the child entity
    """
    # Sanitize the child type to be safe in entity IDs
    sanitized_child_type = sanitize_entity_id(child_type)
    
    # Return the combined ID
    return f"{parent_id}_{sanitized_child_type}"

def get_child_unique_id(parent_unique_id: str, child_type: str) -> str:
    """Generate a standardized unique ID for a child entity.
    
    Args:
        parent_unique_id: The unique ID of the parent entity
        child_type: The type of child entity (e.g., 'kill_switch')
        
    Returns:
        The standardized unique ID for the child entity
    """
    # Sanitize the child type to be safe in unique IDs
    sanitized_child_type = sanitize_entity_id(child_type)
    
    # Return the combined ID
    return f"{parent_unique_id}_{sanitized_child_type}"

def is_our_entity(entity_entry, domain=DOMAIN) -> bool:
    """Reliably identify if an entity entry belongs to this integration.
    
    This function uses the entity registry entry properties that cannot
    be changed by users, making it more reliable than entity_id checks.
    
    Args:
        entity_entry: The entity registry entry to check
        domain: The domain to check against (default: DOMAIN constant)
        
    Returns:
        True if the entity belongs to this integration, False otherwise
    """
    # Check if entity's platform matches our domain
    # This property cannot be changed by users
    return entity_entry.platform == domain