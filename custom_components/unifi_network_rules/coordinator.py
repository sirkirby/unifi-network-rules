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
            
            # Always fetch port forward rules first
            try:
                port_fwd_success, port_fwd_rules, port_fwd_error = await self.api.get_port_forward_rules()
                if port_fwd_success:
                    data['port_forward_rules'] = port_fwd_rules
                else:
                    fetch_errors.append(f"Failed to fetch port forwarding rules: {port_fwd_error}")
            except Exception as e:
                fetch_errors.append(f"Error fetching port forwarding rules: {str(e)}")
            
            # Fetch traffic routes if supported
            if self.api.capabilities.traffic_routes:
                try:
                    routes_success, routes, routes_error = await self.api.get_traffic_routes()
                    if routes_success:
                        data['traffic_routes'] = routes
                    else:
                        fetch_errors.append(f"Failed to fetch traffic routes: {routes_error}")
                except Exception as e:
                    fetch_errors.append(f"Error fetching traffic routes: {str(e)}")
            
            # Handle firewall data based on capabilities
            if self.api.capabilities.zone_based_firewall:
                try:
                    policies_success, policies, policies_error = await self.api.get_firewall_policies()
                    if policies_success:
                        # Filter out predefined policies
                        data['firewall_policies'] = [
                            p for p in policies
                            if not p.get('predefined', False)
                        ]
                    else:
                        fetch_errors.append(f"Failed to fetch policies: {policies_error}")
                except Exception as e:
                    fetch_errors.append(f"Error fetching firewall policies: {str(e)}")
            elif self.api.capabilities.legacy_firewall:
                try:
                    # Legacy firewall rules
                    rules_success, rules, rules_error = await self.api.get_legacy_firewall_rules()
                    if rules_success:
                        data['firewall_rules'] = {'data': rules}
                    else:
                        fetch_errors.append(f"Failed to fetch legacy firewall rules: {rules_error}")
                    
                    # Legacy traffic rules
                    traffic_success, traffic, traffic_error = await self.api.get_legacy_traffic_rules()
                    if traffic_success:
                        data['traffic_rules'] = traffic
                    else:
                        fetch_errors.append(f"Failed to fetch legacy traffic rules: {traffic_error}")
                except Exception as e:
                    fetch_errors.append(f"Error fetching legacy rules: {str(e)}")
            
            # If we have no data at all and there were errors, raise them
            if not data and fetch_errors:
                raise UpdateFailed("\n".join(fetch_errors))
                
            # Log any errors but return what data we have
            if fetch_errors:
                LOGGER.warning("Some data fetching failed:\n%s", "\n".join(fetch_errors))
                
            # Log successful data fetch for debugging
            LOGGER.debug("Fetched data: %s", {k: len(v) if isinstance(v, list) else len(v.get('data', [])) for k, v in data.items()})
                
            return data
            
        except ConfigEntryAuthFailed:
            raise
        except Exception as e:
            LOGGER.exception("Unexpected error in coordinator update")
            raise UpdateFailed(f"Data update failed: {str(e)}")

    @callback
    def handle_websocket_message(self, msg: dict | list) -> None:
        """Handle websocket messages."""
        if not self.data:
            LOGGER.debug("No coordinator data available for websocket update")
            return

        try:
            # If we receive a list, process each message individually
            if isinstance(msg, list):
                for single_msg in msg:
                    if isinstance(single_msg, dict):
                        self._process_single_message(single_msg)
                    else:
                        LOGGER.warning("Invalid message in list: %s", type(single_msg))
                return

            # Handle single message
            if isinstance(msg, dict):
                self._process_single_message(msg)
            else:
                LOGGER.warning("Invalid websocket message format: %s", type(msg))

        except Exception as err:
            LOGGER.error("Error handling websocket message: %s - %s", msg, err)

    def _process_single_message(self, msg: dict) -> None:
        """Process a single websocket message."""
        try:
            meta = msg.get("meta", {})
            if not isinstance(meta, dict):
                LOGGER.warning("Invalid meta format in message: %s", type(meta))
                return

            msg_type = meta.get("message")
            if not msg_type:
                LOGGER.debug("No message type in websocket data")
                return

            data = msg.get("data", {})
            # Some messages might have list data, handle it appropriately
            if not isinstance(data, (dict, list)):
                LOGGER.debug("Unexpected data type in message: %s", type(data))
                return

            LOGGER.debug("Processing websocket message: %s with data: %s", msg_type, data)

            # Convert list data to dict if needed
            if isinstance(data, list) and len(data) > 0:
                data = data[0] if isinstance(data[0], dict) else {}

            # Process message based on type
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
            LOGGER.error("Error processing single message: %s - %s", msg, err)

    def _verify_entities(self) -> None:
        """Verify all entities still correspond to existing rules."""
        if not self.hass or not self.data:
            return
            
        try:
            # Get entity loader from config entry
            if self.config_entry and DOMAIN in self.hass.data:
                entry_data = self.hass.data[DOMAIN].get(self.config_entry.entry_id, {})
                entity_loader = entry_data.get('entity_loader')
                if entity_loader:
                    # Use entity loader's coordinator update handler to clean up entities
                    self.hass.async_create_task(
                        entity_loader.async_handle_coordinator_update(self.data),
                        name="verify_entities"
                    )
        except Exception as err:
            LOGGER.error("Error verifying entities: %s", err)

    def _normalize_rule_data(self, data: Any, rule_type: str) -> list:
        """Normalize rule data to a consistent format."""
        if not data:
            return []
            
        # Handle legacy rule format that uses {data: [...]}
        if isinstance(data, dict) and 'data' in data:
            data = data['data']
            
        # Ensure we always return a list
        if not isinstance(data, list):
            LOGGER.warning("Unexpected data format for %s: %s", rule_type, type(data))
            return []
            
        return data

    def _update_data_list(self, data_key: str, action: str, item_data: dict) -> None:
        """Update a list in coordinator data."""
        if not isinstance(item_data, dict) or '_id' not in item_data:
            LOGGER.warning("Invalid item data for %s update: %s", data_key, item_data)
            return

        if data_key not in self.data:
            self.data[data_key] = []
            
        existing_data = self.data[data_key]
        data_list = self._normalize_rule_data(existing_data, data_key)

        item_id = item_data.get("_id")
        
        try:
            # Ensure consistent data types for enabled state
            if 'enabled' in item_data:
                item_data['enabled'] = bool(item_data['enabled'])

            if action.endswith("_add"):
                if data_key == "firewall_policies" and item_data.get("predefined", False):
                    return
                if not any(item.get("_id") == item_id for item in data_list):
                    data_list.append(item_data)
                
            elif action.endswith("_update"):
                updated = False
                for i, existing in enumerate(data_list):
                    if existing.get("_id") == item_id:
                        # Create a new dict to avoid modifying existing data
                        updated_item = dict(existing)
                        updated_item.update(item_data)
                        data_list[i] = updated_item
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

            # Update the main data structure
            self.data[data_key] = data_list

            # Store previous state for change detection
            self._previous_data[data_key] = data_list.copy()
            
            # Trigger entity updates
            self.async_set_updated_data(self.data)
            
        except Exception as err:
            LOGGER.error(
                "Error updating data list for %s (%s): %s",
                data_key, action, str(err)
            )

    @callback
    async def _handle_websocket_update(self, rule_type: str, action: str, data: dict) -> bool:
        """Handle websocket-based update."""
        try:
            update_start = datetime.now()
            
            # Store current state for verification
            rule_id = data.get('_id')
            if rule_id:
                current_state = self.get_rule(rule_id)

            # Ensure the data exists in coordinator
            if rule_type not in self.data:
                self.data[rule_type] = []

            # Normalize input data
            if 'enabled' in data:
                data['enabled'] = bool(data['enabled'])

            # Try API update first
            success, error = await self.api.update_rule_state(rule_type, rule_id, data.get('enabled', False))
            
            if success:
                # Update coordinator data
                self._update_data_list(rule_type, action, data)
                self.async_set_updated_data(self.data)
            else:
                # Restore previous state if API update failed
                if current_state:
                    self._update_data_list(rule_type, 'update', current_state)
                    self.async_set_updated_data(self.data)
                LOGGER.error("Failed to update rule state: %s", error)
                return False

            update_duration = (datetime.now() - update_start).total_seconds()
            LOGGER.debug(
                "Websocket update for %s completed in %.3f seconds (action: %s)", 
                rule_type, update_duration, action
            )
            
            return True
            
        except Exception as err:
            LOGGER.error(
                "Failed to process websocket update for %s (%s): %s", 
                rule_type, action, str(err)
            )
            return False

    @callback
    def _handle_rule_message(self, rule_type: str, action: str, data: dict) -> None:
        """Generic handler for rule messages."""
        try:
            # Create a copy of the original data
            rule_data = dict(data)
            
            # Ensure the enabled state is properly set
            if 'enabled' in rule_data:
                rule_data['enabled'] = bool(rule_data['enabled'])
            
            if rule_type not in self.data:
                self.data[rule_type] = []
            
            # Create update task
            self.hass.async_create_task(
                self._handle_websocket_update(rule_type, action, rule_data),
                name=f"unifi_rules_{rule_type}_update"
            )

        except Exception as err:
            LOGGER.error("Error in %s message handler: %s", rule_type, err)

    @callback
    def _handle_firewall_rule_message(self, action: str, data: dict) -> None:
        """Handle firewall rule message."""
        if self.api.capabilities.legacy_firewall:
            self._handle_rule_message('firewall_rules', action, data)

    @callback
    def _handle_firewall_policy_message(self, action: str, data: dict) -> None:
        """Handle firewall policy message."""
        if self.api.capabilities.zone_based_firewall:
            self._handle_rule_message('firewall_policies', action, data)

    @callback
    def _handle_traffic_rule_message(self, action: str, data: dict) -> None:
        """Handle traffic rule message."""
        if self.api.capabilities.legacy_firewall:
            self._handle_rule_message('traffic_rules', action, data)

    @callback
    def _handle_traffic_route_message(self, action: str, data: dict) -> None:
        """Handle traffic route message."""
        self._handle_rule_message('traffic_routes', action, data)

    @callback
    def _handle_port_forward_message(self, action: str, data: dict) -> None:
        """Handle port forward message."""
        self._handle_rule_message('port_forward_rules', action, data)

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
            # Normalize the rules data first
            rules = self._normalize_rule_data(rules, '')
            return next((rule for rule in rules if rule.get('_id') == rule_id), None)

        # Check each rule type in order
        rule_types = ['firewall_policies', 'traffic_routes', 'port_forward_rules', 
                     'firewall_rules', 'traffic_rules']
                     
        for rule_type in rule_types:
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
                LOGGER.debug("Started tracking rule %s of type %s", rule_id, rule_type)
                return True
        return False

    def stop_tracking_rule(self, rule_id: str) -> bool:
        """Stop tracking changes for a specific rule."""
        if not hasattr(self, '_tracked_rules'):
            return False

        for rule_type, rules in list(self._tracked_rules.items()):
            if rule_id in rules:
                rules.remove(rule_id)
                if not rules:
                    del self._tracked_rules[rule_type]
                LOGGER.debug("Stopped tracking rule %s of type %s", rule_id, rule_type)
                
                # Check if rule still exists and notify if it doesn't
                if not self.get_rule(rule_id):
                    LOGGER.info("Rule %s no longer exists in coordinator data", rule_id)
                    # Fire event for rule deletion if Home Assistant is available
                    if self.hass:
                        self.hass.bus.async_fire(
                            EVENT_RULE_DELETED,
                            {
                                "rule_id": rule_id,
                                "rule_type": rule_type
                            }
                        )
                return True
        return False