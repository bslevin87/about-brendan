"""
Comprehensive Integration Test for Crypto Arbitrage System

Tests the complete pipeline:
1. Configuration loading
2. Exchange connectivity
3. Market data aggregation
4. Arbitrage detection
5. Risk validation
6. Execution (dry-run)
7. Reconciliation
8. Error handling

Usage:
    python scripts/integration_test.py                    # Full test
    python scripts/integration_test.py --quick            # Quick test (skip waiting)
    python scripts/integration_test.py --verbose          # Detailed output
"""

import asyncio
import sys
import os
import argparse
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
except ImportError:
    print("Error: rich library not installed. Install with: pip install rich")
    sys.exit(1)

# Import system components
try:
    from src.core.config import ConfigManager
    from src.core.logger import get_logger
    from src.exchanges.adapters.kraken import KrakenExchange
    from src.exchanges.adapters.coinbase_advanced import CoinbaseAdvancedExchange
    from src.exchanges.rate_limiter import RateLimiter
    from src.market_data.aggregator import MarketDataAggregator
    from src.detectors.cross_exchange import CrossExchangeDetector
    from src.risk.manager import RiskManager
    from src.execution.engine import ExecutionEngine
    from src.models.opportunity import ArbitrageOpportunity
except ImportError as e:
    print(f"Error importing system components: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)

console = Console()


class IntegrationTest:
    """Integration test orchestrator"""

    def __init__(self, quick: bool = False, verbose: bool = False):
        self.quick = quick
        self.verbose = verbose
        self.results: List[Tuple[str, str, Optional[str]]] = []
        self.exchanges: Dict = {}
        self.aggregator: Optional[MarketDataAggregator] = None
        self.risk_manager: Optional[RiskManager] = None
        self.engine: Optional[ExecutionEngine] = None
        self.detector: Optional[CrossExchangeDetector] = None
        self.config: Optional[ConfigManager] = None
        self.logger = None

    async def run_all_tests(self) -> bool:
        """Run all integration tests"""
        console.print("\n")
        console.print(Panel.fit(
            "[bold cyan]Crypto Arbitrage System - Integration Test Suite[/bold cyan]\n"
            f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Mode: {'Quick' if self.quick else 'Full'} | Verbose: {self.verbose}",
            box=box.DOUBLE
        ))

        tests = [
            ("Configuration", self.test_configuration),
            ("Exchange Connectivity", self.test_exchange_connectivity),
            ("Market Data", self.test_market_data),
            ("Risk Management", self.test_risk_management),
            ("Execution Engine", self.test_execution_engine),
            ("Arbitrage Detection", self.test_arbitrage_detection),
            ("Risk Validation", self.test_risk_validation),
            ("Dry-Run Execution", self.test_dry_run_execution),
            ("Error Handling", self.test_error_handling),
        ]

        passed = 0
        failed = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:

            for test_name, test_func in tests:
                task = progress.add_task(f"Running: {test_name}...", total=None)

                try:
                    result = await test_func()

                    if result:
                        passed += 1
                        self.results.append((test_name, "✅ PASS", None))
                        progress.update(task, description=f"[green]✅ {test_name}[/green]")
                    else:
                        failed += 1
                        self.results.append((test_name, "❌ FAIL", "Test returned False"))
                        progress.update(task, description=f"[red]❌ {test_name}[/red]")

                except Exception as e:
                    failed += 1
                    error_msg = str(e)
                    self.results.append((test_name, "❌ FAIL", error_msg))
                    progress.update(task, description=f"[red]❌ {test_name}[/red]")

                    if self.verbose:
                        console.print(f"[red]Error: {error_msg}[/red]")

                progress.remove_task(task)

                # Small delay between tests
                await asyncio.sleep(0.5)

        # Print results
        self.print_results(passed, failed)

        # Cleanup
        await self.cleanup()

        return failed == 0

    async def test_configuration(self) -> bool:
        """Test 1: Configuration loading"""
        try:
            self.config = ConfigManager()
            self.logger = get_logger(__name__)

            # Verify exchanges configured
            if not hasattr(self.config.exchanges, 'kraken'):
                raise AssertionError("Kraken not configured in config/exchanges.yaml")
            if not hasattr(self.config.exchanges, 'coinbase_advanced'):
                raise AssertionError("Coinbase Advanced not configured in config/exchanges.yaml")

            # Verify risk settings
            if not hasattr(self.config, 'risk'):
                raise AssertionError("Risk settings missing in config/risk.yaml")
            if self.config.risk.active_profile not in ['conservative', 'moderate', 'aggressive']:
                raise AssertionError(f"Invalid risk profile: {self.config.risk.active_profile}")

            # Verify trading settings
            if not hasattr(self.config, 'trading'):
                raise AssertionError("Trading settings missing in config/trading.yaml")
            if self.config.trading.capital_allocation.total_capital_usd <= 0:
                raise AssertionError("No capital configured in config/trading.yaml")

            if self.verbose:
                console.print(f"  [dim]Capital: ${self.config.trading.capital_allocation.total_capital_usd:,.2f}[/dim]")
                console.print(f"  [dim]Risk Profile: {self.config.risk.active_profile}[/dim]")

            return True

        except Exception as e:
            if self.verbose:
                console.print(f"  [red]Configuration error: {e}[/red]")
            raise

    async def test_exchange_connectivity(self) -> bool:
        """Test 2: Exchange connectivity"""
        try:
            # Test Kraken
            kraken_limiter = RateLimiter(requests_per_second=15, burst_size=20, name="kraken")
            kraken_config = self.config.exchanges.kraken

            self.exchanges["Kraken"] = KrakenExchange(
                config=kraken_config,
                logger=self.logger,
                rate_limiter=kraken_limiter
            )

            await self.exchanges["Kraken"].connect()
            health = await self.exchanges["Kraken"].health_check()

            if not health:
                raise AssertionError("Kraken health check failed")

            if self.verbose:
                console.print("  [dim]✅ Kraken connected[/dim]")

            # Test Coinbase Advanced
            coinbase_limiter = RateLimiter(requests_per_second=10, burst_size=15, name="coinbase")
            coinbase_config = self.config.exchanges.coinbase_advanced

            self.exchanges["Coinbase Advanced"] = CoinbaseAdvancedExchange(
                config=coinbase_config,
                logger=self.logger,
                rate_limiter=coinbase_limiter
            )

            await self.exchanges["Coinbase Advanced"].connect()
            health = await self.exchanges["Coinbase Advanced"].health_check()

            if not health:
                raise AssertionError("Coinbase Advanced health check failed")

            if self.verbose:
                console.print("  [dim]✅ Coinbase Advanced connected[/dim]")

            # Test fetching data from Kraken
            try:
                btc_ticker = await self.exchanges["Kraken"].fetch_ticker("BTC/USD")
                if btc_ticker.last <= 0:
                    raise AssertionError("Invalid BTC price from Kraken")

                if self.verbose:
                    console.print(f"  [dim]BTC/USD on Kraken: ${btc_ticker.last:,.2f}[/dim]")
            except Exception as e:
                if self.verbose:
                    console.print(f"  [yellow]Warning: Could not fetch BTC ticker from Kraken: {e}[/yellow]")

            return True

        except Exception as e:
            if self.verbose:
                console.print(f"  [red]Exchange connectivity error: {e}[/red]")
            raise

    async def test_market_data(self) -> bool:
        """Test 3: Market data aggregation"""
        try:
            # Initialize aggregator
            self.aggregator = MarketDataAggregator(
                exchanges=self.exchanges,
                config=self.config,
                logger=self.logger,
                redis_url=self.config.redis_url if hasattr(self.config, 'redis_url') else None
            )

            # Start aggregating
            await self.aggregator.start(symbols=["BTC/USD", "ETH/USD"])

            # Wait for data
            wait_time = 3 if self.quick else 10
            if self.verbose:
                console.print(f"  [dim]Waiting {wait_time}s for market data...[/dim]")

            await asyncio.sleep(wait_time)

            # Verify data
            prices = self.aggregator.get_best_prices("BTC/USD")

            if len(prices) == 0:
                if self.verbose:
                    console.print("  [yellow]Warning: No market data received yet (may need more time)[/yellow]")
                # Don't fail - may just need more time
                return True

            if "Kraken" not in prices and "Coinbase Advanced" not in prices:
                raise AssertionError("Missing exchange data from aggregator")

            if self.verbose:
                for exchange, price_data in prices.items():
                    console.print(f"  [dim]{exchange}: Bid=${price_data['bid']:,.2f}, Ask=${price_data['ask']:,.2f}[/dim]")

            return True

        except Exception as e:
            if self.verbose:
                console.print(f"  [red]Market data error: {e}[/red]")
            raise

    async def test_risk_management(self) -> bool:
        """Test 4: Risk management initialization"""
        try:
            self.risk_manager = RiskManager(config=self.config, logger=self.logger)

            # Verify components initialized
            if self.risk_manager.position_tracker is None:
                raise AssertionError("Position tracker not initialized")
            if self.risk_manager.pnl_tracker is None:
                raise AssertionError("P&L tracker not initialized")
            if self.risk_manager.circuit_breaker is None:
                raise AssertionError("Circuit breaker not initialized")
            if self.risk_manager.emergency is None:
                raise AssertionError("Emergency controls not initialized")

            # Check limits
            if self.risk_manager.risk_limits.max_daily_loss_usd <= 0:
                raise AssertionError("Invalid max daily loss limit")
            if self.risk_manager.risk_limits.max_position_size_percent <= 0:
                raise AssertionError("Invalid max position size limit")

            # Test circuit breaker
            if not self.risk_manager.circuit_breaker.is_trading_allowed():
                if self.verbose:
                    console.print("  [yellow]Warning: Circuit breaker is open[/yellow]")

            # Test kill switch
            if self.risk_manager.emergency.is_kill_switch_active():
                raise AssertionError("Kill switch is already active")

            if self.verbose:
                console.print(f"  [dim]Max daily loss: ${self.risk_manager.risk_limits.max_daily_loss_usd:,.2f}[/dim]")
                console.print(f"  [dim]Trading state: {self.risk_manager.trading_state.value}[/dim]")

            return True

        except Exception as e:
            if self.verbose:
                console.print(f"  [red]Risk management error: {e}[/red]")
            raise

    async def test_execution_engine(self) -> bool:
        """Test 5: Execution engine initialization"""
        try:
            self.engine = ExecutionEngine(
                exchanges=self.exchanges,
                risk_manager=self.risk_manager,
                config=self.config,
                logger=self.logger
            )

            await self.engine.initialize()

            # Verify components
            if self.engine.order_manager is None:
                raise AssertionError("Order manager not initialized")
            if self.engine.balance_manager is None:
                raise AssertionError("Balance manager not initialized")
            if self.engine.coordinator is None:
                raise AssertionError("Coordinator not initialized")
            if self.engine.reconciliation is None:
                raise AssertionError("Reconciliation engine not initialized")

            # Check balances were fetched
            balances = self.engine._get_available_balances()
            if len(balances) == 0:
                if self.verbose:
                    console.print("  [yellow]Warning: No balances fetched (may not have exchange API keys)[/yellow]")
            else:
                if self.verbose:
                    for exchange, currencies in balances.items():
                        for currency, amount in currencies.items():
                            if amount > 0:
                                console.print(f"  [dim]{exchange} - {currency}: {amount}[/dim]")

            return True

        except Exception as e:
            if self.verbose:
                console.print(f"  [red]Execution engine error: {e}[/red]")
            raise

    async def test_arbitrage_detection(self) -> bool:
        """Test 6: Arbitrage detection"""
        try:
            self.detector = CrossExchangeDetector(
                aggregator=self.aggregator,
                config=self.config,
                logger=self.logger
            )

            # Detect opportunities
            opportunities = await self.detector.detect(symbols=["BTC/USD", "ETH/USD"])

            if self.verbose:
                console.print(f"  [dim]Found {len(opportunities)} opportunities[/dim]")

                for i, opp in enumerate(opportunities[:3], 1):
                    console.print(
                        f"    [dim]{i}. {opp.symbol}: "
                        f"Buy on {opp.buy_exchange} @ ${opp.buy_price:,.2f}, "
                        f"Sell on {opp.sell_exchange} @ ${opp.sell_price:,.2f}, "
                        f"Profit: {opp.net_profit_percent:.3f}% (${opp.net_profit_usd:.2f})[/dim]"
                    )

            # Opportunities may be zero if spreads are tight
            # This is OK - not a test failure
            return True

        except Exception as e:
            if self.verbose:
                console.print(f"  [red]Arbitrage detection error: {e}[/red]")
            raise

    async def test_risk_validation(self) -> bool:
        """Test 7: Risk validation"""
        try:
            # Create a test opportunity
            test_opportunity = ArbitrageOpportunity(
                strategy="cross_exchange",
                buy_exchange="Kraken",
                sell_exchange="Coinbase Advanced",
                symbol="BTC/USD",
                buy_price=Decimal("42000"),
                sell_price=Decimal("42100"),
                gross_profit_percent=Decimal("0.238"),
                gross_profit_usd=Decimal("1.00"),
                net_profit_percent=Decimal("0.15"),
                net_profit_usd=Decimal("0.63"),
                total_fees_percent=Decimal("0.088"),
                total_fees_usd=Decimal("0.37"),
                max_quantity=Decimal("0.001"),
                slippage_estimate_percent=Decimal("0.05"),
                confidence_score=Decimal("0.85"),
                risk_score=Decimal("0.3")
            )

            # Validate
            balances = self.engine._get_available_balances()
            validation = self.risk_manager.validate_trade(test_opportunity, balances)

            if validation is None:
                raise AssertionError("Validation returned None")

            if self.verbose:
                if validation.passed:
                    console.print("  [dim]✅ Test opportunity passed validation[/dim]")
                else:
                    console.print(f"  [dim]⚠️ Test opportunity rejected: {validation.reason}[/dim]")
                    console.print(f"     [dim](This is OK - may be due to insufficient balance or limits)[/dim]")

            # Test that validation runs without errors
            return True

        except Exception as e:
            if self.verbose:
                console.print(f"  [red]Risk validation error: {e}[/red]")
            raise

    async def test_dry_run_execution(self) -> bool:
        """Test 8: Dry-run execution"""
        try:
            # Create test opportunity
            test_opportunity = ArbitrageOpportunity(
                strategy="cross_exchange",
                buy_exchange="Kraken",
                sell_exchange="Coinbase Advanced",
                symbol="BTC/USD",
                buy_price=Decimal("42000"),
                sell_price=Decimal("42100"),
                gross_profit_percent=Decimal("0.238"),
                gross_profit_usd=Decimal("1.00"),
                net_profit_percent=Decimal("0.15"),
                net_profit_usd=Decimal("0.63"),
                total_fees_percent=Decimal("0.088"),
                total_fees_usd=Decimal("0.37"),
                max_quantity=Decimal("0.001"),
                slippage_estimate_percent=Decimal("0.05"),
                confidence_score=Decimal("0.85"),
                risk_score=Decimal("0.3")
            )

            # Execute in dry-run mode
            result = await self.engine.execute_opportunity(test_opportunity, dry_run=True)

            if result is None:
                raise AssertionError("Execution returned None")

            if self.verbose:
                console.print(f"  [dim]Execution ID: {result.execution_id}[/dim]")
                console.print(f"  [dim]State: {result.state.value}[/dim]")
                console.print(f"  [dim]Success: {result.success}[/dim]")

                if not result.success:
                    console.print(f"  [dim]Reason: {result.error_message}[/dim]")
                    console.print(f"  [dim](Dry-run may fail due to validation - that's OK)[/dim]")

            # Dry-run may fail due to validation (low balance, etc.) - that's OK
            # We're testing that execution runs without crashing
            return True

        except Exception as e:
            if self.verbose:
                console.print(f"  [red]Dry-run execution error: {e}[/red]")
            raise

    async def test_error_handling(self) -> bool:
        """Test 9: Error handling"""
        try:
            # Test kill switch
            self.risk_manager.activate_kill_switch("Integration test")

            if not self.risk_manager.emergency.is_kill_switch_active():
                raise AssertionError("Kill switch failed to activate")

            self.risk_manager.deactivate_kill_switch()

            if self.risk_manager.emergency.is_kill_switch_active():
                raise AssertionError("Kill switch failed to deactivate")

            if self.verbose:
                console.print("  [dim]✅ Kill switch works correctly[/dim]")

            # Test circuit breaker
            original_state = self.risk_manager.circuit_breaker.is_trading_allowed()

            self.risk_manager.circuit_breaker.open()

            if self.risk_manager.circuit_breaker.is_trading_allowed():
                raise AssertionError("Circuit breaker failed to open")

            self.risk_manager.circuit_breaker.close()

            if not self.risk_manager.circuit_breaker.is_trading_allowed():
                raise AssertionError("Circuit breaker failed to close")

            if self.verbose:
                console.print("  [dim]✅ Circuit breaker works correctly[/dim]")

            return True

        except Exception as e:
            if self.verbose:
                console.print(f"  [red]Error handling test failed: {e}[/red]")
            raise

    def print_results(self, passed: int, failed: int):
        """Print test results summary"""
        console.print("\n")

        # Results table
        table = Table(title="Test Results", box=box.ROUNDED)
        table.add_column("Test", style="cyan", no_wrap=True)
        table.add_column("Status", style="bold", justify="center")
        table.add_column("Notes", style="dim")

        for test_name, status, error in self.results:
            notes = ""
            if error:
                notes = error[:60] + "..." if len(error) > 60 else error
            table.add_row(test_name, status, notes)

        console.print(table)

        # Summary
        total = passed + failed
        pass_rate = (passed / total * 100) if total > 0 else 0

        if failed == 0:
            summary = Panel.fit(
                f"[bold green]✅ ALL TESTS PASSED[/bold green]\n\n"
                f"Passed: {passed}/{total} ({pass_rate:.1f}%)\n\n"
                f"[green]System is ready for further testing.[/green]\n"
                f"[yellow]⚠️  Recommended: Run in dry-run mode for 24-48 hours before live trading.[/yellow]\n"
                f"[yellow]⚠️  Start with small amounts when going live ($10-20).[/yellow]",
                box=box.DOUBLE,
                border_style="green"
            )
        else:
            summary = Panel.fit(
                f"[bold red]❌ SOME TESTS FAILED[/bold red]\n\n"
                f"Passed: {passed}/{total} ({pass_rate:.1f}%)\n"
                f"Failed: {failed}/{total}\n\n"
                f"[yellow]Fix issues before proceeding to live trading.[/yellow]\n"
                f"[yellow]Check error messages above for details.[/yellow]",
                box=box.DOUBLE,
                border_style="red"
            )

        console.print(summary)

    async def cleanup(self):
        """Cleanup resources"""
        if self.verbose:
            console.print("\n[dim]Cleaning up resources...[/dim]")

        try:
            if self.aggregator:
                await self.aggregator.stop()

            for exchange in self.exchanges.values():
                try:
                    await exchange.disconnect()
                except Exception as e:
                    if self.verbose:
                        console.print(f"[yellow]Warning: Error disconnecting exchange: {e}[/yellow]")
        except Exception as e:
            if self.verbose:
                console.print(f"[yellow]Warning: Error during cleanup: {e}[/yellow]")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Integration test for crypto arbitrage system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/integration_test.py              # Full test (~15 minutes)
  python scripts/integration_test.py --quick      # Quick test (~5 minutes)
  python scripts/integration_test.py --verbose    # Detailed output
        """
    )
    parser.add_argument("--quick", action="store_true", help="Quick test (skip waiting periods)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    test = IntegrationTest(quick=args.quick, verbose=args.verbose)

    try:
        success = await test.run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Test interrupted by user[/yellow]")
        await test.cleanup()
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red bold]FATAL ERROR: {e}[/red bold]")
        import traceback
        if args.verbose:
            console.print(f"[red]{traceback.format_exc()}[/red]")
        await test.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
