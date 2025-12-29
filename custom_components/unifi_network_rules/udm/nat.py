"""Module for UniFi NAT rule operations (V2 API)."""

from __future__ import annotations

from ..const import LOGGER
from ..constants.api_endpoints import (
    API_PATH_NAT_RULE_DETAIL,
    API_PATH_NAT_RULES,
)
from ..models.nat_rule import NATRule


class NATMixin:
    """Mixin class for NAT rule operations using UniFi V2 API."""

    async def get_nat_rules(self, include_predefined: bool = False) -> list[NATRule]:
        """Fetch NAT rules and return typed NATRule objects."""
        try:
            # Build request via base API helper if available
            if hasattr(self, "create_api_request"):
                request = self.create_api_request("GET", API_PATH_NAT_RULES, is_v2=True)
                response = await self.controller.request(request)
            else:
                # Fallback direct call without relying on site attribute (for isolated tests)
                response = await self.controller.request({"method": "GET", "path": API_PATH_NAT_RULES})

            result: list[NATRule] = []
            if response and "data" in response:
                for item in response["data"]:
                    rule = NATRule(item)
                    if include_predefined or rule.is_custom():
                        result.append(rule)
            LOGGER.debug("Converted %d NAT rules to typed objects", len(result))
            return result
        except Exception as err:
            LOGGER.error("Failed to get NAT rules: %s", err)
            return []

    async def update_nat_rule(self, rule: NATRule) -> bool:
        """Update a NAT rule by sending full payload back to V2 API."""
        try:
            rule_id = rule.id
            if not rule_id:
                LOGGER.error("Cannot update NAT rule without id")
                return False

            payload = rule.to_api_dict()

            if hasattr(self, "create_api_request"):
                path = API_PATH_NAT_RULE_DETAIL.format(rule_id=rule_id)
                request = self.create_api_request("PUT", path, data=payload, is_v2=True)
                await self.controller.request(request)
            else:
                # Fallback direct call without relying on site attribute (for isolated tests)
                path = API_PATH_NAT_RULE_DETAIL.format(rule_id=rule_id)
                await self.controller.request({"method": "PUT", "path": path, "json": payload})
            LOGGER.debug("NAT rule %s updated successfully", rule_id)
            return True
        except Exception as err:
            LOGGER.error("Failed to update NAT rule: %s", err)
            return False

    async def toggle_nat_rule(self, rule: NATRule) -> bool:
        """Toggle a NAT rule enabled state by flipping and updating."""
        try:
            # Flip enabled state
            current = bool(rule.raw.get("enabled", False))
            rule.raw["enabled"] = not current
            return await self.update_nat_rule(rule)
        except Exception as err:
            LOGGER.error("Failed to toggle NAT rule: %s", err)
            return False
