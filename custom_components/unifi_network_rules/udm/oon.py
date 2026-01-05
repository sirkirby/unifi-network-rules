"""Module for UniFi Object-Oriented Network policy operations."""

import json
from typing import Any

from ..const import (
    API_PATH_OON_POLICIES,  # GET uses plural
    API_PATH_OON_POLICY,  # POST uses singular
    API_PATH_OON_POLICY_DETAIL,  # PUT/DELETE use singular
    LOGGER,
)
from ..models.oon_policy import OONPolicy


class OONMixin:
    """Mixin class for Object-Oriented Network policy operations."""

    async def get_oon_policies(self) -> list[OONPolicy]:
        """Get all Object-Oriented Network policies.

        Returns:
            List of OONPolicy objects. Returns empty list on 404 (unsupported controller).
        """
        try:
            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("GET", API_PATH_OON_POLICIES, is_v2=True)
            response = await self.controller.request(request)

            if response:
                # Convert string response to json if needed
                if isinstance(response, str):
                    try:
                        response = json.loads(response)
                        LOGGER.debug("Converted string response to JSON object: %s", type(response))
                    except json.JSONDecodeError as err:
                        LOGGER.error("Failed to parse OON policies response as JSON: %s", str(err))
                        return []

                # Extract the data array from the response
                data = None
                if isinstance(response, dict) and "data" in response:
                    data = response["data"]
                    LOGGER.debug("Extracted data array from response envelope")
                else:
                    # If response doesn't have the expected structure, assume it's the data directly
                    data = response

                # Now data should be a list
                if not isinstance(data, list):
                    LOGGER.error("Unable to extract policies list from response. Found %s", type(data))
                    return []

                # Convert to typed OONPolicy objects
                result = []
                for policy_data in data:
                    # Create OONPolicy objects
                    policy = OONPolicy(policy_data)
                    result.append(policy)
                LOGGER.debug("Converted %d OON policies to typed objects", len(result))
                return result
            return []
        except Exception as err:
            error_str = str(err).lower()
            # Handle 404 errors gracefully (unsupported controller)
            if "404" in error_str or "not found" in error_str:
                LOGGER.debug("OON policies endpoint not available (controller may not support OON policies): %s", err)
                return []
            LOGGER.error("Failed to get OON policies: %s", str(err))
            return []

    async def update_oon_policy(self, policy: OONPolicy) -> bool:
        """Update an Object-Oriented Network policy.

        Args:
            policy: The OONPolicy object to update

        Returns:
            bool: True if the update was successful, False otherwise
        """
        policy_id = policy.id
        LOGGER.debug("Updating OON policy %s", policy_id)
        try:
            # Convert policy to dictionary for update
            policy_dict = policy.to_api_dict()

            # Format API path with policy ID
            path = API_PATH_OON_POLICY_DETAIL.format(policy_id=policy_id)

            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("PUT", path, data=policy_dict, is_v2=True)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("OON policy %s updated successfully", policy_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to update OON policy %s: %s", policy_id, str(err))
            return False

    async def toggle_oon_policy(self, policy: OONPolicy, target_state: bool) -> bool:
        """Set an Object-Oriented Network policy to a specific enabled/disabled state.

        Args:
            policy: OONPolicy object to modify
            target_state: The desired state (True=enabled, False=disabled)

        Returns:
            bool: True if the operation was successful, False otherwise
        """
        LOGGER.debug("Setting OON policy state")
        try:
            # Create a copy of the policy with the new enabled state
            policy_dict = policy.to_api_dict()
            policy_dict["enabled"] = target_state

            # Format API path with policy ID
            path = API_PATH_OON_POLICY_DETAIL.format(policy_id=policy.id)

            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("PUT", path, data=policy_dict, is_v2=True)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("OON policy %s set successfully to %s", policy.id, target_state)
            return True
        except Exception as err:
            LOGGER.error("Failed to set OON policy state: %s", str(err))
            return False

    async def add_oon_policy(self, policy_data: dict[str, Any]) -> OONPolicy | None:
        """Add a new Object-Oriented Network policy.

        Args:
            policy_data: Dictionary containing the policy data (should not include _id)

        Returns:
            OONPolicy object if creation was successful, None otherwise
        """
        LOGGER.debug("Adding OON policy: %s", policy_data.get("name", "unnamed"))
        try:
            # Remove _id if present to let the API assign a new one
            add_data = policy_data.copy()
            if "_id" in add_data:
                del add_data["_id"]
            if "id" in add_data:
                del add_data["id"]

            # Using is_v2=True because this is a v2 API endpoint
            # POST request returns 201 Created on success
            # POST uses singular form: /object-oriented-network-config
            request = self.create_api_request("POST", API_PATH_OON_POLICY, data=add_data, is_v2=True)
            response = await self.controller.request(request)

            if response:
                # Convert string response to json if needed
                if isinstance(response, str):
                    try:
                        response = json.loads(response)
                    except json.JSONDecodeError as err:
                        LOGGER.error("Failed to parse OON policy creation response as JSON: %s", str(err))
                        return None

                # Extract the created policy data
                data = None
                if isinstance(response, dict) and "data" in response:
                    data = response["data"]
                    # API may return a list or single object
                    if isinstance(data, list) and len(data) > 0:
                        data = data[0]
                else:
                    data = response

                if data:
                    policy = OONPolicy(data)
                    LOGGER.debug("OON policy created successfully with ID: %s", policy.id)
                    return policy

            LOGGER.warning("No policy data returned from API after creation")
            return None
        except Exception as err:
            LOGGER.error("Failed to add OON policy: %s", str(err))
            return None

    async def remove_oon_policy(self, policy_id: str) -> bool:
        """Remove an Object-Oriented Network policy.

        Args:
            policy_id: The ID of the OON policy to remove

        Returns:
            bool: True if the removal was successful, False otherwise
        """
        LOGGER.debug("Removing OON policy: %s", policy_id)
        try:
            # Format API path with policy ID
            path = API_PATH_OON_POLICY_DETAIL.format(policy_id=policy_id)

            # Using is_v2=True because this is a v2 API endpoint
            # DELETE request returns 204 No Content on success
            request = self.create_api_request("DELETE", path, is_v2=True)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("OON policy %s removed successfully", policy_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove OON policy %s: %s", policy_id, str(err))
            return False
