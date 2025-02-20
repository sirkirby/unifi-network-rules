"""Websocket handler for UniFi Network Rules integration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json

import aiohttp
from aiohttp import ClientWebSocketResponse, WSMsgType

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER
from .udm_api import UDMAPI

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
        self._message_handler = None

        self.available = False
        self._ws_reconnect_delay = RETRY_TIMER

    def set_message_handler(self, handler):
        """Set the message handler callback."""
        self._message_handler = handler

    @callback
    def start(self) -> None:
        """Start websocket connection."""
        # Cancel any existing check
        if self._cancel_websocket_check:
            self._cancel_websocket_check()
            
        # Start new connection
        self.reconnect()
        
        # Setup periodic connection check
        self._cancel_websocket_check = async_track_time_interval(
            self.hass, 
            self._check_websocket_health,
            CHECK_WEBSOCKET_INTERVAL
        )

    def reconnect(self, log: bool = False) -> None:
        """Prepare to reconnect UniFi session."""
        async def _reconnect() -> None:
            if log:
                LOGGER.warning("Attempting to reconnect websocket...")
                
            # Ensure previous connection is closed
            if self._ws:
                await self._ws.close()
                self._ws = None
                
            # Start new connection
            self.start_websocket()
            
            # Wait for connection to be established
            if await self.wait_for_connection(timeout=30):
                if log:
                    LOGGER.info("Successfully reconnected websocket")
            else:
                LOGGER.error("Failed to establish websocket connection")
                # Schedule another reconnect attempt
                self.hass.loop.call_later(RETRY_TIMER, lambda: self.reconnect(True))

        if log:
            LOGGER.warning("Disconnected. Reconnecting...")
        self.hass.async_create_task(_reconnect())

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
                    heartbeat=30,
                    receive_timeout=60
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
                        elif msg.type == WSMsgType.ERROR:
                            LOGGER.error("Websocket error: %s", ws.exception())
                            break
                        elif msg.type == WSMsgType.CLOSED:
                            LOGGER.debug("Websocket connection closed")
                            break
                        elif msg.type == WSMsgType.PING:
                            await ws.pong()

        except asyncio.CancelledError:
            LOGGER.debug("Websocket task cancelled")
            raise
        except aiohttp.ClientError as err:
            LOGGER.error("Websocket connection error: %s", err)
            self._handle_ws_error()
            raise
        except Exception as err:
            LOGGER.error("Unexpected websocket error: %s", err)
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
        # Add delay before reconnect to prevent rapid reconnection attempts
        self.hass.loop.call_later(5, self.reconnect)

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
        if not self._message_handler:
            return
            
        try:
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    return
            else:
                data = message
            
            if data and self.hass and self._message_handler:
                if asyncio.iscoroutinefunction(self._message_handler):
                    await self._message_handler(data)
                else:
                    self._message_handler(data)
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