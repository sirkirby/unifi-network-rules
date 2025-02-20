"""UDM API for controlling UniFi Dream Machine."""
from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import aiohttp
import json
from aiohttp import ClientTimeout, CookieJar, WSMsgType
from dataclasses import dataclass

from .const import (
    DOMAIN,
    SITE_FEATURE_MIGRATION_ENDPOINT,
    FIREWALL_POLICIES_ENDPOINT,
    TRAFFIC_ROUTES_ENDPOINT,
    FIREWALL_POLICIES_DELETE_ENDPOINT,
    LEGACY_FIREWALL_RULES_ENDPOINT,
    LEGACY_TRAFFIC_RULES_ENDPOINT,
    FIREWALL_ZONE_MATRIX_ENDPOINT,
    FIREWALL_POLICY_TOGGLE_ENDPOINT,
    AUTH_LOGIN_ENDPOINT,
    DEFAULT_HEADERS,
    MIN_REQUEST_INTERVAL,
    ZONE_BASED_FIREWALL_FEATURE,
    COOKIE_TOKEN,
    SESSION_TIMEOUT,
    PORT_FORWARD_ENDPOINT,
    LOGGER
)
from .utils import logger
from .utils.logger import log_call
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import DOMAIN, LOGGER
from .services import SIGNAL_ENTITIES_CLEANUP

@dataclass
class UDMCapabilities:
    """Class to store UDM capabilities."""
    zone_based_firewall: bool = False
    legacy_firewall: bool = False
    legacy_traffic: bool = False
    traffic_routes: bool = False

class UDMAPI:
    """Class to interact with UniFi Dream Machine API."""
    def __init__(self, host: str, username: str, password: str, max_retries: int = 3, retry_delay: int = 1):
        """Initialize the UDMAPI."""
        self.host = host
        self.username = username
        self.password = password
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.capabilities = UDMCapabilities()
        self.hass = None  # Will be set by the integration
        
        # Websocket state tracking
        self._websocket_last_message = None
        self._websocket_callback = None
        
        # Session management
        self._session: Optional[aiohttp.ClientSession] = None
        self._login_lock = asyncio.Lock()
        self._session_timeout = timedelta(minutes=SESSION_TIMEOUT)
        self._last_login: Optional[datetime] = None
        
        # Authentication state
        self._device_token: Optional[str] = None
        self._csrf_token: Optional[str] = None
        self._cookies: Dict[str, str] = {}
        
        # Rate limiting
        self._request_lock = asyncio.Lock()
        self._last_request_time: Optional[datetime] = None
        self._min_request_interval = MIN_REQUEST_INTERVAL

        self._websocket_capabilities = {
            'firewall_policies': False,
            'traffic_routes': True,
            'port_forward_rules': True,
            'legacy_firewall': True,
            'legacy_traffic': True
        }

    @property
    def websocket_last_message(self) -> Optional[datetime]:
        """Get the timestamp of the last websocket message."""
        return self._websocket_last_message

    @websocket_last_message.setter
    def websocket_last_message(self, value: Optional[datetime]) -> None:
        """Set the timestamp of the last websocket message."""
        self._websocket_last_message = value

    @property
    def websocket_callback(self):
        """Get the websocket callback."""
        return self._websocket_callback

    @websocket_callback.setter
    def websocket_callback(self, value):
        """Set the websocket callback."""
        self._websocket_callback = value

    @log_call
    async def detect_capabilities(self) -> bool:
        """Detect UDM capabilities by checking endpoints.
        
        Returns True if any capabilities were successfully detected,
        False if no capabilities could be detected or there was an error.
        """
        try:
            # Reset capabilities to ensure clean detection
            self.capabilities = UDMCapabilities()

            # Always check traffic routes first as they're available in all modes
            routes_success, routes_data, routes_error = await self.get_traffic_routes()
            self.capabilities.traffic_routes = routes_success and isinstance(routes_data, list)
            
            if not self.capabilities.traffic_routes:
                logger.error("Failed to detect traffic routes capability: %s", routes_error)

            # Check zone-based firewall capability using feature migration endpoint
            migration_url = f"https://{self.host}{SITE_FEATURE_MIGRATION_ENDPOINT}"
            success, migrations, error = await self._make_authenticated_request('get', migration_url)
            
            logger.debug("Feature migration check: success=%s, data=%s, error=%s", 
                        success, migrations, error)

            # Try to detect zone-based firewall capability
            if success and isinstance(migrations, list):
                self.capabilities.zone_based_firewall = any(
                    m.get("feature") == ZONE_BASED_FIREWALL_FEATURE
                    for m in migrations
                )
                if not self.capabilities.zone_based_firewall:
                    logger.debug("Zone-based firewall feature not found in migrations")
            else:
                # If migration endpoint fails, try policies endpoint as fallback
                logger.debug("Migration endpoint check failed, trying policies endpoint")
                success, policies, error = await self.get_firewall_policies()
                logger.debug("Firewall policies check: success=%s, has_data=%s, error=%s", success, bool(policies), error)
                self.capabilities.zone_based_firewall = success and bool(policies)

            # If zone-based firewall is not detected, check legacy endpoints
            if not self.capabilities.zone_based_firewall:
                logger.debug("Zone-based firewall not detected, checking legacy endpoints")
                legacy_success, legacy_rules, legacy_error = await self.get_legacy_firewall_rules()
                self.capabilities.legacy_firewall = legacy_success and isinstance(legacy_rules, list)
                self.capabilities.legacy_traffic = self.capabilities.legacy_firewall
                           
                if not self.capabilities.legacy_firewall:
                    logger.error("Failed to detect legacy firewall capability: %s", legacy_error)

            # Log final capability state
            logger.info(
                "UDM Capabilities detected: traffic_routes=%s, zone_based_firewall=%s, legacy_firewall=%s",
                self.capabilities.traffic_routes,
                self.capabilities.zone_based_firewall,
                self.capabilities.legacy_firewall
            )

            # Handle edge case where no firewall capabilities are detected
            if not self.capabilities.zone_based_firewall and not self.capabilities.legacy_firewall:
                logger.error(
                    "No firewall capabilities detected. This could indicate:\n"
                    "1. UniFi Network has changed its API\n"
                    "2. The device is not properly initialized\n"
                    "3. The user lacks necessary permissions\n"
                    "4. Network connectivity issues"
                )

            # Return True if any capability was detected
            return any([
                self.capabilities.traffic_routes,
                self.capabilities.zone_based_firewall,
                self.capabilities.legacy_firewall
            ])

        except Exception as e:
            logger.exception("Error during capability detection: %s", str(e))
            # Reset capabilities on error
            self.capabilities = UDMCapabilities()
            return any([
                self.capabilities.traffic_routes,
                self.capabilities.zone_based_firewall,
                self.capabilities.legacy_firewall
            ])

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=60, connect=30)
            cookie_jar = CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                cookie_jar=cookie_jar,
                connector=aiohttp.TCPConnector(ssl=False)
            )
        return self._session

    async def _wait_for_next_request(self) -> None:
        """Implement rate limiting between requests."""
        if self._last_request_time:
            elapsed = datetime.now() - self._last_request_time
            if (elapsed.total_seconds() < self._min_request_interval):
                wait_time = self._min_request_interval - elapsed.total_seconds()
                logger.debug(f"Rate limiting: waiting {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
        self._last_request_time = datetime.now()

    def _parse_token_cookie(self, cookie_str: str) -> Optional[str]:
        """Parse TOKEN value from Set-Cookie header."""
        try:
            parts = cookie_str.split(';')[0].split('=')
            if len(parts) == 2 and parts[0].strip().upper() == COOKIE_TOKEN:
                return parts[1].strip()
        except Exception as e:
            logger.error(f"Failed to parse token cookie: {e}")
        return None

    def _is_session_expired(self) -> bool:
        """Check if the current session has expired."""
        now = datetime.now()

        # Ensure at least one form of authentication exists
        if not self._cookies.get("TOKEN"):
            logger.debug("Session expired: Missing authentication cookie")
            return True

        # Extend session lifespan check
        if self._last_login and (now - self._last_login) > timedelta(minutes=30):
            logger.debug("Session expired: Timed out")
            return True

        logger.debug("Session is valid")
        return False

    def _get_base_headers(self) -> Dict[str, str]:
        headers = DEFAULT_HEADERS.copy()  # use constant default headers
        # Only add Authorization header if the cookie is not present.
        if not self._cookies.get(COOKIE_TOKEN) and self._device_token:
            headers['Authorization'] = f'Bearer {self._device_token}'
        return headers

    def _get_proxy_headers(self) -> Dict[str, str]:
        headers = self._get_base_headers()  # Use base headers that contain "Authorization"
        if self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token
        if COOKIE_TOKEN in self._cookies:
            headers["Cookie"] = f"{COOKIE_TOKEN}={self._cookies[COOKIE_TOKEN]}"
        logger.debug(f"Using headers: {headers}")
        return headers

    @log_call
    async def authenticate_session(self) -> Tuple[bool, Optional[str]]:
        """Authenticate and get session token."""
        url = f"https://{self.host}{AUTH_LOGIN_ENDPOINT}"
        data = {
            "username": self.username,
            "password": self.password,
            "rememberMe": True
        }

        try:
            session = await self._get_session()
            async with session.post(url, json=data, headers=DEFAULT_HEADERS, timeout=ClientTimeout(total=30)) as response:
                logger.debug(f"Auth response status: {response.status}")
                
                if response.status != 200:
                    error_text = await response.text()
                    return False, f"Authentication failed: {response.status}, {error_text}"
                
                try:
                    response_data = await response.json()
                except json.JSONDecodeError as e:
                    return False, f"Invalid JSON in auth response: {str(e)}"
                
                self._device_token = response_data.get('deviceToken')
                if not self._device_token:
                    return False, "No device token in response"
                
                self._csrf_token = response.headers.get('x-csrf-token')
                if not self._csrf_token:
                    self._csrf_token = response.headers.get('x-updated-csrf-token')
                
                if not self._csrf_token:
                    return False, "No CSRF token in response headers"
                
                token_cookies = response.headers.getall('Set-Cookie', [])
                token_found = False
                
                for cookie_str in token_cookies:
                    token = self._parse_token_cookie(cookie_str)
                    if token:
                        self._cookies[COOKIE_TOKEN] = token
                        token_found = True
                        break
                
                if not token_found:
                    return False, "No TOKEN cookie in response"
                
                self._last_login = datetime.now()
                logger.debug("Authentication successful, updated session time.")
                return True, None
                
        except asyncio.TimeoutError:
            return False, "Authentication request timed out"
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}", exc_info=True)
            return False, str(e)

    async def ensure_authenticated(self) -> Tuple[bool, Optional[str]]:
        """Ensure we have a valid authentication session."""
        async with self._login_lock:
            if self._is_session_expired():
                logger.debug("Session expired, re-authenticating")
                return await self.authenticate_session()
            return True, None

    @log_call
    async def _make_authenticated_request(self, method: str, url: str, json_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any, Optional[str]]:
        """Make an authenticated request with correct headers and enhanced logging."""
        async with self._request_lock:
            await self.ensure_authenticated()  # Ensure session is authenticated before making request
            await self._wait_for_next_request()
            last_error = None  # capture the last error message
            for attempt in range(self.max_retries):
                try:
                    session = await self._get_session()
                    headers = self._get_proxy_headers()
                    
                    logger.debug(f"Making {method.upper()} request to {url} with headers: {headers}")
                    if json_data:
                        logger.debug(f"Request payload: {json.dumps(json_data, indent=2)}")

                    async with session.request(method, url, headers=headers, json=json_data) as response:
                        response_text = await response.text()
                        
                        if response.status in [401, 403]:
                            last_error = f"Request failed: {response.status}, {response_text}"
                            logger.warning(f"Authentication error ({response.status}): {response_text}")
                            self._cookies.clear()
                            self._csrf_token = None
                            self._device_token = None
                            self._last_login = None
                            
                            auth_success, auth_error = await self.authenticate_session()
                            if not auth_success:
                                logger.error(f"Re-authentication failed: {auth_error}")
                                if attempt < self.max_retries - 1:
                                    await asyncio.sleep(self.retry_delay)
                                    continue
                                return False, None, f"Authentication failed after {self.max_retries} attempts"
                            
                            if attempt < self.max_retries - 1:
                                await asyncio.sleep(self.retry_delay)
                            continue

                        if response.status in [200, 201, 204]:
                            # Update tokens from response
                            new_csrf = response.headers.get("x-csrf-token") or response.headers.get("x-updated-csrf-token")
                            if new_csrf:
                                logger.debug(f"Updating CSRF token to: {new_csrf}")
                                self._csrf_token = new_csrf

                            # Handle both dict and ClientResponse cookie types
                            if hasattr(response.cookies, 'items'):
                                for key, cookie in response.cookies.items():
                                    if key == COOKIE_TOKEN:
                                        if isinstance(cookie, str):
                                            self._cookies[COOKIE_TOKEN] = cookie
                                        else:
                                            self._cookies[COOKIE_TOKEN] = cookie.value
                            else:
                                for cookie_str in response.headers.getall('Set-Cookie', []):
                                    token = self._parse_token_cookie(cookie_str)
                                    if token:
                                        self._cookies[COOKIE_TOKEN] = token
                                        break

                            try:
                                if response.status == 204 or not response_text:
                                    return True, None, None
                                parsed_response = json.loads(response_text)
                                return True, parsed_response, None
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse JSON response: {e}")
                                return False, None, f"Invalid JSON response: {str(e)}"

                        last_error = f"Request failed: {response.status}, {response_text}"
                        return False, None, last_error

                except Exception as e:
                    last_error = str(e)
                    logger.error(f"Request error: {str(e)}")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    return False, None, last_error

            return False, None, last_error if last_error else "Max retries reached"

    async def _process_rules_response(
        self,
        success: bool,
        response: Any,
        error: Optional[str],
        rule_type: str
    ) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Process rule response with consistent error handling."""
        if not success:
            return False, None, error

        try:
            if response is None:
                logger.error("Empty response received")
                return False, None, "Empty response"

            # For legacy firewall rules, we expect {data: [...]}
            if rule_type == "legacy firewall rules":
                if not isinstance(response, dict) or 'data' not in response:
                    logger.error(f"Invalid response format for {rule_type}: {response}")
                    return False, None, "Invalid response format - missing data field"
                rules = response['data']
            else:
                # Handle both direct array and {data: [...]} responses
                rules = response.get('data', response) if isinstance(response, dict) else response
            
            if not isinstance(rules, list):
                logger.error(f"Rules data is not a list: {type(rules)}")
                return False, None, f"Invalid response format - expected list"

            logger.debug(f"Successfully fetched {len(rules)} {rule_type}")
            return True, rules, None

        except Exception as e:
            logger.exception(f"Error processing {rule_type}")
            return False, None, f"Error processing response: {str(e)}"

    async def get_firewall_policies(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch firewall policies from the UDM."""
        url = f"https://{self.host}{FIREWALL_POLICIES_ENDPOINT}"
        success, response, error = await self._make_authenticated_request('get', url)
        return await self._process_rules_response(success, response, error, "firewall policies")

    async def get_firewall_policy(self, policy_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Fetch a single firewall policy by its policy_id."""
        success, policies, error = await self.get_firewall_policies()
        if not success:
            return False, None, error
        if policies is None:
            return False, None, "No policies returned"
        policy = next((p for p in policies if p.get('_id') == policy_id), None)
        if policy is None:
            return False, None, f"Policy with id {policy_id} not found"
        return True, policy, None

    async def get_traffic_routes(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch all traffic routes from the UDM."""
        url = f"https://{self.host}{TRAFFIC_ROUTES_ENDPOINT}"
        success, response, error = await self._make_authenticated_request('get', url)
        return await self._process_rules_response(success, response, error, "traffic routes")

    async def toggle_firewall_policy(self, policy_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a firewall policy on or off."""
        # First get the current policy to preserve all fields
        success, policy, error = await self.get_firewall_policy(policy_id)
        if not success:
            return False, f"Failed to fetch policy: {error}"

        # Update the policy with new enabled state
        policy['enabled'] = enabled
        
        # PUT the update
        url = f"https://{self.host}{FIREWALL_POLICIES_ENDPOINT}/{policy_id}"
        success, response, error = await self._make_authenticated_request('put', url, policy)
        
        if not success:
            return False, f"Failed to update policy: {error}"
            
        return True, None

    async def toggle_traffic_route(self, route_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a traffic route."""
        # First get all traffic routes
        success, all_routes, error = await self.get_traffic_routes()
        if not success:
            return False, f"Failed to fetch routes: {error}"

        # Find our specific route
        route = next((r for r in all_routes if r.get('_id') == route_id), None)
        if not route:
            return False, f"Route {route_id} not found"

        # Create updated route with new enabled state
        updated_route = dict(route)
        updated_route['enabled'] = enabled
        
        # PUT the update
        url = f"https://{self.host}{TRAFFIC_ROUTES_ENDPOINT}/{route_id}"
        success, response, error = await self._make_authenticated_request('put', url, updated_route)
        
        if not success:
            return False, f"Failed to update route: {error}"
            
        return True, None

    async def toggle_port_forward_rule(self, rule_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a port forward rule."""
        # First get all port forward rules
        success, rules, error = await self.get_port_forward_rules()
        if not success:
            return False, f"Failed to fetch rules: {error}"

        # Find our specific rule
        rule = next((r for r in rules if r.get('_id') == rule_id), None)
        if not rule:
            return False, f"Rule {rule_id} not found"

        # Create updated rule with new enabled state
        updated_rule = dict(rule)
        updated_rule['enabled'] = enabled
        
        # PUT the update
        url = f"https://{self.host}{PORT_FORWARD_ENDPOINT}/{rule_id}"
        success, response, error = await self._make_authenticated_request('put', url, updated_rule)
        
        if not success:
            return False, f"Failed to update rule: {error}"
            
        return True, None

    async def get_firewall_zone_matrix(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch firewall zone matrix from the UDM."""
        url = f"https://{self.host}{FIREWALL_ZONE_MATRIX_ENDPOINT}"
        return await self._make_authenticated_request('get', url)

    async def get_legacy_firewall_rules(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch legacy firewall rules from the UDM."""
        url = f"https://{self.host}{LEGACY_FIREWALL_RULES_ENDPOINT}"
        success, response, error = await self._make_authenticated_request('get', url)
        return await self._process_rules_response(success, response, error, "legacy firewall rules")

    async def get_legacy_traffic_rules(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch legacy traffic rules from the UDM."""
        url = f"https://{self.host}{LEGACY_TRAFFIC_RULES_ENDPOINT}"
        success, response, error = await self._make_authenticated_request('get', url)
        return await self._process_rules_response(success, response, error, "legacy traffic rules")
    
    async def get_legacy_firewall_rule(self, rule_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Fetch a single legacy firewall rule by its rule_id.
        
        Returns a tuple (success, rule, error) where rule is the rule dictionary.
        """
        url = f"https://{self.host}{LEGACY_FIREWALL_RULES_ENDPOINT}/{rule_id}"
        success, response, error = await self._make_authenticated_request('get', url)
        
        if not success:
            return False, None, f"Failed to fetch rule: {error}"
            
        if not response or not isinstance(response, dict) or 'data' not in response:
            return False, None, "Invalid rule data received"
        
        rules = response.get('data', [])
        rule = next((r for r in rules if r['_id'] == rule_id), None)
        if not rule:
            return False, None, f"Rule {rule_id} not found"
        
        return True, rule, None
    
    async def toggle_legacy_firewall_rule(self, rule_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a legacy firewall rule."""
        # Use the new helper method to fetch the rule.
        success, rule, error = await self.get_legacy_firewall_rule(rule_id)
        if not success:
            return False, error
        
        # Create a copy and update the enabled state.
        updated_rule = dict(rule)
        updated_rule['enabled'] = enabled
        
        url = f"https://{self.host}{LEGACY_FIREWALL_RULES_ENDPOINT}/{rule_id}"
        success, response, error = await self._make_authenticated_request('put', url, updated_rule)
        if not success:
            return False, f"Failed to update rule: {error}"
            
        return True, None

    async def toggle_legacy_traffic_rule(self, rule_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a legacy traffic rule."""
        url = f"https://{self.host}{LEGACY_TRAFFIC_RULES_ENDPOINT}/{rule_id}"
        
        # First get all traffic rules to find the one we want to update
        success, rules, error = await self.get_legacy_traffic_rules()
        
        if not success:
            return False, f"Failed to fetch rules: {error}"

        if not rules or not isinstance(rules, list):
            return False, "Invalid rules data received"

        rule = next((r for r in rules if r['_id'] == rule_id), None)
        if not rule:
            return False, f"Rule {rule_id} not found"

        # Create a copy and update
        updated_rule = dict(rule)
        updated_rule['enabled'] = enabled
        
        # Send the update
        success, response, error = await self._make_authenticated_request('put', url, updated_rule)
        if not success:
            return False, f"Failed to update rule: {error}"
            
        return True, None

    async def update_firewall_policy(self, policy_id: str, policy_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Update a firewall policy."""
        url = f"https://{self.host}{FIREWALL_POLICIES_ENDPOINT}/{policy_id}"
        success, response, error = await self._make_authenticated_request('put', url, policy_data)
        if not success:
            logger.error(f"Failed to update firewall policy {policy_id}: {error}")
            return False, error
        return True, None

    async def update_traffic_route(self, route_id: str, route_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Update a traffic route."""
        url = f"https://{self.host}{TRAFFIC_ROUTES_ENDPOINT}/{route_id}"
        success, response, error = await self._make_authenticated_request('put', url, route_data)
        if not success:
            logger.error(f"Failed to update traffic route {route_id}: {error}")
            return False, error
        return True, None

    async def create_firewall_policy(self, policy_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Create a new firewall policy."""
        url = f"https://{self.host}{FIREWALL_POLICIES_ENDPOINT}"
        success, response, error = await self._make_authenticated_request('post', url, policy_data)
        if not success:
            logger.error(f"Failed to create firewall policy: {error}")
            return False, error
        return True, None

    async def delete_firewall_policies(self, rule_ids: list[str]) -> tuple[bool, str]:
        """Delete firewall policies."""
        try:
            url = f"https://{self.host}{FIREWALL_POLICIES_DELETE_ENDPOINT}"
            success, response, error = await self._make_authenticated_request('post', url, rule_ids)
            
            if not success:
                return False, f"Failed to delete firewall policies: {error}"

            return True, ""
        except Exception as e:
            return False, str(e)

    # Removed unverified delete endpoints for traffic routes, port forwarding, and legacy rules
    # These should only be added once we've confirmed the endpoints exist and work

    async def get_port_forward_rules(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch port forwarding rules from the UDM."""
        url = f"https://{self.host}{PORT_FORWARD_ENDPOINT}"
        success, response, error = await self._make_authenticated_request('get', url)
        return await self._process_rules_response(success, response, error, "port forward rules")

    async def update_port_forward_rule(self, rule_id: str, rule_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Update a port forward rule."""
        url = f"https://{self.host}{PORT_FORWARD_ENDPOINT}/{rule_id}"
        success, response, error = await self._make_authenticated_request('put', url, rule_data)
        if not success:
            logger.error(f"Failed to update port forward rule {rule_id}: {error}")
            return False, error
        return True, None

    async def create_port_forward_rule(self, rule_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Create a new port forward rule. Mainly used for rule restoration."""
        url = f"https://{self.host}{PORT_FORWARD_ENDPOINT}"
        success, response, error = await self._make_authenticated_request('post', url, rule_data)
        if not success:
            logger.error(f"Failed to create port forward rule: {error}")
            return False, error
        return True, None

    async def delete_port_forward_rule(self, rule_id: str) -> Tuple[bool, Optional[str]]:
        """Delete a port forward rule."""
        url = f"https://{self.host}{PORT_FORWARD_ENDPOINT}/{rule_id}"
        success, response, error = await self._make_authenticated_request('delete', url)
        if not success:
            logger.error(f"Failed to delete port forward rule: {error}")
            return False, error
        return True, None

    def _log_response_data(self, method: str, url: str, response_status: int, response_text: str):
        """Log response data in a structured way."""
        try:
            response_data = json.loads(response_text)
            formatted_response = json.dumps(response_data, indent=2)
        except json.JSONDecodeError:
            formatted_response = response_text

        logger.debug(f"API Response Details:")
        logger.debug(f"Method: {method}")
        logger.debug(f"URL: {url}")
        logger.debug(f"Status: {response_status}")
        logger.debug(f"Response Body:\n{formatted_response}")

    async def cleanup(self):
        """Cleanup resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _detect_websocket_capabilities(self) -> None:
        """Test which features support websocket updates."""
        try:
            # Try to establish websocket connection
            await self.start_websocket()
            
            # Wait for initial messages to determine capabilities
            await asyncio.sleep(5)  # Give time for initial messages
            
            if hasattr(self, '_websocket') and self._websocket:
                supported_types = self._websocket.get_supported_message_types()
                
                # Map message types to capabilities
                self._websocket_capabilities = {
                    'firewall_policies': 'firewall_policy' in supported_types,
                    'traffic_routes': 'traffic_route' in supported_types,
                    'port_forward_rules': 'port_forward' in supported_types,
                    'legacy_firewall': 'firewall_rule' in supported_types,
                    'legacy_traffic': 'traffic_rule' in supported_types
                }
                
                logger.debug(
                    "Detected websocket capabilities: %s", 
                    {k: v for k, v in self._websocket_capabilities.items() if v}
                )
            else:
                logger.warning("No websocket connection available for capability detection")
                
        except Exception as e:
            logger.warning("Could not detect websocket capabilities: %s", str(e))
            # If websocket detection fails, assume no websocket support
            for feature in self._websocket_capabilities:
                self._websocket_capabilities[feature] = False

    async def _test_websocket_feature(self, feature: str) -> bool:
        """Test if a specific feature supports websocket updates."""
        return self._websocket_capabilities[feature]

    def supports_websocket(self, feature: str) -> bool:
        """Check if a feature supports websocket updates."""
        return self._websocket_capabilities.get(feature, False)

    async def start_websocket(self) -> None:
        """Start the websocket connection."""
        url = f"wss://{self.host}/proxy/network/wss/s/default/events"
        session = await self._get_session()
        
        try:
            # Ensure we have valid authentication before starting websocket
            auth_success, auth_error = await self.ensure_authenticated()
            if not auth_success:
                raise Exception(f"Authentication failed: {auth_error}")

            # Get the headers with authentication
            headers = self._get_proxy_headers()
            
            # Create websocket connection
            ws = await session.ws_connect(
                url,
                headers=headers,
                ssl=False
            )
            
            # Start listening for messages
            async def _listen():
                try:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                self.websocket_last_message = datetime.now()
                                if self.websocket_callback:
                                    if asyncio.iscoroutinefunction(self.websocket_callback):
                                        asyncio.create_task(self.websocket_callback(data))
                                    else:
                                        self.websocket_callback(data)
                            except json.JSONDecodeError as e:
                                LOGGER.error("Failed to parse websocket message: %s", e)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            LOGGER.debug("Websocket connection closed or error occurred")
                            break
                except Exception as e:
                    LOGGER.error("Websocket listen error: %s", str(e))
                finally:
                    try:
                        await ws.close()
                    except Exception as e:
                        LOGGER.debug("Error closing websocket: %s", str(e))

            # Start the listen task
            if self.hass and self.hass.loop:
                self.hass.loop.create_task(_listen())
            else:
                LOGGER.error("Cannot start websocket: hass or loop not available")
                raise RuntimeError("Home Assistant instance not properly initialized")
            
        except Exception as e:
            LOGGER.error("Failed to start websocket: %s", str(e))
            raise
            
        LOGGER.info("Websocket connection established")

    async def get_cookie(self) -> str:
        """Get the authentication cookie for websocket connections."""
        # Ensure we have a valid session first
        auth_success, auth_error = await self.ensure_authenticated()
        if not auth_success:
            raise Exception(f"Failed to authenticate: {auth_error}")
            
        # Return the TOKEN cookie if we have it
        if cookie := self._cookies.get(COOKIE_TOKEN):
            return cookie
            
        raise Exception("No valid authentication cookie found")