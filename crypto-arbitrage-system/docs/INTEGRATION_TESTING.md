# Integration Testing Guide

## Overview

Integration testing validates that all system components work together correctly before live trading. This is a **CRITICAL** step to ensure system reliability and safety.

## Quick Start

### Prerequisites

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install rich  # For beautiful console output
   ```

2. **Configure System**:
   - Ensure `config/` YAML files are properly configured
   - Set up exchange API keys in `.env` (optional for basic tests)
   - Verify Redis is running (optional, tests will skip cache if unavailable)

3. **Verify Setup**:
   ```bash
   python scripts/health_check.py --verbose
   ```

## Test Suites

### 1. Standalone Integration Test (Recommended)

The standalone integration test script provides immediate feedback with beautiful console output.

#### Quick Test (~5 minutes)

Skips waiting periods - good for rapid iteration:

```bash
python scripts/integration_test.py --quick
```

#### Full Test (~15 minutes)

Includes waiting periods for market data aggregation - recommended before live trading:

```bash
python scripts/integration_test.py --verbose
```

#### What Gets Tested

The standalone script tests 9 critical components:

1. **Configuration Loading**
   - All YAML configs load correctly
   - Exchange settings present
   - Risk settings valid
   - Trading capital configured

2. **Exchange Connectivity**
   - Kraken connects and responds
   - Coinbase Advanced connects and responds
   - Health checks pass
   - Market data can be fetched

3. **Market Data Aggregation**
   - Real-time price feeds start
   - Data aggregates from multiple exchanges
   - Best bid/ask prices available

4. **Risk Management Initialization**
   - All risk components initialize
   - Limits are configured correctly
   - Circuit breaker is functional
   - Kill switch is operational

5. **Execution Engine Initialization**
   - All execution components initialize
   - Balance manager fetches balances
   - Order manager is ready
   - Coordinator is functional

6. **Arbitrage Detection**
   - Detector can scan markets
   - Opportunities are identified (may be zero)
   - Opportunity models are valid

7. **Risk Validation**
   - Test opportunities pass through validation
   - All 8 validation layers execute
   - Rejection reasons are clear

8. **Dry-Run Execution**
   - Execution pipeline runs end-to-end
   - Orders are created (but not sent)
   - Reconciliation works
   - Statistics are tracked

9. **Error Handling**
   - Kill switch activates/deactivates
   - Circuit breaker opens/closes
   - System fails gracefully

#### Expected Output

**All Tests Pass:**
```
=======================================================================
                     Test Results
=======================================================================
┌─────────────────────────┬────────┬───────┐
│ Test                    │ Status │ Notes │
├─────────────────────────┼────────┼───────┤
│ Configuration           │ ✅ PASS │       │
│ Exchange Connectivity   │ ✅ PASS │       │
│ Market Data             │ ✅ PASS │       │
│ Risk Management         │ ✅ PASS │       │
│ Execution Engine        │ ✅ PASS │       │
│ Arbitrage Detection     │ ✅ PASS │       │
│ Risk Validation         │ ✅ PASS │       │
│ Dry-Run Execution       │ ✅ PASS │       │
│ Error Handling          │ ✅ PASS │       │
└─────────────────────────┴────────┴───────┘

╔══════════════════════════════════════════════════════════════════╗
║                     ✅ ALL TESTS PASSED                          ║
║                                                                  ║
║ Passed: 9/9 (100.0%)                                            ║
║                                                                  ║
║ System is ready for further testing.                            ║
║ ⚠️  Recommended: Run in dry-run mode for 24-48 hours before    ║
║     live trading.                                                ║
║ ⚠️  Start with small amounts when going live ($10-20).          ║
╚══════════════════════════════════════════════════════════════════╝
```

### 2. Pytest Integration Tests

Pytest-based tests provide detailed test coverage and can be integrated into CI/CD.

#### Run All Integration Tests

```bash
pytest tests/integration/ -v
```

#### Run Specific Test Suites

**Full Pipeline Tests:**
```bash
pytest tests/integration/test_full_pipeline.py -v
```

**Exchange Health Tests:**
```bash
pytest tests/integration/test_exchange_health.py -v
```

**Execution Flow Tests:**
```bash
pytest tests/integration/test_execution_flow.py -v
```

#### Run With Coverage

```bash
pytest tests/integration/ -v --cov=src --cov-report=html
```

## Test Scenarios

### Full Pipeline Test

Tests complete workflow:
- Configuration → Exchanges → Market Data → Detection → Validation → Execution

**Files**: `tests/integration/test_full_pipeline.py`

**Coverage:**
- ✅ Configuration loading
- ✅ Exchange initialization
- ✅ Market data aggregation
- ✅ Risk management
- ✅ Execution engine
- ✅ Arbitrage detection
- ✅ Risk validation pipeline
- ✅ Dry-run execution
- ✅ Kill switch functionality
- ✅ Circuit breaker functionality
- ✅ Position tracking
- ✅ P&L tracking
- ✅ Balance management

### Exchange Health Test

Tests exchange connectivity and data quality:
- Individual exchange health checks
- Price data fetching
- Order book fetching
- Cross-exchange price consistency

**Files**: `tests/integration/test_exchange_health.py`

**Coverage:**
- ✅ Kraken connectivity
- ✅ Coinbase Advanced connectivity
- ✅ Health checks
- ✅ Ticker fetching
- ✅ Order book fetching
- ✅ Symbol normalization
- ✅ Cross-exchange price reasonableness
- ✅ Spread reasonableness
- ✅ Order book depth

### Execution Flow Test

Tests end-to-end execution workflows:
- Detection to validation flow
- Validation to execution flow
- Rejection handling
- Kill switch blocking
- Circuit breaker blocking

**Files**: `tests/integration/test_execution_flow.py`

**Coverage:**
- ✅ Opportunity detection to validation
- ✅ Validation to execution
- ✅ Execution plan creation
- ✅ Rejected opportunity handling
- ✅ Kill switch blocking execution
- ✅ Circuit breaker blocking execution
- ✅ Execution statistics tracking
- ✅ Balance reservation
- ✅ Multiple sequential executions
- ✅ Position tracking during execution
- ✅ P&L tracking during execution

## Troubleshooting

### Common Issues

#### Issue: Configuration Test Fails

**Symptoms:**
```
❌ Configuration FAIL
Error: Kraken not configured in config/exchanges.yaml
```

**Solutions:**
1. Verify `config/exchanges.yaml` exists and contains `kraken:` section
2. Check YAML syntax: `python -c "import yaml; yaml.safe_load(open('config/exchanges.yaml'))"`
3. Ensure all required config files exist:
   - `config/exchanges.yaml`
   - `config/trading.yaml`
   - `config/risk.yaml`
   - `config/compliance.yaml`

#### Issue: Exchange Connectivity Test Fails

**Symptoms:**
```
❌ Exchange Connectivity FAIL
Error: Kraken health check failed
```

**Solutions:**
1. **Check Internet Connection**: Verify you can reach exchange APIs
   ```bash
   curl -I https://api.kraken.com/0/public/SystemStatus
   ```

2. **Verify API Keys** (if required):
   - Check `.env` file has correct keys
   - Verify keys are active on exchange
   - Check key permissions (need at least "Query" for public endpoints)

3. **Check Exchange Status**: Exchanges may be down for maintenance
   - Kraken: https://status.kraken.com/
   - Coinbase: https://status.coinbase.com/

4. **Rate Limiting**: Wait a few minutes if you've been making many requests

#### Issue: Market Data Test Fails

**Symptoms:**
```
❌ Market Data FAIL
Warning: No market data received yet
```

**Solutions:**
1. **Wait Longer**: Market data needs time to aggregate
   - Use full test instead of quick: `python scripts/integration_test.py --verbose`
   - Wait time: Quick (3s), Full (10s)

2. **Check Redis** (optional):
   - If configured, verify Redis is running: `redis-cli ping`
   - If not using Redis, tests will work but may be slower

3. **Check WebSocket Connections**:
   - Some exchanges use WebSockets for real-time data
   - Verify firewalls aren't blocking WebSocket connections

#### Issue: Risk Validation Test Fails

**Symptoms:**
```
✅ Risk Validation PASS
⚠️  Test opportunity rejected: Insufficient balance
```

**Note:** This is **NOT** a failure - it's expected behavior!

**Explanation:**
- Test creates a small opportunity ($42 profit)
- Risk manager validates against real balances
- If you don't have $42,000+ in exchange accounts, it will be rejected
- The test passes as long as validation **runs without crashing**

**To Test With Real Balances:**
- Add exchange API keys to `.env`
- Fund exchanges with test capital
- Adjust test opportunity amounts in code

#### Issue: Dry-Run Execution Fails

**Symptoms:**
```
✅ Dry-Run Execution PASS
Reason: Rejected by risk manager
(Dry-run may fail due to validation - that's OK)
```

**Note:** This is **NORMAL** - see Risk Validation section above

**Real Failure Indicators:**
- Python exception/traceback
- "Execution returned None"
- Process crashes

#### Issue: Pytest Import Errors

**Symptoms:**
```
ImportError: No module named 'src.core.config'
```

**Solutions:**
1. **Run from project root**:
   ```bash
   cd crypto-arbitrage-system
   pytest tests/integration/ -v
   ```

2. **Install in development mode**:
   ```bash
   pip install -e .
   ```

3. **Check Python path**:
   ```python
   import sys
   print(sys.path)
   ```

#### Issue: Tests Hang or Timeout

**Symptoms:**
- Tests run forever without completing
- No output for several minutes

**Solutions:**
1. **Use Quick Mode**: `python scripts/integration_test.py --quick`
2. **Check for Deadlocks**: May indicate a bug in async code
3. **Increase Timeout**: Some exchanges may be slow to respond
4. **Check Network**: Slow network can cause timeouts

### Debug Mode

For maximum detail when troubleshooting:

```bash
# Standalone test with verbose output
python scripts/integration_test.py --verbose

# Pytest with verbose output
pytest tests/integration/ -vv -s

# Pytest with traceback on failure
pytest tests/integration/ -vv --tb=long

# Pytest with logging output
pytest tests/integration/ -vv --log-cli-level=DEBUG
```

## Before Live Trading

Complete this checklist before enabling live trading:

### Phase 1: Integration Testing ✅
- [ ] All 9 integration tests pass
- [ ] No errors in console output
- [ ] Exchange connectivity verified
- [ ] Market data flows correctly
- [ ] Risk validation works
- [ ] Dry-run execution succeeds

### Phase 2: Extended Dry-Run (24-48 hours)
- [ ] Run main system in dry-run mode for 24-48 hours
- [ ] Monitor logs for any errors
- [ ] Verify opportunities are detected
- [ ] Confirm risk controls trigger appropriately
- [ ] Check execution statistics are reasonable

### Phase 3: Paper Trading (1 week)
- [ ] Run in paper trading mode (simulated orders)
- [ ] Track simulated P&L
- [ ] Verify win rate and profitability
- [ ] Test during different market conditions
- [ ] Ensure no system crashes or hangs

### Phase 4: Live Trading Preparation
- [ ] Review and understand all risk limits
- [ ] Set conservative risk profile initially
- [ ] Fund exchanges with **SMALL** test amounts ($10-20)
- [ ] Set up monitoring and alerts
- [ ] Have kill switch procedure ready
- [ ] Document emergency contacts

### Phase 5: Live Trading Start
- [ ] Start with minimum position sizes
- [ ] Monitor actively for first 24 hours
- [ ] Gradually increase position sizes
- [ ] Review performance daily
- [ ] Adjust risk limits as needed

## Continuous Integration

### Automated Testing

Add to CI/CD pipeline:

```yaml
# .github/workflows/integration-tests.yml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install rich
      - name: Run integration tests
        run: |
          pytest tests/integration/ -v --cov=src
```

### Scheduled Testing

Run integration tests regularly to catch API changes:

```bash
# Add to crontab
0 0 * * * cd /path/to/crypto-arbitrage-system && python scripts/integration_test.py --quick >> logs/integration_test.log 2>&1
```

### Alert on Failure

Set up monitoring to alert on test failures:

```python
# In scripts/integration_test.py, add alerting:
if not success:
    send_alert("Integration tests failed!")
    send_email(recipient, "Integration Test Failure", results)
```

## Best Practices

1. **Run Tests Regularly**
   - After any code changes
   - Before deploying to production
   - Weekly to catch exchange API changes
   - After configuration changes

2. **Start Conservative**
   - Use quick test during development
   - Use full test before deployment
   - Run extended dry-run before live trading
   - Start with minimum position sizes

3. **Monitor Actively**
   - Watch first live trades closely
   - Review logs daily
   - Track performance metrics
   - Be ready to activate kill switch

4. **Document Changes**
   - Log all configuration changes
   - Note when tests fail and why
   - Track system behavior over time
   - Maintain runbook for common issues

5. **Safety First**
   - When in doubt, don't trade
   - Test thoroughly before live trading
   - Use kill switch liberally
   - Start small and scale gradually

## Support

For issues or questions:

1. **Check Logs**: `logs/` directory contains detailed logs
2. **Review Documentation**: Other docs in `docs/` directory
3. **GitHub Issues**: Report bugs and request features
4. **Email**: your.email@example.com

## Version History

- **v1.0.0** (2025-11-10): Initial integration test suite
  - 9-test standalone script with rich output
  - 3 pytest test suites (30+ tests total)
  - Comprehensive documentation
  - Full pipeline coverage

---

**Remember: Integration testing is your last line of defense before live trading. Take it seriously, and never skip this step!**
