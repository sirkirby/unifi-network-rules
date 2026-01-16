"""Device services for UniFi Network Rules integration.

Provides services for controlling UniFi device features like LED control,
including advanced Etherlighting support for Pro Max switches.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from ..const import DOMAIN, LOGGER
from ..models.ether_lighting import (
    ETHER_LIGHTING_BEHAVIOR_BREATH,
    ETHER_LIGHTING_BEHAVIOR_SOLID,
    ETHER_LIGHTING_LED_MODE_OFF,
    ETHER_LIGHTING_LED_MODE_ON,
    ETHER_LIGHTING_MODE_COLOR,
    ETHER_LIGHTING_MODE_SPEED,
    has_ether_lighting,
)
from .constants import SERVICE_SET_DEVICE_LED

# Schema fields for device LED service
CONF_DEVICE_ID = "device_id"
CONF_ENABLED = "enabled"
CONF_BRIGHTNESS = "brightness"
CONF_MODE = "mode"
CONF_BEHAVIOR = "behavior"

# Valid modes and behaviors for Etherlighting
VALID_ETHER_LIGHTING_MODES = [ETHER_LIGHTING_MODE_SPEED, ETHER_LIGHTING_MODE_COLOR]
VALID_ETHER_LIGHTING_BEHAVIORS = [ETHER_LIGHTING_BEHAVIOR_SOLID, ETHER_LIGHTING_BEHAVIOR_BREATH]

# Schema for set_device_led service
SET_DEVICE_LED_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Required(CONF_ENABLED): cv.boolean,
        vol.Optional(CONF_BRIGHTNESS): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional(CONF_MODE): vol.In(VALID_ETHER_LIGHTING_MODES),
        vol.Optional(CONF_BEHAVIOR): vol.In(VALID_ETHER_LIGHTING_BEHAVIORS),
    }
)


async def async_set_device_led(hass: HomeAssistant, coordinators: dict, call: ServiceCall) -> None:
    """Handle setting device LED state with optional Etherlighting parameters.

    For traditional LED devices, only enabled/disabled is supported.
    For Etherlighting devices (Pro Max switches), brightness, mode, and behavior
    can also be configured.
    """
    device_id = call.data[CONF_DEVICE_ID]
    enabled = call.data[CONF_ENABLED]
    brightness = call.data.get(CONF_BRIGHTNESS)
    mode = call.data.get(CONF_MODE)
    behavior = call.data.get(CONF_BEHAVIOR)

    LOGGER.debug(
        "Set device LED service called: device_id=%s, enabled=%s, brightness=%s, mode=%s, behavior=%s",
        device_id,
        enabled,
        brightness,
        mode,
        behavior,
    )

    if not coordinators:
        raise HomeAssistantError("No UniFi Network Rules coordinators available")

    # Normalize device_id (remove colons if present, lowercase)
    normalized_device_id = device_id.replace(":", "").lower()

    # Find the device across all coordinators
    target_device = None
    target_coordinator = None

    for coordinator in coordinators.values():
        if not coordinator.data or "devices" not in coordinator.data:
            continue

        for device in coordinator.data.get("devices", []):
            device_mac = getattr(device, "mac", "").replace(":", "").lower()
            if device_mac == normalized_device_id:
                target_device = device
                target_coordinator = coordinator
                break

        if target_device:
            break

    if not target_device:
        raise HomeAssistantError(f"Device not found: {device_id}")

    # Get device raw data
    device_raw = getattr(target_device, "raw", {}) if hasattr(target_device, "raw") else {}
    is_etherlighting = has_ether_lighting(device_raw)

    # Validate that advanced options are only used with Etherlighting devices
    if not is_etherlighting and any([brightness is not None, mode is not None, behavior is not None]):
        raise HomeAssistantError(
            f"Device {device_id} does not support Etherlighting. "
            "Brightness, mode, and behavior options are only available for Pro Max switches."
        )

    # Build the update payload
    if is_etherlighting:
        # Start with current ether_lighting config or defaults
        current_ether = device_raw.get("ether_lighting", {})
        new_ether_lighting = {
            "led_mode": ETHER_LIGHTING_LED_MODE_ON if enabled else ETHER_LIGHTING_LED_MODE_OFF,
            "mode": mode if mode is not None else current_ether.get("mode", ETHER_LIGHTING_MODE_SPEED),
            "brightness": brightness if brightness is not None else current_ether.get("brightness", 100),
            "behavior": behavior if behavior is not None else current_ether.get("behavior", ETHER_LIGHTING_BEHAVIOR_SOLID),
        }
        update_payload = {"ether_lighting": new_ether_lighting}
        LOGGER.debug("Etherlighting payload: %s", new_ether_lighting)
    else:
        # Traditional LED device
        update_payload = {"led_override": "on" if enabled else "off"}
        LOGGER.debug("Traditional LED payload: %s", update_payload)

    # Use the coordinator's API to update the device
    try:
        api = target_coordinator.api
        device_id_for_api = target_device.id

        path = f"/rest/device/{device_id_for_api}"
        request = api.create_api_request("PUT", path, data=update_payload, is_v2=False)
        result = await api.controller.request(request)

        if result and isinstance(result, dict):
            meta = result.get("meta", {})
            if meta.get("rc") == "ok":
                LOGGER.info("Device %s LED updated successfully", device_id)
                # Update local state
                if hasattr(target_device, "raw") and target_device.raw:
                    if is_etherlighting:
                        target_device.raw["ether_lighting"] = new_ether_lighting
                    else:
                        target_device.raw["led_override"] = "on" if enabled else "off"
                # Trigger a coordinator refresh to update entity states
                await target_coordinator.async_request_refresh()
            else:
                raise HomeAssistantError(f"API error updating device LED: {meta}")
        else:
            raise HomeAssistantError("Unexpected API response when updating device LED")

    except HomeAssistantError:
        raise
    except Exception as err:
        LOGGER.error("Error setting device LED for %s: %s", device_id, err)
        raise HomeAssistantError(f"Failed to set device LED: {err}") from err


async def async_setup_device_services(hass: HomeAssistant, coordinators: dict) -> None:
    """Set up device-related services."""

    async def handle_set_device_led(call: ServiceCall) -> None:
        await async_set_device_led(hass, coordinators, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DEVICE_LED,
        handle_set_device_led,
        schema=SET_DEVICE_LED_SCHEMA,
    )

    LOGGER.debug("Device services registered: %s", SERVICE_SET_DEVICE_LED)
