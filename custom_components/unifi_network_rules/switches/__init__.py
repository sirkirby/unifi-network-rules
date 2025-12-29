"""Switches module for UniFi Network Rules integration.

This module provides backward compatibility for the decomposed switch.py file.
All switch classes and setup functions are imported here to maintain compatibility.
"""

from __future__ import annotations

# Import base class
from .base import UnifiRuleSwitch

# Import device switches
from .device import UnifiLedToggleSwitch

# Import firewall switches
from .firewall import (
    UnifiFirewallPolicySwitch,
    UnifiLegacyFirewallRuleSwitch,
)

# Import NAT switches
from .nat import (
    UnifiNATRuleSwitch,
)

# Import network switches
from .network import (
    UnifiNetworkSwitch,
    UnifiWlanSwitch,
)

# Import OON policy switches
from .oon_policy import (
    UnifiOONPolicyKillSwitch,
    UnifiOONPolicySwitch,
)

# Import port forwarding switches
from .port_forwarding import (
    UnifiPortForwardSwitch,
)

# Import port profile switches
from .port_profile import (
    UnifiPortProfileSwitch,
)

# Import QoS switches
from .qos import UnifiQoSRuleSwitch

# Import setup functions
from .setup import (
    _CREATED_UNIQUE_IDS,
    _ENTITY_CACHE,
    PARALLEL_UPDATES,
    RULE_TYPES,
    async_setup_entry,
    async_setup_platform,
)

# Import static route switches
from .static_route import (
    UnifiStaticRouteSwitch,
)

# Import traffic route switches and kill switch functionality
from .traffic_route import (
    UnifiTrafficRouteKillSwitch,
    UnifiTrafficRouteSwitch,
    UnifiTrafficRuleSwitch,
    create_traffic_route_kill_switch,
)

# Import VPN switches
from .vpn import (
    UnifiVPNClientSwitch,
    UnifiVPNServerSwitch,
)

# Export all classes and functions for backward compatibility
__all__ = [
    # Base class
    "UnifiRuleSwitch",
    # Setup functions
    "async_setup_platform",
    "async_setup_entry",
    "create_traffic_route_kill_switch",
    "PARALLEL_UPDATES",
    "RULE_TYPES",
    "_ENTITY_CACHE",
    "_CREATED_UNIQUE_IDS",
    # Firewall switches
    "UnifiFirewallPolicySwitch",
    "UnifiLegacyFirewallRuleSwitch",
    # Traffic route switches
    "UnifiTrafficRuleSwitch",
    "UnifiTrafficRouteSwitch",
    "UnifiTrafficRouteKillSwitch",
    # Static route switches
    "UnifiStaticRouteSwitch",
    # Network switches
    "UnifiWlanSwitch",
    "UnifiNetworkSwitch",
    # Port profile switches
    "UnifiPortProfileSwitch",
    # Port forwarding switches
    "UnifiPortForwardSwitch",
    # NAT switches
    "UnifiNATRuleSwitch",
    # VPN switches
    "UnifiVPNClientSwitch",
    "UnifiVPNServerSwitch",
    # Device switches
    "UnifiLedToggleSwitch",
    # QoS switches
    "UnifiQoSRuleSwitch",
    # OON policy switches
    "UnifiOONPolicySwitch",
    "UnifiOONPolicyKillSwitch",
]
