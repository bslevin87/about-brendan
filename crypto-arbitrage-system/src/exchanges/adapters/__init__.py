"""
Exchange adapters package.

This package contains concrete implementations of exchange adapters
for each supported cryptocurrency exchange.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.exchanges.adapters.kraken import KrakenExchange

__all__ = [
    "KrakenExchange",
]
