"""
Balance management system.

Manages available capital across exchanges:
- Real-time balance tracking
- Balance reservation for pending orders
- Balance release on completion
- Multi-exchange coordination
"""
from decimal import Decimal
from typing import Any, Dict

from src.core.logger import get_logger
from src.exchanges.base import BaseExchange

logger = get_logger(__name__, component="balance_manager")


class BalanceManager:
    """
    Manages available capital across exchanges.

    Tracks:
    - Available balance per exchange
    - Reserved balance (pending orders)
    - Real-time balance updates
    """

    def __init__(self, exchanges: Dict[str, BaseExchange]):
        """
        Initialize balance manager.

        Args:
            exchanges: Dictionary of exchange name -> BaseExchange instance
        """
        self.exchanges = exchanges

        # Available balances: {exchange: {currency: amount}}
        self.available_balances: Dict[str, Dict[str, Decimal]] = {}

        # Reserved balances (locked in pending orders)
        self.reserved_balances: Dict[str, Dict[str, Decimal]] = {}

        logger.info("Balance manager initialized")

    async def refresh_balances(self) -> None:
        """Fetch latest balances from all exchanges."""
        for exchange_name, exchange in self.exchanges.items():
            try:
                balances = await exchange.fetch_balances()

                self.available_balances[exchange_name] = {}
                for balance in balances:
                    self.available_balances[exchange_name][
                        balance.currency
                    ] = balance.free

                logger.debug(
                    "balances_refreshed",
                    exchange=exchange_name,
                    currencies=list(self.available_balances[exchange_name].keys()),
                )
            except Exception as e:
                logger.error(
                    "balance_refresh_failed",
                    exchange=exchange_name,
                    error=str(e),
                )

    def get_available_balance(self, exchange: str, currency: str) -> Decimal:
        """
        Get available balance for a currency on an exchange.

        Args:
            exchange: Exchange name
            currency: Currency symbol

        Returns:
            Available balance
        """
        if exchange not in self.available_balances:
            return Decimal("0")
        return self.available_balances[exchange].get(currency, Decimal("0"))

    def reserve_balance(
        self, exchange: str, currency: str, amount: Decimal
    ) -> bool:
        """
        Reserve balance for a pending order.

        Args:
            exchange: Exchange name
            currency: Currency symbol
            amount: Amount to reserve

        Returns:
            True if sufficient balance available and reserved
        """
        available = self.get_available_balance(exchange, currency)

        if available < amount:
            logger.warning(
                "insufficient_balance_to_reserve",
                exchange=exchange,
                currency=currency,
                required=float(amount),
                available=float(available),
            )
            return False

        # Initialize reserved if needed
        if exchange not in self.reserved_balances:
            self.reserved_balances[exchange] = {}
        if currency not in self.reserved_balances[exchange]:
            self.reserved_balances[exchange][currency] = Decimal("0")

        # Reserve the balance
        self.reserved_balances[exchange][currency] += amount
        self.available_balances[exchange][currency] -= amount

        logger.debug(
            "balance_reserved",
            exchange=exchange,
            currency=currency,
            amount=float(amount),
        )

        return True

    def release_balance(
        self, exchange: str, currency: str, amount: Decimal
    ) -> None:
        """
        Release reserved balance (order completed or cancelled).

        Args:
            exchange: Exchange name
            currency: Currency symbol
            amount: Amount to release
        """
        if exchange not in self.reserved_balances:
            return

        if currency not in self.reserved_balances[exchange]:
            return

        # Release the balance
        self.reserved_balances[exchange][currency] -= amount
        self.available_balances[exchange][currency] += amount

        logger.debug(
            "balance_released",
            exchange=exchange,
            currency=currency,
            amount=float(amount),
        )

    def get_total_balance_usd(self) -> Decimal:
        """
        Calculate total balance across all exchanges in USD.

        Returns:
            Total balance in USD
        """
        # Simplified - only counts USD balances
        # Real implementation would need price conversion
        total = Decimal("0")
        for exchange_balances in self.available_balances.values():
            total += exchange_balances.get("USD", Decimal("0"))
        return total

    def get_stats(self) -> Dict[str, Any]:
        """
        Get balance statistics.

        Returns:
            Dictionary with balance stats
        """
        total_reserved = Decimal("0")
        for exchange_reserved in self.reserved_balances.values():
            total_reserved += exchange_reserved.get("USD", Decimal("0"))

        return {
            "total_available_usd": float(self.get_total_balance_usd()),
            "total_reserved_usd": float(total_reserved),
            "exchanges": list(self.available_balances.keys()),
        }
