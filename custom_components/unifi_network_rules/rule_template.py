"""Rule templates for UniFi Network Rules."""
from enum import Enum

class RuleType(Enum):
    """Enumeration of rule types."""
    FIREWALL_POLICY = "policy"
    TRAFFIC_ROUTE = "route"
    PORT_FORWARD = "port_forward"
