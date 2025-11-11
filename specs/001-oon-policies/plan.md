# Implementation Plan: Object-Oriented Network Policies Support

**Branch**: `001-oon-policies` | **Date**: 2025-11-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-oon-policies/spec.md`

## Summary

Add support for UniFi's Object-Oriented Network (OON) policies by creating custom model classes, UDM API methods, switch entities, and coordinator integration. This enables users to toggle OON policies via Home Assistant switches for automation scenarios like temporary app blocking overrides. The implementation follows existing UNR patterns for custom models (similar to QoSRule, NATRule) and integrates seamlessly with the coordinator's data fetching and entity management systems.

## Technical Context

**Language/Version**: Python 3.13  
**Primary Dependencies**: Home Assistant Core, aiounifi (local copy in `/aiounifi`), existing UNR coordinator infrastructure  
**Storage**: N/A (state managed by UniFi controller, Home Assistant entity registry)  
**Testing**: pytest (existing test infrastructure)  
**Target Platform**: Home Assistant (Python integration)  
**Project Type**: Home Assistant custom integration (single project)  
**Performance Goals**: Toggle operations complete within 2 seconds, discovery within 60 seconds  
**Constraints**: Must handle 404 errors gracefully for unsupported controllers, follow existing UNR conventions, maintain backward compatibility  
**Scale/Scope**: Support unlimited OON policies per controller, integrate with existing 12+ entity types

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Phase 0 Check

- ✅ **DRY & Testability**: Implementation follows existing patterns (custom models, UDM mixins, switch classes) - no duplication
- ✅ **Native Library Prioritization**: Uses aiounifi for base API infrastructure, extends with custom models where needed
- ✅ **Type Safety**: Custom OONPolicy model will be fully typed with type hints
- ✅ **Root Cause Analysis**: Addresses user need for OON policy automation control
- ✅ **Preserve Existing Functionality**: No changes to existing entity types or coordinator behavior
- ✅ **Code Quality Standards**: Follows PEP 8, existing code patterns, and project structure
- ✅ **KISS**: Simple extension of existing patterns - no new architectural patterns needed
- ✅ **Code Hygiene**: Will resolve all linting errors before completion
- ✅ **Targeted Diagnostics**: Uses existing logging patterns, no excessive debug output
- ✅ **Project Structure Standards**: Follows existing structure (`models/`, `udm/`, `switches/`)
- ✅ **Documentation Standards**: Will document public APIs with docstrings
- ✅ **Open Source Accessibility**: Feature enhances home automation use cases

**Status**: ✅ PASS - All constitution principles satisfied

### Post-Phase 1 Check

*To be re-evaluated after design phase*

## Project Structure

### Documentation (this feature)

```text
specs/001-oon-policies/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
custom_components/unifi_network_rules/
├── models/
│   └── oon_policy.py          # NEW: Custom OON policy model
├── udm/
│   └── oon.py                 # NEW: UDM API mixin for OON operations
├── switches/
│   └── oon_policy.py          # NEW: OON policy switch and kill switch entities
├── coordination/
│   ├── data_fetcher.py        # MODIFY: Add oon_policies to entity_type_methods
│   └── entity_manager.py      # MODIFY: Add oon_policies to rule_type_entity_map
├── helpers/
│   └── rule.py                # MODIFY: Add get_rule_id/get_rule_name support for OONPolicy
├── constants/
│   └── api_endpoints.py       # MODIFY: Add OON policy API endpoint constants
└── __init__.py                # MODIFY: Add oon_policies entity creation support

tests/
└── test_oon_policy.py         # NEW: Tests for OON policy model and switch
```

**Structure Decision**: Extends existing Home Assistant custom integration structure. New files follow established patterns:
- Custom models in `models/` directory (like `qos_rule.py`, `nat_rule.py`)
- UDM API mixins in `udm/` directory (like `qos.py`, `nat.py`)
- Switch entities in `switches/` directory (like `traffic_route.py`)
- Integration points in coordinator, helpers, and constants modules

## Complexity Tracking

> **No violations detected** - Implementation follows existing patterns and architecture
