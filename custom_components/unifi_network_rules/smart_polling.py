"""Smart Polling Manager for UniFi Network Rules."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import LOGGER


@dataclass
class SmartPollingConfig:
    """Configuration for smart polling behavior."""

    base_interval: int = 300  # 5 minutes - idle polling interval
    active_interval: int = 30  # 30 seconds - active polling interval
    realtime_interval: int = 10  # 10 seconds - near real-time interval
    activity_timeout: int = 120  # 2 minutes - time to return to base interval
    debounce_seconds: int = 10  # 10 seconds - debounce window
    optimistic_timeout: int = 15  # 15 seconds - maximum optimistic state duration


class SmartPollingManager:
    """Manages intelligent polling intervals and debounced refresh for HA-initiated changes."""

    def __init__(self, coordinator: DataUpdateCoordinator, config: SmartPollingConfig):
        """Initialize the smart polling manager.

        Args:
            coordinator: The DataUpdateCoordinator to manage
            config: Smart polling configuration
        """
        self.coordinator = coordinator
        self.config = config

        # Activity tracking
        self._last_activity = 0
        self._activity_entities: set[str] = set()

        # Debounce system
        self._pending_poll_task: asyncio.Task | None = None
        self._debounce_timer: asyncio.Handle | None = None

        # Smart polling timer management
        self._polling_timer: asyncio.Handle | None = None
        self._current_interval = config.base_interval
        self._is_active = False
        self._timer_active = False

        # Track if we're currently in a smart polling cycle
        self._in_smart_poll_cycle = False

    async def register_entity_change(self, entity_id: str, change_type: str) -> None:
        """Register that an entity change occurred (HA-initiated).

        This triggers the debounced refresh system and switches to active polling.

        Args:
            entity_id: The entity that changed
            change_type: Type of change (e.g., 'enabled', 'disabled', 'modified')
        """
        current_time = time.time()
        self._last_activity = current_time
        self._activity_entities.add(entity_id)

        LOGGER.debug("[SMART_POLL] Entity change registered: %s (%s)", entity_id, change_type)

        # Start smart polling if not already active
        await self._ensure_smart_polling_active()

        # Cancel existing pending poll if any
        if self._pending_poll_task and not self._pending_poll_task.done():
            self._pending_poll_task.cancel()
            LOGGER.debug("[SMART_POLL] Cancelled existing pending poll task")

        # Cancel existing debounce timer if any
        if self._debounce_timer:
            self._debounce_timer.cancel()

        # Schedule new debounced poll
        loop = asyncio.get_event_loop()
        self._debounce_timer = loop.call_later(
            self.config.debounce_seconds, lambda: asyncio.create_task(self._execute_debounced_poll())
        )

        LOGGER.debug("[SMART_POLL] Scheduled debounced poll in %d seconds", self.config.debounce_seconds)

    async def _execute_debounced_poll(self) -> None:
        """Execute a debounced poll after the timer expires."""
        try:
            # Clear the timer reference
            self._debounce_timer = None

            # Get the entities that triggered this poll
            affected_entities = self._activity_entities.copy()
            self._activity_entities.clear()

            LOGGER.info(
                "[SMART_POLL] Executing debounced poll for %d entities: %s",
                len(affected_entities),
                list(affected_entities),
            )

            # Set flag to indicate this is a smart polling cycle
            self._in_smart_poll_cycle = True
            try:
                # Perform the coordinator refresh
                await self.coordinator.async_refresh()
            finally:
                # Clear flag after refresh completes
                self._in_smart_poll_cycle = False

            LOGGER.info("[SMART_POLL] Debounced poll completed successfully")

        except asyncio.CancelledError:
            LOGGER.debug("[SMART_POLL] Debounced poll was cancelled")
            raise
        except Exception as err:
            LOGGER.error("[SMART_POLL] Error in debounced poll: %s", err)

    async def _ensure_smart_polling_active(self) -> None:
        """Ensure smart polling is active and schedule next poll based on activity."""
        if not self._timer_active:
            self._timer_active = True
            await self._schedule_next_smart_poll()

    async def _schedule_next_smart_poll(self) -> None:
        """Schedule the next smart poll based on current activity level."""
        if not self._timer_active:
            return

        # Cancel any existing timer
        if self._polling_timer:
            self._polling_timer.cancel()

        # Get current interval based on activity
        current_interval = self.get_current_interval()

        # Only continue smart polling if we're in active mode
        if not self._is_active:
            LOGGER.debug("[SMART_POLL] Switching to idle mode - smart polling disabled")
            self._timer_active = False
            return

        LOGGER.debug("[SMART_POLL] Scheduling next smart poll in %d seconds", current_interval)

        # Schedule the next poll
        loop = asyncio.get_event_loop()
        self._polling_timer = loop.call_later(current_interval, lambda: asyncio.create_task(self._execute_smart_poll()))

    async def _execute_smart_poll(self) -> None:
        """Execute a smart poll and schedule the next one."""
        try:
            LOGGER.debug("[SMART_POLL] Executing smart poll")

            # Set flag to indicate this is a smart polling cycle
            self._in_smart_poll_cycle = True
            try:
                # Perform the coordinator refresh
                await self.coordinator.async_refresh()
            finally:
                # Clear flag after refresh completes
                self._in_smart_poll_cycle = False

            # Schedule the next poll
            await self._schedule_next_smart_poll()

        except asyncio.CancelledError:
            LOGGER.debug("[SMART_POLL] Smart poll was cancelled")
            self._timer_active = False
        except Exception as err:
            LOGGER.error("[SMART_POLL] Error in smart poll: %s", err)
            # Clear flag on error too
            self._in_smart_poll_cycle = False
            # Still schedule next poll to maintain polling
            await self._schedule_next_smart_poll()

    def is_in_smart_poll_cycle(self) -> bool:
        """Check if we're currently in a smart polling cycle.

        This is used by the coordinator to avoid registering smart polling
        cycles as external changes, which would create a feedback loop.

        Returns:
            True if currently in a smart polling cycle
        """
        return self._in_smart_poll_cycle

    def get_current_interval(self) -> int:
        """Get current polling interval based on activity.

        Returns:
            Current polling interval in seconds
        """
        current_time = time.time()
        time_since_activity = current_time - self._last_activity

        if time_since_activity < self.config.debounce_seconds * 2:
            # Very recent activity - use real-time interval
            self._is_active = True
            return self.config.realtime_interval
        elif time_since_activity < self.config.activity_timeout:
            # Recent activity - use active interval
            self._is_active = True
            return self.config.active_interval
        else:
            # No recent activity - disable smart polling, let baseline handle it
            self._is_active = False
            return self.config.base_interval

    async def register_external_change_detected(self) -> None:
        """Register that an external change was detected via polling.

        This helps maintain activity tracking for external changes too.
        """
        self._last_activity = time.time()

        # Start smart polling for external changes too
        await self._ensure_smart_polling_active()

        LOGGER.debug("[SMART_POLL] External change detected, started smart polling")

    def get_status(self) -> dict[str, Any]:
        """Get current smart polling status for diagnostics.

        Returns:
            Dictionary with current polling status
        """
        current_time = time.time()
        time_since_activity = current_time - self._last_activity

        return {
            "current_interval": self.get_current_interval(),
            "is_active": self._is_active,
            "timer_active": self._timer_active,
            "in_smart_poll_cycle": self._in_smart_poll_cycle,
            "time_since_activity": round(time_since_activity, 1),
            "pending_entities": len(self._activity_entities),
            "has_pending_poll": self._pending_poll_task is not None and not self._pending_poll_task.done(),
            "has_debounce_timer": self._debounce_timer is not None,
            "has_smart_timer": self._polling_timer is not None,
            "coordinator_interval": self.coordinator.update_interval.total_seconds()
            if self.coordinator.update_interval
            else None,
            "config": {
                "base_interval": self.config.base_interval,
                "active_interval": self.config.active_interval,
                "realtime_interval": self.config.realtime_interval,
                "activity_timeout": self.config.activity_timeout,
                "debounce_seconds": self.config.debounce_seconds,
            },
        }

    async def cleanup(self) -> None:
        """Clean up resources when shutting down."""
        # Stop smart polling
        self._timer_active = False
        self._in_smart_poll_cycle = False

        # Cancel smart polling timer
        if self._polling_timer:
            self._polling_timer.cancel()
            self._polling_timer = None

        # Cancel pending tasks
        if self._pending_poll_task and not self._pending_poll_task.done():
            self._pending_poll_task.cancel()
            try:
                await self._pending_poll_task
            except asyncio.CancelledError:
                pass

        # Cancel debounce timer
        if self._debounce_timer:
            self._debounce_timer.cancel()
            self._debounce_timer = None

        # Clear state
        self._activity_entities.clear()

        LOGGER.debug("[SMART_POLL] Cleanup completed")
