"""
Order book manager with real-time updates.

Maintains in-memory order books for all exchanges and symbols using
efficient sorted data structures for fast bid/ask lookups.
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Literal, Optional, Tuple

from sortedcontainers import SortedDict

from src.core.logger import get_logger
from src.exchanges.models import OrderBook

logger = get_logger(__name__, component="order_book")


class OrderBookManager:
    """
    Maintains real-time order books for all exchanges and symbols.

    Uses efficient sorted data structures for fast bid/ask lookups.
    Handles incremental updates from WebSocket feeds.

    Structure:
        {exchange: {symbol: {"bids": SortedDict, "asks": SortedDict, "timestamp": datetime}}}
    """

    def __init__(self) -> None:
        """Initialize order book manager."""
        # Structure: {exchange: {symbol: {"bids": SortedDict, "asks": SortedDict, "timestamp": datetime}}}
        self.order_books: Dict[str, Dict[str, Dict]] = {}
        self._update_count = 0

    def initialize_order_book(
        self, exchange: str, symbol: str, order_book: OrderBook
    ) -> None:
        """
        Initialize or replace order book with full snapshot.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol
            order_book: OrderBook model with full snapshot
        """
        if exchange not in self.order_books:
            self.order_books[exchange] = {}

        # Bids: sorted by price descending (highest first)
        # Use negative price as key for descending sort
        bids = SortedDict()
        for price, quantity in order_book.bids:
            bids[-price] = (price, quantity)  # Store negative for descending sort

        # Asks: sorted by price ascending (lowest first)
        asks = SortedDict()
        for price, quantity in order_book.asks:
            asks[price] = quantity

        self.order_books[exchange][symbol] = {
            "bids": bids,
            "asks": asks,
            "timestamp": order_book.timestamp,
        }

        logger.debug(
            "order_book_initialized",
            exchange=exchange,
            symbol=symbol,
            bid_levels=len(bids),
            ask_levels=len(asks),
        )

    def update_order_book(
        self,
        exchange: str,
        symbol: str,
        bids: List[Tuple[Decimal, Decimal]],
        asks: List[Tuple[Decimal, Decimal]],
    ) -> None:
        """
        Update order book with incremental changes.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol
            bids: List of (price, quantity) tuples for bids
            asks: List of (price, quantity) tuples for asks
        """
        if exchange not in self.order_books or symbol not in self.order_books[exchange]:
            logger.warning(
                "order_book_not_initialized",
                exchange=exchange,
                symbol=symbol,
                action="skipping_update",
            )
            return

        book = self.order_books[exchange][symbol]

        # Update bids
        for price, quantity in bids:
            neg_price = -price
            if quantity == 0:
                book["bids"].pop(neg_price, None)  # Remove level
            else:
                book["bids"][neg_price] = (price, quantity)  # Add/update level

        # Update asks
        for price, quantity in asks:
            if quantity == 0:
                book["asks"].pop(price, None)  # Remove level
            else:
                book["asks"][price] = quantity  # Add/update level

        book["timestamp"] = datetime.utcnow()
        self._update_count += 1

        logger.debug(
            "order_book_updated",
            exchange=exchange,
            symbol=symbol,
            bid_updates=len(bids),
            ask_updates=len(asks),
            total_updates=self._update_count,
        )

    def get_best_bid(
        self, exchange: str, symbol: str
    ) -> Optional[Tuple[Decimal, Decimal]]:
        """
        Get best bid (highest price to buy).

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol

        Returns:
            Tuple of (price, quantity) or None if not available
        """
        if exchange not in self.order_books or symbol not in self.order_books[exchange]:
            return None

        bids = self.order_books[exchange][symbol]["bids"]
        if not bids:
            return None

        # Get highest price (first item in sorted dict with negative keys)
        neg_price = bids.keys()[0]
        price, quantity = bids[neg_price]
        return (price, quantity)

    def get_best_ask(
        self, exchange: str, symbol: str
    ) -> Optional[Tuple[Decimal, Decimal]]:
        """
        Get best ask (lowest price to sell).

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol

        Returns:
            Tuple of (price, quantity) or None if not available
        """
        if exchange not in self.order_books or symbol not in self.order_books[exchange]:
            return None

        asks = self.order_books[exchange][symbol]["asks"]
        if not asks:
            return None

        # Get lowest price (first item in sorted dict)
        price = asks.keys()[0]
        quantity = asks[price]
        return (price, quantity)

    def get_spread(self, exchange: str, symbol: str) -> Optional[Decimal]:
        """
        Calculate bid-ask spread.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol

        Returns:
            Spread in price units or None if not available
        """
        best_bid = self.get_best_bid(exchange, symbol)
        best_ask = self.get_best_ask(exchange, symbol)

        if not best_bid or not best_ask:
            return None

        return best_ask[0] - best_bid[0]

    def get_mid_price(self, exchange: str, symbol: str) -> Optional[Decimal]:
        """
        Calculate mid-market price.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol

        Returns:
            Mid price or None if not available
        """
        best_bid = self.get_best_bid(exchange, symbol)
        best_ask = self.get_best_ask(exchange, symbol)

        if not best_bid or not best_ask:
            return None

        return (best_bid[0] + best_ask[0]) / 2

    def get_depth(
        self, exchange: str, symbol: str, side: Literal["buy", "sell"], depth: int = 10
    ) -> List[Tuple[Decimal, Decimal]]:
        """
        Get order book depth (top N levels).

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol
            side: "buy" for bids, "sell" for asks
            depth: Number of levels to return

        Returns:
            List of (price, quantity) tuples
        """
        if exchange not in self.order_books or symbol not in self.order_books[exchange]:
            return []

        if side == "buy":
            bids = self.order_books[exchange][symbol]["bids"]
            # Return top N bids (highest prices first)
            result = []
            for neg_price in list(bids.keys())[:depth]:
                price, quantity = bids[neg_price]
                result.append((price, quantity))
            return result
        else:
            asks = self.order_books[exchange][symbol]["asks"]
            # Return top N asks (lowest prices first)
            return [(price, asks[price]) for price in list(asks.keys())[:depth]]

    def calculate_slippage(
        self, exchange: str, symbol: str, side: Literal["buy", "sell"], quantity: Decimal
    ) -> Decimal:
        """
        Estimate slippage for a given order size.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol
            side: "buy" or "sell"
            quantity: Order quantity

        Returns:
            Estimated slippage percentage
        """
        depth = self.get_depth(exchange, symbol, side, depth=50)

        if not depth:
            return Decimal("1.0")  # 1% default if no data

        total_quantity = Decimal("0")
        weighted_price = Decimal("0")

        for price, available_qty in depth:
            if total_quantity >= quantity:
                break

            qty_to_take = min(available_qty, quantity - total_quantity)
            weighted_price += price * qty_to_take
            total_quantity += qty_to_take

        if total_quantity == 0:
            return Decimal("1.0")

        # Calculate average execution price
        avg_price = weighted_price / total_quantity

        # Best price (first level)
        best_price = depth[0][0]

        # Slippage as percentage
        slippage_percent = abs(avg_price - best_price) / best_price * 100
        return slippage_percent

    def get_order_book_snapshot(
        self, exchange: str, symbol: str, depth: int = 10
    ) -> Optional[Dict]:
        """
        Get order book snapshot.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol
            depth: Number of levels

        Returns:
            Dictionary with bids, asks, and timestamp
        """
        if exchange not in self.order_books or symbol not in self.order_books[exchange]:
            return None

        bids = self.get_depth(exchange, symbol, "buy", depth)
        asks = self.get_depth(exchange, symbol, "sell", depth)
        timestamp = self.order_books[exchange][symbol]["timestamp"]

        return {"bids": bids, "asks": asks, "timestamp": timestamp}

    def has_order_book(self, exchange: str, symbol: str) -> bool:
        """
        Check if order book exists.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol

        Returns:
            True if order book exists
        """
        return (
            exchange in self.order_books and symbol in self.order_books[exchange]
        )

    def get_all_symbols(self, exchange: str) -> List[str]:
        """
        Get all symbols for an exchange.

        Args:
            exchange: Exchange name

        Returns:
            List of symbol names
        """
        if exchange not in self.order_books:
            return []

        return list(self.order_books[exchange].keys())

    def get_stats(self) -> Dict:
        """
        Get order book manager statistics.

        Returns:
            Dictionary with statistics
        """
        total_books = sum(len(symbols) for symbols in self.order_books.values())
        total_levels = 0

        for exchange_books in self.order_books.values():
            for book in exchange_books.values():
                total_levels += len(book["bids"]) + len(book["asks"])

        return {
            "exchanges": len(self.order_books),
            "total_books": total_books,
            "total_levels": total_levels,
            "updates_processed": self._update_count,
        }
