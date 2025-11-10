#!/usr/bin/env python3
"""
System health check script.

This script verifies that all system components are functioning correctly.
Use this to validate the system setup and diagnose issues.

Usage:
    python scripts/health_check.py [--verbose]

Options:
    --verbose: Show detailed output for each check
"""
import asyncio
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.config import ConfigManager
from src.core.database import DatabaseManager
from src.core.logger import get_logger, setup_logging

# Setup logging
setup_logging(log_level="INFO")
logger = get_logger(__name__, component="health_check")


class HealthCheck:
    """Health check manager."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize health check.

        Args:
            verbose: Whether to show verbose output
        """
        self.verbose = verbose
        self.results: List[Tuple[str, bool, str]] = []

    def add_result(self, check_name: str, passed: bool, message: str = "") -> None:
        """
        Add a check result.

        Args:
            check_name: Name of the check
            passed: Whether the check passed
            message: Optional message with details
        """
        self.results.append((check_name, passed, message))

        status = "✓" if passed else "✗"
        level = "info" if passed else "error"
        log_msg = f"{status} {check_name}"

        if message and (self.verbose or not passed):
            log_msg += f": {message}"

        if level == "info":
            logger.info(log_msg)
        else:
            logger.error(log_msg)

    def get_summary(self) -> Dict[str, int]:
        """
        Get summary of health check results.

        Returns:
            Dictionary with passed, failed, and total counts
        """
        passed = sum(1 for _, p, _ in self.results if p)
        failed = sum(1 for _, p, _ in self.results if not p)
        return {
            "total": len(self.results),
            "passed": passed,
            "failed": failed
        }

    def all_passed(self) -> bool:
        """Check if all tests passed."""
        return all(passed for _, passed, _ in self.results)


async def check_configuration(health: HealthCheck) -> None:
    """
    Check configuration loading and validation.

    Args:
        health: HealthCheck instance
    """
    logger.info("Checking configuration...")

    try:
        config = ConfigManager()
        health.add_result(
            "Configuration Loading",
            True,
            "All configuration files loaded successfully"
        )

        # Check exchanges
        enabled_exchanges = config.get_enabled_exchanges()
        if len(enabled_exchanges) >= 2:
            health.add_result(
                "Exchange Configuration",
                True,
                f"{len(enabled_exchanges)} exchanges enabled"
            )
        else:
            health.add_result(
                "Exchange Configuration",
                False,
                "Need at least 2 exchanges enabled"
            )

        # Check trading mode
        health.add_result(
            "Trading Mode",
            True,
            f"Mode: {config.trading.mode}"
        )

        # Check risk profile
        risk_profile = config.get_active_risk_profile()
        health.add_result(
            "Risk Profile",
            True,
            f"Active profile: {config.risk.active_profile}"
        )

        return config

    except Exception as e:
        health.add_result(
            "Configuration Loading",
            False,
            str(e)
        )
        return None


async def check_database(health: HealthCheck, config: ConfigManager) -> None:
    """
    Check database connectivity and tables.

    Args:
        health: HealthCheck instance
        config: Configuration manager
    """
    logger.info("Checking database...")

    db_manager = None
    try:
        # Create database manager
        db_manager = DatabaseManager(config.database_url)
        health.add_result(
            "Database Manager",
            True,
            "Database manager created"
        )

        # Connect to database
        await db_manager.connect()
        health.add_result(
            "Database Connection",
            True,
            "Connected successfully"
        )

        # Health check
        healthy = await db_manager.health_check()
        health.add_result(
            "Database Health",
            healthy,
            "Database responding" if healthy else "Database not responding"
        )

        # Check pool status
        pool_status = await db_manager.get_pool_status()
        health.add_result(
            "Connection Pool",
            True,
            f"Pool size: {pool_status.get('size', 'N/A')}"
        )

        # Verify tables exist
        query = """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = 'public';
        """
        result = await db_manager.execute_query(query)
        table_count = result.fetchone()[0]

        health.add_result(
            "Database Tables",
            table_count >= 7,
            f"{table_count} tables found"
        )

    except Exception as e:
        health.add_result(
            "Database Connection",
            False,
            str(e)
        )
    finally:
        if db_manager and db_manager.is_connected:
            await db_manager.disconnect()


async def check_logging(health: HealthCheck) -> None:
    """
    Check logging system.

    Args:
        health: HealthCheck instance
    """
    logger.info("Checking logging system...")

    try:
        # Test logger creation
        test_logger = get_logger("test", component="health_check")
        health.add_result(
            "Logger Creation",
            True,
            "Logger created successfully"
        )

        # Check log directory
        log_dir = project_root / "logs"
        if log_dir.exists():
            health.add_result(
                "Log Directory",
                True,
                f"Log directory exists: {log_dir}"
            )
        else:
            health.add_result(
                "Log Directory",
                False,
                f"Log directory not found: {log_dir}"
            )

    except Exception as e:
        health.add_result(
            "Logging System",
            False,
            str(e)
        )


async def check_file_structure(health: HealthCheck) -> None:
    """
    Check project file structure.

    Args:
        health: HealthCheck instance
    """
    logger.info("Checking file structure...")

    required_dirs = [
        "src/core",
        "src/models",
        "src/exchanges",
        "src/strategies",
        "src/execution",
        "src/utils",
        "config",
        "tests",
        "scripts"
    ]

    required_files = [
        "config/exchanges.yaml",
        "config/trading.yaml",
        "config/risk.yaml",
        "config/compliance.yaml",
        ".env.example",
        ".gitignore",
        "requirements.txt"
    ]

    # Check directories
    missing_dirs = []
    for dir_path in required_dirs:
        full_path = project_root / dir_path
        if not full_path.exists():
            missing_dirs.append(dir_path)

    health.add_result(
        "Directory Structure",
        len(missing_dirs) == 0,
        f"Missing directories: {', '.join(missing_dirs)}" if missing_dirs else "All directories present"
    )

    # Check files
    missing_files = []
    for file_path in required_files:
        full_path = project_root / file_path
        if not full_path.exists():
            missing_files.append(file_path)

    health.add_result(
        "Required Files",
        len(missing_files) == 0,
        f"Missing files: {', '.join(missing_files)}" if missing_files else "All files present"
    )


async def check_environment_variables(health: HealthCheck) -> None:
    """
    Check required environment variables.

    Args:
        health: HealthCheck instance
    """
    logger.info("Checking environment variables...")

    import os

    required_vars = [
        "DATABASE_URL",
        "REDIS_URL",
        "ENVIRONMENT"
    ]

    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    health.add_result(
        "Environment Variables",
        len(missing_vars) == 0,
        f"Missing variables: {', '.join(missing_vars)}" if missing_vars else "All required variables set"
    )


async def main() -> None:
    """Main function to run health checks."""
    import argparse

    parser = argparse.ArgumentParser(description="System health check")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show verbose output"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("CRYPTO ARBITRAGE SYSTEM - HEALTH CHECK")
    logger.info("=" * 60)

    health = HealthCheck(verbose=args.verbose)

    # Run all health checks
    await check_file_structure(health)
    await check_environment_variables(health)
    await check_logging(health)

    config = await check_configuration(health)
    if config:
        await check_database(health, config)

    # Print summary
    logger.info("=" * 60)
    logger.info("HEALTH CHECK SUMMARY")
    logger.info("=" * 60)

    summary = health.get_summary()
    logger.info(f"Total checks: {summary['total']}")
    logger.info(f"Passed: {summary['passed']}")
    logger.info(f"Failed: {summary['failed']}")

    if health.all_passed():
        logger.info("=" * 60)
        logger.info("✓ ALL HEALTH CHECKS PASSED")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        logger.error("=" * 60)
        logger.error("✗ SOME HEALTH CHECKS FAILED")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
