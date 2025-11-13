#!/usr/bin/env python3
"""
Quick test to verify API key configuration and file reference resolution.
This test doesn't require network access - just validates configuration.
"""

import os
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import ConfigManager

def test_environment_variables():
    """Test that environment variables are loaded correctly."""
    print("=" * 70)
    print("TEST 1: Environment Variables")
    print("=" * 70)

    # Check Kraken keys
    kraken_key = os.getenv('KRAKEN_API_KEY')
    kraken_secret = os.getenv('KRAKEN_API_SECRET')

    print(f"✅ Kraken API Key: {kraken_key[:20]}... ({len(kraken_key)} chars)")
    print(f"✅ Kraken Secret: {kraken_secret[:20]}... ({len(kraken_secret)} chars)")

    # Check Coinbase keys
    coinbase_key = os.getenv('COINBASE_ADVANCED_API_KEY')
    coinbase_secret = os.getenv('COINBASE_ADVANCED_API_SECRET')

    print(f"✅ Coinbase API Key: {coinbase_key[:40]}... ({len(coinbase_key)} chars)")
    print(f"✅ Coinbase Secret: {len(coinbase_secret)} chars")

    # Verify Coinbase secret is the actual key, not file reference
    if coinbase_secret.startswith('file:'):
        print("❌ FAIL: Coinbase secret still contains 'file:' prefix!")
        print("   File reference was NOT resolved automatically.")
        return False

    if coinbase_secret.startswith('-----BEGIN EC PRIVATE KEY-----'):
        print("✅ Coinbase secret is properly resolved from file")
        print(f"   First line: {coinbase_secret.split(chr(10))[0]}")
        print(f"   Has newlines: {chr(10) in coinbase_secret}")
    else:
        print("❌ FAIL: Coinbase secret doesn't look like an EC private key")
        return False

    print()
    return True


def test_config_manager():
    """Test ConfigManager loads keys correctly."""
    print("=" * 70)
    print("TEST 2: ConfigManager")
    print("=" * 70)

    config = ConfigManager()

    # Check configuration loaded
    print(f"✅ Mode: {config.trading.mode}")
    print(f"✅ Enabled exchanges: {config.get_enabled_exchanges()}")

    # Check Kraken keys
    kraken_keys = config.api_keys['kraken']
    print(f"✅ Kraken API Key: {kraken_keys['api_key'][:20]}... ({len(kraken_keys['api_key'])} chars)")
    print(f"✅ Kraken Secret: {kraken_keys['api_secret'][:20]}... ({len(kraken_keys['api_secret'])} chars)")

    # Check Coinbase keys
    coinbase_keys = config.api_keys['coinbase_advanced']
    print(f"✅ Coinbase API Key: {coinbase_keys['api_key'][:40]}...")
    print(f"✅ Coinbase Secret: {len(coinbase_keys['api_secret'])} chars")

    # Verify Coinbase secret format
    secret = coinbase_keys['api_secret']
    if not secret.startswith('-----BEGIN EC PRIVATE KEY-----'):
        print("❌ FAIL: Coinbase secret doesn't start with BEGIN marker")
        return False

    if not secret.strip().endswith('-----END EC PRIVATE KEY-----'):
        print("❌ FAIL: Coinbase secret doesn't end with END marker")
        return False

    lines = secret.split('\n')
    print(f"✅ Coinbase private key has {len(lines)} lines")
    print(f"   Structure: BEGIN -> {len(lines) - 2} data lines -> END")

    print()
    return True


def test_exchange_config():
    """Test exchange configurations."""
    print("=" * 70)
    print("TEST 3: Exchange Configuration")
    print("=" * 70)

    config = ConfigManager()

    # Kraken config
    kraken = config.exchanges.kraken
    print(f"✅ Kraken:")
    print(f"   URL: {kraken.api_url}")
    print(f"   Pairs: {len(kraken.supported_pairs)} ({', '.join(kraken.supported_pairs[:3])}...)")
    print(f"   Maker fee: {kraken.maker_fee * 100:.2f}%")
    print(f"   Taker fee: {kraken.taker_fee * 100:.2f}%")

    # Coinbase config
    coinbase = config.exchanges.coinbase_advanced
    print(f"✅ Coinbase Advanced:")
    print(f"   URL: {coinbase.api_url}")
    print(f"   Pairs: {len(coinbase.supported_pairs)} ({', '.join(coinbase.supported_pairs[:3])}...)")
    print(f"   Maker fee: {coinbase.maker_fee * 100:.2f}%")
    print(f"   Taker fee: {coinbase.taker_fee * 100:.2f}%")

    print()
    return True


def main():
    """Run all tests."""
    print("\n")
    print("🔍 API KEY CONFIGURATION TEST")
    print("=" * 70)
    print()

    try:
        # Run tests
        test1 = test_environment_variables()
        test2 = test_config_manager()
        test3 = test_exchange_config()

        # Summary
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)

        if test1 and test2 and test3:
            print("✅ ALL TESTS PASSED")
            print()
            print("Your API keys are properly configured!")
            print("File references are automatically resolved.")
            print()
            print("Next steps:")
            print("  1. Run: python scripts/integration_test.py")
            print("  2. Run: python src/main.py")
            print()
            return 0
        else:
            print("❌ SOME TESTS FAILED")
            print("Check the output above for details.")
            print()
            return 1

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
