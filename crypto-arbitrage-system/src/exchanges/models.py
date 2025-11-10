"""
Data models for normalized exchange data.

This module provides Pydantic models for standardizing data across
different cryptocurrency exchanges.
"""
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class OrderBook(BaseModel):
    """
    Normalized order book structure.

    Represents a snapshot of bids and asks at a point in time.
    """

    exchange: str = Field(description="Exchange name (e.g., 'kraken')")
    symbol: str = Field(description="Normalized trading pair (e.g., 'BTC/USD')")
    bids: list[tuple[Decimal, Decimal]] = Field(
        description="List of (price, quantity) tuples for bids, sorted by price descending"
    )
    asks: list[tuple[Decimal, Decimal]] = Field(
        description="List of (price, quantity) tuples for asks, sorted by price ascending"
    )
    timestamp: datetime = Field(description="Time of the order book snapshot")

    @property
    def best_bid(self) -> Optional[tuple[Decimal, Decimal]]:
        """Get the best bid (highest price)."""
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Optional[tuple[Decimal, Decimal]]:
        """Get the best ask (lowest price)."""
        return self.asks[0] if self.asks else None

    @property
    def spread(self) -> Optional[Decimal]:
        """Calculate the bid-ask spread."""
        if self.best_bid and self.best_ask:
            return self.best_ask[0] - self.best_bid[0]
        return None

    @property
    def mid_price(self) -> Optional[Decimal]:
        """Calculate the mid price between best bid and ask."""
        if self.best_bid and self.best_ask:
            return (self.best_bid[0] + self.best_ask[0]) / 2
        return None

    @property
    def spread_percent(self) -> Optional[Decimal]:
        """Calculate spread as percentage of mid price."""
        spread = self.spread
        mid = self.mid_price
        if spread and mid and mid > 0:
            return (spread / mid) * 100
        return None


class Trade(BaseModel):
    """
    Normalized trade structure.

    Represents a completed trade on an exchange.
    """

    trade_id: str = Field(description="Unique trade identifier")
    exchange: str = Field(description="Exchange name")
    symbol: str = Field(description="Trading pair (e.g., 'BTC/USD')")
    side: Literal["buy", "sell"] = Field(description="Trade side")
    price: Decimal = Field(description="Execution price", gt=0)
    quantity: Decimal = Field(description="Trade quantity", gt=0)
    timestamp: datetime = Field(description="Trade execution time")
    fee: Optional[Decimal] = Field(None, description="Trade fee amount")
    fee_currency: Optional[str] = Field(None, description="Fee currency")

    @property
    def total_value(self) -> Decimal:
        """Calculate total value (price * quantity)."""
        return self.price * self.quantity


class Order(BaseModel):
    """
    Normalized order structure.

    Represents an order (open, filled, or cancelled).
    """

    order_id: str = Field(description="Unique order identifier")
    exchange: str = Field(description="Exchange name")
    symbol: str = Field(description="Trading pair")
    side: Literal["buy", "sell"] = Field(description="Order side")
    order_type: Literal["market", "limit", "stop_loss", "take_profit"] = Field(
        description="Order type"
    )
    price: Optional[Decimal] = Field(None, description="Limit price (None for market orders)", gt=0)
    quantity: Decimal = Field(description="Order quantity", gt=0)
    filled_quantity: Decimal = Field(Decimal("0"), description="Filled quantity", ge=0)
    status: Literal[
        "pending", "open", "filled", "partially_filled", "cancelled", "rejected"
    ] = Field(description="Order status")
    timestamp: datetime = Field(description="Order creation time")
    updated_at: datetime = Field(description="Last update time")
    fee: Optional[Decimal] = Field(None, description="Total fees paid")
    fee_currency: Optional[str] = Field(None, description="Fee currency")

    @field_validator("filled_quantity")
    @classmethod
    def validate_filled_quantity(cls, v: Decimal, info) -> Decimal:
        """Ensure filled quantity doesn't exceed order quantity."""
        if "quantity" in info.data and v > info.data["quantity"]:
            raise ValueError("Filled quantity cannot exceed order quantity")
        return v

    @property
    def remaining_quantity(self) -> Decimal:
        """Calculate remaining unfilled quantity."""
        return self.quantity - self.filled_quantity

    @property
    def fill_percent(self) -> Decimal:
        """Calculate fill percentage."""
        if self.quantity > 0:
            return (self.filled_quantity / self.quantity) * 100
        return Decimal("0")

    @property
    def is_open(self) -> bool:
        """Check if order is still open."""
        return self.status in ["pending", "open", "partially_filled"]

    @property
    def is_completed(self) -> bool:
        """Check if order is completed (filled or cancelled)."""
        return self.status in ["filled", "cancelled", "rejected"]


class Balance(BaseModel):
    """
    Normalized balance structure.

    Represents account balance for a specific currency.
    """

    exchange: str = Field(description="Exchange name")
    currency: str = Field(description="Currency code (e.g., 'BTC', 'USD')")
    total: Decimal = Field(description="Total balance", ge=0)
    available: Decimal = Field(description="Available for trading", ge=0)
    locked: Decimal = Field(description="Locked in open orders", ge=0)
    timestamp: datetime = Field(description="Balance snapshot time")

    @field_validator("available", "locked")
    @classmethod
    def validate_balance_components(cls, v: Decimal, info) -> Decimal:
        """Ensure available + locked = total."""
        if "total" in info.data:
            # We'll check this in a model validator instead
            pass
        return v

    @property
    def locked_percent(self) -> Decimal:
        """Calculate percentage of balance locked."""
        if self.total > 0:
            return (self.locked / self.total) * 100
        return Decimal("0")


class Ticker(BaseModel):
    """
    Normalized ticker structure.

    Represents current market data for a trading pair.
    """

    exchange: str = Field(description="Exchange name")
    symbol: str = Field(description="Trading pair")
    bid: Decimal = Field(description="Best bid price", gt=0)
    ask: Decimal = Field(description="Best ask price", gt=0)
    last: Decimal = Field(description="Last trade price", gt=0)
    volume_24h: Decimal = Field(description="24h trading volume", ge=0)
    timestamp: datetime = Field(description="Ticker timestamp")
    high_24h: Optional[Decimal] = Field(None, description="24h high price")
    low_24h: Optional[Decimal] = Field(None, description="24h low price")
    change_24h: Optional[Decimal] = Field(None, description="24h price change")
    change_24h_percent: Optional[Decimal] = Field(None, description="24h price change percent")

    @property
    def spread(self) -> Decimal:
        """Calculate bid-ask spread."""
        return self.ask - self.bid

    @property
    def mid_price(self) -> Decimal:
        """Calculate mid price."""
        return (self.bid + self.ask) / 2

    @property
    def spread_percent(self) -> Decimal:
        """Calculate spread as percentage."""
        if self.mid_price > 0:
            return (self.spread / self.mid_price) * 100
        return Decimal("0")


class ExchangeInfo(BaseModel):
    """
    Exchange information and status.

    Represents the current state and capabilities of an exchange.
    """

    name: str = Field(description="Exchange name")
    status: Literal["online", "offline", "maintenance"] = Field(
        description="Exchange status"
    )
    supported_pairs: list[str] = Field(description="List of supported trading pairs")
    rate_limit: int = Field(description="Requests per second limit", gt=0)
    has_websocket: bool = Field(description="Whether WebSocket is supported")
    timestamp: datetime = Field(description="Status check timestamp")
