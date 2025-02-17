"""Templates for UniFi Network Rules."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .const import LOGGER

class RuleType(Enum):
    """Types of rules that can be templated."""
    FIREWALL_POLICY = "firewall_policy"
    TRAFFIC_ROUTE = "traffic_route"
    PORT_FORWARD = "port_forward"

class RuleAction(Enum):
    """Possible actions for rules."""
    ACCEPT = "accept"
    DENY = "deny"
    REJECT = "reject"
    DROP = "drop"

@dataclass
class ZoneMapping:
    """Mapping for source and destination zones."""
    zone_id: str
    networks: List[str] = field(default_factory=list)
    addresses: List[str] = field(default_factory=list)

@dataclass(kw_only=True)
class RuleTemplate:
    """Base template for creating network rules."""
    name: str
    description: str
    source: Any  # Base field for source, to be overridden by subclasses
    rule_type: RuleType = field(init=False)
    enabled: bool = True
    variables: Dict[str, str] = field(default_factory=dict)
    
    def substitute_variables(self, values: Dict[str, str]) -> Dict[str, str]:
        """Substitute template variables with provided values."""
        result = {}
        for key, template in self.variables.items():
            try:
                result[key] = template.format(**values)
            except KeyError as e:
                LOGGER.error("Missing required variable: %s", e)
                raise ValueError(f"Missing required variable: {e}")
        return result

@dataclass(kw_only=True)  # Make FirewallPolicyTemplate keyword-only to avoid argument order issues
class FirewallPolicyTemplate(RuleTemplate):
    """Template for firewall policies."""
    destination: ZoneMapping
    action: RuleAction
    protocol: Optional[str] = None
    ports: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Set rule type after initialization."""
        self.rule_type = RuleType.FIREWALL_POLICY
    
    def to_rule(self, **kwargs) -> Dict[str, Any]:
        """Convert template to a firewall policy rule."""
        variables = self.substitute_variables(kwargs)
        
        rule = {
            "name": self.name.format(**variables),
            "description": self.description.format(**variables),
            "enabled": self.enabled,
            "action": self.action.value,
            "source": {
                "zone_id": self.source.zone_id,
                "networks": [net.format(**variables) for net in self.source.networks],
                "addresses": [addr.format(**variables) for addr in self.source.addresses]
            },
            "destination": {
                "zone_id": self.destination.zone_id,
                "networks": [net.format(**variables) for net in self.destination.networks],
                "addresses": [addr.format(**variables) for addr in self.destination.addresses]
            }
        }
        
        if self.protocol:
            rule["protocol"] = self.protocol.format(**variables)
        if self.ports:
            rule["ports"] = [port.format(**variables) for port in self.ports]
            
        return rule

@dataclass(kw_only=True)  # Make TrafficRouteTemplate keyword-only to avoid argument order issues
class TrafficRouteTemplate(RuleTemplate):
    """Template for traffic routes."""
    matching_address: str
    target_gateway: str
    source: str = "any"  # Override source type from parent
    priority: int = 1000
    
    def __post_init__(self):
        """Set rule type after initialization."""
        self.rule_type = RuleType.TRAFFIC_ROUTE
    
    def to_rule(self, **kwargs) -> Dict[str, Any]:
        """Convert template to a traffic route rule."""
        variables = self.substitute_variables(kwargs)
        
        return {
            "name": self.name.format(**variables),
            "description": self.description.format(**variables),
            "enabled": self.enabled,
            "matching_address": self.matching_address.format(**variables),
            "target_gateway": self.target_gateway.format(**variables),
            "priority": self.priority,
            "source": self.source
        }

@dataclass(kw_only=True)  # Make PortForwardTemplate keyword-only to avoid argument order issues
class PortForwardTemplate(RuleTemplate):
    """Template for port forwarding rules."""
    forward_ip: str
    forward_port: str
    dest_port: str
    source: str = "any"  # Override source type from parent
    protocol: str = "tcp_udp"
    
    def __post_init__(self):
        """Set rule type after initialization."""
        self.rule_type = RuleType.PORT_FORWARD
    
    def to_rule(self, **kwargs) -> Dict[str, Any]:
        """Convert template to a port forward rule."""
        variables = self.substitute_variables(kwargs)
        
        return {
            "name": self.name.format(**variables),
            "description": self.description.format(**variables),
            "enabled": self.enabled,
            "fwd": self.forward_ip.format(**variables),
            "fwd_port": self.forward_port.format(**variables),
            "dst_port": self.dest_port.format(**variables),
            "proto": self.protocol,
            "src": self.source,
        }

class RuleTemplateRegistry:
    """Registry for rule templates."""
    
    def __init__(self):
        """Initialize the registry."""
        self._templates: Dict[str, RuleTemplate] = {}
        
    def register_template(self, template_id: str, template: RuleTemplate) -> None:
        """Register a new template."""
        self._templates[template_id] = template
        
    def get_template(self, template_id: str) -> Optional[RuleTemplate]:
        """Get a template by ID."""
        return self._templates.get(template_id)
        
    def remove_template(self, template_id: str) -> None:
        """Remove a template from the registry."""
        self._templates.pop(template_id, None)
        
    @property
    def templates(self) -> Dict[str, RuleTemplate]:
        """Get all registered templates."""
        return self._templates.copy()

# Built-in templates
BUILTIN_TEMPLATES = {
    "block_external_access": FirewallPolicyTemplate(
        name="Block External {service_name}",
        description="Block external access to {service_name}",
        source=ZoneMapping(zone_id="external"),
        destination=ZoneMapping(
            zone_id="internal",
            addresses=["{service_ip}"]
        ),
        action=RuleAction.DENY,
        protocol="{protocol}",
        ports=["{port}"],
        variables={
            "service_name": "",
            "service_ip": "",
            "protocol": "tcp",
            "port": ""
        }
    ),
    "route_vpn_traffic": TrafficRouteTemplate(
        name="Route {network_name} via VPN",
        description="Route {network_name} traffic through VPN gateway",
        source="any",
        matching_address="{network_cidr}",
        target_gateway="{vpn_gateway}",
        variables={
            "network_name": "",
            "network_cidr": "",
            "vpn_gateway": ""
        }
    ),
    "game_server_port_forward": PortForwardTemplate(
        name="{game_name} Server",
        description="Port forward for {game_name} game server",
        forward_ip="{server_ip}",
        forward_port="{game_port}",
        dest_port="{game_port}",
        source="any",
        variables={
            "game_name": "",
            "server_ip": "",
            "game_port": ""
        }
    )
}