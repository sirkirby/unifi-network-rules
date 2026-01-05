"""Module for UniFi traffic rule operations."""

from typing import Any

# Import directly from specific module rather than models package
from aiounifi.models.traffic_rule import TrafficRule, TrafficRuleListRequest

from ..const import (
    API_PATH_LEGACY_TRAFFIC_RULE_DETAIL,
    API_PATH_LEGACY_TRAFFIC_RULES,
    LOGGER,
)


class TrafficMixin:
    """Mixin class for traffic rule operations."""

    async def get_traffic_rules(self) -> list[TrafficRule]:
        """Get all traffic rules."""
        try:
            # Using TrafficRuleListRequest for proper instantiation
            request = TrafficRuleListRequest.create()
            data = await self.controller.request(request)

            if data and "data" in data:
                # Convert to typed TrafficRule objects
                result = []
                for rule_data in data["data"]:
                    # Explicitly create TrafficRule objects
                    rule = TrafficRule(rule_data)
                    result.append(rule)
                LOGGER.debug("Converted %d traffic rules to typed objects", len(result))
                return result
            return []
        except Exception as err:
            LOGGER.error("Failed to get traffic rules: %s", str(err))
            return []

    async def add_traffic_rule(self, rule_data: dict[str, Any]) -> TrafficRule | None:
        """Add a new traffic rule."""
        LOGGER.debug("Adding traffic rule: %s", rule_data)
        try:
            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("POST", API_PATH_LEGACY_TRAFFIC_RULES, data=rule_data, is_v2=True)
            response = await self.controller.request(request)

            if response and "data" in response:
                # Return a typed TrafficRule object
                return TrafficRule(response["data"])
            return None
        except Exception as err:
            LOGGER.error("Failed to add traffic rule: %s", str(err))
            return None

    async def update_traffic_rule(self, rule: TrafficRule) -> bool:
        """Update a traffic rule.

        Args:
            rule: The TrafficRule object to update

        Returns:
            bool: True if the update was successful, False otherwise
        """
        rule_id = rule.id
        LOGGER.debug("Updating traffic rule %s", rule_id)
        try:
            # Convert rule to dictionary for update
            rule_dict = rule.raw.copy()

            path = API_PATH_LEGACY_TRAFFIC_RULE_DETAIL.format(rule_id=rule_id)
            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("PUT", path, data=rule_dict, is_v2=True)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Traffic rule %s updated successfully", rule_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to update traffic rule: %s", str(err))
            return False

    async def toggle_traffic_rule(self, rule: Any, target_state: bool) -> bool:
        """Set a traffic rule to a specific enabled/disabled state.

        Args:
            rule: The TrafficRule object to modify
            target_state: The desired state (True=enabled, False=disabled)

        Returns:
            bool: True if the operation was successful, False otherwise
        """
        LOGGER.debug("Setting traffic rule state")
        try:
            # Ensure the rule is a proper TrafficRule object
            if not isinstance(rule, TrafficRule):
                LOGGER.error("Expected TrafficRule object but got %s", type(rule))
                return False

            LOGGER.debug("Setting rule %s to %s", rule.id, target_state)

            # Create a new TrafficRule with updated state
            updated_rule = TrafficRule(rule.raw.copy())
            updated_rule.raw["enabled"] = target_state

            # Use update method with the updated rule
            result = await self.update_traffic_rule(updated_rule)
            if result:
                LOGGER.debug("Traffic rule %s set successfully to %s", rule.id, target_state)
            else:
                LOGGER.error("Failed to set traffic rule %s", rule.id)
            return result
        except Exception as err:
            LOGGER.error("Failed to set traffic rule state: %s", str(err))
            return False

    async def remove_traffic_rule(self, rule_id: str) -> bool:
        """Remove a traffic rule."""
        LOGGER.debug("Removing traffic rule: %s", rule_id)
        try:
            path = API_PATH_LEGACY_TRAFFIC_RULE_DETAIL.format(rule_id=rule_id)
            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("DELETE", path, is_v2=True)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Traffic rule %s removed successfully", rule_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove traffic rule: %s", str(err))
            return False
