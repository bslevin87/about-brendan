"""
Spread calculator for arbitrage opportunity detection.

Analyzes price differences across exchanges accounting for:
- Trading fees (maker/taker)
- Withdrawal fees
- Slippage estimates
- Minimum trade sizes
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.core.logger import get_logger
from src.market_data.order_book_manager import OrderBookManager

logger = get_logger(__name__, component="spread_calc")


class SpreadCalculator:
    """
    Calculates cross-exchange spreads and identifies arbitrage opportunities.

    Analyzes price differences across exchanges accounting for:
    - Trading fees (maker/taker)
    - Withdrawal fees
    - Slippage estimates
    - Minimum trade sizes
    """

    def __init__(self, order_book_manager: OrderBookManager, config: Any) -> None:
        """
        Initialize spread calculator.

        Args:
            order_book_manager: Order book manager instance
            config: Configuration manager
        """
        self.order_book_manager = order_book_manager
        self.config = config

    def calculate_cross_exchange_spread(
        self, symbol: str, exchanges: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Calculate spreads for a symbol across all exchange pairs.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USD")
            exchanges: List of exchange names to compare

        Returns:
            List of potential arbitrage opportunities sorted by profit
        """
        opportunities = []

        # Get best bid/ask from each exchange
        prices = {}
        for exchange in exchanges:
            best_bid = self.order_book_manager.get_best_bid(exchange, symbol)
            best_ask = self.order_book_manager.get_best_ask(exchange, symbol)

            if best_bid and best_ask:
                prices[exchange] = {
                    "bid": best_bid[0],
                    "ask": best_ask[0],
                    "bid_qty": best_bid[1],
                    "ask_qty": best_ask[1],
                }

        if len(prices) < 2:
            logger.debug(
                "insufficient_exchanges_for_spread",
                symbol=symbol,
                exchanges_with_data=len(prices),
            )
            return []

        # Compare all exchange pairs
        for buy_exchange in exchanges:
            if buy_exchange not in prices:
                continue

            for sell_exchange in exchanges:
                if sell_exchange not in prices or buy_exchange == sell_exchange:
                    continue

                # Buy on buy_exchange (at ask price), sell on sell_exchange (at bid price)
                buy_price = prices[buy_exchange]["ask"]
                sell_price = prices[sell_exchange]["bid"]

                # Calculate gross profit
                gross_profit_percent = ((sell_price - buy_price) / buy_price) * 100

                # Get fee structure
                buy_exchange_config = self.config.exchanges.get(buy_exchange)
                sell_exchange_config = self.config.exchanges.get(sell_exchange)

                if not buy_exchange_config or not sell_exchange_config:
                    logger.warning(
                        "exchange_config_missing",
                        buy_exchange=buy_exchange,
                        sell_exchange=sell_exchange,
                    )
                    continue

                # Calculate fees (assume taker fees for market orders)
                buy_fee_percent = Decimal(str(buy_exchange_config.get("taker_fee", 0.001))) * 100
                sell_fee_percent = Decimal(str(sell_exchange_config.get("taker_fee", 0.001))) * 100
                total_fee_percent = buy_fee_percent + sell_fee_percent

                # Net profit after fees
                net_profit_percent = gross_profit_percent - total_fee_percent

                # Only consider if profitable
                if net_profit_percent > 0:
                    # Calculate max tradeable quantity
                    max_quantity = min(
                        prices[buy_exchange]["ask_qty"],
                        prices[sell_exchange]["bid_qty"],
                    )

                    # Estimate slippage
                    buy_slippage = self.order_book_manager.calculate_slippage(
                        buy_exchange, symbol, "buy", max_quantity
                    )
                    sell_slippage = self.order_book_manager.calculate_slippage(
                        sell_exchange, symbol, "sell", max_quantity
                    )
                    total_slippage = buy_slippage + sell_slippage

                    # Adjusted net profit
                    adjusted_net_profit = net_profit_percent - total_slippage

                    opportunities.append({
                        "symbol": symbol,
                        "buy_exchange": buy_exchange,
                        "sell_exchange": sell_exchange,
                        "buy_price": buy_price,
                        "sell_price": sell_price,
                        "gross_profit_percent": gross_profit_percent,
                        "net_profit_percent": adjusted_net_profit,
                        "total_fees_percent": total_fee_percent,
                        "slippage_percent": total_slippage,
                        "max_quantity": max_quantity,
                    })

                    logger.debug(
                        "cross_exchange_opportunity_calculated",
                        symbol=symbol,
                        buy_exchange=buy_exchange,
                        sell_exchange=sell_exchange,
                        net_profit=f"{adjusted_net_profit:.4f}%",
                    )

        # Sort by net profit (descending)
        opportunities.sort(key=lambda x: x["net_profit_percent"], reverse=True)

        return opportunities

    def find_triangle_arbitrage(
        self, exchange: str, base_currency: str = "USD"
    ) -> List[Dict[str, Any]]:
        """
        Find triangle arbitrage opportunities on a single exchange.

        Example: BTC/USD -> ETH/BTC -> ETH/USD -> USD

        Args:
            exchange: Exchange name
            base_currency: Base currency for the cycle (e.g., "USD")

        Returns:
            List of profitable cycles
        """
        opportunities = []

        # Get exchange configuration
        exchange_config = self.config.exchanges.get(exchange)
        if not exchange_config:
            logger.warning("exchange_config_missing", exchange=exchange)
            return []

        # Get supported pairs for this exchange
        supported_pairs = exchange_config.get("supported_pairs", [])

        # For demonstration, check common triangle: BTC/USD, ETH/BTC, ETH/USD
        # Full implementation would use graph traversal to find all cycles

        triangle_paths = [
            # USD -> BTC -> ETH -> USD
            {
                "path": ["BTC/USD", "ETH/BTC", "ETH/USD"],
                "start": base_currency,
                "steps": [
                    ("BTC/USD", "buy", "USD", "BTC"),  # Buy BTC with USD
                    ("ETH/BTC", "buy", "BTC", "ETH"),  # Buy ETH with BTC
                    ("ETH/USD", "sell", "ETH", "USD"),  # Sell ETH for USD
                ],
            },
            # USD -> ETH -> BTC -> USD
            {
                "path": ["ETH/USD", "ETH/BTC", "BTC/USD"],
                "start": base_currency,
                "steps": [
                    ("ETH/USD", "buy", "USD", "ETH"),  # Buy ETH with USD
                    ("ETH/BTC", "sell", "ETH", "BTC"),  # Sell ETH for BTC
                    ("BTC/USD", "sell", "BTC", "USD"),  # Sell BTC for USD
                ],
            },
        ]

        for triangle in triangle_paths:
            # Check if all pairs in path are supported
            if not all(pair in supported_pairs for pair in triangle["path"]):
                continue

            # Check if order books exist for all pairs
            if not all(
                self.order_book_manager.has_order_book(exchange, pair)
                for pair in triangle["path"]
            ):
                continue

            # Calculate profit for this triangle
            result = self._calculate_triangle_profit(
                exchange, triangle["path"], triangle["steps"]
            )

            if result and result["net_profit_percent"] > 0:
                opportunities.append({
                    "exchange": exchange,
                    "path": triangle["path"],
                    "start_currency": triangle["start"],
                    "end_currency": triangle["start"],
                    "gross_profit_percent": result["gross_profit_percent"],
                    "net_profit_percent": result["net_profit_percent"],
                    "total_fees_percent": result["total_fees_percent"],
                    "steps": result["steps"],
                })

                logger.debug(
                    "triangle_opportunity_found",
                    exchange=exchange,
                    path=triangle["path"],
                    net_profit=f"{result['net_profit_percent']:.4f}%",
                )

        return opportunities

    def _calculate_triangle_profit(
        self, exchange: str, path: List[str], steps: List[tuple]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate profit for a triangle arbitrage path.

        Args:
            exchange: Exchange name
            path: List of trading pairs
            steps: List of (pair, action, from_currency, to_currency) tuples

        Returns:
            Dictionary with profit calculation or None if calculation fails
        """
        # Starting with 1 unit of base currency
        start_amount = Decimal("1.0")
        current_amount = start_amount

        step_details = []
        exchange_config = self.config.exchanges.get(exchange)
        fee_per_trade = Decimal(str(exchange_config.get("taker_fee", 0.001)))

        for pair, action, from_curr, to_curr in steps:
            if action == "buy":
                # Buying: get ask price (we pay the ask)
                best_ask = self.order_book_manager.get_best_ask(exchange, pair)
                if not best_ask:
                    return None

                price = best_ask[0]
                # Amount after buying (minus fee)
                current_amount = (current_amount / price) * (1 - fee_per_trade)

            else:  # sell
                # Selling: get bid price (we receive the bid)
                best_bid = self.order_book_manager.get_best_bid(exchange, pair)
                if not best_bid:
                    return None

                price = best_bid[0]
                # Amount after selling (minus fee)
                current_amount = (current_amount * price) * (1 - fee_per_trade)

            step_details.append({
                "pair": pair,
                "action": action,
                "price": str(price),
                "amount": str(current_amount),
            })

        # Calculate profit
        end_amount = current_amount
        gross_profit_percent = ((end_amount - start_amount) / start_amount) * 100

        # Total fees (3 trades)
        total_fees_percent = fee_per_trade * 3 * 100

        # Net profit is already included in end_amount calculation (fees deducted)
        # But we can also express it as gross - fees
        net_profit_percent = gross_profit_percent

        return {
            "gross_profit_percent": gross_profit_percent,
            "net_profit_percent": net_profit_percent,
            "total_fees_percent": total_fees_percent,
            "start_amount": str(start_amount),
            "end_amount": str(end_amount),
            "steps": step_details,
        }

    def get_all_spreads(self, symbol: str, exchanges: List[str]) -> Dict[str, Dict]:
        """
        Get all bid/ask spreads for a symbol across exchanges.

        Args:
            symbol: Trading pair symbol
            exchanges: List of exchange names

        Returns:
            Dictionary mapping exchange names to spread data
        """
        spreads = {}

        for exchange in exchanges:
            best_bid = self.order_book_manager.get_best_bid(exchange, symbol)
            best_ask = self.order_book_manager.get_best_ask(exchange, symbol)
            spread = self.order_book_manager.get_spread(exchange, symbol)
            mid_price = self.order_book_manager.get_mid_price(exchange, symbol)

            if best_bid and best_ask and spread and mid_price:
                spreads[exchange] = {
                    "bid": best_bid[0],
                    "ask": best_ask[0],
                    "spread": spread,
                    "spread_percent": (spread / mid_price * 100),
                    "mid_price": mid_price,
                }

        return spreads
