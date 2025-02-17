"""Websocket handler for UniFi Network Rules integration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import aiohttp
import aiounifi

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, LOGGER
from .udm_api import UDMAPI  # Add import for type checking

RETRY_TIMER = 15
CHECK_WEBSOCKET_INTERVAL = timedelta(minutes=1)

class UnifiRuleWebsocket:
    """Manages a UniFi Network instance websocket connection."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        api: UDMAPI, 
        signal: str
    ) -> None:
        """Initialize the system."""
        self.hass = hass
        self.api = api
        self.signal = signal

        self.ws_task: asyncio.Task | None = None
        self._cancel_websocket_check: CALLBACK_TYPE | None = None
        self._initialized = False

        self.available = True
        self._ws_reconnect_delay = RETRY_TIMER
        self.coordinator_callback = None
        
        # Set up websocket message tracking
        self.api.websocket_last_message = None
        self.api.websocket_callback = self.handle_websocket_message

    @callback
    def start(self) -> None:
        """Start websocket handler."""
        if self._initialized:
            return

        self._cancel_websocket_check = async_track_time_interval(
            self.hass, 
            self._async_watch_websocket, 
            CHECK_WEBSOCKET_INTERVAL
        )
        self.start_websocket()
        self._initialized = True

    @callback
    def stop(self) -> None:
        """Stop the current websocket task."""
        if self.ws_task is not None:
            self.ws_task.cancel()

    async def stop_and_wait(self) -> None:
        """Stop websocket handler and await tasks."""
        if self._cancel_websocket_check:
            self._cancel_websocket_check()
            self._cancel_websocket_check = None
        if self.ws_task is not None:
            self.stop()
            try:
                await asyncio.wait([self.ws_task], timeout=10)
            except asyncio.TimeoutError:
                LOGGER.warning(
                    "Unloading UniFi Network Rules (%s). Task %s did not complete in time",
                    self.api.host,
                    self.ws_task,
                )
            finally:
                self.ws_task = None

    @callback
    def start_websocket(self) -> None:
        """Start up connection to websocket."""
        async def _websocket_runner() -> None:
            """Start websocket."""
            try:
                LOGGER.debug("Starting websocket connection")
                await self.api.start_websocket()
                # Reset reconnect delay on successful connection
                self._ws_reconnect_delay = RETRY_TIMER
                self.available = True
                async_dispatcher_send(self.hass, self.signal)
                
            except Exception as err:
                LOGGER.error("Unexpected websocket error: %s", str(err))
                self._handle_ws_error()
                return

        if self.ws_task is not None:
            self.ws_task.cancel()
        
        self.ws_task = self.hass.loop.create_task(_websocket_runner())

    def _handle_ws_error(self) -> None:
        """Handle websocket errors with exponential backoff."""
        self.available = False
        async_dispatcher_send(self.hass, self.signal)
        
        # Implement exponential backoff with max delay
        self._ws_reconnect_delay = min(self._ws_reconnect_delay * 2, 300)  # Max 5 minutes
        self.hass.loop.call_later(self._ws_reconnect_delay, self.reconnect, True)

    @callback
    def reconnect(self, log: bool = False) -> None:
        """Prepare to reconnect UniFi session."""
        async def _reconnect() -> None:
            """Try to reconnect UniFi Network session."""
            try:
                # Use asyncio.timeout context manager
                async with asyncio.timeout(5):
                    success, error = await self.api.authenticate_session()
                    if success:
                        self.start_websocket()
                    else:
                        raise Exception(f"Authentication failed during reconnect: {error}")
            except Exception as exc:
                LOGGER.debug("Schedule reconnect to UniFi Network Rules '%s'", exc)
                self.hass.loop.call_later(self._ws_reconnect_delay, self.reconnect)

        if log:
            LOGGER.info("Will try to reconnect to UniFi Network in %s seconds", self._ws_reconnect_delay)
        self.hass.loop.create_task(_reconnect())

    @callback
    def _async_watch_websocket(self, now: datetime) -> None:
        """Watch websocket status and reconnect if needed."""
        # Check websocket status based on last message time from API
        if not hasattr(self.api, 'websocket_last_message'):
            return

        LOGGER.debug(
            "Last received websocket message: %s",
            self.api.websocket_last_message,
        )
        
        # Check if we haven't received a message in too long
        if self.api.websocket_last_message:
            time_since_last = now - self.api.websocket_last_message
            if time_since_last > timedelta(minutes=2):
                LOGGER.warning("No websocket message received in %s, reconnecting", time_since_last)
                self.ws_task.cancel()
                self.start_websocket()

    @callback
    def handle_websocket_message(self, msg: dict) -> None:
        """Handle websocket message."""
        try:
            # Update last message time first
            self.api.websocket_last_message = datetime.now()
            
            # Forward to coordinator callback if set
            if self.coordinator_callback:
                if asyncio.iscoroutinefunction(self.coordinator_callback):
                    self.hass.async_create_task(
                        self.coordinator_callback(msg),
                        name="unifi_rules_ws_callback"
                    )
                else:
                    self.coordinator_callback(msg)
            
            # Send availability signal
            if not self.available:
                self.available = True
                async_dispatcher_send(self.hass, self.signal)
                
        except Exception as err:
            LOGGER.error("Error handling websocket message: %s", err)
            self._handle_ws_error()

    def record_message_received(self, msg_type: str) -> None:
        """Record receipt of a message type."""
        base_type = msg_type.rsplit('_', 1)[0]  # Strip _add/_update/_remove
        if base_type in self._message_type_stats:
            self._message_type_stats[base_type]['received'] += 1
            self._message_type_stats[base_type]['last_received'] = datetime.now()

    def get_supported_message_types(self) -> set[str]:
        """Get set of message types that have been received."""
        now = datetime.now()
        timeout = timedelta(minutes=5)  # Consider message type inactive after 5 minutes
        
        return {
            msg_type
            for msg_type, stats in self._message_type_stats.items()
            if (stats['received'] > 0 and 
                stats['last_received'] and 
                (now - stats['last_received']) < timeout)
        }