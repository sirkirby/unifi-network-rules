"""ID parsing helpers for UniFi Network Rules services."""
from __future__ import annotations

from typing import Tuple, Optional
import logging

LOGGER = logging.getLogger(__name__)


def parse_rule_id(rule_id: str, rule_type: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """Parse and normalize rule ID from trigger.rule_id or legacy formats.
    
    Primary usage: Pass through raw UniFi IDs from trigger.rule_id (fastest).
    Legacy support: Parse entity IDs for backward compatibility (slower).
    
    Args:
        rule_id: UniFi rule ID (preferably from trigger.rule_id)
        rule_type: Optional rule type (if not provided, will try to auto-detect)
        
    Returns:
        Tuple of (unifi_id, detected_rule_type)
    """
    if not rule_id:
        return "", None
        
    original_rule_id = rule_id
    detected_rule_type = rule_type  # Start with provided type
    
    LOGGER.debug("[ID_PARSER] Parsing rule_id: %s (provided_type: %s)", rule_id, rule_type)
    
    # Fast path: If it looks like a raw UniFi ID (no dots/prefixes), use it directly
    if not ('.' in rule_id or rule_id.startswith('unr_')):
        LOGGER.debug("[ID_PARSER] Fast path - detected raw UniFi ID: %s", rule_id)
        return rule_id, detected_rule_type
    
    # Step 1: Strip entity domain prefix if present
    if rule_id.startswith("switch."):
        rule_id = rule_id[7:]  # Remove "switch." prefix
        LOGGER.debug("[ID_PARSER] Stripped entity domain prefix, now: %s", rule_id)
    
    # Step 2: Extract the real UniFi ID from our prefixed format
    if "_" in rule_id and rule_id.startswith("unr_"):
        # Split into at least 3 parts: unr + type_hint + unifi_id
        # For multi-part type hints like "vpn_client", we need to be smarter
        parts = rule_id.split("_")
        if len(parts) >= 3 and parts[0] == "unr":
            # Last part is always the UniFi ID (24-char hex or similar)
            real_unifi_id = parts[-1]
            # Everything between "unr" and the last part is the type hint
            extracted_type_hint = "_".join(parts[1:-1])  # e.g., "vpn_client"
            
            LOGGER.debug("[ID_PARSER] Extracted UniFi ID: %s, type hint: %s", real_unifi_id, extracted_type_hint)
            
            # If no rule_type was provided, auto-detect from type hint
            if not detected_rule_type:
                detected_rule_type = get_rule_type_from_hint(extracted_type_hint)
                LOGGER.debug("[ID_PARSER] Auto-detected rule_type: %s (from hint: %s)", detected_rule_type, extracted_type_hint)
            
            rule_id = real_unifi_id
    
    LOGGER.debug("[ID_PARSER] Final result - UniFi ID: %s, rule_type: %s", rule_id, detected_rule_type)
    return rule_id, detected_rule_type


def get_rule_type_from_hint(type_hint: str) -> str:
    """Convert type hint from entity unique ID to service rule type.
    
    Args:
        type_hint: Type hint from unique ID (e.g., "vpn_client")
        
    Returns:
        Service rule type (e.g., "vpn_clients")
    """
    type_mapping = {
        "vpn_client": "vpn_clients",
        "vpn_server": "vpn_servers", 
        "firewall_policy": "firewall_policies",
        "traffic_route": "traffic_routes",
        "port_forward": "port_forwards",
        "traffic_rule": "traffic_rules",
        "legacy_firewall_rule": "legacy_firewall_rules",
        "firewall_zone": "firewall_zones",
        "qos_rule": "qos_rules",
        "wlan": "wlans",
        "device": "devices",
        "port_profile": "port_profiles",
        "network": "networks",
        # Fallback mappings for edge cases
        "vpn": "vpn_clients",  # Default VPN fallback to clients
        "zone": "firewall_zones",  # Firewall zone fallback
    }
    
    result = type_mapping.get(type_hint, type_hint)
    LOGGER.debug("[ID_PARSER] Type hint mapping: %s → %s", type_hint, result)
    return result


def validate_rule_type(rule_type: str) -> bool:
    """Validate that a rule type is supported by services.
    
    Args:
        rule_type: The rule type to validate
        
    Returns:
        True if the rule type is supported
    """
    supported_types = {
        "firewall_policies",
        "traffic_rules", 
        "port_forwards",
        "traffic_routes",
        "legacy_firewall_rules",
        "qos_rules",
        "wlans",
        "vpn_clients",
        "vpn_servers",
        "port_profiles",
        "networks",
        "devices"
    }
    
    return rule_type in supported_types


def generate_entity_id_from_rule(rule_id: str, rule_type: str) -> str:
    """Generate entity ID from UniFi rule ID and type.
    
    This is the inverse of parse_rule_id - creates entity ID from components.
    
    Args:
        rule_id: Clean UniFi rule ID
        rule_type: Service rule type (e.g., "vpn_clients")
        
    Returns:
        Full entity ID (e.g., "switch.unr_vpn_client_6786d55a88d13a5ebfc7fc26")
    """
    # Convert service rule type back to hint
    hint_mapping = {
        "vpn_clients": "vpn_client",
        "vpn_servers": "vpn_server",
        "firewall_policies": "firewall_policy", 
        "traffic_routes": "traffic_route",
        "port_forwards": "port_forward",
        "traffic_rules": "traffic_rule",
        "legacy_firewall_rules": "legacy_firewall_rule",
        "firewall_zones": "firewall_zone",
        "qos_rules": "qos_rule",
        "wlans": "wlan",
        "devices": "device",
        "port_profiles": "port_profile",
        "networks": "network"
    }
    
    type_hint = hint_mapping.get(rule_type, rule_type)
    return f"switch.unr_{type_hint}_{rule_id}"
