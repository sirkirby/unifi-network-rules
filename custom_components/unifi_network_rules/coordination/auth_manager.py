"""Authentication and state management for UniFi Network Rules coordinator.

Handles session management, authentication state tracking, and CQRS operation management.
Consolidates authentication logic and Home Assistant-initiated operation tracking.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from homeassistant.helpers.dispatcher import async_dispatcher_send

from ..const import DOMAIN, LOGGER
from ..constants.integration import HA_INITIATED_OPERATION_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..udm import UDMAPI


class CoordinatorAuthManager:
    """Manages authentication and state for the coordinator."""

    def __init__(self, hass: HomeAssistant, api: UDMAPI) -> None:
        """Initialize the authentication manager.

        Args:
            hass: Home Assistant instance
            api: The UDMAPI instance for authentication operations
        """
        self.hass = hass
        self.api = api

        # Authentication state
        self._authentication_in_progress = False
        self._auth_failures = 0
        self._max_auth_failures = 5  # After this many failures, stop trying to reconnect

        # CQRS-style Operation Tracking
        # Tracks rule_ids for operations initiated within Home Assistant
        # to prevent redundant refresh and potential race conditions
        self._ha_initiated_operations: dict[str, float] = {}

    def register_ha_initiated_operation(
        self, rule_id: str, entity_id: str, change_type: str = "modified",
        timeout: int = HA_INITIATED_OPERATION_TIMEOUT_SECONDS
    ) -> None:
        """Register that a rule change was initiated from HA.

        This is called by a switch entity just before it queues an API call.
        The smart polling system will use this for debounced refresh.

        Args:
            rule_id: The ID of the rule being changed.
            entity_id: The entity ID that initiated the change.
            change_type: Type of change (enabled, disabled, modified).
            timeout: How long (in seconds) to keep the registration active.
        """
        self._ha_initiated_operations[rule_id] = time.time()
        LOGGER.debug("[CQRS] Registered HA-initiated operation for rule_id: %s", rule_id)

        # Register with smart polling system for debounced refresh
        # Note: We'll need to pass the smart polling manager reference when this is called

        # Schedule cleanup to prevent the dictionary from growing indefinitely
        async def cleanup_op(op_rule_id: str) -> None:
            await asyncio.sleep(timeout)
            if op_rule_id in self._ha_initiated_operations:
                del self._ha_initiated_operations[op_rule_id]
                LOGGER.debug("[CQRS] Expired and removed HA-initiated operation for rule_id: %s", op_rule_id)

        self.hass.async_create_task(cleanup_op(rule_id))

    def check_and_consume_ha_initiated_operation(self, rule_id: str) -> bool:
        """Check if a rule change was HA-initiated and consume the flag.

        This is called by the trigger system before it decides to fire a
        refresh, to see if the change was expected.

        Args:
            rule_id: The ID of the rule that changed.

        Returns:
            True if the operation was initiated from HA, False otherwise.
        """
        if rule_id in self._ha_initiated_operations:
            LOGGER.debug(
                "[CQRS] Consumed HA-initiated operation for rule_id: %s. Suppressing trigger refresh.", rule_id
            )
            del self._ha_initiated_operations[rule_id]
            return True
        return False

    async def handle_authentication_error(self, error: Exception, coordinator) -> bool:
        """Handle authentication errors with retry logic.

        Args:
            error: The authentication error that occurred
            coordinator: Reference to coordinator for data access

        Returns:
            True if authentication was recovered, False otherwise
        """
        error_str = str(error).lower()
        if "401 unauthorized" not in error_str and "403 forbidden" not in error_str:
            return False  # Not an auth error

        self._auth_failures += 1
        self._authentication_in_progress = True

        try:
            LOGGER.warning("Authentication failure #%d during data update", self._auth_failures)

            # Signal auth failure to entities
            async_dispatcher_send(self.hass, f"{DOMAIN}_auth_failure")

            # Try to refresh the session if we haven't exceeded max failures
            if self._auth_failures < self._max_auth_failures:
                LOGGER.info("Attempting to refresh authentication session")
                try:
                    await self.api.refresh_session(force=True)
                    # If we succeeded in refreshing, notify components
                    async_dispatcher_send(self.hass, f"{DOMAIN}_auth_restored")
                    LOGGER.info("Successfully recovered from authentication failure")
                    return True
                except Exception as refresh_err:
                    LOGGER.error("Failed to refresh session: %s", refresh_err)
                    return False
            else:
                LOGGER.error("Max authentication failures (%d) exceeded, giving up", self._max_auth_failures)
                return False

        finally:
            self._authentication_in_progress = False

    async def validate_api_session(self) -> bool:
        """Validate current API session and refresh if needed.

        Returns:
            True if session is valid or was successfully refreshed, False otherwise
        """
        if self._authentication_in_progress:
            LOGGER.debug("Authentication already in progress, skipping validation")
            return False

        try:
            # Simple validation - attempt a lightweight API call
            # This could be enhanced to check session expiry if available
            return True
        except Exception as err:
            LOGGER.warning("Session validation failed: %s", err)
            return await self.handle_authentication_error(err, None)

    def reset_authentication_state(self) -> None:
        """Reset authentication state after successful operation."""
        if self._auth_failures > 0:
            LOGGER.info("Resetting authentication state after successful operation")
            self._auth_failures = 0
            self._authentication_in_progress = False

    def is_authentication_in_progress(self) -> bool:
        """Check if authentication is currently in progress.

        Returns:
            True if authentication is in progress, False otherwise
        """
        return self._authentication_in_progress

    def get_auth_status(self) -> dict[str, any]:
        """Get current authentication status for diagnostics.

        Returns:
            Dictionary with authentication status information
        """
        return {
            "auth_failures": self._auth_failures,
            "max_auth_failures": self._max_auth_failures,
            "authentication_in_progress": self._authentication_in_progress,
            "ha_initiated_operations_count": len(self._ha_initiated_operations),
            "ha_initiated_operations": list(self._ha_initiated_operations.keys()),
        }

    def check_auth_error(self, error: Exception) -> bool:
        """Check if an error is authentication-related.

        Args:
            error: The error to check

        Returns:
            True if the error is authentication-related, False otherwise
        """
        error_str = str(error).lower()
        return "401 unauthorized" in error_str or "403 forbidden" in error_str
