"""
Triangle arbitrage detector.

Detects opportunities for circular trading within a single exchange
(e.g., USD -> BTC -> ETH -> USD).
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List

from src.core.logger import get_logger
from src.detectors.base_detector import BaseDetector
from src.market_data.aggregator import MarketDataAggregator
from src.models.opportunity import ArbitrageOpportunity

logger = get_logger(__name__, component="triangle_detector")


class TriangleDetector(BaseDetector):
    """
    Detects triangle arbitrage opportunities.

    Strategy: Execute circular trades within a single exchange
    Example: USD -> BTC -> ETH -> USD
    """

    def __init__(self, aggregator: MarketDataAggregator, config: Any) -> None:
        """
        Initialize triangle detector.

        Args:
            aggregator: Market data aggregator instance
            config: Configuration manager
        """
        super().__init__("triangle", config)
        self.aggregator = aggregator

        # Get profit threshold from config
        trading_config = getattr(config, "trading", None)
        if trading_config:
            thresholds = getattr(trading_config, "profit_thresholds", None)
            if thresholds:
                self.min_profit_percent = Decimal(str(getattr(thresholds, "min_profit_percent", 0.5)))
            else:
                self.min_profit_percent = Decimal("0.5")
        else:
            self.min_profit_percent = Decimal("0.5")

    async def detect(self, symbols: List[str]) -> List[ArbitrageOpportunity]:
        """
        Detect triangle arbitrage opportunities.

        Args:
            symbols: List of trading pair symbols (not used directly,
                    triangles are found based on available pairs)

        Returns:
            List of detected opportunities
        """
        opportunities = []

        # Check each exchange for triangle opportunities
        for exchange_name in self.aggregator.exchanges.keys():
            raw_opps = self.aggregator.spread_calculator.find_triangle_arbitrage(
                exchange_name
            )

            for opp in raw_opps:
                # Filter by minimum profit threshold
                if opp["net_profit_percent"] < self.min_profit_percent:
                    self.opportunities_filtered += 1
                    continue

                # Calculate confidence and risk
                confidence = self._calculate_confidence(opp)
                risk = self._calculate_risk(opp)

                # Estimate quantities and USD profit
                # For triangle arbitrage, we use a standard test amount
                test_amount = Decimal("1000")  # $1000 test amount
                estimated_profit_usd = test_amount * (
                    opp["net_profit_percent"] / 100
                )

                # Convert to ArbitrageOpportunity model
                opportunity = ArbitrageOpportunity(
                    strategy="triangle",
                    exchange=opp["exchange"],
                    path=opp["path"],
                    symbol=None,  # Triangle involves multiple pairs
                    buy_price=Decimal("0"),  # Not applicable for triangle
                    sell_price=Decimal("0"),  # Not applicable for triangle
                    gross_profit_percent=opp["gross_profit_percent"],
                    gross_profit_usd=estimated_profit_usd
                    * (opp["gross_profit_percent"] / opp["net_profit_percent"]),
                    net_profit_percent=opp["net_profit_percent"],
                    net_profit_usd=estimated_profit_usd,
                    total_fees_percent=opp["total_fees_percent"],
                    total_fees_usd=test_amount * (opp["total_fees_percent"] / 100),
                    max_quantity=Decimal(
                        "1.0"
                    ),  # Placeholder - real calculation needed
                    slippage_estimate_percent=Decimal("0.1"),  # Estimate
                    confidence_score=confidence,
                    risk_score=risk,
                    expires_at=datetime.utcnow() + timedelta(seconds=15),  # Shorter window
                )

                opportunities.append(opportunity)
                self.opportunities_detected += 1

                logger.info(
                    "triangle_opportunity_detected",
                    exchange=opp["exchange"],
                    path=opp["path"],
                    net_profit=f"{opp['net_profit_percent']:.2f}%",
                    confidence=f"{confidence:.2f}",
                )

        return opportunities

    def _calculate_confidence(self, opp: Dict) -> Decimal:
        """
        Calculate confidence score for triangle opportunity.

        Args:
            opp: Opportunity dictionary

        Returns:
            Confidence score between 0 and 1
        """
        score = Decimal("1.0")

        # Reduce confidence if profit is very high (likely stale or error)
        if opp["net_profit_percent"] > 3:
            score -= Decimal("0.4")

        # Triangle arbitrage typically has lower confidence than cross-exchange
        # due to execution complexity (3 trades vs 2)
        score -= Decimal("0.1")

        return max(score, Decimal("0"))

    def _calculate_risk(self, opp: Dict) -> Decimal:
        """
        Calculate risk score for triangle opportunity.

        Args:
            opp: Opportunity dictionary

        Returns:
            Risk score between 0 and 1
        """
        risk = Decimal("0.2")  # Higher base risk than cross-exchange

        # Triangle arbitrage has execution risk across 3 trades
        risk += Decimal("0.2")

        # Higher risk if profit margin is small
        if opp["net_profit_percent"] < 0.75:
            risk += Decimal("0.2")

        return min(risk, Decimal("1.0"))
