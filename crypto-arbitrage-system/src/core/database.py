"""
Database connection and session management for the crypto arbitrage system.

This module provides async database connectivity using SQLAlchemy with
connection pooling, automatic retries, and health checking.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, QueuePool

from src.core.exceptions import DatabaseError
from src.core.logger import get_logger

logger = get_logger(__name__, component="database")


class DatabaseManager:
    """
    Manages database connections and sessions.

    This class handles:
    - Async database engine creation
    - Connection pooling
    - Session management
    - Health checks
    - Automatic retries on connection failures
    """

    def __init__(
        self,
        database_url: str,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        connect_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """
        Initialize the database manager.

        Args:
            database_url: Database connection URL
            echo: Whether to echo SQL statements (for debugging)
            pool_size: Number of connections to maintain in pool
            max_overflow: Max connections beyond pool_size
            pool_timeout: Seconds to wait for connection from pool
            pool_recycle: Seconds before recycling connections
            connect_retries: Number of connection retry attempts
            retry_delay: Delay between retry attempts in seconds
        """
        self.database_url = database_url
        self.echo = echo
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.pool_recycle = pool_recycle
        self.connect_retries = connect_retries
        self.retry_delay = retry_delay

        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._is_connected = False

    async def connect(self) -> None:
        """
        Establish database connection with retry logic.

        Raises:
            DatabaseError: If connection fails after all retries
        """
        if self._is_connected:
            logger.warning("Database already connected")
            return

        for attempt in range(1, self.connect_retries + 1):
            try:
                logger.info(
                    "database_connection_attempt",
                    attempt=attempt,
                    max_attempts=self.connect_retries
                )

                # Create async engine with connection pooling
                self._engine = create_async_engine(
                    self.database_url,
                    echo=self.echo,
                    poolclass=QueuePool,
                    pool_size=self.pool_size,
                    max_overflow=self.max_overflow,
                    pool_timeout=self.pool_timeout,
                    pool_recycle=self.pool_recycle,
                    pool_pre_ping=True,  # Test connections before using
                )

                # Create session factory
                self._session_factory = async_sessionmaker(
                    self._engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )

                # Test the connection
                async with self._engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))

                self._is_connected = True
                logger.info("database_connected_successfully")
                return

            except OperationalError as e:
                logger.warning(
                    "database_connection_failed",
                    attempt=attempt,
                    error=str(e),
                    retry_delay=self.retry_delay
                )

                if attempt < self.connect_retries:
                    await asyncio.sleep(self.retry_delay * attempt)
                else:
                    raise DatabaseError(
                        "Failed to connect to database after all retries",
                        details={
                            "attempts": self.connect_retries,
                            "error": str(e)
                        }
                    ) from e

            except Exception as e:
                logger.error(
                    "database_connection_error",
                    attempt=attempt,
                    error=str(e)
                )
                raise DatabaseError(
                    f"Unexpected error connecting to database: {e}",
                    details={"error": str(e)}
                ) from e

    async def disconnect(self) -> None:
        """
        Close database connection and cleanup resources.
        """
        if not self._is_connected:
            logger.warning("Database not connected")
            return

        try:
            if self._engine:
                await self._engine.dispose()
                logger.info("database_disconnected")

            self._engine = None
            self._session_factory = None
            self._is_connected = False

        except Exception as e:
            logger.error("database_disconnect_error", error=str(e))
            raise DatabaseError(
                f"Error disconnecting from database: {e}",
                details={"error": str(e)}
            ) from e

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session using context manager.

        Yields:
            AsyncSession: Database session

        Raises:
            DatabaseError: If session cannot be created

        Example:
            >>> async with db_manager.get_session() as session:
            >>>     result = await session.execute(select(Trade))
            >>>     trades = result.scalars().all()
        """
        if not self._is_connected or not self._session_factory:
            raise DatabaseError("Database not connected")

        session: Optional[AsyncSession] = None
        try:
            session = self._session_factory()
            yield session
            await session.commit()

        except SQLAlchemyError as e:
            if session:
                await session.rollback()
            logger.error("database_session_error", error=str(e))
            raise DatabaseError(
                f"Database session error: {e}",
                details={"error": str(e)}
            ) from e

        except Exception as e:
            if session:
                await session.rollback()
            logger.error("unexpected_session_error", error=str(e))
            raise

        finally:
            if session:
                await session.close()

    async def execute_query(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None
    ) -> Any:
        """
        Execute a raw SQL query.

        Args:
            query: SQL query to execute
            params: Optional query parameters

        Returns:
            Query result

        Raises:
            DatabaseError: If query execution fails
        """
        async with self.get_session() as session:
            try:
                result = await session.execute(text(query), params or {})
                return result

            except SQLAlchemyError as e:
                logger.error("query_execution_error", query=query, error=str(e))
                raise DatabaseError(
                    f"Failed to execute query: {e}",
                    details={"query": query, "error": str(e)}
                ) from e

    async def health_check(self) -> bool:
        """
        Perform database health check.

        Returns:
            True if database is healthy, False otherwise
        """
        if not self._is_connected or not self._engine:
            logger.warning("health_check_failed", reason="not_connected")
            return False

        try:
            async with self._engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.debug("health_check_passed")
            return True

        except Exception as e:
            logger.error("health_check_failed", error=str(e))
            return False

    async def get_pool_status(self) -> dict[str, Any]:
        """
        Get current connection pool status.

        Returns:
            Dictionary with pool statistics
        """
        if not self._engine:
            return {"status": "not_connected"}

        pool = self._engine.pool
        return {
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "timeout": self.pool_timeout,
        }

    async def create_all_tables(self) -> None:
        """
        Create all database tables.

        This should typically be done via Alembic migrations,
        but is provided for testing and initial setup.

        Raises:
            DatabaseError: If table creation fails
        """
        if not self._engine:
            raise DatabaseError("Database not connected")

        try:
            from src.models.base import Base

            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            logger.info("database_tables_created")

        except Exception as e:
            logger.error("table_creation_error", error=str(e))
            raise DatabaseError(
                f"Failed to create tables: {e}",
                details={"error": str(e)}
            ) from e

    async def drop_all_tables(self) -> None:
        """
        Drop all database tables.

        WARNING: This will delete all data!
        Should only be used in testing or development.

        Raises:
            DatabaseError: If table drop fails
        """
        if not self._engine:
            raise DatabaseError("Database not connected")

        try:
            from src.models.base import Base

            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)

            logger.warning("database_tables_dropped")

        except Exception as e:
            logger.error("table_drop_error", error=str(e))
            raise DatabaseError(
                f"Failed to drop tables: {e}",
                details={"error": str(e)}
            ) from e

    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._is_connected

    def __repr__(self) -> str:
        """Return string representation of database manager."""
        return (
            f"DatabaseManager(connected={self._is_connected}, "
            f"pool_size={self.pool_size})"
        )


# Singleton instance for global access
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """
    Get the global database manager instance.

    Returns:
        DatabaseManager instance

    Raises:
        DatabaseError: If database manager not initialized
    """
    global _db_manager
    if _db_manager is None:
        raise DatabaseError("Database manager not initialized")
    return _db_manager


def initialize_db_manager(database_url: str, **kwargs: Any) -> DatabaseManager:
    """
    Initialize the global database manager.

    Args:
        database_url: Database connection URL
        **kwargs: Additional arguments for DatabaseManager

    Returns:
        Initialized DatabaseManager instance
    """
    global _db_manager
    _db_manager = DatabaseManager(database_url, **kwargs)
    logger.info("database_manager_initialized")
    return _db_manager
