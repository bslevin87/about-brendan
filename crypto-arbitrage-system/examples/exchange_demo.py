#!/usr/bin/env python3
"""
Example script demonstrating exchange adapter usage.

This script shows how to:
- Initialize exchange adapters
- Fetch market data
- Check balances
- Create orders (dry run mode)

Run with: python examples/exchange_demo.py
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.exchanges.adapters.kraken import KrakenExchange
from src.exchanges.base import MockExchange
from src.exchanges.rate_limiter import RateLimiter


async def demo_mock_exchange():
    """Demonstrate MockExchange usage."""
    print("=" * 60)
    print("MOCK EXCHANGE DEMO")
    print("=" * 60)

    # Create mock exchange
    config = {
        "name": "MockExchange",
        "api_url": "http://mock.example.com",
    }
    rate_limiter = RateLimiter(requests_per_second=10, name="mock")
    exchange = MockExchange(config, rate_limiter)

    # Connect
    await exchange.connect()
    print(f"✓ Connected to {exchange.name}")

    # Check health
    is_healthy = await exchange.health_check()
    print(f"✓ Health check: {'healthy' if is_healthy else 'unhealthy'}")

    # Fetch ticker
    ticker = await exchange.fetch_ticker("BTC/USD")
    print(f"\n✓ Ticker for BTC/USD:")
    print(f"  - Bid: ${ticker.bid:,.2f}")
    print(f"  - Ask: ${ticker.ask:,.2f}")
    print(f"  - Spread: ${ticker.spread:.2f} ({ticker.spread_percent:.3f}%)")

    # Fetch order book
    order_book = await exchange.fetch_order_book("BTC/USD", depth=5)
    print(f"\n✓ Order book for BTC/USD:")
    print(f"  - Best bid: ${order_book.best_bid[0]:,.2f} ({order_book.best_bid[1]} BTC)")
    print(f"  - Best ask: ${order_book.best_ask[0]:,.2f} ({order_book.best_ask[1]} BTC)")

    # Fetch balances
    balances = await exchange.fetch_balances()
    print(f"\n✓ Account balances:")
    for balance in balances:
        print(f"  - {balance.currency}: {balance.available} (available)")

    # Create order (dry run)
    order = await exchange.create_order(
        symbol="BTC/USD",
        side="buy",
        order_type="limit",
        quantity=Decimal("0.1"),
        price=Decimal("50000"),
        dry_run=True,
    )
    print(f"\n✓ Created order (dry run):")
    print(f"  - Order ID: {order.order_id}")
    print(f"  - Side: {order.side}")
    print(f"  - Quantity: {order.quantity} BTC")
    print(f"  - Price: ${order.price:,.2f}")

    # Disconnect
    await exchange.disconnect()
    print(f"\n✓ Disconnected from {exchange.name}")


async def demo_kraken_exchange():
    """Demonstrate KrakenExchange usage."""
    print("\n" + "=" * 60)
    print("KRAKEN EXCHANGE DEMO")
    print("=" * 60)

    # Create Kraken exchange
    config = {
        "name": "Kraken",
        "api_url": "https://api.kraken.com",
        "ws_url": "wss://ws.kraken.com",
    }
    rate_limiter = RateLimiter(requests_per_second=5, name="kraken")
    exchange = KrakenExchange(config, rate_limiter)

    print(f"\n✓ Initialized {exchange.name} adapter")

    # Test symbol normalization
    print(f"\n✓ Symbol normalization:")
    test_symbols = [
        ("XXBTZUSD", "BTC/USD"),
        ("XETHZUSD", "ETH/USD"),
        ("XLTCZUSD", "LTC/USD"),
    ]
    for kraken_sym, normalized in test_symbols:
        result = exchange.normalize_symbol(kraken_sym)
        status = "✓" if result == normalized else "✗"
        print(f"  {status} {kraken_sym} → {result}")

    # Test order creation (dry run - doesn't need API connection)
    print(f"\n✓ Testing order creation (dry run mode):")
    order = await exchange.create_order(
        symbol="BTC/USD",
        side="buy",
        order_type="limit",
        quantity=Decimal("0.05"),
        price=Decimal("45000"),
        dry_run=True,
    )
    print(f"  - Order ID: {order.order_id}")
    print(f"  - Status: {order.status}")
    print(f"  - Symbol: {order.symbol}")

    print(f"\n✓ Kraken adapter ready for use")
    print(f"  (Set KRAKEN_API_KEY and KRAKEN_API_SECRET to use live API)")


async def demo_rate_limiter():
    """Demonstrate rate limiter usage."""
    print("\n" + "=" * 60)
    print("RATE LIMITER DEMO")
    print("=" * 60)

    # Create rate limiter
    limiter = RateLimiter(
        requests_per_second=5,  # 5 requests per second
        burst_size=10,  # Allow bursts up to 10
        name="demo"
    )

    print(f"\n✓ Rate limiter configured:")
    print(f"  - Rate: 5 requests/second")
    print(f"  - Burst capacity: 10 requests")

    # Make some requests
    print(f"\n✓ Making 5 requests (should be instant with burst)...")
    import time
    start = time.time()
    for i in range(5):
        await limiter.acquire()
        print(f"  - Request {i+1} completed")
    elapsed = time.time() - start
    print(f"  - Total time: {elapsed:.3f}s (instant due to burst)")

    # Show statistics
    stats = limiter.get_statistics()
    print(f"\n✓ Rate limiter statistics:")
    print(f"  - Total requests: {stats['total_requests']}")
    print(f"  - Total waits: {stats['total_waits']}")
    print(f"  - Available tokens: {stats['current_tokens']:.1f}")


async def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("CRYPTO ARBITRAGE SYSTEM - EXCHANGE ADAPTER DEMO")
    print("=" * 60)

    try:
        # Demo mock exchange
        await demo_mock_exchange()

        # Demo Kraken exchange
        await demo_kraken_exchange()

        # Demo rate limiter
        await demo_rate_limiter()

        print("\n" + "=" * 60)
        print("✓ ALL DEMOS COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Set up exchange API keys in .env file")
        print("2. Run health checks: python scripts/health_check.py")
        print("3. Run full test suite: pytest")
        print()

    except Exception as e:
        print(f"\n✗ Error during demo: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
