# PRD.{number} - {title}

**Author:** @{handle}
**Status:** {Draft|Proposed|Approved}

## Executive Summary

*Briefly describe the problem, the proposed solution at a high level, and the user-facing impact.*

## Background and Problem Statement

*Summarize the current state and the specific issues motivating this PRD.*

## Goals and Non-Goals

- **Goals**: *List what success includes.*
- **Non-Goals**: *List what is explicitly out of scope.*

## User Stories / Use Cases

*- As a <user>, I want <capability>, so that <benefit>.*

## Requirements

- **Functional**: *Enumerate concrete behaviors, inputs/outputs, and edge cases.*
- **Non-Functional**: *Performance, reliability, security, resource usage.*

## Design Overview

*Describe the high-level architecture and main components. Keep details minimal here and link deeper docs if needed.*

- **Components**: *List modules/classes at a high level.*
- **Data Flow**: *Summarize how data moves through the system.*

## Configuration

*Show concise examples of configuration that users may set.*

```yaml
# Example configuration (adjust to this PRD)
feature:
  enabled: true
  option_a: 30
  option_b: "value"
```

## Triggers & Events (if applicable)

*Define any events/triggers and their payloads.*

```yaml
trigger:
  platform: unifi_network_rules
  type: {event_type}
  # optional filters
  entity_id: {entity}
  change_type: {type}
  change_action: {action}
```

## Data Models & Typing

*Reference `aiounifi` models where possible; define custom typed models for anything not covered. Keep all data typed.*

## Observability & Diagnostics

*What to log, how to enable diagnostics, and how to keep it targeted and resource-friendly.*

## Performance & Resource Management

*Target intervals, caching, request limits, and expected load. Note any dynamic behavior.*

## Reliability & Error Handling

*Backoff/circuit breaker, retries, auth failures, and graceful degradation patterns.*

## Migration & Breaking Changes (if any)

*Describe changes to configuration, triggers, or services. Provide migration examples.*

## Success Criteria & Metrics

- **Primary Objectives**: *What outcomes define success.*
- **Performance Metrics**: *Latency, API calls, memory.*
- **Quality Metrics**: *Coverage, docs completeness, error rate.*

## Risks & Mitigations

*List top risks and how to mitigate them.*

## Dependencies & Constraints

*List technical and external dependencies (HA Core, `aiounifi`, Python version), constraints, and compatibility notes.*

## Implementation Steps (High-Level)

1. *Step 1 with verification points*
2. *Step 2 with tests*
3. *Step 3 with docs*

## Open Questions

*Track unresolved decisions requiring follow-up.*

## Appendix (Optional)

*Links to related PRDs/RFCs, diagrams, prototypes, or references.*
