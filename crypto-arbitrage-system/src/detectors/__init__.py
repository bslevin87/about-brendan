"""
Arbitrage opportunity detectors.

This package contains detectors for various arbitrage strategies:
- Cross-exchange arbitrage
- Triangle arbitrage
- Statistical arbitrage (future)
"""
from src.detectors.base_detector import BaseDetector
from src.detectors.cross_exchange import CrossExchangeDetector
from src.detectors.triangle import TriangleDetector

__all__ = [
    "BaseDetector",
    "CrossExchangeDetector",
    "TriangleDetector",
]
