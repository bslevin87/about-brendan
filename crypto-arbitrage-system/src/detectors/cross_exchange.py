"""
Cross-exchange arbitrage detector.

Detects opportunities to buy on one exchange and sell on another
for immediate profit.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List

from src.core.logger import get_logger
from src.detectors.base_detector import BaseDetector
from src.market_data.aggregator import MarketDataAggregator
from src.models.opportunity import ArbitrageOpportunity

logger = get_logger(__name__, component="cross_exchange_detector")


class CrossExchangeDetector(BaseDetector):
    """
    Detects cross-exchange arbitrage opportunities.

    Strategy: Buy on Exchange A, Sell on Exchange B
    """

    def __init__(self, aggregator: MarketDataAggregator, config: Any) -> None:
        """
        Initialize cross-exchange detector.

        Args:
            aggregator: Market data aggregator instance
            config: Configuration manager
        """
        super().__init__("cross_exchange", config)
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
        Detect arbitrage opportunities for given symbols.

        Args:
            symbols: List of trading pair symbols to analyze

        Returns:
            List of detected opportunities
        """
        opportunities = []

        for symbol in symbols:
            # Get opportunities from spread calculator
            raw_opps = self.aggregator.spread_calculator.calculate_cross_exchange_spread(
                symbol, list(self.aggregator.exchanges.keys())
            )

            for opp in raw_opps:
                # Filter by minimum profit threshold
                if opp["net_profit_percent"] < self.min_profit_percent:
                    self.opportunities_filtered += 1
                    continue

                # Calculate confidence score (0-1)
                confidence = self._calculate_confidence(opp)

                # Calculate risk score (0-1)
                risk = self._calculate_risk(opp)

                # Convert to ArbitrageOpportunity model
                opportunity = ArbitrageOpportunity(
                    strategy="cross_exchange",
                    buy_exchange=opp["buy_exchange"],
                    sell_exchange=opp["sell_exchange"],
                    symbol=opp["symbol"],
                    buy_price=opp["buy_price"],
                    sell_price=opp["sell_price"],
                    gross_profit_percent=opp["gross_profit_percent"],
                    gross_profit_usd=self._calculate_usd_profit(
                        opp["gross_profit_percent"],
                        opp["max_quantity"],
                        opp["buy_price"],
                    ),
                    net_profit_percent=opp["net_profit_percent"],
                    net_profit_usd=self._calculate_usd_profit(
                        opp["net_profit_percent"],
                        opp["max_quantity"],
                        opp["buy_price"],
                    ),
                    total_fees_percent=opp["total_fees_percent"],
                    total_fees_usd=self._calculate_usd_profit(
                        opp["total_fees_percent"],
                        opp["max_quantity"],
                        opp["buy_price"],
                    ),
                    max_quantity=opp["max_quantity"],
                    slippage_estimate_percent=opp["slippage_percent"],
                    confidence_score=confidence,
                    risk_score=risk,
                    expires_at=datetime.utcnow()
                    + timedelta(seconds=30),  # 30 second window
                )

                opportunities.append(opportunity)
                self.opportunities_detected += 1

                logger.info(
                    "cross_exchange_opportunity_detected",
                    symbol=symbol,
                    buy_exchange=opp["buy_exchange"],
                    sell_exchange=opp["sell_exchange"],
                    net_profit=f"{opp['net_profit_percent']:.2f}%",
                    confidence=f"{confidence:.2f}",
                )

        return opportunities

    def _calculate_confidence(self, opp: Dict) -> Decimal:
        """
        Calculate confidence score based on various factors.

        Args:
            opp: Opportunity dictionary

        Returns:
            Confidence score between 0 and 1
        """
        score = Decimal("1.0")

        # Reduce confidence if spread is very large (might be stale data)
        if opp["gross_profit_percent"] > 5:
            score -= Decimal("0.3")

        # Reduce confidence if liquidity is low
        if opp["max_quantity"] < Decimal("0.01"):  # Very low quantity
            score -= Decimal("0.2")

        # Reduce confidence if slippage is high
        if opp["slippage_percent"] > 1:
            score -= Decimal("0.2")

        return max(score, Decimal("0"))

    def _calculate_risk(self, opp: Dict) -> Decimal:
        """
        Calculate risk score.

        Args:
            opp: Opportunity dictionary

        Returns:
            Risk score between 0 and 1
        """
        risk = Decimal("0.1")  # Base risk

        # Higher risk if profit margin is small
        if opp["net_profit_percent"] < 0.5:
            risk += Decimal("0.3")

        # Higher risk if slippage is high
        risk += opp["slippage_percent"] / 10

        return min(risk, Decimal("1.0"))
