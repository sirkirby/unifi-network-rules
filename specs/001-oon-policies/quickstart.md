# Quick Start: Object-Oriented Network Policies Support

**Date**: 2025-11-11  
**Feature**: Object-Oriented Network Policies Support

## Overview

This guide provides a quick reference for implementing Object-Oriented Network (OON) policy support in the UniFi Network Rules integration.

## Implementation Checklist

### Phase 1: Model & API Layer

- [X] Create `custom_components/unifi_network_rules/models/oon_policy.py`
  - [X] Implement `OONPolicy` class with `raw`, `id`, `name`, `enabled` properties
  - [X] Add `to_api_dict()` method for API updates
  - [X] Add `has_kill_switch()` helper method

- [X] Create `custom_components/unifi_network_rules/udm/oon.py`
  - [X] Implement `OONMixin` class
  - [X] Add `get_oon_policies()` method (handle 404 gracefully)
  - [X] Add `update_oon_policy()` method
  - [X] Add `toggle_oon_policy()` method
  - [X] Add `add_oon_policy()` method (POST support)
  - [X] Add `remove_oon_policy()` method (DELETE support)

- [X] Update `custom_components/unifi_network_rules/constants/api_endpoints.py`
  - [X] Add `API_ENDPOINT_OON_POLICIES` constant (plural for GET)
  - [X] Add `API_ENDPOINT_OON_POLICY_DETAIL` constant (singular for PUT/DELETE)
  - [X] Add `API_ENDPOINT_OON_POLICY` constant (singular for POST)
  - [X] Add `API_PATH_OON_POLICIES` constant (plural for GET)
  - [X] Add `API_PATH_OON_POLICY_DETAIL` constant (singular for PUT/DELETE)
  - [X] Add `API_PATH_OON_POLICY` constant (singular for POST)

### Phase 2: Coordinator Integration

- [X] Update `custom_components/unifi_network_rules/coordination/data_fetcher.py`
  - [X] Add `"oon_policies": self.api.get_oon_policies` to `entity_type_methods`

- [X] Update `custom_components/unifi_network_rules/coordination/entity_manager.py`
  - [X] Add `("oon_policies", "UnifiOONPolicySwitch")` to `_rule_type_entity_map`

- [X] Update `custom_components/unifi_network_rules/coordinator.py`
  - [X] Import `OONPolicy` model
  - [X] Add `oon_policies` property to coordinator

### Phase 3: Helper Functions

- [X] Update `custom_components/unifi_network_rules/helpers/rule.py`
  - [X] Add `OONPolicy` case to `get_rule_id()` (returns `unr_oon_{id}`)
  - [X] Add `OONPolicy` case to `get_rule_name()` (returns `name`)
  - [X] Add `OONPolicy` case to `get_rule_enabled()` (returns `enabled`)
  - [X] Add `OONPolicy` case to `get_object_id()` (for entity ID generation)

### Phase 4: Switch Entities

- [X] Create `custom_components/unifi_network_rules/switches/oon_policy.py`
  - [X] Implement `UnifiOONPolicySwitch` class (inherits `UnifiRuleSwitch`)
  - [X] Set icon to `"mdi:shield-network"`
  - [X] Implement `UnifiOONPolicyKillSwitch` class (inherits `UnifiRuleSwitch`)
  - [X] Implement kill switch toggle logic

- [X] Update `custom_components/unifi_network_rules/switches/__init__.py`
  - [X] Export `UnifiOONPolicySwitch` and `UnifiOONPolicyKillSwitch`

- [X] Update `custom_components/unifi_network_rules/switches/setup.py`
  - [X] Add `("oon_policies", coordinator.oon_policies or [], UnifiOONPolicySwitch)` to `all_rule_sources`
  - [X] Add kill switch creation logic (similar to traffic route kill switches)

- [X] Update `custom_components/unifi_network_rules/__init__.py`
  - [X] Add `oon_policies` case to `async_create_entity()` function
  - [X] Import `UnifiOONPolicySwitch` and `UnifiOONPolicyKillSwitch`

### Phase 5: Change Detection & Triggers

- [X] Update `custom_components/unifi_network_rules/unified_change_detector.py`
  - [X] Add `oon_policies` to change detection mapping
  - [X] Add kill switch state snapshot handling
  - [X] Ensure `enabled` property changes are detected

- [X] Update `custom_components/unifi_network_rules/unified_trigger.py`
  - [X] Add `"oon_policy"` to `VALID_CHANGE_TYPES`

### Phase 6: Services Integration

- [X] Update `custom_components/unifi_network_rules/helpers/id_parser.py`
  - [X] Add `"oon_policy": "oon_policies"` type mapping
  - [X] Add `"oon_policies"` to `validate_rule_type()`
  - [X] Add `"oon_policies": "oon_policy"` entity ID mapping

- [X] Update `custom_components/unifi_network_rules/services/rule_services.py`
  - [X] Add OON policy support to `toggle_rule()` service
  - [X] Add OON policy support to `delete_rule()` service
  - [X] Add OON policy support to `bulk_update_rules()` service

- [X] Update `custom_components/unifi_network_rules/services/backup_services.py`
  - [X] Add `"oon_policy"` to restore schema validation
  - [X] Add OON policy restore logic (create/update support)
  - [X] Add OON policy to rule type mapping

### Phase 7: Testing & Documentation

- [X] Create `tests/test_oon_policy.py`
  - [X] Test `OONPolicy` model creation and properties
  - [X] Test `has_kill_switch()` method
  - [X] Test `to_api_dict()` method
  - [X] Test switch entity creation (integration tests)
  - [X] Test kill switch entity creation/removal (integration tests)
  - [X] Test toggle operations (API mixin tests)
  - [X] Test error handling (404, API failures)

- [X] Update `changelog.md` with OON policy support feature description
- [X] Update `README.md` with OON policy feature documentation

## Key Implementation Patterns

### Model Pattern

```python
class OONPolicy:
    def __init__(self, data: Dict[str, Any]) -> None:
        self.raw = data.copy()
        self._id = data.get("id")
        self.name = data.get("name", "")
        self.enabled = data.get("enabled", False)
        # ... other properties
    
    @property
    def id(self) -> str:
        return self._id
    
    def to_api_dict(self) -> Dict[str, Any]:
        return dict(self.raw)
```

### API Mixin Pattern

```python
class OONMixin:
    async def get_oon_policies(self) -> List[OONPolicy]:
        try:
            request = self.create_api_request("GET", API_PATH_OON_POLICIES, is_v2=True)
            response = await self.controller.request(request)
            # Parse response and return List[OONPolicy]
        except Exception as err:
            # Handle 404 gracefully
            if "404" in str(err):
                LOGGER.debug("OON policies endpoint not available")
                return []
            LOGGER.error("Failed to get OON policies: %s", err)
            return []
```

### Switch Pattern

```python
class UnifiOONPolicySwitch(UnifiRuleSwitch):
    def __init__(self, coordinator, rule_data, rule_type, entry_id=None):
        super().__init__(coordinator, rule_data, rule_type, entry_id)
        self._attr_icon = "mdi:shield-network"
```

## Testing Strategy

1. **Unit Tests**: Test model classes, helper functions
2. **Integration Tests**: Test API calls, entity creation
3. **Manual Testing**: Test with real UniFi controller
   - Controller with OON policies
   - Controller without OON policies (404 handling)
   - Toggle operations
   - Kill switch operations

## Common Pitfalls

1. **404 Handling**: Must gracefully handle 404 errors without breaking integration
2. **Kill Switch Detection**: Must check both `route.enabled` AND `route.kill_switch` exists
3. **Unique ID Format**: Must use `unr_oon_<id>` format consistently
4. **Optimistic Updates**: Must revert state on API failure
5. **Entity Cleanup**: Must remove kill switch entities when conditions no longer met

## Next Steps

After implementation:
1. Run linting and fix all errors
2. Run tests and ensure coverage
3. Update `changelog.md` with feature description
4. Update `README.md` if needed
5. Test with real UniFi controller

