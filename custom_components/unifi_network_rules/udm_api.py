"""UDM API for controlling UniFi Dream Machine."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import asyncio
import ssl
from aiohttp import CookieJar, WSMsgType
import aiohttp

from aiounifi import Controller
from aiounifi.models.configuration import Configuration
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
        self.api = None
        self._initialized = False
        self._hass_session = False  # Track if we're using HA's session
        self._ws = None
        self._ws_task = None
        self._ws_callback = None
        self._running = False
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
                self.api = Controller(config)

                async with asyncio.timeout(10):
                    await self.api.login()
                    # Load initial data
                    await self.api.clients.update()
                    await self.api.devices.update()
                    self._initialized = True

            except (BadGateway, ResponseError, RequestError, ServiceUnavailable) as err:
                if self._session and not self._hass_session:
                    await self._session.close()
                self._session = None
                self.api = None
                raise CannotConnect(f"Failed to connect: {err}") from err
            except LoginRequired as err:
                if self._session and not self._hass_session:
                    await self._session.close()
                self._session = None
                self.api = None
                raise InvalidAuth("Invalid credentials") from err
            except Exception as err:
                if self._session and not self._hass_session:
                    await self._session.close()
                self._session = None
                self.api = None
                raise UnifiNetworkRulesError(f"Unexpected error: {err}") from err

    @property
    def initialized(self) -> bool:
        """Return True if API is initialized."""
        return self._initialized

    async def authenticate_session(self) -> Tuple[bool, Optional[str]]:
        """Authenticate session."""
        try:
            if not self.api:
                await self.async_init()
            await self.api.login()
            self._initialized = True
            return True, None
        except LoginRequired as err:
            return False, "Invalid credentials"
        except ResponseError as err:
            return False, f"Response error: {err}"
        except RequestError as err:
            return False, f"Request error: {err}"
        except Exception as err:
            return False, str(err)

    async def cleanup(self) -> None:
        """Cleanup resources."""
        try:
            if self._session and not self._hass_session:
                await self._session.close()
        except Exception as err:
            LOGGER.error("Error during cleanup: %s", str(err))
        finally:
            self._session = None
            self.api = None

    async def start_websocket(self) -> None:
        """Start websocket connection."""
        if not self.api:
            raise RuntimeError("API not initialized")

        if not self._ws_task:
            self._running = True
            self._ws_task = asyncio.create_task(self._websocket_loop())

    async def stop_websocket(self) -> None:
        """Stop websocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None

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
            await self.api.login()
            self._login_attempt_count = 0
            return True
        except Exception as err:
            self._last_login_attempt = current_time
            self._login_attempt_count += 1
            LOGGER.error("Login attempt failed (%d/%d): %s", 
                        self._login_attempt_count, self._max_login_attempts, str(err))
            return False

    async def _websocket_loop(self) -> None:
        """Websocket connection loop."""
        LOGGER.debug("Starting websocket loop")
        url = f"wss://{self.host}:443/wss/s/default/events"
        retry_delay = 5
        max_retry_delay = 300  # 5 minutes
        
        while self._running:
            try:
                if not self._session or not self.api:
                    await self.async_init()
                
                # Ensure we're authenticated before connecting
                if not await self._try_login():
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    continue

                cookies = self._session.cookie_jar.filter_cookies(f"https://{self.host}")
                headers = {
                    "Origin": f"https://{self.host}",
                    "Cookie": "; ".join([f"{k}={v.value}" for k, v in cookies.items()])
                }

                async with self._session.ws_connect(
                    url,
                    ssl=False if not self.verify_ssl else None,
                    heartbeat=30,
                    headers=headers
                ) as ws:
                    self._ws = ws
                    LOGGER.debug("Websocket connected")
                    retry_delay = 5  # Reset retry delay on successful connection

                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            if self._ws_callback:
                                await self._ws_callback(msg.json())
                        elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                            break

            except Exception as err:
                LOGGER.error("Websocket error: %s", str(err))
                if self._ws:
                    await self._ws.close()
                self._ws = None
                
                if self._running:
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                    continue
                break

        self._ws = None
        LOGGER.debug("Websocket loop ended")

    def set_websocket_callback(self, callback):
        """Set the websocket callback."""
        self._ws_callback = callback

    # Firewall Policy Methods
    async def get_firewall_policies(self) -> List[Dict[str, Any]]:
        """Get all firewall policies."""
        LOGGER.debug("Fetching firewall policies")
        try:
            await self.api.firewall_policies.update()
            return list(self.api.firewall_policies.values())
        except Exception as err:
            LOGGER.error("Failed to get firewall policies: %s", str(err))
            return []

    async def add_firewall_policy(self, policy_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new firewall policy."""
        LOGGER.debug("Adding firewall policy: %s", policy_data)
        try:
            policy = await self.api.firewall_policies.async_add(policy_data)
            return policy
        except Exception as err:
            LOGGER.error("Failed to add firewall policy: %s", str(err))
            return None

    async def update_firewall_policy(self, policy_id: str, policy_data: Dict[str, Any]) -> bool:
        """Update an existing firewall policy."""
        LOGGER.debug("Updating firewall policy %s: %s", policy_id, policy_data)
        try:
            await self.api.firewall_policies.async_update(policy_id, policy_data)
            return True
        except Exception as err:
            LOGGER.error("Failed to update firewall policy: %s", str(err))
            return False

    async def remove_firewall_policy(self, policy_id: str) -> bool:
        """Remove a firewall policy."""
        LOGGER.debug("Removing firewall policy: %s", policy_id)
        try:
            await self.api.firewall_policies.async_delete(policy_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove firewall policy: %s", str(err))
            return False

    # Traffic Rules Methods
    async def get_traffic_rules(self) -> List[Dict[str, Any]]:
        """Get all traffic rules."""
        LOGGER.debug("Fetching traffic rules")
        try:
            await self.api.traffic_rules.update()
            return list(self.api.traffic_rules.values())
        except Exception as err:
            LOGGER.error("Failed to get traffic rules: %s", str(err))
            return []

    async def add_traffic_rule(self, rule_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new traffic rule."""
        LOGGER.debug("Adding traffic rule: %s", rule_data)
        try:
            rule = await self.api.traffic_rules.async_add(rule_data)
            return rule
        except Exception as err:
            LOGGER.error("Failed to add traffic rule: %s", str(err))
            return None

    async def update_traffic_rule(self, rule_id: str, rule_data: Dict[str, Any]) -> bool:
        """Update an existing traffic rule."""
        LOGGER.debug("Updating traffic rule %s: %s", rule_id, rule_data)
        try:
            await self.api.traffic_rules.async_update(rule_id, rule_data)
            return True
        except Exception as err:
            LOGGER.error("Failed to update traffic rule: %s", str(err))
            return False

    async def remove_traffic_rule(self, rule_id: str) -> bool:
        """Remove a traffic rule."""
        LOGGER.debug("Removing traffic rule: %s", rule_id)
        try:
            await self.api.traffic_rules.async_delete(rule_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove traffic rule: %s", str(err))
            return False

    # Port Forward Methods
    async def get_port_forwards(self) -> List[Dict[str, Any]]:
        """Get all port forwards."""
        LOGGER.debug("Fetching port forwards")
        try:
            await self.api.port_forward.update()
            return list(self.api.port_forward.values())
        except Exception as err:
            LOGGER.error("Failed to get port forwards: %s", str(err))
            return []

    async def add_port_forward(self, forward_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new port forward."""
        LOGGER.debug("Adding port forward: %s", forward_data)
        try:
            forward = await self.api.port_forward.async_add(forward_data)
            return forward
        except Exception as err:
            LOGGER.error("Failed to add port forward: %s", str(err))
            return None

    async def update_port_forward(self, forward_id: str, forward_data: Dict[str, Any]) -> bool:
        """Update an existing port forward."""
        LOGGER.debug("Updating port forward %s: %s", forward_id, forward_data)
        try:
            await self.api.port_forward.async_update(forward_id, forward_data)
            return True
        except Exception as err:
            LOGGER.error("Failed to update port forward: %s", str(err))
            return False

    async def remove_port_forward(self, forward_id: str) -> bool:
        """Remove a port forward."""
        LOGGER.debug("Removing port forward: %s", forward_id)
        try:
            await self.api.port_forward.async_delete(forward_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove port forward: %s", str(err))
            return False

    # Traffic Routes Methods
    async def get_traffic_routes(self) -> List[Dict[str, Any]]:
        """Get all traffic routes."""
        LOGGER.debug("Fetching traffic routes")
        try:
            await self.api.traffic_routes.update()
            return list(self.api.traffic_routes.values())
        except Exception as err:
            LOGGER.error("Failed to get traffic routes: %s", str(err))
            return []

    async def add_traffic_route(self, route_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new traffic route."""
        LOGGER.debug("Adding traffic route: %s", route_data)
        try:
            route = await self.api.traffic_routes.async_add(route_data)
            return route
        except Exception as err:
            LOGGER.error("Failed to add traffic route: %s", str(err))
            return None

    async def update_traffic_route(self, route_id: str, route_data: Dict[str, Any]) -> bool:
        """Update an existing traffic route."""
        LOGGER.debug("Updating traffic route %s: %s", route_id, route_data)
        try:
            await self.api.traffic_routes.async_update(route_id, route_data)
            return True
        except Exception as err:
            LOGGER.error("Failed to update traffic route: %s", str(err))
            return False

    async def remove_traffic_route(self, route_id: str) -> bool:
        """Remove a traffic route."""
        LOGGER.debug("Removing traffic route: %s", route_id)
        try:
            await self.api.traffic_routes.async_delete(route_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove traffic route: %s", str(err))
            return False

    # Firewall Zone Methods
    async def get_firewall_zones(self) -> List[Dict[str, Any]]:
        """Get all firewall zones."""
        LOGGER.debug("Fetching firewall zones")
        try:
            await self.api.firewall_zones.update()
            return list(self.api.firewall_zones.values())
        except Exception as err:
            LOGGER.error("Failed to get firewall zones: %s", str(err))
            return []

    async def add_firewall_zone(self, zone_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new firewall zone."""
        LOGGER.debug("Adding firewall zone: %s", zone_data)
        try:
            zone = await self.api.firewall_zones.async_add(zone_data)
            return zone
        except Exception as err:
            LOGGER.error("Failed to add firewall zone: %s", str(err))
            return None

    async def update_firewall_zone(self, zone_id: str, zone_data: Dict[str, Any]) -> bool:
        """Update an existing firewall zone."""
        LOGGER.debug("Updating firewall zone %s: %s", zone_id, zone_data)
        try:
            await self.api.firewall_zones.async_update(zone_id, zone_data)
            return True
        except Exception as err:
            LOGGER.error("Failed to update firewall zone: %s", str(err))
            return False

    # DPI Restriction Methods
    async def get_dpi_groups(self) -> List[Dict[str, Any]]:
        """Get all DPI restriction groups."""
        LOGGER.debug("Fetching DPI restriction groups")
        try:
            await self.api.dpi_groups.update()
            return list(self.api.dpi_groups.values())
        except Exception as err:
            LOGGER.error("Failed to get DPI groups: %s", str(err))
            return []

    async def add_dpi_group(self, group_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new DPI restriction group."""
        LOGGER.debug("Adding DPI group: %s", group_data)
        try:
            group = await self.api.dpi_groups.async_add(group_data)
            return group
        except Exception as err:
            LOGGER.error("Failed to add DPI group: %s", str(err))
            return None

    async def update_dpi_group(self, group_id: str, group_data: Dict[str, Any]) -> bool:
        """Update an existing DPI restriction group."""
        LOGGER.debug("Updating DPI group %s: %s", group_id, group_data)
        try:
            await self.api.dpi_groups.async_update(group_id, group_data)
            return True
        except Exception as err:
            LOGGER.error("Failed to update DPI group: %s", str(err))
            return False

    # WLAN Management Methods
    async def get_wlans(self) -> List[Dict[str, Any]]:
        """Get all WLANs."""
        LOGGER.debug("Fetching WLANs")
        try:
            await self.api.wlans.update()
            return list(self.api.wlans.values())
        except Exception as err:
            LOGGER.error("Failed to get WLANs: %s", str(err))
            return []

    async def update_wlan(self, wlan_id: str, wlan_data: Dict[str, Any]) -> bool:
        """Update WLAN settings."""
        LOGGER.debug("Updating WLAN %s: %s", wlan_id, wlan_data)
        try:
            await self.api.wlans.async_update(wlan_id, wlan_data)
            return True
        except Exception as err:
            LOGGER.error("Failed to update WLAN: %s", str(err))
            return False

    async def toggle_wlan(self, wlan_id: str, enabled: bool) -> bool:
        """Enable or disable a WLAN."""
        LOGGER.debug("Setting WLAN %s enabled state to: %s", wlan_id, enabled)
        try:
            wlan = self.api.wlans[wlan_id]
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
            await self.api.system_info.update()
            return self.api.system_info.data
        except Exception as err:
            LOGGER.error("Failed to get system stats: %s", str(err))
            return {}

    # Bulk Operations
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
                
            success = await self.update_firewall_policy(policy_id, policy)
            if success:
                success_count += 1
            else:
                failed_ids.append(policy_id)
        
        return success_count, failed_ids

    async def refresh_all(self) -> None:
        """Refresh all data from the UniFi controller."""
        LOGGER.debug("Refreshing all data from UniFi controller")
        try:
            await asyncio.gather(
                self.api.firewall_policies.update(),
                self.api.traffic_rules.update(),
                self.api.port_forwarding.update(),
                self.api.traffic_routes.update()
            )
        except Exception as err:
            LOGGER.error("Failed to refresh all data: %s", str(err))

    async def get_rule_status(self, rule_id: str) -> Dict[str, Any]:
        """Get detailed status for a specific rule including dependencies."""
        LOGGER.debug("Getting detailed status for rule: %s", rule_id)
        try:
            status = {
                "active": False,
                "dependencies": [],
                "conflicts": [],
                "last_modified": None
            }
            
            # Check across different rule types
            for rules in [
                self.api.firewall_policies,
                self.api.traffic_rules,
                self.api.port_forward,
                self.api.traffic_routes
            ]:
                if rule_id in rules:
                    rule = rules[rule_id]
                    status["active"] = rule.get("enabled", False)
                    status["last_modified"] = rule.get("last_modified")
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

    # Client Management Methods
    async def get_clients(self, include_offline: bool = False) -> List[Dict[str, Any]]:
        """Get all client devices."""
        LOGGER.debug("Fetching clients (include_offline=%s)", include_offline)
        try:
            await self.api.clients.update()
            clients = list(self.api.clients.values())
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
            await self.api.clients.async_block(client_mac)
            return True
        except Exception as err:
            LOGGER.error("Failed to block client: %s", str(err))
            return False

    async def unblock_client(self, client_mac: str) -> bool:
        """Unblock a client device."""
        LOGGER.debug("Unblocking client: %s", client_mac)
        try:
            await self.api.clients.async_unblock(client_mac)
            return True
        except Exception as err:
            LOGGER.error("Failed to unblock client: %s", str(err))
            return False

    # Network Security Methods
    async def get_threats(self) -> List[Dict[str, Any]]:
        """Get detected security threats."""
        LOGGER.debug("Fetching security threats")
        try:
            await self.api.events.update()
            threats = [
                event for event in self.api.events.values()
                if event.get('type') in ['IPS', 'IDS', 'Threat']
            ]
            return threats
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
            
            if mac in self.api.clients:
                client = self.api.clients[mac]
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
            await self.api.clients.async_force_reconnect(client_mac)
            return True
        except Exception as err:
            LOGGER.error("Failed to reconnect client: %s", str(err))
            return False

    async def get_bandwidth_usage(self, timespan: int = 3600) -> Dict[str, Any]:
        """Get bandwidth usage statistics for the specified timespan in seconds."""
        LOGGER.debug("Fetching bandwidth usage for last %d seconds", timespan)
        try:
            stats = await self.api.stat_dashboard.async_get()
            return {
                "wan-tx_bytes": stats.get("wan-tx_bytes", 0),
                "wan-rx_bytes": stats.get("wan-rx_bytes", 0),
                "lan-tx_bytes": stats.get("lan-tx_bytes", 0),
                "lan-rx_bytes": stats.get("lan-rx_bytes", 0)
            }
        except Exception as err:
            LOGGER.error("Failed to get bandwidth usage: %s", str(err))
            return {}