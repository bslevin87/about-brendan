#!/usr/bin/env python3
"""
Crypto Arbitrage System - Main Entry Point

This is the main entry point for the crypto arbitrage trading system.
It initializes all components and runs the main trading loop.
"""
import asyncio
import signal
import sys
from typing import Dict, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.core.config import ConfigManager
from src.core.logging import setup_logger
from src.exchanges.adapters.kraken import KrakenExchange
from src.exchanges.adapters.coinbase_advanced import CoinbaseAdvancedExchange
from src.exchanges.rate_limiter import RateLimiter
from src.market_data.aggregator import MarketDataAggregator
from src.risk.manager import RiskManager
from src.execution.engine import ExecutionEngine
from src.detectors.cross_exchange import CrossExchangeDetector

console = Console()
logger = setup_logger(__name__)


class ArbitrageSystem:
    """Main arbitrage system coordinator."""

    def __init__(self):
        """Initialize the arbitrage system."""
        self.config: Optional[ConfigManager] = None
        self.exchanges: Dict[str, any] = {}
        self.aggregator: Optional[MarketDataAggregator] = None
        self.risk_manager: Optional[RiskManager] = None
        self.execution_engine: Optional[ExecutionEngine] = None
        self.detector: Optional[CrossExchangeDetector] = None
        self.running = False
        self.shutdown_event = asyncio.Event()

    async def initialize(self) -> None:
        """Initialize all system components."""
        try:
            console.print("\n[bold cyan]🚀 Initializing Crypto Arbitrage System[/bold cyan]\n")

            # Load configuration
            console.print("[yellow]Loading configuration...[/yellow]")
            self.config = ConfigManager()
            logger.info("configuration_loaded", mode=self.config.trading.mode)

            # Display configuration
            self._display_config()

            # Initialize exchanges
            console.print("\n[yellow]Connecting to exchanges...[/yellow]")
            await self._initialize_exchanges()

            # Initialize market data aggregator
            console.print("\n[yellow]Starting market data aggregator...[/yellow]")
            self.aggregator = MarketDataAggregator(
                exchanges=self.exchanges,
                config=self.config
            )

            # Get trading pairs from config
            pairs = self.config.trading.pairs.symbols
            await self.aggregator.start(symbols=pairs)
            console.print(f"[green]✅ Monitoring {len(pairs)} pairs: {', '.join(pairs)}[/green]")

            # Initialize risk manager
            console.print("\n[yellow]Initializing risk management...[/yellow]")
            self.risk_manager = RiskManager(config=self.config)
            console.print(f"[green]✅ Risk profile: {self.config.risk.active_profile}[/green]")

            # Initialize execution engine
            console.print("\n[yellow]Initializing execution engine...[/yellow]")
            self.execution_engine = ExecutionEngine(
                exchanges=self.exchanges,
                risk_manager=self.risk_manager,
                config=self.config
            )
            await self.execution_engine.start()
            console.print("[green]✅ Execution engine ready[/green]")

            # Initialize arbitrage detector
            console.print("\n[yellow]Initializing arbitrage detector...[/yellow]")
            self.detector = CrossExchangeDetector(
                exchanges=self.exchanges,
                config=self.config,
                execution_engine=self.execution_engine
            )
            console.print("[green]✅ Arbitrage detector ready[/green]")

            console.print("\n[bold green]✅ System initialization complete![/bold green]\n")

        except Exception as e:
            logger.error("system_initialization_failed", error=str(e))
            console.print(f"\n[bold red]❌ Initialization failed: {e}[/bold red]\n")
            raise

    async def _initialize_exchanges(self) -> None:
        """Initialize exchange connections."""
        enabled_exchanges = self.config.get_enabled_exchanges()

        for exchange_name in enabled_exchanges:
            try:
                exchange_config = getattr(self.config.exchanges, exchange_name)

                if exchange_name == "kraken":
                    rate_limiter = RateLimiter(
                        requests_per_second=exchange_config.rate_limit_requests_per_second,
                        burst_size=20,
                        name="kraken"
                    )
                    self.exchanges["Kraken"] = KrakenExchange(
                        config=exchange_config.model_dump(),
                        rate_limiter=rate_limiter
                    )
                    console.print("[green]✅ Kraken connected[/green]")

                elif exchange_name == "coinbase_advanced":
                    rate_limiter = RateLimiter(
                        requests_per_second=exchange_config.rate_limit_requests_per_second,
                        burst_size=15,
                        name="coinbase_advanced"
                    )
                    self.exchanges["Coinbase Advanced"] = CoinbaseAdvancedExchange(
                        config=exchange_config.model_dump(),
                        rate_limiter=rate_limiter
                    )
                    console.print("[green]✅ Coinbase Advanced connected[/green]")

            except Exception as e:
                logger.error("exchange_initialization_failed",
                           exchange=exchange_name, error=str(e))
                console.print(f"[red]❌ Failed to connect to {exchange_name}: {e}[/red]")

    def _display_config(self) -> None:
        """Display system configuration."""
        table = Table(title="System Configuration", show_header=True)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="yellow")

        table.add_row("Mode", self.config.trading.mode.upper())
        table.add_row("Risk Profile", self.config.risk.active_profile)
        table.add_row("Starting Capital", f"${self.config.trading.capital_allocation.total_capital_usd:,.2f}")
        table.add_row("Max Position Size", f"{self.risk_manager.risk_limits.max_position_size_percent:.1f}%" if self.risk_manager else "N/A")
        table.add_row("Min Profit Threshold", f"{self.config.trading.profit_thresholds.min_profit_bps / 100:.2f}%")

        console.print(table)

    async def run(self) -> None:
        """Run the main trading loop."""
        self.running = True

        console.print("\n[bold green]🔍 Starting arbitrage detection...[/bold green]")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        try:
            # Start the detector
            detector_task = asyncio.create_task(self.detector.start())

            # Wait for shutdown signal
            await self.shutdown_event.wait()

            # Stop detector
            await self.detector.stop()
            await detector_task

        except asyncio.CancelledError:
            logger.info("main_loop_cancelled")
        except Exception as e:
            logger.error("main_loop_error", error=str(e))
            console.print(f"\n[bold red]❌ Error in main loop: {e}[/bold red]\n")

    async def shutdown(self) -> None:
        """Gracefully shutdown the system."""
        if not self.running:
            return

        console.print("\n\n[yellow]Shutting down system...[/yellow]")
        self.running = False
        self.shutdown_event.set()

        try:
            # Stop execution engine
            if self.execution_engine:
                console.print("[yellow]Stopping execution engine...[/yellow]")
                await self.execution_engine.stop()

            # Stop aggregator
            if self.aggregator:
                console.print("[yellow]Stopping market data aggregator...[/yellow]")
                await self.aggregator.stop()

            # Disconnect exchanges
            console.print("[yellow]Disconnecting exchanges...[/yellow]")
            for exchange_name, exchange in self.exchanges.items():
                await exchange.disconnect()

            # Display final stats
            if self.risk_manager:
                self._display_final_stats()

            console.print("\n[bold green]✅ Shutdown complete[/bold green]\n")

        except Exception as e:
            logger.error("shutdown_error", error=str(e))
            console.print(f"\n[red]Error during shutdown: {e}[/red]\n")

    def _display_final_stats(self) -> None:
        """Display final P&L statistics."""
        stats = self.risk_manager.pnl_tracker.get_stats()

        table = Table(title="Final Statistics", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="yellow")

        table.add_row("Total Trades", str(stats['total_trades']))
        table.add_row("Winning Trades", str(stats['total_wins']))
        table.add_row("Losing Trades", str(stats['total_losses']))
        table.add_row("Win Rate", f"{stats['win_rate_percent']:.1f}%")
        table.add_row("Total P&L", f"${stats['total_pnl_usd']:.2f}")
        table.add_row("Average P&L", f"${stats['average_profit_usd']:.2f}")
        table.add_row("Best Trade", f"${stats['largest_win_usd']:.2f}")
        table.add_row("Worst Trade", f"${stats['largest_loss_usd']:.2f}")

        console.print("\n")
        console.print(table)


async def main():
    """Main entry point."""
    system = ArbitrageSystem()

    # Setup signal handlers
    def signal_handler(signum, frame):
        """Handle shutdown signals."""
        console.print("\n[yellow]Received shutdown signal...[/yellow]")
        asyncio.create_task(system.shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize system
        await system.initialize()

        # Run main loop
        await system.run()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        logger.error("system_error", error=str(e))
        console.print(f"\n[bold red]System error: {e}[/bold red]\n")
        sys.exit(1)
    finally:
        await system.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Goodbye![/yellow]\n")
        sys.exit(0)
