#!/usr/bin/env python3
"""
Cross-exchange arbitrage monitoring demonstration.

This script demonstrates real-time arbitrage detection between
Kraken and Coinbase Advanced exchanges by:
1. Connecting to both exchanges
2. Fetching order books from both
3. Detecting cross-exchange arbitrage opportunities
4. Calculating net profit after fees
5. Displaying real-time opportunities

Run with: python examples/cross_exchange_monitor.py
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import ConfigManager
from src.core.logger import get_logger
from src.exchanges.adapters.kraken import KrakenExchange
from src.exchanges.adapters.coinbase_advanced import CoinbaseAdvancedExchange
from src.exchanges.rate_limiter import RateLimiter
from src.market_data.aggregator import MarketDataAggregator
from src.detectors.cross_exchange import CrossExchangeDetector

logger = get_logger(__name__)


async def main():
    """Run cross-exchange monitoring demonstration."""
    print("=" * 70)
    print("CROSS-EXCHANGE ARBITRAGE MONITOR")
    print("Kraken ⟷ Coinbase Advanced")
    print("=" * 70)

    # Initialize configuration
    config = ConfigManager()

    # Check for API credentials
    kraken_config = config.exchanges.get("kraken", {})
    coinbase_config = config.exchanges.get("coinbase_advanced", {})

    use_real_exchanges = (
        kraken_config.get("api_key") and coinbase_config.get("api_key")
    )

    exchanges = {}

    print("\n1. Initializing exchanges...")
    print("-" * 70)

    if use_real_exchanges:
        print("   Using REAL exchanges (API credentials found)")
        print("   ⚠️  This will make actual API calls to exchanges")

        # Create Kraken exchange
        kraken_rate_limiter = RateLimiter(
            requests_per_second=kraken_config.get("rate_limit_requests_per_second", 15),
            name="kraken",
        )
        kraken = KrakenExchange(kraken_config, kraken_rate_limiter)
        await kraken.connect()
        exchanges["Kraken"] = kraken
        print("   ✓ Kraken connected")

        # Create Coinbase Advanced exchange
        coinbase_rate_limiter = RateLimiter(
            requests_per_second=coinbase_config.get(
                "rate_limit_requests_per_second", 10
            ),
            name="coinbase_advanced",
        )
        coinbase = CoinbaseAdvancedExchange(coinbase_config, coinbase_rate_limiter)
        await coinbase.connect()
        exchanges["Coinbase Advanced"] = coinbase
        print("   ✓ Coinbase Advanced connected")

    else:
        print("   Using MOCK exchanges (no API credentials)")
        print("   💡 Add API keys to config/exchanges.yaml for real data")

        from src.exchanges.base import MockExchange

        # Create mock exchanges with different price levels
        mock_kraken_config = {
            "name": "Kraken",
            "api_url": "http://mock.kraken.com",
            "taker_fee": 0.0026,  # 0.26%
            "maker_fee": 0.0016,  # 0.16%
        }
        kraken_rate_limiter = RateLimiter(requests_per_second=15, name="kraken")
        kraken = MockExchange(mock_kraken_config, kraken_rate_limiter)
        await kraken.connect()
        exchanges["Kraken"] = kraken
        print("   ✓ Kraken (mock) connected")

        mock_coinbase_config = {
            "name": "Coinbase Advanced",
            "api_url": "http://mock.coinbase.com",
            "taker_fee": 0.006,  # 0.6%
            "maker_fee": 0.004,  # 0.4%
        }
        coinbase_rate_limiter = RateLimiter(
            requests_per_second=10, name="coinbase_advanced"
        )
        coinbase = MockExchange(mock_coinbase_config, coinbase_rate_limiter)
        await coinbase.connect()
        exchanges["Coinbase Advanced"] = coinbase
        print("   ✓ Coinbase Advanced (mock) connected")

    # Create market data aggregator
    print("\n2. Starting market data aggregator...")
    print("-" * 70)
    aggregator = MarketDataAggregator(
        exchanges=exchanges,
        config=config,
        redis_url=config.redis_url,
    )

    # Start aggregator with common trading pairs
    symbols = ["BTC/USD", "ETH/USD"]
    await aggregator.start(symbols)
    print(f"   ✓ Aggregator started for {len(symbols)} symbols")

    # Give time for initial order book population
    print("   ⏱  Waiting for order book initialization...")
    await asyncio.sleep(2)

    # Display current order books
    print("\n3. Current Order Book Snapshots:")
    print("=" * 70)
    for symbol in symbols:
        print(f"\n📊 {symbol}")
        print("-" * 70)
        prices = aggregator.get_best_prices(symbol)

        if not prices:
            print("   ⚠️  No order book data available yet")
            continue

        for exchange_name, price_data in prices.items():
            bid = price_data.get("bid", 0)
            ask = price_data.get("ask", 0)
            spread = price_data.get("spread", 0)
            spread_pct = (spread / bid * 100) if bid > 0 else 0

            print(
                f"   {exchange_name:20} "
                f"Bid: ${bid:>10,.2f}  "
                f"Ask: ${ask:>10,.2f}  "
                f"Spread: ${spread:>6.2f} ({spread_pct:.3f}%)"
            )

    # Detect arbitrage opportunities
    print("\n4. Detecting Cross-Exchange Arbitrage Opportunities:")
    print("=" * 70)

    detector = CrossExchangeDetector(aggregator, config)
    opportunities = await detector.detect(symbols)

    if opportunities:
        print(f"\n✅ Found {len(opportunities)} profitable opportunities:\n")

        for i, opp in enumerate(opportunities, 1):
            print(f"   {'─' * 66}")
            print(f"   Opportunity #{i}:")
            print(f"   {'─' * 66}")
            print(f"   Symbol:           {opp.symbol}")
            print(f"   Buy Exchange:     {opp.buy_exchange}")
            print(f"   Buy Price:        ${opp.buy_price:,.2f}")
            print(f"   Sell Exchange:    {opp.sell_exchange}")
            print(f"   Sell Price:       ${opp.sell_price:,.2f}")
            print()
            print(f"   Gross Profit:     {opp.gross_profit_percent:.3f}%")
            print(f"   Total Fees:       {opp.total_fees_percent:.3f}%")
            print(f"   Net Profit:       {opp.net_profit_percent:.3f}%")
            print()
            print(f"   Max Quantity:     {opp.max_quantity:.4f}")
            print(f"   Confidence:       {opp.confidence_score:.2f}")
            print(f"   Risk Score:       {opp.risk_score:.2f}")
            print()

            # Calculate potential profit for different amounts
            test_amounts = [
                Decimal("0.01"),
                Decimal("0.1"),
                Decimal("1.0"),
            ]
            print(f"   Potential Profit (USD):")
            for amount in test_amounts:
                if amount <= opp.max_quantity:
                    buy_cost = amount * opp.buy_price
                    sell_revenue = amount * opp.sell_price
                    gross_profit = sell_revenue - buy_cost
                    net_profit = gross_profit * (
                        Decimal("1") - opp.total_fees_percent / Decimal("100")
                    )
                    print(
                        f"      {float(amount):>6.2f} {opp.symbol.split('/')[0]:>4}: "
                        f"${float(net_profit):>8.2f}"
                    )

        print(f"\n   {'─' * 66}")

    else:
        print("\n   ℹ️  No profitable arbitrage opportunities detected")
        print()
        print("   Reasons could include:")
        print("   • Spreads too small after fees")
        print("   • Mock data has insufficient price differences")
        print("   • Markets are currently efficient")
        print()
        print("   💡 Try with real API credentials for actual market data")

    # Show cross-exchange spreads
    print("\n5. Cross-Exchange Price Comparison:")
    print("=" * 70)

    for symbol in symbols:
        prices = aggregator.get_best_prices(symbol)

        if len(prices) < 2:
            print(f"\n   {symbol}: Insufficient data for comparison")
            continue

        exchange_names = list(prices.keys())
        e1, e2 = exchange_names[0], exchange_names[1]

        e1_bid = prices[e1].get("bid", 0)
        e1_ask = prices[e1].get("ask", 0)
        e2_bid = prices[e2].get("bid", 0)
        e2_ask = prices[e2].get("ask", 0)

        # Calculate potential arbitrage (buy low, sell high)
        if e1_ask > 0 and e2_bid > 0:
            spread_1_to_2 = ((e2_bid - e1_ask) / e1_ask) * 100
        else:
            spread_1_to_2 = 0

        if e2_ask > 0 and e1_bid > 0:
            spread_2_to_1 = ((e1_bid - e2_ask) / e2_ask) * 100
        else:
            spread_2_to_1 = 0

        print(f"\n   {symbol}:")
        print(f"   ├─ Buy on {e1:20} @ ${e1_ask:>10,.2f}")
        print(f"   └─ Sell on {e2:20} @ ${e2_bid:>10,.2f}")
        print(f"      → Spread: {spread_1_to_2:>6.3f}%")
        print()
        print(f"   ├─ Buy on {e2:20} @ ${e2_ask:>10,.2f}")
        print(f"   └─ Sell on {e1:20} @ ${e1_bid:>10,.2f}")
        print(f"      → Spread: {spread_2_to_1:>6.3f}%")

    # System statistics
    print("\n6. System Statistics:")
    print("=" * 70)
    stats = aggregator.get_stats()
    print(f"   Exchanges:        {stats['exchanges']}")
    print(f"   Order Books:      {stats['order_book_manager']['total_books']}")
    print(f"   Total Levels:     {stats['order_book_manager']['total_levels']}")
    print(f"   Updates:          {stats['order_book_manager']['updates_processed']}")

    # Cleanup
    print("\n7. Shutting down...")
    print("-" * 70)
    await aggregator.stop()
    for exchange in exchanges.values():
        await exchange.disconnect()
    print("   ✓ All connections closed")

    print("\n" + "=" * 70)
    print("✅ MONITORING SESSION COMPLETED")
    print("=" * 70)
    print()
    print("Key Insights:")
    print("• Cross-exchange arbitrage requires real-time order book monitoring")
    print("• Fees significantly impact net profitability")
    print("• Price differences exist but may be too small after costs")
    print("• Higher liquidity pairs have smaller spreads")
    print()

    if not use_real_exchanges:
        print("💡 Next Steps:")
        print("• Add API credentials to config/exchanges.yaml")
        print("• Run again with real market data")
        print("• Monitor opportunities in real-time")
        print("• Consider execution speed and slippage")
        print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
