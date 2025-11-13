#!/usr/bin/env python3
"""
Database initialization script.

This script creates all database tables and sets up initial data.
Run this script once during initial setup.

Usage:
    python scripts/init_db.py [--drop] [--seed]

Options:
    --drop: Drop all existing tables before creating new ones
    --seed: Seed database with sample data
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.config import ConfigManager
from src.core.database import DatabaseManager
from src.core.exceptions import DatabaseError
from src.core.logger import get_logger, setup_logging

# Setup logging
setup_logging(log_level="INFO")
logger = get_logger(__name__, component="init_db")


async def drop_tables(db_manager: DatabaseManager) -> None:
    """
    Drop all database tables.

    Args:
        db_manager: Database manager instance
    """
    logger.warning("Dropping all database tables...")
    try:
        await db_manager.drop_all_tables()
        logger.info("All tables dropped successfully")
    except Exception as e:
        logger.error("Failed to drop tables", error=str(e))
        raise


async def create_tables(db_manager: DatabaseManager) -> None:
    """
    Create all database tables.

    Args:
        db_manager: Database manager instance
    """
    logger.info("Creating database tables...")
    try:
        await db_manager.create_all_tables()
        logger.info("All tables created successfully")
    except Exception as e:
        logger.error("Failed to create tables", error=str(e))
        raise


async def seed_data(db_manager: DatabaseManager) -> None:
    """
    Seed database with sample data.

    Args:
        db_manager: Database manager instance
    """
    logger.info("Seeding database with sample data...")

    from datetime import datetime, timedelta
    from decimal import Decimal

    from src.models.base import Balance, SystemMetric

    try:
        async with db_manager.get_session() as session:
            # Add sample balances for each exchange
            exchanges = ["kraken", "binance_us", "coinbase_advanced"]
            assets = ["USD", "BTC", "ETH"]

            for exchange in exchanges:
                for asset in assets:
                    if asset == "USD":
                        total = Decimal("10000")
                    elif asset == "BTC":
                        total = Decimal("0.1")
                    else:
                        total = Decimal("1.0")

                    balance = Balance(
                        exchange=exchange,
                        asset=asset,
                        total=total,
                        available=total * Decimal("0.9"),
                        locked=total * Decimal("0.1"),
                        usd_value=total * Decimal("50000") if asset == "BTC" else total,
                        last_price=Decimal("50000") if asset == "BTC" else Decimal("1"),
                    )
                    session.add(balance)

            # Add sample system metrics
            metrics = [
                {
                    "metric_type": "health",
                    "component": "database",
                    "metric_name": "connection_pool_size",
                    "value": Decimal("5"),
                    "unit": "connections"
                },
                {
                    "metric_type": "health",
                    "component": "system",
                    "metric_name": "uptime",
                    "value": Decimal("100"),
                    "unit": "percent"
                }
            ]

            for metric_data in metrics:
                metric = SystemMetric(**metric_data)
                session.add(metric)

            await session.commit()
            logger.info("Sample data seeded successfully")

    except Exception as e:
        logger.error("Failed to seed data", error=str(e))
        raise


async def verify_tables(db_manager: DatabaseManager) -> None:
    """
    Verify that all tables were created successfully.

    Args:
        db_manager: Database manager instance
    """
    logger.info("Verifying database tables...")

    try:
        # Query to get all table names
        query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
        """

        result = await db_manager.execute_query(query)
        tables = [row[0] for row in result.fetchall()]

        expected_tables = [
            "opportunities",
            "trades",
            "positions",
            "balances",
            "audit_log",
            "tax_lots",
            "system_metrics",
        ]

        logger.info(f"Found {len(tables)} tables in database")

        for table in expected_tables:
            if table in tables:
                logger.info(f"✓ Table '{table}' exists")
            else:
                logger.warning(f"✗ Table '{table}' missing")

        missing_tables = set(expected_tables) - set(tables)
        if missing_tables:
            logger.error(
                f"Missing tables: {', '.join(missing_tables)}"
            )
            return False

        logger.info("All expected tables verified successfully")
        return True

    except Exception as e:
        logger.error("Failed to verify tables", error=str(e))
        return False


async def main() -> None:
    """Main function to initialize database."""
    import argparse

    parser = argparse.ArgumentParser(description="Initialize database")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop all existing tables before creating"
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed database with sample data"
    )

    args = parser.parse_args()

    logger.info("Starting database initialization")

    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = ConfigManager()
        logger.info("Configuration loaded successfully")

        # Initialize database manager
        logger.info("Initializing database manager...")
        db_manager = DatabaseManager(config.database_url)

        # Connect to database
        logger.info("Connecting to database...")
        await db_manager.connect()
        logger.info("Database connected successfully")

        # Perform health check
        logger.info("Performing health check...")
        healthy = await db_manager.health_check()
        if not healthy:
            logger.error("Database health check failed")
            return

        logger.info("Database is healthy")

        # Drop tables if requested
        if args.drop:
            confirmation = input(
                "⚠️  WARNING: This will delete all data. Type 'YES' to confirm: "
            )
            if confirmation == "YES":
                await drop_tables(db_manager)
            else:
                logger.info("Drop cancelled")
                return

        # Create tables
        await create_tables(db_manager)

        # Verify tables
        await verify_tables(db_manager)

        # Seed data if requested
        if args.seed:
            await seed_data(db_manager)

        # Show pool status
        pool_status = await db_manager.get_pool_status()
        logger.info("Database pool status", **pool_status)

        logger.info("✓ Database initialization completed successfully")

    except DatabaseError as e:
        logger.error("Database initialization failed", error=str(e))
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error during initialization", error=str(e))
        sys.exit(1)
    finally:
        # Disconnect
        if db_manager and db_manager.is_connected:
            await db_manager.disconnect()
            logger.info("Database disconnected")


if __name__ == "__main__":
    asyncio.run(main())
