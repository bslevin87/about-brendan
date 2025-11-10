"""
Position tracking system.

Tracks all open positions across exchanges, providing:
- Position counts by exchange and symbol
- Total exposure calculations
- Unrealized P&L tracking
- Position lifecycle management
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from src.core.logger import get_logger
from src.risk.models import Position

logger = get_logger(__name__, component="position_tracker")


class PositionTracker:
    """
    Tracks all open positions across exchanges.

    Provides real-time view of:
    - Positions per exchange
    - Positions per symbol
    - Total exposure
    - Unrealized P&L
    """

    def __init__(self):
        """Initialize position tracker."""
        self.positions: Dict[str, Position] = {}  # position_id -> Position
        logger.info("Position tracker initialized")

    def add_position(
        self,
        position_id: str,
        exchange: str,
        symbol: str,
        side: str,
        quantity: Decimal,
        entry_price: Decimal,
    ) -> None:
        """
        Add new position.

        Args:
            position_id: Unique position identifier
            exchange: Exchange name
            symbol: Trading pair (e.g., "BTC/USD")
            side: Position side ("long" or "short")
            quantity: Position size
            entry_price: Entry price
        """
        position = Position(
            position_id=position_id,
            exchange=exchange,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,  # Initially same as entry
            unrealized_pnl_usd=Decimal("0"),
            opened_at=datetime.utcnow(),
        )

        self.positions[position_id] = position

        logger.info(
            "position_opened",
            position_id=position_id,
            exchange=exchange,
            symbol=symbol,
            side=side,
            quantity=float(quantity),
            entry_price=float(entry_price),
        )

    def remove_position(self, position_id: str) -> Optional[Position]:
        """
        Remove closed position.

        Args:
            position_id: Position identifier to remove

        Returns:
            Removed Position if it existed, None otherwise
        """
        position = self.positions.pop(position_id, None)

        if position:
            logger.info(
                "position_closed",
                position_id=position_id,
                pnl_usd=float(position.unrealized_pnl_usd),
                pnl_percent=float(position.pnl_percent),
            )

        return position

    def update_position_price(
        self, position_id: str, current_price: Decimal
    ) -> None:
        """
        Update position with current market price.

        Args:
            position_id: Position identifier
            current_price: Current market price
        """
        if position_id not in self.positions:
            return

        position = self.positions[position_id]
        position.current_price = current_price

        # Calculate unrealized P&L
        if position.side == "long":
            pnl = (current_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - current_price) * position.quantity

        position.unrealized_pnl_usd = pnl

    def get_positions_by_exchange(self, exchange: str) -> List[Position]:
        """
        Get all positions for an exchange.

        Args:
            exchange: Exchange name

        Returns:
            List of positions on that exchange
        """
        return [p for p in self.positions.values() if p.exchange == exchange]

    def get_positions_by_symbol(self, symbol: str) -> List[Position]:
        """
        Get all positions for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            List of positions for that symbol
        """
        return [p for p in self.positions.values() if p.symbol == symbol]

    def get_position_count_by_exchange(self, exchange: str) -> int:
        """
        Count positions on an exchange.

        Args:
            exchange: Exchange name

        Returns:
            Number of open positions on exchange
        """
        return len(self.get_positions_by_exchange(exchange))

    def get_total_position_count(self) -> int:
        """
        Total number of open positions.

        Returns:
            Count of all open positions
        """
        return len(self.positions)

    def get_total_exposure(self) -> Decimal:
        """
        Total exposure across all positions in USD.

        Returns:
            Sum of all position exposures
        """
        return sum(p.exposure_usd for p in self.positions.values())

    def get_exposure_by_exchange(self, exchange: str) -> Decimal:
        """
        Total exposure on a specific exchange.

        Args:
            exchange: Exchange name

        Returns:
            Total exposure on that exchange
        """
        positions = self.get_positions_by_exchange(exchange)
        return sum(p.exposure_usd for p in positions)

    def get_exposure_by_symbol(self, symbol: str) -> Decimal:
        """
        Total exposure for a specific symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Total exposure for that symbol
        """
        positions = self.get_positions_by_symbol(symbol)
        return sum(p.exposure_usd for p in positions)

    def get_total_unrealized_pnl(self) -> Decimal:
        """
        Total unrealized P&L across all positions.

        Returns:
            Sum of unrealized P&L from all positions
        """
        return sum(p.unrealized_pnl_usd for p in self.positions.values())

    def get_position(self, position_id: str) -> Optional[Position]:
        """
        Get position by ID.

        Args:
            position_id: Position identifier

        Returns:
            Position if found, None otherwise
        """
        return self.positions.get(position_id)

    def clear_all_positions(self) -> int:
        """
        Clear all positions (emergency use only).

        Returns:
            Number of positions cleared
        """
        count = len(self.positions)
        self.positions.clear()
        logger.warning(f"All positions cleared (count: {count})")
        return count

    def get_stats(self) -> Dict[str, any]:
        """
        Get position tracking statistics.

        Returns:
            Dictionary with position statistics
        """
        return {
            "total_positions": self.get_total_position_count(),
            "total_exposure_usd": float(self.get_total_exposure()),
            "total_unrealized_pnl_usd": float(self.get_total_unrealized_pnl()),
            "positions_by_exchange": {
                exchange: self.get_position_count_by_exchange(exchange)
                for exchange in set(p.exchange for p in self.positions.values())
            },
        }
