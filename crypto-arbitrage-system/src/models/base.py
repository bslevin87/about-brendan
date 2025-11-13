"""
SQLAlchemy base models for the crypto arbitrage system.

This module defines the database schema for all core entities including
opportunities, trades, positions, balances, audit logs, and tax lots.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""

    pass


class Opportunity(Base):
    """
    Detected arbitrage opportunities.

    Tracks all arbitrage opportunities identified by the system,
    whether executed or not.
    """

    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    opportunity_type: Mapped[str] = mapped_column(
        String(20)
    )  # cross_exchange, triangle, statistical
    pair: Mapped[str] = mapped_column(String(20), index=True)

    # Exchange information
    exchange_buy: Mapped[Optional[str]] = mapped_column(String(50))
    exchange_sell: Mapped[Optional[str]] = mapped_column(String(50))
    exchanges_involved: Mapped[Optional[str]] = mapped_column(JSON)

    # Pricing
    buy_price: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    sell_price: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 10))

    # Profit calculations
    gross_profit_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    net_profit_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    profit_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    fees_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2))

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="detected"
    )  # detected, executed, expired, rejected
    executed: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_time_seconds: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))

    # Additional data
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    risk_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    trades: Mapped[list["Trade"]] = relationship(
        "Trade", back_populates="opportunity", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_opportunity_status", "status", "detected_at"),
        Index("idx_opportunity_type", "opportunity_type", "executed"),
    )


class Trade(Base):
    """
    Trade execution history.

    Records all trade executions including order details,
    execution prices, and outcomes.
    """

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    opportunity_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("opportunities.opportunity_id")
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Trade details
    exchange: Mapped[str] = mapped_column(String(50), index=True)
    pair: Mapped[str] = mapped_column(String(20), index=True)
    side: Mapped[str] = mapped_column(String(10))  # buy, sell
    order_type: Mapped[str] = mapped_column(String(20))  # market, limit

    # Order details
    order_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    price: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 10), default=0)
    average_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 10))

    # Costs
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(20, 10), default=0)
    fee_currency: Mapped[str] = mapped_column(String(10))
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2))

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, filled, partial, canceled, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Additional data
    slippage_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    execution_time_ms: Mapped[Optional[int]] = mapped_column()
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    opportunity: Mapped[Optional["Opportunity"]] = relationship(
        "Opportunity", back_populates="trades"
    )
    tax_lots: Mapped[list["TaxLot"]] = relationship(
        "TaxLot", back_populates="trade", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_trade_exchange_pair", "exchange", "pair", "created_at"),
        Index("idx_trade_status", "status", "created_at"),
    )


class Position(Base):
    """
    Current holdings and open positions.

    Tracks the current state of all positions across exchanges.
    """

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    # Position details
    exchange: Mapped[str] = mapped_column(String(50), index=True)
    asset: Mapped[str] = mapped_column(String(10), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 10))

    # Value calculations
    current_price: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    market_value_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    unrealized_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    unrealized_pnl_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4))

    # Timestamps
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # open, closed
    realized_pnl_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))

    # Additional data
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON)

    __table_args__ = (
        Index("idx_position_exchange_asset", "exchange", "asset", "status"),
    )


class Balance(Base):
    """
    Capital balances per exchange.

    Tracks available and total balances for each asset on each exchange.
    """

    __tablename__ = "balances"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Exchange and asset
    exchange: Mapped[str] = mapped_column(String(50), index=True)
    asset: Mapped[str] = mapped_column(String(10), index=True)

    # Balances
    total: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    available: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    locked: Mapped[Decimal] = mapped_column(Numeric(20, 10), default=0)

    # USD values
    usd_value: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    last_price: Mapped[Decimal] = mapped_column(Numeric(20, 10))

    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )

    # Additional data
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON)

    __table_args__ = (
        Index("idx_balance_exchange_asset", "exchange", "asset", unique=True),
    )


class AuditLog(Base):
    """
    Compliance and audit trail.

    Records all significant system actions for compliance and auditing.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    log_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    # Action details
    action: Mapped[str] = mapped_column(String(50), index=True)
    action_type: Mapped[str] = mapped_column(
        String(20)
    )  # trade, config, system, compliance
    component: Mapped[str] = mapped_column(String(50))

    # User/System
    actor: Mapped[str] = mapped_column(String(50))  # system, admin, etc.
    actor_type: Mapped[str] = mapped_column(String(20))  # system, user

    # Details
    description: Mapped[str] = mapped_column(Text)
    details: Mapped[Optional[dict]] = mapped_column(JSON)

    # Status
    status: Mapped[str] = mapped_column(String(20))  # success, failure, warning
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Compliance
    compliance_relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_required: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("idx_audit_action_type", "action_type", "timestamp"),
        Index("idx_audit_compliance", "compliance_relevant", "timestamp"),
    )


class TaxLot(Base):
    """
    Tax lot tracking for cost basis calculation.

    Tracks individual tax lots for accurate cost basis reporting
    and tax compliance.
    """

    __tablename__ = "tax_lots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lot_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    trade_id: Mapped[Optional[str]] = mapped_column(ForeignKey("trades.trade_id"))

    # Asset details
    asset: Mapped[str] = mapped_column(String(10), index=True)
    exchange: Mapped[str] = mapped_column(String(50))

    # Acquisition
    acquired_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    cost_basis_per_unit: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    total_cost_basis: Mapped[Decimal] = mapped_column(Numeric(20, 2))

    # Disposition
    disposed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    disposed_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 10), default=0)
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    proceeds: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    realized_gain_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))

    # Tax treatment
    holding_period: Mapped[Optional[int]] = mapped_column()  # days
    term: Mapped[Optional[str]] = mapped_column(
        String(10)
    )  # short_term, long_term
    wash_sale: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # open, partial, closed

    # Tax year
    tax_year: Mapped[int] = mapped_column(index=True)

    # Additional data
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    trade: Mapped[Optional["Trade"]] = relationship("Trade", back_populates="tax_lots")

    __table_args__ = (
        Index("idx_tax_lot_asset_status", "asset", "status", "tax_year"),
        Index("idx_tax_lot_disposed", "disposed_at", "tax_year"),
    )


class SystemMetric(Base):
    """
    System performance and health metrics.

    Tracks system performance, health checks, and operational metrics.
    """

    __tablename__ = "system_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    # Metric details
    metric_type: Mapped[str] = mapped_column(String(50), index=True)
    component: Mapped[str] = mapped_column(String(50), index=True)
    metric_name: Mapped[str] = mapped_column(String(100))

    # Value
    value: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    unit: Mapped[str] = mapped_column(String(20))

    # Additional data
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON)

    __table_args__ = (
        Index("idx_metric_type_component", "metric_type", "component", "timestamp"),
    )
