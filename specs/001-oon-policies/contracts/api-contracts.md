# API Contracts: Object-Oriented Network Policies

**Date**: 2025-11-11  
**Feature**: Object-Oriented Network Policies Support  
**API Version**: UniFi Network v2 API

## Base URL

All endpoints are relative to the UniFi controller base URL with site context:
- Base: `https://{controller_host}:{port}`
- Site Context: `/proxy/network/v2/api/site/{site}`

## Endpoints

### GET /object-oriented-network-configs

**Description**: Retrieve all Object-Oriented Network policies for a site.

**Method**: `GET`

**Path**: `/proxy/network/v2/api/site/{site}/object-oriented-network-configs`

**Authentication**: Required (session cookie or API token)

**Query Parameters**: None

**Request Headers**:
```
Content-Type: application/json
Cookie: {session_cookie}
```

**Response Status Codes**:
- `200 OK`: Success
- `404 Not Found`: Endpoint not available (controller doesn't support OON policies)
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Insufficient permissions

**Response Body (200 OK)**:
```json
[
  {
    "id": "67890abcdef1234567890",
    "name": "YouTube Blocking",
    "enabled": true,
    "target_type": "CLIENTS",
    "targets": ["28:70:4e:xx:xx:xx"],
    "qos": {
      "enabled": false,
      "all_traffic": true,
      "mode": "LIMIT",
      "apps": {"enabled": false, "values": []},
      "domains": {"enabled": false, "values": []},
      "ip_addresses": {"enabled": false, "values": []},
      "regions": {"enabled": false, "values": []},
      "download_limit": {"enabled": false, "limit": 10000, "burst": "DISABLED"},
      "upload_limit": {"enabled": false, "limit": 10000, "burst": "DISABLED"}
    },
    "route": {
      "enabled": true,
      "all_traffic": true,
      "network_id": "600ee7b246fdxxxxxxxxxxxx",
      "kill_switch": true,
      "apps": {"enabled": false, "values": []},
      "domains": {"enabled": false, "values": []},
      "ip_addresses": {"enabled": false, "values": []},
      "regions": {"enabled": false, "values": []}
    },
    "secure": {
      "enabled": true,
      "internet": {
        "mode": "ALLOWLIST",
        "everything": true,
        "apps": {"enabled": false, "values": []},
        "domains": {"enabled": false, "values": []},
        "ip_addresses": {"enabled": false, "values": []},
        "regions": {"enabled": false, "values": []},
        "schedule": {"mode": "ALWAYS"}
      }
    }
  }
]
```

**Response Body (404 Not Found)**:
```json
{
  "meta": {
    "rc": "error",
    "msg": "not found"
  }
}
```

**Error Handling**:
- 404 errors should be caught and handled gracefully (skip OON policy discovery)
- Other errors should be logged and handled according to existing error handling patterns

---

### GET /object-oriented-network-configs/{policy_id}

**Description**: Retrieve a specific Object-Oriented Network policy by ID.

**Method**: `GET`

**Path**: `/proxy/network/v2/api/site/{site}/object-oriented-network-configs/{policy_id}`

**Authentication**: Required

**Path Parameters**:
- `policy_id` (string, required): The unique identifier of the policy

**Response Status Codes**:
- `200 OK`: Success
- `404 Not Found`: Policy not found
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Insufficient permissions

**Response Body (200 OK)**: Same structure as single policy object in list endpoint

---

### PUT /object-oriented-network-configs/{policy_id}

**Description**: Update an Object-Oriented Network policy.

**Method**: `PUT`

**Path**: `/proxy/network/v2/api/site/{site}/object-oriented-network-configs/{policy_id}`

**Authentication**: Required

**Path Parameters**:
- `policy_id` (string, required): The unique identifier of the policy

**Request Headers**:
```
Content-Type: application/json
Cookie: {session_cookie}
```

**Request Body**: Full policy object with updated fields

**Example Request Body (Toggle Enabled)**:
```json
{
  "id": "67890abcdef1234567890",
  "name": "YouTube Blocking",
  "enabled": false,
  "target_type": "CLIENTS",
  "targets": ["28:70:4e:xx:xx:xx"],
  "qos": { ... },
  "route": { ... },
  "secure": { ... }
}
```

**Example Request Body (Toggle Kill Switch)**:
```json
{
  "id": "67890abcdef1234567890",
  "name": "YouTube Blocking",
  "enabled": true,
  "target_type": "CLIENTS",
  "targets": ["28:70:4e:xx:xx:xx"],
  "qos": { ... },
  "route": {
    "enabled": true,
    "all_traffic": true,
    "network_id": "600ee7b246fdxxxxxxxxxxxx",
    "kill_switch": false,
    ...
  },
  "secure": { ... }
}
```

**Response Status Codes**:
- `200 OK`: Update successful
- `400 Bad Request`: Invalid request body
- `404 Not Found`: Policy not found
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Insufficient permissions

**Response Body (200 OK)**: Updated policy object (same structure as GET response)

**Error Handling**:
- Failed updates should revert optimistic state in switch entity
- Errors should be logged with policy ID and operation type
- User-facing error messages should be clear and actionable

---

## Implementation Notes

### API Request Pattern

All requests use the existing UDM API wrapper pattern:

```python
# GET request
request = self.create_api_request("GET", API_PATH_OON_POLICIES, is_v2=True)
response = await self.controller.request(request)

# PUT request
request = self.create_api_request(
    "PUT", 
    API_PATH_OON_POLICY_DETAIL.format(policy_id=policy_id),
    data=policy_dict,
    is_v2=True
)
response = await self.controller.request(request)
```

### Error Handling

- 404 errors on GET: Return empty list, log debug message
- 404 errors on PUT: Log error, revert optimistic state
- Other errors: Log error, revert optimistic state, raise exception if needed

### Rate Limiting

Follow existing coordinator rate limiting patterns. OON policy operations should respect the same rate limits as other API operations.

### Authentication

Uses existing coordinator authentication mechanisms. No special authentication required for OON policies.

