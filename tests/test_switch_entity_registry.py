"""Tests for UnifiRuleSwitch entity tracking and in-place entity_id changes (issue #168)."""

import importlib
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_network_rules.const import DOMAIN
from custom_components.unifi_network_rules.switches import base as base_module
from custom_components.unifi_network_rules.switches.base import UnifiRuleSwitch
from custom_components.unifi_network_rules.switches.setup import _CREATED_UNIQUE_IDS


class FakeRegistry:
    """Minimal entity registry double keyed by unique_id."""

    def __init__(self):
        self.entity_ids = {}  # unique_id -> current entity_id
        self.removed = []

    def async_get_entity_id(self, domain, platform, unique_id):
        return self.entity_ids.get(unique_id)

    def async_get(self, entity_id):
        return entity_id if entity_id in self.entity_ids.values() else None

    def async_get_or_create(self, domain, platform, unique_id, **kwargs):
        entity_id = self.entity_ids.setdefault(unique_id, f"switch.{unique_id}")
        return MagicMock(entity_id=entity_id)

    def async_remove(self, entity_id):
        self.removed.append(entity_id)


@pytest.fixture
def registry():
    return FakeRegistry()


@pytest.fixture
def hass_double():
    hass = MagicMock()
    hass.data = {}
    return hass


@pytest.fixture(autouse=True)
def patched_module(registry, hass_double):
    """Patch collaborators on the module the entity uses and keep the tracking set clean."""
    _CREATED_UNIQUE_IDS.clear()
    state = {"subscriptions": 0}

    def fake_connect(hass, signal, target):
        state["subscriptions"] += 1
        removed = []

        def unsub():
            if not removed:
                removed.append(True)
                state["subscriptions"] -= 1

        return unsub

    with (
        patch.object(base_module, "async_get_entity_registry", return_value=registry),
        patch.object(base_module, "async_dispatcher_connect", side_effect=fake_connect),
        patch.object(base_module, "get_rule_id", side_effect=lambda rule: rule.rule_id),
        patch.object(base_module, "get_rule_name", side_effect=lambda rule, coordinator=None: rule.rule_id),
        patch.object(base_module, "get_object_id", side_effect=lambda rule, rule_type: rule.rule_id),
        patch.object(base_module, "generate_entity_id", side_effect=lambda fmt, obj, hass=None: fmt.format(obj)),
        patch.object(UnifiRuleSwitch, "async_write_ha_state", lambda self: None),
    ):
        yield state
    _CREATED_UNIQUE_IDS.clear()


@pytest.fixture
def make_switch(hass_double):
    def _make(rule_id):
        coordinator = MagicMock()
        coordinator.hass = hass_double
        coordinator.known_unique_ids = set()
        coordinator.async_add_listener.return_value = lambda: None
        entity = UnifiRuleSwitch(coordinator, MagicMock(rule_id=rule_id), "test_rule", "entry")
        entity.hass = hass_double
        entity.async_remove = AsyncMock()
        return entity

    return _make


def tracked(hass):
    return hass.data.get(DOMAIN, {}).get("entities", {})


async def run_remove(entity):
    """Mimic Entity.async_remove: will_remove hook, then run async_on_remove callbacks."""
    await entity.async_will_remove_from_hass()
    while entity._on_remove:
        entity._on_remove.pop()()


async def test_add_and_remove_track_by_unique_id(make_switch, hass_double):
    entity = make_switch("unr_test_1")
    await entity.async_added_to_hass()

    assert tracked(hass_double) == {"unr_test_1": entity}
    assert "unr_test_1" in _CREATED_UNIQUE_IDS

    await entity.async_will_remove_from_hass()

    assert tracked(hass_double) == {}
    assert "unr_test_1" not in _CREATED_UNIQUE_IDS


async def test_entity_id_rename_keeps_tracking(make_switch, hass_double):
    entity = make_switch("unr_test_1")
    await entity.async_added_to_hass()

    old_entity_id = entity.entity_id
    entity.entity_id = "switch.renamed"
    entity.async_entity_id_changed(old_entity_id)

    assert list(tracked(hass_double).items()) == [("unr_test_1", entity)]

    await entity.async_will_remove_from_hass()
    assert tracked(hass_double) == {}
    assert "unr_test_1" not in _CREATED_UNIQUE_IDS


async def test_parent_removal_reaches_renamed_child(make_switch, hass_double, registry):
    parent = make_switch("unr_parent")
    child = make_switch("unr_child")
    await parent.async_added_to_hass()
    await child.async_added_to_hass()
    UnifiRuleSwitch.establish_parent_child_relationship(parent, child)

    old = child.entity_id
    child.entity_id = "switch.child_renamed"
    child.async_entity_id_changed(old)
    child.async_initiate_self_removal = AsyncMock()

    await parent.async_initiate_self_removal()

    child.async_initiate_self_removal.assert_awaited_once()
    parent.async_remove.assert_awaited_once_with(force_remove=True)
    assert registry.removed == []


async def test_missing_child_object_removes_registry_entry_by_current_entity_id(make_switch, registry):
    parent = make_switch("unr_parent")
    parent.register_child_entity("unr_child")
    registry.entity_ids["unr_child"] = "switch.child_renamed"
    _CREATED_UNIQUE_IDS.add("unr_child")
    parent.coordinator.known_unique_ids.add("unr_child")

    await parent.async_initiate_self_removal()

    assert registry.removed == ["switch.child_renamed"]
    assert "unr_child" not in _CREATED_UNIQUE_IDS
    assert "unr_child" not in parent.coordinator.known_unique_ids
    assert parent.linked_child_ids == set()
    parent.async_remove.assert_awaited_once_with(force_remove=True)


async def test_child_removal_error_does_not_abort_parent(make_switch, hass_double):
    parent = make_switch("unr_parent")
    child = make_switch("unr_child")
    await parent.async_added_to_hass()
    await child.async_added_to_hass()
    UnifiRuleSwitch.establish_parent_child_relationship(parent, child)
    child.async_initiate_self_removal = AsyncMock(side_effect=RuntimeError("boom"))

    await parent.async_initiate_self_removal()  # must not raise (e.g. UnboundLocalError)

    child.async_initiate_self_removal.assert_awaited_once()
    parent.async_remove.assert_awaited_once_with(force_remove=True)


async def test_remove_then_readd_restores_tracking_without_leaking_subscriptions(
    make_switch, hass_double, patched_module
):
    entity = make_switch("unr_test_1")

    await entity.async_added_to_hass()
    first_dispatcher = patched_module["subscriptions"]
    first_listeners = entity.coordinator.async_add_listener.call_count
    assert first_dispatcher > 0

    await run_remove(entity)
    assert tracked(hass_double) == {}
    assert patched_module["subscriptions"] == 0

    await entity.async_added_to_hass()

    assert tracked(hass_double) == {"unr_test_1": entity}
    assert "unr_test_1" in _CREATED_UNIQUE_IDS
    assert patched_module["subscriptions"] == first_dispatcher
    assert entity.coordinator.async_add_listener.call_count == first_listeners * 2


def test_entity_id_changed_hook_tolerates_missing_base_method(make_switch):
    entity = make_switch("unr_test_1")
    # Pinned/minimum HA has no base async_entity_id_changed; the hook must still be safe.
    for klass in type(entity).__mro__[1:]:
        if "async_entity_id_changed" in vars(klass):
            pytest.skip("installed Home Assistant defines async_entity_id_changed")
    entity.async_entity_id_changed("switch.old")


def test_entity_id_changed_hook_forwards_to_base_once(make_switch):
    entity = make_switch("unr_test_1")
    base_hook = MagicMock()
    with patch.object(base_module.CoordinatorEntity, "async_entity_id_changed", base_hook, create=True):
        entity.async_entity_id_changed("switch.old")

    base_hook.assert_called_once_with("switch.old")


def _concrete_switch_classes():
    classes = {UnifiRuleSwitch}
    package = "custom_components.unifi_network_rules.switches"
    for name in (
        "device", "firewall", "nat", "network", "oon_policy", "port_forwarding", "port_profile",
        "qos", "static_route", "traffic_route", "vpn",
    ):  # fmt: skip
        module = importlib.import_module(f"{package}.{name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, UnifiRuleSwitch) and obj.__module__ == module.__name__:
                classes.add(obj)
    return sorted(classes, key=lambda c: c.__name__)


def test_no_switch_class_requires_readd():
    try:
        from homeassistant.helpers.entity import _entity_class_requires_readd
    except ImportError:
        pytest.skip("installed Home Assistant has no _entity_class_requires_readd (needs 2026.11+)")

    classes = _concrete_switch_classes()
    assert len(classes) > 1
    for klass in classes:
        assert _entity_class_requires_readd(klass) is False, klass.__name__
