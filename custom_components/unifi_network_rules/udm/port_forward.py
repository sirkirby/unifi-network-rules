"""Module for UniFi port forwarding operations."""

from typing import Any

# Import directly from specific module
from aiounifi.models.port_forward import PortForward, PortForwardEnableRequest, PortForwardListRequest

from ..const import (
    API_PATH_PORT_FORWARD_DETAIL,
    API_PATH_PORT_FORWARDS,
    LOGGER,
)


class PortForwardMixin:
    """Mixin class for port forwarding operations."""

    async def get_port_forwards(self) -> list[PortForward]:
        """Get all port forwards."""
        try:
            # Using PortForwardListRequest for proper instantiation
            request = PortForwardListRequest.create()
            data = await self.controller.request(request)

            if data and "data" in data:
                # Return typed PortForward objects instead of raw dictionaries
                result = []
                for forward_data in data["data"]:
                    # Explicitly create PortForward objects from the raw dictionary data
                    forward = PortForward(forward_data)
                    result.append(forward)
                LOGGER.debug("Converted %d port forwards to typed objects", len(result))
                return result
            return []
        except Exception as err:
            LOGGER.error("Failed to get port forwards: %s", str(err))
            return []

    async def add_port_forward(self, forward_data: dict[str, Any]) -> PortForward | None:
        """Add a new port forward."""
        LOGGER.debug("Adding port forward: %s", forward_data)
        try:
            # Using the path constant from const.py
            request = self.create_api_request("POST", API_PATH_PORT_FORWARDS, data=forward_data)
            response = await self.controller.request(request)

            if response and "data" in response:
                # Return a typed PortForward object
                return PortForward(response["data"])
            return None
        except Exception as err:
            LOGGER.error("Failed to add port forward: %s", str(err))
            return None

    async def update_port_forward(self, forward: PortForward) -> bool:
        """Update a port forward.

        Args:
            forward: The PortForward object to update

        Returns:
            bool: True if the update was successful, False otherwise
        """
        forward_id = forward.id
        LOGGER.debug("Updating port forward %s", forward_id)
        try:
            # Convert forward to dictionary for update
            forward_dict = forward.raw.copy()

            # Using the DETAIL path with forward_id
            path = API_PATH_PORT_FORWARD_DETAIL.format(forward_id=forward_id)
            request = self.create_api_request("PUT", path, data=forward_dict)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Port forward %s updated successfully", forward_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to update port forward: %s", str(err))
            return False

    async def toggle_port_forward(self, forward: Any, target_state: bool) -> bool:
        """Set a port forward to a specific enabled/disabled state.

        Args:
            forward: The PortForward object to modify
            target_state: The desired state (True=enabled, False=disabled)

        Returns:
            bool: True if the operation was successful, False otherwise
        """
        LOGGER.debug("Setting port forward state")
        try:
            # Ensure the forward is a proper PortForward object
            if not isinstance(forward, PortForward):
                LOGGER.error("Expected PortForward object but got %s", type(forward))
                return False

            LOGGER.debug("Setting port forward %s to %s", forward.id, target_state)

            # The PortForwardEnableRequest.create method expects both the object and the enable flag
            request = PortForwardEnableRequest.create(forward, target_state)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Port forward %s set successfully to %s", forward.id, target_state)
            return True
        except Exception as err:
            LOGGER.error("Failed to set port forward state: %s", str(err))
            return False

    async def remove_port_forward(self, forward_id: str) -> bool:
        """Remove a port forward."""
        LOGGER.debug("Removing port forward: %s", forward_id)
        try:
            # Using the DETAIL path with forward_id
            path = API_PATH_PORT_FORWARD_DETAIL.format(forward_id=forward_id)
            request = self.create_api_request("DELETE", path)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Port forward %s removed successfully", forward_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove port forward: %s", str(err))
            return False
