# PRD.002 - Code Organization and Architecture Refactoring

**Author:** @sirkirby  
**Status:** Proposed

## Executive Summary

This PRD outlines a comprehensive code organization refactoring to transform the UniFi Network Rules integration from its current monolithic structure into a modular, maintainable architecture. The refactoring will split large files (1,879+ lines) into focused modules, achieve 100% type hint coverage, and establish clear separation of concerns while maintaining all existing functionality.

## Background and Problem Statement

**Current State Analysis:**

- `switch.py`: 1,879 lines, 67 methods, 14 switch classes (monolithic)
- `coordinator.py`: 1,762 lines, 39 methods, single large class with multiple responsibilities
- `const.py`: 205 lines, 130+ constants (could benefit from logical grouping)
- `__init__.py`: 454 lines (unusually large for an init file)
- Type hint coverage: 89% (42/47 files)
- Documentation coverage: 100% ✅

**Problems:**

1. **Maintainability**: Large files are difficult to navigate and modify
2. **Testability**: Monolithic classes make unit testing challenging
3. **Collaboration**: Multiple developers cannot work on related features without conflicts
4. **Code Discovery**: Finding specific functionality requires searching through large files
5. **Type Safety**: Missing type hints in 5 files reduce IDE support and error detection

## Goals and Non-Goals

- **Goals:**

  - Split large files into logical, focused modules
  - Achieve 100% type hint coverage across all Python files
  - Establish clear separation of concerns
  - Maintain 100% backward compatibility
  - Improve code discoverability and navigation
  - Enable better testing practices
  - Prepare codebase for enterprise-scale development

- **Non-Goals:**

  - Changing any public APIs or user-facing functionality
  - Modifying existing configuration schemas
  - Breaking changes to Home Assistant integration patterns
  - Performance optimization (maintain current performance)

## User Stories / Use Cases

- As a **developer**, I want focused modules so that I can quickly locate and modify specific functionality.
- As a **maintainer**, I want clear separation of concerns so that I can test components in isolation.
- As a **contributor**, I want well-organized code so that I can understand the architecture and make improvements.
- As a **user**, I want the same functionality so that my existing automations continue to work without changes.

## Requirements

### Functional Requirements

1. **Module Structure**: Create focused modules for switches, coordination, and constants
2. **Type Coverage**: Add type hints to all public and private methods
3. **Import Compatibility**: Maintain all existing import paths through `__init__.py` exports
4. **Documentation**: Preserve all existing docstrings and add module-level documentation
5. **Testing**: Ensure all existing tests continue to pass

### Non-Functional Requirements

- **Performance**: No regression in startup time or memory usage
- **Reliability**: Zero functional changes or behavior modifications
- **Maintainability**: Reduce average file size to <500 lines where practical
- **Code Quality**: Achieve 100% type hint coverage
- **Documentation**: Maintain comprehensive docstring coverage

## Design Overview

### New Architecture Structure

```text
custom_components/unifi_network_rules/
├── __init__.py                    # Main exports (reduced size)
├── config_flow.py                 # Unchanged
├── manifest.json                  # Unchanged
├── services.yaml                  # Unchanged
├── coordination/                  # NEW: Coordinator refactoring
│   ├── __init__.py               # Exports main coordinator
│   ├── coordinator.py            # Main coordinator (reduced)
│   ├── state_manager.py          # State diff detection & processing
│   ├── entity_manager.py         # Entity creation/deletion logic
│   ├── data_fetcher.py           # Data fetching and validation
│   └── trigger_manager.py        # Trigger firing and management
├── switches/                      # NEW: Switch class organization
│   ├── __init__.py               # Exports all switch classes
│   ├── base.py                   # UnifiRuleSwitch base class
│   ├── rules.py                  # Firewall, Traffic, QoS switches
│   ├── networking.py             # Network & Port Profile switches
│   ├── devices.py                # Device LED switches
│   ├── vpn.py                    # VPN Client/Server switches
│   └── forwarding.py             # Port Forward switches
├── constants/                     # NEW: Organized constants
│   ├── __init__.py               # Main exports
│   ├── integration.py            # Domain, platforms, defaults
│   ├── config.py                 # Configuration keys and defaults
│   ├── api_endpoints.py          # All API endpoint constants
│   ├── smart_polling.py          # Smart polling configuration
│   └── debugging.py              # Debug flags and logging
├── helpers/                       # Existing (unchanged)
├── models/                        # Existing (unchanged)
├── services/                      # Existing (unchanged)
├── udm/                          # Existing (unchanged)
├── utils/                        # Existing (unchanged)
└── translations/                 # Existing (unchanged)
```

### Data Flow

1. **Coordinator**: `coordination/coordinator.py` orchestrates data flow
2. **State Management**: `coordination/state_manager.py` handles change detection
3. **Entity Management**: `coordination/entity_manager.py` creates/removes entities
4. **Switch Classes**: `switches/` modules handle entity-specific logic
5. **Constants**: `constants/` modules provide organized configuration

## Configuration

No configuration changes required. All existing configurations remain valid:

```yaml
# Existing configuration remains unchanged
unifi_network_rules:
  host: "192.168.1.1"
  username: "admin"
  password: "password"
  site: "default"
  update_interval: 300
```

## Triggers & Events (if applicable)

No changes to existing trigger patterns. All current triggers remain functional:

```yaml
trigger:
  platform: unifi_network_rules
  type: configuration_changed
  entity_id: switch.unifi_firewall_rule_example
  change_type: modified
```

## Data Models & Typing

### Type Hint Implementation

All methods will receive proper type annotations:

```python
# Before
def register_ha_initiated_operation(self, rule_id, entity_id, change_type="modified", timeout=15):

# After
def register_ha_initiated_operation(
    self,
    rule_id: str,
    entity_id: str,
    change_type: str = "modified",
    timeout: int = 15
) -> None:
```

### Module Exports

Clear typing for all module exports:

```python
# switches/__init__.py
from .base import UnifiRuleSwitch
from .rules import (
    UnifiFirewallPolicySwitch,
    UnifiTrafficRuleSwitch,
    UnifiLegacyFirewallRuleSwitch,
)
from .networking import (
    UnifiNetworkSwitch,
    UnifiPortProfileSwitch,
)

__all__ = [
    "UnifiRuleSwitch",
    "UnifiFirewallPolicySwitch",
    # ... etc
]
```

## Observability & Diagnostics

- **Logging**: Maintain existing logging patterns with module-specific loggers
- **Diagnostics**: Preserve all current diagnostic capabilities
- **Debugging**: Keep existing debug flags in `constants/debugging.py`

## Performance & Resource Management

- **Target**: No performance regression
- **Memory**: Maintain current memory footprint
- **Import Time**: Minimize import overhead through lazy loading where appropriate
- **Module Loading**: Optimize `__init__.py` exports to avoid circular imports

## Reliability & Error Handling

- **Backward Compatibility**: All existing error handling patterns preserved
- **Import Safety**: Graceful fallbacks if module structure changes
- **Testing**: Comprehensive test coverage to prevent regressions

## Migration & Breaking Changes (if any)

**No Breaking Changes**: This is a pure refactoring with full backward compatibility.

**Internal Import Updates**:

```python
# Old internal imports (will be updated)
from .switch import UnifiRuleSwitch

# New internal imports
from .switches import UnifiRuleSwitch

# Public API imports remain unchanged
```

## Success Criteria & Metrics

### Primary Objectives

- ✅ Split 4 large files (>400 lines) into focused modules
- ✅ Achieve 100% type hint coverage (47/47 files)
- ✅ Reduce average file size to <500 lines where practical
- ✅ Maintain 100% test coverage
- ✅ Zero functional regressions

### Performance Metrics

- **Import Time**: ≤ current baseline
- **Memory Usage**: ≤ current baseline  
- **Startup Time**: ≤ current baseline

### Quality Metrics

- **Type Coverage**: 100% (up from 89%)
- **File Organization**: 20+ focused modules vs 4 monolithic files
- **Code Discoverability**: <30 seconds to locate any specific functionality
- **Test Coverage**: Maintain 100% coverage
- **Documentation**: 100% docstring coverage (maintain current)

## Risks & Mitigations

### Risks

1. **Import Circular Dependencies**: New module structure could create circular imports
2. **Test Breakage**: Refactoring could break existing tests
3. **Performance Regression**: Additional module overhead
4. **Merge Conflicts**: Large refactoring could conflict with ongoing development

### Mitigations

1. **Careful Import Design**: Use dependency injection and lazy imports
2. **Incremental Testing**: Test each phase before proceeding
3. **Performance Monitoring**: Benchmark before/after each phase
4. **Coordination**: Coordinate with other developers and freeze non-essential changes

## Dependencies & Constraints

### Dependencies

- **Home Assistant Core**: ≥2024.1.0 (current requirement)
- **Python**: ≥3.11 (current requirement)
- **aiounifi**: ≥84.0.0 (current requirement)

### Constraints

- **Zero Breaking Changes**: Must maintain full API compatibility
- **Test Compatibility**: All existing tests must pass without modification
- **Import Compatibility**: Public imports must remain unchanged

## Implementation Steps (High-Level)

### Phase 1: Type Hint Completion (1-2 hours)

1. Add type hints to 5 remaining files:
   - `udm/__init__.py`
   - `utils/__init__.py`  
   - `helpers/__init__.py`
   - `const.py`
   - `services/constants.py`
2. Verify with mypy/pylint
3. Test import compatibility

### Phase 2: Constants Organization (2-3 hours)

1. Create `constants/` directory structure
2. Split `const.py` into logical modules
3. Update `constants/__init__.py` exports
4. Update all internal imports
5. Verify functionality

### Phase 3: Switch Module Refactoring (4-6 hours)

1. Create `switches/` directory structure
2. Extract base class to `switches/base.py`
3. Group related switches into focused modules
4. Update `switches/__init__.py` exports
5. Update all imports throughout codebase
6. Comprehensive testing

### Phase 4: Coordinator Refactoring (6-8 hours)

1. Create `coordination/` directory structure
2. Extract state management logic
3. Extract entity management logic
4. Extract data fetching logic
5. Extract trigger management logic
6. Update main coordinator to orchestrate components
7. Update `coordination/__init__.py` exports
8. Update imports and test thoroughly

### Phase 5: Final Integration & Testing (2-3 hours)

1. Full integration testing
2. Performance benchmarking
3. Documentation updates
4. Final code review

## Open Questions

1. **Module Naming**: Should we use `switches` or `entities` for the switch module directory?
2. **Export Strategy**: Should we maintain full backward compatibility or deprecate some internal imports?
3. **Testing Strategy**: Should we add new tests for individual modules or rely on existing integration tests?

## Appendix (Optional)

### Related Documents

- **Current Architecture**: See existing codebase structure
- **Home Assistant Integration Patterns**: [HA Quality Scale](https://developers.home-assistant.io/docs/integration_quality_scale/)
- **Python Type Hinting**: PEP 484, PEP 526

### References

- **Code Quality Standards**: Follows Home Assistant development guidelines
- **Module Organization**: Based on established Python packaging best practices
