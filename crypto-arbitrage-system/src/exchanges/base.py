"""
Base exchange adapter interface with complete implementation requirements.

This module defines the abstract base class that all exchange adapters
must implement to ensure consistent interfaces across all exchanges.
"""
import os
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import aiohttp

from src.core.logger import get_logger
from src.exchanges.exceptions import ExchangeException
from src.exchanges.models import Balance, Order, OrderBook, Ticker, Trade
from src.exchanges.rate_limiter import RateLimiter
from src.exchanges.websocket_manager import WebSocketManager

logger = get_logger(__name__, component="exchange")


class BaseExchange(ABC):
    """
    Abstract base class for all exchange adapters.

    All exchange-specific implementations must inherit from this class
    and implement all abstract methods. This ensures consistent interface
    across all exchanges for arbitrage system integration.

    Attributes:
        name: Exchange name
        config: Exchange configuration from yaml
        rate_limiter: Rate limiter for API calls
        api_key: API key from environment
        api_secret: API secret from environment
    """

    def __init__(
        self,
        config: Dict[str, Any],
        rate_limiter: RateLimiter,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ) -> None:
        """
        Initialize exchange adapter.

        Args:
            config: Exchange configuration dictionary
            rate_limiter: Rate limiter instance
            api_key: Optional API key (will load from env if not provided)
            api_secret: Optional API secret (will load from env if not provided)
        """
        self.name = config.get("name", "Unknown")
        self.config = config
        self.rate_limiter = rate_limiter

        # API credentials - load from environment if not provided
        exchange_name_upper = self.name.upper().replace(" ", "_").replace(".", "_")
        self.api_key = api_key or os.getenv(f"{exchange_name_upper}_API_KEY")
        self.api_secret = api_secret or os.getenv(f"{exchange_name_upper}_API_SECRET")

        # URLs from config
        self.api_url = config.get("api_url")
        self.ws_url = config.get("ws_url")

        # Connection state
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_manager: Optional[WebSocketManager] = None
        self._is_connected = False

        logger.info(
            "exchange_adapter_initialized",
            exchange=self.name,
            has_credentials=bool(self.api_key and self.api_secret)
        )

    # ==================== Connection Management ====================

    @abstractmethod
    async def connect(self) -> None:
        """
        Initialize connection to exchange.

        Should create HTTP session and optionally establish WebSocket connection.

        Raises:
            ExchangeException: If connection fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close all connections to exchange.

        Should close HTTP session and WebSocket connections gracefully.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if exchange is reachable and responding.

        Returns:
            True if exchange is healthy, False otherwise
        """
        pass

    # ==================== Market Data (Public API) ====================

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Ticker:
        """
        Fetch current ticker for a symbol.

        Args:
            symbol: Trading pair in normalized format (e.g., "BTC/USD")

        Returns:
            Ticker object with current market data

        Raises:
            ExchangeException: If fetch fails
        """
        pass

    @abstractmethod
    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        """
        Fetch current order book.

        Args:
            symbol: Trading pair in normalized format
            depth: Number of price levels to fetch per side

        Returns:
            OrderBook object with bids and asks

        Raises:
            ExchangeException: If fetch fails
        """
        pass

    @abstractmethod
    async def fetch_trades(self, symbol: str, limit: int = 100) -> List[Trade]:
        """
        Fetch recent trades.

        Args:
            symbol: Trading pair in normalized format
            limit: Maximum number of trades to fetch

        Returns:
            List of Trade objects, most recent first

        Raises:
            ExchangeException: If fetch fails
        """
        pass

    @abstractmethod
    async def fetch_supported_pairs(self) -> List[str]:
        """
        Fetch all trading pairs supported by exchange.

        Returns:
            List of trading pairs in normalized format

        Raises:
            ExchangeException: If fetch fails
        """
        pass

    # ==================== Account Management (Private API) ====================

    @abstractmethod
    async def fetch_balances(self) -> List[Balance]:
        """
        Fetch all account balances.

        Returns:
            List of Balance objects for all currencies

        Raises:
            ExchangeException: If fetch fails
        """
        pass

    @abstractmethod
    async def fetch_balance(self, currency: str) -> Balance:
        """
        Fetch balance for specific currency.

        Args:
            currency: Currency code (e.g., "BTC", "USD")

        Returns:
            Balance object

        Raises:
            ExchangeException: If fetch fails
        """
        pass

    # ==================== Order Management (Private API) ====================

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        dry_run: bool = True
    ) -> Order:
        """
        Create a new order.

        Args:
            symbol: Trading pair (e.g., "BTC/USD")
            side: "buy" or "sell"
            order_type: "market" or "limit"
            quantity: Order quantity
            price: Limit price (required for limit orders)
            dry_run: If True, validate but don't execute

        Returns:
            Order object

        Raises:
            ExchangeException: If order creation fails
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Order identifier
            symbol: Trading pair

        Returns:
            True if successfully cancelled

        Raises:
            ExchangeException: If cancellation fails
        """
        pass

    @abstractmethod
    async def fetch_order(self, order_id: str, symbol: str) -> Order:
        """
        Fetch order status.

        Args:
            order_id: Order identifier
            symbol: Trading pair

        Returns:
            Order object with current status

        Raises:
            ExchangeException: If fetch fails
        """
        pass

    @abstractmethod
    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Fetch all open orders.

        Args:
            symbol: Optional trading pair to filter by

        Returns:
            List of Order objects

        Raises:
            ExchangeException: If fetch fails
        """
        pass

    # ==================== WebSocket Real-Time Data ====================

    @abstractmethod
    async def subscribe_order_book(self, symbol: str) -> None:
        """
        Subscribe to real-time order book updates.

        Args:
            symbol: Trading pair

        Raises:
            ExchangeException: If subscription fails
        """
        pass

    @abstractmethod
    async def subscribe_trades(self, symbol: str) -> None:
        """
        Subscribe to real-time trade updates.

        Args:
            symbol: Trading pair

        Raises:
            ExchangeException: If subscription fails
        """
        pass

    @abstractmethod
    async def unsubscribe(self, channel: str, symbol: str) -> None:
        """
        Unsubscribe from a channel.

        Args:
            channel: Channel name (e.g., "orderbook", "trades")
            symbol: Trading pair

        Raises:
            ExchangeException: If unsubscribe fails
        """
        pass

    # ==================== Utility Methods ====================

    @abstractmethod
    def normalize_symbol(self, symbol: str) -> str:
        """
        Convert exchange-specific symbol to standard format.

        Args:
            symbol: Exchange-specific symbol (e.g., "XXBTZUSD" for Kraken)

        Returns:
            Normalized symbol (e.g., "BTC/USD")
        """
        pass

    @abstractmethod
    def denormalize_symbol(self, symbol: str) -> str:
        """
        Convert standard format to exchange-specific symbol.

        Args:
            symbol: Normalized symbol (e.g., "BTC/USD")

        Returns:
            Exchange-specific symbol (e.g., "XXBTZUSD" for Kraken)
        """
        pass

    async def _create_session(self) -> None:
        """Create aiohttp client session."""
        if not self._session:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
            logger.debug("http_session_created", exchange=self.name)

    async def _close_session(self) -> None:
        """Close aiohttp client session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.debug("http_session_closed", exchange=self.name)

    @abstractmethod
    async def _sign_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate authentication signature for private endpoints.

        Args:
            endpoint: API endpoint path
            params: Request parameters

        Returns:
            Dictionary with authentication headers
        """
        pass

    @abstractmethod
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False
    ) -> Dict[str, Any]:
        """
        Make HTTP request with rate limiting, retries, and error handling.

        This helper method should handle:
        - Rate limiting via self.rate_limiter
        - Request signing for private endpoints
        - Automatic retries on failure
        - Error parsing and exception raising

        Args:
            method: HTTP method ("GET", "POST", etc.)
            endpoint: API endpoint path
            params: Request parameters
            signed: Whether request requires authentication

        Returns:
            Response data as dictionary

        Raises:
            ExchangeException: On any error
        """
        pass

    @property
    def is_connected(self) -> bool:
        """Check if exchange is connected."""
        return self._is_connected

    def __repr__(self) -> str:
        """Return string representation of exchange adapter."""
        return (
            f"{self.__class__.__name__}(name='{self.name}', "
            f"connected={self._is_connected})"
        )


class MockExchange(BaseExchange):
    """
    Mock exchange implementation for testing.

    Returns dummy data for all operations without hitting real APIs.
    """

    async def connect(self) -> None:
        """Establish mock connection."""
        await self._create_session()
        self._is_connected = True
        logger.info("mock_exchange_connected", exchange=self.name)

    async def disconnect(self) -> None:
        """Close mock connection."""
        await self._close_session()
        self._is_connected = False
        logger.info("mock_exchange_disconnected", exchange=self.name)

    async def health_check(self) -> bool:
        """Mock health check always passes."""
        return True

    async def fetch_ticker(self, symbol: str) -> Ticker:
        """Return mock ticker."""
        return Ticker(
            exchange=self.name,
            symbol=symbol,
            bid=Decimal("50000"),
            ask=Decimal("50100"),
            last=Decimal("50050"),
            volume_24h=Decimal("1000"),
            timestamp=datetime.utcnow()
        )

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        """Return mock order book."""
        bids = [(Decimal("50000"), Decimal("1.0"))]
        asks = [(Decimal("50100"), Decimal("1.0"))]
        return OrderBook(
            exchange=self.name,
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.utcnow()
        )

    async def fetch_trades(self, symbol: str, limit: int = 100) -> List[Trade]:
        """Return mock trades."""
        return [
            Trade(
                trade_id="trade_1",
                exchange=self.name,
                symbol=symbol,
                side="buy",
                price=Decimal("50050"),
                quantity=Decimal("0.1"),
                timestamp=datetime.utcnow()
            )
        ]

    async def fetch_supported_pairs(self) -> List[str]:
        """Return mock supported pairs."""
        return ["BTC/USD", "ETH/USD", "BTC/ETH"]

    async def fetch_balances(self) -> List[Balance]:
        """Return mock balances."""
        return [
            Balance(
                exchange=self.name,
                currency="USD",
                total=Decimal("10000"),
                available=Decimal("9000"),
                locked=Decimal("1000"),
                timestamp=datetime.utcnow()
            ),
            Balance(
                exchange=self.name,
                currency="BTC",
                total=Decimal("1.0"),
                available=Decimal("0.9"),
                locked=Decimal("0.1"),
                timestamp=datetime.utcnow()
            )
        ]

    async def fetch_balance(self, currency: str) -> Balance:
        """Return mock balance."""
        return Balance(
            exchange=self.name,
            currency=currency,
            total=Decimal("1000"),
            available=Decimal("900"),
            locked=Decimal("100"),
            timestamp=datetime.utcnow()
        )

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        dry_run: bool = True
    ) -> Order:
        """Return mock order."""
        return Order(
            order_id="mock_order_123",
            exchange=self.name,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            filled_quantity=Decimal("0"),
            status="open",
            timestamp=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Mock order cancellation."""
        return True

    async def fetch_order(self, order_id: str, symbol: str) -> Order:
        """Return mock order status."""
        return Order(
            order_id=order_id,
            exchange=self.name,
            symbol=symbol,
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            filled_quantity=Decimal("0.1"),
            status="filled",
            timestamp=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Return mock open orders."""
        return []

    async def subscribe_order_book(self, symbol: str) -> None:
        """Mock orderbook subscription."""
        logger.info("mock_orderbook_subscribed", symbol=symbol)

    async def subscribe_trades(self, symbol: str) -> None:
        """Mock trades subscription."""
        logger.info("mock_trades_subscribed", symbol=symbol)

    async def unsubscribe(self, channel: str, symbol: str) -> None:
        """Mock unsubscribe."""
        logger.info("mock_unsubscribed", channel=channel, symbol=symbol)

    def normalize_symbol(self, symbol: str) -> str:
        """Mock symbol normalization."""
        return symbol

    def denormalize_symbol(self, symbol: str) -> str:
        """Mock symbol denormalization."""
        return symbol

    async def _sign_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, str]:
        """Mock request signing."""
        return {}

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False
    ) -> Dict[str, Any]:
        """Mock HTTP request."""
        return {"status": "ok"}
