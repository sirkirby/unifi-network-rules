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
        self._session_timeout = timedelta(minutes=15)
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
        
        if not self._last_login or not self._device_token or not self._csrf_token:
            _LOGGER.debug("Session expired: Missing basic authentication components")
            return True
            
        if now - self._last_login > self._session_timeout:
            _LOGGER.debug("Session expired: Exceeded session timeout")
            return True
            
        if self._last_successful_request and now - self._last_successful_request > timedelta(minutes=10):
            _LOGGER.debug("Session expired: Inactivity timeout")
            return True
            
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
        """Get headers for proxy endpoints."""
        headers = self._get_base_headers()
        if self._csrf_token:
            headers['x-csrf-token'] = self._csrf_token
        return headers

    async def _authenticate_session(self) -> Tuple[bool, Optional[str]]:
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
                _LOGGER.debug("Session expired or invalid, performing fresh login")
                return await self.login()
            
            if self._last_successful_request:
                time_since_success = datetime.now() - self._last_successful_request
                if time_since_success > timedelta(seconds=30):
                    _LOGGER.debug("Last successful request too old, performing fresh login")
                    return await self.login()
            
            return True, None

    async def login(self) -> Tuple[bool, Optional[str]]:
        """Log in to the UDM."""
        async with self._login_lock:
            if not self._is_session_expired():
                return True, None

            await self._wait_for_next_request()
            success, error = await self._authenticate_session()
            
            if success:
                self._last_login = datetime.now()
                self._last_successful_request = datetime.now()
                _LOGGER.info("Successfully logged in to UDM")
            else:
                _LOGGER.error(f"Login failed: {error}")
            
            return success, error

    async def _make_authenticated_request(
        self, 
        method: str, 
        url: str, 
        json_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Any, Optional[str]]:
        """Make an authenticated request with improved session handling."""
        async with self._request_lock:
            await self._wait_for_next_request()

            for attempt in range(self.max_retries):
                try:
                    if attempt == 0 and self._is_session_expired():
                        _LOGGER.debug("Session expired, attempting reauth")
                        success, error = await self.login()
                        if not success:
                            return False, None, f"Authentication failed: {error}"
                    elif attempt > 0:
                        _LOGGER.debug(f"Retry attempt {attempt}, forcing reauth")
                        success, error = await self.login()
                        if not success:
                            return False, None, f"Authentication failed on retry: {error}"

                    session = await self._get_session()
                    headers = self._get_proxy_headers()
                    cookies = {'TOKEN': self._cookies.get('TOKEN', '')}
                    
                    async with session.request(
                        method, 
                        url, 
                        headers=headers,
                        cookies=cookies,
                        json=json_data,
                        timeout=ClientTimeout(total=30)
                    ) as response:
                        response_text = await response.text()
                        
                        if response.status == 200:
                            self._last_successful_request = datetime.now()
                            try:
                                return True, json.loads(response_text), None
                            except json.JSONDecodeError as e:
                                return False, None, f"Invalid JSON response: {str(e)}"
                        
                        if response.status in [401, 403]:
                            _LOGGER.debug(f"Got {response.status}, clearing session state")
                            self._device_token = None
                            self._csrf_token = None
                            self._cookies = {}
                            self._last_login = None
                            self._last_successful_request = None
                            
                            if attempt < self.max_retries - 1:
                                await asyncio.sleep(self.retry_delay * (attempt + 1))
                                continue
                        
                        return False, None, f"Request failed: {response.status}, {response_text}"

                except asyncio.TimeoutError:
                    _LOGGER.error(f"Request timeout on attempt {attempt + 1}")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                        continue
                    return False, None, "Request timeout after all retries"
                except Exception as e:
                    _LOGGER.error(f"Request error on attempt {attempt + 1}: {str(e)}")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
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

    async def get_firewall_policy(self, policy_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Fetch a specific firewall policy from the UDM."""
        auth_success, auth_error = await self.ensure_authenticated()
        if not auth_success:
            return False, None, f"Authentication failed: {auth_error}"
            
        url = f"https://{self.host}/proxy/network/v2/api/site/default/firewall-policies/{policy_id}"
        return await self._make_authenticated_request('get', url)

    async def toggle_firewall_policy(self, policy_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a firewall policy."""
        url = f"https://{self.host}/proxy/network/v2/api/site/default/firewall-policies/{policy_id}"
        _LOGGER.info("Fetching current policy state from URL: %s", url)
        success, policy, error = await self._make_authenticated_request('get', url)
        _LOGGER.info("GET response - Success: %s, Policy: %s, Error: %s", success, policy, error)
        
        if not success or not policy:
            return False, f"Failed to fetch policy: {error}"

        policy['enabled'] = enabled
        _LOGGER.info("Sending PUT request with policy: %s", policy)
        success, response, error = await self._make_authenticated_request('put', url, policy)
        _LOGGER.info("PUT response - Success: %s, Response: %s, Error: %s", success, response, error)
        
        if success:
            _LOGGER.info(f"Toggled firewall policy {policy_id} to {'on' if enabled else 'off'}")
            return True, None
        return False, f"Failed to update policy: {error}"

    async def get_traffic_routes(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch all traffic routes from the UDM."""
        auth_success, auth_error = await self.ensure_authenticated()
        if not auth_success:
            return False, None, f"Authentication failed: {auth_error}"
            
        url = f"https://{self.host}/proxy/network/v2/api/site/default/trafficroutes"
        return await self._make_authenticated_request('get', url)

    async def toggle_traffic_route(self, route_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a traffic route.

        Note: The UDM API doesn't support getting individual traffic routes.
        We must get all routes, find the target route, modify it, and PUT it back.
        """
        # Get all routes first
        success, routes, error = await self.get_traffic_routes()
        if not success or not routes:
            return False, f"Failed to fetch routes: {error}"

        # Find our target route
        route = next((r for r in routes if r.get('_id') == route_id), None)
        if not route:
            return False, f"Route with id {route_id} not found"

        # Update only the enabled status
        route['enabled'] = enabled

        # PUT the updated route back
        url = f"https://{self.host}/proxy/network/v2/api/site/default/trafficroutes/{route_id}"
        _LOGGER.info("Sending PUT request to %s with route: %s", url, route)
        success, response, error = await self._make_authenticated_request('put', url, route)
        _LOGGER.info("PUT response - Success: %s, Response: %s, Error: %s", success, response, error)

        if success:
            _LOGGER.info(f"Toggled traffic route {route_id} to {'on' if enabled else 'off'}")
            return True, None

        return False, f"Failed to update route: {error}"

    async def cleanup(self):
        """Cleanup resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None