"""Switches module for UniFi Network Rules integration.

This module provides backward compatibility for the decomposed switch.py file.
All switch classes and setup functions are imported here to maintain compatibility.
"""
from __future__ import annotations

# Import base class
from .base import UnifiRuleSwitch

# Import setup functions
from .setup import (
    async_setup_platform,
    async_setup_entry,
    PARALLEL_UPDATES,
    RULE_TYPES,
    _ENTITY_CACHE,
    _CREATED_UNIQUE_IDS,
)

# Import firewall switches
from .firewall import (
    UnifiFirewallPolicySwitch,
    UnifiLegacyFirewallRuleSwitch,
)

# Import traffic route switches and kill switch functionality
from .traffic_route import (
    UnifiTrafficRuleSwitch,
    UnifiTrafficRouteSwitch,
    UnifiTrafficRouteKillSwitch,
    create_traffic_route_kill_switch,
)

# Import static route switches
from .static_route import (
    UnifiStaticRouteSwitch,
)

# Import network switches
from .network import (
    UnifiWlanSwitch,
    UnifiNetworkSwitch,
)

# Import port profile switches
from .port_profile import (
    UnifiPortProfileSwitch,
)

# Import port forwarding switches
from .port_forwarding import (
    UnifiPortForwardSwitch,
)

# Import NAT switches
from .nat import (
    UnifiNATRuleSwitch,
)

# Import VPN switches
from .vpn import (
    UnifiVPNClientSwitch,
    UnifiVPNServerSwitch,
)

# Import device switches
from .device import UnifiLedToggleSwitch

# Import QoS switches
from .qos import UnifiQoSRuleSwitch

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
]