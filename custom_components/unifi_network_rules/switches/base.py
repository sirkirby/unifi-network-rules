"""Base switch class for UniFi Network Rules integration."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo, EntityCategory, generate_entity_id
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN, MANUFACTURER, SWITCH_DELAYED_VERIFICATION_SLEEP_SECONDS
from ..coordinator import UnifiRuleUpdateCoordinator
from ..helpers.rule import (
    get_object_id,
    get_rule_enabled,
    get_rule_id,
    get_rule_name,
)
from ..services.constants import SIGNAL_ENTITIES_CLEANUP

LOGGER = logging.getLogger(__name__)

# Per-entity toggle debounce delay in seconds
# This prevents rapid toggles from queuing multiple operations
TOGGLE_DEBOUNCE_DELAY: float = 0.5


class UnifiRuleSwitch(CoordinatorEntity[UnifiRuleUpdateCoordinator], SwitchEntity):
    """Switch to enable/disable UniFi Network rules."""

    def __init__(
        self,
        coordinator: UnifiRuleUpdateCoordinator,
        rule_data: Any,
        rule_type: str,
        entry_id: str = None,
    ) -> None:
        """Initialize the rule switch."""
        super().__init__(coordinator)
        self._rule_data = rule_data
        self._rule_type = rule_type
        self._entry_id = entry_id
        # Set entity category as a configuration entity
        self.entity_category = EntityCategory.CONFIG

        # Get rule ID using helper function
        self._rule_id = get_rule_id(rule_data)
        if not self._rule_id:
            raise ValueError("Rule must have an ID")

        # Get rule name using helper function - rely entirely on rule.py for naming
        # Pass coordinator to get_rule_name to enable zone name lookups for FirewallPolicy objects
        self._attr_name = get_rule_name(rule_data, coordinator) or f"Rule {self._rule_id}"

        # Set unique_id to the rule ID directly - this is what the helper provides
        # This ensures consistency with how rules are identified throughout the integration
        self._attr_unique_id = self._rule_id

        # Get the object_id from our helper for consistency
        object_id = get_object_id(rule_data, rule_type)

        # Set the entity_id properly using generate_entity_id helper
        # This is the correct way to set a custom entity_id
        self.entity_id = generate_entity_id(f"{DOMAIN}.{{}}", object_id, hass=coordinator.hass)

        # Set has_entity_name to False to ensure the entity name is shown in UI
        self._attr_has_entity_name = False

        # Set default icon for all rule switches (can be overridden by subclasses)
        self._attr_icon = "mdi:toggle-switch"

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.api.host)},
            name="UniFi Network Rules",
            manufacturer=MANUFACTURER,
            model="UniFi Dream Machine",
        )

        # Enable optimistic updates for better UX
        self._attr_assumed_state = True
        self._optimistic_state = None
        self._optimistic_timestamp = 0  # Add timestamp for optimistic state
        self._optimistic_max_age = 5  # Maximum age in seconds for optimistic state
        self._operation_pending = False
        self._last_auth_failure_time = 0

        # Per-entity toggle debouncing
        # Stores the pending debounce timer handle and target state
        self._toggle_debounce_timer: asyncio.TimerHandle | None = None
        self._toggle_debounce_target_state: bool | None = None

        # Initialize linked entity tracking
        self._linked_parent_id = None  # Unique ID of parent entity, if any
        self._linked_child_ids = set()  # Set of unique IDs of child entities

        LOGGER.debug("Initialized entity instance for unique_id=%s, entity_id=%s", self._attr_unique_id, self.entity_id)

    @property
    def linked_parent_id(self) -> str | None:
        """Return the unique ID of the parent entity, if this is a child entity."""
        return self._linked_parent_id

    @property
    def linked_child_ids(self) -> set[str]:
        """Return the set of unique IDs of child entities."""
        return self._linked_child_ids

    def register_child_entity(self, child_unique_id: str) -> None:
        """Register a child entity with this entity."""
        self._linked_child_ids.add(child_unique_id)
        LOGGER.debug("Registered child entity %s with parent %s", child_unique_id, self._attr_unique_id)

    def register_parent_entity(self, parent_unique_id: str) -> None:
        """Register this entity as a child of the given parent."""
        self._linked_parent_id = parent_unique_id
        LOGGER.debug("Registered entity %s as child of %s", self._attr_unique_id, parent_unique_id)

    @staticmethod
    def establish_parent_child_relationship(parent: UnifiRuleSwitch, child: UnifiRuleSwitch) -> None:
        """Establish bidirectional parent-child relationship between two entities.

        Args:
            parent: The parent entity
            child: The child entity
        """
        parent.register_child_entity(child.unique_id)
        child.register_parent_entity(parent.unique_id)
        LOGGER.debug("Established parent-child relationship: %s → %s", parent.entity_id, child.entity_id)

    def clear_optimistic_state(self, force: bool = False) -> None:
        """Clear the optimistic state if it exists.

        Args:
            force: If True, force clearing regardless of timestamp
        """
        if self._optimistic_state is not None:
            if force:
                LOGGER.debug("Forcibly clearing optimistic state for %s", self._rule_id)
                self._optimistic_state = None
                self._optimistic_timestamp = 0
                self._operation_pending = False
            else:
                current_time = time.time()
                age = current_time - self._optimistic_timestamp
                if age > self._optimistic_max_age:
                    LOGGER.debug("Clearing optimistic state for %s (age: %.1f seconds)", self._rule_id, age)
                    self._optimistic_state = None
                    self._optimistic_timestamp = 0
                    self._operation_pending = False

    def mark_pending_operation(self, target_state: bool) -> None:
        """Mark that an operation is pending with a target state.

        Args:
            target_state: The target state (True for on, False for off)
        """
        self._optimistic_state = target_state
        self._optimistic_timestamp = time.time()
        self._operation_pending = True

    def handle_auth_failure(self) -> None:
        """Handle authentication failure by adjusting optimistic states."""
        # Record when this auth failure happened
        self._last_auth_failure_time = time.time()

        # Only retain optimistic state for a shorter period during auth failures
        if self._optimistic_state is not None:
            self._optimistic_max_age = 2  # Reduced maximum age during auth problems

        # Log that we're handling an auth failure for this entity
        LOGGER.debug(
            "Handling auth failure for entity %s (current optimistic state: %s)",
            self.entity_id,
            "on" if self._optimistic_state else "off" if self._optimistic_state is not None else "None",
        )

        # Don't immediately clear optimistic state - let it expire naturally
        # This gives time for auth recovery to succeed

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        LOGGER.debug("%s(%s): Handling coordinator update.", type(self).__name__, self.entity_id or self.unique_id)

        if not self.coordinator or not self.coordinator.data:
            LOGGER.debug(
                "%s(%s): Coordinator or coordinator data missing, skipping update.",
                type(self).__name__,
                self.entity_id or self.unique_id,
            )
            return

        # Get the current rule from the coordinator data
        new_rule = self._get_current_rule()
        current_availability = new_rule is not None
        LOGGER.debug(
            "%s(%s): Rule lookup result: %s. Availability: %s",
            type(self).__name__,
            self.entity_id or self.unique_id,
            "Found" if new_rule else "Not Found",
            current_availability,
        )

        if new_rule is not None:
            # Store the NEW rule data
            self._rule_data = new_rule

            # --- Optimistic State Handling ---
            if self._optimistic_state is not None:
                current_time = time.time()
                age = current_time - self._optimistic_timestamp
                max_age = self._optimistic_max_age

                # Check if optimistic state expired
                if age > max_age:
                    LOGGER.debug(
                        "%s(%s): Optimistic state expired (age: %.1fs > max: %ds).",
                        type(self).__name__,
                        self.entity_id or self.unique_id,
                        age,
                        max_age,
                    )

                    # Get actual state from the NEW rule data
                    actual_state = self._get_actual_state_from_rule(new_rule)
                    LOGGER.debug(
                        "%s(%s): Actual state from new rule data: %s",
                        type(self).__name__,
                        self.entity_id or self.unique_id,
                        actual_state,
                    )

                    # Clear optimistic state only if actual state matches or is unknown
                    if self._optimistic_state == actual_state or actual_state is None:
                        LOGGER.debug(
                            "%s(%s): Clearing optimistic state (matches actual or actual is None).",
                            type(self).__name__,
                            self.entity_id or self.unique_id,
                        )
                        self.clear_optimistic_state(force=True)  # Force clear here
                    else:
                        LOGGER.debug(
                            "%s(%s): State mismatch: optimistic=%s, actual=%s. Keeping optimistic state briefly.",
                            type(self).__name__,
                            self.entity_id or self.unique_id,
                            self._optimistic_state,
                            actual_state,
                        )

            # Clear operation pending flag if not cleared by optimistic logic
            if self._operation_pending and self._optimistic_state is None:
                LOGGER.debug(
                    "%s(%s): Clearing pending operation flag as optimistic state is now None.",
                    type(self).__name__,
                    self.entity_id or self.unique_id,
                )
                self._operation_pending = False

        else:
            # --- Rule Not Found ---
            LOGGER.debug(
                "%s(%s): Rule not found in coordinator data. Initiating removal.",
                type(self).__name__,
                self.entity_id or self.unique_id,
            )
            # Ensure internal data reflects disappearance
            self._rule_data = None
            # Clear any lingering optimistic state
            self.clear_optimistic_state(force=True)
            # Mark as unavailable immediately
            self._attr_available = False
            # Proactively trigger the removal process - This is already in the event loop
            self.hass.async_create_task(self.async_initiate_self_removal())
            # Write state to reflect unavailability before removal completes
            self.async_write_ha_state()
            return  # Exit early as the entity is being removed

        # Write the state AFTER processing coordinator update if not removing
        LOGGER.debug(
            "%s(%s): Writing HA state after coordinator update.", type(self).__name__, self.entity_id or self.unique_id
        )
        self.async_write_ha_state()

    def _get_actual_state_from_rule(self, rule: Any) -> bool | None:
        """Helper to get the actual state from a rule object, handling different types."""
        # Default implementation for most rules
        if hasattr(rule, "enabled"):
            return rule.enabled
        # Handle raw dict case if needed
        if isinstance(rule, dict) and "enabled" in rule:
            return rule.get("enabled")
        LOGGER.warning(
            "%s(%s): Could not determine actual state from rule object type %s",
            type(self).__name__,
            self.entity_id or self.unique_id,
            type(rule).__name__,
        )
        return None  # Return None if state cannot be determined

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # If parent entity is linked, base availability on parent
        if self._linked_parent_id:
            # Find parent entity by unique ID
            parent_entity_id = None
            entity_registry = async_get_entity_registry(self.hass)
            if entity_registry:
                parent_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, self._linked_parent_id)

            if parent_entity_id:
                parent_state = self.hass.states.get(parent_entity_id)
                # Check if parent state exists and is not unavailable
                parent_state_available = parent_state and parent_state.state != "unavailable"

                parent_is_available = parent_state_available
                if parent_is_available:
                    # Check the parent entity object's available property if possible
                    parent_entity = self.hass.data.get(DOMAIN, {}).get(DOMAIN, {}).get(parent_entity_id)
                    if parent_entity and hasattr(parent_entity, "available"):
                        try:
                            # Use a flag to prevent infinite recursion if parent also checks child
                            if getattr(self, "_checking_parent_availability", False):
                                parent_is_truly_available = True  # Assume true to break loop
                            else:
                                parent_entity._checking_parent_availability = True
                                parent_is_truly_available = parent_entity.available
                                delattr(parent_entity, "_checking_parent_availability")
                            if not parent_is_truly_available:
                                return False  # If parent object says it's not available, we aren't either
                        except Exception as e:
                            LOGGER.warning(
                                "%s(%s): Error checking parent entity availability property: %s",
                                type(self).__name__,
                                self.entity_id,
                                e,
                            )
                    return True
                else:
                    return False

        # Standard availability check (if not a child or parent lookup failed)
        coord_success = self.coordinator.last_update_success
        current_rule = self._get_current_rule()
        rule_exists = current_rule is not None
        is_available = coord_success and rule_exists

        return is_available

    @property
    def is_on(self) -> bool:
        """Return the enabled state of the rule."""
        # Use optimistic state if set
        if self._optimistic_state is not None:
            return self._optimistic_state

        rule = self._get_current_rule()
        if rule is None:
            return False

        return get_rule_enabled(rule)

    @property
    def assumed_state(self) -> bool:
        """Return False to get toggle slider UI instead of icon buttons."""
        return False

    def _get_current_rule(self) -> Any | None:
        """Get current rule data from coordinator."""
        try:
            if not self.coordinator or not self.coordinator.data or self._rule_type not in self.coordinator.data:
                return None

            rules = self.coordinator.data.get(self._rule_type, [])

            found_rule = None
            for rule in rules:
                current_rule_id = get_rule_id(rule)
                if current_rule_id == self._rule_id:
                    found_rule = rule
                    break  # Exit loop once found

            return found_rule
        except Exception as err:
            LOGGER.error(
                "%s(%s): Error getting rule data in _get_current_rule: %s",
                type(self).__name__,
                self.entity_id or self._rule_id,
                err,
            )
            return None

    def _to_dict(self, obj: Any) -> dict:
        """Convert a rule object to a dictionary."""
        # Handle objects with raw property (aiounifi API objects and FirewallRule)
        if hasattr(obj, "raw") and isinstance(obj.raw, dict):
            return obj.raw.copy()

        # Handle plain dictionaries
        if isinstance(obj, dict):
            return obj.copy()

        # Handle other objects by creating a dict from properties
        # Get the rule ID properly considering object type
        rule_id = None
        if hasattr(obj, "id"):
            rule_id = obj.id

        base_data = {"_id": rule_id, "enabled": getattr(obj, "enabled", False)}

        # Include other common attributes if they exist
        for attr in ["name", "description", "action"]:
            if hasattr(obj, attr):
                base_data[attr] = getattr(obj, attr)

        return {k: v for k, v in base_data.items() if v is not None}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on (enable) the rule."""
        await self._async_toggle_rule(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off (disable) the rule."""
        await self._async_toggle_rule(False)

    def turn_on(self, **kwargs: Any) -> None:
        """Turn on (enable) the rule - synchronous wrapper."""
        if self.hass and self.hass.loop and self.hass.loop.is_running():
            asyncio.create_task(self.async_turn_on(**kwargs))

    def turn_off(self, **kwargs: Any) -> None:
        """Turn off (disable) the rule - synchronous wrapper."""
        if self.hass and self.hass.loop and self.hass.loop.is_running():
            asyncio.create_task(self.async_turn_off(**kwargs))

    async def _async_toggle_rule(self, enable: bool) -> None:
        """Handle toggling the rule state with per-entity debouncing.

        This method provides immediate UI feedback via optimistic state updates,
        then debounces rapid toggles of the same entity. Only the final state
        after the debounce delay will be submitted to the API.
        """
        action_type = "Turning on" if enable else "Turning off"
        LOGGER.debug("%s rule %s (%s) - scheduling debounced operation", action_type, self._rule_id, self._rule_type)

        # Set optimistic state first for immediate UI feedback
        self.mark_pending_operation(enable)
        self.async_write_ha_state()

        # Cancel any existing debounce timer for this entity
        if self._toggle_debounce_timer is not None:
            self._toggle_debounce_timer.cancel()
            LOGGER.debug(
                "Cancelled pending toggle for %s, replacing with new target state: %s",
                self._rule_id,
                enable,
            )

        # Store the target state for when the debounce timer fires
        self._toggle_debounce_target_state = enable

        # Schedule the debounced operation using get_running_loop (Python 3.13+ compliant)
        loop = asyncio.get_running_loop()
        self._toggle_debounce_timer = loop.call_later(
            TOGGLE_DEBOUNCE_DELAY,
            lambda: self.hass.async_create_task(self._execute_toggle_operation()),
        )

        LOGGER.debug(
            "Scheduled toggle for %s in %.1fs with target state: %s",
            self._rule_id,
            TOGGLE_DEBOUNCE_DELAY,
            enable,
        )

    async def _execute_toggle_operation(self) -> None:
        """Execute the actual toggle operation after debounce delay.

        This method is called when the debounce timer fires. It uses the stored
        target state to set the rule to the exact desired state, regardless of
        the current state in the coordinator.
        """
        # Clear the timer reference
        self._toggle_debounce_timer = None

        # Get the target state that was set during debouncing
        enable = self._toggle_debounce_target_state
        if enable is None:
            LOGGER.warning("Toggle operation for %s has no target state, aborting", self._rule_id)
            return

        # Clear the stored target state
        self._toggle_debounce_target_state = None

        LOGGER.debug("Executing debounced toggle for %s with target state: %s", self._rule_id, enable)

        # Get the current rule object
        current_rule = self._get_current_rule()
        if current_rule is None:
            LOGGER.error("Rule not found in coordinator data: %s", self._rule_id)
            # Revert optimistic state
            self.mark_pending_operation(not enable)
            self.async_write_ha_state()
            return

        # Initialize pending operations dict if needed
        if not hasattr(self.coordinator, "_pending_operations"):
            self.coordinator._pending_operations = {}

        # Add this entity's ID to pending operations with target state
        self.coordinator._pending_operations[self._rule_id] = enable

        LOGGER.debug("Adding rule %s to pending operations queue with target state: %s", self._rule_id, enable)

        # Register the operation with the coordinator to prevent redundant refreshes.
        change_type = "enabled" if enable else "disabled"
        entity_id = self.entity_id or f"switch.{self._rule_id}"
        self.coordinator.register_ha_initiated_operation(self._rule_id, entity_id, change_type)

        # Define callback to handle operation completion
        async def handle_operation_complete(future):
            """Handle operation completion."""
            try:
                success = future.result()

                if not success:
                    # Revert optimistic state if failed
                    LOGGER.error("Failed to %s rule %s", "enable" if enable else "disable", self._rule_id)
                    self.mark_pending_operation(not enable)
                    self.async_write_ha_state()
                else:
                    # On success, refresh the optimistic state timestamp to prevent premature clearing
                    self._optimistic_timestamp = time.time()
                    self.async_write_ha_state()

                    # --- Smart Verification Task ---
                    # This task acts as a safety net. It waits a few seconds and then checks
                    # if the change was confirmed by the trigger system (which consumes the
                    # HA-initiated operation flag). If not, it forces a refresh.
                    async def delayed_verification():
                        await asyncio.sleep(SWITCH_DELAYED_VERIFICATION_SLEEP_SECONDS)  # Wait for smart polling update
                        if self.coordinator.check_and_consume_ha_initiated_operation(self._rule_id):
                            # If the flag was still present, it means the trigger system
                            # did NOT get a change event. We must refresh.
                            LOGGER.debug(
                                "Delayed verification: Trigger did not receive change event for %s. Forcing refresh.",
                                self._rule_id,
                            )
                            await self.coordinator.async_request_refresh()
                        else:
                            # The flag was already consumed, so the trigger worked correctly.
                            LOGGER.debug(
                                "Delayed verification: Trigger confirmed change for %s. No refresh needed.",
                                self._rule_id,
                            )

                    # Skip delayed verification for device LED toggles since we use immediate trigger + polling detection
                    if self._rule_type != "devices":
                        self.hass.async_create_task(delayed_verification())

            except Exception as err:
                # Check if this is an auth error
                error_str = str(err).lower()
                if "401 unauthorized" in error_str or "403 forbidden" in error_str:
                    LOGGER.warning("Authentication error in toggle operation for rule %s: %s", self._rule_id, err)
                    # Report auth failure to handle it appropriately
                    self.handle_auth_failure()
                else:
                    LOGGER.error("Error in toggle operation for rule %s: %s", self._rule_id, err)

                # Revert optimistic state on error
                self.mark_pending_operation(not enable)
                self.async_write_ha_state()
            finally:
                # Always remove from pending operations when complete
                if self._rule_id in self.coordinator._pending_operations:
                    LOGGER.debug("Removing rule %s from pending operations after completion", self._rule_id)
                    del self.coordinator._pending_operations[self._rule_id]

        # Queue the appropriate toggle operation based on rule type
        try:
            # Select the appropriate toggle function
            toggle_func = None
            if self._rule_type == "firewall_policies":
                toggle_func = self.coordinator.api.toggle_firewall_policy
            elif self._rule_type == "traffic_rules":
                toggle_func = self.coordinator.api.toggle_traffic_rule
            elif self._rule_type == "port_forwards":
                toggle_func = self.coordinator.api.toggle_port_forward
            elif self._rule_type == "traffic_routes":
                toggle_func = self.coordinator.api.toggle_traffic_route
            elif self._rule_type == "static_routes":
                toggle_func = self.coordinator.api.toggle_static_route
            elif self._rule_type == "legacy_firewall_rules":
                toggle_func = self.coordinator.api.toggle_legacy_firewall_rule
            elif self._rule_type == "wlans":
                toggle_func = self.coordinator.api.toggle_wlan
            elif self._rule_type == "qos_rules":
                toggle_func = self.coordinator.api.toggle_qos_rule
            elif self._rule_type == "vpn_clients":
                toggle_func = self.coordinator.api.toggle_vpn_client
            elif self._rule_type == "vpn_servers":
                toggle_func = self.coordinator.api.toggle_vpn_server
            elif self._rule_type == "nat_rules":
                toggle_func = self.coordinator.api.toggle_nat_rule
            elif self._rule_type == "oon_policies":
                toggle_func = self.coordinator.api.toggle_oon_policy
            elif self._rule_type == "port_profiles":

                async def port_profile_toggle_wrapper(profile_obj, target_state):
                    # When enabling, provide a native_networkconf_id if missing by
                    # using coordinator.networks preference. The API function itself
                    # will also try to discover a default if needed, but we prefer
                    # to choose deterministically here.
                    native_id = None
                    try:
                        # If enabling, supply target native id
                        if target_state and hasattr(self.coordinator, "networks"):
                            networks = self.coordinator.networks or []
                            # Prefer corporate/LAN
                            preferred = next((n for n in networks if getattr(n, "purpose", "") == "corporate"), None)
                            if not preferred and networks:
                                preferred = networks[0]
                            native_id = preferred.id if preferred else None
                    except Exception:
                        native_id = None
                    return await self.coordinator.api.toggle_port_profile(profile_obj, native_id, target_state)

                toggle_func = port_profile_toggle_wrapper
            elif self._rule_type == "devices":
                # For device LED toggles, use a special wrapper function
                async def led_toggle_wrapper(device, state):
                    """Wrapper to make LED toggle compatible with queue system."""
                    return await self.coordinator.api.set_device_led(device, state)

                toggle_func = led_toggle_wrapper
            else:
                raise ValueError(f"Unknown rule type: {self._rule_type}")

            # Queue the operation with the target state
            # All toggle functions now accept target_state to set explicit state
            future = await self.coordinator.api.queue_api_operation(toggle_func, current_rule, enable)

            # Add the completion callback
            future.add_done_callback(lambda f: self.hass.async_create_task(handle_operation_complete(f)))

            LOGGER.debug(
                "Successfully queued toggle operation for rule %s with target state: %s", self._rule_id, enable
            )
        except Exception as err:
            LOGGER.error("Failed to queue toggle operation for rule %s: %s", self._rule_id, err)
            # Remove from pending operations if queueing failed
            if self._rule_id in self.coordinator._pending_operations:
                del self.coordinator._pending_operations[self._rule_id]

            # Revert optimistic state
            self.mark_pending_operation(not enable)
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity cleanup when removed from Home Assistant."""
        LOGGER.debug("Entity %s cleaning up before removal from Home Assistant", self.entity_id)

        # Cancel any pending debounce timer
        if self._toggle_debounce_timer is not None:
            self._toggle_debounce_timer.cancel()
            self._toggle_debounce_timer = None
            self._toggle_debounce_target_state = None

        # Clean up internal entity tracking dictionary
        entity_dict = self.hass.data.get(DOMAIN, {}).get("entities", {})
        if self.entity_id in entity_dict:
            del entity_dict[self.entity_id]
            LOGGER.debug("Removed %s from internal entity tracking.", self.entity_id)

        # Clean up global _CREATED_UNIQUE_IDS set (if still used)
        from .setup import _CREATED_UNIQUE_IDS

        _CREATED_UNIQUE_IDS.discard(self._attr_unique_id)  # Use discard for safety

        # IMPORTANT: Call super().async_will_remove_from_hass() LAST
        # This ensures base class cleanup (like removing listeners registered with self.async_on_remove) happens.
        await super().async_will_remove_from_hass()
        LOGGER.debug("Finished async_will_remove_from_hass for %s", self.entity_id)

    @callback
    def _handle_entity_removal(self, removed_entity_id: str) -> None:
        """Handle the removal of an entity via dispatcher signal."""
        # This function is primarily for reacting to EXTERNAL removal signals.
        # Proactive removal initiated by _handle_coordinator_update uses async_initiate_self_removal.
        if removed_entity_id != self._rule_id:
            return

        LOGGER.info(
            "Received external removal signal for entity %s (%s). Initiating cleanup.", self.entity_id, self._rule_id
        )
        # Avoid duplicate removal if already initiated
        if getattr(self, "_removal_initiated", False):
            LOGGER.debug("Removal already initiated for %s, skipping signal handler.", self.entity_id)
            return

        # Initiate removal asynchronously in a thread-safe way
        self.hass.loop.call_soon_threadsafe(self.hass.async_create_task, self.async_initiate_self_removal())

    async def async_initiate_self_removal(self) -> None:
        """Proactively remove this entity and its children from Home Assistant."""
        from .setup import _CREATED_UNIQUE_IDS

        entity_id_for_log = self.entity_id or self._attr_unique_id

        if getattr(self, "_removal_initiated", False):
            return

        self._removal_initiated = True  # Set flag to prevent loops

        entity_registry = async_get_entity_registry(self.hass)

        # 0. Always remove from coordinator known_unique_ids first to prevent recreation
        if hasattr(self.coordinator, "known_unique_ids"):
            self.coordinator.known_unique_ids.discard(self._attr_unique_id)

        # Also remove from global tracking set immediately
        _CREATED_UNIQUE_IDS.discard(self._attr_unique_id)

        # 1. Remove Child Entities RECURSIVELY
        if self._linked_child_ids:
            children_to_remove = list(self._linked_child_ids)
            for child_unique_id in children_to_remove:
                child_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, child_unique_id)
                child_entity = None
                if child_entity_id:
                    # Look up child entity instance from hass.data
                    child_entity = self.hass.data.get(DOMAIN, {}).get("entities", {}).get(child_entity_id)

                if child_entity and hasattr(child_entity, "async_initiate_self_removal"):
                    try:
                        await child_entity.async_initiate_self_removal()
                    except Exception as child_err:
                        LOGGER.error(
                            "%s(%s): Error requesting self-removal for child entity %s (%s): %s",
                            type(self).__name__,
                            entity_id_for_log,
                            child_entity_id or child_unique_id,
                            child_unique_id,
                            child_err,
                        )
                else:
                    # Fallback: Child object not found or doesn't have the method. Remove directly from registry.
                    if child_entity_id and entity_registry.async_get(child_entity_id):
                        try:
                            entity_registry.async_remove(child_entity_id)
                        except Exception as reg_rem_err:
                            LOGGER.error(
                                "%s(%s): Error removing child %s from registry directly: %s",
                                type(self).__name__,
                                entity_id_for_log,
                                child_entity_id,
                                reg_rem_err,
                            )
                    # Also clean up tracking even if registry removal fails or wasn't needed
                    if hasattr(self.coordinator, "known_unique_ids"):
                        self.coordinator.known_unique_ids.discard(child_unique_id)
                    _CREATED_UNIQUE_IDS.discard(child_unique_id)  # Use discard

                # Remove from parent's list regardless of success/failure of child removal
                self._linked_child_ids.discard(child_unique_id)

        # 3. Remove Self from Entity Registry and HA Core
        entity_id_to_remove = self.entity_id  # Store current entity_id for logging
        LOGGER.debug(
            "%s(%s): Preparing to call self.async_remove(force_remove=True) for entity_id: %s",
            type(self).__name__,
            entity_id_for_log,
            entity_id_to_remove,
        )
        try:
            await self.async_remove(force_remove=True)
            LOGGER.info(
                "%s(%s): Successfully completed self.async_remove() for entity_id: %s.",
                type(self).__name__,
                entity_id_for_log,
                entity_id_to_remove,
            )
        except Exception as remove_err:
            # Log expected errors during removal less severely
            if isinstance(remove_err, HomeAssistantError) and "Entity not found" in str(remove_err):
                LOGGER.debug(
                    "%s(%s): Entity %s already removed from HA core.",
                    type(self).__name__,
                    entity_id_for_log,
                    entity_id_to_remove,
                )
            else:
                LOGGER.error(
                    "%s(%s): Error during final async_remove for entity_id %s: %s",
                    type(self).__name__,
                    entity_id_for_log,
                    entity_id_to_remove,
                    remove_err,
                )
                LOGGER.exception(
                    "%s(%s): Exception during async_remove for entity_id %s:",
                    type(self).__name__,
                    entity_id_for_log,
                    entity_id_to_remove,
                )

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        from .setup import _CREATED_UNIQUE_IDS  # Add global declaration here

        await super().async_added_to_hass()

        # Store entity in a central place for easy lookup (e.g., by parent/child logic)
        if DOMAIN not in self.hass.data:
            self.hass.data[DOMAIN] = {}
        if "entities" not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN]["entities"] = {}
        self.hass.data[DOMAIN]["entities"][self.entity_id] = self
        LOGGER.debug("Stored entity %s in hass.data[%s]['entities']", self.entity_id, DOMAIN)

        # Perform global unique ID tracking here
        if self.unique_id in _CREATED_UNIQUE_IDS:
            # This case should ideally not happen if setup_entry filtering works,
            # but log if it does.
            LOGGER.warning(
                "Entity %s added to HASS, but unique_id %s was already tracked.", self.entity_id, self.unique_id
            )
        else:
            _CREATED_UNIQUE_IDS.add(self.unique_id)
            LOGGER.debug(
                "Added unique_id %s to global tracking upon adding entity %s to HASS.", self.unique_id, self.entity_id
            )

        # Add update callbacks
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))

        # Also listen for specific events related to this entity
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_entity_update_{self._rule_id}", self.async_schedule_update_ha_state
            )
        )

        # Listen for authentication failure events
        self.async_on_remove(
            async_dispatcher_connect(self.hass, f"{DOMAIN}_auth_failure", self._handle_auth_failure_event)
        )

        # Listen for authentication restored events
        self.async_on_remove(
            async_dispatcher_connect(self.hass, f"{DOMAIN}_auth_restored", self._handle_auth_restored_event)
        )

        # Listen for entity created events
        self.async_on_remove(
            async_dispatcher_connect(self.hass, f"{DOMAIN}_entity_created", self._handle_entity_created)
        )

        # Listen for force cleanup signal
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_ENTITIES_CLEANUP, self._handle_force_cleanup))

        # --- Ensure initial state is based on current coordinator data ---

        # Make sure the entity is properly registered in the entity registry
        try:
            registry = async_get_entity_registry(self.hass)

            # Log the entity registry state
            LOGGER.debug("Entity registry check - unique_id: %s, entity_id: %s", self.unique_id, self.entity_id)

            # Check if the entity already exists in the registry
            existing_entity = registry.async_get_entity_id("switch", DOMAIN, self.unique_id)

            if existing_entity:
                LOGGER.debug("Entity already exists in registry: %s", existing_entity)
                # Don't try to update the entity_id - this has been causing problems
                # Just force a state update to ensure it's current
            else:
                # Register the entity with our consistent ID format
                try:
                    # Use the object_id from rule.py
                    object_id = get_object_id(self._rule_data, self._rule_type)

                    entity_entry = registry.async_get_or_create(
                        "switch",
                        DOMAIN,
                        self.unique_id,
                        suggested_object_id=object_id,
                        # Don't set disabled_by to ensure it's enabled
                        disabled_by=None,
                    )

                    if entity_entry:
                        LOGGER.info("Entity registered in registry: %s", entity_entry.entity_id)
                    else:
                        LOGGER.warning("Failed to register entity with registry")
                except Exception as reg_err:
                    LOGGER.warning("Could not register entity: %s", reg_err)

            # Force a state update to ensure it shows up AFTER potentially registering
            self.async_write_ha_state()
        except Exception as err:
            LOGGER.error("Error during entity registration: %s", err)

    @callback
    def _handle_auth_failure_event(self, _: Any = None) -> None:
        """Handle authentication failure event."""
        LOGGER.debug("Authentication failure event received for entity %s", self.entity_id)

        # Track the auth failure time
        self._last_auth_failure_time = time.time()

        # Notify the entity to handle auth failure appropriately
        self.handle_auth_failure()

        # Force a state update to reflect any changes
        self.async_write_ha_state()

    @callback
    def _handle_auth_restored_event(self, _: Any = None) -> None:
        """Handle authentication restored event."""
        LOGGER.debug("Authentication restored event received for entity %s", self.entity_id)

        # Reset auth failure time
        self._last_auth_failure_time = 0

        # Reset optimistic max age to normal
        self._optimistic_max_age = 5

        # If we have an operation pending and optimistic state is set, keep it longer
        # to allow time for the next refresh to verify state
        if self._operation_pending and self._optimistic_state is not None:
            self._optimistic_timestamp = time.time()
            LOGGER.debug("Refreshed optimistic state timestamp due to auth restoration")
        else:
            # No operations pending, clear any lingering optimistic state
            self.clear_optimistic_state()

        # Force an update
        self.async_schedule_update_ha_state(True)

    @callback
    def _handle_entity_created(self) -> None:
        """Handle entity created event."""
        LOGGER.debug("Entity created event received for %s", self.entity_id)

        # Force a state update
        self.async_write_ha_state()

        # Use a dispatcher instead of trying to call async_update_entity directly
        async_dispatcher_send(self.hass, f"{DOMAIN}_entity_update_{self.unique_id}")

    @callback
    def _handle_force_cleanup(self, _: Any = None) -> None:
        """Handle force cleanup signal."""
        LOGGER.debug("Force cleanup signal received for entity %s", self.entity_id)
        # Force an update to synchronize with latest data
        self.async_schedule_update_ha_state(True)
