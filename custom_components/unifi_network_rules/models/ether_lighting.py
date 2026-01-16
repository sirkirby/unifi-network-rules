"""Typed model for UniFi Etherlighting configuration.

Etherlighting is a feature on UniFi Pro Max switches that provides
LED lighting on Ethernet ports with configurable modes, brightness,
and behaviors.

This model wraps the raw ether_lighting dict from the device API
and provides typed accessors for use in LED control entities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Known Etherlighting modes
ETHER_LIGHTING_MODE_SPEED = "speed"
ETHER_LIGHTING_MODE_COLOR = "color"

# Known Etherlighting behaviors
ETHER_LIGHTING_BEHAVIOR_BREATH = "breath"
ETHER_LIGHTING_BEHAVIOR_SOLID = "solid"

# LED mode values
ETHER_LIGHTING_LED_MODE_ON = "etherlighting"
ETHER_LIGHTING_LED_MODE_OFF = "off"


@dataclass
class EtherLighting:
    """Represents UniFi Etherlighting configuration with typed accessors.

    Etherlighting devices use a different API structure than traditional
    LED override devices. Instead of led_override field, they use an
    ether_lighting object with mode, brightness, behavior, and led_mode.

    Example raw data:
        {
            "mode": "speed",
            "brightness": 95,
            "behavior": "breath",
            "led_mode": "etherlighting"
        }
    """

    raw: dict[str, Any]

    @property
    def mode(self) -> str:
        """Get the lighting mode (e.g., 'speed', 'color').

        Returns:
            The mode string, defaults to 'speed' if not set.
        """
        return str(self.raw.get("mode", ETHER_LIGHTING_MODE_SPEED))

    @property
    def brightness(self) -> int:
        """Get the brightness level (0-100).

        Returns:
            Brightness as integer, defaults to 100 if not set.
        """
        value = self.raw.get("brightness", 100)
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return 100

    @property
    def behavior(self) -> str:
        """Get the lighting behavior (e.g., 'breath', 'solid').

        Returns:
            The behavior string, defaults to 'solid' if not set.
        """
        return str(self.raw.get("behavior", ETHER_LIGHTING_BEHAVIOR_SOLID))

    @property
    def led_mode(self) -> str:
        """Get the LED mode ('etherlighting' for on, 'off' for off).

        Returns:
            The led_mode string, defaults to 'etherlighting' if not set.
        """
        return str(self.raw.get("led_mode", ETHER_LIGHTING_LED_MODE_ON))

    @property
    def is_enabled(self) -> bool:
        """Check if Etherlighting is enabled.

        Returns:
            True if led_mode is not 'off', False otherwise.
        """
        return self.led_mode != ETHER_LIGHTING_LED_MODE_OFF

    def to_dict(self) -> dict[str, Any]:
        """Return a shallow copy of the raw dict suitable for API updates.

        Returns:
            Copy of the raw Etherlighting configuration.
        """
        return dict(self.raw)

    def with_enabled(self, enabled: bool) -> dict[str, Any]:
        """Create a new dict with the enabled state changed.

        Preserves existing mode, brightness, and behavior settings.

        Args:
            enabled: True to enable Etherlighting, False to disable.

        Returns:
            New dict with led_mode set appropriately.
        """
        result = self.to_dict()
        result["led_mode"] = ETHER_LIGHTING_LED_MODE_ON if enabled else ETHER_LIGHTING_LED_MODE_OFF
        return result


def has_ether_lighting(device_raw: dict[str, Any]) -> bool:
    """Check if a device has Etherlighting capability.

    Args:
        device_raw: Raw device data from the UniFi API.

    Returns:
        True if the device has ether_lighting configuration.
    """
    return "ether_lighting" in device_raw and isinstance(
        device_raw.get("ether_lighting"), dict
    )


def get_ether_lighting(device_raw: dict[str, Any]) -> EtherLighting | None:
    """Get EtherLighting model from device raw data.

    Args:
        device_raw: Raw device data from the UniFi API.

    Returns:
        EtherLighting instance if device has Etherlighting, None otherwise.
    """
    if has_ether_lighting(device_raw):
        return EtherLighting(device_raw["ether_lighting"])
    return None
