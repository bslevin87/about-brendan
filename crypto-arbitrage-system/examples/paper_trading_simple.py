#!/usr/bin/env python3
"""
Simple Paper Trading Demo

Shows how paper trading mode differs from dry-run:
- In DRY-RUN: Opportunities detected but no simulated execution
- In PAPER: Opportunities executed with simulated orders and P&L tracking

Usage:
    python examples/paper_trading_simple.py
"""

import sys
from decimal import Decimal

sys.path.insert(0, '.')

from src.core.config import ConfigManager
from src.core.logger import get_logger
from src.risk.manager import RiskManager
from src.models.opportunity import ArbitrageOpportunity


def main():
    """Demonstrate paper trading concept."""
    print("\n" + "=" * 70)
    print("  PAPER TRADING DEMONSTRATION")
    print("=" * 70)
    print()

    # Load config
    print("📋 Configuration:")
    config = ConfigManager()
    logger = get_logger(__name__)

    print(f"   Mode: {config.trading.mode}")
    print(f"   Starting Capital: ${config.trading.capital_allocation.total_capital_usd:,.2f}")
    print(f"   Risk Profile: {config.risk.active_profile}")
    print()

    # Show mode differences
    print("🎯 Trading Mode Comparison:")
    print()
    print("┌─────────────┬──────────────┬──────────────┬─────────────┐")
    print("│ Mode        │ Detect Opps  │ Execute      │ Track P&L   │")
    print("├─────────────┼──────────────┼──────────────┼─────────────┤")
    print("│ DRY-RUN     │ ✅ Yes       │ ❌ No        │ ❌ No       │")
    print("│ PAPER       │ ✅ Yes       │ ✅ Simulated │ ✅ Yes      │")
    print("│ LIVE        │ ✅ Yes       │ ✅ Real      │ ✅ Yes      │")
    print("└─────────────┴──────────────┴──────────────┴─────────────┘")
    print()

    # Initialize risk manager
    print("🛡️  Risk Management:")
    risk_manager = RiskManager(config=config)
    print(f"   Max Position Size: {risk_manager.risk_limits.max_position_size_percent}%")
    print(f"   Max Daily Loss: ${risk_manager.risk_limits.max_daily_loss_usd:,.2f}")
    print(f"   Max Consecutive Losses: {risk_manager.risk_limits.max_consecutive_losses}")
    print()

    # Simulate some paper trades
    print("📊 Simulating Paper Trades:")
    print("-" * 70)
    print()

    trades = [
        {
            "symbol": "BTC/USD",
            "buy_exchange": "Kraken",
            "sell_exchange": "Coinbase",
            "buy_price": Decimal("49900"),
            "sell_price": Decimal("50100"),
            "quantity": Decimal("0.1"),
            "profit": Decimal("16.50"),
        },
        {
            "symbol": "ETH/USD",
            "buy_exchange": "Coinbase",
            "sell_exchange": "Kraken",
            "buy_price": Decimal("2990"),
            "sell_price": Decimal("3010"),
            "quantity": Decimal("1.0"),
            "profit": Decimal("15.20"),
        },
        {
            "symbol": "BTC/USD",
            "buy_exchange": "Kraken",
            "sell_exchange": "Coinbase",
            "buy_price": Decimal("50200"),
            "sell_price": Decimal("50150"),
            "quantity": Decimal("0.05"),
            "profit": Decimal("-3.50"),  # Loss
        },
    ]

    total_pnl = Decimal("0")

    for i, trade in enumerate(trades, 1):
        print(f"Trade #{i}:")
        print(f"   Symbol: {trade['symbol']}")
        print(f"   Buy:  {trade['buy_exchange']} @ ${trade['buy_price']:,.2f}")
        print(f"   Sell: {trade['sell_exchange']} @ ${trade['sell_price']:,.2f}")
        print(f"   Quantity: {trade['quantity']}")

        # Record the trade
        risk_manager.pnl_tracker.record_trade(
            pnl_usd=trade['profit'],
            trade_details={
                "symbol": trade['symbol'],
                "paper_trade": True,
                "quantity": float(trade['quantity'])
            }
        )

        total_pnl += trade['profit']

        if trade['profit'] > 0:
            print(f"   Result: ✅ PROFIT ${trade['profit']:.2f}")
        else:
            print(f"   Result: ❌ LOSS ${abs(trade['profit']):.2f}")

        print()

    print("-" * 70)
    print()

    # Show P&L stats
    print("💰 Paper Trading Results:")
    stats = risk_manager.pnl_tracker.get_stats()

    print(f"   Total Trades: {stats['total_trades']}")
    print(f"   Winning Trades: {stats['total_wins']}")
    print(f"   Losing Trades: {stats['total_losses']}")
    print(f"   Win Rate: {stats['win_rate_percent']:.1f}%")
    print()
    print(f"   Total P&L: ${stats['total_pnl_usd']:.2f}")
    print(f"   Average P&L per Trade: ${stats['average_profit_usd']:.2f}")
    print(f"   Best Trade: ${stats['largest_win_usd']:.2f}")
    print(f"   Worst Trade: ${stats['largest_loss_usd']:.2f}")
    print()

    # Show portfolio summary
    starting_capital = config.trading.capital_allocation.total_capital_usd
    final_capital = starting_capital + stats['total_pnl_usd']
    return_pct = (stats['total_pnl_usd'] / starting_capital) * 100

    print("📈 Portfolio Summary:")
    print(f"   Starting Capital: ${starting_capital:,.2f}")
    print(f"   Final Capital: ${final_capital:,.2f}")
    print(f"   Return: {return_pct:+.2f}%")
    print()

    # Show risk metrics
    print("⚠️  Risk Metrics:")
    if stats['consecutive_losses'] > 0:
        print(f"   Consecutive Losses: {stats['consecutive_losses']}")
        if stats['consecutive_losses'] >= risk_manager.risk_limits.max_consecutive_losses:
            print("   ⚠️  WARNING: Circuit breaker would trigger!")
    else:
        print(f"   Consecutive Wins: {stats['consecutive_wins']}")

    max_daily_loss = float(risk_manager.risk_limits.max_daily_loss_usd)
    if abs(stats['daily_pnl_usd']) >= max_daily_loss:
        print("   🚨 WARNING: Daily loss limit would be hit!")
    else:
        loss_remaining = max_daily_loss + stats['daily_pnl_usd']
        print(f"   Daily Loss Remaining: ${loss_remaining:.2f}")

    print()

    # Trading state
    print("📊 Trading State:")
    print(f"   Current State: {risk_manager.trading_state.value}")
    print(f"   Circuit Breaker: {'🟢 CLOSED (Trading Allowed)' if risk_manager.circuit_breaker.is_trading_allowed() else '🔴 OPEN (Trading Halted)'}")
    print(f"   Kill Switch: {'🔴 ACTIVE (Emergency Halt)' if risk_manager.emergency.is_kill_switch_active() else '🟢 INACTIVE'}")
    print()

    print("=" * 70)
    print("  PAPER TRADING BENEFITS")
    print("=" * 70)
    print()
    print("✅ No Risk: Test strategies without losing real money")
    print("✅ Real Data: Uses live market prices from exchanges")
    print("✅ Full P&L: Tracks profits/losses as if trading were real")
    print("✅ Risk Validation: Circuit breakers and limits work the same")
    print("✅ Strategy Tuning: Adjust parameters based on paper results")
    print()
    print("📚 Recommended Paper Trading Duration:")
    print("   • Minimum: 48 hours continuous operation")
    print("   • Ideal: 1-2 weeks across different market conditions")
    print("   • Test scenarios: High volatility, low liquidity, various spreads")
    print()
    print("🚀 Next Steps:")
    print("   1. Enable paper mode in config/trading.yaml")
    print("   2. Run the system for at least 48 hours")
    print("   3. Monitor P&L and risk metrics daily")
    print("   4. Adjust risk limits based on results")
    print("   5. Only move to live trading after consistent profitability")
    print()


if __name__ == "__main__":
    main()
