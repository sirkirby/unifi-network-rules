# Data Model: Object-Oriented Network Policies

**Date**: 2025-11-11  
**Feature**: Object-Oriented Network Policies Support

## Entity: OONPolicy

### Overview

Represents a UniFi Object-Oriented Network policy that combines policy, traffic routing, QoS, and security features into a unified configuration rule.

### Core Attributes

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `str` | Yes | Unique policy identifier (top-level `id` from API) |
| `name` | `str` | Yes | Display name for the policy (top-level `name` from API) |
| `enabled` | `bool` | Yes | Whether the policy is currently enabled (top-level `enabled` from API) |
| `target_type` | `str` | Yes | Type of targets: `"CLIENTS"`, `"NETWORKS"`, etc. |
| `targets` | `List[str]` | Yes | List of target identifiers (MAC addresses, network IDs, etc.) |

### Nested Configuration Objects

#### QoS Configuration (`qos`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | `bool` | Yes | Whether QoS is enabled for this policy |
| `all_traffic` | `bool` | Yes | Whether QoS applies to all traffic |
| `mode` | `str` | Yes | QoS mode: `"LIMIT"`, `"PRIORITIZE"`, etc. |
| `apps` | `Dict[str, Any]` | No | App-based QoS configuration |
| `domains` | `Dict[str, Any]` | No | Domain-based QoS configuration |
| `ip_addresses` | `Dict[str, Any]` | No | IP address-based QoS configuration |
| `regions` | `Dict[str, Any]` | No | Region-based QoS configuration |
| `download_limit` | `Dict[str, Any]` | No | Download limit configuration |
| `upload_limit` | `Dict[str, Any]` | No | Upload limit configuration |

#### Routing Configuration (`route`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | `bool` | Yes | Whether routing is enabled for this policy |
| `all_traffic` | `bool` | Yes | Whether routing applies to all traffic |
| `network_id` | `str` | No | Target network ID for routing |
| `kill_switch` | `bool` | No | Whether kill switch is enabled (required for kill switch entity creation) |
| `apps` | `Dict[str, Any]` | No | App-based routing configuration |
| `domains` | `Dict[str, Any]` | No | Domain-based routing configuration |
| `ip_addresses` | `Dict[str, Any]` | No | IP address-based routing configuration |
| `regions` | `Dict[str, Any]` | No | Region-based routing configuration |

#### Security Configuration (`secure`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | `bool` | Yes | Whether security features are enabled |
| `internet` | `Dict[str, Any]` | No | Internet security configuration |

### Model Class Structure

```python
class OONPolicy:
    """Representation of a UniFi Object-Oriented Network policy."""
    
    def __init__(self, data: Dict[str, Any]) -> None:
        """Initialize OON policy from raw API data."""
        self.raw = data.copy()  # Store raw data for API updates
        
        # Core properties
        self._id = data.get("id")
        self.name = data.get("name", "")
        self.enabled = data.get("enabled", False)
        self.target_type = data.get("target_type", "CLIENTS")
        self.targets = data.get("targets", [])
        
        # Nested configurations stored as dicts (can be parsed if needed)
        self.qos = data.get("qos", {})
        self.route = data.get("route", {})
        self.secure = data.get("secure", {})
    
    @property
    def id(self) -> str:
        """Get the policy ID."""
        return self._id
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API updates."""
        return dict(self.raw)
    
    def has_kill_switch(self) -> bool:
        """Check if policy has routing enabled with kill switch."""
        route = self.route
        return (
            route.get("enabled", False) is True
            and isinstance(route.get("kill_switch"), bool)
        )
```

### Validation Rules

1. **Required Fields**: `id`, `name`, `enabled` must exist before creating entities
2. **Kill Switch Detection**: Kill switch entity created only when `route.enabled` is `True` AND `route.kill_switch` is a boolean
3. **Unique Identification**: Policy ID used as unique identifier with `unr_oon_<id>` prefix

### State Transitions

#### Policy Enabled State

```
Disabled (enabled=False) → Enabled (enabled=True)
  - User toggles switch ON
  - PUT request to update policy
  - Optimistic update → API confirmation

Enabled (enabled=True) → Disabled (enabled=False)
  - User toggles switch OFF
  - PUT request to update policy
  - Optimistic update → API confirmation
```

#### Kill Switch State (if applicable)

```
Kill Switch OFF → Kill Switch ON
  - User toggles kill switch ON
  - PUT request updates route.kill_switch=True
  - Optimistic update → API confirmation

Kill Switch ON → Kill Switch OFF
  - User toggles kill switch OFF
  - PUT request updates route.kill_switch=False
  - Optimistic update → API confirmation
```

#### Entity Lifecycle

```
Policy Created in UniFi → Switch Entity Created
  - Coordinator discovers new policy
  - Entity manager creates switch entity
  - Kill switch entity created if conditions met

Policy Updated in UniFi → Switch Entity Updated
  - Coordinator detects changes
  - Entity name updated if policy name changed
  - Kill switch entity added/removed based on route config

Policy Deleted in UniFi → Switch Entity Removed
  - Coordinator detects deletion
  - Entity manager removes switch entity
  - Kill switch entity removed if exists
```

### Relationships

- **Belongs to**: UniFi Site (via site identifier in API context)
- **Targets**: Clients (MAC addresses) or Networks (network IDs)
- **Has Child**: Kill Switch Entity (optional, when routing enabled with kill switch)

### Example Data Structure

```json
{
  "id": "67890abcdef1234567890",
  "name": "YouTube Blocking",
  "enabled": true,
  "target_type": "CLIENTS",
  "targets": ["28:70:4e:xx:xx:xx"],
  "qos": {
    "enabled": false,
    "all_traffic": true,
    "mode": "LIMIT"
  },
  "route": {
    "enabled": true,
    "all_traffic": true,
    "network_id": "600ee7b246fdxxxxxxxxxxxx",
    "kill_switch": true
  },
  "secure": {
    "enabled": true,
    "internet": {
      "mode": "ALLOWLIST",
      "everything": true
    }
  }
}
```

## Entity: OONPolicySwitch

### Overview

Home Assistant switch entity that controls an OON policy's enabled state.

### Attributes

| Field | Type | Description |
|-------|------|-------------|
| `unique_id` | `str` | Format: `unr_oon_<policy_id>` |
| `name` | `str` | Policy name from `OONPolicy.name` |
| `is_on` | `bool` | Current enabled state (from `OONPolicy.enabled`) |
| `assumed_state` | `bool` | `True` (optimistic updates enabled) |

### Relationships

- **Parent**: UniFi Network Rules Device
- **Controls**: Single `OONPolicy` instance
- **May Have Child**: `OONPolicyKillSwitch` entity

## Entity: OONPolicyKillSwitch

### Overview

Optional child switch entity that controls the kill switch feature for OON policies with routing enabled.

### Attributes

| Field | Type | Description |
|-------|------|-------------|
| `unique_id` | `str` | Format: `unr_oon_<policy_id>_kill_switch` |
| `name` | `str` | Format: `{parent_name} Kill Switch` |
| `is_on` | `bool` | Current kill switch state (from `OONPolicy.route.kill_switch`) |
| `assumed_state` | `bool` | `True` (optimistic updates enabled) |

### Relationships

- **Parent**: `OONPolicySwitch` entity
- **Controls**: `OONPolicy.route.kill_switch` property

### Lifecycle

- **Created**: When `route.enabled` is `True` AND `route.kill_switch` exists/is boolean
- **Removed**: When `route.enabled` becomes `False` OR `route.kill_switch` is removed/disabled

