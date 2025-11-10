"""
Market data management package.

This package handles real-time market data aggregation, order book management,
spread calculation, and WebSocket feed processing.
"""
from src.market_data.aggregator import MarketDataAggregator
from src.market_data.cache import MarketDataCache
from src.market_data.feed_handler import FeedHandler
from src.market_data.order_book_manager import OrderBookManager
from src.market_data.spread_calculator import SpreadCalculator

__all__ = [
    "MarketDataAggregator",
    "MarketDataCache",
    "FeedHandler",
    "OrderBookManager",
    "SpreadCalculator",
]
