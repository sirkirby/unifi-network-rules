"""Websocket handler for UniFi Network Rules integration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import aiohttp
from aiohttp import ClientWebSocketResponse, WSMsgType

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

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
        self._ws = None
        self._connection_event = asyncio.Event()

        self.available = False
        self._ws_reconnect_delay = RETRY_TIMER
        self.coordinator_callback = None

    @callback
    def start(self) -> None:
        """Start websocket connection."""
        self.reconnect()
        
        # Setup periodic connection check
        if not self._cancel_websocket_check:
            self._cancel_websocket_check = async_track_time_interval(
                self.hass, self._check_websocket_health, CHECK_WEBSOCKET_INTERVAL
            )

    def reconnect(self, log: bool = False) -> None:
        """Prepare to reconnect UniFi session."""
        async def _reconnect() -> None:
            """Trigger a reconnect and notify HA."""
            self.start_websocket()
            if log:
                LOGGER.warning(
                    "Connected. Please report if this message appears unreasonably often as it indicates an unstable connection"
                )

        if log:
            LOGGER.warning("Disconnected. Reconnecting...")
        self.hass.loop.create_task(_reconnect())

    @callback
    def start_websocket(self) -> None:
        """Start up connection."""
        if self.ws_task is not None:
            self.ws_task.cancel()
            
        self.ws_task = self.hass.async_create_task(
            self._initialize_websocket(),
            name="unifi_rules_websocket"
        )

    async def _initialize_websocket(self) -> None:
        """Initialize websocket connection."""
        url = f"wss://{self.api.host}/proxy/network/wss/s/default/events"

        try:
            cookie = await self.api.get_cookie()
            headers = {"Cookie": f"TOKEN={cookie}"}

            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    url,
                    headers=headers,
                    ssl=False,
                    heartbeat=30
                ) as ws:
                    self._ws = ws
                    self._initialized = True
                    self._connection_event.set()
                    LOGGER.debug("Websocket connected")
                    
                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            try:
                                await self._handle_ws_message(msg.data)
                            except Exception as err:
                                LOGGER.error("Error handling message: %s", err)
                        elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                            LOGGER.debug("Websocket connection closed")
                            break
                        
                    LOGGER.debug("Websocket connection loop ended")
                    
        except asyncio.CancelledError:
            LOGGER.debug("Websocket task cancelled")
            raise
        except Exception as err:
            LOGGER.error("Websocket connection error: %s", err)
            self._handle_ws_error()
            raise
        finally:
            self._initialized = False
            self._connection_event.clear()
            if self._ws:
                await self._ws.close()
                self._ws = None

    def _handle_ws_error(self) -> None:
        """Handle websocket error."""
        if self.ws_task is not None:
            self.ws_task.cancel()
        self.reconnect()

    async def stop_and_wait(self) -> None:
        """Close websocket connection and wait for it to close."""
        if self._cancel_websocket_check:
            self._cancel_websocket_check()
            self._cancel_websocket_check = None

        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass
            self.ws_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

        self._initialized = False
        self._connection_event.clear()

    async def wait_for_connection(self, timeout: float | None = None) -> bool:
        """Wait for websocket to be connected."""
        try:
            await asyncio.wait_for(self._connection_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def _handle_ws_message(self, message: str) -> None:
        """Handle incoming websocket message."""
        if not self.coordinator_callback:
            return
            
        try:
            # Try to parse message as JSON if it's a string
            if isinstance(message, str):
                try:
                    import json
                    parsed_message = json.loads(message)
                except json.JSONDecodeError as e:
                    LOGGER.warning("Failed to parse websocket message as JSON: %s - %s", message, str(e))
                    return
            else:
                parsed_message = message

            if self.hass and self.coordinator_callback:
                # Handle both async and non-async callbacks
                if asyncio.iscoroutinefunction(self.coordinator_callback):
                    self.hass.async_create_task(
                        self.coordinator_callback(parsed_message),
                        name="unifi_rules_ws_callback"
                    )
                else:
                    # For non-async callbacks, run directly
                    self.coordinator_callback(parsed_message)

        except Exception as e:
            LOGGER.error("Error processing websocket message: %s", str(e))

    @callback
    async def _check_websocket_health(self, *_) -> None:
        """Check websocket health and reconnect if needed."""
        if not self._initialized or not self._ws:
            LOGGER.debug("Websocket health check - reconnecting")
            self.reconnect()
        elif self._ws.closed:
            LOGGER.debug("Websocket health check - connection closed")
            self.reconnect()