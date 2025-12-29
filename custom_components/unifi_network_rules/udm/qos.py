"""Module for UniFi QoS rule operations."""

import json
from typing import Any

from ..const import (
    API_PATH_QOS_RULE_DETAIL,
    API_PATH_QOS_RULES,
    API_PATH_QOS_RULES_BATCH,
    API_PATH_QOS_RULES_BATCH_DELETE,
    LOGGER,
)
from ..models.qos_rule import QoSRule, QoSRuleBatchToggleRequest


class QoSMixin:
    """Mixin class for QoS rule operations."""

    async def get_qos_rules(self) -> list[QoSRule]:
        """Get all QoS rules.

        Returns:
            List of QoSRule objects
        """
        try:
            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("GET", API_PATH_QOS_RULES, is_v2=True)
            response = await self.controller.request(request)

            if response:
                # Convert string response to json if needed
                if isinstance(response, str):
                    try:
                        response = json.loads(response)
                        LOGGER.debug("Converted string response to JSON object: %s", type(response))
                    except json.JSONDecodeError as err:
                        LOGGER.error("Failed to parse QoS rules response as JSON: %s", str(err))
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
                    LOGGER.error("Unable to extract rules list from response. Found %s", type(data))
                    return []

                # Convert to typed QoSRule objects
                result = []
                for rule_data in data:
                    # Create QoSRule objects
                    rule = QoSRule(rule_data)
                    result.append(rule)
                LOGGER.debug("Converted %d QoS rules to typed objects", len(result))
                return result
            return []
        except Exception as err:
            LOGGER.error("Failed to get QoS rules: %s", str(err))
            return []

    async def add_qos_rule(self, rule_data: dict[str, Any]) -> QoSRule | None:
        """Add a new QoS rule.

        Args:
            rule_data: Dictionary containing the QoS rule configuration

        Returns:
            QoSRule object if successful, None otherwise
        """
        LOGGER.debug("Adding QoS rule: %s", rule_data)
        try:
            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("POST", API_PATH_QOS_RULES, data=rule_data, is_v2=True)
            response = await self.controller.request(request)

            if response:
                # Handle string response
                if isinstance(response, str):
                    try:
                        response = json.loads(response)
                    except json.JSONDecodeError as err:
                        LOGGER.error("Failed to parse add QoS rule response as JSON: %s", str(err))
                        return None

                # Extract data from response envelope if present
                if isinstance(response, dict):
                    if "data" in response:
                        response = response["data"]
                        LOGGER.debug("Extracted data from response envelope")
                    elif "meta" in response and response["meta"].get("rc") != "ok":
                        # Check for API error in meta
                        LOGGER.error("API error adding QoS rule: %s", response["meta"].get("msg"))
                        return None

                # Return a typed QoSRule object
                return QoSRule(response)
            return None
        except Exception as err:
            LOGGER.error("Failed to add QoS rule: %s", str(err))
            return None

    async def update_qos_rule(self, rule: QoSRule) -> bool:
        """Update a QoS rule.

        Args:
            rule: The QoSRule object to update

        Returns:
            bool: True if the update was successful, False otherwise
        """
        rule_id = rule.id
        LOGGER.debug("Updating QoS rule %s", rule_id)
        try:
            # Convert rule to dictionary for update
            rule_dict = rule.to_dict()

            # Format API path with site name and rule ID
            path = API_PATH_QOS_RULE_DETAIL.format(rule_id=rule_id)

            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("PUT", path, data=rule_dict, is_v2=True)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("QoS rule %s updated successfully", rule_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to update QoS rule: %s", str(err))
            return False

    async def toggle_qos_rule(self, rule: Any) -> bool:
        """Toggle a QoS rule on/off.

        Args:
            rule: QoSRule object or dictionary with rule data

        Returns:
            bool: True if the toggle was successful, False otherwise
        """
        LOGGER.debug("Toggling QoS rule state")
        try:
            # Ensure we have a proper rule ID
            rule_id = None
            new_state = None

            if isinstance(rule, QoSRule):
                rule_id = rule.id
                new_state = not rule.enabled
            elif isinstance(rule, dict) and "_id" in rule:
                rule_id = rule["_id"]
                new_state = not rule.get("enabled", False)
            else:
                LOGGER.error("Cannot determine rule ID from provided object: %s", type(rule))
                return False

            LOGGER.debug("Toggling QoS rule %s to %s using batch API", rule_id, new_state)

            # Create batch toggle request
            batch_request = QoSRuleBatchToggleRequest([rule_id], new_state)

            # Format API path
            path = API_PATH_QOS_RULES_BATCH

            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("PUT", path, data=batch_request.to_dict(), is_v2=True)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("QoS rule %s toggled successfully to %s", rule_id, new_state)
            return True
        except Exception as err:
            LOGGER.error("Failed to toggle QoS rule: %s", str(err))
            return False

    async def remove_qos_rule(self, rule_id: str) -> bool:
        """Remove a QoS rule.

        Args:
            rule_id: ID of the QoS rule to remove

        Returns:
            bool: True if the removal was successful, False otherwise
        """
        LOGGER.debug("Removing QoS rule: %s", rule_id)
        try:
            # Format API path with rule ID
            path = API_PATH_QOS_RULE_DETAIL.format(rule_id=rule_id)

            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("DELETE", path, is_v2=True)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("QoS rule %s removed successfully", rule_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to remove QoS rule: %s", str(err))
            return False

    async def batch_delete_qos_rules(self, rule_ids: list[str]) -> bool:
        """Delete multiple QoS rules at once.

        Args:
            rule_ids: List of QoS rule IDs to delete

        Returns:
            bool: True if the batch deletion was successful, False otherwise
        """
        if not rule_ids:
            LOGGER.debug("No QoS rules to delete in batch operation")
            return True

        LOGGER.debug("Batch deleting %d QoS rules: %s", len(rule_ids), rule_ids)
        try:
            # Path for batch delete
            path = API_PATH_QOS_RULES_BATCH_DELETE

            # Using is_v2=True because this is a v2 API endpoint
            request = self.create_api_request("POST", path, data=rule_ids, is_v2=True)

            # Execute the API call
            await self.controller.request(request)
            LOGGER.debug("Successfully batch deleted %d QoS rules", len(rule_ids))
            return True
        except Exception as err:
            LOGGER.error("Failed to batch delete QoS rules: %s", str(err))
            return False
