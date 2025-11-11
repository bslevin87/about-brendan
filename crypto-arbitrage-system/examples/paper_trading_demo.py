#!/usr/bin/env python3
"""
Paper Trading Demo

Demonstrates the system running in paper trading mode:
- Simulates trades with fake capital ($10,000)
- Tracks P&L as if trades were real
- No actual orders placed on exchanges
- Perfect for strategy validation

Usage:
    python examples/paper_trading_demo.py
"""

import asyncio
import sys
from decimal import Decimal
from datetime import datetime

sys.path.insert(0, '.')

from src.core.config import ConfigManager
from src.core.logger import get_logger
from src.exchanges.rate_limiter import RateLimiter
from src.market_data.aggregator import MarketDataAggregator
from src.detectors.cross_exchange import CrossExchangeDetector
from src.risk.manager import RiskManager
from src.execution.engine import ExecutionEngine
from src.models.opportunity import ArbitrageOpportunity

# For demo, we'll use a mock exchange
from src.exchanges.models import Ticker, OrderBook
from src.exchanges.base import BaseExchange


class MockExchange(BaseExchange):
    """Mock exchange for paper trading demo."""

    async def connect(self) -> None:
        self._is_connected = True

    async def disconnect(self) -> None:
        self._is_connected = False

    async def health_check(self) -> bool:
        return True

    async def fetch_ticker(self, symbol: str) -> Ticker:
        """Return fake ticker data with slight price differences."""
        base_prices = {
            "BTC/USD": Decimal("50000"),
            "ETH/USD": Decimal("3000"),
        }

        base_price = base_prices.get(symbol, Decimal("1000"))

        # Add small randomness based on exchange name
        if self.name == "Kraken":
            spread_offset = Decimal("0.998")  # Slightly lower
        else:
            spread_offset = Decimal("1.002")  # Slightly higher

        mid_price = base_price * spread_offset
        spread = mid_price * Decimal("0.001")  # 0.1% spread

        return Ticker(
            symbol=symbol,
            bid=mid_price - spread,
            ask=mid_price + spread,
            last=mid_price,
            volume_24h=Decimal("1000"),
            timestamp=datetime.utcnow()
        )

    async def fetch_order_book(self, symbol: str, depth: int = 10) -> OrderBook:
        ticker = await self.fetch_ticker(symbol)
        return OrderBook(
            symbol=symbol,
            bids=[[ticker.bid, Decimal("1.0")]],
            asks=[[ticker.ask, Decimal("1.0")]],
            timestamp=datetime.utcnow()
        )

    async def fetch_balances(self):
        """Return fake balances for demo."""
        return []

    async def create_order(self, **kwargs):
        """Simulate order creation."""
        return {"order_id": "paper_trade_123", "status": "filled"}

    async def fetch_order(self, order_id: str):
        return {"order_id": order_id, "status": "filled"}

    async def cancel_order(self, order_id: str):
        return True


async def main():
    """Run paper trading demo."""
    print("\n" + "=" * 70)
    print("  PAPER TRADING DEMO")
    print("=" * 70)
    print()
    print("💰 Starting Capital: $10,000 (simulated)")
    print("📊 Mode: PAPER TRADING (no real money)")
    print()

    # Initialize config
    print("1. Loading Configuration...")
    config = ConfigManager()
    logger = get_logger(__name__)

    if config.trading.mode != "paper":
        print("   ⚠️  Warning: Config is not in paper mode!")
        print(f"   Current mode: {config.trading.mode}")
        print("   To use paper trading, set mode='paper' in config/trading.yaml")
        print()

    print(f"   ✅ Mode: {config.trading.mode}")
    print(f"   ✅ Capital: ${config.trading.capital_allocation.total_capital_usd:,.2f}")
    print(f"   ✅ Risk Profile: {config.risk.active_profile}")
    print()

    # Create mock exchanges for demo
    print("2. Initializing Mock Exchanges (for demo)...")
    exchanges = {}

    kraken_config = {"name": "Kraken", "api_url": "mock", "ws_url": "mock"}
    exchanges["Kraken"] = MockExchange(
        config=kraken_config,
        rate_limiter=RateLimiter(15, 20, "kraken")
    )
    await exchanges["Kraken"].connect()
    print("   ✅ Kraken (mock) ready")

    coinbase_config = {"name": "Coinbase Advanced", "api_url": "mock", "ws_url": "mock"}
    exchanges["Coinbase Advanced"] = MockExchange(
        config=coinbase_config,
        rate_limiter=RateLimiter(10, 15, "coinbase")
    )
    await exchanges["Coinbase Advanced"].connect()
    print("   ✅ Coinbase Advanced (mock) ready")
    print()

    # Initialize risk manager
    print("3. Initializing Risk Management...")
    risk_manager = RiskManager(config=config)
    print(f"   ✅ Max position size: {risk_manager.risk_limits.max_position_size_percent}%")
    print(f"   ✅ Max daily loss: ${risk_manager.risk_limits.max_daily_loss_usd:,.2f}")
    print()

    # Initialize execution engine
    print("4. Initializing Execution Engine...")
    engine = ExecutionEngine(
        exchanges=exchanges,
        risk_manager=risk_manager,
        config=config
    )
    await engine.initialize()
    print("   ✅ Execution engine ready")
    print()

    # Create test opportunities
    print("5. Simulating Arbitrage Opportunities...")
    print("-" * 70)
    print()

    opportunities = [
        ArbitrageOpportunity(
            strategy="cross_exchange",
            buy_exchange="Kraken",
            sell_exchange="Coinbase Advanced",
            symbol="BTC/USD",
            buy_price=Decimal("49900"),
            sell_price=Decimal("50100"),
            gross_profit_percent=Decimal("0.40"),
            gross_profit_usd=Decimal("200"),
            net_profit_percent=Decimal("0.32"),
            net_profit_usd=Decimal("160"),
            total_fees_percent=Decimal("0.08"),
            total_fees_usd=Decimal("40"),
            max_quantity=Decimal("0.1"),
            slippage_estimate_percent=Decimal("0.05"),
            confidence_score=Decimal("0.90"),
            risk_score=Decimal("0.2")
        ),
        ArbitrageOpportunity(
            strategy="cross_exchange",
            buy_exchange="Kraken",
            sell_exchange="Coinbase Advanced",
            symbol="ETH/USD",
            buy_price=Decimal("2990"),
            sell_price=Decimal("3010"),
            gross_profit_percent=Decimal("0.67"),
            gross_profit_usd=Decimal("20"),
            net_profit_percent=Decimal("0.52"),
            net_profit_usd=Decimal("15.60"),
            total_fees_percent=Decimal("0.15"),
            total_fees_usd=Decimal("4.50"),
            max_quantity=Decimal("1.0"),
            slippage_estimate_percent=Decimal("0.05"),
            confidence_score=Decimal("0.85"),
            risk_score=Decimal("0.3")
        ),
    ]

    # Execute opportunities in paper trading mode
    total_profit = Decimal("0")
    successful_trades = 0

    for i, opportunity in enumerate(opportunities, 1):
        print(f"📈 Opportunity #{i}:")
        print(f"   Symbol: {opportunity.symbol}")
        print(f"   Strategy: {opportunity.strategy}")
        print(f"   Buy: {opportunity.buy_exchange} @ ${opportunity.buy_price:,.2f}")
        print(f"   Sell: {opportunity.sell_exchange} @ ${opportunity.sell_price:,.2f}")
        print(f"   Expected Profit: ${opportunity.net_profit_usd:.2f} ({opportunity.net_profit_percent:.2f}%)")
        print()

        # Execute in paper mode (dry_run=False means use config mode)
        result = await engine.execute_opportunity(opportunity, dry_run=False)

        if result.success:
            print(f"   ✅ TRADE EXECUTED (simulated)")
            print(f"   Execution ID: {result.execution_id}")
            print(f"   Profit: ${result.profit_usd:.2f}")
            total_profit += result.profit_usd
            successful_trades += 1
        else:
            print(f"   ❌ TRADE REJECTED")
            print(f"   Reason: {result.error_message}")

        print()
        print("-" * 70)
        print()

    # Show statistics
    print("6. Paper Trading Results:")
    stats = engine.get_stats()
    print(f"   Total Executions: {stats['total_executions']}")
    print(f"   Successful: {stats['successful_executions']}")
    print(f"   Failed: {stats['failed_executions']}")
    print(f"   Success Rate: {stats['success_rate']:.1f}%")
    print()

    print("7. Simulated P&L:")
    pnl_stats = risk_manager.pnl_tracker.get_stats()
    print(f"   Total Trades: {pnl_stats['total_trades']}")
    print(f"   Total P&L: ${pnl_stats['total_pnl_usd']:.2f}")
    print(f"   Daily P&L: ${pnl_stats['daily_pnl_usd']:.2f}")
    print(f"   Win Rate: {pnl_stats['win_rate']:.1f}%")
    print()

    # Final capital
    starting_capital = config.trading.capital_allocation.total_capital_usd
    final_capital = starting_capital + float(pnl_stats['total_pnl_usd'])
    print("8. Portfolio Summary:")
    print(f"   Starting Capital: ${starting_capital:,.2f}")
    print(f"   Final Capital: ${final_capital:,.2f}")
    print(f"   Profit/Loss: ${pnl_stats['total_pnl_usd']:.2f}")
    print(f"   Return: {(pnl_stats['total_pnl_usd'] / Decimal(str(starting_capital)) * 100):.2f}%")
    print()

    print("=" * 70)
    print("  DEMO COMPLETE")
    print("=" * 70)
    print()
    print("💡 Key Takeaways:")
    print("   • Paper trading simulates real trades without risk")
    print("   • Perfect for validating strategies and risk controls")
    print("   • All P&L tracking works the same as live trading")
    print("   • Move to live trading only after extensive paper trading")
    print()
    print("📊 Next Steps:")
    print("   1. Run this demo multiple times with different scenarios")
    print("   2. Monitor for 24-48 hours in paper mode")
    print("   3. Adjust risk limits based on results")
    print("   4. Only then consider live trading with small amounts")
    print()

    # Cleanup
    for exchange in exchanges.values():
        await exchange.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
