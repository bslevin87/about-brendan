"""
Tests for database manager.

This module tests database connectivity, session management, and operations.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.core.database import DatabaseManager
from src.core.exceptions import DatabaseError
from src.models.base import Balance, Opportunity, Trade


class TestDatabaseConnection:
    """Test database connection functionality."""

    @pytest.mark.asyncio
    async def test_database_connect(self, test_db: DatabaseManager) -> None:
        """Test database connection."""
        assert test_db.is_connected is True

    @pytest.mark.asyncio
    async def test_database_health_check(self, test_db: DatabaseManager) -> None:
        """Test database health check."""
        healthy = await test_db.health_check()
        assert healthy is True

    @pytest.mark.asyncio
    async def test_pool_status(self, test_db: DatabaseManager) -> None:
        """Test getting pool status."""
        status = await test_db.get_pool_status()
        assert isinstance(status, dict)


class TestDatabaseSessions:
    """Test database session management."""

    @pytest.mark.asyncio
    async def test_get_session(self, test_db: DatabaseManager) -> None:
        """Test getting a database session."""
        async with test_db.get_session() as session:
            assert session is not None

    @pytest.mark.asyncio
    async def test_session_commit(self, test_db: DatabaseManager) -> None:
        """Test session commit."""
        async with test_db.get_session() as session:
            balance = Balance(
                exchange="test_exchange",
                asset="BTC",
                total=Decimal("1.0"),
                available=Decimal("0.9"),
                locked=Decimal("0.1"),
                usd_value=Decimal("50000"),
                last_price=Decimal("50000")
            )
            session.add(balance)
        # Should commit automatically

    @pytest.mark.asyncio
    async def test_session_rollback_on_error(
        self, test_db: DatabaseManager
    ) -> None:
        """Test session rollback on error."""
        try:
            async with test_db.get_session() as session:
                # This should cause an error
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected


class TestDatabaseOperations:
    """Test database CRUD operations."""

    @pytest.mark.asyncio
    async def test_insert_balance(self, test_db: DatabaseManager) -> None:
        """Test inserting a balance record."""
        async with test_db.get_session() as session:
            balance = Balance(
                exchange="kraken",
                asset="BTC",
                total=Decimal("1.5"),
                available=Decimal("1.0"),
                locked=Decimal("0.5"),
                usd_value=Decimal("75000"),
                last_price=Decimal("50000")
            )
            session.add(balance)

        # Verify insertion
        async with test_db.get_session() as session:
            result = await session.execute(
                select(Balance).where(
                    Balance.exchange == "kraken",
                    Balance.asset == "BTC"
                )
            )
            retrieved = result.scalar_one_or_none()
            assert retrieved is not None
            assert retrieved.total == Decimal("1.5")

    @pytest.mark.asyncio
    async def test_insert_opportunity(self, test_db: DatabaseManager) -> None:
        """Test inserting an opportunity record."""
        async with test_db.get_session() as session:
            opportunity = Opportunity(
                opportunity_id="opp_123",
                opportunity_type="cross_exchange",
                pair="BTC/USD",
                exchange_buy="kraken",
                exchange_sell="coinbase_advanced",
                buy_price=Decimal("50000"),
                sell_price=Decimal("50500"),
                quantity=Decimal("0.1"),
                gross_profit_usd=Decimal("50"),
                net_profit_usd=Decimal("45"),
                profit_percent=Decimal("0.9"),
                fees_usd=Decimal("5")
            )
            session.add(opportunity)

        # Verify insertion
        async with test_db.get_session() as session:
            result = await session.execute(
                select(Opportunity).where(
                    Opportunity.opportunity_id == "opp_123"
                )
            )
            retrieved = result.scalar_one_or_none()
            assert retrieved is not None
            assert retrieved.pair == "BTC/USD"

    @pytest.mark.asyncio
    async def test_insert_trade(self, test_db: DatabaseManager) -> None:
        """Test inserting a trade record."""
        async with test_db.get_session() as session:
            trade = Trade(
                trade_id="trade_123",
                exchange="kraken",
                pair="BTC/USD",
                side="buy",
                order_type="limit",
                quantity=Decimal("0.1"),
                price=Decimal("50000"),
                filled_quantity=Decimal("0.1"),
                fee_amount=Decimal("0.0001"),
                fee_currency="BTC",
                total_cost_usd=Decimal("5000")
            )
            session.add(trade)

        # Verify insertion
        async with test_db.get_session() as session:
            result = await session.execute(
                select(Trade).where(Trade.trade_id == "trade_123")
            )
            retrieved = result.scalar_one_or_none()
            assert retrieved is not None
            assert retrieved.exchange == "kraken"

    @pytest.mark.asyncio
    async def test_query_multiple_records(
        self, test_db: DatabaseManager
    ) -> None:
        """Test querying multiple records."""
        # Insert multiple balances
        async with test_db.get_session() as session:
            for i in range(3):
                balance = Balance(
                    exchange=f"exchange_{i}",
                    asset="USD",
                    total=Decimal("1000"),
                    available=Decimal("900"),
                    locked=Decimal("100"),
                    usd_value=Decimal("1000"),
                    last_price=Decimal("1")
                )
                session.add(balance)

        # Query all
        async with test_db.get_session() as session:
            result = await session.execute(select(Balance))
            balances = result.scalars().all()
            assert len(balances) >= 3

    @pytest.mark.asyncio
    async def test_update_record(self, test_db: DatabaseManager) -> None:
        """Test updating a record."""
        # Insert
        async with test_db.get_session() as session:
            balance = Balance(
                exchange="test",
                asset="BTC",
                total=Decimal("1.0"),
                available=Decimal("1.0"),
                locked=Decimal("0"),
                usd_value=Decimal("50000"),
                last_price=Decimal("50000")
            )
            session.add(balance)

        # Update
        async with test_db.get_session() as session:
            result = await session.execute(
                select(Balance).where(
                    Balance.exchange == "test",
                    Balance.asset == "BTC"
                )
            )
            balance = result.scalar_one()
            balance.available = Decimal("0.5")
            balance.locked = Decimal("0.5")

        # Verify update
        async with test_db.get_session() as session:
            result = await session.execute(
                select(Balance).where(
                    Balance.exchange == "test",
                    Balance.asset == "BTC"
                )
            )
            balance = result.scalar_one()
            assert balance.available == Decimal("0.5")
            assert balance.locked == Decimal("0.5")


class TestDatabaseRetry:
    """Test database retry logic."""

    @pytest.mark.asyncio
    async def test_connect_with_valid_url(self) -> None:
        """Test connection with valid URL."""
        db = DatabaseManager(
            "sqlite+aiosqlite:///:memory:",
            connect_retries=1
        )
        await db.connect()
        assert db.is_connected is True
        await db.disconnect()

    @pytest.mark.asyncio
    async def test_connect_with_invalid_url(self) -> None:
        """Test connection failure with invalid URL."""
        db = DatabaseManager(
            "postgresql+asyncpg://invalid:invalid@nonexistent/db",
            connect_retries=1,
            retry_delay=0.1
        )

        with pytest.raises(DatabaseError):
            await db.connect()


class TestDatabaseErrors:
    """Test database error handling."""

    @pytest.mark.asyncio
    async def test_session_without_connection(self) -> None:
        """Test getting session without connection."""
        db = DatabaseManager("sqlite+aiosqlite:///:memory:")

        with pytest.raises(DatabaseError):
            async with db.get_session() as session:
                pass

    @pytest.mark.asyncio
    async def test_health_check_without_connection(self) -> None:
        """Test health check without connection."""
        db = DatabaseManager("sqlite+aiosqlite:///:memory:")
        healthy = await db.health_check()
        assert healthy is False
