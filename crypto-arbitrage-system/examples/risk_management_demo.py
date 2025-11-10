#!/usr/bin/env python3
"""
Risk Management System Demonstration.

Demonstrates:
- Multi-layer validation
- Position tracking
- P&L monitoring
- Circuit breakers
- Kill switch
- Trading state management

This shows how the risk management system protects capital
and prevents losses through comprehensive safety controls.
"""
import sys
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import ConfigManager
from src.models.opportunity import ArbitrageOpportunity
from src.risk.manager import RiskManager
from src.risk.models import TradingState


def create_test_opportunity(
    net_profit=Decimal("0.5"),
    confidence=Decimal("0.85"),
    risk=Decimal("0.3"),
):
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
        net_profit_percent=net_profit,
        net_profit_usd=Decimal("200"),
        total_fees_percent=Decimal("0.2"),
        total_fees_usd=Decimal("50"),
        max_quantity=Decimal("0.1"),
        confidence_score=confidence,
        risk_score=risk,
    )


def print_header(title: str):
    """Print section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_subheader(title: str):
    """Print subsection header."""
    print(f"\n{title}")
    print("-" * 70)


def main():
    """Run risk management demonstration."""
    print_header("RISK MANAGEMENT SYSTEM DEMONSTRATION")

    # Initialize configuration
    config = ConfigManager()

    # Initialize risk manager
    risk_manager = RiskManager(config)

    print("✅ Risk Manager initialized")
    print(f"   Active Profile: {config.risk.active_profile}")
    print(f"   Max Daily Loss: ${risk_manager.risk_limits.max_daily_loss_usd}")
    print(
        f"   Min Confidence: {risk_manager.risk_limits.min_confidence_score}"
    )
    print(f"   Trading State: {risk_manager.trading_state.value}")

    # Demo 1: Successful Validation
    print_subheader("1. Successful Trade Validation")

    good_opportunity = create_test_opportunity()
    balances = {"Kraken": {"USD": Decimal("10000")}}

    result = risk_manager.validate_trade(good_opportunity, balances)

    if result.passed:
        print("✅ VALIDATION PASSED")
        print(f"   Opportunity: {good_opportunity.symbol}")
        print(f"   Profit: {good_opportunity.net_profit_percent}%")
        print(f"   Confidence: {good_opportunity.confidence_score}")
        print(f"   Risk: {good_opportunity.risk_score}")
    else:
        print(f"❌ VALIDATION FAILED: {result.reason}")

    # Demo 2: Low Confidence Rejection
    print_subheader("2. Low Confidence Rejection")

    low_conf_opp = create_test_opportunity(confidence=Decimal("0.5"))
    result = risk_manager.validate_trade(low_conf_opp, balances)

    if not result.passed:
        print(f"❌ REJECTED: {result.reason}")
        print(f"   Confidence: {low_conf_opp.confidence_score}")
        print(
            f"   Required: {risk_manager.risk_limits.min_confidence_score}"
        )
        print(f"   Risk Level: {result.risk_level.value}")
    else:
        print("⚠️  Unexpected: Validation passed")

    # Demo 3: High Risk Rejection
    print_subheader("3. High Risk Rejection")

    high_risk_opp = create_test_opportunity(risk=Decimal("0.8"))
    result = risk_manager.validate_trade(high_risk_opp, balances)

    if not result.passed:
        print(f"❌ REJECTED: {result.reason}")
        print(f"   Risk Score: {high_risk_opp.risk_score}")
        print(f"   Max Allowed: {risk_manager.risk_limits.max_risk_score}")
        print(f"   Risk Level: {result.risk_level.value}")

    # Demo 4: Low Profit Rejection
    print_subheader("4. Low Profit Rejection")

    low_profit_opp = create_test_opportunity(net_profit=Decimal("0.1"))
    result = risk_manager.validate_trade(low_profit_opp, balances)

    if not result.passed:
        print(f"❌ REJECTED: {result.reason}")
        print(f"   Profit: {low_profit_opp.net_profit_percent}%")
        print(
            f"   Required: {risk_manager.risk_limits.min_profit_threshold_percent}%"
        )

    # Demo 5: Insufficient Balance Rejection
    print_subheader("5. Insufficient Balance Rejection")

    insufficient_balances = {"Kraken": {"USD": Decimal("10")}}
    result = risk_manager.validate_trade(good_opportunity, insufficient_balances)

    if not result.passed:
        print(f"❌ REJECTED: {result.reason}")
        print("   Capital preservation: Insufficient funds detected")

    # Demo 6: Position Tracking
    print_subheader("6. Position Tracking")

    risk_manager.open_position(
        position_id="pos1",
        exchange="Kraken",
        symbol="BTC/USD",
        side="long",
        quantity=Decimal("0.1"),
        entry_price=Decimal("50000"),
    )

    print("✅ Position opened")
    print(f"   Total Positions: {risk_manager.position_tracker.get_total_position_count()}")
    print(f"   Total Exposure: ${risk_manager.position_tracker.get_total_exposure():,.2f}")

    # Update price (simulating market movement)
    risk_manager.position_tracker.update_position_price(
        "pos1", Decimal("51000")
    )

    position = risk_manager.position_tracker.get_position("pos1")
    print(f"   Unrealized P&L: ${position.unrealized_pnl_usd:,.2f} ({position.pnl_percent}%)")

    # Demo 7: P&L Tracking
    print_subheader("7. P&L Tracking & Consecutive Wins")

    # Record some winning trades
    risk_manager.record_trade_outcome("pos1", Decimal("100"), {"symbol": "BTC/USD"})
    print("✅ Trade #1: +$100")

    # Open and close another position
    risk_manager.open_position(
        "pos2", "Kraken", "ETH/USD", "long", Decimal("1.0"), Decimal("3000")
    )
    risk_manager.record_trade_outcome("pos2", Decimal("50"), {"symbol": "ETH/USD"})
    print("✅ Trade #2: +$50")

    stats = risk_manager.pnl_tracker.get_stats()
    print(f"\n   Total P&L: ${stats['total_pnl_usd']:,.2f}")
    print(f"   Consecutive Wins: {stats['consecutive_wins']}")
    print(f"   Win Rate: {stats['win_rate_percent']:.1f}%")

    # Demo 8: Loss Limits & Consecutive Losses
    print_subheader("8. Loss Limits & Consecutive Losses")

    # Simulate consecutive losses
    for i in range(3):
        risk_manager.pnl_tracker.record_trade(Decimal("-50"))
        print(f"❌ Loss #{i+1}: -$50")

    print(f"\n   Consecutive Losses: {risk_manager.pnl_tracker.consecutive_losses}")
    print(f"   Daily P&L: ${risk_manager.pnl_tracker.daily_pnl:,.2f}")

    # Demo 9: Circuit Breaker
    print_subheader("9. Circuit Breaker - Auto Halt on Errors")

    # Simulate multiple failures
    for i in range(5):
        risk_manager.circuit_breaker.record_failure()

    print(f"   State: {risk_manager.circuit_breaker.state.value}")
    print(f"   Trading Allowed: {risk_manager.circuit_breaker.is_trading_allowed()}")

    # Test validation with circuit breaker open
    result = risk_manager.validate_trade(good_opportunity, balances)
    if not result.passed:
        print(f"   ❌ Trade blocked: {result.reason}")

    # Reset circuit breaker
    risk_manager.reset_circuit_breaker()
    print("   ✅ Circuit breaker reset")

    # Demo 10: Kill Switch
    print_subheader("10. Emergency Kill Switch")

    risk_manager.activate_kill_switch("Manual test - demonstrating emergency control")

    print(f"   🚨 Kill Switch: ACTIVE")
    print(f"   Trading State: {risk_manager.trading_state.value}")

    # Try to validate trade with kill switch active
    result = risk_manager.validate_trade(good_opportunity, balances)
    if not result.passed:
        print(f"   ❌ Trade blocked: {result.reason}")
        print(f"   Risk Level: {result.risk_level.value}")

    # Deactivate kill switch
    risk_manager.deactivate_kill_switch()
    print("   ✅ Kill switch deactivated")
    print(f"   Trading State: {risk_manager.trading_state.value}")

    # Demo 11: Comprehensive Status
    print_subheader("11. Comprehensive Risk Status")

    status = risk_manager.get_status()

    print(f"   Trading State: {status['trading_state']}")
    print(f"   Circuit Breaker: {status['circuit_breaker']['state']}")
    print(f"   Kill Switch: {'ACTIVE' if status['kill_switch']['active'] else 'INACTIVE'}")
    print(f"\n   Positions:")
    print(f"      Total Count: {status['positions']['total_count']}")
    print(f"      Total Exposure: ${status['positions']['total_exposure_usd']:,.2f}")
    print(f"      Unrealized P&L: ${status['positions']['unrealized_pnl_usd']:,.2f}")
    print(f"\n   P&L:")
    print(f"      Total: ${status['pnl']['total_pnl_usd']:,.2f}")
    print(f"      Daily: ${status['pnl']['daily_pnl_usd']:,.2f}")
    print(f"      Win Rate: {status['pnl']['win_rate_percent']:.1f}%")
    print(f"      Consecutive Wins: {status['pnl']['consecutive_wins']}")
    print(f"      Consecutive Losses: {status['pnl']['consecutive_losses']}")
    print(f"\n   Limits:")
    print(f"      Max Daily Loss: ${status['limits']['max_daily_loss_usd']:,.2f}")
    print(f"      Max Positions: {status['limits']['max_positions']}")
    print(f"      Min Confidence: {status['limits']['min_confidence_score']}")

    # Summary
    print_header("DEMONSTRATION COMPLETE")

    print("Key Takeaways:")
    print("  ✅ Multi-layer validation prevents bad trades")
    print("  ✅ Position tracking provides real-time exposure monitoring")
    print("  ✅ P&L tracking catches consecutive losses early")
    print("  ✅ Circuit breakers auto-halt on high error rates")
    print("  ✅ Kill switch provides immediate emergency control")
    print("  ✅ All risk decisions are logged for audit trail")
    print("\n  🛡️  CAPITAL PRESERVATION IS PARAMOUNT 🛡️")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
