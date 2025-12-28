"""State management module for UniFi Network Rules coordinator.

Handles state tracking, change detection, error management, and device monitoring.
Provides centralized state management with diagnostic capabilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..const import LOG_TRIGGERS, LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class CoordinatorStateManager:
    """Manages state and change detection for the coordinator."""

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        """Initialize the state manager.

        Args:
            hass: Home Assistant instance
            coordinator: Reference to parent coordinator
        """
        self.hass = hass
        self.coordinator = coordinator

        # Error tracking
        self._in_error_state = False
        self._consecutive_errors = 0
        self._api_errors = 0
        self._last_successful_data = {}

        # Track initial update
        self._initial_update_done = False

    def data_has_changes(self, previous_data: dict[str, list[Any]], new_data: dict[str, list[Any]]) -> bool:
        """Check if data has changed between polling cycles.

        This is used to detect external changes (not HA-initiated) during polling.

        Args:
            previous_data: The previous data from coordinator
            new_data: The new data from coordinator

        Returns:
            True if changes were detected, False otherwise
        """
        if not previous_data or not new_data:
            return False

        # Quick check: compare collection sizes first
        for rule_type in [
            "port_forwards",
            "traffic_routes",
            "static_routes",
            "firewall_policies",
            "traffic_rules",
            "legacy_firewall_rules",
            "wlans",
            "firewall_zones",
            "qos_rules",
            "vpn_clients",
            "vpn_servers",
            "devices",
            "port_profiles",
            "networks",
            "nat_rules",
        ]:
            prev_count = len(previous_data.get(rule_type, []))
            new_count = len(new_data.get(rule_type, []))
            if prev_count != new_count:
                LOGGER.debug("[SMART_POLL] Count change detected in %s: %d → %d", rule_type, prev_count, new_count)
                return True

        # If counts are the same, do a deeper check on enabled states and key attributes
        # This is a lightweight check focused on the most common changes
        for rule_type in [
            "port_forwards",
            "traffic_routes",
            "static_routes",
            "firewall_policies",
            "traffic_rules",
            "legacy_firewall_rules",
            "wlans",
            "qos_rules",
            "nat_rules",
        ]:
            prev_rules = previous_data.get(rule_type, [])
            new_rules = new_data.get(rule_type, [])

            # Create lookup dictionaries for efficient comparison
            prev_lookup = {}
            new_lookup = {}

            for rule in prev_rules:
                rule_id = getattr(rule, "id", None) or (rule.raw.get("_id") if hasattr(rule, "raw") else None)
                if rule_id:
                    enabled = getattr(rule, "enabled", None) or (
                        rule.raw.get("enabled") if hasattr(rule, "raw") else None
                    )
                    prev_lookup[rule_id] = enabled

            for rule in new_rules:
                rule_id = getattr(rule, "id", None) or (rule.raw.get("_id") if hasattr(rule, "raw") else None)
                if rule_id:
                    enabled = getattr(rule, "enabled", None) or (
                        rule.raw.get("enabled") if hasattr(rule, "raw") else None
                    )
                    new_lookup[rule_id] = enabled

            # Check for enabled state changes
            for rule_id in prev_lookup:
                if rule_id in new_lookup:
                    if prev_lookup[rule_id] != new_lookup[rule_id]:
                        LOGGER.debug(
                            "[SMART_POLL] Enabled state change detected in %s rule %s: %s → %s",
                            rule_type,
                            rule_id,
                            prev_lookup[rule_id],
                            new_lookup[rule_id],
                        )
                        return True

        return False

    def check_for_device_state_changes(
        self, previous_data: dict[str, list[Any]], new_data: dict[str, list[Any]]
    ) -> None:
        """Check for LED state changes on devices and fire device triggers accordingly.

        This detects LED changes during regular coordinator polling cycles as part
        of the unified change detection system.

        Args:
            previous_data: The previous coordinator data
            new_data: The current coordinator data
        """
        if not previous_data or not new_data:
            LOGGER.debug("Skipping device LED state change detection - no previous or new data")
            return

        previous_devices = previous_data.get("devices", [])
        new_devices = new_data.get("devices", [])

        if not previous_devices and not new_devices:
            return  # No devices to compare

        # Create lookup dictionaries by device MAC for efficient comparison
        previous_device_states = {}
        for device in previous_devices:
            try:
                device_id = getattr(device, "mac", getattr(device, "id", None))
                if device_id:
                    previous_device_states[device_id] = {
                        "led_override": getattr(device, "led_override", None),
                        "name": getattr(device, "name", f"Device {device_id}"),
                    }
            except Exception as err:
                LOGGER.warning("Error processing previous device LED state: %s", err)

        new_device_states = {}
        for device in new_devices:
            try:
                device_id = getattr(device, "mac", getattr(device, "id", None))
                if device_id:
                    new_device_states[device_id] = {
                        "led_override": getattr(device, "led_override", None),
                        "name": getattr(device, "name", f"Device {device_id}"),
                    }
            except Exception as err:
                LOGGER.warning("Error processing new device LED state: %s", err)

        # Compare device LED states and fire triggers for changes
        all_device_ids = set(previous_device_states.keys()) | set(new_device_states.keys())

        # Build lookup for full device objects
        previous_devices_lookup = {}
        new_devices_lookup = {}

        for device in previous_devices:
            device_id = getattr(device, "mac", getattr(device, "id", None))
            if device_id:
                previous_devices_lookup[device_id] = device

        for device in new_devices:
            device_id = getattr(device, "mac", getattr(device, "id", None))
            if device_id:
                new_devices_lookup[device_id] = device

        for device_id in all_device_ids:
            previous_state = previous_device_states.get(device_id)
            new_state = new_device_states.get(device_id)

            # Skip if device was just added or removed (handled elsewhere)
            if not previous_state or not new_state:
                continue

            # Check for LED state changes only
            prev_led = previous_state.get("led_override")
            new_led = new_state.get("led_override")

            if prev_led != new_led:
                device_name = new_state.get("name", f"Device {device_id}")

                # Get full device objects for trigger payload
                previous_device_obj = previous_devices_lookup.get(device_id)
                new_device_obj = new_devices_lookup.get(device_id)

                # Check if this was an HA-initiated operation to avoid duplicate triggers
                was_ha_initiated = self.coordinator.check_and_consume_ha_initiated_operation(device_id)

                if was_ha_initiated:
                    if LOG_TRIGGERS:
                        LOGGER.info(
                            "🔄 DEVICE LED CHANGE: %s (%s) LED: %s → %s [HA-INITIATED - Skipping duplicate trigger]",
                            device_name,
                            device_id,
                            prev_led,
                            new_led,
                        )
                else:
                    if LOG_TRIGGERS:
                        LOGGER.info(
                            "🔍 DEVICE LED CHANGE DETECTED: %s (%s) LED: %s → %s [EXTERNAL CHANGE - Firing trigger]",
                            device_name,
                            device_id,
                            prev_led,
                            new_led,
                        )

                    # Fire device trigger via dispatcher (external change)
                    self.coordinator.fire_device_trigger_via_dispatcher(
                        device_id=device_id,
                        device_name=device_name,
                        change_type="led_toggled",
                        old_state=previous_device_obj,
                        new_state=new_device_obj,
                    )

    def track_error_state(self, is_error: bool, error_message: str = "") -> None:
        """Track error state and consecutive error count.

        Args:
            is_error: Whether an error occurred
            error_message: Optional error message for logging
        """
        if is_error:
            self._consecutive_errors += 1
            self._api_errors += 1
            if not self._in_error_state:
                LOGGER.warning(
                    "Entering error state after %d consecutive errors: %s", self._consecutive_errors, error_message
                )
                self._in_error_state = True
        else:
            if self._consecutive_errors > 0:
                LOGGER.info("Recovered from error state after %d consecutive errors", self._consecutive_errors)
            self._consecutive_errors = 0
            self._in_error_state = False

    def validate_data_and_handle_errors(self, data: dict[str, list[Any]], previous_data: dict[str, list[Any]]) -> bool:
        """Validate fetched data and handle potential errors.

        Args:
            data: The newly fetched data
            previous_data: The previous data for fallback

        Returns:
            True if data is valid, False if using fallback data
        """
        # Check if we have valid data
        data_valid = any(
            len(data.get(key, [])) > 0
            for key in [
                "firewall_policies",
                "traffic_rules",
                "port_forwards",
                "qos_rules",
                "traffic_routes",
                "static_routes",
                "legacy_firewall_rules",
                "port_profiles",
                "networks",
                "devices",
                "nat_rules",
            ]
        )

        # If we get no data but had data before, likely a temporary API issue
        if (
            not data_valid
            and previous_data
            and any(
                len(previous_data.get(key, [])) > 0
                for key in [
                    "firewall_policies",
                    "traffic_rules",
                    "port_forwards",
                    "traffic_routes",
                    "static_routes",
                    "nat_rules",
                ]
            )
        ):
            self.track_error_state(True, "No valid rule data received but had previous data")

            # If this is a persistent issue (3+ consecutive failures)
            if self._consecutive_errors >= 3:
                LOGGER.error(
                    "Multiple consecutive empty data responses. API may be experiencing issues. Using last valid data."
                )
                # Update coordinator data with fallback
                for key, value in self._last_successful_data.items():
                    if key in data:
                        data[key] = value
                return False

            # For fewer errors, try to preserve previous data
            for key in [
                "firewall_policies",
                "traffic_rules",
                "port_forwards",
                "traffic_routes",
                "static_routes",
                "nat_rules",
            ]:
                if not data.get(key) and previous_data.get(key):
                    LOGGER.info("Preserving previous %s data due to API issue", key)
                    data[key] = previous_data[key]

            return False

        # If we got valid data, reset error state
        if data_valid:
            self.track_error_state(False)
            self._last_successful_data = data.copy()
            return True

        return data_valid

    def mark_initial_update_done(self) -> None:
        """Mark that the initial update has been completed."""
        if not self._initial_update_done:
            self._initial_update_done = True
            LOGGER.debug("Marked initial update as complete")

    def is_initial_update_done(self) -> bool:
        """Check if initial update has been completed.

        Returns:
            True if initial update is done, False otherwise
        """
        return self._initial_update_done

    def get_state_status(self) -> dict[str, Any]:
        """Get current state status for diagnostics.

        Returns:
            Dictionary with current state information
        """
        return {
            "in_error_state": self._in_error_state,
            "consecutive_errors": self._consecutive_errors,
            "api_errors": self._api_errors,
            "initial_update_done": self._initial_update_done,
            "has_last_successful_data": bool(self._last_successful_data),
            "last_successful_data_types": list(self._last_successful_data.keys()) if self._last_successful_data else [],
        }

    def reset_error_state(self) -> None:
        """Reset error state tracking."""
        self._in_error_state = False
        self._consecutive_errors = 0
        LOGGER.debug("Reset error state tracking")
