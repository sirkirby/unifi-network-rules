# Tasks: Object-Oriented Network Policies Support

**Input**: Design documents from `/specs/001-oon-policies/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are OPTIONAL - not explicitly requested in specification, but included for completeness.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Home Assistant Integration**: `custom_components/unifi_network_rules/` at repository root
- **Tests**: `tests/` at repository root
- All paths shown are relative to repository root

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and API endpoint constants

- [X] T001 Add OON policy API endpoint constants to `custom_components/unifi_network_rules/constants/api_endpoints.py`
- [X] T002 [P] Add OON policy API path constants to `custom_components/unifi_network_rules/constants/api_endpoints.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Create `OONPolicy` model class in `custom_components/unifi_network_rules/models/oon_policy.py` with `raw`, `id`, `name`, `enabled` properties
- [X] T004 [P] Add `to_api_dict()` method to `OONPolicy` class in `custom_components/unifi_network_rules/models/oon_policy.py`
- [X] T005 [P] Add `has_kill_switch()` helper method to `OONPolicy` class in `custom_components/unifi_network_rules/models/oon_policy.py`
- [X] T006 [P] Create `OONMixin` class in `custom_components/unifi_network_rules/udm/oon.py`
- [X] T007 [P] Implement `get_oon_policies()` method in `OONMixin` class in `custom_components/unifi_network_rules/udm/oon.py` with graceful 404 handling
- [X] T008 [P] Implement `update_oon_policy()` method in `OONMixin` class in `custom_components/unifi_network_rules/udm/oon.py`
- [X] T009 [P] Implement `toggle_oon_policy()` method in `OONMixin` class in `custom_components/unifi_network_rules/udm/oon.py`
- [X] T010 Add `OONPolicy` import to `custom_components/unifi_network_rules/coordinator.py`
- [X] T011 Add `oon_policies` property to coordinator in `custom_components/unifi_network_rules/coordinator.py`
- [X] T012 Add `"oon_policies": self.api.get_oon_policies` to `entity_type_methods` in `custom_components/unifi_network_rules/coordination/data_fetcher.py`
- [X] T013 Add `("oon_policies", "UnifiOONPolicySwitch")` to `_rule_type_entity_map` in `custom_components/unifi_network_rules/coordination/entity_manager.py`
- [X] T014 Add `OONPolicy` case to `get_rule_id()` function in `custom_components/unifi_network_rules/helpers/rule.py` (returns `unr_oon_{id}`)
- [X] T015 [P] Add `OONPolicy` case to `get_rule_name()` function in `custom_components/unifi_network_rules/helpers/rule.py` (returns `name`)
- [X] T016 [P] Add `OONPolicy` case to `get_rule_enabled()` function in `custom_components/unifi_network_rules/helpers/rule.py` (returns `enabled`)
- [X] T017 [P] Add `OONPolicy` case to `get_object_id()` function in `custom_components/unifi_network_rules/helpers/rule.py` (for entity ID generation)

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 2 - Discover and Display OON Policies (Priority: P1) 🎯 MVP Foundation

**Goal**: Users can see all their Object-Oriented Network policies in Home Assistant so they can understand what rules are configured and manage them from a single interface.

**Independent Test**: Verify that all OON policies from the UniFi controller appear as switch entities in Home Assistant after integration setup or refresh. Test with controller that has OON policies and controller that doesn't (404 handling).

### Implementation for User Story 2

- [X] T018 [US2] Create `UnifiOONPolicySwitch` class in `custom_components/unifi_network_rules/switches/oon_policy.py` inheriting from `UnifiRuleSwitch`
- [X] T019 [US2] Set icon to `"mdi:shield-network"` in `UnifiOONPolicySwitch.__init__()` in `custom_components/unifi_network_rules/switches/oon_policy.py`
- [X] T020 [US2] Export `UnifiOONPolicySwitch` from `custom_components/unifi_network_rules/switches/__init__.py`
- [X] T021 [US2] Add `("oon_policies", coordinator.oon_policies or [], UnifiOONPolicySwitch)` to `all_rule_sources` in `custom_components/unifi_network_rules/switches/setup.py`
- [X] T022 [US2] Add `oon_policies` case to `async_create_entity()` function in `custom_components/unifi_network_rules/__init__.py`
- [X] T023 [US2] Import `UnifiOONPolicySwitch` in `custom_components/unifi_network_rules/__init__.py`
- [X] T024 [US2] Add `oon_policies` to change detection in `custom_components/unifi_network_rules/unified_change_detector.py` (if needed)

**Checkpoint**: At this point, User Story 2 should be fully functional - OON policies are discoverable and displayed as switch entities

---

## Phase 4: User Story 1 - Toggle Object-Oriented Network Policies (Priority: P1) 🎯 MVP Core

**Goal**: Users can toggle OON policies ON and OFF through Home Assistant switches to enable automation scenarios like temporary rule overrides.

**Independent Test**: Create a switch entity for an existing OON policy, toggle it on/off, and verify the policy state changes in the UniFi controller. Test successful toggles and API failure scenarios (state reversion).

### Implementation for User Story 1

- [X] T025 [US1] Verify `UnifiOONPolicySwitch` toggle functionality works with base class `async_turn_on()` method in `custom_components/unifi_network_rules/switches/oon_policy.py`
- [X] T026 [US1] Verify `UnifiOONPolicySwitch` toggle functionality works with base class `async_turn_off()` method in `custom_components/unifi_network_rules/switches/oon_policy.py`
- [X] T027 [US1] Ensure optimistic updates work correctly in `UnifiOONPolicySwitch` (inherited from base class)
- [X] T028 [US1] Ensure error handling reverts switch state on API failure in `UnifiOONPolicySwitch` (inherited from base class)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently - users can discover and toggle OON policies

---

## Phase 5: User Story 3 - Automation Integration for Policy Management (Priority: P2)

**Goal**: Users can create Home Assistant automations that automatically enable or disable OON policies based on time schedules, device presence, or other Home Assistant events.

**Independent Test**: Create a Home Assistant automation that toggles an OON policy switch based on a time trigger and verify the policy state changes accordingly. Test multiple simultaneous toggles and unreachable controller scenarios.

### Implementation for User Story 3

- [X] T029 [US3] Verify `UnifiOONPolicySwitch` works correctly when triggered by Home Assistant automations (no changes needed, inherits from base class)
- [X] T030 [US3] Test multiple OON policy switches toggled simultaneously in automation scenarios
- [X] T031 [US3] Verify error handling when UniFi controller is unreachable during automation execution

**Checkpoint**: At this point, User Stories 1, 2, AND 3 should all work independently - users can discover, toggle, and automate OON policies

---

## Phase 6: User Story 4 - Kill Switch Support for Traffic Routing Policies (Priority: P3)

**Goal**: Users can control the kill switch feature for OON policies that include traffic routing functionality, similar to how traffic route switches work today.

**Independent Test**: Create a child kill switch entity for an OON policy that has routing enabled, and verify that toggling the kill switch updates the policy's route.kill_switch property. Test kill switch creation/removal lifecycle.

### Implementation for User Story 4

- [X] T032 [US4] Create `UnifiOONPolicyKillSwitch` class in `custom_components/unifi_network_rules/switches/oon_policy.py` inheriting from `UnifiRuleSwitch`
- [X] T033 [US4] Implement kill switch initialization logic in `UnifiOONPolicyKillSwitch.__init__()` using parent policy ID and `get_child_unique_id()` helper
- [X] T034 [US4] Override name and entity_id for kill switch in `UnifiOONPolicyKillSwitch.__init__()` using `get_child_entity_name()` and `get_child_entity_id()` helpers
- [X] T035 [US4] Implement `async_turn_on()` method in `UnifiOONPolicyKillSwitch` to update `route.kill_switch=True` in `custom_components/unifi_network_rules/switches/oon_policy.py`
- [X] T036 [US4] Implement `async_turn_off()` method in `UnifiOONPolicyKillSwitch` to update `route.kill_switch=False` in `custom_components/unifi_network_rules/switches/oon_policy.py`
- [X] T037 [US4] Export `UnifiOONPolicyKillSwitch` from `custom_components/unifi_network_rules/switches/__init__.py`
- [X] T038 [US4] Add kill switch creation logic to `custom_components/unifi_network_rules/switches/setup.py` (similar to traffic route kill switches)
- [X] T039 [US4] Add kill switch creation logic to `custom_components/unifi_network_rules/__init__.py` in `async_create_entity()` function
- [X] T040 [US4] Import `UnifiOONPolicyKillSwitch` in `custom_components/unifi_network_rules/__init__.py`
- [X] T041 [US4] Implement kill switch entity removal logic when `route.enabled` becomes false or `route.kill_switch` is removed in entity manager

**Checkpoint**: At this point, all user stories should be independently functional - users can discover, toggle, automate, and control kill switches for OON policies

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T042 [P] Run linting tools (Ruff, Flake8) and fix all errors
- [ ] T043 [P] Run type checking (mypy) and resolve type issues (mypy not configured/installed)
- [X] T044 [P] Create unit tests in `tests/test_oon_policy.py` for `OONPolicy` model creation and properties
- [X] T045 [P] Add tests for `has_kill_switch()` method in `tests/test_oon_policy.py`
- [X] T046 [P] Add tests for `to_api_dict()` method in `tests/test_oon_policy.py`
- [X] T047 [P] Add tests for switch entity creation in `tests/test_oon_policy.py` (integration tests included)
- [X] T048 [P] Add tests for kill switch entity creation/removal in `tests/test_oon_policy.py` (integration tests included)
- [X] T049 [P] Add tests for toggle operations in `tests/test_oon_policy.py` (API mixin tests included)
- [X] T050 [P] Add tests for error handling (404, API failures) in `tests/test_oon_policy.py`
- [X] T051 Update `changelog.md` with OON policy support feature description
- [X] T052 Update `README.md` if needed with OON policy feature documentation
- [X] T053 Verify quickstart.md implementation checklist is complete
- [ ] T054 Manual testing with real UniFi controller (with OON policies) - requires manual verification
- [ ] T055 Manual testing with UniFi controller without OON policies (404 handling) - requires manual verification

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 2 (Phase 3)**: Depends on Foundational completion - Discovery must work before toggling
- **User Story 1 (Phase 4)**: Depends on User Story 2 completion - Need entities before toggling
- **User Story 3 (Phase 5)**: Depends on User Story 1 completion - Need toggle functionality for automations
- **User Story 4 (Phase 6)**: Depends on User Story 1 completion - Kill switch extends toggle functionality
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 1 (P1)**: Depends on User Story 2 - Need entities before toggling
- **User Story 3 (P2)**: Depends on User Story 1 - Need toggle functionality for automations
- **User Story 4 (P3)**: Depends on User Story 1 - Kill switch extends toggle functionality

### Within Each User Story

- Models before services
- Services before endpoints/entities
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks (T001-T002) can run in parallel
- All Foundational tasks marked [P] (T003-T009, T015-T017) can run in parallel within Phase 2
- Once Foundational phase completes, User Story 2 can start
- After User Story 2 completes, User Stories 1, 3, and 4 can be planned (though 1 should come before 3 and 4)
- All Polish tasks marked [P] (T042-T050) can run in parallel

---

## Parallel Example: Foundational Phase

```bash
# Launch all model and API tasks together:
Task: "Create OONPolicy model class in custom_components/unifi_network_rules/models/oon_policy.py"
Task: "Add to_api_dict() method to OONPolicy class"
Task: "Add has_kill_switch() helper method to OONPolicy class"
Task: "Create OONMixin class in custom_components/unifi_network_rules/udm/oon.py"
Task: "Implement get_oon_policies() method in OONMixin class"
Task: "Implement update_oon_policy() method in OONMixin class"
Task: "Implement toggle_oon_policy() method in OONMixin class"

# Launch all helper function updates together:
Task: "Add OONPolicy case to get_rule_name() function"
Task: "Add OONPolicy case to get_rule_enabled() function"
Task: "Add OONPolicy case to get_object_id() function"
```

---

## Parallel Example: Polish Phase

```bash
# Launch all testing tasks together:
Task: "Create unit tests in tests/test_oon_policy.py for OONPolicy model"
Task: "Add tests for has_kill_switch() method"
Task: "Add tests for to_api_dict() method"
Task: "Add tests for switch entity creation"
Task: "Add tests for kill switch entity creation/removal"
Task: "Add tests for toggle operations"
Task: "Add tests for error handling"

# Launch all code quality tasks together:
Task: "Run linting tools and fix all errors"
Task: "Run type checking and resolve type issues"
```

---

## Implementation Strategy

### MVP First (User Stories 1 & 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 2 (Discovery)
4. Complete Phase 4: User Story 1 (Toggle)
5. **STOP and VALIDATE**: Test User Stories 1 & 2 independently
6. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 2 → Test independently → Discovery working
3. Add User Story 1 → Test independently → Toggle working (MVP!)
4. Add User Story 3 → Test independently → Automation working
5. Add User Story 4 → Test independently → Kill switch working
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 2 (Discovery)
3. Once User Story 2 is done:
   - Developer A: User Story 1 (Toggle)
   - Developer B: User Story 3 (Automation) - can start after US1
   - Developer C: User Story 4 (Kill Switch) - can start after US1
4. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- User Story 2 (Discovery) must complete before User Story 1 (Toggle)
- User Story 1 (Toggle) must complete before User Stories 3 and 4
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- All tasks include exact file paths for clarity
- Tests are included but optional - can be deferred if needed
