# PRD.003 - Static Routes Support

**Author:** @sirkirby  
**Status:** Draft  

## Executive Summary

This PRD defines the requirements for adding comprehensive static route support to the UniFi Network Rules integration. The feature will enable Home Assistant users to manage UniFi static routes through:

- **Switch entities** for enabling/disabling configured static routes
- **Automated backup and restoration** of route configurations  
- **Real-time change detection** via the unified trigger system
- **Seamless integration** with existing Home Assistant automations

This extends the integration's network management capabilities beyond firewall policies and traffic rules to include routing table control, enabling complete infrastructure automation for home and small office networks.

## Background and Problem Statement

### Current Limitation

The UniFi Network Rules integration currently supports management of firewall policies, traffic rules, port forwards, QoS rules, WLANs, VPN configurations, and port profiles. However, **static routes configured in UniFi Network are not accessible** through Home Assistant, forcing users to:

- Manually manage routes through the UniFi web interface
- Unable to automate route changes based on network conditions  
- Cannot backup/restore routing configurations programmatically
- Miss route changes in Home Assistant automations and notifications

### User Impact

Network administrators managing complex home networks with multiple VLANs, VPNs, or segmented networks need dynamic routing control for:

- **Conditional route activation** (e.g., disable routes during maintenance)
- **Backup scenarios** (e.g., failover route activation)
- **Security policies** (e.g., temporarily isolating network segments)
- **Automation integration** (e.g., route changes triggered by presence detection)

### Technical Context

UniFi Network exposes static routes through a V1 REST API at `/proxy/network/api/s/default/rest/routing` with standard CRUD operations. The integration already has routing infrastructure in place (`udm/routes.py`) that handles traffic routes, providing a foundation for static route support.

## Goals and Non-Goals

- **Goals**:
  - Create switch entities for all configured static routes with enable/disable functionality
  - Integrate with the unified `unr_changed` trigger system for route change notifications  
  - Support backup and restoration of route configurations through switch state management
  - Maintain consistency with existing integration patterns and code organization
  - Provide comprehensive route metadata in trigger payloads for automation use
- **Non-Goals**:
  - Creating new static routes through Home Assistant (only enable/disable existing routes)
  - Modifying route parameters (destination, gateway, interface) - configuration remains in UniFi
  - Supporting dynamic routing protocols (OSPF, BGP) - only static routes
  - Route performance monitoring or analytics

## User Stories / Use Cases

- As a **network administrator**, I want to enable/disable static routes from Home Assistant, so that I can automate network topology changes based on conditions.
- As a **home automation user**, I want to receive notifications when routes are changed, so that I can monitor network configuration changes.
- As a **security-conscious user**, I want to automatically disable routes to isolated network segments during security incidents, so that I can limit potential attack vectors.
- As a **backup system operator**, I want to activate failover routes when primary connections fail, so that network connectivity is maintained.
- As a **maintenance technician**, I want to backup route configurations before making changes, so that I can restore them if needed.
- As an **integration user**, I want route changes to trigger Home Assistant automations, so that I can coordinate network changes with other home systems.

## Requirements

- **Functional**:
  - **API Integration**: Implement routing mixin to interface with UniFi V1 routing API (`/proxy/network/api/s/default/rest/routing`)
  - **Entity Creation**: Generate Home Assistant switch entities for each configured static route with unique IDs based on route parameters
  - **Enable/Disable Operations**: Support toggling route `enabled` status through switch entity state changes
  - **State Synchronization**: Maintain entity states synchronized with UniFi Network route configurations  
  - **Trigger Integration**: Fire `unr_changed` triggers with `change_type: "route"` when routes are modified
  - **Service Integration**: Full integration with existing services for automation support:
    - **Backup/Restore**: Static routes included in `backup_rules` and `restore_rules` services
    - **Rule Toggling**: Support `toggle_rule` service for programmatic route enable/disable
    - **Bulk Operations**: Support `bulk_update_rules` service for mass route state changes
  - **Naming Convention**: Generate descriptive entity names from route destination networks and descriptions
  - **Error Handling**: Graceful handling of API failures, network timeouts, and invalid route states
  
- **Non-Functional**:
  - **Performance**: Route polling integrated with existing smart polling system (base 300s, active 30s intervals)
  - **Resource Usage**: Minimal memory footprint using typed models and efficient data structures
  - **Reliability**: Route operations must not disrupt existing firewall/traffic rule functionality
  - **Security**: All API interactions use existing authentication mechanisms with proper error handling
  - **Compatibility**: Support UniFi Network Controller versions 7.0+ with V1 routing API availability
  - **Scalability**: Handle up to 50 static routes per site without performance degradation

## Design Overview

The static routes feature extends the existing UniFi Network Rules architecture by adding routing capabilities to the established patterns for switch entities and unified triggers.

- **Components**:
  - **StaticRouteMixin** (`udm/routes.py`): Extends existing RoutesMixin with static route API operations  
  - **StaticRoute** (`models/static_route.py`): Typed data model for static route configurations
  - **StaticRouteSwitch** (`switch.py`): Home Assistant switch entity for route enable/disable
  - **Unified Trigger Integration**: Extends existing `unr_changed` trigger with `change_type: "route"`
  
- **Data Flow**:
  1. **Discovery**: Coordinator polls V1 routing API and creates StaticRoute models
  2. **Entity Creation**: Switch platform generates StaticRouteSwitch entities for each route
  3. **State Updates**: Smart polling system detects route changes and updates entity states  
  4. **User Actions**: Switch toggle operations call StaticRouteMixin methods to update UniFi
  5. **Change Notifications**: Modified routes trigger `unr_changed` events with route metadata

## Configuration

No additional configuration is required for static routes support. The feature automatically discovers and creates switch entities for existing static routes configured in UniFi Network.

**Entity Naming Examples:**

```yaml
# Switch entities will be created with descriptive names based on user-defined names and network destinations:
switch.unr_route_192_168_2_0_24_guest_network       # Route: 192.168.2.0/24 "Guest Network"
switch.unr_route_10_0_100_0_24_backup_route         # Route: 10.0.100.0/24 "Backup Route"
switch.unr_route_172_16_0_0_16_vpn_tunnel           # Route: 172.16.0.0/16 "VPN Tunnel"
```

## Triggers & Events

Static routes integrate with the existing unified trigger system using the `unr_changed` trigger type with a new `change_type: "route"`.

**Basic Route Change Trigger:**

```yaml
trigger:
  platform: unifi_network_rules
  type: unr_changed
  change_type: route
```

**Specific Route Monitoring:**

```yaml
trigger:
  platform: unifi_network_rules  
  type: unr_changed
  change_type: route
  entity_id: switch.unr_route_192_168_2_0_24_via_guest_gateway
  change_action: 
    - enabled
    - disabled
```

**Route Enablement Automation Example:**

```yaml
automation:
  - alias: "Backup Route Activation"
    trigger:
      platform: unifi_network_rules
      type: unr_changed  
      change_type: route
      name_filter: "*backup*"
      change_action: enabled
    action:
      - service: notify.admin
        data:
          message: "Backup route {{ trigger.entity_id }} has been activated"
          data:
            route_destination: "{{ trigger.new_state.attributes.destination }}"
            route_gateway: "{{ trigger.new_state.attributes.gateway }}"
```

**Service Integration Examples:**

```yaml
# Backup all static routes
service: unifi_network_rules.backup_rules
data:
  filename: "routes_backup_{{ now().strftime('%Y%m%d_%H%M%S') }}"

# Restore specific route types  
service: unifi_network_rules.restore_rules
data:
  filename: "routes_backup_20250922_143022"
  rule_types: ["route"]

# Toggle specific route programmatically
service: unifi_network_rules.toggle_rule
data:
  rule_id: "6750795xxxxxxxxxxxxxxxx"
  enabled: false

# Bulk update routes matching pattern
service: unifi_network_rules.bulk_update_rules
data:
  name_filter: "*backup*"
  state: true
```

## Data Models & Typing

**StaticRoute Model** (`models/static_route.py`):

```python
@dataclass
class StaticRoute:
    """Typed model for UniFi static route configuration."""
    id: str                          # Route ID from UniFi  
    name: str                        # User-defined route name
    destination: str                 # Network CIDR (e.g., "192.168.2.0/24")
    gateway: str                     # Gateway IP or device ID
    interface: Optional[str]         # Interface name/ID
    enabled: bool                    # Route enabled status
    route_type: str                  # "interface-route" or "static-route"
    gateway_type: str                # "default", "interface", or custom
    site_id: str                     # UniFi site identifier
```

Integration leverages existing `aiounifi` models where available and extends with custom typed models for static route specific properties not covered by the base library.

## Observability & Diagnostics

**Logging Strategy:**

- **DEBUG**: Route discovery, entity creation/updates, API request/response details
- **INFO**: Route enable/disable operations, trigger events, configuration changes  
- **WARNING**: API failures, timeout issues, invalid route configurations
- **ERROR**: Critical failures preventing route management functionality

**Diagnostic Data:**

- Route count and status distribution
- API response times and error rates  
- Entity state synchronization metrics
- Trigger fire frequency and filtering effectiveness

Diagnostics will be targeted and resource-conscious, following existing integration patterns for optional detailed logging.

## Performance & Resource Management

**Smart Polling Integration:**

- Route data fetched during existing coordinator refresh cycles
- No additional API calls beyond standard integration polling intervals
- Route changes detected through unified change detection system

**Resource Targets:**

- **Memory**: <1MB additional for 50 static routes with full metadata
- **API Calls**: Integrated with existing polling - no separate requests  
- **Processing**: <50ms for route data processing per polling cycle
- **Entity Count**: 1 switch entity per configured static route

**Caching Strategy:**

- Route configurations cached in coordinator data
- Entity states synchronized on polling intervals
- No separate route-specific caching layer needed

## Reliability & Error Handling

**API Error Patterns:**

- **Authentication Failures**: Use existing integration auth retry mechanisms
- **Network Timeouts**: Graceful degradation with existing timeout handling
- **Invalid Route States**: Log warnings and maintain last known good state
- **API Version Changes**: Detect V1 routing API availability during startup

**Error Recovery:**

- Failed route operations logged but don't affect other integration functions
- Entity states reflect last known UniFi configuration on communication failures  
- Automatic retry on temporary API failures using existing coordinator patterns

**Circuit Breaker**: Leverage existing integration circuit breaker patterns for API failures.

## Migration & Breaking Changes (if any)

**No Breaking Changes**: This is a new feature addition with no impact on existing functionality.

**Configuration Migration**: Not applicable - no configuration changes required.

**Entity Migration**: New switch entities will be created automatically on first discovery of static routes.

## Success Criteria & Metrics

- **Primary Objectives**:
  - All configured static routes discoverable as Home Assistant switch entities
  - Route enable/disable operations complete within 10 seconds  
  - Trigger events fire reliably for all route state changes
  - Integration with existing automation patterns works seamlessly

- **Performance Metrics**:
  - Route API response time <2 seconds under normal conditions
  - Memory usage increase <1MB for typical home network scenarios
  - No impact on existing polling intervals or API call frequency

- **Quality Metrics**:
  - Test coverage >90% for new route-related code
  - Documentation completeness including automation examples
  - Error rate <1% for route operations under normal network conditions

## Risks & Mitigations

**API Compatibility Risk**: UniFi V1 routing API may change without notice

- *Mitigation*: Implement API version detection and graceful degradation
- *Monitoring*: Log API response formats for early change detection

**Performance Impact**: Additional API calls may affect system performance  

- *Mitigation*: Integrate with existing smart polling system, no separate API requests
- *Monitoring*: Track coordinator refresh times and resource usage

**Route Conflict Risk**: Simultaneous route modifications from UniFi UI and Home Assistant

- *Mitigation*: UniFi Network remains authoritative source, Home Assistant reconciles to it
- *Monitoring*: Log state synchronization discrepancies

**Scale Risk**: Large numbers of routes may impact entity management performance

- *Mitigation*: Implement entity limits and performance monitoring  
- *Monitoring*: Track entity creation/update times and memory usage

## Dependencies & Constraints

**Technical Dependencies**:

- Home Assistant Core 2024.1+ (for latest switch platform features)
- `aiounifi` library with routing API support
- Python 3.11+ (following integration standards)
- UniFi Network Controller 9.0+ with V1 routing API

**External Dependencies**:  

- UniFi Network Controller with configured static routes
- Network connectivity to UniFi Controller API endpoints
- Sufficient UniFi user permissions for routing configuration access

**Compatibility Constraints**:

- Limited to static routes only - dynamic routing protocols not supported
- Route creation/deletion must be done through UniFi interface
- API rate limiting follows existing controller constraints

## Implementation Steps (High-Level)

**Phase 1: API Integration** (Issue #115)

1. Extend `RoutesMixin` with static route API methods (`get_static_routes`, `update_static_route`)
2. Add routing API endpoints to constants (`API_PATH_STATIC_ROUTES`, `API_PATH_STATIC_ROUTE_DETAIL`)  
3. Create `StaticRoute` typed model with proper field mappings
4. Test API integration with mock static route configurations

**Phase 2: Entity & Trigger Integration** (Issue #116)  

1. Implement `StaticRouteSwitch` class extending base switch entity patterns
2. Add static route discovery to coordinator refresh cycle
3. Extend unified trigger system with `change_type: "route"` support
4. Add route entities to switch platform setup and entity management
5. Implement entity naming conventions and unique ID generation
6. Integrate static routes with existing services:
   - Update backup/restore services to support static route type
   - Ensure `toggle_rule` service works with static route entities
   - Add static route support to `bulk_update_rules` service
7. Test switch operations and trigger events end-to-end

**Phase 3: Testing & Documentation**

1. Create comprehensive test suite covering API, entities, triggers, and services
2. Update README with static routes in supported features list and trigger documentation
3. Integration testing with UniFi Network Controller 9.0+ versions

## Open Questions

**Resolved:**

- **Entity Naming**: Route names will be based on user-defined names and network destinations only, without including interface/device information  
- **Documentation**: README will be updated to include static routes in supported features and trigger documentation sections
- **Performance Validation**: Not required - performance will be constrained by UniFi device API capabilities
- **Version Support**: UniFi Network Controller 9.0+ officially supported (unable to test versions below 9.0)
- **API Permissions**: Admin permissions required (same as entire integration - no change needed)
- **Route Limits**: No configurable limits - UniFi Network manages route constraints
- **Backup Strategy**: Static routes must be fully integrated with existing backup/restore services and rule management services

**Remaining:**
- None - all technical questions have been resolved

## Appendix (Optional)

**Related Issues:**

- [Issue #114](https://github.com/sirkirby/unifi-network-rules/issues/114): Include support for Static Routes
- [Issue #115](https://github.com/sirkirby/unifi-network-rules/issues/115): Integrate with Routing API for Static Route support  
- [Issue #116](https://github.com/sirkirby/unifi-network-rules/issues/116): Add new switches and trigger change type for routing

**Related PRDs:**

- [PRD.001](./PRD.001%20-%20Smart%20Polling%20and%20Unified%20Triggers.md): Smart Polling Architecture and Unified Trigger System
- [PRD.002](./PRD.002%20-%20Code%20Organization%20and%20Architecture%20Refactoring.md): Code Organization and Architecture Refactoring

**API Reference:**

```json
{
  "meta": {"rc": "ok"},
  "data": [
    {
      "static-route_interface": "600ee7bxxxxxxxxxxxx",
      "static-route_network": "192.168.2.0/24", 
      "gateway_device": "60:60:60:60:60",
      "name": "Route Name",
      "site_id": "600ee7xxxxxxxxxxxxxxx", 
      "gateway_type": "default",
      "static-route_type": "interface-route",
      "_id": "6750795xxxxxxxxxxxxxxxx",
      "type": "static-route",
      "enabled": true
    }
  ]
}
```
