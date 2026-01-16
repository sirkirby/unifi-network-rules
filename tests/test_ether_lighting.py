"""Tests for Etherlighting support (model, discovery, state logic)."""


import pytest

from custom_components.unifi_network_rules.models.ether_lighting import (
    ETHER_LIGHTING_BEHAVIOR_BREATH,
    ETHER_LIGHTING_BEHAVIOR_SOLID,
    ETHER_LIGHTING_LED_MODE_OFF,
    ETHER_LIGHTING_LED_MODE_ON,
    ETHER_LIGHTING_MODE_COLOR,
    ETHER_LIGHTING_MODE_SPEED,
    EtherLighting,
    get_ether_lighting,
    has_ether_lighting,
)


@pytest.fixture
def etherlighting_payload():
    """Sample Etherlighting configuration payload."""
    return {
        "mode": "speed",
        "brightness": 95,
        "behavior": "breath",
        "led_mode": "etherlighting",
    }


@pytest.fixture
def etherlighting_off_payload():
    """Etherlighting configuration with LED off."""
    return {
        "mode": "speed",
        "brightness": 50,
        "behavior": "solid",
        "led_mode": "off",
    }


@pytest.fixture
def device_with_etherlighting(etherlighting_payload):
    """Device raw data with Etherlighting."""
    return {
        "_id": "device123",
        "device_id": "device123",
        "mac": "aa:bb:cc:dd:ee:ff",
        "name": "Pro Max 48-PoE",
        "type": "usw",
        "model": "USWPROMAX48POE",
        "ether_lighting": etherlighting_payload,
    }


@pytest.fixture
def device_with_led_override():
    """Traditional device with LED override."""
    return {
        "_id": "device456",
        "device_id": "device456",
        "mac": "11:22:33:44:55:66",
        "name": "U6-Enterprise",
        "type": "uap",
        "model": "U6E",
        "led_override": "on",
    }


class TestEtherLightingModel:
    """Test EtherLighting model creation and properties."""

    def test_etherlighting_defaults_and_properties(self, etherlighting_payload):
        """Test EtherLighting model creation and basic properties."""
        ether = EtherLighting(etherlighting_payload)
        assert ether.mode == "speed"
        assert ether.brightness == 95
        assert ether.behavior == "breath"
        assert ether.led_mode == "etherlighting"
        assert ether.is_enabled is True

    def test_etherlighting_off_state(self, etherlighting_off_payload):
        """Test EtherLighting when LED is off."""
        ether = EtherLighting(etherlighting_off_payload)
        assert ether.mode == "speed"
        assert ether.brightness == 50
        assert ether.behavior == "solid"
        assert ether.led_mode == "off"
        assert ether.is_enabled is False

    def test_etherlighting_minimal_data(self):
        """Test EtherLighting with minimal required data."""
        minimal_data = {}
        ether = EtherLighting(minimal_data)
        assert ether.mode == ETHER_LIGHTING_MODE_SPEED  # Default
        assert ether.brightness == 100  # Default
        assert ether.behavior == ETHER_LIGHTING_BEHAVIOR_SOLID  # Default
        assert ether.led_mode == ETHER_LIGHTING_LED_MODE_ON  # Default
        assert ether.is_enabled is True

    def test_etherlighting_brightness_clamping(self):
        """Test brightness value is clamped to 0-100."""
        # Test above 100
        ether = EtherLighting({"brightness": 150})
        assert ether.brightness == 100

        # Test below 0
        ether = EtherLighting({"brightness": -10})
        assert ether.brightness == 0

        # Test invalid value
        ether = EtherLighting({"brightness": "invalid"})
        assert ether.brightness == 100  # Default on error

    def test_to_dict(self, etherlighting_payload):
        """Test to_dict() returns correct dictionary copy."""
        ether = EtherLighting(etherlighting_payload)
        result = ether.to_dict()
        assert isinstance(result, dict)
        assert result == etherlighting_payload
        # Ensure it's a copy
        result["mode"] = "modified"
        assert ether.mode == "speed"

    def test_with_enabled_true(self, etherlighting_off_payload):
        """Test with_enabled(True) creates correct payload."""
        ether = EtherLighting(etherlighting_off_payload)
        result = ether.with_enabled(True)
        assert result["led_mode"] == ETHER_LIGHTING_LED_MODE_ON
        # Original settings preserved
        assert result["mode"] == "speed"
        assert result["brightness"] == 50
        assert result["behavior"] == "solid"

    def test_with_enabled_false(self, etherlighting_payload):
        """Test with_enabled(False) creates correct payload."""
        ether = EtherLighting(etherlighting_payload)
        result = ether.with_enabled(False)
        assert result["led_mode"] == ETHER_LIGHTING_LED_MODE_OFF
        # Original settings preserved
        assert result["mode"] == "speed"
        assert result["brightness"] == 95
        assert result["behavior"] == "breath"


class TestEtherLightingHelpers:
    """Test helper functions for Etherlighting detection."""

    def test_has_ether_lighting_true(self, device_with_etherlighting):
        """Test has_ether_lighting returns True for Etherlighting device."""
        assert has_ether_lighting(device_with_etherlighting) is True

    def test_has_ether_lighting_false_no_key(self, device_with_led_override):
        """Test has_ether_lighting returns False for traditional device."""
        assert has_ether_lighting(device_with_led_override) is False

    def test_has_ether_lighting_false_invalid_value(self):
        """Test has_ether_lighting returns False when value is not a dict."""
        device = {"ether_lighting": "invalid"}
        assert has_ether_lighting(device) is False

        device = {"ether_lighting": None}
        assert has_ether_lighting(device) is False

    def test_has_ether_lighting_empty_dict(self):
        """Test has_ether_lighting returns True for empty dict value."""
        device = {"ether_lighting": {}}
        assert has_ether_lighting(device) is True

    def test_get_ether_lighting_success(self, device_with_etherlighting):
        """Test get_ether_lighting returns model for Etherlighting device."""
        result = get_ether_lighting(device_with_etherlighting)
        assert result is not None
        assert isinstance(result, EtherLighting)
        assert result.mode == "speed"
        assert result.brightness == 95

    def test_get_ether_lighting_none_for_traditional(self, device_with_led_override):
        """Test get_ether_lighting returns None for traditional device."""
        result = get_ether_lighting(device_with_led_override)
        assert result is None


class TestEtherLightingConstants:
    """Test Etherlighting constants are properly defined."""

    def test_mode_constants(self):
        """Test mode constants."""
        assert ETHER_LIGHTING_MODE_SPEED == "speed"
        assert ETHER_LIGHTING_MODE_COLOR == "color"

    def test_behavior_constants(self):
        """Test behavior constants."""
        assert ETHER_LIGHTING_BEHAVIOR_SOLID == "solid"
        assert ETHER_LIGHTING_BEHAVIOR_BREATH == "breath"

    def test_led_mode_constants(self):
        """Test LED mode constants."""
        assert ETHER_LIGHTING_LED_MODE_ON == "etherlighting"
        assert ETHER_LIGHTING_LED_MODE_OFF == "off"


class TestEtherLightingStateLogic:
    """Test Etherlighting integration with state logic."""

    def test_get_rule_enabled_etherlighting_on(self, device_with_etherlighting):
        """Test get_rule_enabled returns True for Etherlighting device with LED on."""
        from aiounifi.models.device import Device

        from custom_components.unifi_network_rules.helpers.rule import get_rule_enabled

        device = Device(device_with_etherlighting)
        assert get_rule_enabled(device) is True

    def test_get_rule_enabled_etherlighting_off(self, device_with_etherlighting):
        """Test get_rule_enabled returns False for Etherlighting device with LED off."""
        from aiounifi.models.device import Device

        from custom_components.unifi_network_rules.helpers.rule import get_rule_enabled

        # Modify the fixture to have LED off
        device_with_etherlighting["ether_lighting"]["led_mode"] = "off"
        device = Device(device_with_etherlighting)
        assert get_rule_enabled(device) is False

    def test_get_rule_enabled_traditional_on(self, device_with_led_override):
        """Test get_rule_enabled returns True for traditional device with LED on."""
        from aiounifi.models.device import Device

        from custom_components.unifi_network_rules.helpers.rule import get_rule_enabled

        device = Device(device_with_led_override)
        assert get_rule_enabled(device) is True

    def test_get_rule_enabled_traditional_off(self, device_with_led_override):
        """Test get_rule_enabled returns False for traditional device with LED off."""
        from aiounifi.models.device import Device

        from custom_components.unifi_network_rules.helpers.rule import get_rule_enabled

        device_with_led_override["led_override"] = "off"
        device = Device(device_with_led_override)
        assert get_rule_enabled(device) is False
