"""
WebSocket connection manager with auto-reconnect and subscription handling.

This module provides robust WebSocket management for real-time exchange data.
"""
import asyncio
import json
from typing import Any, Callable, Optional

import websockets
from websockets.client import WebSocketClientProtocol

from src.core.logger import get_logger

logger = get_logger(__name__, component="websocket")


class WebSocketManager:
    """
    Manages WebSocket connections to cryptocurrency exchanges.

    Features:
    - Automatic reconnection with exponential backoff
    - Heartbeat/ping-pong monitoring
    - Message queue with async iteration
    - Multiple channel subscriptions
    - Connection state tracking
    - Graceful shutdown

    Example:
        >>> ws_manager = WebSocketManager(url="wss://ws.kraken.com")
        >>> await ws_manager.connect()
        >>> await ws_manager.subscribe("ticker", "BTC/USD")
        >>> async for message in ws_manager:
        >>>     print(message)
    """

    def __init__(
        self,
        url: str,
        name: str = "default",
        heartbeat_interval: int = 30,
        max_reconnect_attempts: int = 10,
        reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 60.0,
    ) -> None:
        """
        Initialize WebSocket manager.

        Args:
            url: WebSocket URL
            name: Name for logging (e.g., exchange name)
            heartbeat_interval: Seconds between heartbeat checks
            max_reconnect_attempts: Maximum reconnection attempts
            reconnect_delay: Initial reconnection delay in seconds
            max_reconnect_delay: Maximum reconnection delay
        """
        self.url = url
        self.name = name
        self.heartbeat_interval = heartbeat_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay

        self._ws: Optional[WebSocketClientProtocol] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._subscriptions: set[tuple[str, Optional[str]]] = set()
        self._is_connected = False
        self._should_reconnect = True
        self._reconnect_attempts = 0

        # Tasks
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Callbacks
        self._on_message: Optional[Callable] = None
        self._on_connect: Optional[Callable] = None
        self._on_disconnect: Optional[Callable] = None

        logger.debug(
            "websocket_manager_initialized",
            name=self.name,
            url=self.url
        )

    async def connect(self) -> None:
        """
        Establish WebSocket connection.

        Raises:
            ConnectionError: If connection fails after all retries
        """
        if self._is_connected:
            logger.warning("websocket_already_connected", name=self.name)
            return

        while self._reconnect_attempts < self.max_reconnect_attempts:
            try:
                logger.info(
                    "websocket_connecting",
                    name=self.name,
                    url=self.url,
                    attempt=self._reconnect_attempts + 1
                )

                self._ws = await websockets.connect(
                    self.url,
                    ping_interval=self.heartbeat_interval,
                    ping_timeout=self.heartbeat_interval * 2,
                )

                self._is_connected = True
                self._reconnect_attempts = 0

                logger.info("websocket_connected", name=self.name)

                # Start background tasks
                self._receive_task = asyncio.create_task(self._receive_loop())
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # Call on_connect callback
                if self._on_connect:
                    await self._on_connect()

                # Resubscribe to channels after reconnect
                await self._resubscribe()

                return

            except Exception as e:
                self._reconnect_attempts += 1
                delay = min(
                    self.reconnect_delay * (2 ** self._reconnect_attempts),
                    self.max_reconnect_delay
                )

                logger.error(
                    "websocket_connection_failed",
                    name=self.name,
                    error=str(e),
                    attempt=self._reconnect_attempts,
                    retry_delay=delay
                )

                if self._reconnect_attempts < self.max_reconnect_attempts:
                    await asyncio.sleep(delay)
                else:
                    raise ConnectionError(
                        f"Failed to connect after {self.max_reconnect_attempts} attempts"
                    )

    async def disconnect(self) -> None:
        """Close WebSocket connection gracefully."""
        logger.info("websocket_disconnecting", name=self.name)

        self._should_reconnect = False
        self._is_connected = False

        # Cancel background tasks
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None

        # Call on_disconnect callback
        if self._on_disconnect:
            await self._on_disconnect()

        logger.info("websocket_disconnected", name=self.name)

    async def subscribe(self, channel: str, symbol: Optional[str] = None) -> None:
        """
        Subscribe to a data channel.

        Args:
            channel: Channel name (e.g., "ticker", "trades", "orderbook")
            symbol: Optional trading pair symbol

        Note:
            This is a generic method. Exchange-specific implementations
            should override this to send proper subscription messages.
        """
        subscription = (channel, symbol)
        self._subscriptions.add(subscription)

        logger.info(
            "websocket_subscribed",
            name=self.name,
            channel=channel,
            symbol=symbol
        )

    async def unsubscribe(self, channel: str, symbol: Optional[str] = None) -> None:
        """
        Unsubscribe from a data channel.

        Args:
            channel: Channel name
            symbol: Optional trading pair symbol
        """
        subscription = (channel, symbol)
        self._subscriptions.discard(subscription)

        logger.info(
            "websocket_unsubscribed",
            name=self.name,
            channel=channel,
            symbol=symbol
        )

    async def send(self, message: dict) -> None:
        """
        Send message through WebSocket.

        Args:
            message: Message dictionary to send (will be JSON encoded)

        Raises:
            ConnectionError: If not connected
        """
        if not self._is_connected or not self._ws:
            raise ConnectionError("WebSocket not connected")

        try:
            await self._ws.send(json.dumps(message))
            logger.debug("websocket_message_sent", name=self.name, message=message)
        except Exception as e:
            logger.error("websocket_send_error", name=self.name, error=str(e))
            raise

    async def receive(self) -> dict:
        """
        Receive next message from queue.

        Returns:
            Parsed message dictionary

        Raises:
            ConnectionError: If connection is closed
        """
        if not self._is_connected:
            raise ConnectionError("WebSocket not connected")

        message = await self._message_queue.get()
        return message

    async def _receive_loop(self) -> None:
        """Background task to receive messages."""
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)

                    # Call on_message callback if set
                    if self._on_message:
                        await self._on_message(data)

                    # Add to queue
                    await self._message_queue.put(data)

                    logger.debug(
                        "websocket_message_received",
                        name=self.name,
                        message_type=data.get("type") or data.get("event")
                    )

                except json.JSONDecodeError as e:
                    logger.error(
                        "websocket_json_decode_error",
                        name=self.name,
                        error=str(e),
                        message=message
                    )
                except Exception as e:
                    logger.error(
                        "websocket_message_processing_error",
                        name=self.name,
                        error=str(e)
                    )

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(
                "websocket_connection_closed",
                name=self.name,
                code=e.code,
                reason=e.reason
            )
            self._is_connected = False

            # Attempt reconnection if enabled
            if self._should_reconnect:
                await self._reconnect()

        except Exception as e:
            logger.error(
                "websocket_receive_loop_error",
                name=self.name,
                error=str(e)
            )
            self._is_connected = False

    async def _heartbeat_loop(self) -> None:
        """Background task to monitor connection health."""
        while self._is_connected:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                # Check if still connected
                if self._ws and self._ws.open:
                    logger.debug("websocket_heartbeat", name=self.name)
                else:
                    logger.warning(
                        "websocket_heartbeat_failed",
                        name=self.name
                    )
                    self._is_connected = False
                    if self._should_reconnect:
                        await self._reconnect()
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "websocket_heartbeat_error",
                    name=self.name,
                    error=str(e)
                )

    async def _reconnect(self) -> None:
        """Attempt to reconnect."""
        logger.info("websocket_reconnecting", name=self.name)

        # Close existing connection
        if self._ws:
            await self._ws.close()
            self._ws = None

        # Attempt new connection
        try:
            await self.connect()
        except Exception as e:
            logger.error(
                "websocket_reconnect_failed",
                name=self.name,
                error=str(e)
            )

    async def _resubscribe(self) -> None:
        """Resubscribe to all channels after reconnect."""
        if not self._subscriptions:
            return

        logger.info(
            "websocket_resubscribing",
            name=self.name,
            count=len(self._subscriptions)
        )

        for channel, symbol in self._subscriptions:
            try:
                await self.subscribe(channel, symbol)
            except Exception as e:
                logger.error(
                    "websocket_resubscribe_error",
                    name=self.name,
                    channel=channel,
                    symbol=symbol,
                    error=str(e)
                )

    def set_on_message(self, callback: Callable) -> None:
        """Set callback for message handling."""
        self._on_message = callback

    def set_on_connect(self, callback: Callable) -> None:
        """Set callback for connection events."""
        self._on_connect = callback

    def set_on_disconnect(self, callback: Callable) -> None:
        """Set callback for disconnection events."""
        self._on_disconnect = callback

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._is_connected

    @property
    def subscriptions(self) -> set[tuple[str, Optional[str]]]:
        """Get current subscriptions."""
        return self._subscriptions.copy()

    def __aiter__(self):
        """Async iterator support."""
        return self

    async def __anext__(self) -> dict:
        """Get next message for async iteration."""
        if not self._is_connected:
            raise StopAsyncIteration
        return await self.receive()

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"WebSocketManager(name='{self.name}', "
            f"connected={self._is_connected}, "
            f"subscriptions={len(self._subscriptions)})"
        )
