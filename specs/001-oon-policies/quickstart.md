# Quick Start: Object-Oriented Network Policies Support

**Date**: 2025-11-11  
**Feature**: Object-Oriented Network Policies Support

## Overview

This guide provides a quick reference for implementing Object-Oriented Network (OON) policy support in the UniFi Network Rules integration.

## Implementation Checklist

### Phase 1: Model & API Layer

- [ ] Create `custom_components/unifi_network_rules/models/oon_policy.py`
  - [ ] Implement `OONPolicy` class with `raw`, `id`, `name`, `enabled` properties
  - [ ] Add `to_api_dict()` method for API updates
  - [ ] Add `has_kill_switch()` helper method

- [ ] Create `custom_components/unifi_network_rules/udm/oon.py`
  - [ ] Implement `OONMixin` class
  - [ ] Add `get_oon_policies()` method (handle 404 gracefully)
  - [ ] Add `update_oon_policy()` method
  - [ ] Add `toggle_oon_policy()` method

- [ ] Update `custom_components/unifi_network_rules/constants/api_endpoints.py`
  - [ ] Add `API_ENDPOINT_OON_POLICIES` constant
  - [ ] Add `API_ENDPOINT_OON_POLICY_DETAIL` constant
  - [ ] Add `API_PATH_OON_POLICIES` constant
  - [ ] Add `API_PATH_OON_POLICY_DETAIL` constant

### Phase 2: Coordinator Integration

- [ ] Update `custom_components/unifi_network_rules/coordination/data_fetcher.py`
  - [ ] Add `"oon_policies": self.api.get_oon_policies` to `entity_type_methods`

- [ ] Update `custom_components/unifi_network_rules/coordination/entity_manager.py`
  - [ ] Add `("oon_policies", "UnifiOONPolicySwitch")` to `_rule_type_entity_map`

- [ ] Update `custom_components/unifi_network_rules/coordinator.py`
  - [ ] Import `OONPolicy` model
  - [ ] Add `oon_policies` property to coordinator

### Phase 3: Helper Functions

- [ ] Update `custom_components/unifi_network_rules/helpers/rule.py`
  - [ ] Add `OONPolicy` case to `get_rule_id()` (returns `unr_oon_{id}`)
  - [ ] Add `OONPolicy` case to `get_rule_name()` (returns `name`)
  - [ ] Add `OONPolicy` case to `get_rule_enabled()` (returns `enabled`)
  - [ ] Add `OONPolicy` case to `get_object_id()` (for entity ID generation)

### Phase 4: Switch Entities

- [ ] Create `custom_components/unifi_network_rules/switches/oon_policy.py`
  - [ ] Implement `UnifiOONPolicySwitch` class (inherits `UnifiRuleSwitch`)
  - [ ] Set icon to `"mdi:shield-network"` or appropriate icon
  - [ ] Implement `UnifiOONPolicyKillSwitch` class (inherits `UnifiRuleSwitch`)
  - [ ] Implement kill switch toggle logic

- [ ] Update `custom_components/unifi_network_rules/switches/__init__.py`
  - [ ] Export `UnifiOONPolicySwitch` and `UnifiOONPolicyKillSwitch`

- [ ] Update `custom_components/unifi_network_rules/switches/setup.py`
  - [ ] Add `("oon_policies", coordinator.oon_policies or [], UnifiOONPolicySwitch)` to `all_rule_sources`
  - [ ] Add kill switch creation logic (similar to traffic route kill switches)

- [ ] Update `custom_components/unifi_network_rules/__init__.py`
  - [ ] Add `oon_policies` case to `async_create_entity()` function
  - [ ] Import `UnifiOONPolicySwitch` and `UnifiOONPolicyKillSwitch`

### Phase 5: Change Detection

- [ ] Update `custom_components/unifi_network_rules/unified_change_detector.py`
  - [ ] Add `oon_policies` to change detection (if needed)
  - [ ] Ensure `enabled` property changes are detected

### Phase 6: Testing

- [ ] Create `tests/test_oon_policy.py`
  - [ ] Test `OONPolicy` model creation and properties
  - [ ] Test `has_kill_switch()` method
  - [ ] Test `to_api_dict()` method
  - [ ] Test switch entity creation
  - [ ] Test kill switch entity creation/removal
  - [ ] Test toggle operations
  - [ ] Test error handling (404, API failures)

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

