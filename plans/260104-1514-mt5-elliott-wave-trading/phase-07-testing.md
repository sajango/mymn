# Phase 7: Testing & Paper Trading

## Context Links
- [Plan Overview](./plan.md)
- [Phase 6: Orchestration](./phase-06-orchestration.md)

## Overview
- **Priority**: P1
- **Status**: Pending
- **Effort**: 4h
- **Description**: Comprehensive testing and paper trading validation

## Key Insights
- Unit tests for each component
- Integration tests for flow
- 2-4 weeks paper trading before live
- Track signal accuracy metrics
- Daily loss limit check

## Requirements

### Functional
- Unit tests for all modules
- Integration test for full flow
- Paper trading mode validation
- Performance metrics tracking
- Signal accuracy analysis

### Non-Functional
- pytest for testing
- pytest-asyncio for async tests
- Mocking for external dependencies

## Test Coverage Goals

| Module | Target Coverage |
|--------|-----------------|
| config.py | 90% |
| mt5_client.py | 80% (mock MT5) |
| claude_client.py | 80% (mock API) |
| signal_parser.py | 95% |
| telegram_bot.py | 70% (mock bot) |
| database.py | 90% |
| scheduler.py | 80% |
| main.py | 60% (integration) |

## Implementation Steps

1. **Create tests/conftest.py**

```python
"""Pytest fixtures"""
import pytest
from datetime import datetime
from pathlib import Path
import tempfile

from src.signal_parser import TradingSignal, Signal, TakeProfit, WaveAnalysis


@pytest.fixture
def sample_signal():
    """Sample trading signal for tests"""
    return TradingSignal(
        timestamp=datetime(2026, 1, 4, 15, 0, 0),
        symbol="XAUUSD",
        signal=Signal(
            action="BUY",
            entry_price=3340.0,
            stop_loss=3310.0,
            stop_loss_atr=3312.5,
            take_profit=[
                TakeProfit(level="TP1", price=3380.0, close_percent=50),
                TakeProfit(level="TP2", price=3420.0, close_percent=30),
                TakeProfit(level="TP3", price=3450.0, close_percent=20),
            ],
            risk_reward=2.67,
            confidence=78,
        ),
        wave_analysis=WaveAnalysis(
            h4_trend="bullish",
            current_wave="wave_4_complete",
        ),
    )


@pytest.fixture
def temp_db():
    """Temporary database for tests"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def sample_csv_content():
    """Sample CSV data"""
    return """timestamp,open,high,low,close,tick_volume,rsi_14,ema_34,ema_89,macd,macd_signal,macd_histogram,atr_14
2026.01.04 12:00,3340.50,3345.20,3338.00,3342.80,1234,52.3,3341.5,3335.2,2.5,1.8,0.7,12.5
2026.01.04 12:15,3342.80,3348.00,3341.00,3346.50,1456,54.2,3342.0,3336.0,2.8,2.0,0.8,12.3
"""
```

2. **Create tests/test_signal_parser.py**

```python
"""Tests for signal parsing"""
import pytest
from src.signal_parser import (
    parse_signal,
    extract_json_from_text,
    TradingSignal,
)


class TestExtractJson:
    def test_extract_from_code_block(self):
        text = '''Some text
```json
{"signal": {"action": "BUY", "confidence": 75}}
```
More text'''
        result = extract_json_from_text(text)
        assert result["signal"]["action"] == "BUY"

    def test_extract_from_raw_json(self):
        text = 'Analysis: {"signal": {"action": "SELL", "confidence": 60}}'
        result = extract_json_from_text(text)
        assert result["signal"]["action"] == "SELL"

    def test_no_json_returns_none(self):
        result = extract_json_from_text("No JSON here")
        assert result is None


class TestParseSignal:
    def test_valid_buy_signal(self):
        response = '''```json
{
  "timestamp": "2026-01-04T15:00:00Z",
  "symbol": "XAUUSD",
  "signal": {
    "action": "BUY",
    "entry_price": 3340.0,
    "stop_loss": 3310.0,
    "take_profit": [{"level": "TP1", "price": 3380.0, "close_percent": 50}],
    "risk_reward": 2.5,
    "confidence": 78
  }
}```'''
        signal = parse_signal(response)
        assert signal is not None
        assert signal.signal.action == "BUY"
        assert signal.signal.confidence == 78

    def test_no_trade_signal(self):
        response = '{"signal": {"action": "NO_TRADE", "confidence": 30}}'
        signal = parse_signal(response)
        assert signal is not None
        assert signal.signal.action == "NO_TRADE"

    def test_invalid_action_fails(self):
        response = '{"signal": {"action": "HOLD", "confidence": 50}}'
        signal = parse_signal(response)
        assert signal is None

    def test_confidence_out_of_range_fails(self):
        response = '{"signal": {"action": "BUY", "confidence": 150}}'
        signal = parse_signal(response)
        assert signal is None
```

3. **Create tests/test_database.py**

```python
"""Tests for database operations"""
import pytest
from src.database import Database


class TestDatabase:
    def test_save_and_retrieve_signal(self, sample_signal, temp_db):
        db = Database(temp_db)
        signal_id = db.save_signal(sample_signal)
        assert signal_id > 0

    def test_save_trade(self, sample_signal, temp_db):
        db = Database(temp_db)
        signal_id = db.save_signal(sample_signal)
        trade_id = db.save_trade(signal_id, 12345, 0.1, sample_signal)
        assert trade_id > 0

    def test_get_open_trades(self, sample_signal, temp_db):
        db = Database(temp_db)
        signal_id = db.save_signal(sample_signal)
        db.save_trade(signal_id, 12345, 0.1, sample_signal)

        trades = db.get_open_trades()
        assert len(trades) == 1
        assert trades[0]["ticket"] == 12345

    def test_update_signal_status(self, sample_signal, temp_db):
        db = Database(temp_db)
        signal_id = db.save_signal(sample_signal)
        db.update_signal_status(signal_id, "executed")
        # No assertion needed - just checking it doesn't error
```

4. **Create tests/test_integration.py**

```python
"""Integration tests for full flow"""
import pytest
from unittest.mock import Mock, patch, AsyncMock


@pytest.mark.asyncio
async def test_full_analysis_flow():
    """Test complete analysis flow with mocks"""
    # This would mock MT5, Claude, and Telegram
    # and verify the full flow works
    pass  # TODO: Implement


@pytest.mark.asyncio
async def test_execute_callback():
    """Test trade execution callback"""
    pass  # TODO: Implement
```

5. **Paper Trading Checklist**

```markdown
# Paper Trading Validation Checklist

## Week 1: System Stability
- [ ] Bot runs 24/7 without crashes
- [ ] All M15 triggers fire correctly
- [ ] Claude API calls succeed >95%
- [ ] Telegram notifications delivered
- [ ] Database records all signals

## Week 2: Signal Quality
- [ ] Review 20+ signals manually
- [ ] Compare to actual price movement
- [ ] Calculate theoretical win rate
- [ ] Identify false signals

## Week 3: Execution Simulation
- [ ] Simulate Execute on all signals
- [ ] Track theoretical P&L
- [ ] Calculate drawdown
- [ ] Verify risk management

## Week 4: Go-Live Preparation
- [ ] Daily loss limit working
- [ ] Circuit breaker tested
- [ ] Backup/restore database
- [ ] Document lessons learned

## Metrics to Track
| Metric | Target | Actual |
|--------|--------|--------|
| Signal accuracy | >60% | |
| Win rate (executed) | >50% | |
| Avg R:R achieved | >1.5 | |
| Max drawdown | <10% | |
| System uptime | >99% | |
```

## Todo List

- [ ] Create tests/conftest.py with fixtures
- [ ] Write tests for signal_parser.py
- [ ] Write tests for database.py
- [ ] Write tests for mt5_client.py (mocked)
- [ ] Write tests for telegram_bot.py (mocked)
- [ ] Create integration test
- [ ] Run paper trading for 2 weeks minimum
- [ ] Document results and tune

## Success Criteria

- [ ] >80% test coverage on core modules
- [ ] All tests pass
- [ ] Paper trading shows positive expectancy
- [ ] No critical bugs in 1 week
- [ ] User approves go-live

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| False confidence | Medium | High | 2+ weeks paper |
| Curve fitting | Medium | High | Out-of-sample test |
| Execution slippage | Medium | Medium | Factor into R:R |

## Security Considerations

- No live credentials in tests
- Mock all external services
- Test database is temporary

## Next Steps

After paper trading validation:
1. Switch PAPER_TRADING=false
2. Start with minimum lot size
3. Monitor closely for 1 week
4. Gradually increase size

---

*Implementation complete. Ready for development phase.*
