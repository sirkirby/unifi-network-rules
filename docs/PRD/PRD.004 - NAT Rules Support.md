# PRD.004 - NAT Rules Support

**Author:** @sirkirby  
**Status:** Proposed  

## Executive Summary

This PRD defines the requirements for adding comprehensive NAT (Network Address Translation) rules support to the UniFi Network Rules integration. The feature will enable Home Assistant users to manage custom UniFi NAT rules through:

- **Switch entities** for enabling/disabling configured NAT rules
- **Automated backup and restoration** of NAT rule configurations  
- **Real-time change detection** via the unified trigger system
- **Seamless integration** with existing Home Assistant automations

This extends the integration's network management capabilities beyond firewall policies and routing to include network address translation control, enabling complete network transformation and security automation for home and small office networks.

## Background and Problem Statement

### Current Limitation

The UniFi Network Rules integration currently supports management of firewall policies, traffic rules, port forwards, QoS rules, static routes, WLANs, VPN configurations, and port profiles. However, **NAT rules configured in UniFi Network are not accessible** through Home Assistant, forcing users to:

- Manually manage NAT rules through the UniFi web interface
- Unable to automate NAT rule changes based on network conditions  
- Cannot backup/restore NAT configurations programmatically
- Miss NAT rule changes in Home Assistant automations and notifications

### User Impact

Network administrators managing complex home networks with multiple VLANs, custom routing scenarios, or advanced security policies need dynamic NAT control for:

- **DNS redirection scenarios** (e.g., temporarily redirect DNS requests to different servers)
- **Traffic manipulation** (e.g., redirect specific client traffic through different paths)
- **Security policies** (e.g., enable/disable source NAT rules based on threat conditions)
- **Service availability** (e.g., activate backup NAT rules when primary services fail)
- **Automation integration** (e.g., NAT rule changes triggered by presence detection or security events)

### Technical Context

UniFi Network exposes custom NAT rules through a V2 REST API at `/proxy/network/v2/api/site/{site}/nat` with standard CRUD operations. Unlike firewall policies or routing tables, NAT rules use a dedicated policy framework with both Source NAT (SNAT) and Destination NAT (DNAT) capabilities. The integration already has V2 API infrastructure in place with QoS and firewall policies, providing a foundation for NAT rule support.

## Goals and Non-Goals

- **Goals**:
  - Create switch entities for all configured custom NAT rules with enable/disable functionality
  - Integrate with the unified `unr_changed` trigger system for NAT rule change notifications  
  - Support backup and restoration of NAT rule configurations through switch state management
  - Maintain consistency with existing integration patterns and code organization
  - Provide comprehensive NAT rule metadata in trigger payloads for automation use
  - Support both SNAT and DNAT rule types with appropriate entity naming
- **Non-Goals**:
  - Creating new NAT rules through Home Assistant (only enable/disable existing rules)
  - Modifying NAT rule parameters (addresses, ports, interfaces) - configuration remains in UniFi
  - Supporting predefined/system NAT rules (only custom user-defined rules)
  - NAT rule performance monitoring or traffic analytics

## User Stories / Use Cases

- As a **network administrator**, I want to enable/disable NAT rules from Home Assistant, so that I can automate network address translation based on conditions.
- As a **security administrator**, I want to automatically disable specific SNAT rules during security incidents, so that I can control traffic flow and prevent data exfiltration.
- As a **DNS management user**, I want to toggle destination NAT rules that redirect DNS queries, so that I can switch between different DNS providers based on network conditions.
- As a **home automation user**, I want to receive notifications when NAT rules are changed, so that I can monitor network configuration changes that affect traffic routing.
- As a **service management operator**, I want to activate backup NAT rules when primary services fail, so that traffic redirection maintains service availability.
- As an **integration user**, I want NAT rule changes to trigger Home Assistant automations, so that I can coordinate network address translation with other home systems.

## Requirements

- **Functional**:
  - **API Integration**: Implement NAT mixin to interface with UniFi V2 NAT API (`/proxy/network/v2/api/site/{site}/nat`)
  - **Entity Creation**: Generate Home Assistant switch entities for each configured custom NAT rule with unique IDs based on rule parameters
  - **Enable/Disable Operations**: Support toggling NAT rule `enabled` status through switch entity state changes
  - **State Synchronization**: Maintain entity states synchronized with UniFi Network NAT rule configurations  
  - **Trigger Integration**: Fire `unr_changed` triggers with `change_type: "nat"` when NAT rules are modified
  - **Service Integration**: Full integration with existing services for automation support:
    - **Backup/Restore**: NAT rules included in `backup_rules` and `restore_rules` services
    - **Rule Toggling**: Support `toggle_rule` service for programmatic NAT rule enable/disable
    - **Bulk Operations**: Support `bulk_update_rules` service for mass NAT rule state changes
  - **Rule Type Support**: Handle both SNAT and DNAT rule types with appropriate naming conventions
  - **Predefined Rule Filtering**: Exclude system/predefined NAT rules, only manage custom user-defined rules
  - **Naming Convention**: Generate descriptive entity names from rule descriptions, IP addresses, and NAT type
  - **Error Handling**: Graceful handling of API failures, network timeouts, and invalid rule states
  
- **Non-Functional**:
  - **Performance**: NAT rule polling integrated with existing smart polling system (base 300s, active 30s intervals)
  - **Resource Usage**: Minimal memory footprint using typed models and efficient data structures
  - **Reliability**: NAT rule operations must not disrupt existing firewall/routing rule functionality
  - **Security**: All API interactions use existing authentication mechanisms with proper error handling
  - **Compatibility**: Support UniFi Network Controller versions 9.0+ with V2 NAT API availability

## Design Overview

The NAT rules feature extends the existing UniFi Network Rules architecture by adding NAT capabilities to the established patterns for switch entities and unified triggers.

- **Components**:
  - **NATMixin** (`udm/nat.py`): New mixin class for NAT rule API operations using V2 endpoint patterns
  - **NATRule** (`models/nat_rule.py`): Typed data model for NAT rule configurations with support for SNAT/DNAT types
  - **NATRuleSwitch** (`switch.py`): Home Assistant switch entity for NAT rule enable/disable
  - **Unified Trigger Integration**: Extends existing `unr_changed` trigger with `change_type: "nat"`
  
- **Data Flow**:
  1. **Discovery**: Coordinator polls V2 NAT API and creates NATRule models (filtered to custom rules only)
  2. **Entity Creation**: Switch platform generates NATRuleSwitch entities for each custom NAT rule
  3. **State Updates**: Smart polling system detects NAT rule changes and updates entity states  
  4. **User Actions**: Switch toggle operations call NATMixin methods to update UniFi
  5. **Change Notifications**: Modified NAT rules trigger `unr_changed` events with NAT rule metadata

## Configuration

No additional configuration is required for NAT rules support. The feature automatically discovers and creates switch entities for existing custom NAT rules configured in UniFi Network.

**Entity Naming Examples:**

```yaml
# Switch entities will be created with descriptive names based on rule descriptions and NAT type:
switch.unr_nat_snat_dns_redirect_10_0_1_100            # SNAT rule: "DNS Redirect" for 10.0.1.100
switch.unr_nat_dnat_web_server_80_443                  # DNAT rule: "Web Server" ports 80→443
switch.unr_nat_snat_guest_isolation_192_168_2_0        # SNAT rule: "Guest Isolation" for 192.168.2.0/24
```

## Triggers & Events

NAT rules integrate with the existing unified trigger system using the `unr_changed` trigger type with a new `change_type: "nat"`.

**Basic NAT Rule Change Trigger:**

```yaml
trigger:
  platform: unifi_network_rules
  type: unr_changed
  change_type: nat
```

**Specific NAT Rule Monitoring:**

```yaml
trigger:
  platform: unifi_network_rules  
  type: unr_changed
  change_type: nat
  entity_id: switch.unr_nat_snat_dns_redirect_10_0_1_100
  change_action: 
    - enabled
    - disabled
```

**NAT Rule Type Filtering:**

```yaml
trigger:
  platform: unifi_network_rules
  type: unr_changed
  change_type: nat
  name_filter: "*snat*"  # Only SNAT rules
  change_action: enabled
```

**Service Integration Examples:**

```yaml
# Backup all NAT rules
service: unifi_network_rules.backup_rules
data:
  filename: "nat_backup_{{ now().strftime('%Y%m%d_%H%M%S') }}"

# Restore specific rule types  
service: unifi_network_rules.restore_rules
data:
  filename: "nat_backup_20250923_143022"
  rule_types: ["nat"]

# Toggle specific NAT rule programmatically
service: unifi_network_rules.toggle_rule
data:
  rule_id: "68b6eef7dd411xxxxxxxxx"
  enabled: false

# Bulk update SNAT rules
service: unifi_network_rules.bulk_update_rules
data:
  name_filter: "*snat*"
  state: true
```

**Automation Examples:**

```yaml
# DNS Redirection Control
automation:
  - alias: "Enable DNS Filtering During Bedtime"
    trigger:
      platform: time
      at: "22:00:00"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.unr_nat_dnat_dns_filter_family_safe

  - alias: "Disable DNS Filtering in Morning"  
    trigger:
      platform: time
      at: "07:00:00"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.unr_nat_dnat_dns_filter_family_safe

# Security Response
automation:
  - alias: "Isolate Guest Network on Threat"
    trigger:
      platform: state
      entity_id: binary_sensor.security_threat_detected
      to: "on"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.unr_nat_snat_guest_isolation_192_168_2_0
      - service: notify.admin
        data:
          message: "Guest network isolation activated due to security threat"
```

## Data Models & Typing

**NATRule Model Requirements** (`models/nat_rule.py`):

NAT rules require comprehensive custom models as the complete NAT rule structure is not represented in the aiounifi library. Based on the API payload from issue #102, the model must support all properties:

**Core NAT Rule Properties (from API payload):**

- `_id`: Unique identifier for the NAT rule
- `description`: User-defined description of the NAT rule  
- `enabled`: Boolean flag for rule enablement status
- `exclude`: Boolean flag for rule exclusion
- `ip_address`: Target IP address for NAT operations (e.g., "100.6.6.6")
- `ip_version`: IP version ("IPV4" or "IPV6")
- `is_predefined`: Boolean flag to distinguish custom vs system rules
- `logging`: Boolean flag for rule logging enablement
- `out_interface`: Output interface ID (e.g., "67b4f927xxxxxxxxx")
- `pppoe_use_base_interface`: Boolean flag for PPPoE interface behavior
- `protocol`: Protocol specification ("all", "tcp", "udp", etc.)
- `rule_index`: Integer ordering index for rule precedence
- `setting_preference`: Preference setting ("manual" or "auto")
- `site_id`: UniFi site identifier
- `type`: NAT rule type ("SNAT" or "DNAT")

**Nested Filter Objects:**

`destination_filter` and `source_filter` objects must support:

- `address`: Optional IP address or network (e.g., "10.1.9.5")  
- `filter_type`: Filter type ("NONE", "ADDRESS_AND_PORT", "ADDRESS", "PORT")
- `firewall_group_ids`: Array of firewall group references
- `invert_address`: Boolean flag for address inversion
- `invert_port`: Boolean flag for port inversion

**Model Requirements:**

- **Complete API Coverage**: All properties from the V2 NAT API payload must be supported
- **Type Safety**: Use proper typing with Literal types for constrained values (SNAT/DNAT, IPV4/IPV6, etc.)
- **Nested Object Support**: Proper handling of destination_filter and source_filter complex objects
- **Custom Rule Detection**: Logic to filter out predefined/system rules using `is_predefined` flag
- **Entity Naming Logic**: Methods to generate descriptive Home Assistant entity names from rule properties
- **Serialization Support**: Ability to convert back to API format for update operations

**Entity Naming Requirements:**

The model must provide intelligent entity naming that may combine:

- NAT type prefix (SNAT/DNAT)
- Rule description (if available)
- Primary IP address information
- Port information (if applicable)

**Custom Rule Filtering:**

Model must implement logic to distinguish custom NAT rules (user-created) from predefined system rules, as only custom rules should generate Home Assistant entities.

Integration requires custom typed models as NAT rule structures and V2 NAT API endpoints are not currently represented in the aiounifi library.

## Observability & Diagnostics

**Logging Strategy:**

- **DEBUG**: NAT rule discovery, entity creation/updates, API request/response details, rule filtering logic
- **INFO**: NAT rule enable/disable operations, trigger events, configuration changes  
- **WARNING**: API failures, timeout issues, invalid rule configurations, predefined rule filtering
- **ERROR**: Critical failures preventing NAT rule management functionality

**Diagnostic Data:**

- NAT rule count and status distribution (SNAT vs DNAT, enabled vs disabled)

## Performance & Resource Management

**Smart Polling Integration:**

- NAT rule data fetched during existing coordinator refresh cycles
- No additional API calls beyond standard integration polling intervals
- NAT rule changes detected through unified change detection system

**Resource Targets:**

- **API Calls**: Integrated with existing polling - no separate requests  
- **Entity Count**: 1 switch entity per configured custom NAT rule

**Caching Strategy:**

- NAT rule configurations cached in coordinator data
- Entity states synchronized on polling intervals

## Reliability & Error Handling

**API Error Patterns:**

- **Authentication Failures**: Use existing integration auth retry mechanisms
- **Network Timeouts**: Graceful degradation with existing timeout handling
- **Invalid Rule States**: Log warnings and maintain last known good state

**Error Recovery:**

- Failed NAT rule operations logged but don't affect other integration functions
- Entity states reflect last known UniFi configuration on communication failures  
- Automatic retry on temporary API failures using existing coordinator patterns

## Migration & Breaking Changes (if any)

**No Breaking Changes**: This is a new feature addition with no impact on existing functionality.

**Configuration Migration**: Not applicable - no configuration changes required.

**Entity Migration**: New switch entities will be created automatically on first discovery of custom NAT rules.

**Service Updates**: Existing services (`backup_rules`, `restore_rules`, `toggle_rule`, `bulk_update_rules`) will be extended to support NAT rules without breaking existing functionality.

## Success Criteria & Metrics

- **Primary Objectives**:
  - All configured custom NAT rules discoverable as Home Assistant switch entities
  - Trigger events fire reliably for all NAT rule state changes
  - Integration with existing automation patterns works seamlessly
  - Predefined NAT rules properly filtered out from entity creation

- **Performance Metrics**:
  - No impact on existing polling intervals or API call frequency

- **Quality Metrics**:
  - Test coverage >90% for new NAT-related code
  - Documentation completeness including automation examples
  - Error rate <1% for NAT operations under normal network conditions

## Risks & Mitigations

**Rule Filtering Risk**: Predefined vs custom rule detection may be unreliable

- *Mitigation*: Use multiple detection methods (is_predefined flag, rule naming patterns)
- *Monitoring*: Log rule filtering decisions for troubleshooting

**Concurrent Modification Risk**: Simultaneous NAT rule modifications from UniFi UI and Home Assistant

- *Mitigation*: UniFi Network remains authoritative source, Home Assistant reconciles to it. HA also uses a custom queue for all API requests.
- *Monitoring*: Log state synchronization discrepancies

## Dependencies & Constraints

**Technical Dependencies**:

- Home Assistant Core 2024.1+ (for latest switch platform features)
- Python 3.13+ (following integration standards)
- UniFi Network Controller 9.0+ with V2 NAT API

**External Dependencies**:  

- UniFi Network Controller with configured custom NAT rules
- Network connectivity to UniFi Controller API endpoints
- Sufficient UniFi user permissions for NAT rule configuration access

**Compatibility Constraints**:

- Limited to custom NAT rules only - predefined/system rules not supported
- NAT rule creation/deletion must be done through UniFi interface
- API rate limiting follows existing controller constraints
- Both SNAT and DNAT rule types supported

## Implementation Steps (High-Level)

**Phase 1: API Integration** (Issue #102)

1. Create `NATMixin` class in `udm/nat.py` with NAT API methods (`get_nat_rules`, `update_nat_rule`)
2. Add NAT API endpoints to constants (`API_ENDPOINT_NAT_RULES`, `API_ENDPOINT_NAT_RULE_DETAIL`)  
3. Implement comprehensive `NATRule` model in `models/nat_rule.py` with:
   - Full NAT rule data structure support (all fields from API payload)
   - Nested filter objects (`NATRuleDestinationFilter`, `NATRuleSourceFilter`)
   - Custom vs predefined rule filtering logic
   - Smart entity naming methods for SNAT/DNAT types
4. Test API integration with mock NAT rule configurations

**Phase 2: Entity & Trigger Integration** (Issue #117)  

1. Implement `NATRuleSwitch` class extending base switch entity patterns
2. Add NAT rule discovery to coordinator refresh cycle with custom rule filtering
3. Extend unified trigger system with `change_type: "nat"` support
4. Add NAT rule entities to switch platform setup and entity management
5. Implement entity naming conventions and unique ID generation for SNAT/DNAT types
6. Integrate NAT rules with existing services:
   - Update backup/restore services to support NAT rule type
   - Ensure `toggle_rule` service works with NAT rule entities
   - Add NAT rule support to `bulk_update_rules` service
7. Test switch operations and trigger events end-to-end

### Phase 3: Testing & Documentation

1. Create comprehensive test suite covering API, entities, triggers, and services
2. Update README with NAT rules in supported features list and trigger documentation

## Open Questions

**Resolved:**

- **Entity Naming**: NAT rule names will include NAT type prefix (SNAT/DNAT), description, and relevant IP addresses
- **Documentation**: README will be updated to include NAT rules in supported features and trigger documentation sections
- **Performance Validation**: Not required - performance will be constrained by UniFi device API capabilities
- **Version Support**: UniFi Network Controller 9.0+ officially supported (NAT API availability varies)
- **API Permissions**: Admin permissions required (same as entire integration - no change needed)
- **Rule Limits**: No configurable limits - UniFi Network manages NAT rule constraints
- **Rule Type Support**: Both SNAT and DNAT types supported with appropriate entity naming

**Remaining:**

- None - all technical questions have been resolved

## Appendix (Optional)

**Related Issues:**

- [Issue #101](https://github.com/sirkirby/unifi-network-rules/issues/101): Include NAT rules
- [Issue #102](https://github.com/sirkirby/unifi-network-rules/issues/102): Switch entities for UniFi NAT Rules  
- [Issue #117](https://github.com/sirkirby/unifi-network-rules/issues/117): Add new switches and trigger change type for NAT

**Related PRDs:**

- [PRD.001](./PRD.001%20-%20Smart%20Polling%20and%20Unified%20Triggers.md): Smart Polling Architecture and Unified Trigger System
- [PRD.003](./PRD.003%20-%20Static%20Routes%20Support.md): Static Routes Support

**API Reference:**

```json
{
  "meta": {"rc": "ok"},
  "data": [
    {
      "_id": "68b6eef7dd411xxxxxxxxx",
      "description": "source nat test",
      "destination_filter": {
        "address": "10.1.9.5",
        "filter_type": "ADDRESS_AND_PORT",
        "firewall_group_ids": [],
        "invert_address": false,
        "invert_port": false
      },
      "enabled": false,
      "exclude": false,
      "ip_address": "100.6.6.6",
      "ip_version": "IPV4",
      "is_predefined": false,
      "logging": false,
      "out_interface": "67b4f927xxxxxxxxx",
      "pppoe_use_base_interface": false,
      "protocol": "all",
      "rule_index": 0,
      "setting_preference": "manual",
      "source_filter": {
        "filter_type": "NONE",
        "firewall_group_ids": [],
        "invert_address": false,
        "invert_port": false
      },
      "type": "SNAT"
    }
  ]
}
```
