#!/usr/bin/env python3
"""
Execution Engine Demonstration.

Demonstrates:
- Creating execution plans
- Risk validation integration
- Dry-run execution
- Order tracking
- Reconciliation
- Error handling

IMPORTANT: This demo runs in DRY-RUN mode by default for safety.
"""
import sys
import asyncio
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import ConfigManager
from src.models.opportunity import ArbitrageOpportunity
from src.risk.manager import RiskManager
from src.execution.engine import ExecutionEngine
from src.exchanges.base import MockExchange
from src.exchanges.rate_limiter import RateLimiter


def print_header(title: str):
    """Print section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def create_test_opportunity():
    """Create a test arbitrage opportunity."""
    return ArbitrageOpportunity(
        strategy="cross_exchange",
        buy_exchange="Kraken",
        sell_exchange="Coinbase Advanced",
        symbol="BTC/USD",
        buy_price=Decimal("50000"),
        sell_price=Decimal("50250"),
        gross_profit_percent=Decimal("0.5"),
        gross_profit_usd=Decimal("250"),
        net_profit_percent=Decimal("0.4"),
        net_profit_usd=Decimal("200"),
        total_fees_percent=Decimal("0.1"),
        total_fees_usd=Decimal("50"),
        max_quantity=Decimal("0.1"),
        confidence_score=Decimal("0.85"),
        risk_score=Decimal("0.3"),
    )


async def main():
    """Run execution engine demonstration."""
    print_header("EXECUTION ENGINE DEMONSTRATION")
    print("⚠️  Running in DRY-RUN mode (no real trades)")

    # Initialize configuration
    config = ConfigManager()

    # Initialize risk manager
    risk_manager = RiskManager(config)

    # Create mock exchanges for demo
    print("\n1. Initializing Exchanges (Mock Mode)")
    print("-" * 70)

    exchanges = {}

    # Kraken mock
    kraken_config = {
        "name": "Kraken",
        "api_url": "http://mock.kraken.com",
        "taker_fee": 0.0026,
        "maker_fee": 0.0016,
    }
    kraken_rate_limiter = RateLimiter(requests_per_second=15, name="kraken")
    kraken = MockExchange(kraken_config, kraken_rate_limiter)
    await kraken.connect()
    exchanges["Kraken"] = kraken
    print("   ✅ Kraken (mock) initialized")

    # Coinbase mock
    coinbase_config = {
        "name": "Coinbase Advanced",
        "api_url": "http://mock.coinbase.com",
        "taker_fee": 0.006,
        "maker_fee": 0.004,
    }
    coinbase_rate_limiter = RateLimiter(requests_per_second=10, name="coinbase")
    coinbase = MockExchange(coinbase_config, coinbase_rate_limiter)
    await coinbase.connect()
    exchanges["Coinbase Advanced"] = coinbase
    print("   ✅ Coinbase Advanced (mock) initialized")

    # Initialize execution engine
    print("\n2. Initializing Execution Engine")
    print("-" * 70)

    engine = ExecutionEngine(exchanges, risk_manager, config)
    await engine.initialize()

    print("   ✅ Execution engine initialized")
    print(f"   Tracked Executions: {len(engine.executions)}")

    # Create test opportunity
    print("\n3. Creating Arbitrage Opportunity")
    print("-" * 70)

    opportunity = create_test_opportunity()

    print(f"   Strategy: {opportunity.strategy}")
    print(f"   Buy:  {opportunity.buy_exchange} @ ${opportunity.buy_price:,.2f}")
    print(f"   Sell: {opportunity.sell_exchange} @ ${opportunity.sell_price:,.2f}")
    print(f"   Expected Profit: ${opportunity.net_profit_usd:,.2f} ({opportunity.net_profit_percent}%)")
    print(f"   Quantity: {opportunity.max_quantity} BTC")

    # Execute opportunity
    print("\n4. Executing Opportunity (DRY-RUN)")
    print("-" * 70)

    result = await engine.execute_opportunity(opportunity, dry_run=True)

    if result.success:
        print("   ✅ EXECUTION SUCCESSFUL")
        print(f"   Execution ID: {result.execution_id[:16]}...")
        print(f"   Orders Filled: {result.orders_filled}/{result.total_orders}")
        print(f"   Execution Time: {result.execution_time_seconds:.2f}s")
        if result.profit_usd:
            print(f"   Actual Profit: ${result.profit_usd:,.2f}")
    else:
        print("   ❌ EXECUTION FAILED")
        print(f"   State: {result.state.value}")
        print(f"   Orders Filled: {result.orders_filled}/{result.total_orders}")
        if result.error_message:
            print(f"   Error: {result.error_message}")

    # Get execution details
    print("\n5. Execution Plan Details")
    print("-" * 70)

    plan = engine.get_execution_status(result.execution_id)
    if plan:
        print(f"   Execution ID: {plan.execution_id[:16]}...")
        print(f"   Strategy: {plan.strategy}")
        print(f"   State: {plan.state.value}")
        print(f"   Dry Run: {plan.dry_run}")
        print(f"\n   Orders:")
        for i, order in enumerate(plan.orders, 1):
            print(f"      {i}. {order.side.upper()} on {order.exchange}")
            print(f"         Symbol: {order.symbol}")
            print(f"         Quantity: {order.quantity}")
            print(f"         Price: ${order.price:,.2f}" if order.price else "         Price: Market")
            print(f"         Status: {order.status.value}")

    # Get engine statistics
    print("\n6. Execution Engine Statistics")
    print("-" * 70)

    stats = engine.get_stats()
    print(f"   Total Executions: {stats['total_executions']}")
    print(f"   Successful: {stats['successful']}")
    print(f"   Failed: {stats['failed']}")
    print(f"   Success Rate: {stats['success_rate']:.1f}%")

    # Balance stats
    if 'balance_stats' in stats:
        balance_stats = stats['balance_stats']
        print(f"\n   Balance Management:")
        print(f"      Available USD: ${balance_stats.get('total_available_usd', 0):,.2f}")
        print(f"      Reserved USD: ${balance_stats.get('total_reserved_usd', 0):,.2f}")
        print(f"      Exchanges: {', '.join(balance_stats.get('exchanges', []))}")

    # Cleanup
    print("\n7. Cleanup")
    print("-" * 70)

    for exchange in exchanges.values():
        await exchange.disconnect()

    print("   ✅ All exchanges disconnected")

    print_header("DEMONSTRATION COMPLETE")

    print("Key Takeaways:")
    print("  ✅ Execution engine coordinates multi-leg trades")
    print("  ✅ Risk validation integrated (8-layer safety)")
    print("  ✅ DRY-RUN mode for safe testing")
    print("  ✅ Order tracking and reconciliation")
    print("  ✅ Balance management across exchanges")
    print("  ✅ Comprehensive error handling")
    print("\n  🔒 SAFETY FIRST: Always test with dry-run before live trading")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
