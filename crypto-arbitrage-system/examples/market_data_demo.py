#!/usr/bin/env python3
"""
Market data aggregation demonstration.

This script demonstrates the market data layer by:
1. Initializing order books from exchanges
2. Calculating cross-exchange spreads
3. Detecting arbitrage opportunities
4. Showing real-time market data

Run with: python examples/market_data_demo.py
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
from src.exchanges.base import MockExchange
from src.exchanges.rate_limiter import RateLimiter
from src.market_data.aggregator import MarketDataAggregator
from src.detectors.cross_exchange import CrossExchangeDetector

logger = get_logger(__name__)


async def main():
    """Run market data demonstration."""
    print("=" * 60)
    print("MARKET DATA AGGREGATION DEMO")
    print("=" * 60)

    # Initialize configuration
    config = ConfigManager()

    # Create exchanges (using MockExchange for demonstration)
    exchanges = {}

    print("\n1. Initializing exchanges...")

    # Create mock exchanges with different prices
    for i, name in enumerate(["Exchange1", "Exchange2"]):
        exchange_config = {
            "name": name,
            "api_url": f"http://mock{i}.example.com",
            "taker_fee": 0.001 + (i * 0.0005),  # Different fees
            "maker_fee": 0.0005,
        }
        rate_limiter = RateLimiter(requests_per_second=10, name=name.lower())
        exchange = MockExchange(exchange_config, rate_limiter)
        await exchange.connect()
        exchanges[name] = exchange
        print(f"   ✓ {name} connected")

    # Create market data aggregator
    print("\n2. Starting market data aggregator...")
    aggregator = MarketDataAggregator(
        exchanges=exchanges,
        config=config,
        redis_url=config.redis_url,
    )

    # Start aggregator (will initialize order books)
    symbols = ["BTC/USD", "ETH/USD"]
    await aggregator.start(symbols)
    print(f"   ✓ Aggregator started for {len(symbols)} symbols")

    # Display order books
    print("\n3. Order Book Snapshots:")
    print("-" * 60)
    for symbol in symbols:
        print(f"\n{symbol}:")
        prices = aggregator.get_best_prices(symbol)
        for exchange_name, price_data in prices.items():
            print(
                f"  {exchange_name:15} "
                f"Bid: ${price_data['bid']:>10,.2f}  "
                f"Ask: ${price_data['ask']:>10,.2f}  "
                f"Spread: ${price_data['spread']:>6.2f}"
            )

    # Calculate spreads
    print("\n4. Cross-Exchange Spreads:")
    print("-" * 60)
    for symbol in symbols:
        spreads = aggregator.spread_calculator.get_all_spreads(
            symbol, list(exchanges.keys())
        )
        print(f"\n{symbol}:")
        for exchange_name, spread_data in spreads.items():
            print(
                f"  {exchange_name:15} "
                f"Spread: {spread_data['spread_percent']:>6.2f}%  "
                f"Mid Price: ${spread_data['mid_price']:>10,.2f}"
            )

    # Detect arbitrage opportunities
    print("\n5. Detecting Arbitrage Opportunities:")
    print("-" * 60)
    opportunities = aggregator.find_arbitrage_opportunities(
        symbols, min_profit_percent=Decimal("0.01")
    )

    if opportunities:
        print(f"\n✓ Found {len(opportunities)} opportunities:\n")
        for i, opp in enumerate(opportunities[:5], 1):  # Show top 5
            print(f"  Opportunity #{i}:")
            print(f"    Symbol: {opp.get('symbol', 'N/A')}")
            print(f"    Buy:  {opp.get('buy_exchange', 'N/A')} @ ${opp.get('buy_price', 0):,.2f}")
            print(f"    Sell: {opp.get('sell_exchange', 'N/A')} @ ${opp.get('sell_price', 0):,.2f}")
            print(f"    Gross Profit: {opp.get('gross_profit_percent', 0):.2f}%")
            print(f"    Net Profit:   {opp.get('net_profit_percent', 0):.2f}%")
            print(f"    Max Quantity: {opp.get('max_quantity', 0):.4f}")
            print()
    else:
        print("\n✗ No profitable opportunities found")
        print("  (This is expected with mock data and fees)")

    # Create detector for more detailed analysis
    print("\n6. Using Cross-Exchange Detector:")
    print("-" * 60)
    detector = CrossExchangeDetector(aggregator, config)
    detected_opps = await detector.detect(symbols)

    print(f"\n   Detector found {len(detected_opps)} opportunities")
    if detected_opps:
        print("\n   Best opportunity:")
        best = detected_opps[0]
        print(f"     {best.symbol}: {best.buy_exchange} → {best.sell_exchange}")
        print(f"     Net Profit: {best.net_profit_percent:.2f}%")
        print(f"     Confidence: {best.confidence_score:.2f}")
        print(f"     Risk Score: {best.risk_score:.2f}")

    # Statistics
    print("\n7. System Statistics:")
    print("-" * 60)
    stats = aggregator.get_stats()
    print(f"   Running: {stats['running']}")
    print(f"   Exchanges: {stats['exchanges']}")
    print(f"   Order Books: {stats['order_book_manager']['total_books']}")
    print(f"   Total Levels: {stats['order_book_manager']['total_levels']}")
    print(f"   Updates Processed: {stats['order_book_manager']['updates_processed']}")

    # Cleanup
    print("\n8. Shutting down...")
    await aggregator.stop()
    for exchange in exchanges.values():
        await exchange.disconnect()

    print("\n" + "=" * 60)
    print("✓ DEMONSTRATION COMPLETED")
    print("=" * 60)
    print()
    print("Key takeaways:")
    print("- Market data aggregator manages order books from multiple exchanges")
    print("- Spread calculator identifies price differences")
    print("- Detectors find and score arbitrage opportunities")
    print("- All components work together seamlessly")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    except Exception as e:
        print(f"\n\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
