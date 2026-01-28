"""Module for UniFi firewall operations."""

from typing import Any

# Import directly from specific module rather than models package
from aiounifi.models.firewall_policy import FirewallPolicy, FirewallPolicyListRequest, FirewallPolicyUpdateRequest

from ..const import (
    API_PATH_FIREWALL_POLICIES,
    API_PATH_FIREWALL_POLICIES_BATCH_DELETE,
    API_PATH_LEGACY_FIREWALL_RULE_DETAIL,
    API_PATH_LEGACY_FIREWALL_RULES,
    LOGGER,
)

# Import our custom FirewallRule model for legacy firewall rules
from ..models.firewall_rule import FirewallRule


class FirewallMixin:
    """Mixin class for firewall operations."""

    async def get_firewall_policies(
        self, include_predefined: bool = False, force_refresh: bool = False
    ) -> list[FirewallPolicy]:
        """Get all firewall policies."""
        try:
            if force_refresh and hasattr(self.controller, "refresh_cache"):
                await self.controller.refresh_cache()

            # Using FirewallPolicyListRequest.create() for proper instantiation
            request = FirewallPolicyListRequest.create()
            data = await self.controller.request(request)

            if data and "data" in data:
                policies_data = data["data"]

                # Filter out predefined rules if not requested
                if not include_predefined:
                    policies_data = [p for p in policies_data if not p.get("predefined", True)]

                # Explicitly convert to FirewallPolicy objects
                result = []
                for policy_data in policies_data:
                    # Create a typed FirewallPolicy object
                    policy = FirewallPolicy(policy_data)
                    result.append(policy)

                LOGGER.debug("Converted %d firewall policies to typed objects", len(result))
                return result
            return []
        except Exception as err:
            LOGGER.error("Failed to get firewall policies: %s", str(err))
            return []

    async def add_firewall_policy(self, policy_data: dict[str, Any]) -> FirewallPolicy | None:
        """Add a new firewall policy."""
        LOGGER.debug("Adding firewall policy: %s", policy_data)
        try:
            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("POST", API_PATH_FIREWALL_POLICIES, data=policy_data, is_v2=True)
            response = await self.controller.request(request)

            if response and "data" in response and len(response["data"]) > 0:
                LOGGER.debug("Firewall policy added successfully")
                # Convert response to typed FirewallPolicy object
                return FirewallPolicy(response["data"][0])

            LOGGER.warning("No policy data returned from API")
            return None
        except Exception as err:
            LOGGER.error("Failed to add firewall policy: %s", str(err))
            return None

    async def update_firewall_policy(self, policy: FirewallPolicy) -> bool:
        """Update a firewall policy.

        Args:
            policy: The FirewallPolicy object to update

        Returns:
            bool: True if the update was successful, False otherwise
        """
        try:
            policy_id = policy.id
            LOGGER.debug("Updating firewall policy %s", policy_id)

            # Get the raw dictionary from the policy
            policy_dict = policy.raw.copy()

            # Using FirewallPolicyUpdateRequest.create() for proper instantiation
            request = FirewallPolicyUpdateRequest.create(policy_dict)

            # Execute with retry if needed
            await self.controller.request(request)
            LOGGER.debug("Firewall policy %s updated successfully", policy_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to update firewall policy: %s", str(err))
            return False

    async def remove_firewall_policy(self, policy_id: str) -> bool:
        """Remove a firewall policy."""
        try:
            # Using batch delete path
            data = {"ids": [policy_id]}
            request = self.create_api_request("POST", API_PATH_FIREWALL_POLICIES_BATCH_DELETE, data=data, is_v2=True)

            # Execute with retry if needed
            await self.controller.request(request)
            LOGGER.debug("Firewall policy %s removed successfully", policy_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove firewall policy: %s", str(err))
            return False

    async def toggle_firewall_policy(self, policy: Any, target_state: bool) -> bool:
        """Set a firewall policy to a specific enabled/disabled state.

        Args:
            policy: The FirewallPolicy object to modify
            target_state: The desired state (True=enabled, False=disabled)

        Returns:
            bool: True if the operation was successful, False otherwise
        """
        LOGGER.debug("Setting firewall policy state")
        try:
            # Ensure the policy is a proper FirewallPolicy object
            if not isinstance(policy, FirewallPolicy):
                LOGGER.error("Expected FirewallPolicy object but got %s", type(policy))
                return False

            LOGGER.debug("Setting policy %s to %s", policy.id, target_state)

            # Get the raw dictionary from the policy
            policy_dict = policy.raw.copy()
            policy_dict["enabled"] = target_state

            # Create the update request with the raw dictionary
            # The FirewallPolicyUpdateRequest.create() expects a dict it can access with subscript notation
            request = FirewallPolicyUpdateRequest.create(policy_dict)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Firewall policy %s set successfully to %s", policy.id, target_state)
            return True
        except Exception as err:
            LOGGER.error("Failed to set firewall policy state: %s", str(err))
            return False

    async def get_legacy_firewall_rules(self) -> list[FirewallRule]:
        """Get all legacy firewall rules and return as typed FirewallRule objects."""
        try:
            # Using the correct path constant from const.py
            request = self.create_api_request("GET", API_PATH_LEGACY_FIREWALL_RULES)

            # Create a request to the legacy endpoint
            response = await self.controller.request(request)

            # Check for both success response and the specific zone-based firewall "error" case
            if response and "data" in response:
                # For devices migrated to zone-based firewalls, this is a known response
                if (
                    "meta" in response
                    and response["meta"].get("rc") == "error"
                    and response["meta"].get("msg") == "api.err.InvalidObject"
                ):
                    LOGGER.debug("Legacy firewall rules not available - device likely using zone-based firewalls")
                    return []

                # Convert raw dictionary data to FirewallRule objects - use model's static method
                rule_objects = []
                for rule_data in response["data"]:
                    # Use the FirewallRule's static method to ensure complete data
                    typed_data = FirewallRule.ensure_complete_data(rule_data)
                    rule_objects.append(FirewallRule(typed_data))

                return rule_objects
            return []
        except Exception as err:
            # Convert error to string for checking
            err_str = str(err)

            # Check if this is the "api.err.InvalidObject" error
            if "api.err.InvalidObject" in err_str:
                LOGGER.debug("Legacy firewall rules not available - device likely using zone-based firewalls")
                return []

            # Log other errors
            LOGGER.error("Get legacy firewall rules failed: %s", err_str)
            return []

    async def add_legacy_firewall_rule(self, rule_data: dict[str, Any]) -> FirewallRule | None:
        """Add a new legacy firewall rule."""
        LOGGER.debug("Adding legacy firewall rule: %s", rule_data)
        try:
            # Using the correct path constant
            request = self.create_api_request("POST", API_PATH_LEGACY_FIREWALL_RULES, data=rule_data)
            response = await self.controller.request(request)

            if response and isinstance(response, dict):
                # Convert to FirewallRule object using the model's static method
                typed_data = FirewallRule.ensure_complete_data(response)
                return FirewallRule(typed_data)
            return None
        except Exception as err:
            LOGGER.error("Failed to add legacy firewall rule: %s", str(err))
            return None

    async def update_legacy_firewall_rule(self, rule: FirewallRule) -> bool:
        """Update an existing legacy firewall rule.

        Args:
            rule: The FirewallRule object to update

        Returns:
            bool: True if the update was successful, False otherwise
        """
        rule_id = rule.id
        LOGGER.debug("Updating legacy firewall rule %s", rule_id)
        try:
            # Convert rule to dictionary for update (required for API)
            rule_dict = rule.raw.copy()

            # Using the DETAIL path with rule_id
            path = API_PATH_LEGACY_FIREWALL_RULE_DETAIL.format(rule_id=rule_id)
            request = self.create_api_request("PUT", path, data=rule_dict)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Legacy firewall rule %s updated successfully", rule_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to update legacy firewall rule: %s", str(err))
            return False

    async def toggle_legacy_firewall_rule(self, rule: Any, target_state: bool) -> bool:
        """Set a legacy firewall rule to a specific enabled/disabled state.

        Args:
            rule: The FirewallRule object to modify
            target_state: The desired state (True=enabled, False=disabled)

        Returns:
            bool: True if the operation was successful, False otherwise
        """
        LOGGER.debug("Setting legacy firewall rule state")
        try:
            # Ensure the rule is a proper FirewallRule object
            if not isinstance(rule, FirewallRule):
                LOGGER.error("Expected FirewallRule object but got %s", type(rule))
                return False

            LOGGER.debug("Setting legacy firewall rule %s to %s", rule.id, target_state)

            # Convert rule to dictionary for update (required for API)
            rule_dict = rule.raw.copy()

            # Update enabled state
            rule_dict["enabled"] = target_state

            # Create a new FirewallRule object with the updated state
            updated_rule = FirewallRule(rule_dict)

            # Update the rule using our standardized method
            result = await self.update_legacy_firewall_rule(updated_rule)
            if result:
                LOGGER.debug("Legacy firewall rule %s set successfully to %s", rule.id, target_state)
            else:
                LOGGER.error("Failed to set legacy firewall rule %s", rule.id)
            return result
        except Exception as err:
            LOGGER.error("Failed to set legacy firewall rule state: %s", str(err))
            return False
