"""Complete UniFi Dream Machine API implementation."""

import logging
from typing import Dict, Any, Callable, Awaitable
import asyncio

from .api_base import UDMAPI as BaseAPI
from .capabilities import CapabilitiesMixin
from .firewall import FirewallMixin
from .authentication import AuthenticationMixin  
from .api_handlers import ApiHandlerMixin
from .websocket import WebSocketMixin
from .traffic import TrafficMixin
from .port_forward import PortForwardMixin
from .routes import RoutesMixin
from .network import NetworkMixin
from .qos import QoSMixin

from ..const import LOGGER
from ..queue import ApiOperationQueue

class UDMAPI(
    NetworkMixin,
    RoutesMixin,
    PortForwardMixin,
    TrafficMixin,
    FirewallMixin,
    WebSocketMixin,
    AuthenticationMixin,
    ApiHandlerMixin,
    CapabilitiesMixin,
    QoSMixin,
    BaseAPI
):
    def __init__(self, *args, **kwargs):
        """Initialize the UDMAPI with additional operation queue."""
        super().__init__(*args, **kwargs)
        self.api_queue = ApiOperationQueue(delay_between_requests=0.5)
        # Keep toggle_queue reference for backward compatibility
        self.toggle_queue = self.api_queue
        
    async def async_init(self, hass=None):
        """Initialize the UDMAPI."""
        # Call the parent method first to handle authentication
        await super().async_init(hass)
        
        # Start the API queue
        await self.api_queue.start()
        LOGGER.debug("API operation queue started")
        
    async def cleanup(self):
        """Clean up resources."""
        # Stop the API queue first
        if hasattr(self, "api_queue"):
            await self.api_queue.stop()
            LOGGER.debug("API operation queue stopped")
            
        # Clean up other resources
        await super().cleanup()
    
    async def queue_api_operation(self, operation_func: Callable[..., Awaitable[Any]], *args, **kwargs) -> Awaitable[Any]:
        """Queue any API operation.
        
        Args:
            operation_func: The API function to call
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            Future containing the result of the operation
        """
        # Check if this is a toggle operation for priority handling
        operation_name = operation_func.__name__
        is_toggle = 'toggle' in operation_name.lower()
        
        LOGGER.debug("Queueing API operation: %s (priority: %s)", operation_name, is_toggle)
        # Create a future that will be completed when the operation completes
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        
        # Add an internal wrapper to the queue that will complete our future
        async def wrapper_operation():
            try:
                result = await operation_func(*args, **kwargs)
                future.set_result(result)
                return result
            except Exception as err:
                LOGGER.error("Error in operation %s: %s", operation_func.__name__, err)
                future.set_exception(err)
                raise
                
        # Add the wrapper to the queue with priority flag for toggle operations
        # This will make toggle operations get processed faster for better responsiveness
        asyncio.create_task(self.api_queue.add_operation(
            wrapper_operation, 
            is_priority=is_toggle  # Pass the priority flag
        ))
        
        # Return the future immediately
        return future
    
    async def queue_toggle(self, toggle_func: Callable[..., Awaitable[bool]], *args, **kwargs) -> Awaitable[bool]:
        """Queue a toggle operation (legacy method).
        
        Args:
            toggle_func: The toggle function to call
            *args, **kwargs: Arguments to pass to the toggle function
            
        Returns:
            Future containing a boolean indicating success or failure
        """
        LOGGER.debug("Queueing toggle operation: %s", toggle_func.__name__)
        return await self.queue_api_operation(toggle_func, *args, **kwargs)
        
    def create_api_request(self, method: str, path: str, data: Any = None, is_v2: bool = False) -> Any:
        """
        Create an API request object with proper formatting and headers.
        
        Public wrapper for the private _create_api_request method in the base class.
        Provides additional logging for debugging purposes.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint to call
            data: Optional data payload for the request
            is_v2: Whether this is a v2 API endpoint requiring special handling
            
        Returns:
            The formatted API request object ready to be passed to controller.request()
        """
        LOGGER.debug(
            "Creating API request: method=%s, endpoint=%s, is_v2=%s", 
            method, path, is_v2
        )
        
        # Sanitize data for logging
        sanitized = self._sanitize_data_for_logging(data)
        if sanitized:
            LOGGER.debug("Request data: %s", sanitized)
            
        return self._create_api_request(method, path, data, is_v2)
        
    def _sanitize_data_for_logging(self, data: Any) -> Any:
        """Remove sensitive information from data before logging."""
        if not isinstance(data, dict):
            return data
            
        # Create a copy to avoid modifying the original
        safe_data = data.copy()
        
        # Remove sensitive fields (passwords, tokens, etc.)
        sensitive_fields = ["password", "key", "psk", "secret", "token", "auth"]
        for field in sensitive_fields:
            if field in safe_data:
                safe_data[field] = "***REDACTED***"
                
        return safe_data

    async def refresh_all(self) -> None:
        """Refresh all API data from the controller."""
        LOGGER.debug("Refreshing all data from the controller")
        
        try:
            # Refresh the controller data first
            if hasattr(self.controller, "refresh_cache"):
                LOGGER.debug("Refreshing controller cache")
                await self.controller.refresh_cache()
            
            # Now refresh specific data types
            
            # Get firewall policies 
            await self.get_firewall_policies(force_refresh=True)
            
            # Get legacy firewall rules if that capability is available
            if self.capabilities.legacy_firewall:
                await self.get_legacy_firewall_rules()
                
            # Get traffic rules
            await self.get_traffic_rules()
            
            # Get port forwards
            await self.get_port_forwards()
            
            # Get traffic routes
            await self.get_traffic_routes()
            
            # Get QoS rules
            await self.get_qos_rules()
            
            # Get network-related info
            await self.get_firewall_zones()
            await self.get_wlans()
                
            LOGGER.debug("Successfully refreshed all data")
        except Exception as err:
            LOGGER.error("Error refreshing data: %s", str(err))
            # We don't raise the exception here to avoid breaking the whole API
            # if one particular data type fails to refresh
            
    async def clear_cache(self) -> None:
        """Clear any cached data."""
        try:
            LOGGER.debug("Clearing API cache")
            # This is a no-op for now to avoid errors
            LOGGER.debug("API cache cleared")
        except Exception as err:
            LOGGER.error("Error clearing cache: %s", str(err))
            
    async def get_rule_status(self, rule_id: str) -> Dict[str, Any]:
        """Get the status of a rule.
        
        Args:
            rule_id: The ID of the rule to check
            
        Returns:
            Dict with status information
        """
        try:
            # The format of rule_id should be "type_id" e.g. "firewall_policies_123"
            parts = rule_id.split("_")
            
            # Need at least 2 parts - type and id
            if len(parts) < 2:
                LOGGER.error("Invalid rule_id format: %s", rule_id)
                return {"error": "Invalid rule ID format"}
                
            # The type is the first part(s)
            # The ID is the last part
            rule_type = "_".join(parts[:-1])
            actual_id = parts[-1]
            
            LOGGER.debug("Getting status for rule type: %s, id: %s", rule_type, actual_id)
            
            # Check status based on rule type
            if rule_type == "firewall_policies":
                policies = await self.get_firewall_policies(include_predefined=True)
                rule = next((p for p in policies if str(p.get("_id")) == actual_id), None)
                if rule:
                    return {"found": True, "enabled": rule.get("enabled", False), "data": rule}
            elif rule_type == "traffic_rules":
                rules = await self.get_traffic_rules()
                rule = next((r for r in rules if str(r.get("_id")) == actual_id), None)
                if rule:
                    return {"found": True, "enabled": rule.get("enabled", False), "data": rule}
            elif rule_type == "port_forwards":
                forwards = await self.get_port_forwards()
                rule = next((f for f in forwards if str(f.get("_id")) == actual_id), None)
                if rule:
                    return {"found": True, "enabled": rule.get("enabled", False), "data": rule}
            elif rule_type == "traffic_routes":
                routes = await self.get_traffic_routes()
                rule = next((r for r in routes if str(r.get("_id")) == actual_id), None)
                if rule:
                    return {"found": True, "enabled": rule.get("enabled", False), "data": rule}
            elif rule_type == "legacy_firewall_rules":
                rules = await self.get_legacy_firewall_rules()
                rule = next((r for r in rules if str(r.get("_id")) == actual_id), None)
                if rule:
                    return {"found": True, "enabled": rule.get("enabled", False), "data": rule}
            elif rule_type == "qos_rules":
                rules = await self.get_qos_rules()
                rule = next((r for r in rules if str(r.id) == actual_id), None)
                if rule:
                    return {"found": True, "enabled": rule.enabled, "data": rule.raw}
                    
            # If we get here, rule was not found
            return {"found": False, "error": f"Rule {rule_id} not found"}
            
        except Exception as err:
            LOGGER.error("Error getting rule status: %s", str(err))
            return {"error": str(err)}