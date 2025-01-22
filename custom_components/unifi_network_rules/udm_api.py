import aiohttp
import asyncio
import logging
import json
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from aiohttp import ClientTimeout

_LOGGER = logging.getLogger(__name__)

class UDMAPI:
    def __init__(self, host, username, password, max_retries=3, retry_delay=1):
        self.host = host
        self.username = username
        self.password = password
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.cookies = None
        self.csrf_token = None
        self.device_token = None  # Added for UniFi OS 9.x auth
        self.last_login = None
        self.session_timeout = timedelta(minutes=30)
        self._login_lock = asyncio.Lock()
        self._session = None
        self._last_request_time = None
        self._min_request_interval = 0.5

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _rate_limit(self):
        """Implement rate limiting between requests."""
        if self._last_request_time is not None:
            elapsed = datetime.now() - self._last_request_time
            if elapsed.total_seconds() < self._min_request_interval:
                await asyncio.sleep(self._min_request_interval - elapsed.total_seconds())
        self._last_request_time = datetime.now()

    def _is_session_expired(self):
        """Check if the current session has expired."""
        if not self.last_login:
            return True
        return datetime.now() - self.last_login > self.session_timeout

    async def ensure_logged_in(self) -> bool:
        """Ensure the API is logged in, refreshing the session if necessary."""
        if not self.device_token or self._is_session_expired():
            success, error = await self.login()
            if not success:
                _LOGGER.error(f"Failed to log in: {error}")
                return False
        return True

    async def login(self):
        """Log in to the UDM with UniFi OS 9.x compatible authentication."""
        async with self._login_lock:
            if not self._is_session_expired() and self.device_token:
                return True, None

            await self._rate_limit()
            
            url = f"https://{self.host}/api/auth/login"
            data = {"username": self.username, "password": self.password}
            
            try:
                session = await self._get_session()
                _LOGGER.debug(f"Attempting login to {url}")
                
                async with session.post(url, json=data, ssl=False) as response:
                    response_text = await response.text()
                    _LOGGER.debug(f"Login response status: {response.status}")
                    _LOGGER.debug(f"Login response headers: {dict(response.headers)}")
                    
                    if response.status == 200:
                        try:
                            response_data = json.loads(response_text)
                            self.device_token = response_data.get('deviceToken')
                            if not self.device_token:
                                _LOGGER.error("Login succeeded but no deviceToken in response")
                                return False, "No deviceToken in response"
                            
                            _LOGGER.debug(f"Successfully obtained deviceToken")
                            
                            # Store cookies if needed
                            self.cookies = {cookie.key: cookie.value for cookie in response.cookies.values()}
                            
                            # Store CSRF token if provided
                            self.csrf_token = response.headers.get('x-csrf-token')
                            
                            self.last_login = datetime.now()
                            _LOGGER.info("Successfully logged in to UDM")
                            return True, None
                            
                        except json.JSONDecodeError:
                            _LOGGER.error(f"Failed to parse login response: {response_text}")
                            return False, "Invalid login response format"
                            
                    elif response.status == 429:
                        error_message = "Rate limit exceeded. Waiting before retry."
                        _LOGGER.warning(error_message)
                        await asyncio.sleep(5)
                        return False, error_message
                    else:
                        error_message = f"Login failed with status {response.status}"
                        _LOGGER.error(f"{error_message}: {response_text}")
                        return False, error_message
                        
            except aiohttp.ClientError as e:
                error_message = f"Connection error during login: {str(e)}"
                _LOGGER.error(error_message)
                return False, error_message
            except Exception as e:
                error_message = f"Unexpected error during login: {str(e)}"
                _LOGGER.exception(error_message)
                return False, error_message

    async def _make_authenticated_request(self, method: str, url: str, headers: Dict[str, str], json_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any, Optional[str]]:
        """Make an authenticated request with UniFi OS 9.x authentication."""
        await self._rate_limit()

        for attempt in range(self.max_retries):
            if not await self.ensure_logged_in():
                _LOGGER.error(f"Failed to ensure logged in state before {method} request to {url}")
                return False, None, "Failed to login"
                
            _LOGGER.debug(f"Making {method} request to {url} (attempt {attempt + 1}/{self.max_retries})")
            
            # Add authentication headers
            headers['Authorization'] = f'Bearer {self.device_token}'
            if self.csrf_token:
                headers['x-csrf-token'] = self.csrf_token
            
            if json_data:
                headers['Content-Type'] = 'application/json'
                
            session = await self._get_session()
            
            try:
                _LOGGER.debug(f"Request headers: {headers}")
                
                async with getattr(session, method)(url, headers=headers, json=json_data, cookies=self.cookies, ssl=False) as response:
                    if response.status == 200:
                        return True, await response.json(), None
                    elif response.status == 401:
                        _LOGGER.warning(f"Authentication failed (attempt {attempt + 1})")
                        # Clear tokens to force new login
                        self.device_token = None
                        self.csrf_token = None
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay)
                            continue
                    elif response.status == 429:
                        _LOGGER.warning("Rate limit hit, waiting before retry")
                        await asyncio.sleep(5)
                        continue
                    
                    error_text = await response.text()
                    error_message = f"Request failed. Status: {response.status}, Response: {error_text}"
                    _LOGGER.error(error_message)
                    return False, None, error_message

            except aiohttp.ClientError as e:
                error_message = f"Connection error: {str(e)}"
                _LOGGER.error(error_message)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    continue
                return False, None, error_message
            except Exception as e:
                error_message = f"Unexpected error: {str(e)}"
                _LOGGER.exception(error_message)
                return False, None, error_message

        return False, None, "Max retries reached"

    async def get_traffic_routes(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch traffic routes from the UDM."""
        url = f"https://{self.host}/proxy/network/v2/api/site/default/trafficroutes"
        headers = {'Accept': 'application/json'}
        
        success, data, error = await self._make_authenticated_request('get', url, headers)
        if success:
            _LOGGER.debug("Successfully fetched traffic routes")
            return True, data, None
        else:
            _LOGGER.error(f"Failed to fetch traffic routes: {error}")
            return False, None, error

    async def toggle_traffic_route(self, route_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a traffic route on or off."""
        url = f"https://{self.host}/proxy/network/v2/api/site/default/trafficroutes/{route_id}"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        # First get all routes and find the one we want to modify
        success, routes, error = await self.get_traffic_routes()
        if not success:
            return False, f"Failed to fetch routes: {error}"

        route_data = next((route for route in routes if route['_id'] == route_id), None)
        if not route_data:
            return False, f"Route with id {route_id} not found"

        # Update the 'enabled' field
        route_data['enabled'] = enabled

        # Send the PUT request with the updated data
        success, _, error = await self._make_authenticated_request('put', url, headers, route_data)
        if success:
            _LOGGER.info(f"Successfully toggled traffic route {route_id} to {'on' if enabled else 'off'}")
            return True, None
        else:
            _LOGGER.error(f"Failed to toggle traffic route {route_id}: {error}")
            return False, f"Failed to toggle route: {error}"
    
    async def get_firewall_policies(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch all firewall policies from the UDM."""
        url = f"https://{self.host}/proxy/network/v2/api/site/default/firewall-policies"
        headers = {'Accept': 'application/json'}
        
        success, data, error = await self._make_authenticated_request('get', url, headers)
        if success:
            _LOGGER.debug("Successfully fetched firewall policies")
            return True, data, None
        else:
            _LOGGER.error(f"Failed to fetch firewall policies: {error}")
            return False, None, error

    async def get_firewall_policy(self, policy_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Fetch a single firewall policy from the UDM."""
        url = f"https://{self.host}/proxy/network/v2/api/site/default/firewall-policies/{policy_id}"
        headers = {'Accept': 'application/json'}
        
        success, data, error = await self._make_authenticated_request('get', url, headers)
        if success:
            return True, data, None
        else:
            _LOGGER.error(f"Failed to fetch firewall policy {policy_id}: {error}")
            return False, None, error

    async def toggle_firewall_policy(self, policy_id: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        """Toggle a firewall policy on or off."""
        success, policy, error = await self.get_firewall_policy(policy_id)
        if not success:
            return False, f"Failed to fetch policy: {error}"

        policy['enabled'] = enabled

        url = f"https://{self.host}/proxy/network/v2/api/site/default/firewall-policies/{policy_id}"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        success, _, error = await self._make_authenticated_request('put', url, headers, policy)
        if success:
            _LOGGER.info(f"Successfully toggled firewall policy {policy_id} to {'on' if enabled else 'off'}")
            return True, None
        else:
            return False, f"Failed to toggle policy: {error}"

    async def cleanup(self):
        """Cleanup the API session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None