# Research: Object-Oriented Network Policies Support

**Date**: 2025-11-11  
**Feature**: Object-Oriented Network Policies Support  
**Phase**: Phase 0 - Research & Decision Making

## Research Tasks & Findings

### 1. Custom Model Pattern Analysis

**Task**: Research how custom models are implemented in UNR for types not supported by aiounifi

**Decision**: Use custom model class pattern similar to `QoSRule` and `NATRule`

**Rationale**: 
- Existing custom models (`QoSRule`, `NATRule`, `StaticRoute`, `PortProfile`) follow consistent patterns
- Models store raw API data in `self.raw` dict for flexibility
- Models expose typed properties for key fields (`id`, `enabled`, `name`)
- Models provide `to_dict()` or `to_api_dict()` methods for API updates
- This pattern maintains consistency with existing codebase

**Alternatives Considered**:
- Extending aiounifi models: Rejected - aiounifi doesn't have OON policy support, and extending external library would create maintenance burden
- Using raw dicts only: Rejected - violates type safety principle, makes code harder to maintain
- Creating aiounifi-compatible wrapper: Rejected - unnecessary complexity, custom models are simpler

**References**:
- `custom_components/unifi_network_rules/models/qos_rule.py`
- `custom_components/unifi_network_rules/models/nat_rule.py`
- `custom_components/unifi_network_rules/models/static_route.py`

### 2. UDM API Integration Pattern

**Task**: Research how UDM API mixins are structured for custom entity types

**Decision**: Create `OONMixin` class following `QoSMixin` and `NATMixin` patterns

**Rationale**:
- Mixins provide `get_oon_policies()`, `update_oon_policy()`, `toggle_oon_policy()` methods
- Methods use `create_api_request()` helper with `is_v2=True` for v2 API endpoints
- Error handling follows existing patterns (try/except with logging)
- Methods return typed model instances (`OONPolicy`) not raw dicts

**Alternatives Considered**:
- Direct API calls in coordinator: Rejected - violates separation of concerns, duplicates code
- Single monolithic API class: Rejected - violates DRY, existing mixin pattern is cleaner

**References**:
- `custom_components/unifi_network_rules/udm/qos.py`
- `custom_components/unifi_network_rules/udm/nat.py`
- `custom_components/unifi_network_rules/udm/traffic.py`

### 3. Switch Entity Pattern

**Task**: Research how switch entities are created for custom rule types

**Decision**: Create `UnifiOONPolicySwitch` inheriting from `UnifiRuleSwitch` base class

**Rationale**:
- Base class provides optimistic updates, error handling, state management
- Subclasses only need to override icon and any custom behavior
- Kill switch entities follow `UnifiTrafficRouteKillSwitch` pattern
- Entity creation integrated through `async_create_entity()` function

**Alternatives Considered**:
- Creating switch from scratch: Rejected - violates DRY, base class provides all needed functionality
- Using generic switch class: Rejected - loses type safety and custom behavior

**References**:
- `custom_components/unifi_network_rules/switches/base.py`
- `custom_components/unifi_network_rules/switches/traffic_route.py`
- `custom_components/unifi_network_rules/__init__.py` (async_create_entity)

### 4. Coordinator Integration Pattern

**Task**: Research how new entity types are integrated into coordinator data fetching

**Decision**: Add `oon_policies` to `entity_type_methods` mapping and `rule_type_entity_map`

**Rationale**:
- Coordinator uses `entity_type_methods` dict to map entity types to API methods
- Entity manager uses `rule_type_entity_map` to map rule types to entity classes
- Integration requires minimal changes to existing coordinator code
- Follows established pattern for all 12+ existing entity types

**Alternatives Considered**:
- Creating separate coordinator: Rejected - unnecessary complexity, existing coordinator handles all types
- Modifying coordinator core logic: Rejected - violates open/closed principle, mapping approach is extensible

**References**:
- `custom_components/unifi_network_rules/coordination/data_fetcher.py`
- `custom_components/unifi_network_rules/coordination/entity_manager.py`

### 5. Helper Function Integration

**Task**: Research how helper functions support custom rule types

**Decision**: Extend `get_rule_id()`, `get_rule_name()`, `get_rule_enabled()` in `helpers/rule.py`

**Rationale**:
- Helper functions provide consistent rule identification across entity types
- `get_rule_id()` returns `unr_oon_<policy_id>` format
- `get_rule_name()` extracts display name from policy
- `get_rule_enabled()` reads enabled state
- Pattern matches existing implementations for all rule types

**Alternatives Considered**:
- Per-entity-type helpers: Rejected - violates DRY, central helpers are cleaner
- No helpers: Rejected - would duplicate code across switch classes

**References**:
- `custom_components/unifi_network_rules/helpers/rule.py`

### 6. API Endpoint Constants

**Task**: Research API endpoint constant patterns

**Decision**: Add OON policy endpoints to `constants/api_endpoints.py` following existing patterns

**Rationale**:
- Constants file centralizes all API endpoint definitions
- Both full endpoint paths and API path fragments needed
- Follows pattern: `API_ENDPOINT_*` for full paths, `API_PATH_*` for fragments
- Enables consistent endpoint usage across codebase

**Alternatives Considered**:
- Hardcoding endpoints: Rejected - violates DRY, makes updates difficult
- Separate constants file: Rejected - unnecessary, existing file handles all endpoints

**References**:
- `custom_components/unifi_network_rules/constants/api_endpoints.py`

### 7. Kill Switch Entity Pattern

**Task**: Research how child entities (kill switches) are created and managed

**Decision**: Follow `UnifiTrafficRouteKillSwitch` pattern for OON policy kill switches

**Rationale**:
- Kill switch entities are child entities with parent/child relationships
- Use `get_child_unique_id()` helper to generate unique IDs
- Override name and entity_id in `__init__` after calling super()
- Lifecycle managed through entity manager's parent/child linking

**Alternatives Considered**:
- Separate entity type: Rejected - kill switches are logically children of policy switches
- Generic child entity class: Rejected - kill switches have specific behavior, custom class needed

**References**:
- `custom_components/unifi_network_rules/switches/traffic_route.py` (UnifiTrafficRouteKillSwitch)
- `custom_components/unifi_network_rules/helpers/rule.py` (get_child_unique_id)

### 8. Error Handling for Unsupported Controllers

**Task**: Research how to handle controllers that don't support OON policies

**Decision**: Gracefully handle 404 errors by catching exceptions and returning empty list

**Rationale**:
- 404 errors indicate endpoint doesn't exist (unsupported controller version)
- Catching exception allows integration to continue with other entity types
- Debug logging provides visibility without user-facing errors
- Matches pattern used for optional features in other integrations

**Alternatives Considered**:
- Failing integration setup: Rejected - too strict, breaks integration for users without OON support
- Warning users: Rejected - creates noise, silent skip is better UX
- Version checking: Rejected - unreliable, endpoint existence is better indicator

**References**:
- Specification clarification: "Gracefully handle 404/endpoint not found errors - skip OON policy discovery silently, log debug message, continue with other entity types"

## Summary

All research tasks completed. Implementation will follow established UNR patterns:
- Custom model class (`OONPolicy`) in `models/oon_policy.py`
- UDM API mixin (`OONMixin`) in `udm/oon.py`
- Switch entities (`UnifiOONPolicySwitch`, `UnifiOONPolicyKillSwitch`) in `switches/oon_policy.py`
- Coordinator integration through existing mapping mechanisms
- Helper function extensions for rule identification
- API endpoint constants following existing patterns
- Graceful error handling for unsupported controllers

No architectural changes required - pure extension of existing patterns.

