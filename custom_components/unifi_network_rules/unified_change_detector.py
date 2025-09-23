"""Unified Change Detection Engine for UniFi Network Rules."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, List
from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import LOGGER, DOMAIN


@dataclass
class ChangeEvent:
    """Represents a detected change in the UniFi system."""
    
    entity_id: str
    unique_id: str
    rule_id: str
    change_type: str  # firewall_policy, traffic_rule, traffic_route, port_forward, etc.
    change_action: str  # created, deleted, enabled, disabled, modified
    entity_name: str
    old_state: Optional[Dict[str, Any]]
    new_state: Optional[Dict[str, Any]]
    timestamp: str
    source: str = "polling"  # Always "polling" in new architecture


class UnifiedChangeDetector:
    """Centralized change detection and trigger emission system."""
    
    def __init__(self, hass: HomeAssistant, coordinator):
        """Initialize the change detector.
        
        Args:
            hass: Home Assistant instance
            coordinator: The coordinator instance
        """
        self.hass = hass
        self.coordinator = coordinator
        self._previous_state: Dict[str, Dict[str, Any]] = {}
        
        # Rule type mapping for entity types
        self._rule_type_mapping = {
            "port_forwards": "port_forward",
            "traffic_routes": "traffic_route", 
            "firewall_policies": "firewall_policy",
            "traffic_rules": "traffic_rule",
            "legacy_firewall_rules": "firewall_policy",  # Treat legacy as firewall_policy
            "firewall_zones": "firewall_zone",
            "wlans": "wlan",
            "qos_rules": "qos_rule",
            "vpn_clients": "vpn_client",
            "vpn_servers": "vpn_server",
            "devices": "device",
            "port_profiles": "port_profile",
            "networks": "network",
            "static_routes": "route"
        }

    async def detect_and_fire_changes(self, current_data: Dict[str, List[Any]]) -> List[ChangeEvent]:
        """Detect changes and fire unified triggers.
        
        Args:
            current_data: Current coordinator data
            
        Returns:
            List of detected change events
        """
        changes = []
        
        # Build current state snapshot
        current_state = self._build_state_snapshot(current_data)
        
        LOGGER.debug("[CHANGE_DETECTOR] Built current state snapshot: %d rule types, %d total entities",
                    len(current_state), sum(len(entities) for entities in current_state.values()))
        
        # Compare with previous state to detect changes
        changes.extend(await self._detect_changes(current_state))
        
        # Fire triggers for all detected changes
        for change in changes:
            await self._fire_unified_trigger(change)
        
        # Update previous state for next comparison
        self._previous_state = current_state
        
        LOGGER.debug("[CHANGE_DETECTOR] Detection complete: %d changes found", len(changes))
        return changes
    
    async def _detect_changes(self, current_state: Dict[str, Dict[str, Any]]) -> List[ChangeEvent]:
        """Detect changes between previous and current state.
        
        Args:
            current_state: Current state snapshot
            
        Returns:
            List of detected changes
        """
        changes = []
        
        # Check for new and modified entities
        for rule_type, current_entities in current_state.items():
            previous_entities = self._previous_state.get(rule_type, {})
            
            for entity_id, current_entity_state in current_entities.items():
                previous_entity_state = previous_entities.get(entity_id)
                
                if previous_entity_state is None:
                    # New entity created
                    change = await self._create_change_event(
                        entity_id, rule_type, None, current_entity_state, "created"
                    )
                    if change:
                        changes.append(change)
                        LOGGER.debug("[CHANGE_DETECTOR] New entity detected: %s (%s)", entity_id, rule_type)
                else:
                    # Check for modifications
                    change_action = self._determine_change_action(previous_entity_state, current_entity_state)
                    if change_action:
                        change = await self._create_change_event(
                            entity_id, rule_type, previous_entity_state, current_entity_state, change_action
                        )
                        if change:
                            changes.append(change)
                            LOGGER.debug("[CHANGE_DETECTOR] Entity modified: %s (%s) - %s", entity_id, rule_type, change_action)
        
        # Check for deleted entities
        for rule_type, previous_entities in self._previous_state.items():
            current_entities = current_state.get(rule_type, {})
            
            for entity_id, previous_entity_state in previous_entities.items():
                if entity_id not in current_entities:
                    change = await self._create_change_event(
                        entity_id, rule_type, previous_entity_state, None, "deleted"
                    )
                    if change:
                        changes.append(change)
                        LOGGER.debug("[CHANGE_DETECTOR] Entity deleted: %s (%s)", entity_id, rule_type)
        
        return changes
    
    def _determine_change_action(self, old_state: Dict[str, Any], new_state: Dict[str, Any]) -> Optional[str]:
        """Determine what type of change occurred.
        
        Args:
            old_state: Previous entity state
            new_state: Current entity state
            
        Returns:
            Change action string or None if no significant change
        """
        # Check for enabled/disabled changes first (most important)
        old_enabled = old_state.get("enabled", False)
        new_enabled = new_state.get("enabled", False)
        
        if old_enabled != new_enabled:
            return "enabled" if new_enabled else "disabled"
        
        # Check for other significant changes
        significant_fields = ["name", "description", "action", "protocol", "port", 
                            "dst_port", "fwd_port", "gateway", "next_hop", "ssid",
                            "bandwidth_limit", "rate_limit", "kill_switch"]
        
        for field in significant_fields:
            if old_state.get(field) != new_state.get(field):
                return "modified"
        
        return None  # No significant change detected
    
    async def _create_change_event(
        self, 
        entity_id: str, 
        rule_type: str, 
        old_state: Optional[Dict[str, Any]], 
        new_state: Optional[Dict[str, Any]], 
        change_action: str
    ) -> Optional[ChangeEvent]:
        """Create a change event from detected changes.
        
        Args:
            entity_id: The entity ID that changed
            rule_type: The rule type (coordinator data key)
            old_state: Previous state (None for created)
            new_state: Current state (None for deleted)
            change_action: Type of change (created, deleted, enabled, disabled, modified)
            
        Returns:
            ChangeEvent or None if event couldn't be created
        """
        try:
            # Extract relevant information
            rule_id = entity_id  # For now, use entity_id as rule_id
            if new_state:
                rule_id = new_state.get('_id') or new_state.get('id') or entity_id
            elif old_state:
                rule_id = old_state.get('_id') or old_state.get('id') or entity_id
            
            # Generate entity name
            entity_name = self._get_entity_name(rule_type, old_state, new_state, rule_id)
            
            # Generate unique ID for Home Assistant entity
            unique_id = f"unr_{self._rule_type_mapping.get(rule_type, rule_type)}_{rule_id}"
            
            # Generate entity ID for Home Assistant entity
            ha_entity_id = f"switch.{unique_id}"
            
            # Get change type for trigger
            change_type = self._rule_type_mapping.get(rule_type, rule_type)
            
            return ChangeEvent(
                entity_id=ha_entity_id,
                unique_id=unique_id,
                rule_id=rule_id,
                change_type=change_type,
                change_action=change_action,
                entity_name=entity_name,
                old_state=old_state,
                new_state=new_state,
                timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                source="polling"
            )
            
        except Exception as err:
            LOGGER.error("[CHANGE_DETECTOR] Error creating change event: %s", err)
            return None
    
    def _get_entity_name(self, rule_type: str, old_state: Optional[Dict], new_state: Optional[Dict], rule_id: str) -> str:
        """Extract a meaningful entity name from rule data.
        
        Args:
            rule_type: The rule type
            old_state: Previous state
            new_state: Current state
            rule_id: Rule ID
            
        Returns:
            Human-readable entity name
        """
        # Use new_state preferentially, fall back to old_state
        state = new_state or old_state
        if not state:
            return f"Unknown {rule_type} {rule_id[:8]}"
        
        # Try common name fields
        for name_field in ["name", "description", "label", "title"]:
            if name_field in state and state[name_field]:
                return str(state[name_field])
        
        # Rule-type specific naming
        if rule_type == "port_forwards":
            dst_port = state.get("dst_port", "")
            fwd_port = state.get("fwd_port", "")
            if dst_port and fwd_port:
                return f"Port Forward {dst_port} → {fwd_port}"
            elif dst_port:
                return f"Port Forward {dst_port}"
        
        elif rule_type == "firewall_policies":
            action = state.get("action", "").upper()
            if action:
                return f"Firewall {action} Rule {rule_id[:8]}"
        
        elif rule_type == "qos_rules":
            # Try bandwidth or rate limit info
            if "bandwidth_limit" in state:
                return f"QoS Rule {rule_id[:8]} ({state['bandwidth_limit']})"
            elif "rate_limit" in state:
                return f"QoS Rule {rule_id[:8]} (Rate: {state['rate_limit']})"
        
        elif rule_type == "wlans":
            ssid = state.get("ssid", "")
            if ssid:
                return f"WLAN: {ssid}"
        
        elif rule_type == "devices":
            device_name = state.get("name", "")
            if device_name:
                return f"Device: {device_name}"
        
        # Generic fallback
        return f"{rule_type.replace('_', ' ').title()} {rule_id[:8]}"
    
    async def _fire_unified_trigger(self, change: ChangeEvent) -> None:
        """Fire the unified unr_changed trigger.
        
        Args:
            change: The change event to fire
        """
        try:
            # Prepare trigger data payload
            trigger_data = {
                "platform": DOMAIN,
                "type": "unr_changed",
                "entity_id": change.entity_id,
                "unique_id": change.unique_id,
                "rule_id": change.rule_id,
                "change_type": change.change_type,
                "change_action": change.change_action,
                "entity_name": change.entity_name,
                "old_state": change.old_state,
                "new_state": change.new_state,
                "timestamp": change.timestamp,
                "source": change.source
            }
            
            # Dispatch the unified trigger event
            signal_name = f"{DOMAIN}_trigger_unr_changed"
            async_dispatcher_send(self.hass, signal_name, trigger_data)
            
            LOGGER.debug("[CHANGE_DETECTOR] Fired unified trigger: %s for %s (%s)", 
                        change.change_action, change.entity_name, change.change_type)
            
        except Exception as err:
            LOGGER.error("[CHANGE_DETECTOR] Error firing unified trigger: %s", err)
    
    def _build_state_snapshot(self, data: Dict[str, List[Any]]) -> Dict[str, Dict[str, Any]]:
        """Build a state snapshot for comparison.
        
        Args:
            data: Current coordinator data
            
        Returns:
            Nested dictionary of rule_type -> entity_id -> state
        """
        snapshot = {}
        
        for rule_type, entities in data.items():
            if rule_type not in self._rule_type_mapping:
                continue  # Skip unknown rule types
                
            snapshot[rule_type] = {}
            
            for entity in entities:
                try:
                    # Handle both typed objects and raw dictionaries
                    if hasattr(entity, 'raw') and isinstance(entity.raw, dict):
                        # This is a typed aiounifi object with raw data
                        entity_data = entity.raw.copy()
                        entity_id = entity_data.get('_id') or entity_data.get('id')
                        
                        # For objects with computed properties (like PortProfile.enabled), 
                        # we need to capture those properties in the state snapshot
                        if hasattr(entity, 'enabled'):
                            entity_data['enabled'] = entity.enabled
                    elif isinstance(entity, dict):
                        # This is a raw dictionary
                        entity_data = entity.copy()
                        entity_id = entity_data.get('_id') or entity_data.get('id')
                    else:
                        # Try to get attributes directly
                        entity_id = getattr(entity, 'id', None) or getattr(entity, '_id', None)
                        if entity_id:
                            # Convert to dictionary representation
                            entity_data = {}
                            for attr in ['id', '_id', 'enabled', 'name', 'description', 'action', 'protocol']:
                                if hasattr(entity, attr):
                                    entity_data[attr] = getattr(entity, attr)
                        else:
                            continue  # Skip entities without ID
                    
                    if entity_id:
                        snapshot[rule_type][entity_id] = entity_data
                        
                except Exception as err:
                    LOGGER.warning("[CHANGE_DETECTOR] Error processing entity in %s: %s", rule_type, err)
                    continue
        
        return snapshot
    
    def get_status(self) -> Dict[str, Any]:
        """Get current change detector status for diagnostics.
        
        Returns:
            Status information dictionary
        """
        total_entities = sum(len(entities) for entities in self._previous_state.values())
        
        return {
            "previous_state_entities": total_entities,
            "rule_types_tracked": len(self._previous_state),
            "rule_type_mapping": self._rule_type_mapping,
            "last_snapshot_types": list(self._previous_state.keys())
        }
