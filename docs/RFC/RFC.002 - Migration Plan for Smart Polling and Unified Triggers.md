# RFC.002 - Migration Plan for Smart Polling and Unified Triggers

**Author:** @sirkirby  
**Status:** Draft  
**Implementation Date:** TBD  
**Completion Target:** Next Major Release  

> Companion RFC to [RFC.001 - Smart Polling and Unified Trigger](./RFC.001%20-%20Smart%20Polling%20and%20Unified%20Trigger.md)  
> Implementation Plan for [PRD.001 - Smart Polling and Unified Triggers](../PRD/PRD.001%20-%20Smart%20Polling%20and%20Unified%20Triggers.md)

## Objective

Provide a comprehensive migration strategy for users to transition from the legacy trigger system to the new unified `unr_changed` trigger with a clean breaking change approach, including automated migration tooling and clear documentation.

## Current Implementation Status

### ✅ **Phase 1: Foundation (Completed)**

- Smart polling architecture implemented
- Unified change detection system active
- New `unr_changed` trigger available
- Legacy triggers still functional with deprecation warnings
- **Dual trigger emission** - Both legacy AND new triggers fire simultaneously

### 🔄 **Phase 2: Transition Period (Current)**

- Legacy triggers marked as deprecated but fully functional
- New `unr_changed` trigger available for early adopters
- Documentation and migration examples provided
- User education and community engagement

### 📋 **Phase 3: Legacy Removal (Future)**

- Timeline: TBD based on adoption metrics
- Complete removal of legacy trigger code
- Performance optimizations post-cleanup

## Migration Strategy

### **Approach: Clean Breaking Change with Migration Tools**

We implement a **clean architectural break** with comprehensive migration support:

1. **Legacy triggers completely removed** - clean codebase
2. **Single `unr_changed` trigger system** - no dual complexity
3. **Automated migration utility** for easy conversion
4. **Comprehensive documentation** with examples
5. **Clear error messages** directing to migration guide

### **Benefits of This Approach**

- ✅ **Clean, maintainable codebase** without legacy burden
- ✅ **Simplified architecture** - no dual system complexity
- ✅ **Better performance** without legacy overhead
- ✅ **Future-proof foundation** for new features
- ✅ **Clear migration path** with automated tooling

## Implementation Phases

### **Phase 1: Foundation ✅ (Complete)**

**Duration:** Initial release  
**Status:** Implemented

**Deliverables:**

- [x] Smart polling system with dynamic intervals
- [x] Unified change detection engine
- [x] New `unr_changed` trigger implementation
- [x] Dual trigger emission (legacy + unified)
- [x] Legacy trigger deprecation warnings
- [x] Updated `triggers.yaml` with new trigger definition

**Technical Details:**

```python
# Both triggers fire for the same event
await self._fire_new_unified_trigger(change)  # New system
await self._fire_legacy_triggers(change)      # Legacy compatibility
```

### **Phase 2: Transition Period 🔄 (Current)**

**Duration:** 6-12 months (flexible based on adoption)  
**Status:** In Progress

**Objectives:**

- Educate users about new trigger system
- Provide migration tools and documentation
- Monitor adoption metrics
- Gather feedback on new system
- Maintain full backward compatibility

**Deliverables:**

- [ ] Comprehensive migration documentation
- [ ] Automation migration utility (optional)
- [ ] Community education and examples
- [ ] Adoption metrics collection
- [ ] Performance monitoring
- [ ] User feedback collection

**Migration Documentation:**

```yaml
# Example migration patterns:

# OLD (still works, but deprecated)
trigger:
  platform: unifi_network_rules
  type: rule_enabled
  rule_type: firewall_policy
  name_filter: "Guest*"

# NEW (recommended)  
trigger:
  platform: unifi_network_rules
  type: unr_changed
  change_type: firewall_policy
  change_action: enabled
  name_filter: "Guest*"
```

**Success Criteria:**

- Legacy triggers continue to work without issues
- New triggers demonstrate improved reliability
- Community feedback is positive
- No performance regressions
- Migration documentation is comprehensive

### **Phase 3: Legacy Sunset 📋 (Future)**

**Duration:** TBD (based on Phase 2 metrics)  
**Status:** Planning

**Trigger Conditions:**

- >80% of active users have migrated to new triggers
- New system proven stable for >6 months
- Community consensus for migration
- No major blocking issues reported

**Implementation Steps:**

1. **Final migration notice** (3 months advance warning)
2. **Enhanced deprecation warnings** (1 month before removal)
3. **Legacy trigger removal** from codebase
4. **Performance optimizations** post-cleanup
5. **Documentation updates**

**Deliverables:**

- [ ] Final migration timeline announcement
- [ ] Enhanced deprecation warnings with specific migration guidance
- [ ] Legacy code removal
- [ ] Performance optimizations
- [ ] Updated documentation
- [ ] Release notes for breaking change

## Migration Tools

### **Automated Migration Utility (Optional)**

**Script:** `scripts/migrate_triggers.py`

```bash
# Scan for legacy triggers in automations
python scripts/migrate_triggers.py --scan /config/automations.yaml

# Perform dry-run migration
python scripts/migrate_triggers.py --migrate /config/automations.yaml --dry-run

# Apply migration (with backup)
python scripts/migrate_triggers.py --migrate /config/automations.yaml --apply
```

**Features:**

- Backup creation before changes
- Dry-run mode for safe testing
- Detailed migration report
- Error handling and validation
- Support for multiple automation files

### **Migration Examples**

#### **Basic Rule State Triggers**

```yaml
# Before
automation:
  - alias: "Guest Network Enabled"
    trigger:
      platform: unifi_network_rules
      type: rule_enabled
      rule_type: firewall_policy
      name_filter: "Guest"
    action:
      - service: notify.mobile_app
        data:
          message: "Guest network access enabled"

# After  
automation:
  - alias: "Guest Network Enabled"
    trigger:
      platform: unifi_network_rules
      type: unr_changed
      change_type: firewall_policy
      change_action: enabled
      name_filter: "Guest"
    action:
      - service: notify.mobile_app
        data:
          message: "Guest network access enabled"
```

#### **Complex Multi-Action Triggers**

```yaml
# Before (multiple triggers needed)
automation:
  - alias: "Any Rule Change"
    trigger:
      - platform: unifi_network_rules
        type: rule_enabled
        rule_type: firewall_policy
      - platform: unifi_network_rules  
        type: rule_disabled
        rule_type: firewall_policy
      - platform: unifi_network_rules
        type: rule_changed
        rule_type: firewall_policy

# After (single trigger)
automation:
  - alias: "Any Rule Change"
    trigger:
      platform: unifi_network_rules
      type: unr_changed
      change_type: firewall_policy
      change_action: [enabled, disabled, modified]
```

#### **Device State Changes**

```yaml
# Before
automation:
  - alias: "AP LED Changed"
    trigger:
      platform: unifi_network_rules
      type: device_changed
      device_id: "aa:bb:cc:dd:ee:ff"
      change_type: "led_toggled"

# After
automation:
  - alias: "AP LED Changed" 
    trigger:
      platform: unifi_network_rules
      type: unr_changed
      change_type: device
      entity_id: "switch.unr_device_aabbccddeeff_led"
      change_action: [enabled, disabled]
```

## Monitoring and Success Metrics

### **Adoption Metrics**

- Percentage of legacy vs unified triggers in active use
- Number of automations using each trigger type
- Community feedback and issue reports
- Performance impact measurements

### **Quality Metrics**

- Trigger reliability (false positives/negatives)
- Response time consistency
- Memory and CPU usage impact
- Error rates in change detection

### **User Experience Metrics**

- Documentation clarity ratings
- Migration utility usage and success rates
- Community forum feedback sentiment
- Support request volume and type

## Risk Assessment and Mitigation

### **High-Risk Items**

#### **1. User Resistance to Migration**

**Risk:** Users may not migrate during transition period
**Mitigation:**

- Maintain full backward compatibility indefinitely if needed
- Provide clear benefits documentation
- Offer migration assistance
- Gradual approach with no forced timeline

#### **2. Dual System Complexity**

**Risk:** Maintaining both systems increases complexity and potential bugs
**Mitigation:**

- Comprehensive testing of both systems
- Clear separation of legacy and unified code paths
- Monitoring for performance impact
- Regular review of dual emission logic

#### **3. New System Bugs**

**Risk:** New trigger system may have undiscovered issues
**Mitigation:**

- Extensive testing in real environments
- Gradual rollout approach
- Easy rollback mechanisms
- Community beta testing program

### **Medium-Risk Items**

#### **4. Performance Impact**

**Risk:** Dual trigger emission may impact performance
**Mitigation:**

- Performance monitoring and optimization
- Conditional legacy emission (opt-in/opt-out)
- Efficient signal dispatch implementation

#### **5. Documentation Maintenance**

**Risk:** Maintaining docs for both systems is complex
**Mitigation:**

- Clear versioning of documentation
- Automated generation where possible
- Community contribution encouragement

## Timeline and Milestones

### **Phase 2: Transition Period (6-12 months)**

#### **Month 1-2: Documentation and Tools**

- [ ] Complete migration documentation
- [ ] Release migration utility (if needed)
- [ ] Community announcement and education
- [ ] Performance baseline establishment

#### **Month 3-4: Early Adoption**

- [ ] Encourage early adopter feedback
- [ ] Monitor new trigger system stability
- [ ] Address any reported issues
- [ ] Refine documentation based on feedback

#### **Month 5-6: Mid-Transition Assessment**

- [ ] Analyze adoption metrics
- [ ] Performance impact assessment
- [ ] Community feedback evaluation
- [ ] Decide on Phase 3 timeline

#### **Month 7-12: Continued Support**

- [ ] Ongoing support for both systems
- [ ] Performance optimizations
- [ ] Additional migration examples
- [ ] Prepare for Phase 3 if metrics support it

### **Phase 3: Legacy Sunset (TBD)**

- Final timeline will be determined based on Phase 2 success metrics
- Minimum 3-month advance notice before any breaking changes
- Community consensus required before proceeding

## Communication Plan

### **User Education**

- Blog posts explaining benefits of new trigger system
- Video tutorials for common migration patterns
- Community forum discussions and Q&A
- Updated integration documentation

### **Developer Communication**

- Clear commit messages and PR descriptions
- Changelog entries with migration guidance
- Release notes highlighting deprecation timeline
- Community Discord/forum engagement

### **Support Strategy**

- Dedicated support for migration questions
- FAQ document for common migration issues
- Template automations using new trigger format
- Community-driven migration examples

## Success Criteria

**Phase 2 Success:**

- [ ] Legacy triggers continue working without regression
- [ ] New trigger system demonstrates improved reliability
- [ ] >50% of active users try new triggers
- [ ] <5% increase in support requests during transition
- [ ] Positive community feedback on new system

**Phase 3 Readiness:**

- [ ] >80% adoption of new trigger system
- [ ] 6+ months of stable new system operation
- [ ] Community consensus for legacy removal
- [ ] Migration utility tested and proven
- [ ] All major use cases covered in documentation

## Conclusion

This migration plan provides a **risk-averse, user-friendly approach** to transitioning from legacy triggers to the unified system. By maintaining full backward compatibility and allowing users to migrate at their own pace, we minimize disruption while enabling the benefits of the new architecture.

The key insight is that **both systems can coexist temporarily**, allowing for gradual migration and real-world validation of the new approach before any breaking changes are introduced.

**Timeline Summary:**

- **Phase 1:** ✅ Complete (Smart polling + unified triggers + backward compatibility)
- **Phase 2:** 🔄 6-12 months (Education + gradual migration + metrics collection)
- **Phase 3:** 📋 TBD (Legacy removal based on success criteria)

This approach ensures a **smooth transition** that respects existing user investments while enabling the long-term benefits of the simplified, unified architecture.
