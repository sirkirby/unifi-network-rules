# RFC.001 - Smart Polling and Unified Trigger

**Author:** @sirkirby
**Status:** Draft

This RFC proposes replacing the current mixed WebSocket + polling model with a single smart polling approach and consolidating triggers into a universal `unr_changed` event, as specified in [PRD.001 - Smart Polling and Unified Triggers](../PRD/PRD.001 - Smart Polling and Unified Triggers.md).

## Objective

Adopt a polling-only architecture with a debounced, near-real-time refresh for HA-initiated changes, centralize state comparison logic, and emit a single normalized trigger for all change types, keeping UniFi Network as the canonical source of truth.

## Problem Description

### Current State

- The integration relies on both WebSocket events and periodic polling.
- WebSocket coverage is incomplete and reverse-engineered; some UniFi changes do not emit usable events.
- Change detection logic is duplicated across WebSocket and polling code paths.
- New entities (networks, port profiles) require consistent change handling.

### Challenges

- Inconsistent update behavior and timing across entity types.
- Reliability and maintainability issues due to undocumented WebSocket behavior.
- Complex trigger surface with multiple event types.
- Ensuring low API load while providing timely state reconciliation.

## Proposed Solution

### Design

- Remove WebSocket consumption and use polling only.
- Introduce a debounced refresh (default 10s) for HA-initiated changes; subsequent changes within the window reset the timer to coalesce updates.
- Maintain periodic polling at user-configured intervals to capture external changes.
- Centralize typed snapshot/diff logic in the coordinator to classify changes: `created`, `removed`, `enabled`, `disabled`, `modified`.
- Emit a single trigger `unr_changed` with fields: `id`, `change_type`, `change_action`, `old_state`, `new_state`, `was_ha_initiated`.
- Keep optimistic entity updates for UX; reconcile via debounced poll.

### Alternatives Considered

- Keep mixed WebSocket + polling: rejected due to complexity, brittleness, and inconsistency.
- Enhance WebSocket parsing: rejected given lack of documentation and ongoing maintenance cost.
- Event-bridge or webhooks: not available in UniFi Network for required coverage.

### Risks and Mitigation

- Slightly increased latency vs WebSocket events: mitigate with configurable debounce (default 10s) and user-tunable periodic polling.
- Higher API load during bursts: mitigate by coalescing via debounce and honoring existing rate-limit/backoff.
- Automation migration friction: mitigate with a deprecation plan and migration guidance (or utility) from legacy triggers to `unr_changed`.

## Implementation Plan

### Timeline

- Sprint 1: Implement debounced smart polling and options; wire CQRS registration to the debounce scheduler.
- Sprint 2: Implement centralized diff/trigger emission and `unr_changed`.
- Sprint 3: Remove WebSocket usage and related code; cleanup configuration and docs.
- Sprint 4: Testing (unit/integration), performance verification, and release notes/migration docs.

### Dependencies

- Home Assistant DataUpdateCoordinator patterns and async best practices.
- aiounifi models; custom typed models where aiounifi coverage is lacking.
- Python 3.13 runtime and HA Core 2024.8+.

### Monitoring and Metrics

- Change detection latency distribution (target: 95% within 15s during active periods).
- API call rate before/after under bursty user changes.
- Trigger emission accuracy (spot-verified in tests and diagnostics).
- Error rates for update and comparison paths.

## Appendix (Optional)

- PRD reference: [PRD.001 - Smart Polling and Unified Triggers](../PRD/PRD.001 - Smart Polling and Unified Triggers.md)
- Affected modules: `coordinator.py`, `trigger.py`, `services/*`, `udm/*`, `switch.py`, `triggers.yaml`
- Configuration options (proposed): `debounce_seconds`, `update_interval_seconds`
