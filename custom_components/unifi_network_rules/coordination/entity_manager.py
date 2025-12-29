"""Entity management module for UniFi Network Rules coordinator.

Handles entity discovery, creation, deletion, and lifecycle management.
Consolidates complex entity tracking logic into a focused, maintainable module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from ..const import DOMAIN, LOGGER
from ..helpers.rule import get_child_unique_id, get_rule_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class CoordinatorEntityManager:
    """Manages entity lifecycle for the coordinator."""

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        """Initialize the entity manager.

        Args:
            hass: Home Assistant instance
            coordinator: Reference to parent coordinator
        """
        self.hass = hass
        self.coordinator = coordinator

        # Define entity type to entity class mapping for discovery
        self._rule_type_entity_map = [
            ("port_forwards", "UnifiPortForwardSwitch"),
            ("traffic_rules", "UnifiTrafficRuleSwitch"),
            ("firewall_policies", "UnifiFirewallPolicySwitch"),
            ("traffic_routes", "UnifiTrafficRouteSwitch"),
            ("static_routes", "UnifiStaticRouteSwitch"),
            ("nat_rules", "UnifiNATRuleSwitch"),
            ("legacy_firewall_rules", "UnifiLegacyFirewallRuleSwitch"),
            ("qos_rules", "UnifiQoSRuleSwitch"),
            ("wlans", "UnifiWlanSwitch"),
            ("port_profiles", "UnifiPortProfileSwitch"),
            ("networks", "UnifiNetworkSwitch"),
            ("vpn_clients", "UnifiVPNClientSwitch"),
            ("vpn_servers", "UnifiVPNServerSwitch"),
            ("oon_policies", "UnifiOONPolicySwitch"),
        ]

    async def discover_and_add_new_entities(self, new_data: dict[str, list[Any]]) -> None:
        """Discover new rules from fetched data and dynamically add corresponding entities.

        Args:
            new_data: The newly fetched data from API
        """
        LOGGER.debug(
            "Entity discovery called - callback set: %s, initial_update_done: %s",
            bool(self.coordinator.async_add_entities_callback),
            self.coordinator._initial_update_done,
        )

        if not self.coordinator.async_add_entities_callback:
            LOGGER.warning("Cannot add entities: callback not set (this is normal during initial setup)")
            return

        # Import entity classes dynamically to avoid circular imports
        entity_classes = self._import_entity_classes()

        # Gather potential entities from the NEW data
        potential_entities_data = {}  # Map: unique_id -> {rule_data, rule_type, entity_class}
        all_current_unique_ids = set()  # Keep track of all IDs found in this run

        # Process standard entity types
        for rule_type_key, entity_class_name in self._rule_type_entity_map:
            entity_class = entity_classes.get(entity_class_name)
            if not entity_class:
                LOGGER.warning("Could not find entity class: %s", entity_class_name)
                continue

            rules = new_data.get(rule_type_key, [])
            if not rules:
                continue

            await self._process_entity_type_for_discovery(
                rules, rule_type_key, entity_class, potential_entities_data, all_current_unique_ids
            )

        # Special handling for LED-capable devices
        await self._process_devices_for_discovery(
            new_data.get("devices", []),
            entity_classes.get("UnifiLedToggleSwitch"),
            potential_entities_data,
            all_current_unique_ids,
        )

        # Clean up stale known IDs that are no longer present
        await self._cleanup_stale_known_ids(all_current_unique_ids)

        # Create and add new entities
        await self._create_and_add_entities(potential_entities_data, entity_classes)

    async def _process_entity_type_for_discovery(
        self,
        rules: list[Any],
        rule_type_key: str,
        entity_class: type,
        potential_entities_data: dict[str, dict[str, Any]],
        all_current_unique_ids: set[str],
    ) -> None:
        """Process a specific entity type for discovery."""
        entity_registry = async_get_entity_registry(self.hass)

        for rule in rules:
            try:
                rule_id = get_rule_id(rule)
                if not rule_id:
                    continue

                all_current_unique_ids.add(rule_id)

                # Only consider if not already known and not already in HA registry
                if rule_id not in self.coordinator.known_unique_ids:
                    existing_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, rule_id)

                    if existing_entity_id:
                        # Entity exists in registry but not in tracking - add to known_unique_ids
                        LOGGER.debug("Found existing entity in registry: %s, adding to tracking", rule_id)
                        self.coordinator.known_unique_ids.add(rule_id)
                    else:
                        # Truly new entity - add to potential creation list
                        potential_entities_data[rule_id] = {
                            "rule_data": rule,
                            "rule_type": rule_type_key,
                            "entity_class": entity_class,
                        }
                        LOGGER.debug("Discovered potential new entity: %s (%s)", rule_id, rule_type_key)

                # Special handling for Traffic Routes Kill Switch
                if rule_type_key == "traffic_routes" and hasattr(rule, "raw") and "kill_switch_enabled" in rule.raw:
                    kill_switch_id = get_child_unique_id(rule_id, "kill_switch")
                    all_current_unique_ids.add(kill_switch_id)

                    if kill_switch_id not in self.coordinator.known_unique_ids:
                        existing_kill_switch = entity_registry.async_get_entity_id("switch", DOMAIN, kill_switch_id)

                        if existing_kill_switch:
                            LOGGER.debug(
                                "Found existing kill switch in registry: %s, adding to tracking", kill_switch_id
                            )
                            self.coordinator.known_unique_ids.add(kill_switch_id)
                        else:
                            # Import kill switch class
                            kill_switch_class = self._import_entity_classes().get("UnifiTrafficRouteKillSwitch")
                            if kill_switch_class:
                                potential_entities_data[kill_switch_id] = {
                                    "rule_data": rule,  # Parent data
                                    "rule_type": rule_type_key,
                                    "entity_class": kill_switch_class,
                                }
                                LOGGER.debug(
                                    "Discovered potential new kill switch: %s (for parent %s)", kill_switch_id, rule_id
                                )

            except Exception as err:
                LOGGER.warning("Error processing rule during discovery: %s", err)

    async def _process_devices_for_discovery(
        self,
        devices: list[Any],
        led_switch_class: type,
        potential_entities_data: dict[str, dict[str, Any]],
        all_current_unique_ids: set[str],
    ) -> None:
        """Process LED-capable devices for discovery."""
        if not devices or not led_switch_class:
            return

        entity_registry = async_get_entity_registry(self.hass)

        for device in devices:
            try:
                device_unique_id = f"unr_device_{device.mac}_led"
                all_current_unique_ids.add(device_unique_id)

                if device_unique_id not in self.coordinator.known_unique_ids:
                    existing_led_switch = entity_registry.async_get_entity_id("switch", DOMAIN, device_unique_id)

                    if existing_led_switch:
                        LOGGER.debug("Found existing LED switch in registry: %s, adding to tracking", device_unique_id)
                        self.coordinator.known_unique_ids.add(device_unique_id)
                    else:
                        potential_entities_data[device_unique_id] = {
                            "rule_data": device,
                            "rule_type": "devices",
                            "entity_class": led_switch_class,
                        }
                        LOGGER.debug("Discovered potential new LED switch: %s", device_unique_id)
            except Exception as err:
                LOGGER.warning("Error processing device during discovery: %s", err)

    async def _cleanup_stale_known_ids(self, all_current_unique_ids: set[str]) -> None:
        """Remove known IDs that are no longer present in current data."""
        stale_known_ids = self.coordinator.known_unique_ids - all_current_unique_ids
        if stale_known_ids:
            LOGGER.debug("Found %d known IDs no longer present in current data.", len(stale_known_ids))
            self.coordinator.known_unique_ids -= stale_known_ids
            for stale_id in stale_known_ids:
                LOGGER.info("Forcibly removing stale ID from tracking: %s", stale_id)
                self.hass.async_create_task(self._remove_entity_async(stale_id))

    async def _create_and_add_entities(
        self, potential_entities_data: dict[str, dict[str, Any]], entity_classes: dict[str, type]
    ) -> None:
        """Create and add new entities to Home Assistant."""
        if not potential_entities_data:
            LOGGER.debug("No new entities discovered.")
            return

        LOGGER.debug("Creating instances for %d discovered potential new entities...", len(potential_entities_data))

        entities_to_add = []
        added_ids_this_run = set()
        entity_map = {}  # Store created entities to link parents/children

        # Create entity instances
        for unique_id, data in potential_entities_data.items():
            if unique_id in self.coordinator.known_unique_ids or unique_id in added_ids_this_run:
                LOGGER.warning("Skipping entity creation for %s as it's already known or added.", unique_id)
                continue

            try:
                entity_class = data["entity_class"]
                entity = entity_class(
                    self.coordinator,  # Pass coordinator
                    data["rule_data"],
                    data["rule_type"],
                    self.coordinator.config_entry.entry_id if self.coordinator.config_entry else None,
                )

                # Sanity check unique ID
                if entity.unique_id != unique_id:
                    LOGGER.error(
                        "Mismatch! Expected unique_id %s but created entity has %s. Skipping.",
                        unique_id,
                        entity.unique_id,
                    )
                    continue

                entities_to_add.append(entity)
                added_ids_this_run.add(unique_id)
                entity_map[unique_id] = entity
                LOGGER.debug("Created new entity instance for %s", unique_id)

            except Exception as err:
                LOGGER.error("Error creating new entity instance for unique_id %s: %s", unique_id, err)

        # Establish parent/child links for newly created entities
        await self._establish_parent_child_links(entity_map, entity_classes)

        # Add entities to Home Assistant
        if entities_to_add:
            await self._add_entities_to_home_assistant(entities_to_add, added_ids_this_run)
        else:
            LOGGER.debug("No new entities to add dynamically in this cycle.")

    async def _establish_parent_child_links(self, entity_map: dict[str, Any], entity_classes: dict[str, type]) -> None:
        """Establish parent/child relationships for newly created entities."""
        if not entity_map:
            return

        LOGGER.debug("Establishing parent/child links for %d newly created entities...", len(entity_map))

        kill_switch_class = entity_classes.get("UnifiTrafficRouteKillSwitch")
        route_switch_class = entity_classes.get("UnifiTrafficRouteSwitch")

        for unique_id, entity in entity_map.items():
            # If it's a kill switch, find its parent
            if kill_switch_class and isinstance(entity, kill_switch_class) and hasattr(entity, "linked_parent_id"):
                parent_id = entity.linked_parent_id
                parent_entity = entity_map.get(parent_id)

                # If parent wasn't created in this run, look it up in Home Assistant
                if not parent_entity:
                    parent_entity_id_in_hass = None
                    registry = async_get_entity_registry(self.hass)
                    if registry:
                        parent_entity_id_in_hass = registry.async_get_entity_id("switch", DOMAIN, parent_id)
                    if parent_entity_id_in_hass:
                        parent_entity_state = self.hass.states.get(parent_entity_id_in_hass)
                        if parent_entity_state:
                            LOGGER.debug("Found parent entity '%s' state for kill switch", parent_entity_id_in_hass)
                            entity.parent_entity_id = parent_entity_id_in_hass
                            LOGGER.debug("Linked new child %s to parent state %s", unique_id, parent_entity_id_in_hass)
                        else:
                            LOGGER.warning(
                                "Could not find parent entity state %s for new kill switch %s", parent_id, unique_id
                            )

                if parent_entity and route_switch_class and isinstance(parent_entity, route_switch_class):
                    parent_entity.register_child_entity(unique_id)
                    entity.register_parent_entity(parent_id)
                    LOGGER.debug("Linked new child %s to parent %s", unique_id, parent_id)
                elif not parent_entity:
                    LOGGER.warning("Could not find parent entity %s for new kill switch %s", parent_id, unique_id)

    async def _add_entities_to_home_assistant(self, entities_to_add: list[Any], added_ids_this_run: set[str]) -> None:
        """Add entities to Home Assistant and update tracking."""
        LOGGER.info("Dynamically adding %d new entities to Home Assistant.", len(entities_to_add))

        try:
            if self.coordinator.async_add_entities_callback:
                try:
                    self.coordinator.async_add_entities_callback(entities_to_add)
                except TypeError as te:
                    LOGGER.error("async_add_entities_callback is not callable: %s", te)
                    return
            else:
                LOGGER.error("async_add_entities_callback is not set, cannot add entities")
                return

            # Update known IDs after successful addition
            self.coordinator.known_unique_ids.update(added_ids_this_run)
            LOGGER.debug(
                "Added %d new IDs to known_unique_ids (Total: %d)",
                len(added_ids_this_run),
                len(self.coordinator.known_unique_ids),
            )

        except Exception as add_err:
            LOGGER.error("Failed to dynamically add entities: %s", add_err)

    def check_for_deleted_rules(self, new_data: dict[str, list[Any]]) -> None:
        """Check for rules previously known but not in the new data, and trigger their removal.

        Args:
            new_data: The current data from API fetch
        """
        # Safety checks - prevent premature deletion
        if not self.coordinator._initial_update_done or not self.coordinator.known_unique_ids:
            LOGGER.debug(
                "Skipping deletion check: Initial update done=%s, Known IDs=%s",
                self.coordinator._initial_update_done,
                bool(self.coordinator.known_unique_ids),
            )
            return

        LOGGER.debug(
            "Starting deletion check against known_unique_ids (current size: %d)",
            len(self.coordinator.known_unique_ids),
        )

        current_known_ids = set(self.coordinator.known_unique_ids)  # Take a snapshot

        # Gather ALL unique IDs present in the new data
        all_current_unique_ids = set()
        all_rule_sources_types = [
            "port_forwards",
            "traffic_routes",
            "static_routes",
            "nat_rules",
            "firewall_policies",
            "traffic_rules",
            "legacy_firewall_rules",
            "qos_rules",
            "wlans",
            "vpn_clients",
            "vpn_servers",
            "port_profiles",
            "networks",
        ]

        for rule_type in all_rule_sources_types:
            rules = new_data.get(rule_type, [])
            if rules:
                for rule in rules:
                    try:
                        rule_id = get_rule_id(rule)
                        if rule_id:
                            all_current_unique_ids.add(rule_id)
                            # Add kill switch ID if applicable
                            if (
                                rule_type == "traffic_routes"
                                and hasattr(rule, "raw")
                                and "kill_switch_enabled" in rule.raw
                            ):
                                kill_switch_id = get_child_unique_id(rule_id, "kill_switch")
                                all_current_unique_ids.add(kill_switch_id)
                    except Exception as e:
                        LOGGER.warning("Error getting ID during deletion check for %s: %s", rule_type, e)

        # Special handling for device LED switches
        devices = new_data.get("devices", [])
        for device in devices:
            try:
                device_unique_id = f"unr_device_{device.mac}_led"
                all_current_unique_ids.add(device_unique_id)
            except Exception as e:
                LOGGER.warning("Error getting device ID during deletion check: %s", e)

        # Find IDs that are known but NOT in the current data
        deleted_unique_ids = current_known_ids - all_current_unique_ids
        LOGGER.debug(
            "Deletion Check: Known IDs: %d, Current IDs: %d, To Delete: %d",
            len(current_known_ids),
            len(all_current_unique_ids),
            len(deleted_unique_ids),
        )

        if deleted_unique_ids:
            self._process_deleted_rules("various_orphaned", deleted_unique_ids, len(self.coordinator.known_unique_ids))
        else:
            LOGGER.debug("Deletion check: No discrepancies found between known IDs and current data.")

    def _process_deleted_rules(self, rule_type: str, deleted_ids: set, total_previous_count: int) -> None:
        """Process detected rule deletions and dispatch removal events.

        Args:
            rule_type: The type of rule being processed
            deleted_ids: Set of rule IDs that were detected as deleted
            total_previous_count: Total number of rules in the previous update
        """
        if not deleted_ids:
            return

        # If removing too many entities at once, this might be an API glitch
        if len(deleted_ids) > 5 and len(deleted_ids) > total_previous_count * 0.25:  # More than 25%
            LOGGER.warning(
                "Large number of %s deletions detected (%d of %d, %.1f%%). "
                "This could be an API connection issue rather than actual deletions.",
                rule_type,
                len(deleted_ids),
                total_previous_count,
                (len(deleted_ids) / total_previous_count) * 100,
            )
            # For major deletions, only process a few at a time to be cautious
            if len(deleted_ids) > 10:
                LOGGER.warning("Processing only first 5 deletions to prevent mass removal during potential API issues")
                deleted_ids_subset = list(deleted_ids)[:5]
                LOGGER.info("Processing subset of deletions: %s", deleted_ids_subset)
                deleted_ids = set(deleted_ids_subset)

        LOGGER.info("Found %d deleted %s rules: %s", len(deleted_ids), rule_type, sorted(list(deleted_ids)))

        # Dispatch deletion events for each deleted rule
        for rule_id in deleted_ids:
            self.hass.async_create_task(self._remove_entity_async(rule_id))

    async def _remove_entity_async(self, unique_id: str) -> None:
        """Asynchronously remove an entity by its unique ID using direct registry removal.

        Args:
            unique_id: The unique ID of the entity to remove
        """
        LOGGER.debug("Attempting asynchronous removal for unique_id: %s", unique_id)

        # 1. Remove from coordinator tracking IMMEDIATELY
        if hasattr(self.coordinator, "known_unique_ids"):
            self.coordinator.known_unique_ids.discard(unique_id)
            LOGGER.debug("Removed unique_id '%s' from coordinator known_unique_ids.", unique_id)

        # 2. Find the current entity_id using the unique_id
        entity_registry = async_get_entity_registry(self.hass)
        if not entity_registry:
            LOGGER.warning("Could not get entity registry for removal of %s", unique_id)
            return

        entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, unique_id)

        # 3. Remove directly from the entity registry if entity_id found
        if entity_id:
            LOGGER.debug(
                "Found current entity_id '%s' for unique_id '%s'. Proceeding with registry removal.",
                entity_id,
                unique_id,
            )

            # Perform the removal
            if entity_registry.async_get(entity_id):  # Check if it still exists before removing
                try:
                    entity_registry.async_remove(entity_id)
                    LOGGER.info("Successfully removed entity %s (unique_id: %s) from registry.", entity_id, unique_id)
                except Exception as reg_err:
                    LOGGER.error("Error removing entity %s from registry: %s", entity_id, reg_err)
            else:
                LOGGER.debug("Entity %s already removed from registry.", entity_id)
        else:
            LOGGER.warning("Could not find entity_id for unique_id '%s' in registry. Cannot remove.", unique_id)

    def _import_entity_classes(self) -> dict[str, type]:
        """Import entity classes dynamically to avoid circular imports.

        Returns:
            Dictionary mapping class names to their actual classes
        """
        try:
            from ..switches import (
                UnifiFirewallPolicySwitch,
                UnifiLedToggleSwitch,
                UnifiLegacyFirewallRuleSwitch,
                UnifiNATRuleSwitch,
                UnifiNetworkSwitch,
                UnifiOONPolicySwitch,
                UnifiPortForwardSwitch,
                UnifiPortProfileSwitch,
                UnifiQoSRuleSwitch,
                UnifiStaticRouteSwitch,
                UnifiTrafficRouteKillSwitch,
                UnifiTrafficRouteSwitch,
                UnifiTrafficRuleSwitch,
                UnifiVPNClientSwitch,
                UnifiVPNServerSwitch,
                UnifiWlanSwitch,
            )

            return {
                "UnifiPortForwardSwitch": UnifiPortForwardSwitch,
                "UnifiTrafficRuleSwitch": UnifiTrafficRuleSwitch,
                "UnifiFirewallPolicySwitch": UnifiFirewallPolicySwitch,
                "UnifiTrafficRouteSwitch": UnifiTrafficRouteSwitch,
                "UnifiLegacyFirewallRuleSwitch": UnifiLegacyFirewallRuleSwitch,
                "UnifiQoSRuleSwitch": UnifiQoSRuleSwitch,
                "UnifiWlanSwitch": UnifiWlanSwitch,
                "UnifiTrafficRouteKillSwitch": UnifiTrafficRouteKillSwitch,
                "UnifiLedToggleSwitch": UnifiLedToggleSwitch,
                "UnifiStaticRouteSwitch": UnifiStaticRouteSwitch,
                "UnifiNATRuleSwitch": UnifiNATRuleSwitch,
                "UnifiPortProfileSwitch": UnifiPortProfileSwitch,
                "UnifiNetworkSwitch": UnifiNetworkSwitch,
                "UnifiVPNClientSwitch": UnifiVPNClientSwitch,
                "UnifiVPNServerSwitch": UnifiVPNServerSwitch,
                "UnifiOONPolicySwitch": UnifiOONPolicySwitch,
            }
        except ImportError as err:
            LOGGER.error("Failed to import entity classes: %s", err)
            return {}
