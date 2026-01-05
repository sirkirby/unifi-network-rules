"""Tests for NAT rules support (model, API mixin, switch, mappings)."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.unifi_network_rules.models.nat_rule import NATRule
from custom_components.unifi_network_rules.switch import UnifiNATRuleSwitch
from custom_components.unifi_network_rules.udm.nat import NATMixin
from custom_components.unifi_network_rules.unified_change_detector import UnifiedChangeDetector
from custom_components.unifi_network_rules.unified_trigger import VALID_CHANGE_TYPES


@pytest.fixture
def nat_rule_payload():
    return {
        "_id": "68b6eef7dd411xxxxxxxxx",
        "description": "source nat test",
        "destination_filter": {
            "address": "10.1.9.5",
            "filter_type": "ADDRESS_AND_PORT",
            "firewall_group_ids": [],
            "invert_address": False,
            "invert_port": False,
        },
        "enabled": False,
        "exclude": False,
        "ip_address": "100.6.6.6",
        "ip_version": "IPV4",
        "is_predefined": False,
        "logging": False,
        "out_interface": "67b4f927xxxxxxxxx",
        "pppoe_use_base_interface": False,
        "protocol": "all",
        "rule_index": 0,
        "setting_preference": "manual",
        "source_filter": {
            "filter_type": "NONE",
            "firewall_group_ids": [],
            "invert_address": False,
            "invert_port": False,
        },
        "type": "SNAT",
    }


class TestNATRuleModel:
    def test_nat_rule_defaults_and_properties(self, nat_rule_payload):
        rule = NATRule(nat_rule_payload)
        assert rule.id == nat_rule_payload["_id"]
        assert rule.description == "source nat test"
        assert rule.enabled is False
        assert rule.is_custom() is True
        assert rule.type == "SNAT"
        assert rule.ip_version == "IPV4"
        assert rule.ip_address == "100.6.6.6"
        # Naming suffix is a heuristic; ensure it's non-empty
        assert isinstance(rule.display_suffix(), str)
        assert rule.display_suffix() != ""

    def test_nat_rule_predefined_filter(self, nat_rule_payload):
        data = dict(nat_rule_payload)
        data["is_predefined"] = True
        rule = NATRule(data)
        assert rule.is_custom() is False


class TestNATMixin:
    @pytest.mark.asyncio
    async def test_get_nat_rules_filters_predefined(self, nat_rule_payload):
        mixin = NATMixin()
        mixin.controller = AsyncMock()

        # Include both custom and predefined
        custom = dict(nat_rule_payload)
        system = dict(nat_rule_payload)
        system["_id"] = "sys1"
        system["is_predefined"] = True
        mixin.controller.request = AsyncMock(return_value={"data": [custom, system]})

        rules = await mixin.get_nat_rules()
        assert len(rules) == 1
        assert isinstance(rules[0], NATRule)
        assert rules[0].id == custom["_id"]

    @pytest.mark.asyncio
    async def test_update_nat_rule(self, nat_rule_payload):
        mixin = NATMixin()
        mixin.controller = AsyncMock()
        rule = NATRule(nat_rule_payload)

        ok = await mixin.update_nat_rule(rule)
        assert ok is True
        assert mixin.controller.request.await_count == 1

    @pytest.mark.asyncio
    async def test_toggle_nat_rule(self, nat_rule_payload):
        mixin = NATMixin()
        mixin.controller = AsyncMock()
        rule = NATRule(nat_rule_payload)
        assert rule.enabled is False
        # Pass explicit target_state to enable the rule
        ok = await mixin.toggle_nat_rule(rule, target_state=True)
        assert ok is True
        assert rule.enabled is True


class TestNATMappings:
    def test_change_detector_mapping_includes_nat(self):
        detector = UnifiedChangeDetector(Mock(), Mock())
        assert "nat_rules" in detector._rule_type_mapping
        assert detector._rule_type_mapping["nat_rules"] == "nat"

    def test_trigger_valid_change_types_includes_nat(self):
        assert "nat" in VALID_CHANGE_TYPES


class TestUnifiNATRuleSwitch:
    def test_icon_selection_by_type(self, nat_rule_payload):
        # SNAT
        from custom_components.unifi_network_rules.coordinator import UnifiRuleUpdateCoordinator

        coordinator = Mock(spec=UnifiRuleUpdateCoordinator)
        coordinator.hass = Mock()
        coordinator.api = Mock()
        coordinator.api.host = "test-host"
        rule = NATRule(nat_rule_payload)
        switch = UnifiNATRuleSwitch(coordinator, rule, "nat_rules")
        assert switch._attr_icon in ("mdi:swap-horizontal", "mdi:swap-horizontal-bold")

        # DNAT
        dnat = dict(nat_rule_payload)
        dnat["type"] = "DNAT"
        dnat_rule = NATRule(dnat)
        switch2 = UnifiNATRuleSwitch(coordinator, dnat_rule, "nat_rules")
        assert switch2._attr_icon == "mdi:swap-vertical"
