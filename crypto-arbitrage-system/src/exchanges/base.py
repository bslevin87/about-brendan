"""
Base exchange adapter interface.

This module defines the abstract base class for exchange adapters.
Future phases will implement concrete adapters for each exchange.
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.core.exceptions import ExchangeConnectionError
from src.core.logger import get_logger

logger = get_logger(__name__, component="exchange")


class OrderBook:
    """Represents an order book snapshot."""

    def __init__(
        self,
        pair: str,
        bids: List[tuple[Decimal, Decimal]],
        asks: List[tuple[Decimal, Decimal]],
        timestamp: float
    ) -> None:
        """
        Initialize order book.

        Args:
            pair: Trading pair
            bids: List of (price, quantity) tuples for bids
            asks: List of (price, quantity) tuples for asks
            timestamp: Unix timestamp of the snapshot
        """
        self.pair = pair
        self.bids = bids
        self.asks = asks
        self.timestamp = timestamp

    @property
    def best_bid(self) -> Optional[tuple[Decimal, Decimal]]:
        """Get best bid (highest price)."""
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Optional[tuple[Decimal, Decimal]]:
        """Get best ask (lowest price)."""
        return self.asks[0] if self.asks else None

    @property
    def spread(self) -> Optional[Decimal]:
        """Calculate bid-ask spread."""
        if self.best_bid and self.best_ask:
            return self.best_ask[0] - self.best_bid[0]
        return None

    @property
    def mid_price(self) -> Optional[Decimal]:
        """Calculate mid price."""
        if self.best_bid and self.best_ask:
            return (self.best_bid[0] + self.best_ask[0]) / 2
        return None


class Order:
    """Represents a trading order."""

    def __init__(
        self,
        order_id: str,
        pair: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        status: str = "pending"
    ) -> None:
        """
        Initialize order.

        Args:
            order_id: Unique order identifier
            pair: Trading pair
            side: Order side (buy/sell)
            order_type: Order type (market/limit)
            quantity: Order quantity
            price: Order price (for limit orders)
            status: Order status
        """
        self.order_id = order_id
        self.pair = pair
        self.side = side
        self.order_type = order_type
        self.quantity = quantity
        self.price = price
        self.status = status
        self.filled_quantity = Decimal("0")
        self.average_price: Optional[Decimal] = None
        self.fee: Optional[Decimal] = None


class Balance:
    """Represents account balance for an asset."""

    def __init__(
        self,
        asset: str,
        total: Decimal,
        available: Decimal,
        locked: Decimal
    ) -> None:
        """
        Initialize balance.

        Args:
            asset: Asset symbol
            total: Total balance
            available: Available balance
            locked: Locked balance
        """
        self.asset = asset
        self.total = total
        self.available = available
        self.locked = locked


class BaseExchange(ABC):
    """
    Abstract base class for exchange adapters.

    All exchange implementations must inherit from this class and
    implement the required methods.
    """

    def __init__(
        self,
        exchange_name: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ) -> None:
        """
        Initialize exchange adapter.

        Args:
            exchange_name: Name of the exchange
            api_key: API key for authentication
            api_secret: API secret for authentication
        """
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.is_connected = False

        logger.info(
            "exchange_adapter_initialized",
            exchange=exchange_name
        )

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish connection to the exchange.

        Raises:
            ExchangeConnectionError: If connection fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Disconnect from the exchange.
        """
        pass

    @abstractmethod
    async def get_orderbook(
        self,
        pair: str,
        depth: int = 20
    ) -> OrderBook:
        """
        Fetch order book for a trading pair.

        Args:
            pair: Trading pair (e.g., "BTC/USD")
            depth: Number of price levels to fetch

        Returns:
            OrderBook object

        Raises:
            ExchangeConnectionError: If fetch fails
        """
        pass

    @abstractmethod
    async def get_balance(self, asset: str) -> Balance:
        """
        Get balance for a specific asset.

        Args:
            asset: Asset symbol

        Returns:
            Balance object

        Raises:
            ExchangeConnectionError: If fetch fails
        """
        pass

    @abstractmethod
    async def get_all_balances(self) -> Dict[str, Balance]:
        """
        Get all account balances.

        Returns:
            Dictionary mapping asset symbols to Balance objects

        Raises:
            ExchangeConnectionError: If fetch fails
        """
        pass

    @abstractmethod
    async def place_order(
        self,
        pair: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> Order:
        """
        Place a trading order.

        Args:
            pair: Trading pair
            side: Order side (buy/sell)
            order_type: Order type (market/limit)
            quantity: Order quantity
            price: Order price (required for limit orders)

        Returns:
            Order object

        Raises:
            ExchangeConnectionError: If order placement fails
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Order identifier

        Returns:
            True if cancellation successful

        Raises:
            ExchangeConnectionError: If cancellation fails
        """
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Order:
        """
        Get status of an order.

        Args:
            order_id: Order identifier

        Returns:
            Order object with current status

        Raises:
            ExchangeConnectionError: If fetch fails
        """
        pass

    @abstractmethod
    async def get_ticker(self, pair: str) -> Dict[str, Any]:
        """
        Get ticker information for a pair.

        Args:
            pair: Trading pair

        Returns:
            Dictionary with ticker information

        Raises:
            ExchangeConnectionError: If fetch fails
        """
        pass

    def __repr__(self) -> str:
        """Return string representation of exchange adapter."""
        return (
            f"{self.__class__.__name__}(exchange={self.exchange_name}, "
            f"connected={self.is_connected})"
        )


class MockExchange(BaseExchange):
    """
    Mock exchange implementation for testing.

    This is a simple implementation that returns dummy data
    for testing purposes.
    """

    async def connect(self) -> None:
        """Establish mock connection."""
        logger.info("mock_exchange_connecting", exchange=self.exchange_name)
        self.is_connected = True

    async def disconnect(self) -> None:
        """Disconnect from mock exchange."""
        logger.info("mock_exchange_disconnecting", exchange=self.exchange_name)
        self.is_connected = False

    async def get_orderbook(self, pair: str, depth: int = 20) -> OrderBook:
        """Return mock order book."""
        bids = [(Decimal("50000.00"), Decimal("1.0"))]
        asks = [(Decimal("50100.00"), Decimal("1.0"))]
        return OrderBook(pair, bids, asks, 0.0)

    async def get_balance(self, asset: str) -> Balance:
        """Return mock balance."""
        return Balance(
            asset=asset,
            total=Decimal("1000"),
            available=Decimal("900"),
            locked=Decimal("100")
        )

    async def get_all_balances(self) -> Dict[str, Balance]:
        """Return mock balances."""
        return {
            "USD": await self.get_balance("USD"),
            "BTC": await self.get_balance("BTC")
        }

    async def place_order(
        self,
        pair: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> Order:
        """Place mock order."""
        return Order(
            order_id="mock_order_123",
            pair=pair,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status="filled"
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel mock order."""
        return True

    async def get_order_status(self, order_id: str) -> Order:
        """Get mock order status."""
        return Order(
            order_id=order_id,
            pair="BTC/USD",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            status="filled"
        )

    async def get_ticker(self, pair: str) -> Dict[str, Any]:
        """Get mock ticker."""
        return {
            "pair": pair,
            "last": Decimal("50050.00"),
            "bid": Decimal("50000.00"),
            "ask": Decimal("50100.00"),
            "volume": Decimal("1000.0")
        }
