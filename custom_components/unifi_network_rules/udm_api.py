"""UDM API for controlling UniFi Dream Machine."""
import aiohttp
import asyncio
import logging
import json
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from aiohttp import ClientTimeout, ClientError, CookieJar

_LOGGER = logging.getLogger(__name__)

class UDMAPI:
    def __init__(self, host: str, username: str, password: str, max_retries: int = 3, retry_delay: int = 1):
        """Initialize the UDMAPI."""
        self.host = host
        self.username = username
        self.password = password
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Session management
        self._session: Optional[aiohttp.ClientSession] = None
        self._login_lock = asyncio.Lock()
        self._session_timeout = timedelta(minutes=30)
        self._last_login: Optional[datetime] = None
        self._last_successful_request: Optional[datetime] = None
        
        # Authentication state
        self._device_token: Optional[str] = None
        self._csrf_token: Optional[str] = None
        self._cookies: Dict[str, str] = {}
        
        # Rate limiting
        self._request_lock = asyncio.Lock()
        self._last_request_time: Optional[datetime] = None
        self._min_request_interval = 2.0

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
                _LOGGER.debug(f"Rate limiting: waiting {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
        self._last_request_time = datetime.now()

    def _parse_token_cookie(self, cookie_str: str) -> Optional[str]:
        """Parse TOKEN value from Set-Cookie header."""
        try:
            parts = cookie_str.split(';')[0].split('=')
            if len(parts) == 2 and parts[0].strip().upper() == 'TOKEN':
                return parts[1].strip()
        except Exception as e:
            _LOGGER.error(f"Failed to parse token cookie: {e}")
        return None

    def _is_session_expired(self) -> bool:
        """Check if the current session has expired."""
        now = datetime.now()

        # Ensure at least one form of authentication exists
        if not self._cookies.get("TOKEN"):
            _LOGGER.debug("Session expired: Missing authentication cookie")
            return True

        # Extend session lifespan check
        if self._last_login and (now - self._last_login) > timedelta(minutes=30):
            _LOGGER.debug("Session expired: Timed out")
            return True

        _LOGGER.debug("Session is valid")
        return False


    def _get_base_headers(self) -> Dict[str, str]:
        """Get base headers for requests."""
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        if self._device_token:
            headers['Authorization'] = f'Bearer {self._device_token}'
        return headers

    def _get_proxy_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-CSRF-Token": self._csrf_token or "", 
        }

        if "TOKEN" in self._cookies:
            headers["Cookie"] = f"TOKEN={self._cookies['TOKEN']}"

        _LOGGER.debug(f"Using headers: {headers}")
        return headers


    async def authenticate_session(self) -> Tuple[bool, Optional[str]]:
        """Authenticate and get session token."""
        url = f"https://{self.host}/api/auth/login"
        data = {
            "username": self.username,
            "password": self.password,
            "rememberMe": True
        }

        try:
            session = await self._get_session()
            async with session.post(url, json=data, timeout=ClientTimeout(total=30)) as response:
                _LOGGER.debug(f"Auth response status: {response.status}")
                
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
                        self._cookies['TOKEN'] = token
                        token_found = True
                        break
                
                if not token_found:
                    return False, "No TOKEN cookie in response"
                
                _LOGGER.debug("Authentication successful")
                return True, None
                
        except asyncio.TimeoutError:
            return False, "Authentication request timed out"
        except Exception as e:
            _LOGGER.error(f"Authentication error: {str(e)}", exc_info=True)
            return False, str(e)

    async def ensure_authenticated(self) -> Tuple[bool, Optional[str]]:
        """Ensure we have a valid authentication session."""
        async with self._login_lock:
            if self._is_session_expired():
                _LOGGER.debug("Session expired, but checking for valid authentication cookie.")

                # If we have a valid TOKEN cookie, assume session is still valid
                if self._cookies.get("TOKEN"):
                    _LOGGER.debug("Session cookie is present, skipping re-authentication.")
                    return True, None

                # If no valid session, attempt re-authentication
                _LOGGER.debug("No valid session cookie, performing re-authentication.")
                success, error = await self.authenticate_session()
                return success, error
            return True, None

    async def _make_authenticated_request(self, method: str, url: str, json_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any, Optional[str]]:
        """Make an authenticated request with correct headers."""
        async with self._request_lock:
            await self._wait_for_next_request()

            for attempt in range(self.max_retries):
                try:
                    if self._is_session_expired():
                        _LOGGER.debug("Session expired, attempting reauth")
                        success, error = await self.authenticate_session()
                        if not success:
                            return False, None, f"Authentication failed: {error}"

                    session = await self._get_session()
                    headers = self._get_proxy_headers()

                    async with session.request(method, url, headers=headers, json=json_data) as response:
                        response_text = await response.text()

                        if response.status == 200:
                            self._last_successful_request = datetime.now()
                            return True, json.loads(response_text), None

                        if response.status in [401, 403]:
                            _LOGGER.warning(f"Received {response.status}: {response_text}")
                            _LOGGER.warning(f"CSRF token before re-auth: {self._csrf_token}")

                            if attempt < self.max_retries - 1:
                                await asyncio.sleep(self.retry_delay)
                                continue

                        return False, None, f"Request failed: {response.status}, {response_text}"

                except Exception as e:
                    _LOGGER.error(f"Request error: {str(e)}")
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
            
        url = f"https://{self.host}/proxy/network/v2/api/site/default/firewall-policies"
        return await self._make_authenticated_request('get', url)

    async def get_traffic_routes(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch all traffic routes from the UDM."""
        auth_success, auth_error = await self.ensure_authenticated()
        if not auth_success:
            return False, None, f"Authentication failed: {auth_error}"
            
        url = f"https://{self.host}/proxy/network/v2/api/site/default/trafficroutes"
        return await self._make_authenticated_request('get', url)

    async def toggle_firewall_policy(self, policy_id: str, enabled: bool):
        """Toggle a firewall policy on or off."""
        url = f"https://{self.host}/proxy/network/v2/api/site/default/firewall-policies/batch"
        payload = [{"_id": policy_id, "enabled": enabled}]

        _LOGGER.info("Sending firewall policy toggle request: %s", payload)

        success, response, error = await self._make_authenticated_request('put', url, payload)
        _LOGGER.info("PUT response - Success: %s, Response: %s, Error: %s", success, response, error)

        if not success:
            _LOGGER.error("Failed to toggle firewall policy %s: %s", policy_id, error)
            if response:
                _LOGGER.error("Response content: %s", await response.text())
            return False, error

        _LOGGER.info("Toggled firewall policy %s to %s successfully", policy_id, enabled)
        return True, None

    async def toggle_traffic_route(self, route_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a traffic route."""
        # First get all traffic routes
        all_routes_url = f"https://{self.host}/proxy/network/v2/api/site/default/trafficroutes"
        _LOGGER.info("Fetching all routes from URL: %s", all_routes_url)
        success, all_routes, error = await self._make_authenticated_request('get', all_routes_url)
        _LOGGER.info("GET all routes response - Success: %s, Total Routes: %s, Error: %s", 
                    success, len(all_routes) if all_routes else 0, error)
        
        if not success or not all_routes:
            _LOGGER.error("Failed to fetch all routes: %s", error)
            return False, f"Failed to fetch all routes: {error}"

        # Find our specific route
        route = next((r for r in all_routes if r.get('_id') == route_id), None)
        if not route:
            _LOGGER.error("Route ID %s not found in routes list", route_id)
            return False, f"Route ID {route_id} not found"

        # Create updated route with new enabled state
        updated_route = dict(route)
        updated_route['enabled'] = enabled
        
        # PUT the update back
        update_url = f"{all_routes_url}/{route_id}"
        _LOGGER.info("Sending PUT request to %s with route: %s", update_url, updated_route)
        success, response, error = await self._make_authenticated_request('put', update_url, updated_route)
        _LOGGER.info("PUT response - Success: %s, Response: %s, Error: %s", success, response, error)
        
        if success:
            _LOGGER.info(f"Toggled traffic route {route_id} to {'on' if enabled else 'off'}")
            return True, None
            
        return False, f"Failed to update route: {error}"
    
    async def get_firewall_zone_matrix(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch firewall zone matrix from the UDM."""
        auth_success, auth_error = await self.ensure_authenticated()
        if not auth_success:
            return False, None, f"Authentication failed: {auth_error}"
            
        url = f"https://{self.host}/proxy/network/v2/api/site/default/firewall/zone-matrix"
        return await self._make_authenticated_request('get', url)

    async def cleanup(self):
        """Cleanup resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None