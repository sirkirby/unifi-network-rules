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
            timeout = ClientTimeout(total=30, connect=10)
            cookie_jar = CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                cookie_jar=cookie_jar,
                connector=aiohttp.TCPConnector(ssl=False)
            )
        return self._session

    def _is_session_expired(self) -> bool:
        """Check if the current session has expired."""
        return (not self._last_login or 
                not self._device_token or 
                datetime.now() - self._last_login > self._session_timeout)

    async def _wait_for_next_request(self) -> None:
        """Wait for the appropriate interval between requests."""
        if self._last_request_time:
            elapsed = datetime.now() - self._last_request_time
            if elapsed.total_seconds() < self._min_request_interval:
                await asyncio.sleep(self._min_request_interval - elapsed.total_seconds())
        self._last_request_time = datetime.now()

    def _parse_token_cookie(self, cookie_str: str) -> Optional[str]:
        """Parse TOKEN value from Set-Cookie header."""
        try:
            # Extract token value from cookie string
            parts = cookie_str.split(';')[0].split('=')
            if len(parts) == 2 and parts[0] == 'TOKEN':
                return parts[1]
        except Exception as e:
            _LOGGER.error(f"Failed to parse token cookie: {e}")
        return None

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
            async with session.post(url, json=data) as response:
                _LOGGER.debug(f"Auth response status: {response.status}")
                _LOGGER.debug(f"Auth response headers: {response.headers}")
                
                if response.status != 200:
                    return False, f"Authentication failed: {response.status}"
                
                response_data = await response.json()
                
                # Get device token from response
                self._device_token = response_data.get('deviceToken')
                if not self._device_token:
                    return False, "No device token in response"
                
                # Get CSRF token from headers
                self._csrf_token = response.headers.get('x-csrf-token')
                if not self._csrf_token:
                    _LOGGER.debug("No CSRF token in x-csrf-token header, trying x-updated-csrf-token")
                    self._csrf_token = response.headers.get('x-updated-csrf-token')
                
                if not self._csrf_token:
                    return False, "No CSRF token in response headers"
                
                # Parse TOKEN from Set-Cookie header
                token_cookies = response.headers.getall('Set-Cookie', [])
                _LOGGER.debug(f"Token cookies: {token_cookies}")
                
                for cookie_str in token_cookies:
                    token = self._parse_token_cookie(cookie_str)
                    if token:
                        self._cookies['TOKEN'] = token
                        _LOGGER.debug(f"Got TOKEN cookie: {token[:20]}...")
                        break
                
                if not self._cookies.get('TOKEN'):
                    return False, "No TOKEN cookie in response"
                
                _LOGGER.debug(f"Authentication successful - DeviceToken: {bool(self._device_token)}, "
                            f"CSRF: {self._csrf_token}, TOKEN cookie length: {len(self._cookies.get('TOKEN', ''))}")
                
                return True, None
                
        except Exception as e:
            _LOGGER.error(f"Authentication error: {str(e)}", exc_info=True)
            return False, str(e)

    async def _get_csrf_token(self) -> Tuple[bool, Optional[str]]:
        """Get CSRF token for proxy endpoints."""
        url = f"https://{self.host}/api/auth/csrf"
        headers = self._get_base_headers()
        
        try:
            session = await self._get_session()
            async with session.get(url, headers=headers, cookies=self._cookies) as response:
                _LOGGER.debug(f"CSRF response status: {response.status}")
                _LOGGER.debug(f"CSRF response headers: {response.headers}")
                
                if response.status != 200:
                    error_text = await response.text()
                    return False, f"Failed to get CSRF token: {response.status}, {error_text}"
                
                self._csrf_token = response.headers.get('x-csrf-token')
                if not self._csrf_token:
                    return False, "No CSRF token in response headers"
                
                _LOGGER.debug(f"Got CSRF token: {self._csrf_token}")
                return True, None
                
        except Exception as e:
            return False, f"CSRF token error: {str(e)}"

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
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        if self._device_token:
            headers['Authorization'] = f'Bearer {self._device_token}'
        
        if self._csrf_token:
            headers['x-csrf-token'] = self._csrf_token
        
        _LOGGER.debug(f"Using headers: {headers}")
        return headers

    async def login(self) -> Tuple[bool, Optional[str]]:
        """Log in to the UDM."""
        async with self._login_lock:
            if not self._is_session_expired():
                return True, None

            await self._wait_for_next_request()

            # Authenticate and get all tokens in one request
            auth_success, auth_error = await self._authenticate_session()
            if not auth_success:
                return False, auth_error

            self._last_login = datetime.now()
            _LOGGER.info("Successfully logged in to UDM")
            _LOGGER.debug(f"Login state - Token: {bool(self._device_token)}, "
                         f"CSRF: {bool(self._csrf_token)}, "
                         f"Cookies: {self._cookies}")
            return True, None

    async def quick_auth_check(self) -> Tuple[bool, Optional[str]]:
        """Perform a quick authentication check."""
        try:
            # First try to login
            login_success, login_error = await self.login()
            if not login_success:
                _LOGGER.error(f"Quick auth check - login failed: {login_error}")
                return False, login_error

            # Verify we have all required auth components
            if not self._device_token or not self._csrf_token or not self._cookies:
                _LOGGER.error("Quick auth check - missing required auth components")
                return False, "Incomplete authentication state"

            _LOGGER.info("Quick auth check successful")
            _LOGGER.debug(f"Auth state: Token: {self._device_token is not None}, " 
                         f"CSRF: {self._csrf_token is not None}, "
                         f"Cookie count: {len(self._cookies)}")
            return True, None
            
        except Exception as e:
            _LOGGER.error(f"Quick auth check failed: {str(e)}")
            return False, str(e)

    async def _make_authenticated_request(
        self, 
        method: str, 
        url: str, 
        json_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Any, Optional[str]]:
        """Make an authenticated request."""
        async with self._request_lock:
            await self._wait_for_next_request()

            for attempt in range(self.max_retries):
                try:
                    if self._is_session_expired():
                        success, error = await self.login()
                        if not success:
                            return False, None, f"Authentication failed: {error}"

                    session = await self._get_session()
                    headers = self._get_proxy_headers()
                    cookies = {'TOKEN': self._cookies.get('TOKEN', '')}
                    
                    _LOGGER.debug(f"Making {method} request to {url}")
                    _LOGGER.debug(f"Request headers: {headers}")
                    _LOGGER.debug(f"Request cookies: {cookies}")
                    
                    async with session.request(
                        method, 
                        url, 
                        headers=headers,
                        cookies=cookies,
                        json=json_data
                    ) as response:
                        _LOGGER.debug(f"Response status: {response.status}")
                        _LOGGER.debug(f"Response headers: {response.headers}")
                        response_text = await response.text()
                        
                        if response.status == 200:
                            return True, json.loads(response_text), None
                        
                        _LOGGER.debug(f"Error response body: {response_text}")
                        
                        if response.status == 429:
                            await asyncio.sleep(self._min_request_interval * (2 ** attempt))
                            continue
                        
                        if response.status == 401:
                            _LOGGER.debug("Got 401, clearing session state")
                            self._device_token = None
                            self._csrf_token = None
                            self._cookies = {}
                            self._last_login = None
                            
                            if attempt < self.max_retries - 1:
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
        url = f"https://{self.host}/proxy/network/v2/api/site/default/firewall-policies"
        return await self._make_authenticated_request('get', url)

    async def get_traffic_routes(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch traffic routes from the UDM."""
        url = f"https://{self.host}/proxy/network/v2/api/site/default/trafficroutes"
        return await self._make_authenticated_request('get', url)

    async def toggle_firewall_policy(self, policy_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a firewall policy."""
        url = f"https://{self.host}/proxy/network/v2/api/site/default/firewall-policies/{policy_id}"
        success, policy, error = await self._make_authenticated_request('get', url)
        
        if not success:
            return False, f"Failed to fetch policy: {error}"

        policy['enabled'] = enabled
        success, _, error = await self._make_authenticated_request('put', url, policy)
        
        if success:
            _LOGGER.info(f"Toggled firewall policy {policy_id} to {'on' if enabled else 'off'}")
            return True, None
        return False, f"Failed to update policy: {error}"

    async def toggle_traffic_route(self, route_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a traffic route."""
        url = f"https://{self.host}/proxy/network/v2/api/site/default/trafficroutes/{route_id}"
        success, route, error = await self._make_authenticated_request('get', url)
        
        if not success:
            return False, f"Failed to fetch route: {error}"

        route['enabled'] = enabled
        success, _, error = await self._make_authenticated_request('put', url, route)
        
        if success:
            _LOGGER.info(f"Toggled traffic route {route_id} to {'on' if enabled else 'off'}")
            return True, None
        return False, f"Failed to update route: {error}"

    async def cleanup(self):
        """Cleanup resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None