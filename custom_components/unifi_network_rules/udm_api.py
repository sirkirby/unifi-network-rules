"""UDM API for controlling UniFi Dream Machine."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import asyncio
import ssl
from aiohttp import CookieJar, WSMsgType
import aiohttp

from aiounifi import Controller
from aiounifi.models.configuration import Configuration
from aiounifi.models.traffic_route import TrafficRoute, TrafficRouteSaveRequest
from aiounifi.models.firewall_policy import FirewallPolicy, FirewallPolicyUpdateRequest
from aiounifi.models.traffic_rule import TrafficRule, TrafficRuleEnableRequest
from aiounifi.models.port_forward import PortForward, PortForwardEnableRequest
from aiounifi.errors import (
    AiounifiException,
    BadGateway,
    LoginRequired,
    RequestError,
    ResponseError,
    ServiceUnavailable,
    Unauthorized,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.const import CONF_VERIFY_SSL
from homeassistant.exceptions import HomeAssistantError

from .const import LOGGER
from .utils import get_rule_id

class UnifiNetworkRulesError(HomeAssistantError):
    """Base error for UniFi Network Rules."""

class CannotConnect(UnifiNetworkRulesError):
    """Error to indicate we cannot connect."""

class InvalidAuth(UnifiNetworkRulesError):
    """Error to indicate there is invalid auth."""

class UDMAPI:
    """Class to interact with UniFi Dream Machine API."""
    def __init__(self, host: str, username: str, password: str, verify_ssl: bool = False):
        """Initialize the UDMAPI."""
        self.host = host
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self._session = None
        self.controller = None  # Store Controller instance directly
        self._initialized = False
        self._hass_session = False  # Track if we're using HA's session
        self._ws_callback = None
        self._last_login_attempt = 0
        self._login_attempt_count = 0
        self._max_login_attempts = 3
        self._login_cooldown = 60  # seconds between login attempt resets

    async def async_init(self, hass: HomeAssistant | None = None) -> None:
        """Async initialization of the API."""
        if not self._session:
            try:
                ssl_context: ssl.SSLContext | bool = False
                if self.verify_ssl:
                    if isinstance(self.verify_ssl, str):
                        ssl_context = ssl.create_default_context(cafile=self.verify_ssl)
                    else:
                        ssl_context = True

                if hass:
                    if ssl_context:
                        self._session = aiohttp_client.async_get_clientsession(hass)
                    else:
                        self._session = aiohttp_client.async_create_clientsession(
                            hass, verify_ssl=False, cookie_jar=CookieJar(unsafe=True)
                        )
                    self._hass_session = True
                else:
                    self._session = aiohttp.ClientSession()

                config = Configuration(
                    session=self._session,
                    host=self.host,
                    username=self.username,
                    password=self.password,
                    port=443,
                    site="default",
                    ssl_context=ssl_context,
                )
                self.controller = Controller(config)

                async with asyncio.timeout(10):
                    await self.controller.login()
                    
                    # Initialize data only after interfaces are ready
                    if hasattr(self.controller, "sites"):
                        await self.controller.sites.update()
                    
                    # Update all data in parallel
                    update_tasks = [
                        self.get_firewall_policies(),
                        self.get_firewall_zones(),
                        self.get_port_forwards(),
                        self.get_traffic_rules(),
                        self.get_traffic_routes(),
                        self.get_wlans()
                    ]
                    
                    results = await asyncio.gather(*update_tasks, return_exceptions=True)
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            LOGGER.warning("Error updating %s: %s", update_tasks[i].__name__, result)
                    
                    self._initialized = True
                    LOGGER.debug(
                        "API Initialization complete. Available interfaces: %s",
                        [attr for attr in dir(self.controller) if not attr.startswith('_')]
                    )

            except (BadGateway, ResponseError, RequestError, ServiceUnavailable) as err:
                if self._session and not self._hass_session:
                    await self._session.close()
                self._session = None
                self.controller = None
                raise CannotConnect(f"Failed to connect: {err}") from err
            except LoginRequired as err:
                if self._session and not self._hass_session:
                    await self._session.close()
                self._session = None
                self.controller = None
                raise InvalidAuth("Invalid credentials") from err
            except Exception as err:
                if self._session and not self._hass_session:
                    await self._session.close()
                self._session = None
                self.controller = None
                LOGGER.error("Initialization error: %s. API attributes: %s", 
                           err, 
                           dir(self.controller) if self.controller else "No API instance")
                raise UnifiNetworkRulesError(f"Unexpected error: {err}") from err

    @property
    def initialized(self) -> bool:
        """Return True if API is initialized."""
        return self._initialized

    async def cleanup(self) -> None:
        """Cleanup resources."""
        try:
            if self._session and not self._hass_session:
                await self._session.close()
        except Exception as err:
            LOGGER.error("Error during cleanup: %s", str(err))
        finally:
            self._session = None
            self.controller = None

    async def start_websocket(self) -> None:
        """Start websocket connection."""
        if not self.controller:
            raise RuntimeError("API not initialized")
        
        await self.controller.start_websocket()

    async def stop_websocket(self) -> None:
        """Stop websocket connection."""
        if self.controller:
            await self.controller.stop_websocket()

    def set_websocket_callback(self, callback):
        """Set the websocket callback."""
        if self.controller:
            self.controller.ws_handler = callback

    async def _try_login(self) -> bool:
        """Attempt to login with rate limiting."""
        current_time = asyncio.get_event_loop().time()
        
        # Reset login attempts if cooldown period has passed
        if current_time - self._last_login_attempt > self._login_cooldown:
            self._login_attempt_count = 0
            
        # Check if we've exceeded login attempts
        if self._login_attempt_count >= self._max_login_attempts:
            wait_time = self._login_cooldown - (current_time - self._last_login_attempt)
            if wait_time > 0:
                LOGGER.warning("Login attempt limit reached. Waiting %d seconds before retry", wait_time)
                return False
            self._login_attempt_count = 0
            
        try:
            await self.controller.login()
            self._login_attempt_count = 0
            return True
        except Exception as err:
            self._last_login_attempt = current_time
            self._login_attempt_count += 1
            LOGGER.error("Login attempt failed (%d/%d): %s", 
                        self._login_attempt_count, self._max_login_attempts, str(err))
            return False

    # Firewall Policy Methods
    async def get_firewall_policies(self) -> List[Any]:
        """Get all firewall policies."""
        LOGGER.debug("Fetching firewall policies")
        try:
            await self.controller.firewall_policies.update()
            return list(self.controller.firewall_policies.values())
        except Exception as err:
            LOGGER.error("Failed to get firewall policies: %s", str(err))
            return []

    async def add_firewall_policy(self, policy_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new firewall policy."""
        LOGGER.debug("Adding firewall policy: %s", policy_data)
        try:
            policy = await self.controller.firewall_policies.add_item(policy_data)
            return policy
        except Exception as err:
            LOGGER.error("Failed to add firewall policy: %s", str(err))
            return None

    async def update_firewall_policy(self, policy_id: str, policy_data: Dict[str, Any]) -> bool:
        """Update an existing firewall policy."""
        LOGGER.debug("Updating firewall policy %s: %s", policy_id, policy_data)
        try:
            # Get the current policy
            current_policies = await self.get_firewall_policies()
            policy = next((p for p in current_policies if get_rule_id(p) == policy_id), None)
            if not policy:
                LOGGER.error("Firewall policy %s not found", policy_id)
                return False
            
            # Update the policy's enabled state using the proper request
            policy_dict = policy.raw.copy()
            policy_dict["enabled"] = policy_data.get("enabled", False)
            request = FirewallPolicyUpdateRequest.create(policy_dict)
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to update firewall policy: %s", str(err))
            return False

    async def remove_firewall_policy(self, policy_id: str) -> bool:
        """Remove a firewall policy."""
        LOGGER.debug("Removing firewall policy: %s", policy_id)
        try:
            await self.controller.firewall_policies.remove_item(policy_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove firewall policy: %s", str(err))
            return False

    # Traffic Rules Methods
    async def get_traffic_rules(self) -> List[Any]:
        """Get all traffic rules."""
        LOGGER.debug("Fetching traffic rules")
        try:
            await self.controller.traffic_rules.update()
            return list(self.controller.traffic_rules.values())
        except Exception as err:
            LOGGER.error("Failed to get traffic rules: %s", str(err))
            return []

    async def add_traffic_rule(self, rule_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new traffic rule."""
        LOGGER.debug("Adding traffic rule: %s", rule_data)
        try:
            rule = await self.controller.traffic_rules.add_item(rule_data)
            return rule
        except Exception as err:
            LOGGER.error("Failed to add traffic rule: %s", str(err))
            return None

    async def update_traffic_rule(self, rule_id: str, rule_data: Dict[str, Any]) -> bool:
        """Update an existing traffic rule."""
        LOGGER.debug("Updating traffic rule %s: %s", rule_id, rule_data)
        try:
            # Get the current rule
            current_rules = await self.get_traffic_rules()
            rule = next((r for r in current_rules if get_rule_id(r) == rule_id), None)
            if not rule:
                LOGGER.error("Traffic rule %s not found", rule_id)
                return False
            
            # Update the rule's enabled state using the proper request
            request = TrafficRuleEnableRequest.create(rule.raw, enable=rule_data.get("enabled", False))
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to update traffic rule: %s", str(err))
            return False

    async def remove_traffic_rule(self, rule_id: str) -> bool:
        """Remove a traffic rule."""
        LOGGER.debug("Removing traffic rule: %s", rule_id)
        try:
            await self.controller.traffic_rules.remove_item(rule_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove traffic rule: %s", str(err))
            return False

    # Port Forward Methods
    async def get_port_forwards(self) -> List[Any]:
        """Get all port forwards."""
        LOGGER.debug("Fetching port forwards")
        try:
            await self.controller.port_forwarding.update()
            return list(self.controller.port_forwarding.values())
        except Exception as err:
            LOGGER.error("Failed to get port forwards: %s", str(err))
            return []

    async def add_port_forward(self, forward_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new port forward."""
        LOGGER.debug("Adding port forward: %s", forward_data)
        try:
            forward = await self.controller.port_forwarding.add_item(forward_data)
            return forward
        except Exception as err:
            LOGGER.error("Failed to add port forward: %s", str(err))
            return None

    async def update_port_forward(self, forward_id: str, forward_data: Dict[str, Any]) -> bool:
        """Update an existing port forward."""
        LOGGER.debug("Updating port forward %s: %s", forward_id, forward_data)
        try:
            # Get the current forward
            current_forwards = await self.get_port_forwards()
            forward = next((f for f in current_forwards if get_rule_id(f) == forward_id), None)
            if not forward:
                LOGGER.error("Port forward %s not found", forward_id)
                return False
            
            # Update the forward's enabled state using the proper request
            request = PortForwardEnableRequest.create(forward, enable=forward_data.get("enabled", False))
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to update port forward: %s", str(err))
            return False

    async def remove_port_forward(self, forward_id: str) -> bool:
        """Remove a port forward."""
        LOGGER.debug("Removing port forward: %s", forward_id)
        try:
            await self.controller.port_forwarding.remove_item(forward_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove port forward: %s", str(err))
            return False

    # Traffic Routes Methods
    async def get_traffic_routes(self) -> List[Any]:
        """Get all traffic routes."""
        LOGGER.debug("Fetching traffic routes")
        try:
            await self.controller.traffic_routes.update()
            return list(self.controller.traffic_routes.values())
        except Exception as err:
            LOGGER.error("Failed to get traffic routes: %s", str(err))
            return []

    async def add_traffic_route(self, route_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new traffic route."""
        LOGGER.debug("Adding traffic route: %s", route_data)
        try:
            route = await self.controller.traffic_routes.add_item(route_data)
            return route
        except Exception as err:
            LOGGER.error("Failed to add traffic route: %s", str(err))
            return None

    async def update_traffic_route(self, route_id: str, route_data: Dict[str, Any]) -> bool:
        """Update an existing traffic route."""
        LOGGER.debug("Updating traffic route %s: %s", route_id, route_data)
        try:
            # Get the current route
            current_routes = await self.get_traffic_routes()
            route = next((r for r in current_routes if get_rule_id(r) == route_id), None)
            if not route:
                LOGGER.error("Traffic route %s not found", route_id)
                return False
            
            # Update the route's enabled state using the proper request
            request = TrafficRouteSaveRequest.create(route.raw, enable=route_data.get("enabled"))
            await self.controller.request(request)
            return True
        except Exception as err:
            LOGGER.error("Failed to update traffic route: %s", str(err))
            return False

    async def remove_traffic_route(self, route_id: str) -> bool:
        """Remove a traffic route."""
        LOGGER.debug("Removing traffic route: %s", route_id)
        try:
            await self.controller.traffic_routes.remove_item(route_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove traffic route: %s", str(err))
            return False

    # Firewall Zone Methods
    async def get_firewall_zones(self) -> List[Dict[str, Any]]:
        """Get all firewall zones."""
        LOGGER.debug("Fetching firewall zones")
        try:
            await self.controller.firewall_zones.update()
            return list(self.controller.firewall_zones.values())
        except Exception as err:
            LOGGER.error("Failed to get firewall zones: %s", str(err))
            return []

    async def add_firewall_zone(self, zone_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new firewall zone."""
        LOGGER.debug("Adding firewall zone: %s", zone_data)
        try:
            zone = await self.controller.firewall_zones.add_item(zone_data)
            return zone
        except Exception as err:
            LOGGER.error("Failed to add firewall zone: %s", str(err))
            return None

    async def update_firewall_zone(self, zone_id: str, zone_data: Dict[str, Any]) -> bool:
        """Update an existing firewall zone."""
        LOGGER.debug("Updating firewall zone %s: %s", zone_id, zone_data)
        try:
            await self.controller.firewall_zones.update_item(zone_id, zone_data)
            return True
        except Exception as err:
            LOGGER.error("Failed to update firewall zone: %s", str(err))
            return False

    # WLAN Management Methods
    async def get_wlans(self) -> List[Dict[str, Any]]:
        """Get all WLANs."""
        LOGGER.debug("Fetching WLANs")
        try:
            await self.controller.wlans.update()
            return list(self.controller.wlans.values())
        except Exception as err:
            LOGGER.error("Failed to get WLANs: %s", str(err))
            return []

    async def update_wlan(self, wlan_id: str, wlan_data: Dict[str, Any]) -> bool:
        """Update WLAN settings."""
        LOGGER.debug("Updating WLAN %s: %s", wlan_id, wlan_data)
        try:
            await self.controller.wlans.update_item(wlan_id, wlan_data)
            return True
        except Exception as err:
            LOGGER.error("Failed to update WLAN: %s", str(err))
            return False

    async def toggle_wlan(self, wlan_id: str, enabled: bool) -> bool:
        """Enable or disable a WLAN."""
        LOGGER.debug("Setting WLAN %s enabled state to: %s", wlan_id, enabled)
        try:
            wlan = self.controller.wlans[wlan_id]
            if not wlan:
                raise KeyError(f"WLAN {wlan_id} not found")
            
            wlan_data = dict(wlan)
            wlan_data['enabled'] = enabled
            return await self.update_wlan(wlan_id, wlan_data)
        except Exception as err:
            LOGGER.error("Failed to toggle WLAN: %s", str(err))
            return False

    # System Status Methods
    async def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics and status."""
        LOGGER.debug("Fetching system statistics")
        try:
            stats = {}
            # Get system info
            await self.controller.system_info.update()
            if self.controller.system_info.data:
                stats.update(self.controller.system_info.data)
            
            # Get dashboard stats
            dashboard_stats = await self.controller.stat_dashboard.async_get()
            if (dashboard_stats):
                stats.update(dashboard_stats)
            
            return stats
        except Exception as err:
            LOGGER.error("Failed to get system stats: %s", str(err))
            return {}

    async def get_bandwidth_usage(self, timespan: int = 3600) -> Dict[str, Any]:
        """Get bandwidth usage statistics for the specified timespan in seconds."""
        LOGGER.debug("Fetching bandwidth usage for last %d seconds", timespan)
        try:
            # Get realtime stats from dashboard
            stats = await self.controller.stat_dashboard.async_get()
            
            # Add historical stats if available
            try:
                history = await self.controller.stat_dashboard.async_historical_data(timespan)
                if history:
                    stats.update({
                        "historical": history
                    })
            except Exception as history_err:
                LOGGER.warning("Failed to get historical bandwidth data: %s", str(history_err))
            
            return stats
        except Exception as err:
            LOGGER.error("Failed to get bandwidth usage: %s", str(err))
            return {}

    # Bulk Operations and Updates
    async def refresh_all(self) -> None:
        """Refresh all data from the UniFi controller."""
        LOGGER.debug("Refreshing all data from UniFi controller")
        try:
            update_tasks = [
                self.controller.firewall_policies.update(),
                self.controller.traffic_rules.update(),
                self.controller.port_forwarding.update(),
                self.controller.traffic_routes.update(),
                self.controller.clients.update(),
                self.controller.devices.update(),
                self.controller.wlans.update()
            ]
            
            results = await asyncio.gather(*update_tasks, return_exceptions=True)
            for task_result in results:
                if isinstance(task_result, Exception):
                    LOGGER.warning("Error during refresh: %s", str(task_result))
                    
        except Exception as err:
            LOGGER.error("Failed to refresh all data: %s", str(err))

    async def bulk_update_firewall_policies(self, policies: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
        """Bulk update firewall policies. Returns (success_count, failed_ids)."""
        LOGGER.debug("Performing bulk update of %d firewall policies", len(policies))
        success_count = 0
        failed_ids = []
        
        for policy in policies:
            policy_id = policy.get('_id')
            if not policy_id:
                LOGGER.error("Policy missing _id field: %s", policy)
                continue
                
            success, error = await self._handle_api_request(
                "Update firewall policy",
                self.controller.firewall_policies.async_update(policy_id, policy)
            )
            
            if success:
                success_count += 1
            else:
                LOGGER.error("Failed to update policy %s: %s", policy_id, error)
                failed_ids.append(policy_id)
        
        return success_count, failed_ids

    async def get_rule_status(self, rule_id: str) -> Dict[str, Any]:
        """Get detailed status for a specific rule including dependencies."""
        LOGGER.debug("Getting detailed status for rule: %s", rule_id)
        try:
            status = {
                "active": False,
                "dependencies": [],
                "conflicts": [],
                "last_modified": None,
                "type": None
            }
            
            # Check across different rule types
            rules_map = {
                "firewall_policy": self.controller.firewall_policies,
                "traffic_rule": self.controller.traffic_rules,
                "port_forward": self.controller.port_forwarding,
                "traffic_route": self.controller.traffic_routes
            }
            
            for rule_type, rules in rules_map.items():
                if rule_id in rules:
                    rule = rules[rule_id]
                    status.update({
                        "active": rule.get("enabled", False),
                        "last_modified": rule.get("last_modified"),
                        "type": rule_type
                    })
                    # Add any dependent or conflicting rules
                    status["dependencies"].extend(self._find_dependencies(rule))
                    status["conflicts"].extend(self._find_conflicts(rule))
                    break
            
            return status
        except Exception as err:
            LOGGER.error("Failed to get rule status: %s", str(err))
            return {}

    def _find_dependencies(self, rule: Dict[str, Any]) -> List[str]:
        """Find rules that this rule depends on."""
        dependencies = []
        # Implementation specific to your rule structure
        return dependencies

    def _find_conflicts(self, rule: Dict[str, Any]) -> List[str]:
        """Find rules that might conflict with this rule."""
        conflicts = []
        # Implementation specific to your rule structure
        return conflicts

    # Client and Device Management Methods
    async def get_clients(self, include_offline: bool = False) -> List[Dict[str, Any]]:
        """Get all client devices."""
        LOGGER.debug("Fetching clients (include_offline=%s)", include_offline)
        try:
            success, error = await self._handle_api_request(
                "Get clients",
                self.controller.clients.update()
            )
            if not success:
                LOGGER.error("Failed to get clients: %s", error)
                return []
                
            clients = list(self.controller.clients.values())
            if not include_offline:
                clients = [c for c in clients if c.get('is_online', False)]
            return clients
        except Exception as err:
            LOGGER.error("Failed to get clients: %s", str(err))
            return []

    async def block_client(self, client_mac: str) -> bool:
        """Block a client device."""
        LOGGER.debug("Blocking client: %s", client_mac)
        try:
            success, error = await self._handle_api_request(
                "Block client",
                self.controller.clients.async_block(client_mac)
            )
            if not success:
                LOGGER.error("Failed to block client: %s", error)
            return success
        except Exception as err:
            LOGGER.error("Failed to block client: %s", str(err))
            return False

    async def unblock_client(self, client_mac: str) -> bool:
        """Unblock a client device."""
        LOGGER.debug("Unblocking client: %s", client_mac)
        try:
            success, error = await self._handle_api_request(
                "Unblock client",
                self.controller.clients.async_unblock(client_mac)
            )
            if not success:
                LOGGER.error("Failed to unblock client: %s", error)
            return success
        except Exception as err:
            LOGGER.error("Failed to unblock client: %s", str(err))
            return False

    async def reconnect_client(self, client_mac: str) -> bool:
        """Force a client to reconnect."""
        LOGGER.debug("Forcing reconnect for client: %s", client_mac)
        try:
            success, error = await self._handle_api_request(
                "Reconnect client",
                self.controller.clients.async_force_reconnect(client_mac)
            )
            if not success:
                LOGGER.error("Failed to reconnect client: %s", error)
            return success
        except Exception as err:
            LOGGER.error("Failed to reconnect client: %s", str(err))
            return False

    async def get_device_stats(self, mac: str) -> Dict[str, Any]:
        """Get statistics for a specific device."""
        LOGGER.debug("Fetching device stats for: %s", mac)
        try:
            success, error = await self._handle_api_request(
                "Get device stats",
                self.controller.devices.update()
            )
            if not success:
                LOGGER.error("Failed to get device stats: %s", error)
                return {}

            stats = {
                "rx_bytes": 0,
                "tx_bytes": 0,
                "uptime": 0,
                "last_seen": None,
                "status": "unknown"
            }
            
            # Check both devices and clients since the MAC could be either
            if mac in self.controller.devices:
                device = self.controller.devices[mac]
                stats.update({
                    "rx_bytes": device.get("rx_bytes", 0),
                    "tx_bytes": device.get("tx_bytes", 0),
                    "uptime": device.get("uptime", 0),
                    "last_seen": device.get("last_seen"),
                    "status": device.get("state", "unknown"),
                    "type": "device"
                })
            elif mac in self.controller.clients:
                client = self.controller.clients[mac]
                stats.update({
                    "rx_bytes": client.get("rx_bytes", 0),
                    "tx_bytes": client.get("tx_bytes", 0),
                    "uptime": client.get("uptime", 0),
                    "last_seen": client.get("last_seen"),
                    "status": "online" if client.get("is_online", False) else "offline",
                    "type": "client",
                    "blocked": client.get("blocked", False)
                })
            
            return stats
        except Exception as err:
            LOGGER.error("Failed to get device stats: %s", str(err))
            return {}

    # Network Security Methods
    async def get_threats(self) -> List[Dict[str, Any]]:
        """Get detected security threats."""
        LOGGER.debug("Fetching security threats")
        try:
            # Get security-related events
            security_types = ["IPS", "IDS", "Threat", "SecurityEvent"]
            events = await self.get_events()
            return [
                event for event in events
                if event.get("type") in security_types
                or event.get("subsystem") == "security"
            ]
        except Exception as err:
            LOGGER.error("Failed to get threats: %s", str(err))
            return []

    async def get_device_stats(self, mac: str) -> Dict[str, Any]:
        """Get statistics for a specific device."""
        LOGGER.debug("Fetching device stats for: %s", mac)
        try:
            stats = {
                "rx_bytes": 0,
                "tx_bytes": 0,
                "uptime": 0,
                "last_seen": None,
                "blocked": False
            }
            
            if mac in self.controller.clients:
                client = self.controller.clients[mac]
                stats.update({
                    "rx_bytes": client.get("rx_bytes", 0),
                    "tx_bytes": client.get("tx_bytes", 0),
                    "uptime": client.get("uptime", 0),
                    "last_seen": client.get("last_seen"),
                    "blocked": client.get("blocked", False)
                })
            
            return stats
        except Exception as err:
            LOGGER.error("Failed to get device stats: %s", str(err))
            return {}

    # Network Management Methods
    async def reconnect_client(self, client_mac: str) -> bool:
        """Force a client to reconnect."""
        LOGGER.debug("Forcing reconnect for client: %s", client_mac)
        try:
            await self.controller.clients.async_force_reconnect(client_mac)
            return True
        except Exception as err:
            LOGGER.error("Failed to reconnect client: %s", str(err))
            return False

    async def get_bandwidth_usage(self, timespan: int = 3600) -> Dict[str, Any]:
        """Get bandwidth usage statistics for the specified timespan in seconds."""
        LOGGER.debug("Fetching bandwidth usage for last %d seconds", timespan)
        try:
            # Get realtime stats from dashboard
            stats = await self.controller.stat_dashboard.async_get()
            
            # Add historical stats if available
            try:
                history = await self.controller.stat_dashboard.async_historical_data(timespan)
                if history:
                    stats.update({
                        "historical": history
                    })
            except Exception as history_err:
                LOGGER.warning("Failed to get historical bandwidth data: %s", str(history_err))
            
            return stats
        except Exception as err:
            LOGGER.error("Failed to get bandwidth usage: %s", str(err))
            return {}

    # Events and Security Methods
    async def get_events(self, event_type: str | None = None) -> List[Dict[str, Any]]:
        """Get events, optionally filtered by type."""
        LOGGER.debug("Fetching events (type=%s)", event_type)
        try:
            await self.controller.events.update()
            events = list(self.controller.events.values())
            if event_type:
                events = [e for e in events if e.get("type") == event_type]
            return events
        except Exception as err:
            LOGGER.error("Failed to get events: %s", str(err))
            return []

    # Error handling helper
    async def _handle_api_request(self, request_type: str, action: str) -> Tuple[bool, Optional[str]]:
        """Handle an API request with proper error handling."""
        try:
            await action
            return True, None
        except LoginRequired:
            LOGGER.warning("%s failed: Session expired, attempting to reconnect", request_type)
            try:
                await self._try_login()
                await action
                return True, None
            except Exception as login_err:
                return False, f"Failed to reconnect: {login_err}"
        except (BadGateway, ServiceUnavailable) as err:
            return False, f"Service unavailable: {err}"
        except RequestError as err:
            return False, f"Request failed: {err}"
        except ResponseError as err:
            return False, f"Invalid response: {err}"
        except AiounifiException as err:
            return False, f"API error: {err}"
        except Exception as err:
            return False, f"Unexpected error: {err}"