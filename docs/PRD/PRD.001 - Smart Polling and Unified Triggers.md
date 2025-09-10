# Product Requirements Document: Smart Polling Architecture and Unified Trigger System

**Document Version:** 1.0  
**Date:** August 27, 2025  
**Author:** @sirkirby 
**Status:** Approved  

> See companion RFC: [RFC.001 - Smart Polling and Unified Trigger](../RFC/RFC.001 - Smart Polling and Unified Trigger.md)

## Executive Summary

This PRD outlines a comprehensive architectural refactoring to replace the current mixed WebSocket + polling update model with a single, reliable smart polling approach and a unified `unr_changed` trigger. This change will:

- **Streamline updates** with smart polling only (eliminating UniFi WebSocket dependency)
- **Provide near-real-time confirmation** after HA actions via configurable debounce windows
- **Centralize comparison logic** in one place for all entity types
- **Normalize triggers** to a single universal `unr_changed` payload with old/new state included
- **Follow HA best practices** while keeping code DRY, typed, and resource-conscious
- **Maintain UniFi Network as canonical source of truth** with HA reconciling to it

The changes will simplify the architecture, improve reliability, and provide consistent user experience across all entity types including the new port profiles and networks.

## Background and Problem Statement

### Current Architecture Issues

The current implementation uses a complex hybrid approach with several critical pain points:

1. **Inconsistent Event Paths**: Some UniFi changes emit websocket events (triggering immediate refresh), while others do not (relying on periodic polling). This creates unpredictable user experience.
2. **Brittle WebSocket Stack**: The websocket implementation is reverse-engineered, undocumented, and requires extensive maintenance with frequent breakage.
3. **Split Change Logic**: Comparison and triggering logic is duplicated across websocket and polling flows, creating maintenance burden and inconsistency.
4. **Incomplete Entity Coverage**: New entities like networks and port profiles must fully participate in change notifications but current websocket events don't cover all cases.
5. **Source of Truth Complexity**: UniFi Network remains the canonical source of truth, but the hybrid system complicates reconciliation logic.

### Impact on User Experience

- **Inconsistent Response Times**: Some switches respond immediately to changes, others take up to 5 minutes
- **State Synchronization Issues**: Optimistic states may persist longer than necessary for some entity types
- **Complex Troubleshooting**: Multiple event paths make debugging difficult
- **Maintenance Burden**: Websocket implementation requires significant ongoing maintenance

## Proposed Solution

### Smart Polling Architecture

Replace the hybrid websocket/polling system with a unified smart polling approach that provides near real-time updates while maintaining simplicity and reliability.

#### Core Components

1. **Intelligent Update Scheduler**: Dynamic polling intervals based on user activity
2. **Debounced Refresh System**: Consolidates rapid successive changes into single poll operations
3. **Unified State Management**: Single path for all data updates and state changes
4. **Consolidated Trigger System**: Single trigger type with comprehensive change metadata

## Detailed Requirements

### 1. Smart Polling System

#### 1.1 Dynamic Polling Intervals

**Requirement**: Implement adaptive polling intervals based on system activity and user interaction patterns.

**Specification**:
- **Base Interval**: 300 seconds (5 minutes) when system is idle
- **Active Interval**: 30 seconds when recent user activity detected
- **Near Real-time Interval**: 10 seconds during active configuration periods
- **Activity Detection**: Track entity state changes, service calls, and UI interactions

**Configuration Options**:

```yaml
# In integration configuration
smart_polling:
  base_interval: 300        # Idle polling interval (seconds)
  active_interval: 30       # Active polling interval (seconds)
  realtime_interval: 10     # Near real-time interval (seconds)
  activity_timeout: 120     # Time to return to base interval (seconds)
  debounce_seconds: 10      # Debounce window (seconds)
```

#### 1.2 Rolling Timer Implementation

**Requirement**: Implement a debounced refresh system that batches rapid successive changes into single poll operations.

**Specification**:
- **Debounce Window**: 10 seconds (configurable)
- **Timer Reset**: Each new change resets the timer back to the full window
- **Single Poll**: After the window expires with no new changes, execute one comprehensive poll
- **Change Tracking**: Track which entities initiated changes for targeted validation

**Implementation Details example**:
```python
class SmartPollingManager:
    def __init__(self, coordinator, config):
        self.coordinator = coordinator
        self.base_interval = config.get('base_interval', 300)
        self.active_interval = config.get('active_interval', 30)
        self.realtime_interval = config.get('realtime_interval', 10)
        self.activity_timeout = config.get('activity_timeout', 120)
        self.debounce_seconds = config.get('debounce_seconds', 10)
        
        self._last_activity = 0
        self._pending_poll_task = None
        self._activity_entities = set()
        
    async def register_entity_change(self, entity_id: str, change_type: str):
        """Register that an entity change occurred"""
        current_time = time.time()
        self._last_activity = current_time
        self._activity_entities.add(entity_id)
        
        # Cancel existing pending poll
        if self._pending_poll_task and not self._pending_poll_task.done():
            self._pending_poll_task.cancel()
        
        # Schedule new poll with debounce timer
        self._pending_poll_task = asyncio.create_task(
            self._debounced_poll_delay()
        )
    
    async def _debounced_poll_delay(self):
        """Wait for debounce window, then execute poll"""
        try:
            await asyncio.sleep(self.debounce_seconds)
            await self._execute_smart_poll()
        except asyncio.CancelledError:
            # Timer was reset, this is expected
            pass
    
    async def _execute_smart_poll(self):
        """Execute a smart poll with change validation"""
        affected_entities = self._activity_entities.copy()
        self._activity_entities.clear()
        
        # Perform the poll
        await self.coordinator.async_refresh()
        
        # Validate changes for affected entities
        await self._validate_entity_changes(affected_entities)
    
    def get_current_interval(self) -> int:
        """Get current polling interval based on activity"""
        current_time = time.time()
        time_since_activity = current_time - self._last_activity
        
        if time_since_activity < self.rolling_window:
            return self.realtime_interval
        elif time_since_activity < self.activity_timeout:
            return self.active_interval
        else:
            return self.base_interval
```

#### 1.3 Relationship to Existing Periodic Polling

**Requirement**: Maintain existing user-configured periodic polling to capture external changes while adding debounced polling for HA-initiated changes.

**Implementation**:

- **Keep Periodic Polling**: Preserve existing periodic polling behavior for capturing external changes made directly in UniFi Network
- **Add Debounced Polling**: Layer debounced polling specifically for HA-initiated changes (switches, services)
- **Rate Limiting Integration**: Respect existing rate-limit and backoff behavior; if limited, run debounced poll at earliest allowed time
- **Recovery Behavior**: On auth failures, reuse established recovery patterns and return last-known-good state until recovery

#### 1.4 Optimistic State Management

**Requirement**: Enhance optimistic state handling to work seamlessly with smart polling.

**Specification**:
- **Optimistic Duration**: 15 seconds maximum (configurable)
- **Early Validation**: Poll triggers immediate validation for optimistic entities
- **State Reconciliation**: Clear optimistic state when actual state matches or after timeout
- **Fallback Handling**: Graceful degradation if poll fails

### 2. Unified Trigger System

#### 2.1 Single Universal Trigger

**Requirement**: Replace multiple trigger types with a single `unr_changed` trigger that includes comprehensive change metadata.

**Current Triggers to Replace**:
- `rule_enabled`
- `rule_disabled`
- `rule_changed`
- `rule_deleted`
- `device_changed`

**New Universal Trigger Schema**:
```yaml
trigger:
  platform: unifi_network_rules
  type: unr_changed
  # Optional filters
  entity_id: "switch.unr_firewall_policy_abc123"  # Specific entity
  change_type: "firewall_policy"                  # Entity type filter
  change_action: "enabled"                        # Action filter
  name_filter: "Guest Network"                    # Name pattern filter
```

**Trigger Data Payload**:
```python
{
    "platform": "unifi_network_rules",
    "type": "unr_changed",
    "entity_id": "switch.unr_firewall_policy_abc123",
    "unique_id": "unr_firewall_policy_abc123",
    "rule_id": "abc123",
    "change_type": "firewall_policy",  # firewall_policy, traffic_rule, traffic_route, port_forward, firewall_zone, wlan, qos_rule, vpn_client, vpn_server, device_led, port_profile, network
    "change_action": "enabled",  # enabled, disabled, modified, deleted
    "entity_name": "Guest Network Firewall Policy",
    "old_state": {
        "enabled": False,
        "name": "Guest Network Firewall Policy",
        # ... other relevant state
    },
    "new_state": {
        "enabled": True,
        "name": "Guest Network Firewall Policy",
        # ... other relevant state
    },
    "timestamp": "2025-08-27T10:30:00Z",
    "source": "polling"  # Always "polling" in new architecture
}
```

#### 2.2 Change Detection Logic

**Requirement**: Centralize all state comparison and change detection logic in a single location.

**Implementation Location**: `coordinator.py` in the `_async_update_data` method

**Change Detection Process**:

1. **State Snapshots**: Capture previous and current state for all entities using typed models
2. **Deep Comparison**: Compare relevant attributes (not just enabled/disabled)
3. **Change Classification**: Determine change action (enabled, disabled, modified, deleted, created)
4. **Trigger Dispatch**: Fire universal triggers with complete metadata
5. **State Persistence**: Update stored state for next comparison

**Typed Model Integration**:

- Maintain typed snapshots using `aiounifi` models where available (`FirewallPolicy`, `TrafficRoute`, `TrafficRule`, `PortForward`, `FirewallZone`, `Wlan`, `Device`)
- Extend custom types for entities not covered by `aiounifi` (`QoSRule`, `VPNConfig`, `PortProfile`, `NetworkConf`)
- Use consistent ID scheme across all entity types for reliable change tracking
- Implement generic diff logic with per-type normalization hooks as needed

Proposed example:

```python
class UnifiedChangeDetector:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._previous_state = {}
    
    async def detect_and_fire_changes(self, current_data: Dict[str, List[Any]]):
        """Detect changes and fire unified triggers"""
        changes = []
        
        # Build current state snapshot
        current_state = self._build_state_snapshot(current_data)
        
        # Compare with previous state
        for entity_id, current_entity_state in current_state.items():
            previous_entity_state = self._previous_state.get(entity_id)
            
            if previous_entity_state is None:
                # New entity
                changes.append(self._create_change_event(
                    entity_id, None, current_entity_state, "created"
                ))
            else:
                # Existing entity - check for changes
                change_action = self._determine_change_action(
                    previous_entity_state, current_entity_state
                )
                if change_action:
                    changes.append(self._create_change_event(
                        entity_id, previous_entity_state, current_entity_state, change_action
                    ))
        
        # Check for deleted entities
        for entity_id, previous_entity_state in self._previous_state.items():
            if entity_id not in current_state:
                changes.append(self._create_change_event(
                    entity_id, previous_entity_state, None, "deleted"
                ))
        
        # Fire triggers for all changes
        for change in changes:
            await self._fire_unified_trigger(change)
        
        # Update previous state
        self._previous_state = current_state
    
    def _determine_change_action(self, old_state: Dict, new_state: Dict) -> Optional[str]:
        """Determine what type of change occurred"""
        if old_state.get("enabled") != new_state.get("enabled"):
            return "enabled" if new_state.get("enabled") else "disabled"
        
        # Check for other significant changes
        significant_fields = ["name", "description", "action", "protocol", "port"]
        for field in significant_fields:
            if old_state.get(field) != new_state.get(field):
                return "modified"
        
        return None  # No significant change
```

Note: we should preserve and account for specialized logic as a part of the consolidation process.

### 3. WebSocket Removal

#### 3.1 Complete WebSocket Elimination

**Requirement**: Remove all websocket-related code and dependencies.

**Affected Components**:

- `custom_components/unifi_network_rules/coordinator.py` - Remove websocket coordination
- `custom_components/unifi_network_rules/trigger.py` - Remove websocket trigger handling
- `custom_components/unifi_network_rules/services/*` - Update to use smart polling
- `custom_components/unifi_network_rules/udm/*` - Remove websocket API usage
- `custom_components/unifi_network_rules/switch.py` - Update optimistic state handling
- `triggers.yaml` - Replace with unified trigger definition
- Integration options flow - Remove websocket configuration
- Documentation and tests - Update to reflect polling-only approach

**Components to Remove**:

- `websocket.py` - Main websocket handler
- `udm/websocket.py` - UDM-specific websocket implementation
- WebSocket-related mixins and handlers
- WebSocket configuration options
- WebSocket diagnostic services

**Migration Strategy**:
1. **Phase 1**: Disable websocket initialization while keeping code
2. **Phase 2**: Remove websocket event handling logic
3. **Phase 3**: Remove websocket infrastructure code
4. **Phase 4**: Update configuration schema

#### 3.2 Configuration Updates

**Requirement**: Update integration configuration to remove websocket options and add smart polling configuration.

**Removed Configuration**:
- Websocket connection settings
- Websocket retry configurations
- Websocket diagnostic options

**Added Configuration**:
```yaml
# New smart polling configuration section
smart_polling:
  enabled: true
  base_interval: 300
  active_interval: 30
  realtime_interval: 10
  activity_timeout: 120
  rolling_window: 10
  optimistic_timeout: 15
```

## 4. Design Considerations

### 4.1 Home Assistant Integration Patterns

#### DataUpdateCoordinator Best Practices

- **Always Update Control**: Set `always_update=False` when data can be compared with `__eq__` to avoid unnecessary callbacks and state machine writes
- **Update Interval**: Use `timedelta(seconds=30)` as baseline, adjusting dynamically based on activity
- **Context Management**: Leverage `async_contexts()` to limit API data retrieval to actively listening entities
- **First Refresh**: Use `async_config_entry_first_refresh()` for proper initialization with retry logic

#### Entity State Management

- **Polling Control**: Set `should_poll=True` for coordinated polling entities
- **State Updates**: Use `async_write_ha_state()` for immediate state updates without entity refresh
- **Available Property**: Properly implement `available` to indicate API connectivity status
- **Force Update**: Avoid `force_update=True` to prevent state machine spam

#### Async Best Practices

- **Event Loop Integration**: All coordination logic must be async-compatible
- **Executor Jobs**: Use `hass.async_add_executor_job()` for any blocking operations
- **Task Management**: Use `hass.async_create_task()` for independent background tasks
- **Timeout Handling**: Implement proper timeout with `async_timeout.timeout(10)`

### 4.2 Performance and Resource Management

- **Dynamic Intervals**: Prevent unnecessary polling during idle periods
- **Efficient State Comparison**: Utilize `__eq__` methods for change detection
- **Memory Optimization**: Minimize data structures for frequently accessed information
- **Request Parallelism**: Respect Home Assistant's built-in semaphore limiting per integration
- **Context Awareness**: Only fetch data for entities with active subscribers

### 4.3 Reliability and Error Handling

- **Circuit Breaker Pattern**: Implement backoff strategies for failed requests
- **State Consistency**: Ensure atomic updates across related entities
- **Graceful Degradation**: Maintain functionality during network issues
- **Auth Error Handling**: Raise `ConfigEntryAuthFailed` for authentication issues to trigger reauth flow
- **Update Failures**: Use `UpdateFailed` exception for API communication errors

### 4.4 User Experience

- **Responsive Updates**: Provide timely state changes for active interactions
- **Predictable Behavior**: Consistent trigger semantics across all operations
- **Configuration Flexibility**: Allow customization of polling intervals and triggers
- **Entity Naming**: Follow HA patterns with `has_entity_name=True` and proper device association

### 4.5 Maintainability

- **Clean Architecture**: Separate concerns between coordination, triggers, and business logic
- **Testability**: Enable comprehensive unit and integration testing
- **Documentation**: Provide clear migration guides and API documentation
- **Config Entry Management**: Leverage standard HA config entry lifecycle patterns

## 5. Migration Strategy

### 5.1 Breaking Change Approach

**Requirement**: Implement all changes in a single release with clear migration guidance.

**Migration Strategy**:
- **Breaking Change**: Old trigger types will be removed in this release
- **Migration Utility**: Provide conversion tool for existing automations
- **Documentation**: Comprehensive migration examples and guide
- **Version Pinning**: Users who need old triggers must stay on previous release until ready to migrate

#### 4.2 Migration Examples

**Common Migration Patterns**:

```yaml
# OLD: Rule enabled trigger
trigger:
  platform: unifi_network_rules
  type: rule_enabled
  rule_type: firewall_policy

# NEW: Unified trigger equivalent
trigger:
  platform: unifi_network_rules
  type: unr_changed
  change_type: firewall_policy
  change_action: enabled
```

```yaml
# OLD: Rule disabled trigger
trigger:
  platform: unifi_network_rules
  type: rule_disabled
  rule_id: "abc123"

# NEW: Unified trigger equivalent
trigger:
  platform: unifi_network_rules
  type: unr_changed
  entity_id: "switch.unr_firewall_policy_abc123"
  change_action: disabled
```

```yaml
# OLD: Device changed trigger
trigger:
  platform: unifi_network_rules
  type: device_changed
  device_id: "aa:bb:cc:dd:ee:ff"
  change_type: device_led

# NEW: Unified trigger equivalent
trigger:
  platform: unifi_network_rules
  type: unr_changed
  change_type: device
  entity_id: "switch.unr_device_aabbccddeeff_led"
  change_action: [enabled, disabled]  # LED can be toggled either way
```

```yaml
# OLD: Any rule change
trigger:
  platform: unifi_network_rules
  type: rule_changed
  name_filter: "Guest*"

# NEW: Unified trigger equivalent
trigger:
  platform: unifi_network_rules
  type: unr_changed
  name_filter: "Guest*"
  change_action: [enabled, disabled, modified]
```

#### 4.3 Migration Utility

**Nice-To-Have**: Provide a simple conversion tool for automation files.

**Tool Features**:
- Simple script to convert previous automation YAML to new format
- Offline and available in the repository outside of the custom integration installation in Home Assistant

**Example Usage**:
```bash
# Run migration utility
python scripts/migrate_unr_triggers.py --config /config --dry-run

# Apply changes after review
python scripts/migrate_unr_triggers.py --config /config --apply
```

#### 4.4 Service Compatibility

**Requirement**: Maintain existing service interfaces while updating underlying implementation.

**Services to Maintain**:
- `refresh_data` - Update to use smart polling
- `toggle_rule` - Enhanced with smart polling integration
- All backup/restore services - No changes needed

## Technical Implementation Steps

### Step 1: Smart Polling Foundation

#### 1.1 Core Polling Manager

- Implement `SmartPollingManager` class
- Add configuration schema updates
- Integrate with existing coordinator
- Add activity tracking mechanisms

**Testing & Verification Points**:
- Verify polling intervals adjust correctly based on activity
- Test configuration loading and validation
- Confirm coordinator integration doesn't break existing functionality

#### 1.2 Rolling Timer System

- Implement timer reset logic
- Add change batching functionality
- Create entity change registration system
- Test timer behavior under various scenarios

**Testing & Verification Points**:
- Verify timer resets correctly on successive changes
- Test batching with multiple rapid changes
- Confirm single poll executes after timer expires
- Validate timer cancellation on shutdown

### Step 2: Unified Change Detection

#### 2.1 Change Detection Engine

- Implement `UnifiedChangeDetector` class
- Create state snapshot mechanisms
- Add deep state comparison logic
- Implement change classification system

**Testing & Verification Points**:
- Test state comparison accuracy across all entity types
- Verify change action classification (enabled/disabled/modified/deleted)
- Confirm memory efficiency with large numbers of entities
- Optional:Test edge cases (malformed data, missing attributes)

#### 2.2 Trigger Consolidation

- Design new trigger schema
- Implement trigger data structure
- Create trigger firing mechanism
- Add filtering and matching logic

**Testing & Verification Points**:
- Verify trigger registration happens correctly
- Verify trigger data includes all required fields
- Test filtering by change_type, change_action, entity_id
- Confirm trigger firing doesn't impact performance
- Validate trigger data accuracy against actual changes

### Step 3: WebSocket Removal

#### 3.1 Complete Removal

- Remove websocket initialization from setup
- Remove websocket event handlers
- Clean up websocket configuration options
- Remove websocket diagnostic services

**Testing & Verification Points**:
- Confirm integration starts without websocket dependencies
- Verify no websocket-related errors in logs
- Test that polling-only mode provides expected functionality
- Validate configuration schema changes

#### 3.2 Code Cleanup

- Remove websocket infrastructure files (`websocket.py`, `udm/websocket.py`)
- Update imports and dependencies
- Clean up coordinator websocket references
- Remove websocket-related constants and configuration

**Testing & Verification Points**:
- Confirm no import errors after file removal
- Verify clean startup without websocket code
- Test configuration validation without websocket options
- Optional: Confirm reduced memory footprint

### Step 4: Integration Testing

#### 4.1 End-to-End Testing

- Test smart polling across all entity types
- Validate trigger firing accuracy
- Test rolling timer under load
- Verify optimistic state handling

**Testing & Verification Points**:
- Test with small and large numbers of entities
- Verify state synchronization across all rule types
- Test concurrent user actions and polling behavior
- Confirm optimistic states clear correctly

### Step 5: Migration Support and Documentation

#### 5.1 Migration Utilities (optional)

- Create trigger migration script
- Add configuration validation tools
- Implement backup/restore for automation files
- Create migration documentation

**Testing & Verification Points**:
- Test migration script with various trigger configurations
- Verify converted triggers work correctly
- Test backup/restore functionality
- Validate migration documentation completeness

#### 5.2 Documentation and Release Preparation

- Update integration documentation
- Update README with migration guide for automations
- Update configuration examples
- Prepare release notes with breaking changes

**Testing & Verification Points**:
- Review documentation accuracy
- Test all provided examples
- Verify migration guide completeness
- Confirm breaking changes are clearly documented

## Success Criteria

### Primary Objectives

1. **Unified Event Handling**: All entity changes use the same detection and notification path
2. **Improved Reliability**: Eliminate websocket-related connection issues and inconsistencies
3. **Consistent Response Times**: All entities respond to changes within the smart polling windows
4. **Simplified Architecture**: Reduce codebase complexity by removing websocket infrastructure and simplifying trigger system
5. **Enhanced User Experience**: Predictable behavior across all entity types

### Performance Metrics

- **State Update Latency**: 95% of changes detected within 15 seconds during active periods
- **Polling Efficiency**: Reduce unnecessary API calls by 60% through intelligent scheduling
- **Memory Usage**: Maintain or reduce current memory footprint
- **Error Rate**: Achieve <1% error rate in change detection
- **User Activity Response**: Transition to active polling within 10 seconds of user interaction

### Quality Metrics

- **Code Coverage**: Maintain >90% test coverage for new components
- **Documentation**: Complete documentation for all new features and migration guidance
- **Breaking Change Communication**: Clear documentation of breaking changes and migration path
- **Migration Success Rate**: >95% success rate for trigger migration utility

## Risk Assessment and Mitigation

### High-Risk Items

#### 1. Increased API Load
**Risk**: Smart polling may increase load on UniFi controllers
**Mitigation**: 
- Implement intelligent caching
- Add request throttling
- Monitor and adjust intervals based on controller response
- Provide configuration options for conservative settings

#### 2. Change Detection Accuracy
**Risk**: New change detection may miss subtle state changes
**Mitigation**:
- Comprehensive testing with all entity types
- Gradual rollout with fallback options
- Extensive logging during initial releases
- User feedback collection mechanisms

#### 3. Loss of Functionality
**Risk**: We lose or break existing functionality
**Mitigation**:
- Thorough testing to preserver existing feature set
- Ensure all affected services have been updated
- Ensure all helpers and utilities are compatible and have been updated

#### 4. User Adoption and Migration

**Risk**: Users may resist migration to new trigger system or encounter issues during migration

**Mitigation**:
- Clear benefits communication in release notes
- Comprehensive migration documentation and examples
- Migration utility with validation and backup features
- Community engagement and support during release

### Medium-Risk Items

#### 4. Performance Impact
**Risk**: More frequent polling may impact Home Assistant performance
**Mitigation**:
- Async implementation throughout
- Efficient state comparison algorithms
- Configurable intervals
- Performance monitoring

#### 5. User Adoption
**Risk**: Users may resist migration to new trigger system
**Mitigation**:
- Clear benefits communication
- Comprehensive documentation
- Community engagement

## Implementation Approach

The implementation will follow a sequential approach with clear verification points at each step:

1. **Smart Polling Foundation**: Implement debounced refresh system and configuration options
2. **Unified Change Detection**: Centralize change detection logic with typed state snapshots
3. **Unified Trigger System**: Implement `unr_changed` trigger with comprehensive payload
4. **WebSocket Removal**: Remove websocket infrastructure and update documentation

## Success Criteria

- **Unified Update Path**: All entity changes flow through single comparison logic
- **Response Time**: 95% of HA-initiated changes confirmed within debounce window
- **Reliability**: Reduced complexity and elimination of websocket-related defects
- **Test Coverage**: High test coverage for all new components
- **Migration Experience**: Clear documentation and smooth transition for users

## Dependencies and Constraints

### Technical Dependencies
- Home Assistant Core 2024.8+
- aiounifi library compatibility
- Python 3.13 support
- Async/await pattern consistency

### External Constraints
- UniFi Controller API rate limits
- Home Assistant entity lifecycle rules
- Configuration schema migration limitations
- Community feedback and adoption timeline

### Resource Constraints

- Development complexity: Significant architectural changes requiring careful testing
- Testing infrastructure requirements for comprehensive validation
- Documentation effort for migration guidance and new features
- Community support during breaking change transition

## Conclusion

This comprehensive refactoring will significantly improve the UniFi Network Rules integration by simplifying the architecture, improving reliability, and providing consistent user experience. The smart polling approach eliminates the complexity and unreliability of websocket implementation while the unified trigger system provides a cleaner, more powerful automation interface.

The sequential implementation approach ensures thorough testing and validation at each step, with clear verification points to confirm functionality. While this represents a breaking change for trigger configurations, the migration utilities and comprehensive documentation will help users transition smoothly to the new system.

This change represents a mature evolution of the integration, moving from a complex hybrid system to a simpler, more reliable architecture that better aligns with Home Assistant best practices and provides a foundation for future enhancements. Users will benefit from consistent, predictable behavior across all entity types and simplified automation creation with the unified trigger system.
