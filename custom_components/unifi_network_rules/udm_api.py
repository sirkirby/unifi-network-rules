"""UDM API for controlling UniFi Dream Machine."""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import aiohttp
import json
from aiohttp import ClientTimeout, CookieJar
from dataclasses import dataclass

from .const import (
    SITE_FEATURE_MIGRATION_ENDPOINT,
    FIREWALL_POLICIES_ENDPOINT,
    TRAFFIC_ROUTES_ENDPOINT,
    LEGACY_FIREWALL_RULES_ENDPOINT,
    LEGACY_TRAFFIC_RULES_ENDPOINT,
    FIREWALL_ZONE_MATRIX_ENDPOINT,
    FIREWALL_POLICY_TOGGLE_ENDPOINT,
    AUTH_LOGIN_ENDPOINT,
    DEFAULT_HEADERS,
    MIN_REQUEST_INTERVAL,
    ZONE_BASED_FIREWALL_FEATURE,
    COOKIE_TOKEN
)
from .utils import logger
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .utils.logger import log_call

@dataclass
class UDMCapabilities:
    """Class to store UDM capabilities."""
    zone_based_firewall: bool = False
    legacy_firewall: bool = False
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
        
        # Session management
        self._session: Optional[aiohttp.ClientSession] = None
        self._login_lock = asyncio.Lock()
        self._session_timeout = timedelta(minutes=30)
        self._last_login: Optional[datetime] = None
        
        # Authentication state
        self._device_token: Optional[str] = None
        self._csrf_token: Optional[str] = None
        self._cookies: Dict[str, str] = {}
        
        # Rate limiting
        self._request_lock = asyncio.Lock()
        self._last_request_time: Optional[datetime] = None
        self._min_request_interval = MIN_REQUEST_INTERVAL

    @log_call
    async def detect_capabilities(self) -> bool:
        """Detect UDM capabilities by checking endpoints."""
        try:
            url = f"https://{self.host}{SITE_FEATURE_MIGRATION_ENDPOINT}"
            success, migrations, error = await self._make_authenticated_request('get', url)
            
            logger.debug("Feature migration check: success=%s, data=%s, error=%s", 
                        success, migrations, error)

            if success and isinstance(migrations, list):
                self.capabilities.zone_based_firewall = any(
                    m.get("feature") == ZONE_BASED_FIREWALL_FEATURE
                    for m in migrations
                )
            else:
                # If migration check fails, check policies endpoint
                success, policies, error = await self.get_firewall_policies()
                logger.debug("Firewall policies check: success=%s, has_data=%s, error=%s",
                            success, bool(policies), error)
                self.capabilities.zone_based_firewall = success

            # If not zone-based, check legacy endpoints
            if not self.capabilities.zone_based_firewall:
                self.capabilities.legacy_firewall = await self._check_legacy_endpoints()
            else:
                self.capabilities.legacy_firewall = False

            # Check traffic routes (available in both modes)
            routes_success, routes_data, _ = await self.get_traffic_routes()
            self.capabilities.traffic_routes = routes_success and isinstance(routes_data, list)

            logger.info(
                "UDM Capabilities: zone_based_firewall=%s, legacy_firewall=%s, traffic_routes=%s",
                self.capabilities.zone_based_firewall,
                self.capabilities.legacy_firewall,
                self.capabilities.traffic_routes
            )

            return True

        except Exception as e:
            logger.error("Error detecting UDM capabilities: %s", str(e))
            return False
    
    async def _check_legacy_endpoints(self) -> bool:
        """Check if legacy endpoints return data."""
        success, rules, error = await self.get_legacy_firewall_rules()
        logger.debug("Legacy firewall check: success=%s, has_data=%s, error=%s",
                    success, bool(rules), error)
        
        if success and rules:
            return True

        # Try legacy traffic rules endpoint as backup
        success, rules, error = await self.get_legacy_traffic_rules()
        logger.debug("Legacy traffic check: success=%s, has_data=%s, error=%s",
                    success, bool(rules), error)
        
        return success and bool(rules)

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
            if elapsed.total_seconds() < self._min_request_interval:
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
        """Check if the current session has expired.
        
        The session is considered expired if:
          - The authentication cookie is missing.
          - The elapsed time since the last successful login exceeds the session timeout.
        """
        now = datetime.now()
 
        # Check if the authentication cookie exists.
        if not self._cookies.get(COOKIE_TOKEN):
            logger.debug("Session expired: Missing authentication cookie")
            return True
 
        # Check if the last login time exceeds the configured session timeout.
        if self._last_login and (now - self._last_login) > self._session_timeout:
            logger.debug("Session expired: Timed out (elapsed: %s, timeout: %s)", now - self._last_login, self._session_timeout)
            return True
 
        logger.debug("Session is valid")
        return False

    def _get_base_headers(self) -> Dict[str, str]:
        """Get base headers for requests using constants from const.py."""
        headers = DEFAULT_HEADERS.copy()  # use constant default headers
        if self._device_token:
            headers['Authorization'] = f'Bearer {self._device_token}'
        return headers

    def _get_proxy_headers(self) -> Dict[str, str]:
        """Get proxy headers for requests using constants from const.py."""
        headers = DEFAULT_HEADERS.copy()
        headers["X-CSRF-Token"] = self._csrf_token or ""
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
            async with session.post(url, json=data, timeout=ClientTimeout(total=30)) as response:
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
                
                # Update the last login time on successful authentication.
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
                logger.debug("Session expired, but checking for valid authentication cookie.")

                # If we have a valid TOKEN cookie, assume session is still valid
                if self._cookies.get("TOKEN"):
                    logger.debug("Session cookie is present, skipping re-authentication.")
                    return True, None

                # If no valid session, attempt re-authentication
                logger.debug("No valid session cookie, performing re-authentication.")
                success, error = await self.authenticate_session()
                return success, error
            return True, None

    async def _make_authenticated_request(self, method: str, url: str, json_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any, Optional[str]]:
        """Make an authenticated request with correct headers and enhanced logging."""
        async with self._request_lock:
            await self._wait_for_next_request()

            for attempt in range(self.max_retries):
                try:
                    if self._is_session_expired():
                        logger.debug("Session expired, attempting reauth")
                        success, error = await self.authenticate_session()
                        if not success:
                            return False, None, f"Authentication failed: {error}"

                    session = await self._get_session()
                    headers = self._get_proxy_headers()
                    
                    logger.debug(f"Making {method.upper()} request to {url}")
                    if json_data:
                        logger.debug(f"Request payload: {json.dumps(json_data, indent=2)}")

                    async with session.request(method, url, headers=headers, json=json_data) as response:
                        response_text = await response.text()
                        self._log_response_data(method, url, response.status, response_text)

                        if response.status == 200:
                            try:
                                parsed_response = json.loads(response_text)
                                self._last_successful_request = datetime.now()
                                return True, parsed_response, None
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse JSON response: {e}")
                                return False, None, f"Invalid JSON response: {str(e)}"

                        if response.status in [401, 403]:
                            logger.warning(f"Received {response.status}: {response_text}")
                            if attempt < self.max_retries - 1:
                                await asyncio.sleep(self.retry_delay)
                                continue

                        return False, None, f"Request failed: {response.status}, {response_text}"

                except Exception as e:
                    logger.error(f"Request error: {str(e)}")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    return False, None, str(e)

            return False, None, "Max retries reached"


    async def get_firewall_policies(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch firewall policies from the UDM."""
        auth_success, auth_error = await self.ensure_authenticated()
        if not auth_success:
            return False, None, f"Authentication failed: {auth_error}"
            
        url = f"https://{self.host}{FIREWALL_POLICIES_ENDPOINT}"
        return await self._make_authenticated_request('get', url)

    async def get_traffic_routes(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch all traffic routes from the UDM."""
        auth_success, auth_error = await self.ensure_authenticated()
        if not auth_success:
            return False, None, f"Authentication failed: {auth_error}"
            
        url = f"https://{self.host}{TRAFFIC_ROUTES_ENDPOINT}"
        return await self._make_authenticated_request('get', url)

    async def toggle_firewall_policy(self, policy_id: str, enabled: bool):
        """Toggle a firewall policy on or off."""
        url = f"https://{self.host}{FIREWALL_POLICY_TOGGLE_ENDPOINT}"
        payload = [{"_id": policy_id, "enabled": enabled}]

        logger.info("Sending firewall policy toggle request: %s", payload)

        success, response, error = await self._make_authenticated_request('put', url, payload)
        logger.info("PUT response - Success: %s, Response: %s, Error: %s", success, response, error)

        if not success:
            logger.error("Failed to toggle firewall policy %s: %s", policy_id, error)
            if response:
                logger.error("Response content: %s", await response.text())
            return False, error

        logger.info("Toggled firewall policy %s to %s successfully", policy_id, enabled)
        return True, None

    async def toggle_traffic_route(self, route_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a traffic route."""
        # First get all traffic routes
        all_routes_url = f"https://{self.host}{TRAFFIC_ROUTES_ENDPOINT}"
        logger.info("Fetching all routes from URL: %s", all_routes_url)
        success, all_routes, error = await self._make_authenticated_request('get', all_routes_url)
        logger.info("GET all routes response - Success: %s, Total Routes: %s, Error: %s", 
                    success, len(all_routes) if all_routes else 0, error)
        
        if not success or not all_routes:
            logger.error("Failed to fetch all routes: %s", error)
            return False, f"Failed to fetch all routes: {error}"

        # Find our specific route
        route = next((r for r in all_routes if r.get('_id') == route_id), None)
        if not route:
            logger.error("Route ID %s not found in routes list", route_id)
            return False, f"Route ID {route_id} not found"

        # Create updated route with new enabled state
        updated_route = dict(route)
        updated_route['enabled'] = enabled
        
        # PUT the update back
        update_url = f"{all_routes_url}/{route_id}"
        logger.info("Sending PUT request to %s with route: %s", update_url, updated_route)
        success, response, error = await self._make_authenticated_request('put', update_url, updated_route)
        logger.info("PUT response - Success: %s, Response: %s, Error: %s", success, response, error)
        
        if success:
            logger.info(f"Toggled traffic route {route_id} to {'on' if enabled else 'off'}")
            return True, None
            
        return False, f"Failed to update route: {error}"
    
    async def get_firewall_zone_matrix(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch firewall zone matrix from the UDM."""
        auth_success, auth_error = await self.ensure_authenticated()
        if not auth_success:
            return False, None, f"Authentication failed: {auth_error}"
            
        url = f"https://{self.host}{FIREWALL_ZONE_MATRIX_ENDPOINT}"
        return await self._make_authenticated_request('get', url)

    async def get_legacy_firewall_rules(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch legacy firewall rules from the UDM."""
        auth_success, auth_error = await self.ensure_authenticated()
        if not auth_success:
            return False, None, f"Authentication failed: {auth_error}"
        
        url = f"https://{self.host}{LEGACY_FIREWALL_RULES_ENDPOINT}"
        success, response, error = await self._make_authenticated_request('get', url)
        
        if not success:
            return False, None, error
            
        try:
            if not isinstance(response, dict):
                logger.error(f"Unexpected response type: {type(response)}")
                return False, None, "Invalid response format - not a dictionary"
                
            if 'data' not in response:
                logger.error(f"No 'data' key in response: {response}")
                return False, None, "Invalid response format - missing data key"
                
            rules = response['data']
            if not isinstance(rules, list):
                logger.error(f"Rules data is not a list: {type(rules)}")
                return False, None, "Invalid rules format"
                
            logger.debug(f"Successfully fetched {len(rules)} legacy firewall rules")
            for rule in rules:
                logger.debug(f"Rule: {rule.get('name', 'Unnamed')} - Enabled: {rule.get('enabled', False)}")
                
            return True, rules, None
            
        except Exception as e:
            logger.exception("Error processing legacy firewall rules")
            return False, None, f"Error processing response: {str(e)}"

    async def get_legacy_traffic_rules(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch legacy traffic rules from the UDM."""
        auth_success, auth_error = await self.ensure_authenticated()
        if not auth_success:
            return False, None, f"Authentication failed: {auth_error}"
        
        url = f"https://{self.host}{LEGACY_TRAFFIC_RULES_ENDPOINT}"
        success, response, error = await self._make_authenticated_request('get', url)
        
        if not success:
            return False, None, error
            
        try:
            if response is None:
                logger.error("Empty response received")
                return False, None, "Empty response"
                
            if not isinstance(response, list):
                logger.error(f"Unexpected response type: {type(response)}")
                return False, None, f"Invalid response format - expected list, got {type(response)}"
                
            logger.debug(f"Successfully fetched {len(response)} legacy traffic rules")
            for rule in response:
                logger.debug(f"Traffic Rule: {rule.get('description', 'Unnamed')} - Enabled: {rule.get('enabled', False)}")
                
            return True, response, None
            
        except Exception as e:
            logger.exception("Error processing legacy traffic rules")
            return False, None, f"Error processing response: {str(e)}"
    
    async def toggle_legacy_firewall_rule(self, rule_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a legacy firewall rule."""
        url = f"https://{self.host}{LEGACY_FIREWALL_RULES_ENDPOINT}/{rule_id}"
        
        # First get the current rule
        success, response, error = await self._make_authenticated_request('get', url)
        if not success:
            return False, f"Failed to fetch rule: {error}"

        if not response or not isinstance(response, dict) or 'data' not in response:
            return False, "Invalid rule data received"

        # For legacy firewall rules, the response includes a data array
        rules = response.get('data', [])
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

    def _log_response_data(self, method: str, url: str, response_status: int, response_text: str):
        """Log response data in a structured way."""
        try:
            # Try to parse as JSON for pretty printing
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