# Feature Specification: Object-Oriented Network Policies Support

**Feature Branch**: `001-oon-policies`  
**Created**: 2025-11-11  
**Status**: Draft  
**Input**: User description: "we are going to build support the new object oriented networking configuration support in UniFi network. The user reported the issue and made the feature request in https://github.com/sirkirby/unifi-network-rules/issues/129  and i created a sub issue with some key implementation requirements and details in https://github.com/sirkirby/unifi-network-rules/issues/130"

## Clarifications

### Session 2025-11-11

- Q: What unique ID format should be used for OON policy switch entities? → A: Use `unr_oon_<policy_id>` format (e.g., `unr_oon_123456`) to match existing UNR conventions
- Q: What API method and endpoint pattern should be used for updating OON policies? → A: Use PUT method with individual policy detail endpoint `/proxy/network/v2/api/site/{site}/object-oriented-network-configs/{policy_id}` (matches existing rule update patterns)
- Q: How should the system handle UniFi controllers that don't support OON policies? → A: Gracefully handle 404/endpoint not found errors - skip OON policy discovery silently, log debug message, continue with other entity types
- Q: How should kill switch entities be detected and managed? → A: Check `route.enabled` is true AND `route.kill_switch` property exists/is boolean - create kill switch entity only when both conditions met. Remove existing kill switch entity if route.kill_switch is no longer enabled on subsequent updates

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Toggle Object-Oriented Network Policies (Priority: P1)

A parent wants to temporarily disable an app blocking rule (e.g., YouTube blocking) for their child during a specific time period. They use Home Assistant to create an automation that disables the blocking rule for 15 minutes when a button is pressed, then automatically re-enables it.

**Why this priority**: This is the core functionality requested in the feature request. Users need the ability to toggle OON policies via Home Assistant switches to enable automation scenarios like temporary rule overrides.

**Independent Test**: Can be fully tested by creating a switch entity for an existing OON policy, toggling it on/off, and verifying the policy state changes in the UniFi controller. This delivers immediate value by enabling basic policy control through Home Assistant.

**Acceptance Scenarios**:

1. **Given** a UniFi controller has Object-Oriented Network policies configured, **When** the integration discovers these policies, **Then** a switch entity is created for each policy with the policy name displayed
2. **Given** an OON policy switch entity exists in Home Assistant, **When** a user turns the switch ON, **Then** the policy's enabled state is set to true in UniFi and the switch reflects the new state optimistically
3. **Given** an OON policy switch entity exists in Home Assistant, **When** a user turns the switch OFF, **Then** the policy's enabled state is set to false in UniFi and the switch reflects the new state optimistically
4. **Given** an OON policy switch is toggled, **When** the API call completes successfully, **Then** the switch state is confirmed and updated from the controller response
5. **Given** an OON policy switch is toggled, **When** the API call fails, **Then** the switch reverts to its previous state and an error is logged

---

### User Story 2 - Discover and Display OON Policies (Priority: P1)

A user wants to see all their Object-Oriented Network policies in Home Assistant so they can understand what rules are configured and manage them from a single interface.

**Why this priority**: Discovery is foundational - users cannot interact with policies if they are not visible. This must work correctly for the feature to be usable.

**Independent Test**: Can be fully tested by verifying that all OON policies from the UniFi controller appear as switch entities in Home Assistant after integration setup or refresh. This delivers value by providing visibility into existing policy configurations.

**Acceptance Scenarios**:

1. **Given** a UniFi controller has OON policies configured, **When** the integration performs a data refresh, **Then** all policies are fetched from the API endpoint and switch entities are created for each
2. **Given** a new OON policy is created in UniFi, **When** the integration performs its next refresh, **Then** a new switch entity appears in Home Assistant for the new policy
3. **Given** an OON policy is deleted in UniFi, **When** the integration performs its next refresh, **Then** the corresponding switch entity is removed from Home Assistant
4. **Given** an OON policy name is changed in UniFi, **When** the integration performs its next refresh, **Then** the switch entity name is updated to match the new policy name

---

### User Story 3 - Automation Integration for Policy Management (Priority: P2)

A user wants to create Home Assistant automations that automatically enable or disable OON policies based on time schedules, device presence, or other Home Assistant events.

**Why this priority**: While basic toggle functionality is P1, automation integration enables the advanced use cases mentioned in the feature request (e.g., scheduled blocking, temporary overrides). This extends the value significantly.

**Independent Test**: Can be fully tested by creating a Home Assistant automation that toggles an OON policy switch based on a time trigger and verifying the policy state changes accordingly. This delivers value by enabling complex policy management workflows.

**Acceptance Scenarios**:

1. **Given** an OON policy switch exists, **When** a Home Assistant automation triggers the switch to turn ON, **Then** the policy is enabled in UniFi
2. **Given** an OON policy switch exists, **When** a Home Assistant automation triggers the switch to turn OFF, **Then** the policy is disabled in UniFi
3. **Given** multiple OON policy switches exist, **When** an automation triggers multiple switches simultaneously, **Then** all policies update correctly without conflicts
4. **Given** an automation is configured to toggle an OON policy switch, **When** the UniFi controller is unreachable, **Then** the automation completes without error and the switch state reflects the failure appropriately

---

### User Story 4 - Kill Switch Support for Traffic Routing Policies (Priority: P3)

A user wants to control the kill switch feature for OON policies that include traffic routing functionality, similar to how traffic route switches work today.

**Why this priority**: This is an optional enhancement mentioned in the requirements. While not essential for basic policy toggling, it provides additional control for policies with routing features. This can be deferred if needed for MVP.

**Independent Test**: Can be fully tested by creating a child kill switch entity for an OON policy that has routing enabled, and verifying that toggling the kill switch updates the policy's route.kill_switch property. This delivers value by enabling granular control over routing behavior.

**Acceptance Scenarios**:

1. **Given** an OON policy has `route.enabled` true AND `route.kill_switch` property exists, **When** the integration discovers the policy, **Then** a child kill switch entity is created alongside the main policy switch
2. **Given** an OON policy kill switch entity exists, **When** a user toggles the kill switch ON, **Then** the policy's route.kill_switch property is set to true
3. **Given** an OON policy kill switch entity exists, **When** a user toggles the kill switch OFF, **Then** the policy's route.kill_switch property is set to false
4. **Given** an OON policy does not have `route.enabled` true or `route.kill_switch` property, **When** the integration discovers the policy, **Then** no kill switch entity is created
5. **Given** an OON policy kill switch entity exists, **When** the policy's `route.kill_switch` is disabled or `route.enabled` becomes false on a subsequent update, **Then** the kill switch entity is removed from Home Assistant

---

### Edge Cases

- What happens when an OON policy is deleted while a switch is being toggled?
- How does the system handle API rate limiting when fetching OON policies?
- What happens when the OON policy endpoint returns an empty array?
- How does the system handle OON policies with missing required fields (id, name, enabled)?
- What happens when multiple users toggle the same OON policy switch simultaneously?
- How does the system handle OON policies that reference non-existent targets (devices, networks)?
- What happens when the UniFi controller version doesn't support OON policies? → System gracefully handles 404/endpoint not found errors by skipping OON policy discovery silently with debug logging and continuing with other entity types
- How does the system handle OON policies with very long names (>100 characters)?
- What happens when an OON policy's enabled state is changed externally (via UniFi UI) while Home Assistant has it open?
- How does the system handle network connectivity issues during policy updates?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST fetch Object-Oriented Network policies from the UniFi API endpoint `/proxy/network/v2/api/site/{site}/object-oriented-network-configs`
- **FR-002**: System MUST create a switch entity for each discovered OON policy using the unique identifier format `unr_oon_<policy_id>` (e.g., `unr_oon_123456`) to match existing UNR conventions
- **FR-003**: System MUST display the policy's top-level `name` as the switch entity name
- **FR-004**: System MUST use the policy's top-level `enabled` property to control switch state
- **FR-005**: System MUST support toggling OON policies ON and OFF through switch entities using PUT requests to the individual policy detail endpoint `/proxy/network/v2/api/site/{site}/object-oriented-network-configs/{policy_id}`
- **FR-006**: System MUST provide optimistic updates when toggling switches (immediate UI feedback before API confirmation)
- **FR-007**: System MUST verify switch state after API operations complete and update if there's a mismatch
- **FR-008**: System MUST handle API errors gracefully and revert switch state on failure
- **FR-009**: System MUST discover new OON policies automatically during coordinator refresh cycles
- **FR-010**: System MUST remove switch entities when corresponding OON policies are deleted from UniFi
- **FR-011**: System MUST update switch entity names when OON policy names change in UniFi
- **FR-012**: System MUST follow existing UNR conventions for entity naming, unique IDs, and device associations
- **FR-013**: System MUST inherit from the base switch class with standard optimistic toggle support
- **FR-014**: System MUST integrate with the coordinator's data fetching and entity management systems
- **FR-015**: System MUST support change detection and trigger events when OON policy states change
- **FR-016**: System MUST handle OON policies that target clients, networks, or other target types
- **FR-017**: System MUST support OON policies with QoS, routing, and security features configured
- **FR-018**: System SHOULD create child kill switch entities for OON policies when `route.enabled` is true AND `route.kill_switch` property exists/is boolean
- **FR-021**: System MUST remove existing kill switch entities when a policy's `route.kill_switch` is no longer enabled or `route.enabled` becomes false on subsequent updates
- **FR-019**: System MUST validate that required OON policy fields (id, name, enabled) exist before creating entities
- **FR-020**: System MUST handle OON policies gracefully when the API endpoint is unavailable or returns errors - if endpoint returns 404/not found, skip OON policy discovery silently with debug logging and continue with other entity types

### Key Entities *(include if feature involves data)*

- **Object-Oriented Network Policy**: Represents a unified network configuration rule that combines policy, traffic routing, and QoS features. Key attributes include: unique identifier (id), display name (name), enabled state (enabled), target type (target_type), target devices/networks (targets), QoS configuration (qos), routing configuration (route), and security configuration (secure). Relationships: belongs to a UniFi site, targets specific clients or networks, may have child kill switch entities.

- **OON Policy Switch Entity**: Represents a Home Assistant switch entity that controls an OON policy's enabled state. Key attributes include: unique identifier in format `unr_oon_<policy_id>` (e.g., `unr_oon_123456`), display name from policy name, current enabled state, optimistic state tracking. Relationships: belongs to a UniFi Network Rules device, controls a single OON policy, may have a child kill switch entity.

- **OON Policy Kill Switch Entity**: Represents an optional child switch entity that controls the kill switch feature for policies with routing enabled. Key attributes include: unique identifier derived from parent policy ID with suffix, display name indicating kill switch functionality, current kill switch state. Relationships: belongs to a parent OON policy switch entity, controls the route.kill_switch property. Lifecycle: created when `route.enabled` is true AND `route.kill_switch` exists, removed when either condition becomes false.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can toggle any OON policy ON or OFF within 2 seconds of interacting with the switch entity
- **SC-002**: All OON policies configured in UniFi are discoverable and appear as switch entities in Home Assistant within 60 seconds of integration setup or refresh
- **SC-003**: Switch state accurately reflects OON policy enabled state with 99% accuracy after API operations complete
- **SC-004**: Users can successfully create Home Assistant automations using OON policy switches without errors
- **SC-005**: System handles API failures gracefully with switch state reversion and error logging in 100% of failure scenarios
- **SC-006**: New OON policies created in UniFi appear as switch entities in Home Assistant within the next refresh cycle (default 60 seconds)
- **SC-007**: OON policy switches integrate seamlessly with existing UNR switch patterns and conventions
- **SC-008**: Users report successful completion of policy toggle operations in 95% of attempts
- **SC-009**: System supports OON policies with all target types (CLIENTS, NETWORKS, etc.) without errors
- **SC-010**: Optional kill switch entities are created correctly for 100% of eligible OON policies with routing enabled

## Assumptions

- The UniFi controller API endpoint `/proxy/network/v2/api/site/{site}/object-oriented-network-configs` is available and returns data in the documented format
- OON policies follow the data structure provided in issue #130 with top-level `id`, `name`, and `enabled` properties
- The integration follows existing patterns for switch entity creation, naming, and device association
- Optimistic updates follow the same pattern as other UNR switch types
- Change detection and trigger events work similarly to other rule types
- API authentication and error handling follow existing coordinator patterns
- OON policies can be toggled via PUT requests to the individual policy detail endpoint `/proxy/network/v2/api/site/{site}/object-oriented-network-configs/{policy_id}` to update the `enabled` property
- The site identifier is available from the coordinator's API context
- Entity cleanup and lifecycle management follow existing UNR patterns

## Dependencies

- UniFi Network controller with Object-Oriented Network configuration support
- Existing UNR coordinator infrastructure for data fetching and entity management
- Base switch class implementation for common switch functionality
- Helper functions for rule ID extraction, naming, and entity ID generation
- API endpoint constants and UDM API wrapper for making requests
- Change detection system for triggering automations on policy state changes

## Out of Scope

- Creating or deleting OON policies (only toggling existing policies)
- Modifying policy configuration details (QoS settings, routing rules, security settings) beyond enabled state
- Managing policy targets (adding/removing devices or networks from policies)
- UI for configuring OON policies (users configure via UniFi controller)
- Migration of existing policies/traffic rules to OON format
- Support for OON policy scheduling or time-based rules (handled by UniFi controller)
- Advanced QoS or routing configuration through Home Assistant
