"""
Base detector class for arbitrage strategies.

Provides common interface and utilities for all detector implementations.
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List

from src.core.logger import get_logger
from src.models.opportunity import ArbitrageOpportunity

logger = get_logger(__name__, component="detector")


class BaseDetector(ABC):
    """
    Abstract base class for arbitrage opportunity detectors.

    All detector implementations must inherit from this class and implement
    the detect() method.
    """

    def __init__(self, strategy_name: str, config: Any) -> None:
        """
        Initialize base detector.

        Args:
            strategy_name: Name of the strategy (e.g., "cross_exchange")
            config: Configuration manager
        """
        self.strategy_name = strategy_name
        self.config = config

        # Statistics
        self.opportunities_detected = 0
        self.opportunities_filtered = 0

    @abstractmethod
    async def detect(self, symbols: List[str]) -> List[ArbitrageOpportunity]:
        """
        Detect arbitrage opportunities for given symbols.

        Args:
            symbols: List of trading pair symbols to analyze

        Returns:
            List of detected opportunities
        """
        pass

    def _calculate_usd_profit(
        self, profit_percent: Decimal, quantity: Decimal, price: Decimal
    ) -> Decimal:
        """
        Calculate USD profit for an opportunity.

        Args:
            profit_percent: Profit percentage
            quantity: Trade quantity
            price: Trade price

        Returns:
            Profit in USD
        """
        position_size = quantity * price
        return position_size * (profit_percent / 100)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get detector statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "strategy": self.strategy_name,
            "opportunities_detected": self.opportunities_detected,
            "opportunities_filtered": self.opportunities_filtered,
            "detection_rate": (
                self.opportunities_detected
                / max(1, self.opportunities_detected + self.opportunities_filtered)
                * 100
            ),
        }
