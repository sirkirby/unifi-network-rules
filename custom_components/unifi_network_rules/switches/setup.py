"""Setup functions and global tracking for UniFi Network Rules switches."""
from __future__ import annotations

import logging
from typing import Final, Set

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import DOMAIN
from ..coordinator import UnifiRuleUpdateCoordinator
from ..helpers.rule import get_rule_id, get_child_unique_id

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1
RULE_TYPES: Final = {
    "firewall_policies": "Firewall Policy",
    "traffic_rules": "Traffic Rule",
    "port_forwards": "Port Forward",
    "traffic_routes": "Traffic Route",
    "legacy_firewall_rules": "Legacy Firewall Rule",
    "qos_rules": "QoS Rule",
    "vpn_clients": "VPN Client",
    "vpn_servers": "VPN Server",
    "static_routes": "Static Route",
    "nat_rules": "NAT Rule"
}

# Track entities across the platform
_ENTITY_CACHE: Set[str] = set()

# Global registry to track created entity unique IDs
_CREATED_UNIQUE_IDS = set()


async def async_setup_platform(_hass: HomeAssistant, _config, _async_add_entities, _discovery_info=None):
    """Set up the UniFi Network Rules switch platform."""
    LOGGER.debug("Setting up switch platform for UniFi Network Rules")
    # This function will be called when the platform is loaded manually
    # Most functionality is handled through config_flow and config_entries
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up switches for UniFi Network Rules component."""
    from .firewall import UnifiFirewallPolicySwitch, UnifiLegacyFirewallRuleSwitch
    from .traffic_route import UnifiTrafficRuleSwitch, UnifiTrafficRouteSwitch, UnifiTrafficRouteKillSwitch
    from .static_route import UnifiStaticRouteSwitch
    from .network import UnifiWlanSwitch, UnifiNetworkSwitch
    from .port_profile import UnifiPortProfileSwitch
    from .port_forwarding import UnifiPortForwardSwitch
    from .nat import UnifiNATRuleSwitch
    from .vpn import UnifiVPNClientSwitch, UnifiVPNServerSwitch
    from .device import UnifiLedToggleSwitch
    from .qos import UnifiQoSRuleSwitch
    from .oon_policy import UnifiOONPolicySwitch, UnifiOONPolicyKillSwitch
    
    LOGGER.debug("Setting up UniFi Network Rules switches")

    coordinator: UnifiRuleUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    # known_unique_ids are now populated during __init__.py before first refresh
    # No need to repopulate or trigger additional refresh here
    LOGGER.debug("Using known_unique_ids populated during initialization: %d entries", 
                len(coordinator.known_unique_ids))

    # Initialize as empty, coordinator will manage it
    # Do NOT clear on reload, let coordinator handle sync

    # --- Store add_entities callback --- 
    LOGGER.debug("Setting async_add_entities callback on coordinator")
    coordinator.async_add_entities_callback = async_add_entities

    # --- Step 1: Gather all potential entities and their data ---
    potential_entities_data = {} # Map: unique_id -> {rule_data, rule_type, entity_class}

    all_rule_sources = [
        ("port_forwards", coordinator.port_forwards, UnifiPortForwardSwitch),
        ("traffic_routes", coordinator.traffic_routes, UnifiTrafficRouteSwitch),
        ("static_routes", coordinator.static_routes or [], UnifiStaticRouteSwitch),
        ("firewall_policies", coordinator.firewall_policies, UnifiFirewallPolicySwitch),
        ("traffic_rules", coordinator.traffic_rules, UnifiTrafficRuleSwitch),
        ("legacy_firewall_rules", coordinator.legacy_firewall_rules, UnifiLegacyFirewallRuleSwitch),
        ("qos_rules", coordinator.qos_rules, UnifiQoSRuleSwitch),
        ("wlans", coordinator.wlans, UnifiWlanSwitch),
        ("vpn_clients", coordinator.vpn_clients, UnifiVPNClientSwitch),
        ("vpn_servers", coordinator.vpn_servers, UnifiVPNServerSwitch),
        ("port_profiles", coordinator.port_profiles, UnifiPortProfileSwitch),
        # Networks are now pre-filtered in coordinator (no VPN, no default)
        ("networks", coordinator.networks or [], UnifiNetworkSwitch),
        ("nat_rules", coordinator.nat_rules or [], UnifiNATRuleSwitch),
        ("oon_policies", coordinator.oon_policies or [], UnifiOONPolicySwitch),
    ]

    for rule_type, rules, entity_class in all_rule_sources:
        if not rules: # Skip if no rules of this type
            continue
        for rule in rules:
            try:
                rule_id = get_rule_id(rule)
                if not rule_id:
                    LOGGER.error("Cannot process rule without ID: %s", rule)
                    continue

                # Add parent entity data if not already seen
                if rule_id not in potential_entities_data:
                    potential_entities_data[rule_id] = {
                        "rule_data": rule,
                        "rule_type": rule_type,
                        "entity_class": entity_class,
                    }
                    LOGGER.debug("Gathered potential entity: %s", rule_id)

                # Special handling for Traffic Routes: Add potential Kill Switch data
                if rule_type == "traffic_routes" and "kill_switch_enabled" in rule.raw:
                    kill_switch_id = get_child_unique_id(rule_id, "kill_switch")
                    if kill_switch_id not in potential_entities_data:
                        # Pass the PARENT rule data for the kill switch
                        potential_entities_data[kill_switch_id] = {
                            "rule_data": rule, # Use parent data
                            "rule_type": rule_type, # Still traffic_routes type
                            "entity_class": UnifiTrafficRouteKillSwitch,
                        }
                        LOGGER.debug("Gathered potential kill switch entity: %s (for parent %s)", kill_switch_id, rule_id)

                # Special handling for OON Policies: Add potential Kill Switch data
                if rule_type == "oon_policies":
                    from ..models.oon_policy import OONPolicy
                    if isinstance(rule, OONPolicy) and rule.has_kill_switch():
                        kill_switch_id = get_child_unique_id(rule_id, "kill_switch")
                        if kill_switch_id not in potential_entities_data:
                            # Pass the PARENT rule data for the kill switch
                            potential_entities_data[kill_switch_id] = {
                                "rule_data": rule, # Use parent data
                                "rule_type": rule_type, # Still oon_policies type
                                "entity_class": UnifiOONPolicyKillSwitch,
                            }
                            LOGGER.debug("Gathered potential kill switch entity: %s (for parent %s)", kill_switch_id, rule_id)

            except Exception as err:
                LOGGER.exception("Error processing rule during gathering phase: %s", str(err))

    # --- LED toggle switches ---
    LOGGER.debug("Checking for LED-capable devices...")
    if hasattr(coordinator, 'devices') and coordinator.devices:
        LOGGER.info("Found %d LED-capable devices in coordinator", len(coordinator.devices))
        for device in coordinator.devices:
            # Devices are already filtered by coordinator for LED capability
            unique_id = f"unr_device_{device.mac}_led"
            if unique_id not in potential_entities_data:
                potential_entities_data[unique_id] = {
                    "rule_data": device,
                    "rule_type": "devices",
                    "entity_class": UnifiLedToggleSwitch,
                }
                LOGGER.info("Gathered potential LED switch: %s for device %s", unique_id, getattr(device, 'name', device.mac))
    else:
        LOGGER.warning("No LED-capable devices found in coordinator. Coordinator devices: %s", getattr(coordinator, 'devices', 'NOT_SET'))

    # --- Step 2: Create entity instances for unique IDs ---
    switches_to_add = []
    processed_unique_ids = set()

    LOGGER.debug("Creating entity instances from %d potential entities...", len(potential_entities_data))
    for unique_id, data in potential_entities_data.items():
        try:
            # Prevent duplicate processing if somehow gathered twice
            if unique_id in processed_unique_ids:
                LOGGER.warning("Skipping already processed unique_id during instance creation: %s", unique_id)
                continue

            # Create the entity instance
            entity_class = data["entity_class"]
            entity = entity_class(
                coordinator,
                data["rule_data"],
                data["rule_type"],
                config_entry.entry_id
            )

            # Check if the created entity's unique_id matches the key (sanity check)
            if entity.unique_id != unique_id:
                LOGGER.error("Mismatch! Expected unique_id %s but created entity has %s. Skipping.", unique_id, entity.unique_id)
                continue

            switches_to_add.append(entity)
            processed_unique_ids.add(unique_id)
            LOGGER.debug("Created entity instance for %s", unique_id)

        except Exception as err:
            LOGGER.exception("Error creating entity instance for unique_id %s: %s", unique_id, str(err))

    # --- Step 3: Add the uniquely created entities ---
    if switches_to_add:
        LOGGER.debug("Adding %d newly created entity instances to Home Assistant", len(switches_to_add))
        async_add_entities(switches_to_add)

        # --- Update coordinator's known IDs --- 
        # Let the coordinator update known_unique_ids when dynamically adding
        # This prevents adding IDs during initial setup that might already be known from registry

        # Switch platform setup only runs during initial integration startup
        LOGGER.info("Initialized %d UniFi Network Rules switches", len(switches_to_add))
    else:
        # Switch platform setup only runs during initial integration startup  
        LOGGER.debug("No UniFi Network Rules switches to initialize in this run.")

