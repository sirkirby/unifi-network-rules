"""UDM API for controlling UniFi Dream Machine."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import asyncio
import ssl
from aiohttp import CookieJar, WSMsgType
import aiohttp

from aiounifi.models.api import ApiRequest, ApiRequestV2
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
        self.controller = None
        self._initialized = False
        self._hass_session = False
        self._ws_callback = None
        self._last_login_attempt = 0
        self._login_attempt_count = 0
        self._max_login_attempts = 3
        self._login_cooldown = 60
        self._config = None  # Store config for delayed controller creation

    async def async_init(self, hass: HomeAssistant | None = None) -> None:
        """Async initialization of the API."""
        try:
            ssl_context: ssl.SSLContext | bool = False
            if self.verify_ssl:
                if isinstance(self.verify_ssl, str):
                    ssl_context = ssl.create_default_context(cafile=self.verify_ssl)
                else:
                    ssl_context = True

            if not self._session:
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

            self._config = Configuration(
                session=self._session,
                host=self.host,
                username=self.username,
                password=self.password,
                port=443,
                site="default",
                ssl_context=ssl_context,
            )

            # Use existing controller if available to preserve state
            if not self.controller:
                # Import here to allow patching in tests
                from aiounifi import Controller as UnifiController
                self.controller = UnifiController(self._config)

            # Initialize
            await self.controller.login()
            
            if hasattr(self.controller, "sites"):
                await self.controller.sites.update()
            
            # Set initialized before refresh
            self._initialized = True
            
            # Initial refresh of all data
            await self.refresh_all()

        except LoginRequired as err:
            if self._session and not self._hass_session:
                await self._session.close()
            self._session = None
            self.controller = None
            self._initialized = False
            raise InvalidAuth("Invalid credentials") from err
        except (BadGateway, ResponseError, RequestError, ServiceUnavailable) as err:
            if self._session and not self._hass_session:
                await self._session.close()
            self._session = None
            self.controller = None
            self._initialized = False
            raise CannotConnect(f"Failed to connect: {err}") from err
        except Exception as err:
            if self._session and not self._hass_session:
                await self._session.close()
            self._session = None
            self.controller = None
            self._initialized = False
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
            self._initialized = False
            self._config = None

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
    async def get_firewall_policies(self, include_predefined: bool = False) -> List[Any]:
        """Get firewall policies."""
        if not self.controller or not self._initialized:
            return []
            
        try:
            await self.controller.firewall_policies.update()
            policies = list(self.controller.firewall_policies.values())
            if not include_predefined:
                return [policy for policy in policies if not (policy.get("predefined", False) if isinstance(policy, dict) else getattr(policy, "predefined", False))]
            return policies
        except Exception as err:
            LOGGER.error("Failed to get firewall policies: %s", str(err))
            return []

    async def add_firewall_policy(self, policy_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a new firewall policy."""
        LOGGER.debug("Adding firewall policy: %s", policy_data)
        try:
            request = ApiRequestV2 ("POST", "firewall-policies", policy_data)
            policy = await self.controller.request(request)
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
            request = ApiRequestV2.create("POST", "firewall-policies/batch-delete", f"['{policy_id}']")
            await self.controller.firewall_policies.remove_item(policy_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove firewall policy: %s", str(err))
            return False

    # Traffic Rules Methods
    async def get_traffic_rules(self) -> List[Any]:
        """Get all traffic rules."""
        if not self.controller:
            return []
            
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
            request = ApiRequestV2 ("POST", "trafficrules", rule_data)
            rule = await self.controller.request(request)
            return rule
        except Exception as err:
            LOGGER.error("Failed to add traffic rule: %s", str(err))
            return None

    async def toggle_traffic_rule(self, rule_id: str, enabled: bool) -> bool:
        """Enable or disable a traffic rule."""
        LOGGER.debug("Setting traffic rule %s enabled state to: %s", rule_id, enabled)
        try:
            await self.controller.traffic_rules.toggle(rule_id, enabled)
            return True
        except Exception as err:
            LOGGER.error("Failed to toggle traffic rule: %s", str(err))
            return False
    
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
        if not self.controller:
            return []
            
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
            request = ApiRequest ("POST", "portforward", forward_data)
            forward = await self.controller.request(request)
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
            request = ApiRequestV2 ("POST", "trafficroutes", route_data)
            route = await self.controller.request(request)
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

    # WLAN Management Methods
    async def get_wlans(self) -> List[Dict[str, Any]]:
        """Get all WLANs."""
        if not self.controller:
            return []
            
        LOGGER.debug("Fetching WLANs")
        try:
            await self.controller.wlans.update()
            return list(self.controller.wlans.values())
        except Exception as err:
            LOGGER.error("Failed to get WLANs: %s", str(err))
            return []

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
            system_information = await self.controller.system_information.update()
            if system_information:
                stats.update(system_information)
            
            return stats
        except Exception as err:
            LOGGER.error("Failed to get system stats: %s", str(err))
            return {}

    # Bulk Operations and Updates
    async def refresh_all(self) -> None:
        """Refresh all data from the UniFi controller."""
        LOGGER.debug("Refreshing all data from UniFi controller")
        if not self.controller or not self._initialized:
            return
            
        try:
            update_tasks = [
                self.controller.firewall_policies.update(),
                self.controller.traffic_rules.update(),
                self.controller.port_forwarding.update(),
                self.controller.traffic_routes.update(),
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
                FirewallPolicyUpdateRequest.create(policy)
            )
            
            if success:
                success_count += 1
            else:
                LOGGER.error("Failed to update policy %s: %s", policy_id, error)
                failed_ids.append(policy_id)
        
        return success_count, failed_ids

    async def get_rule_status(self, rule_id: str) -> Dict[str, Any]:
        """Get detailed status for a specific rule."""
        if not self.controller:
            return {
                "active": False,
                "dependencies": [],
                "conflicts": [],
                "last_modified": None,
                "type": None
            }
            
        LOGGER.debug("Getting detailed status for rule: %s", rule_id)
        try:
            status = {
                "active": False,
                "dependencies": [],
                "conflicts": [],
                "last_modified": None,
                "type": None
            }
            
            rules_map = {
                "firewall_policy": self.controller.firewall_policies,
                "traffic_rule": self.controller.traffic_rules,
                "port_forward": self.controller.port_forwarding,
                "traffic_route": self.controller.traffic_routes
            }
            
            for rule_type, rules in rules_map.items():
                if rule_id in rules:
                    rule = rules[rule_id]
                    if isinstance(rule, dict):
                        rule_data = rule
                    else:
                        rule_data = dict(rule)
                    
                    status["active"] = rule_data.get("enabled", False)
                    status["last_modified"] = rule_data.get("last_modified")
                    status["type"] = rule_type
                    break
            
            return status
        except Exception as err:
            LOGGER.error("Failed to get rule status: %s", str(err))
            return status

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