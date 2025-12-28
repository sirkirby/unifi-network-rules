"""Helper modules for UniFi Network Rules."""

# Re-export all helper functions from rule.py module
from .rule import (  # noqa
    get_rule_id,
    get_rule_name,
    get_rule_enabled,
    get_object_id,
    get_entity_id,
    is_our_entity,
    sanitize_entity_id,
    get_rule_prefix,
    get_zone_name_by_id,
    extract_descriptive_name,
    get_child_entity_name,
    get_child_entity_id,
    get_child_unique_id,
    is_vpn_network,
    is_default_network,
)
