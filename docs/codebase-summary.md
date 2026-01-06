# MT5 Elliott Wave Trading System - Codebase Summary

**Last Updated**: 2026-01-06
**Current Phase**: Phase 9 (RiskGuard Key Level Proximity Validation)
**Total Repository**: 182,047 tokens, 781,719 characters, 84 files (includes dashboard and tests)

## Quick Overview

The MT5 Elliott Wave Auto-Trading System is a comprehensive automated trading platform for MetaTrader 5 that:
- Analyzes Elliott Wave patterns on XAUUSD (Gold)
- Uses Claude AI for intelligent trade signal generation
- Executes trades with dynamic position sizing and risk management
- Provides real-time Telegram notifications
- Includes trailing stop loss management with state machine
- Features paper trading mode for safe testing
- Tracks all trades and signals in SQLite database
- Includes 281 comprehensive unit and integration tests (100% passing)
- 66% overall test coverage with 84-100% core module coverage

## Architecture Layers

### Layer 1: Configuration & Initialization
```
config.py          - Pydantic Settings for all parameters
__init__.py        - Package initialization and logging setup
```

Configuration includes:
- MT5 connection parameters
- Trading parameters (position size, risk %, confidence thresholds)
- Telegram bot credentials
- Session-based confidence adjustments
- News filter blackout periods
- Trailing stop settings (ATR multiplier, breakeven buffer)

### Layer 2: Market Data & Execution
```
mt5_client.py      - MT5 platform integration
  - Connection management
  - OHLCV data fetching (H4, H1, M30, M15)
  - Technical indicators (RSI, EMA, MACD, ATR)
  - Market order execution (BUY/SELL)
  - Position sizing calculation
  - Partial position closing
  - Account info retrieval
```

Key Methods:
- `initialize()` / `shutdown()` - MT5 connection lifecycle
- `fetch_ohlcv()` - Get price data for analysis
- `calculate_indicators()` - Compute RSI, EMA, MACD, ATR
- `get_account_info()` - Current balance and margin
- `calculate_position_size()` - Risk-adjusted position sizing
- `place_market_order()` - Execute trades with SL/TP
- `get_positions()` - Retrieve open positions
- `modify_position()` - Update SL/TP on existing orders
- `close_partial()` - Partial position closure

### Layer 3: Signal Processing
```
signal_parser.py   - Trading signal models and validation
  - Pydantic models for signals (TradingSignal, TradeLevel, SignalMetadata)
  - JSON extraction with fallback strategies
  - Confidence score calculation
  - Signal validation and parsing
```

Signal Structure:
- Action (BUY/SELL)
- Entry price, stop loss
- Multiple take profit levels (TP1, TP2, TP3)
- Confidence score (0-100)
- Execution instructions
- Metadata (timestamp, session, spread check)

### Layer 4: AI Integration
```
claude_client.py   - Claude CLI subprocess wrapper
  - Message formatting for Elliott Wave analysis
  - Response JSON extraction
  - Retry logic with exponential backoff
  - Session context management
  - Error handling and logging
```

### Layer 5: Data Persistence
```
database.py        - SQLite trade and signal tracking
  Tables:
  - signals: Raw trading signals received
  - trades: Executed trades with tickets
  - tp_levels: Take profit levels for tracking

  Key Methods:
  - save_signal() - Store signal before execution
  - save_trade() - Record executed trade
  - update_signal_status() - Mark as executed/skipped/expired
  - get_open_trades() - Retrieve active positions
```

### Layer 6: Risk Validation (Phase 9 - NEW)
```
risk_guard.py      - Pre-execution risk validation (NEW)
  - Duplicate signal detection (content hashing)
  - Direction conflict handling (reject/close_first/hedge)
  - Key level proximity validation (XAUUSD-specific)
  - Concurrent position & lot exposure limits
  - Account risk percentage management

Key Components:
  - RiskGuard class with async validate() method
  - RiskCheckResult dataclass with detailed feedback
  - RiskCheckReason enum (8 rejection codes)
  - Signal-based key level extraction
  - ATR-based safe distance calculation
```

Configuration (Phase 9 additions):
- `key_level_proximity_enabled` (default: True)
- `key_level_proximity_min_pips` (default: 10.0)
- `key_level_proximity_atr_multiplier` (default: 1.5)

### Layer 7: Trade Execution & Management
```
trade_executor.py  - Orchestrates signal processing and execution
  - Signal execution workflow (post-validation)
  - Position sizing with confidence multiplier
  - Error handling and retry logic
  - Paper trading mode enforcement

trailing_stop_manager.py - Trailing stop state machine
  - States: inactive → activated → trailing
  - Activation triggers: TP1 hit OR profit > 1R
  - Breakeven + buffer logic (5 pips)
  - ATR-based trail distance (1.5x ATR)
```

### Layer 8: User Interface
```
telegram_bot.py    - Telegram bot for notifications and control
  - /start command
  - /signal - Send trading signal
  - /positions - View open positions
  - /trades - Get trade history
  - /balance - Account balance info
  - Real-time trade notifications
```

### Layer 8: Testing Infrastructure (Phase 7)
```
tests/conftest.py         - Centralized pytest fixtures
  - temp_db: Temporary SQLite database
  - mock_mt5: Mocked MT5 client
  - mock_settings: Test configuration
  - Environment setup (Telegram credentials)

tests/test_*.py           - 281 unit and integration tests
  - Signal parsing and validation
  - Database CRUD operations
  - Trade execution workflow
  - Trailing stop state machine
  - MT5 integration (mocked)
  - Telegram bot integration (mocked)

pytest.ini                - Pytest configuration
  - Async test support (pytest-asyncio)
  - Test discovery patterns
  - Coverage reporting
```

## Data Flow

### Trading Signal Execution Flow (Updated Phase 9)
```
1. Telegram /signal command (or Claude AI)
   ↓
2. Signal parsing and validation
   ↓
3. RISK VALIDATION (NEW - Phase 9)
   - Check duplicate within cooldown
   - Handle opposite direction positions
   - Validate key level proximity
   - Check position/lot exposure limits
   - Verify account risk percentage
   ↓ [If all checks pass]
4. Signal stored in database (status: pending)
   ↓
5. Position size calculated (risk % × confidence multiplier)
   ↓
6. Market order placed with SL/TP1
   ↓
7. Trade stored in database with ticket
   ↓
8. Trailing stop manager monitors position
   ↓
9. Partial closes at TP2, TP3
   ↓
10. Trade closed or stopped out
   ↓
11. Signal updated to 'executed' status
```

### Trailing Stop State Machine
```
Position Opened (inactive)
    ↓
Monitor for Activation:
  - TP1 hit (partial close)
  - OR Profit > 1R (unrealized)
    ↓
Activation Triggered (activated)
    ↓
Move SL to Breakeven + 5 pips
    ↓
Monitor for Trail Opportunity:
  - Price retraces by 1.5 × ATR
    ↓
Trail SL Upward (trailing)
    ↓
Repeat trail logic
```

## File Structure

### Source Code (src/)
| File | Purpose | Tests |
|------|---------|-------|
| config.py | Settings management | test_config.py |
| mt5_client.py | Platform integration | test_mt5.py |
| signal_parser.py | Signal models | test_signal_parser.py |
| claude_client.py | AI integration | test_claude_client.py |
| database.py | Trade persistence | test_database.py (16 tests) |
| risk_guard.py | Risk validation (Phase 9) | test_risk_guard.py (16+ tests) |
| trade_executor.py | Execution workflow | test_trade_executor.py (13 tests) |
| trailing_stop_manager.py | Stop loss management | test_trailing_stop.py (16 tests) |
| telegram_bot.py | User interface | test_telegram.py |

### Test Coverage (Phase 7)
```
Core Modules (91-100% coverage):
- config.py:              91%
- database.py:            91%
- signal_parser.py:       97%
- scheduler.py:           100%
- session_detector.py:    100%
- spread_checker.py:      100%

Trade Execution Modules (84-100%):
- trade_executor.py:      87%
- trailing_stop_manager.py: 84%
- claude_client.py:       94%
- news_calendar.py:       91%

Integration & UI (27-45%):
- mt5_client.py:          27% (mocked in tests)
- telegram_bot.py:        45% (mocked in tests)
- main.py:                0% (orchestration only)

OVERALL:                  281/281 tests passing (100%)
                          66% coverage
                          Execution: 9.21 seconds
```

### Documentation (plans/)
- **phase-01-project-setup.md** - Configuration infrastructure ✅
- **phase-02-mt5-data-export.md** - Data fetching and indicators ✅
- **phase-03-claude-integration.md** - AI signal generation ✅
- **phase-04-telegram-bot.md** - User interface and notifications ✅
- **phase-05-trade-execution.md** - Trade execution ✅
- **phase-06-orchestration.md** - System orchestration ✅
- **phase-06.5-news-integration.md** - News filtering ✅
- **phase-07-testing.md** - Testing and validation ✅ (current)
- **phase-08-web-dashboard.md** - Web UI planning (next)
- **phase-09-backtest-analytics.md** - Backtesting framework

## Key Design Patterns

### Lazy Loading Pattern
```python
class TradeExecutor:
    @property
    def mt5(self) -> MT5Client:
        if self._mt5 is None:
            self._mt5 = MT5Client()
        return self._mt5
```
Delays initialization until needed, avoiding circular dependencies.

### State Machine Pattern
```python
class TrailingState(Enum):
    INACTIVE = "inactive"      # Initial state
    ACTIVATED = "activated"    # First target hit or 1R profit
    TRAILING = "trailing"      # Actively trailing stop
```
Clear state transitions with validation.

### Singleton Pattern
```python
# Database singleton
database = Database()

# Config singleton
config = Settings()
```
Ensures single instance across application.

### Context Manager Pattern
```python
with sqlite3.connect(db_path) as conn:
    # Connection auto-closes
    conn.execute(query)
```
Ensures resource cleanup.

## Key Configuration Parameters

### Core Settings (from .env)
```python
# MT5
MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
TRADING_SYMBOL = "XAUUSD"

# Account
RISK_PERCENT = 1.0           # Risk per trade: 1% of balance
MAX_POSITION_SIZE = 0.1      # Max 0.1 lots per trade
PAPER_TRADING = True         # Safe mode default

# Confidence
FULL_POSITION_THRESHOLD = 75 # >= 75%: full position
HALF_POSITION_THRESHOLD = 60 # 60-74%: half position

# Session Adjustments
LONDON_SESSION_CONFIDENCE = 1.2   # +20% during London hours
NY_SESSION_CONFIDENCE = 1.0       # Normal during NY
ASIAN_SESSION_CONFIDENCE = 0.8    # -20% during Asia

# Trailing Stop
TRAILING_ATR_MULTIPLIER = 1.5    # Trail at 1.5 × ATR
BREAKEVEN_BUFFER_PIPS = 5        # Activation: breakeven + 5 pips

# News Filter
NEWS_FILTER_BEFORE = 60          # Blackout 60 min before
NEWS_FILTER_AFTER = 60           # Blackout 60 min after

# Telegram
TELEGRAM_BOT_TOKEN = "..."
TELEGRAM_CHAT_ID = "..."
```

## Testing Strategy

### Unit Tests (45 total)
- **test_config.py** - Configuration validation
- **test_mt5.py** - MT5 client methods
- **test_signal_parser.py** - Signal parsing and validation
- **test_claude_client.py** - AI integration
- **test_database.py** - Database CRUD operations (16 tests)
- **test_trade_executor.py** - Trade execution flow (13 tests)
- **test_trailing_stop.py** - Trailing stop state machine (16 tests)
- **test_telegram.py** - Telegram bot commands

### Test Patterns
```python
# Setup with mocks
@pytest.fixture
def mock_mt5():
    """Mock MT5Client for isolation"""

# Execute with test data
def test_position_sizing_full_confidence():
    size = executor.calculate_position_size(
        symbol="XAUUSD",
        entry=2000.00,
        stop=1990.00,
        confidence=85
    )
    assert size == 0.1  # Full position

# Verify state changes
def test_trailing_stop_activation():
    manager.check_all_positions()
    trade = db.get_trade_by_ticket(123)
    assert trade["trailing_state"] == "activated"
```

## Critical Code Sections

### Position Sizing Formula
```python
risk_amount = account_balance × (risk_percent / 100)
stop_distance = abs(entry_price - stop_loss)
position_size = risk_amount / (stop_distance × pip_value)

# Apply confidence multiplier
if confidence >= 75:
    multiplier = 1.0  # Full position
elif confidence >= 60:
    multiplier = 0.5  # Half position
else:
    multiplier = 0.0  # Skip trade

final_size = position_size × multiplier
final_size = min(final_size, max_position_size)
```

### Trailing Stop Activation Logic
```python
profit_in_r = trade["profit"] / (trade["entry"] - trade["stop_loss"])

if profit_in_r >= 1.0 or tp1_hit:
    # Activate trailing
    new_sl = entry_price + (5 * 0.1)  # Breakeven + 5 pips
    mt5_client.modify_position(ticket, new_sl)
    database.update_trailing_state(ticket, "activated")
```

### Market Order Execution
```python
# Retry on requote (3 attempts)
for attempt in range(3):
    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": "XAUUSD",
        "volume": 0.1,
        "type": ORDER_TYPE_BUY,
        "price": current_ask,
        "sl": 1990.00,
        "tp": 2010.00,
        "deviation": 20,      # Slippage tolerance
        "magic": 123456,      # Order identification
        "type_filling": mt5.ORDER_FILLING_IOC,
    })

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return result.order   # Success
    elif result.retcode == mt5.TRADE_RETCODE_REQUOTE:
        # Refresh price and retry
        continue
```

## Security Measures

### Paper Trading Enforcement
All MT5 operations check paper trading flag:
```python
if config.paper_trading:
    logger.info(f"PAPER: {order_type} {volume}")
    return -1  # Fake ticket
```

### SQL Injection Prevention
All database queries use parameterized statements:
```python
conn.execute(
    "INSERT INTO trades (symbol, action) VALUES (?, ?)",
    (symbol, action)  # Parameters, not string interpolation
)
```

### Input Validation
Pydantic models validate all inputs:
```python
class TradingSignal(BaseModel):
    action: Literal["BUY", "SELL"]
    entry_price: float = Field(gt=0)
    confidence: int = Field(ge=0, le=100)
```

### Authorization Checks
Telegram bot validates chat IDs:
```python
if message.chat_id != config.allowed_chat_id:
    logger.warning(f"Unauthorized access: {message.chat_id}")
    return
```

## Performance Characteristics

### Time Complexity
| Operation | Complexity | Notes |
|-----------|------------|-------|
| Position sizing | O(1) | Direct calculation |
| Order placement | O(1) | Single MT5 API call |
| Trailing check | O(N) | N = open positions |
| Database insert | O(1) | Single query |
| Get open trades | O(N) | N = trades, indexed |

### Resource Usage
- **Memory**: ~50 MB (base) + data buffers
- **MT5 API calls**: ~5-10 per cycle
- **Database queries**: ~2-5 per trade execution
- **Telegram API**: 1-2 requests per signal

### Bottlenecks
1. MT5 API calls (10-50ms per call) - unavoidable
2. Network latency for Telegram - <100ms typical
3. SQLite concurrent writes - acceptable for single-process

## Known Limitations & Future Work

### Current Limitations
- **Single Symbol**: Hardcoded for XAUUSD, gold-specific pip calculations
- **Single Strategy**: One magic number, one confidence schema
- **Local Database**: SQLite has limited concurrent write support
- **No News Integration**: Phase 6.5 upcoming
- **Manual Testing**: Requires live MT5 connection for demo account testing

### Outstanding Code Review Items
1. **Database Connection Leak** - Add explicit close pattern
2. **ATR Timeframe** - Make configurable for different volatility regimes
3. **Position Size Errors** - Replace silent fallbacks with exceptions
4. **Magic Number** - Move to config.py
5. **Multi-Symbol Support** - Fix hardcoded gold pip values

### Upcoming Phases
- **Phase 6**: System orchestration (scheduler, background workers)
- **Phase 6.5**: News integration (blackout periods)
- **Phase 7**: Testing framework (backtesting engine)
- **Phase 8**: Web dashboard (real-time monitoring)
- **Phase 9**: Analytics (trade statistics, performance metrics)

## Development Guidelines

### Code Organization
- **Features**: Organize by responsibility (mt5, signals, execution, database)
- **Testing**: 1:1 test file per source file
- **Naming**: snake_case for functions, PascalCase for classes
- **Documentation**: Docstrings for all public methods

### Standards
- **Type Hints**: Full type hints for all functions
- **Error Handling**: Graceful degradation with logging
- **Logging**: INFO for successes, ERROR for failures
- **Testing**: Unit tests with >80% coverage

### Before Production
1. Fix database connection resource leak
2. Add position sizing error alerts
3. Test with demo account
4. Review all code review findings
5. Update .env with production values

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total Files | 47 |
| Total Tokens | 122,128 |
| Source Files | 9 |
| Test Files | 8 |
| Test Cases | 45 |
| Test Pass Rate | 100% |
| Code Coverage | 84-96% |
| Lines of Implementation | ~1,985 |
| Documentation Files | 12+ |
| Phases Completed | 5 / 9 |

---

**Repository Location**: D:\ws\mymn
**Last Repository Update**: 2026-01-04 18:30 UTC
**Next Documentation Review**: After Phase 6 completion
