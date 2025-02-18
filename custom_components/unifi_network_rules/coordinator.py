"""Data update coordinator for UniFi Network Rules."""
from __future__ import annotations

import asyncio
from datetime import timedelta, datetime
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, LOGGER, EVENT_RULE_UPDATED, EVENT_RULE_DELETED
from .websocket import UnifiRuleWebsocket
from .udm_api import UDMAPI
from .utils.logger import log_call

class UDMUpdateCoordinator(DataUpdateCoordinator):
    """Data update coordinator with websocket support."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UDMAPI,
        name: str,
        update_interval: int
    ) -> None:
        """Initialize the UDM coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=name,
            # Longer interval since we use websockets
            update_interval=timedelta(minutes=update_interval),
        )
        self.api = api
        self._previous_data: Dict[str, Any] = {}
        self._config_entry = None  # Added proper config entry storage

    @property
    def config_entry(self):
        """Get the config entry."""
        return self._config_entry

    @config_entry.setter
    def config_entry(self, entry):
        """Set the config entry."""
        self._config_entry = entry

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API - used as backup and initial load."""
        LOGGER.debug("Running coordinator update")
        
        try:
            if not hasattr(self.api, 'capabilities'):
                LOGGER.error("API capabilities not initialized")
                raise UpdateFailed("API capabilities not initialized")
            
            # Initialize data dictionary
            data = {}
            fetch_errors = []
            
            # Always fetch port forward rules
            try:
                port_fwd_success, port_fwd_rules, port_fwd_error = await self.api.get_port_forward_rules()
                if not port_fwd_success:
                    fetch_errors.append(f"Failed to fetch port forwarding rules: {port_fwd_error}")
                else:
                    data['port_forward_rules'] = port_fwd_rules
            except Exception as e:
                fetch_errors.append(f"Error fetching port forwarding rules: {str(e)}")
            
            # Always fetch traffic routes
            if self.api.capabilities.traffic_routes:
                try:
                    routes_success, routes, routes_error = await self.api.get_traffic_routes()
                    if not routes_success:
                        fetch_errors.append(f"Failed to fetch traffic routes: {routes_error}")
                    else:
                        data['traffic_routes'] = routes
                except Exception as e:
                    fetch_errors.append(f"Error fetching traffic routes: {str(e)}")
            
            # Fetch firewall data based on capabilities
            if self.api.capabilities.zone_based_firewall:
                try:
                    policies_success, policies, policies_error = await self.api.get_firewall_policies()
                    if not policies_success:
                        fetch_errors.append(f"Failed to fetch policies: {policies_error}")
                    else:
                        data['firewall_policies'] = [
                            policy for policy in (policies or [])
                            if not policy.get('predefined', False)
                        ]
                except Exception as e:
                    fetch_errors.append(f"Error fetching firewall policies: {str(e)}")
            elif self.api.capabilities.legacy_firewall:
                try:
                    rules_success, rules, rules_error = await self.api.get_legacy_firewall_rules()
                    if not rules_success:
                        fetch_errors.append(f"Failed to fetch legacy firewall rules: {rules_error}")
                    else:
                        data['firewall_rules'] = {'data': rules or []}
                        
                    traffic_success, traffic, traffic_error = await self.api.get_legacy_traffic_rules()
                    if not traffic_success:
                        fetch_errors.append(f"Failed to fetch legacy traffic rules: {traffic_error}")
                    else:
                        data['traffic_rules'] = traffic or []
                except Exception as e:
                    fetch_errors.append(f"Error fetching legacy rules: {str(e)}")
            
            # If we have no data at all and there were errors, raise them
            if not data and fetch_errors:
                raise UpdateFailed("\n".join(fetch_errors))
                
            # If we have some data, log errors but return what we have
            if fetch_errors:
                LOGGER.warning("Some data fetching failed:\n%s", "\n".join(fetch_errors))
                
            return data
            
        except Exception as e:
            LOGGER.exception("Unexpected error in coordinator update: %s", str(e))
            raise UpdateFailed(f"Data update failed: {str(e)}")

    @callback
    def handle_websocket_message(self, msg: dict) -> None:
        """Handle websocket messages."""
        if not self.data:
            LOGGER.debug("No coordinator data available for websocket update")
            return

        msg_type = msg.get("meta", {}).get("message")
        if not msg_type:
            return
        
        data = msg.get("data", {})
        LOGGER.debug("Received websocket message: %s with data: %s", msg_type, data)

        try:
            if msg_type in ("firewall_rule_add", "firewall_rule_update", "firewall_rule_remove"):
                self._handle_firewall_rule_message(msg_type, data)
            elif msg_type in ("port_forward_add", "port_forward_update", "port_forward_remove"):
                self._handle_port_forward_message(msg_type, data)
            elif msg_type in ("traffic_rule_add", "traffic_rule_update", "traffic_rule_remove"):
                self._handle_traffic_rule_message(msg_type, data)
            elif msg_type in ("traffic_route_add", "traffic_route_update", "traffic_route_remove"):
                self._handle_traffic_route_message(msg_type, data)
            elif msg_type in ("firewall_policy_add", "firewall_policy_update", "firewall_policy_remove"):
                self._handle_firewall_policy_message(msg_type, data)
            else:
                LOGGER.debug("Unhandled message type: %s", msg_type)
        except Exception as err:
            LOGGER.error("Error handling websocket message: %s - %s", msg_type, err)

    def _update_data_list(self, data_key: str, action: str, item_data: dict) -> None:
        """Update a list in coordinator data."""
        if not isinstance(item_data, dict) or '_id' not in item_data:
            LOGGER.warning("Invalid item data for %s update: %s", data_key, item_data)
            return

        if data_key not in self.data:
            self.data[data_key] = []
            
        existing_data = self.data[data_key]
        if isinstance(existing_data, dict) and 'data' in existing_data:
            # Handle nested data structure (used by legacy firewall rules)
            data_list = existing_data['data']
        else:
            data_list = existing_data

        item_id = item_data.get("_id")
        
        try:
            # Ensure consistent data types for enabled state
            if 'enabled' in item_data:
                item_data['enabled'] = bool(item_data['enabled'])

            if action.endswith("_add"):
                if data_key == "firewall_policies" and item_data.get("predefined", False):
                    return
                # Don't add if item already exists
                if not any(item.get("_id") == item_id for item in data_list):
                    data_list.append(item_data)
                
            elif action.endswith("_update"):
                updated = False
                for i, existing in enumerate(data_list):
                    if existing.get("_id") == item_id:
                        if data_key == "firewall_policies" and item_data.get("predefined", False):
                            data_list.pop(i)
                        else:
                            # Special handling for traffic routes and port forwards
                            if data_key in ('traffic_routes', 'port_forward_rules'):
                                # Create a new dict with updated values
                                new_data = dict(existing)
                                new_data.update(item_data)
                                data_list[i] = new_data
                            else:
                                data_list[i] = {**existing, **item_data}  # Merge data
                        updated = True
                        break
                        
                # If item wasn't found but should exist, append it
                if not updated:
                    data_list.append(item_data)
                        
            elif action.endswith("_remove"):
                data_list[:] = [
                    item for item in data_list
                    if item.get("_id") != item_id
                ]

            # Update the main data structure if needed
            if isinstance(existing_data, dict) and 'data' in existing_data:
                self.data[data_key]['data'] = data_list
            else:
                self.data[data_key] = data_list

            # Store previous state for change detection
            self._previous_data[data_key] = data_list.copy() if isinstance(data_list, list) else {'data': data_list.copy()}
            
            # Trigger entity updates
            self.async_set_updated_data(self.data)
            
        except Exception as err:
            LOGGER.error(
                "Error updating data list for %s (%s): %s",
                data_key, action, str(err)
            )

    @callback
    def _handle_firewall_rule_message(self, action: str, data: dict) -> None:
        """Handle firewall rule message."""
        if self.api.capabilities.legacy_firewall:
            if 'firewall_rules' not in self.data:
                self.data['firewall_rules'] = {'data': []}
            self._update_data_list('firewall_rules', action, data)
            # Create task for websocket update
            self.hass.async_create_task(
                self._handle_websocket_update('firewall_rules', action, data),
                name="unifi_rules_ws_update"
            )

    @callback
    async def _handle_websocket_update(self, rule_type: str, action: str, data: dict) -> bool:
        """Handle websocket-based update."""
        try:
            update_start = datetime.now()
            
            # Special handling for traffic routes and port forwards
            if rule_type in ('traffic_routes', 'port_forward_rules'):
                # Ensure the data exists in the coordinator
                if rule_type not in self.data:
                    self.data[rule_type] = []
                
                # Find and update the specific rule
                rule_id = data.get('_id')
                if rule_id:
                    existing_data = self.data[rule_type]
                    current_state = None
                    
                    for i, item in enumerate(existing_data):
                        if item.get('_id') == rule_id:
                            # Store current state
                            current_state = dict(item)
                            
                            # Create new dict to avoid modifying existing data
                            updated_item = dict(item)
                            updated_item.update(data)
                            
                            # Ensure boolean type for enabled state
                            if 'enabled' in updated_item:
                                updated_item['enabled'] = bool(updated_item['enabled'])
                            
                            # Update API state first
                            success, error = await self.api.update_rule_state(
                                rule_type, 
                                rule_id, 
                                updated_item.get('enabled', False)
                            )
                            
                            if success:
                                # Only update coordinator data if API update succeeded
                                self.data[rule_type][i] = updated_item
                                # Force a coordinator update to refresh entities
                                self.async_set_updated_data(self.data)
                            else:
                                # Restore previous state if API update failed
                                if current_state:
                                    self.data[rule_type][i] = current_state
                                    self.async_set_updated_data(self.data)
                                LOGGER.error("Failed to update rule state: %s", error)
                                return False
                            
                            break
                    else:
                        # Rule not found, might be a new rule
                        if action.endswith('_add'):
                            self.data[rule_type].append(data)
            else:
                # Standard update for other rule types
                self._update_data_list(rule_type, action, data)
            
            update_duration = (datetime.now() - update_start).total_seconds()
            LOGGER.debug(
                "Websocket update for %s completed in %.3f seconds (action: %s)", 
                rule_type, update_duration, action
            )
            
            # Track websocket performance
            if not hasattr(self, '_websocket_stats'):
                self._websocket_stats = {}
            
            if rule_type not in self._websocket_stats:
                self._websocket_stats[rule_type] = {
                    'success_count': 0,
                    'failure_count': 0,
                    'total_duration': 0,
                    'last_success': None
                }
            
            stats = self._websocket_stats[rule_type]
            stats['success_count'] += 1
            stats['total_duration'] += update_duration
            stats['last_success'] = datetime.now()
            
            # Log performance stats periodically
            if stats['success_count'] % 10 == 0:
                avg_duration = stats['total_duration'] / stats['success_count']
                LOGGER.info(
                    "%s websocket stats - Success: %d, Failures: %d, Avg Duration: %.3fs",
                    rule_type,
                    stats['success_count'],
                    stats['failure_count'],
                    avg_duration
                )
            
            return True
            
        except Exception as err:
            LOGGER.warning(
                "Failed to process websocket update for %s (%s): %s", 
                rule_type, action, str(err)
            )
            
            # Track failure
            if hasattr(self, '_websocket_stats') and rule_type in self._websocket_stats:
                self._websocket_stats[rule_type]['failure_count'] += 1
            
            return False

    @callback
    def _handle_firewall_policy_message(self, action: str, data: dict) -> None:
        """Handle firewall policy message."""
        if self.api.capabilities.zone_based_firewall:
            self.hass.async_create_task(
                self._handle_websocket_update('firewall_policies', action, data),
                name="unifi_rules_ws_update"
            )

    @callback
    def _handle_traffic_rule_message(self, action: str, data: dict) -> None:
        """Handle traffic rule message."""
        if self.api.capabilities.legacy_firewall:
            self.hass.async_create_task(
                self._handle_websocket_update('traffic_rules', action, data),
                name="unifi_rules_ws_update"
            )

    @callback
    def _handle_traffic_route_message(self, action: str, data: dict) -> None:
        """Handle traffic route message."""
        try:
            # Create a copy of the original data to avoid mutation
            route_data = dict(data)
            
            # Ensure the enabled state is properly set
            if 'enabled' in route_data:
                route_data['enabled'] = bool(route_data['enabled'])
            
            if 'traffic_routes' not in self.data:
                self.data['traffic_routes'] = []
            
            # Store current state for verification
            rule_id = route_data.get('_id')
            if rule_id:
                previous_state = next(
                    (route for route in self.data['traffic_routes'] 
                     if route.get('_id') == rule_id),
                    None
                )
            
            # Handle the update with retries and state verification
            async def update_with_retry():
                for attempt in range(3):  # Try up to 3 times
                    try:
                        await self._handle_websocket_update('traffic_routes', action, route_data)
                        
                        # Verify state was properly updated
                        current_state = next(
                            (route for route in self.data['traffic_routes']
                             if route.get('_id') == rule_id),
                            None
                        )
                        
                        if current_state and current_state.get('enabled') == route_data.get('enabled'):
                            return True
                            
                        if attempt < 2:  # Don't sleep on last attempt
                            await asyncio.sleep(1)
                            
                    except Exception as e:
                        if attempt == 2:  # Last attempt
                            LOGGER.error("Failed to update traffic route after 3 attempts: %s", e)
                            if previous_state:
                                # Restore previous state in coordinator
                                self._update_data_list('traffic_routes', 'update', previous_state)
                            return False
                        await asyncio.sleep(1)  # Wait before retry
                return False
            
            self.hass.async_create_task(
                update_with_retry(),
                name="unifi_rules_traffic_update"
            )

        except Exception as err:
            LOGGER.error("Error in traffic route message handler: %s", err)

    @callback
    def _handle_port_forward_message(self, action: str, data: dict) -> None:
        """Handle port forward message."""
        try:
            # Create a copy of the original data to avoid mutation
            port_data = dict(data)
            
            # Ensure the enabled state is properly set
            if 'enabled' in port_data:
                port_data['enabled'] = bool(port_data['enabled'])
            
            if 'port_forward_rules' not in self.data:
                self.data['port_forward_rules'] = []
            
            # Handle the update with retries
            async def update_with_retry():
                for attempt in range(3):  # Try up to 3 times
                    try:
                        await self._handle_websocket_update('port_forward_rules', action, port_data)
                        return True
                    except Exception as e:
                        if attempt == 2:  # Last attempt
                            LOGGER.error("Failed to update port forward rule after 3 attempts: %s", e)
                            return False
                        await asyncio.sleep(1)  # Wait before retry
                return False
            
            self.hass.async_create_task(
                update_with_retry(),
                name="unifi_rules_portfwd_update"
            )

        except Exception as err:
            LOGGER.error("Error in port forward message handler: %s", err)
    
    @callback
    def _check_rule_changes(self, rule_type: str, new_rules: list) -> None:
        """Compare new rules with previous data and fire events for changes."""
        if not self.hass or rule_type not in self._previous_data:
            return

        previous_rules = self._previous_data.get(rule_type, [])
        if isinstance(previous_rules, dict) and 'data' in previous_rules:
            previous_rules = previous_rules['data']

        # Create maps for efficient lookup
        prev_map = {rule['_id']: rule for rule in previous_rules}
        new_map = {rule['_id']: rule for rule in new_rules}

        # Check for changes and deletions
        for rule_id, prev_rule in prev_map.items():
            if rule_id not in new_map:
                # Rule was deleted
                self.hass.bus.async_fire(
                    EVENT_RULE_DELETED,
                    {
                        "rule_id": rule_id,
                        "rule_type": rule_type,
                        "rule_data": prev_rule
                    }
                )
            else:
                # Check for changes
                new_rule = new_map[rule_id]
                if new_rule != prev_rule:
                    self.hass.bus.async_fire(
                        EVENT_RULE_UPDATED,
                        {
                            "rule_id": rule_id,
                            "rule_type": rule_type,
                            "old_state": prev_rule,
                            "new_state": new_rule
                        }
                    )

        # Check for new rules
        for rule_id in new_map:
            if rule_id not in prev_map:
                self.hass.bus.async_fire(
                    EVENT_RULE_UPDATED,
                    {
                        "rule_id": rule_id,
                        "rule_type": rule_type,
                        "old_state": None,
                        "new_state": new_map[rule_id]
                    }
                )

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Get a rule by ID from any rule type."""
        if not self.data:
            return None

        # Helper function to find rule in a rule set
        def find_rule(rules):
            if isinstance(rules, dict) and 'data' in rules:
                rules = rules['data']
            return next(
                (rule for rule in rules if rule.get('_id') == rule_id),
                None
            )

        # Check each rule type
        for rule_type in ['firewall_policies', 'traffic_routes', 
                         'firewall_rules', 'traffic_rules', 'port_forward_rules']:
            if rule_type in self.data:
                if rule := find_rule(self.data[rule_type]):
                    return rule

        return None

    def get_rule_type(self, rule_id: str) -> Optional[str]:
        """Get the type of a rule by its ID."""
        if not self.data:
            return None

        # Helper function to check rule presence
        def find_rule_type(rules, type_name):
            if isinstance(rules, dict) and 'data' in rules:
                rules = rules['data']
            return type_name if any(r.get('_id') == rule_id for r in rules) else None

        # Check each rule type
        for rule_type in ['firewall_policies', 'traffic_routes', 
                         'firewall_rules', 'traffic_rules', 'port_forward_rules']:
            if rule_type in self.data:
                if found_type := find_rule_type(self.data[rule_type], rule_type):
                    return found_type

        return None

    @log_call
    async def async_refresh_rules(self, rule_type: Optional[str] = None) -> None:
        """Refresh specific rule type or all rules."""
        try:
            if rule_type == 'firewall_policies' and self.api.capabilities.zone_based_firewall:
                success, policies, error = await self.api.get_firewall_policies()
                if success:
                    if not self.data:
                        self.data = {}
                    self.data['firewall_policies'] = [p for p in policies if not p.get('predefined', False)]
                    self._check_rule_changes('firewall_policies', self.data['firewall_policies'])

            elif rule_type == 'traffic_routes' and self.api.capabilities.traffic_routes:
                success, routes, error = await self.api.get_traffic_routes()
                if success:
                    if not self.data:
                        self.data = {}
                    self.data['traffic_routes'] = routes
                    self._check_rule_changes('traffic_routes', routes)

            elif rule_type == 'port_forward_rules':
                success, rules, error = await self.api.get_port_forward_rules()
                if success:
                    if not self.data:
                        self.data = {}
                    self.data['port_forward_rules'] = rules
                    self._check_rule_changes('port_forward_rules', rules)

            elif not rule_type:
                # Refresh all rules
                await self.async_refresh()
            
            # Notify entity loader of updates
            if self.config_entry and DOMAIN in self.hass.data:
                entry_data = self.hass.data[DOMAIN].get(self.config_entry.entry_id, {})
                entity_loader = entry_data.get('entity_loader')
                if entity_loader:
                    await entity_loader.async_handle_coordinator_update(self.data)

        except Exception as e:
            LOGGER.error("Error refreshing rules: %s", str(e))
            raise UpdateFailed(f"Failed to refresh rules: {str(e)}")

    def track_rule_changes(self, rule_id: str) -> bool:
        """Start tracking changes for a specific rule."""
        if not self.data:
            return False

        if rule := self.get_rule(rule_id):
            rule_type = self.get_rule_type(rule_id)
            if rule_type:
                if not hasattr(self, '_tracked_rules'):
                    self._tracked_rules = {}
                if rule_type not in self._tracked_rules:
                    self._tracked_rules[rule_type] = set()
                self._tracked_rules[rule_type].add(rule_id)
                return True
        return False

    def stop_tracking_rule(self, rule_id: str) -> bool:
        """Stop tracking changes for a specific rule."""
        if not hasattr(self, '_tracked_rules'):
            return False

        for rule_type, rules in self._tracked_rules.items():
            if rule_id in rules:
                rules.remove(rule_id)
                if not rules:
                    del self._tracked_rules[rule_type]
                return True
        return False