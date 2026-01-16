"""Device switches for UniFi Network Rules integration."""

from __future__ import annotations

import logging
import time
from typing import Any

from aiounifi.models.device import Device
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from ..const import DOMAIN, LOG_TRIGGERS, MANUFACTURER
from ..coordinator import UnifiRuleUpdateCoordinator
from ..models.ether_lighting import (
    ETHER_LIGHTING_LED_MODE_OFF,
    ETHER_LIGHTING_LED_MODE_ON,
    get_ether_lighting,
    has_ether_lighting,
)
from .base import UnifiRuleSwitch

LOGGER = logging.getLogger(__name__)


class UnifiLedToggleSwitch(UnifiRuleSwitch):
    """Switch to toggle UniFi device LED - inherits resilient patterns from UnifiRuleSwitch."""

    def __init__(
        self, coordinator: UnifiRuleUpdateCoordinator, rule_data: Device, rule_type: str, entry_id: str = None
    ) -> None:
        """Initialize LED toggle switch using the base UnifiRuleSwitch."""
        # Call parent constructor with device data
        super().__init__(coordinator, rule_data, rule_type, entry_id)

        # Store device reference for LED-specific operations
        self._device = rule_data

        # Get device identifiers safely from raw data
        raw_data = getattr(rule_data, "raw", {}) if hasattr(rule_data, "raw") else {}
        device_mac = raw_data.get("mac", raw_data.get("serial", "unknown"))
        device_name = raw_data.get("name", raw_data.get("device_id", device_mac))

        # Override name to be LED-specific
        self._attr_name = f"{device_name} LED"

        # Set appropriate device class and entity category for LED
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_class = SwitchDeviceClass.SWITCH

        # Set up device info with more details
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_mac)},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=raw_data.get("model", raw_data.get("type", "UniFi Device")),
            sw_version=raw_data.get("version"),
            hw_version=raw_data.get("hw_rev"),
        )

        # Icon will be set dynamically based on state
        self._update_icon()

    def _update_icon(self) -> None:
        """Update icon based on current state."""
        if self.is_on:
            self._attr_icon = "mdi:led-on"
        else:
            self._attr_icon = "mdi:led-off"

    def _get_current_rule(self) -> Device | None:
        """Override to get current device from coordinator."""
        try:
            if not self.coordinator or not self.coordinator.data or "devices" not in self.coordinator.data:
                return None

            devices = self.coordinator.data.get("devices", [])
            device_mac = getattr(self._device, "mac", None)

            for device in devices:
                if hasattr(device, "mac") and device.mac == device_mac:
                    return device

            return None
        except Exception as err:
            LOGGER.error("Error getting device data: %s", err)
            return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update icon based on current state
        self._update_icon()

        # Call parent update (handles optimistic state and availability)
        super()._handle_coordinator_update()

    async def _async_toggle_rule(self, enable: bool) -> None:
        """Override toggle for LED devices to add immediate trigger firing."""
        # Fire immediate device trigger for optimistic response
        try:
            device_name = getattr(self._device, "name", f"Device {self._rule_id}")
            device_id = getattr(self._device, "mac", self._rule_id)

            # Use existing CQRS pattern to track this HA-initiated operation
            change_type = "enabled" if enable else "disabled"
            entity_id = self.entity_id or f"switch.{self._rule_id}_led"
            self.coordinator.register_ha_initiated_operation(device_id, entity_id, change_type)

            if LOG_TRIGGERS:
                LOGGER.info(
                    "🔥 LED IMMEDIATE TRIGGER: Firing device trigger for %s (%s): LED %s → %s",
                    device_name,
                    device_id,
                    "OFF" if enable else "ON",
                    "ON" if enable else "OFF",
                )

            # Get current device object for trigger payload (consistent with rule triggers)
            current_device = self._get_current_rule()  # Returns Device object

            # Create optimistic device states for immediate trigger
            if current_device and hasattr(current_device, "raw"):
                # Create old_state (current LED state)
                old_state_device = current_device

                # Create new_state with optimistic LED state
                new_device_data = current_device.raw.copy()

                # Handle Etherlighting vs traditional LED devices
                if has_ether_lighting(new_device_data):
                    # Etherlighting device - update ether_lighting.led_mode
                    ether_lighting = get_ether_lighting(new_device_data)
                    if ether_lighting:
                        new_device_data["ether_lighting"] = ether_lighting.with_enabled(enable)
                    else:
                        new_device_data["ether_lighting"] = {
                            "led_mode": ETHER_LIGHTING_LED_MODE_ON if enable else ETHER_LIGHTING_LED_MODE_OFF
                        }
                    old_led_state = old_state_device.raw.get("ether_lighting", {}).get("led_mode", "unknown")
                    new_led_state = new_device_data["ether_lighting"].get("led_mode", "unknown")
                else:
                    # Traditional LED device - update led_override
                    new_device_data["led_override"] = "default" if enable else "off"
                    old_led_state = old_state_device.raw.get("led_override", "unknown")
                    new_led_state = new_device_data.get("led_override", "unknown")

                # Create optimistic new device object using globally imported Device class
                new_state_device = Device(new_device_data)

                if LOG_TRIGGERS:
                    LOGGER.info(
                        "🎯 OPTIMISTIC DEVICE STATE: %s → %s",
                        old_led_state,
                        new_led_state,
                    )
            else:
                # Fallback if device structure is unexpected
                old_state_device = current_device
                new_state_device = current_device
                LOGGER.warning("Could not create optimistic device state for immediate trigger")

            # Fire immediate device trigger via dispatcher
            # Pass full device objects like rule triggers do
            self.coordinator.fire_device_trigger_via_dispatcher(
                device_id=device_id,
                device_name=device_name,
                change_type="led_toggled",
                old_state=old_state_device,  # Full device object (consistent with rule triggers)
                new_state=new_state_device,  # Full device object (consistent with rule triggers)
            )

        except Exception as trigger_err:
            LOGGER.error("Error firing immediate device trigger for LED toggle: %s", trigger_err)

        # Call parent toggle method to handle the actual API operation
        await super()._async_toggle_rule(enable)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attributes = {}

        device = self._get_current_rule()  # Use base method now
        if device and hasattr(device, "raw"):
            raw_data = device.raw

            # Add device information
            attributes["device_mac"] = raw_data.get("mac", "unknown")
            attributes["device_model"] = raw_data.get("model", "Unknown")
            attributes["device_type"] = raw_data.get("type", "Unknown")

            # Add LED-specific information based on device type
            if has_ether_lighting(raw_data):
                # Etherlighting device (Pro Max switches)
                attributes["led_type"] = "etherlighting"
                ether_lighting = get_ether_lighting(raw_data)
                if ether_lighting:
                    attributes["ether_lighting_mode"] = ether_lighting.mode
                    attributes["ether_lighting_brightness"] = ether_lighting.brightness
                    attributes["ether_lighting_behavior"] = ether_lighting.behavior
                    attributes["ether_lighting_led_mode"] = ether_lighting.led_mode
            else:
                # Traditional LED device
                attributes["led_type"] = "traditional"
                if "led_override" in raw_data:
                    attributes["led_override"] = raw_data["led_override"]
                if "led_override_color" in raw_data:
                    attributes["led_override_color"] = raw_data["led_override_color"]
                if "led_override_color_brightness" in raw_data:
                    attributes["led_brightness"] = raw_data["led_override_color_brightness"]

            # Add connection state
            if "state" in raw_data:
                attributes["connection_state"] = raw_data["state"]

        # Add optimistic state info for debugging
        if self._optimistic_state is not None:
            attributes["optimistic_state"] = self._optimistic_state
            attributes["optimistic_age"] = round(time.time() - self._optimistic_timestamp, 1)

        return attributes
