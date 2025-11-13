#!/usr/bin/env python3
"""
Quick verification script to check that the system is set up correctly.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

def verify_imports():
    """Verify that all core modules can be imported."""
    print("Verifying imports...")
    try:
        from src.core.config import ConfigManager
        from src.core.logger import get_logger, setup_logging
        from src.core.database import DatabaseManager
        from src.core.exceptions import ArbitrageSystemException
        from src.models.base import Base, Opportunity, Trade, Balance
        from src.utils.helpers import generate_id, format_price
        from src.exchanges.base import BaseExchange, MockExchange
        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def verify_configuration():
    """Verify configuration loading."""
    print("\nVerifying configuration...")
    try:
        from src.core.config import ConfigManager
        config = ConfigManager()
        print(f"✓ Configuration loaded successfully")
        print(f"  - Environment: {config.environment}")
        print(f"  - Trading mode: {config.trading.mode}")
        print(f"  - Enabled exchanges: {len(config.get_enabled_exchanges())}")
        return True
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return False

def verify_logging():
    """Verify logging setup."""
    print("\nVerifying logging...")
    try:
        from src.core.logger import get_logger, setup_logging
        setup_logging(log_level="INFO", log_to_file=False)
        logger = get_logger("test")
        logger.info("test_message", test="value")
        print("✓ Logging working correctly")
        return True
    except Exception as e:
        print(f"✗ Logging error: {e}")
        return False

def verify_helpers():
    """Verify utility helpers."""
    print("\nVerifying utility helpers...")
    try:
        from src.utils.helpers import (
            generate_id, format_price, format_percent,
            calculate_profit_percent, validate_pair
        )
        from decimal import Decimal

        # Test helpers
        assert len(generate_id("test")) > 0
        assert format_price(1234.56) == "$1,234.56"
        assert validate_pair("BTC/USD") == True
        profit = calculate_profit_percent(100, 101, 0.001)
        assert profit > 0

        print("✓ Utility helpers working correctly")
        return True
    except Exception as e:
        print(f"✗ Helper error: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_file_structure():
    """Verify file structure."""
    print("\nVerifying file structure...")
    required_files = [
        "config/exchanges.yaml",
        "config/trading.yaml",
        "config/risk.yaml",
        "config/compliance.yaml",
        "src/core/config.py",
        "src/core/logger.py",
        "src/core/database.py",
        "src/core/exceptions.py",
        "src/models/base.py",
        "src/utils/helpers.py",
        "tests/conftest.py",
        "tests/test_config.py",
        "requirements.txt",
        "setup.py",
        "README.md"
    ]

    missing = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing.append(file_path)

    if missing:
        print(f"✗ Missing files: {', '.join(missing)}")
        return False
    else:
        print(f"✓ All {len(required_files)} required files present")
        return True

def main():
    """Run all verifications."""
    print("=" * 60)
    print("CRYPTO ARBITRAGE SYSTEM - SETUP VERIFICATION")
    print("=" * 60)

    results = []
    results.append(("File Structure", verify_file_structure()))
    results.append(("Imports", verify_imports()))
    results.append(("Configuration", verify_configuration()))
    results.append(("Logging", verify_logging()))
    results.append(("Helpers", verify_helpers()))

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)

    print("=" * 60)
    if all_passed:
        print("✓ ALL VERIFICATIONS PASSED")
        print("\nThe system is ready for use!")
        print("\nNext steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Initialize database: python scripts/init_db.py")
        print("3. Run health check: python scripts/health_check.py")
        print("4. Run tests: pytest")
        return 0
    else:
        print("✗ SOME VERIFICATIONS FAILED")
        print("\nPlease check the errors above and fix them.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
