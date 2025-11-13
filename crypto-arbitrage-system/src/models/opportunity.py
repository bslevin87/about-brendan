"""
Arbitrage opportunity models.

This module defines the core data structures for representing
arbitrage opportunities throughout the system.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ArbitrageOpportunity(BaseModel):
    """
    Represents a detected arbitrage opportunity.

    This is the core data structure that flows through the entire system
    from detection → validation → execution → monitoring.
    """

    opportunity_id: str = Field(default_factory=lambda: str(uuid4()))

    # Opportunity type
    strategy: Literal["cross_exchange", "triangle", "statistical"]

    # For cross-exchange arbitrage
    buy_exchange: Optional[str] = None
    sell_exchange: Optional[str] = None
    symbol: Optional[str] = None  # e.g., "BTC/USD"

    # For triangle arbitrage (single exchange)
    exchange: Optional[str] = None
    path: Optional[List[str]] = None  # e.g., ["BTC/USD", "ETH/BTC", "ETH/USD"]

    # Prices
    buy_price: Decimal
    sell_price: Decimal

    # Profitability
    gross_profit_percent: Decimal
    gross_profit_usd: Decimal
    net_profit_percent: Decimal  # After fees
    net_profit_usd: Decimal  # After fees

    # Fees breakdown
    total_fees_percent: Decimal
    total_fees_usd: Decimal
    withdrawal_fees_usd: Optional[Decimal] = None

    # Execution estimates
    max_quantity: Decimal  # Max amount tradeable at these prices
    slippage_estimate_percent: Decimal = Decimal("0.1")  # Default 0.1%
    execution_time_estimate_seconds: int = 2

    # Confidence and risk
    confidence_score: Decimal = Field(ge=0, le=1)  # 0-1 score
    risk_score: Decimal = Field(ge=0, le=1)  # 0-1 score

    # Metadata
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    status: Literal[
        "detected", "validated", "executing", "executed", "expired", "failed"
    ] = "detected"

    # Market context
    order_book_depth_buy: int = 0  # Available liquidity
    order_book_depth_sell: int = 0
    market_volatility: Optional[Decimal] = None

    def is_expired(self) -> bool:
        """Check if opportunity has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def meets_threshold(self, min_profit_percent: Decimal) -> bool:
        """Check if opportunity meets minimum profit threshold."""
        return self.net_profit_percent >= min_profit_percent

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "opportunity_id": self.opportunity_id,
            "strategy": self.strategy,
            "buy_exchange": self.buy_exchange,
            "sell_exchange": self.sell_exchange,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "path": self.path,
            "buy_price": str(self.buy_price),
            "sell_price": str(self.sell_price),
            "gross_profit_percent": str(self.gross_profit_percent),
            "gross_profit_usd": str(self.gross_profit_usd),
            "net_profit_percent": str(self.net_profit_percent),
            "net_profit_usd": str(self.net_profit_usd),
            "total_fees_percent": str(self.total_fees_percent),
            "total_fees_usd": str(self.total_fees_usd),
            "max_quantity": str(self.max_quantity),
            "slippage_estimate_percent": str(self.slippage_estimate_percent),
            "confidence_score": str(self.confidence_score),
            "risk_score": str(self.risk_score),
            "detected_at": self.detected_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "status": self.status,
        }
