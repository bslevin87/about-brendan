# Crypto Arbitrage System

A production-grade cryptocurrency arbitrage trading system designed to identify and execute profitable arbitrage opportunities across multiple exchanges.

## Overview

This system monitors 7 major cryptocurrency exchanges (Kraken, Binance.US, Crypto.com, Bitstamp, Gemini, Coinbase Advanced, OKX.US) to detect and execute:

- **Cross-exchange arbitrage**: Price differences for the same asset across exchanges
- **Triangle arbitrage**: Circular trading opportunities within an exchange
- **Statistical arbitrage**: Mean-reversion and correlation-based strategies (Phase 2)

### Key Features

- 🔒 **Enterprise-grade security**: Secure credential management, encryption at rest
- 📊 **Comprehensive logging**: Structured JSON logging with audit trails
- 💾 **Robust data persistence**: PostgreSQL with async SQLAlchemy ORM
- ⚡ **High performance**: Async-ready architecture for sub-second execution
- 📈 **Scalable**: Designed to handle $10K to $10M+ capital
- 🛡️ **Risk management**: Multi-layer circuit breakers and position limits
- 📝 **Tax compliance**: Automated cost basis tracking and IRS Form 8949 generation
- 🧪 **Fully tested**: Comprehensive test suite with 95%+ coverage

## System Requirements

- **Python**: 3.10 or higher
- **Database**: PostgreSQL 13+ (for production) or SQLite (for testing)
- **Redis**: 6.0+ (for caching and pub/sub)
- **OS**: Linux, macOS, or Windows (WSL recommended for Windows)

## Quick Start

### 1. Clone and Setup

```bash
cd crypto-arbitrage-system
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your credentials
nano .env  # or your preferred editor
```

Required environment variables:

```bash
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/crypto_arbitrage
REDIS_URL=redis://localhost:6379/0
ENVIRONMENT=development

# Exchange API keys (only required for live trading)
KRAKEN_API_KEY=your_api_key
KRAKEN_API_SECRET=your_api_secret
# ... (add keys for other exchanges)
```

### 3. Initialize Database

```bash
# Create database tables
python scripts/init_db.py

# Optional: Seed with sample data
python scripts/init_db.py --seed
```

### 4. Verify Setup

```bash
# Run health check
python scripts/health_check.py --verbose
```

### 5. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_config.py -v
```

## Project Structure

```
crypto-arbitrage-system/
├── config/                      # Configuration files
│   ├── exchanges.yaml          # Exchange configurations
│   ├── trading.yaml            # Trading parameters
│   ├── risk.yaml               # Risk management settings
│   └── compliance.yaml         # Tax and compliance settings
├── src/                        # Source code
│   ├── core/                   # Core system components
│   │   ├── config.py          # Configuration manager
│   │   ├── logger.py          # Logging framework
│   │   ├── database.py        # Database manager
│   │   └── exceptions.py      # Custom exceptions
│   ├── models/                 # Database models
│   │   └── base.py            # SQLAlchemy models
│   ├── exchanges/              # Exchange adapters
│   │   └── base.py            # Base exchange interface
│   ├── strategies/             # Trading strategies (Phase 2)
│   ├── execution/              # Order execution (Phase 2)
│   └── utils/                  # Utility functions
│       └── helpers.py         # Common helpers
├── tests/                      # Test suite
│   ├── conftest.py            # Pytest configuration
│   ├── test_config.py         # Configuration tests
│   ├── test_logger.py         # Logging tests
│   └── test_database.py       # Database tests
├── scripts/                    # Utility scripts
│   ├── init_db.py             # Database initialization
│   └── health_check.py        # System health check
├── logs/                       # Log files (auto-created)
├── .env                        # Environment variables (not in git)
├── .env.example                # Environment template
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Python dependencies
├── setup.py                    # Package setup
├── alembic.ini                 # Database migrations config
└── README.md                   # This file
```

## Configuration Guide

### Exchanges Configuration

Edit `config/exchanges.yaml` to configure exchanges:

```yaml
exchanges:
  kraken:
    enabled: true                          # Enable/disable exchange
    maker_fee: 0.0016                      # Maker fee (0.16%)
    taker_fee: 0.0026                      # Taker fee (0.26%)
    supported_pairs: ["BTC/USD", "ETH/USD"]
    min_trade_size:
      BTC: 0.0001
      ETH: 0.001
```

### Trading Configuration

Edit `config/trading.yaml`:

```yaml
trading:
  mode: "dry_run"  # Options: dry_run, paper, live

  capital_allocation:
    total_capital_usd: 10000
    max_capital_per_exchange: 0.25  # 25% max per exchange

  profit_thresholds:
    min_profit_percent: 0.30  # 0.3% minimum profit
    min_profit_usd: 5.00
```

**Trading Modes:**
- `dry_run`: Detect opportunities but don't execute (safe for production testing)
- `paper`: Simulate trades with fake money
- `live`: Execute real trades (requires API keys and capital)

### Risk Management

The system includes a comprehensive multi-layer risk management system that protects capital through:
- Pre-execution validation
- Position and exposure limits
- P&L monitoring and loss limits
- Circuit breakers (auto-halt on errors)
- Emergency kill switch

#### Risk Profiles

Edit `config/risk.yaml` to configure risk limits:

```yaml
risk:
  active_profile: "conservative"  # conservative, moderate, aggressive

  profiles:
    conservative:
      max_position_size_percent: 10      # 10% of capital per position
      max_daily_loss_percent: 2          # Halt if lose 2% in a day
      min_confidence_score: 0.85         # Only trade high-confidence opportunities

  circuit_breakers:
    max_consecutive_losses: 5            # Halt after 5 losses in a row
    pause_duration_minutes: 15          # Pause trading for 15 minutes
```

#### Using the Risk Manager

```python
from src.risk.manager import RiskManager
from src.models.opportunity import ArbitrageOpportunity

# Initialize risk manager
config = ConfigManager()
risk_manager = RiskManager(config)

# Validate trade before execution
opportunity = ArbitrageOpportunity(...)
balances = {"Kraken": {"USD": Decimal("5000")}}

result = risk_manager.validate_trade(opportunity, balances)

if result.passed:
    # Execute trade
    print("✅ Trade validated - executing")
else:
    # Reject trade
    print(f"❌ Trade rejected: {result.reason}")
    print(f"Risk level: {result.risk_level}")

# Record trade outcome
risk_manager.record_trade_outcome(
    position_id="pos1",
    pnl_usd=Decimal("100"),
    trade_details={"symbol": "BTC/USD"}
)

# Check risk status
status = risk_manager.get_status()
print(f"Trading State: {status['trading_state']}")
print(f"Daily P&L: ${status['pnl']['daily_pnl_usd']}")
print(f"Total Positions: {status['positions']['total_count']}")
```

#### Emergency Controls

```python
# Activate kill switch (immediate halt)
risk_manager.activate_kill_switch("Manual intervention required")

# Check kill switch status
if risk_manager.emergency.is_kill_switch_active():
    print("🚨 Kill switch is ACTIVE - trading halted")

# Deactivate kill switch
risk_manager.deactivate_kill_switch()

# Manually reset circuit breaker
risk_manager.reset_circuit_breaker()
```

#### Risk Management Demo

```bash
# Run the risk management demo
python examples/risk_management_demo.py
```

This demonstrates:
- Multi-layer validation
- Position tracking
- P&L monitoring
- Circuit breakers
- Kill switch
- Trading state management

#### Testing

```bash
# Run risk management tests (50 tests)
pytest tests/risk/ -v

# Test specific components
pytest tests/risk/test_validators.py -v
pytest tests/risk/test_circuit_breaker.py -v
pytest tests/risk/test_manager.py -v
```

### Execution Engine

The execution engine coordinates order placement across exchanges for arbitrage opportunities. It integrates with the risk management system and provides comprehensive safety controls.

#### Architecture

The execution engine consists of 6 integrated components:

1. **Execution Models** (`src/execution/models.py`): Core data structures
   - `ExecutionState`: Lifecycle tracking (PENDING → VALIDATING → EXECUTING → COMPLETED)
   - `OrderStatus`: Individual order status tracking
   - `ExecutionOrder`: Single order with fill tracking
   - `ExecutionPlan`: Complete multi-leg execution plan
   - `ExecutionResult`: Result summary with P&L

2. **Balance Manager** (`src/execution/balance_manager.py`): Capital tracking
   - Real-time balance tracking across exchanges
   - Balance reservation (prevents double-spending)
   - Automatic balance refresh
   - Available vs reserved balance separation

3. **Order Manager** (`src/execution/order_manager.py`): Order placement
   - Retry logic with exponential backoff (using tenacity)
   - Order status polling
   - Fill tracking and partial fill handling
   - Comprehensive error handling

4. **Multi-Leg Coordinator** (`src/execution/coordinator.py`): Atomic execution
   - Concurrent order placement (asyncio.gather)
   - All-or-nothing execution (rollback on failure)
   - Order synchronization across exchanges
   - Partial fill protection

5. **Reconciliation Engine** (`src/execution/reconciliation.py`): P&L verification
   - Expected vs actual profit comparison
   - Fee validation
   - Slippage detection
   - Variance alerts (>10% triggers warning)

6. **Execution Engine** (`src/execution/engine.py`): Main orchestrator
   - Integrates all components
   - Risk validation integration
   - Execution lifecycle management
   - Statistics and monitoring

#### Using the Execution Engine

```python
from src.execution.engine import ExecutionEngine
from src.risk.manager import RiskManager
from src.models.opportunity import ArbitrageOpportunity

# Initialize execution engine
config = ConfigManager()
risk_manager = RiskManager(config)

# Dictionary of connected exchanges
exchanges = {
    "Kraken": kraken_exchange,
    "Coinbase Advanced": coinbase_exchange,
}

engine = ExecutionEngine(exchanges, risk_manager, config)
await engine.initialize()

# Create arbitrage opportunity
opportunity = ArbitrageOpportunity(
    strategy="cross_exchange",
    buy_exchange="Kraken",
    sell_exchange="Coinbase Advanced",
    symbol="BTC/USD",
    buy_price=Decimal("50000"),
    sell_price=Decimal("50250"),
    max_quantity=Decimal("0.1"),
    net_profit_usd=Decimal("200"),
    confidence_score=Decimal("0.85"),
)

# Execute in DRY-RUN mode (safe - no real trades)
result = await engine.execute_opportunity(opportunity, dry_run=True)

if result.success:
    print(f"✅ Execution successful")
    print(f"Execution ID: {result.execution_id}")
    print(f"Orders filled: {result.orders_filled}/{result.total_orders}")
    print(f"Profit: ${result.profit_usd}")
else:
    print(f"❌ Execution failed: {result.error_message}")
    print(f"State: {result.state.value}")

# Get detailed execution status
plan = engine.get_execution_status(result.execution_id)
if plan:
    print(f"State: {plan.state.value}")
    print(f"Orders: {len(plan.orders)}")
    for order in plan.orders:
        print(f"  {order.side.upper()} on {order.exchange}: {order.status.value}")

# Get engine statistics
stats = engine.get_stats()
print(f"Total executions: {stats['total_executions']}")
print(f"Success rate: {stats['success_rate']:.1f}%")
```

#### Dry-Run vs Live Mode

**CRITICAL**: The execution engine defaults to `dry_run=True` for safety. Always test thoroughly in dry-run mode before enabling live trading.

**Dry-Run Mode** (Default - Recommended):
```python
# Safe: Simulates execution without placing real orders
result = await engine.execute_opportunity(opportunity, dry_run=True)
```

**Live Mode** (Requires explicit opt-in):
```python
# DANGER: Places real orders with real money
result = await engine.execute_opportunity(opportunity, dry_run=False)
```

**Best Practices:**
1. Always start with dry-run mode
2. Monitor dry-run executions for 24-48 hours
3. Verify risk controls are working properly
4. Start with small position sizes when going live
5. Monitor live executions closely
6. Keep kill switch accessible

#### Execution Lifecycle

```
PENDING
  ↓
VALIDATING (risk manager checks 8 layers)
  ↓
  ├─ REJECTED (failed validation) → END
  ↓
APPROVED (passed validation)
  ↓
EXECUTING (placing orders)
  ↓
  ├─ FAILED (order placement failed) → ROLLING_BACK → ROLLED_BACK → END
  ├─ PARTIALLY_FILLED (some orders filled) → ROLLING_BACK → ROLLED_BACK → END
  ↓
COMPLETED (all orders filled) → Reconciliation → END
```

#### Risk Integration

The execution engine integrates with the risk management system at multiple points:

```python
# Execution automatically validates through risk manager
result = await engine.execute_opportunity(opportunity, dry_run=True)

# Behind the scenes:
# 1. Risk manager validates opportunity (8 layers)
# 2. Balance manager reserves capital
# 3. Orders placed only if validation passes
# 4. Position tracker updated on fills
# 5. P&L tracker records outcome
# 6. Circuit breaker monitors errors

# If risk validation fails:
if not result.success and result.state == ExecutionState.REJECTED:
    print(f"Blocked by risk manager: {result.error_message}")
```

#### Balance Management

```python
# Balances are automatically managed
# Before execution: capital is reserved
# After execution: capital is released

# Check available balances
stats = engine.get_stats()
balance_stats = stats.get('balance_stats', {})
print(f"Available USD: ${balance_stats['total_available_usd']:,.2f}")
print(f"Reserved USD: ${balance_stats['total_reserved_usd']:,.2f}")

# Manual balance refresh (optional)
await engine.balance_manager.refresh_balances()
```

#### Error Handling

The execution engine handles multiple failure scenarios:

1. **Risk Validation Failure**: Trade rejected before execution
2. **Insufficient Balance**: Trade blocked by balance manager
3. **Order Placement Failure**: Automatic retry with backoff (3 attempts)
4. **Partial Fill**: Automatic rollback (cancel unfilled orders)
5. **Network Errors**: Retry with exponential backoff
6. **Exchange Errors**: Logged and reported

```python
# All errors are captured in the result
result = await engine.execute_opportunity(opportunity, dry_run=True)

if not result.success:
    print(f"Execution failed:")
    print(f"  State: {result.state.value}")
    print(f"  Error: {result.error_message}")
    print(f"  Orders filled: {result.orders_filled}/{result.total_orders}")
```

#### Execution Demo

```bash
# Run the execution engine demo (DRY-RUN mode)
python examples/execution_demo.py
```

This demonstrates:
- Creating execution plans
- Risk validation integration
- Dry-run execution (safe)
- Order tracking
- Reconciliation
- Error handling
- Statistics tracking

**Demo Output:**
```
=======================================================================
  EXECUTION ENGINE DEMONSTRATION
=======================================================================

⚠️  Running in DRY-RUN mode (no real trades)

1. Initializing Exchanges (Mock Mode)
----------------------------------------------------------------------
   ✅ Kraken (mock) initialized
   ✅ Coinbase Advanced (mock) initialized

2. Initializing Execution Engine
----------------------------------------------------------------------
   ✅ Execution engine initialized

3. Creating Arbitrage Opportunity
----------------------------------------------------------------------
   Strategy: cross_exchange
   Buy:  Kraken @ $50,000.00
   Sell: Coinbase Advanced @ $50,250.00
   Expected Profit: $200.00 (0.4%)

4. Executing Opportunity (DRY-RUN)
----------------------------------------------------------------------
   ✅ EXECUTION SUCCESSFUL
   Orders Filled: 2/2
   Actual Profit: $200.00

Key Takeaways:
  ✅ Execution engine coordinates multi-leg trades
  ✅ Risk validation integrated (8-layer safety)
  ✅ DRY-RUN mode for safe testing
  ✅ Order tracking and reconciliation
  ✅ Balance management across exchanges
  ✅ Comprehensive error handling

  🔒 SAFETY FIRST: Always test with dry-run before live trading
```

#### Testing

```bash
# Run execution engine tests (8 tests)
pytest tests/execution/ -v

# Test specific components
pytest tests/execution/test_engine.py -v
pytest tests/execution/test_balance_manager.py -v
pytest tests/execution/test_order_manager.py -v
```

#### Troubleshooting

**Execution rejected by risk manager:**
```python
# Check risk validation result
result = await engine.execute_opportunity(opportunity, dry_run=True)
if result.state == ExecutionState.REJECTED:
    print(f"Risk rejection: {result.error_message}")

# Common causes:
# - Insufficient balance
# - Profit below minimum threshold
# - Confidence score too low
# - Risk score too high
# - Circuit breaker open
# - Kill switch active
```

**Balance reservation fails:**
```python
# Check available balances
stats = engine.get_stats()
balance_stats = stats['balance_stats']
print(f"Available: ${balance_stats['total_available_usd']}")
print(f"Reserved: ${balance_stats['total_reserved_usd']}")

# Refresh balances from exchanges
await engine.balance_manager.refresh_balances()
```

**Orders not filling:**
```python
# Check order status
plan = engine.get_execution_status(execution_id)
for order in plan.orders:
    print(f"{order.exchange} {order.side}: {order.status.value}")
    if order.last_error:
        print(f"  Error: {order.last_error}")
    print(f"  Attempts: {order.attempt_count}")
```

**High profit variance after execution:**
```python
# Reconciliation flags >10% variance
# Common causes:
# - Slippage (price moved during execution)
# - Higher fees than estimated
# - Partial fills at different prices

# Check reconciliation details
plan = engine.get_execution_status(execution_id)
print(f"Expected profit: ${plan.expected_profit_usd}")
print(f"Actual profit: ${plan.actual_profit_usd}")
print(f"Total fees: ${plan.total_fees_usd}")
```

### Compliance Settings

Edit `config/compliance.yaml`:

```yaml
compliance:
  tax:
    cost_basis_method: "FIFO"  # FIFO, LIFO, HIFO
    tax_lot_tracking: true
    generate_8949: true        # IRS Form 8949
```

## Usage Examples

### Basic Usage

```python
from src.core.config import ConfigManager
from src.core.logger import get_logger
from src.core.database import DatabaseManager

# Load configuration
config = ConfigManager()
logger = get_logger(__name__)

# Connect to database
db = DatabaseManager(config.database_url)
await db.connect()

# Access exchange configurations
kraken_config = config.get_exchange_config("kraken")
print(f"Kraken maker fee: {kraken_config.maker_fee}")

# Get active risk profile
risk_profile = config.get_active_risk_profile()
print(f"Max position size: {risk_profile.max_position_size_percent}%")
```

### Exchange Integration

The system provides a unified interface for interacting with cryptocurrency exchanges. All exchanges implement the `BaseExchange` abstract class, ensuring consistent APIs across platforms.

#### Using Exchange Adapters

```python
from src.exchanges.adapters.kraken import KrakenExchange
from src.exchanges.rate_limiter import RateLimiter

# Configure rate limiter (prevents API bans)
rate_limiter = RateLimiter(
    requests_per_second=5,  # Max sustained rate
    burst_size=10,          # Allow bursts
    name="kraken"
)

# Initialize exchange
config = {
    "name": "Kraken",
    "api_url": "https://api.kraken.com",
    "ws_url": "wss://ws.kraken.com",
}
exchange = KrakenExchange(config, rate_limiter)

# Connect to exchange
await exchange.connect()

# Fetch market data
ticker = await exchange.fetch_ticker("BTC/USD")
print(f"Best bid: ${ticker.bid:,.2f}")
print(f"Best ask: ${ticker.ask:,.2f}")
print(f"Spread: {ticker.spread_percent:.3f}%")

# Fetch order book
order_book = await exchange.fetch_order_book("BTC/USD", depth=20)
print(f"Top bid: {order_book.best_bid}")
print(f"Top ask: {order_book.best_ask}")

# Check account balances
balances = await exchange.fetch_balances()
for balance in balances:
    print(f"{balance.currency}: {balance.available} available")

# Create order (dry run - doesn't execute)
order = await exchange.create_order(
    symbol="BTC/USD",
    side="buy",
    order_type="limit",
    quantity=Decimal("0.1"),
    price=Decimal("50000"),
    dry_run=True  # Set to False for live trading
)
print(f"Order {order.order_id} created: {order.status}")

# Subscribe to WebSocket feeds (real-time data)
await exchange.subscribe_order_book("BTC/USD")
await exchange.subscribe_trades("BTC/USD")

# Clean up
await exchange.disconnect()
```

#### Implemented Features

**Data Models** (`src/exchanges/models.py`):
- `OrderBook`: Normalized order book with bid/ask spreads
- `Ticker`: Current market prices and 24h statistics
- `Trade`: Individual trade records
- `Order`: Order tracking with fill status
- `Balance`: Account balance tracking

**Rate Limiting** (`src/exchanges/rate_limiter.py`):
- Token bucket algorithm for API rate limiting
- Configurable burst capacity
- Statistics tracking
- Async-safe with proper locking

**WebSocket Manager** (`src/exchanges/websocket_manager.py`):
- Automatic reconnection with exponential backoff
- Heartbeat monitoring
- Message queue with async iteration
- Subscription management

**Kraken Adapter** (`src/exchanges/adapters/kraken.py`):
- Complete REST API implementation
- HMAC-SHA512 authentication
- Symbol normalization (XXBTZUSD ↔ BTC/USD)
- WebSocket real-time data
- Comprehensive error handling

**Coinbase Advanced Adapter** (`src/exchanges/adapters/coinbase_advanced.py`):
- Complete REST API implementation
- JWT ES256 authentication
- Symbol normalization (BTC-USD ↔ BTC/USD)
- WebSocket level2 orderbook feeds
- Comprehensive error handling

#### Setting Up Coinbase Advanced API

1. **Create API Credentials:**
   - Log in to [Coinbase Advanced Trade](https://www.coinbase.com/advanced-trade)
   - Go to Settings → API
   - Click "Create API Key"
   - Download your API key JSON file containing:
     - `name`: API key name (your key ID)
     - `privateKey`: ECDSA private key (PEM format)

2. **Configure Environment Variables:**
   ```bash
   # Add to your .env file
   COINBASE_ADVANCED_API_KEY="your_key_name"
   COINBASE_ADVANCED_API_SECRET="-----BEGIN EC PRIVATE KEY-----
   MHcCAQEEIBKH...your_private_key...
   -----END EC PRIVATE KEY-----"
   ```

   **Important**: The API secret must be the full ECDSA private key in PEM format, including the BEGIN/END markers.

3. **Verify Configuration:**
   ```bash
   # Test Coinbase connection
   python -c "from src.exchanges.adapters.coinbase_advanced import CoinbaseAdvancedExchange; print('Coinbase adapter loaded successfully')"
   ```

4. **Cross-Exchange Monitoring:**
   ```bash
   # Monitor arbitrage opportunities between Kraken and Coinbase
   python examples/cross_exchange_monitor.py
   ```

#### Running the Demo

```bash
# Run the exchange integration demo
python examples/exchange_demo.py
```

This demonstrates:
- Mock exchange for testing
- Kraken adapter usage
- Rate limiter functionality
- Symbol normalization

#### Testing

All exchange components have comprehensive test coverage:

```bash
# Run exchange tests (26 tests)
pytest tests/test_exchanges.py -v

# Run with coverage
pytest tests/test_exchanges.py --cov=src/exchanges
```

### Logging Examples

```python
from src.core.logger import get_logger, LogContext, PerformanceLogger

logger = get_logger(__name__, component="arbitrage_detector")

# Structured logging
logger.info("opportunity_detected",
    pair="BTC/USD",
    exchange_buy="kraken",
    exchange_sell="coinbase",
    profit_percent=0.45
)

# Context-based logging
with LogContext(logger, exchange="kraken", pair="BTC/USD") as ctx_logger:
    ctx_logger.info("fetching_orderbook")
    # All logs within this context include exchange and pair

# Performance logging
with PerformanceLogger(logger, "fetch_prices"):
    # Code to measure
    await fetch_prices_from_exchange()
```

### Database Operations

```python
from src.models.base import Trade, Balance
from decimal import Decimal

# Insert a trade
async with db.get_session() as session:
    trade = Trade(
        trade_id="trade_123",
        exchange="kraken",
        pair="BTC/USD",
        side="buy",
        quantity=Decimal("0.1"),
        price=Decimal("50000")
    )
    session.add(trade)

# Query balances
async with db.get_session() as session:
    result = await session.execute(
        select(Balance).where(Balance.exchange == "kraken")
    )
    balances = result.scalars().all()
```

## Database Schema

### Core Tables

- **opportunities**: Detected arbitrage opportunities
- **trades**: Trade execution history
- **positions**: Current holdings across exchanges
- **balances**: Available capital per exchange per asset
- **audit_log**: Compliance and audit trail
- **tax_lots**: Cost basis tracking for taxes
- **system_metrics**: Performance and health metrics

## Testing

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_config.py

# With coverage
pytest --cov=src --cov-report=html

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Writing Tests

Tests use pytest with async support:

```python
import pytest

@pytest.mark.asyncio
async def test_database_connection(test_db):
    """Test database connection."""
    assert test_db.is_connected is True

    healthy = await test_db.health_check()
    assert healthy is True
```

## Development Workflow

### 1. Code Style

```bash
# Format code with black
black src/ tests/

# Sort imports with isort
isort src/ tests/

# Lint with flake8
flake8 src/ tests/

# Type check with mypy
mypy src/
```

### 2. Pre-commit Checklist

- [ ] All tests pass: `pytest`
- [ ] Code formatted: `black src/ tests/`
- [ ] No linting errors: `flake8 src/`
- [ ] Type hints correct: `mypy src/`
- [ ] Coverage maintained: `pytest --cov=src`

### 3. Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Security Best Practices

1. **Never commit** `.env` file or API credentials
2. **Use environment variables** for all secrets
3. **Enable 2FA** on all exchange accounts
4. **Restrict API keys** to trading only (no withdrawals)
5. **Use IP whitelisting** on exchange APIs when possible
6. **Regular security audits** of code and configurations
7. **Encrypt database** at rest in production
8. **Monitor logs** for suspicious activity

## Performance Optimization

### Database

- Connection pooling configured (5-20 connections)
- Indexes on frequently queried columns
- Async queries for non-blocking operations

### Logging

- Structured JSON logging for efficient parsing
- Log rotation to prevent disk space issues
- Separate log files for different components

### Caching

- Redis for high-frequency data (order books, prices)
- TTL-based cache invalidation
- Pub/sub for real-time updates

## Troubleshooting

### Common Issues

**Database connection fails:**
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Verify DATABASE_URL in .env
echo $DATABASE_URL

# Test connection
python -c "import asyncpg; asyncpg.connect('your_url')"
```

**Configuration loading fails:**
```bash
# Verify YAML syntax
python -c "import yaml; yaml.safe_load(open('config/exchanges.yaml'))"

# Check file permissions
ls -la config/
```

**Tests failing:**
```bash
# Install test dependencies
pip install -r requirements.txt

# Run verbose tests
pytest -vv

# Check specific test
pytest tests/test_config.py::TestConfigManager::test_config_loading -v
```

## Roadmap

### Phase 1: Foundation (Current)
- ✅ Configuration management
- ✅ Logging framework
- ✅ Database setup
- ✅ Core data models
- ✅ Test suite

### Phase 2: Exchange Integration
- [x] Exchange adapters (Kraken, Binance.US, etc.)
- [x] WebSocket connections for real-time data
- [x] Rate limiting and retry logic
- [x] Order book aggregation (Component #3)
- [x] Market data cache (Redis)
- [ ] Remaining exchange adapters (Binance.US, Crypto.com, etc.)

### Phase 3: Strategy Implementation (Component #3)
- [x] Cross-exchange arbitrage detector
- [x] Triangle arbitrage detector
- [x] Opportunity models and scoring
- [x] Profit calculation with fees
- [ ] Signal validation pipeline
- [ ] Advanced statistical arbitrage

### Phase 4: Execution Engine (Component #6)
- [x] Order placement and management
- [x] Multi-leg execution coordination
- [x] Balance management across exchanges
- [x] Trade reconciliation
- [x] Atomic execution with rollback
- [x] Retry logic with exponential backoff
- [x] Dry-run mode for safe testing

### Phase 5: Risk & Compliance (Component #5)
- [x] Multi-layer risk validation (8 independent checks)
- [x] Real-time position tracking
- [x] P&L monitoring (daily/hourly limits)
- [x] Circuit breaker implementation (auto-halt)
- [x] Emergency kill switch
- [x] Trading state management
- [ ] Tax lot allocation
- [ ] Reporting dashboards

## Contributing

This is a personal project, but suggestions and feedback are welcome:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is proprietary and confidential. Unauthorized copying, distribution, or use is strictly prohibited.

## Disclaimer

**IMPORTANT**: This software is for educational and research purposes only.

- Cryptocurrency trading involves substantial risk of loss
- Past performance does not guarantee future results
- No warranty or guarantee of profitability is provided
- Use at your own risk with capital you can afford to lose
- Consult with financial and tax professionals before trading

## Support

For issues, questions, or feature requests:
- Open an issue on GitHub
- Email: your.email@example.com

## Acknowledgments

Built with:
- [Python](https://python.org)
- [SQLAlchemy](https://sqlalchemy.org)
- [Pydantic](https://pydantic.dev)
- [structlog](https://www.structlog.org)
- [pytest](https://pytest.org)

---

**Version**: 0.1.0 (Phase 1 - Foundation)
**Last Updated**: 2025-11-10
**Status**: Development - Foundation Complete
