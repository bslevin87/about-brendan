"""
Core modules for the crypto arbitrage system.

This package contains the fundamental building blocks including configuration
management, logging, and utilities.
"""

# CRITICAL: Load environment variables with file resolution FIRST
# This ensures file: references are resolved before any other module uses them
from . import env_loader  # noqa: F401 - Auto-runs load_environment()

# Now import other core modules
from .config import ConfigManager

__all__ = [
    "ConfigManager",
]
