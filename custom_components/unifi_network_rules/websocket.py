"""UniFi Network Rules websocket implementation."""
from __future__ import annotations

from typing import Any, Callable
import asyncio

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import LOGGER
from .udm_api import UDMAPI

SIGNAL_WEBSOCKET_CONNECTION_LOST = "unifi_network_rules_websocket_connection_lost"
SIGNAL_WEBSOCKET_MESSAGE = "unifi_network_rules_websocket_message"

class UnifiRuleWebsocket:
    """UniFi Network Rules websocket handler."""

    def __init__(self, hass: HomeAssistant, api: UDMAPI, name: str) -> None:
        """Initialize the websocket handler."""
        self.hass = hass
        self.api = api
        self.name = name
        self._running = False
        self._message_handler: Callable[[dict[str, Any]], None] | None = None

    def start(self) -> None:
        """Start listening to the websocket."""
        LOGGER.debug("Starting UniFi Network Rules websocket %s", self.name)
        if not self._running:
            self._running = True
            self.api.set_websocket_callback(self._handle_message)
            asyncio.create_task(self._start_websocket())

    async def _start_websocket(self) -> None:
        """Start websocket connection."""
        try:
            await self.api.start_websocket()
        except Exception as err:
            LOGGER.error("Error starting websocket: %s", err)
            self._running = False

    async def stop_and_wait(self) -> None:
        """Stop listening to the websocket and wait for it to close."""
        LOGGER.debug("Stopping UniFi Network Rules websocket %s", self.name)
        self._running = False
        try:
            await self.api.stop_websocket()
        except Exception as err:
            LOGGER.error("Error stopping websocket: %s", err)

    @callback
    def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle a message from the websocket."""
        try:
            if self._running:
                # Send message through dispatcher first
                async_dispatcher_send(self.hass, SIGNAL_WEBSOCKET_MESSAGE, message)
                # Then call the specific message handler if set
                if self._message_handler is not None:
                    self._message_handler(message)
        except Exception as err:
            LOGGER.error("Error handling websocket message: %s", err)

    def set_message_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Set the message handler."""
        self._message_handler = handler