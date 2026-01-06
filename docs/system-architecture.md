# System Architecture - MT5 Elliott Wave Trading System

**Last Updated**: 2026-01-06
**Architecture Version**: 1.2
**Current Phase**: Phase 9 (RiskGuard Key Level Proximity Validation)

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Component Interaction](#component-interaction)
3. [Data Flow Diagrams](#data-flow-diagrams)
4. [Technology Stack](#technology-stack)
5. [Design Patterns](#design-patterns)
6. [Module Dependencies](#module-dependencies)
7. [State Machines](#state-machines)
8. [Database Schema](#database-schema)
9. [Security Architecture](#security-architecture)
10. [Scalability & Performance](#scalability--performance)
11. [Deployment Architecture](#deployment-architecture)

---

## High-Level Architecture

```
┌────────────────────────────────────────────┐   ┌──────────────────────────┐
│  TELEGRAM USER INTERFACE (telegram_bot.py) │   │  WEB DASHBOARD (Phase 8) │
│  /signal, /positions, /trades, /balance    │   │  http://localhost:3000   │
│                                            │   │  - Stats & Charts        │
│                                            │   │  - Trade History         │
│                                            │   │  - Equity Curve          │
│                                            │   │  - Performance Analysis  │
└────────────────────┬───────────────────────┘   └──────────┬───────────────┘
                     │                                       │
                     └────────────┬────────────────────────────┘
                                  │
                    ┌─────────────▼──────────────────┐
                    │  DASHBOARD API (FastAPI :8000) │
                    │  - 11 REST endpoints           │
                    │  - Rate limiting               │
                    │  - CORS middleware             │
                    └─────────────┬──────────────────┘
                                  │
        ┌─────────────────────────┴──────────────────────┐
        │  SIGNAL PROCESSING LAYER                       │
        │  (signal_parser.py, claude_client.py)          │
        │  ✓ Parse trading signals                       │
        │  ✓ Extract from Claude AI                      │
        │  ✓ Validate & convert                          │
        └─────────────────────────┬──────────────────────┘
                                  │
        ┌─────────────────────────▼──────────────────────┐
        │   RISK VALIDATION LAYER (NEW - Phase 9)        │
        │   (risk_guard.py)                              │
        │   ✓ Duplicate detection                        │
        │   ✓ Direction conflict handling                │
        │   ✓ Key level proximity validation             │
        │   ✓ Exposure limits checking                   │
        │   ✓ Account risk management                    │
        └─────────────────────────┬──────────────────────┘
                                  │
        ┌─────────────────────────▼──────────────────────┐
        │   EXECUTION & MANAGEMENT LAYER                 │
        │   (trade_executor.py, trailing_stop_manager.py)│
        │   ✓ Position sizing                            │
        │   ✓ Order placement                            │
        │   ✓ Trailing stop logic                        │
        │   ✓ Partial closes                             │
        └─────────────────────────┬──────────────────────┘
                                  │
        ┌─────────────────────────▼──────────────────────┐
        │  MARKET DATA & BROKER LAYER (mt5_client.py)    │
        │  ✓ Connect to MT5                              │
        │  ✓ Fetch OHLCV data                            │
        │  ✓ Calculate indicators                        │
        │  ✓ Execute orders                              │
        │  ✓ Manage positions                            │
        └─────────────────────────┬──────────────────────┘
                                  │
        ┌─────────────────────────▼──────────────────────┐
        │    PERSISTENT DATA LAYER (database.py)         │
        │    SQLite: trades, signals, TP, equity, PnL    │
        │    Read-write: Trading bot                     │
        │    Read-only: Dashboard API                    │
        └────────────────────────────────────────────────┘

        ┌──────────────────────────────────────────────┐
        │   CONFIGURATION LAYER (config.py)            │
        │   Settings from .env file                    │
        └──────────────────────────────────────────────┘
```

---

## Component Interaction

### Component Dependency Graph

```
telegram_bot.py
    ↓
signal_parser.py ←─── claude_client.py
    ↓
risk_guard.py ◄────── Pre-execution validation (NEW - Phase 9)
    ├─→ mt5_client.py
    ├─→ database.py
    └─→ config.py
    ↓
trade_executor.py
    ├─→ mt5_client.py ─┐
    ├─→ database.py    │
    └─→ config.py      │
                        │
trailing_stop_manager.py
    ├─→ mt5_client.py ─┴─→ MetaTrader 5 API
    ├─→ database.py
    └─→ config.py

All modules depend on config.py (Dependency Inversion Pattern)
RiskGuard validates all signals before execution
```

### Message Flow Sequence

#### Trade Signal Execution Sequence

```
User sends /signal command
        ↓
telegram_bot.py receives message
        ↓
signal_parser.py extracts and validates signal
        ↓
trade_executor.py processes signal
        ├─→ trade_executor.execute_signal()
        ├─→ Calculate position size with confidence
        ├─→ mt5_client.py places order
        ├─→ database.py saves trade with ticket
        └─→ trailing_stop_manager monitors position
        ↓
telegram_bot.py sends confirmation
        ↓
Scheduler checks trailing stop every interval
        ├─→ trailing_stop_manager.check_all_positions()
        ├─→ mt5_client.py gets current positions
        ├─→ Update SL if criteria met
        ├─→ database.py updates state
        └─→ telegram_bot.py sends notifications
```

---

## Data Flow Diagrams

### 1. Order Placement Flow

```
Signal Input (Telegram)
    │
    ├─→ Signal Parser (extract JSON, validate Pydantic)
    │       │ ✓ Action (BUY/SELL)
    │       │ ✓ Entry, SL, TP levels
    │       │ ✓ Confidence (0-100)
    │       └─→ TradingSignal object
    │
    ├─→ Trade Executor
    │       │ ✓ Check minimum confidence
    │       │ ✓ Calculate position size
    │       │   - Account balance × risk %
    │       │   - Divide by stop distance
    │       │   - Apply confidence multiplier
    │       └─→ Lot size
    │
    ├─→ MT5 Client
    │       │ ✓ Get current price (ask/bid)
    │       │ ✓ Build order request
    │       │ ✓ Place market order
    │       │ ✓ Retry on requote (3 attempts)
    │       └─→ Order ticket (or -1 in paper mode)
    │
    ├─→ Database
    │       │ ✓ Save signal (status: pending)
    │       │ ✓ Save trade with ticket
    │       │ ✓ Save TP levels
    │       │ ✓ Set trailing_state: inactive
    │       └─→ Signal ID, Trade ID
    │
    └─→ Telegram Bot (send confirmation)
        └─→ "Order placed: Ticket #12345"
```

### 2. Trailing Stop Flow

```
Scheduler triggers (every 5-10 seconds)
    │
    ├─→ Trailing Stop Manager
    │       │ ✓ Get all open trades from DB
    │       │ └─→ List of trades with state
    │
    ├─→ For each trade:
    │   ├─→ Get current position from MT5
    │   │       └─→ Current price, profit, SL
    │   │
    │   └─→ Check state machine:
    │
    │   INACTIVE state:
    │   ├─→ Check activation criteria
    │   │   ├─→ TP1 hit? (partial close occurred)
    │   │   └─→ Profit > 1R? (profit > entry - stop)
    │   │
    │   ├─→ If activated:
    │   │   ├─→ Calculate breakeven + buffer
    │   │   │   └─→ New SL = entry + (5 pips × point)
    │   │   ├─→ MT5 modify position with new SL
    │   │   ├─→ Database update state: activated
    │   │   └─→ Telegram notify (breakeven SL set)
    │   │
    │   ACTIVATED state:
    │   ├─→ Monitor for 1.5 × ATR retracement
    │   │   ├─→ Get current ATR from MT5
    │   │   ├─→ Check if price > highest high - (ATR × 1.5)
    │   │   │
    │   │   └─→ If trail condition met:
    │   │       ├─→ Calculate new SL
    │   │       │   └─→ New SL = current high - (ATR × 1.5)
    │   │       ├─→ Only move SL UP, never down
    │   │       ├─→ MT5 modify position
    │   │       ├─→ Database update state: trailing
    │   │       └─→ Telegram notify (trailing activated)
    │   │
    │   TRAILING state:
    │   └─→ Every check:
    │       ├─→ Check if new high reached
    │       ├─→ If yes: update SL = new high - (ATR × 1.5)
    │       │   └─→ MT5 modify, DB update
    │       └─→ Continue monitoring
    │
    └─→ Database persists all state changes
        └─→ For next cycle
```

### 3. Partial Close Flow

```
TP Level Target Reached (during check_all_positions)
    │
    ├─→ Identify which TP level was hit
    │       └─→ TP1: 25% close, TP2: 35% close, etc.
    │
    ├─→ Calculate close volume
    │       └─→ Total volume × close percentage
    │
    ├─→ MT5 Client partial close
    │       ├─→ Create close order
    │       ├─→ Execute partial volume
    │       └─→ Order confirmation (ticket)
    │
    ├─→ Database
    │       ├─→ Update tp_levels (triggered = 1)
    │       ├─→ Update trade (new remaining volume)
    │       └─→ Update closing price if last TP
    │
    └─→ Telegram notification
        └─→ "TP1 hit at 2010.00, closed 25%"
```

---

## Technology Stack

### Backend Framework
- **Python 3.10+** - Core language
- **Pydantic 2.0+** - Data validation
- **SQLite3** - Persistent storage
- **python-dotenv** - Configuration management

### Trading & Market Data
- **MetaTrader 5 (MT5)** - Broker platform
- **MetaTrader5 Python library** - MT5 API integration
- **pandas/numpy** - Technical analysis

### AI Integration
- **Claude CLI** - AI signal generation via subprocess
- **JSON extraction** - Parse Claude responses with fallbacks

### User Interface
- **Telegram Bot API** - Messaging interface
- **aiogram 3.x** - Telegram bot framework
- **APScheduler** - Background scheduling (Phase 6)

### Testing
- **pytest** - Unit testing framework
- **pytest-cov** - Coverage reporting
- **unittest.mock** - Mocking dependencies

### Development
- **git** - Version control
- **black** - Code formatting
- **mypy** - Static type checking

---

## Design Patterns

### 1. Singleton Pattern (Configuration)

```python
# config.py
class Settings(BaseSettings):
    # Configuration loaded once from .env
    risk_percent: float = 1.0
    paper_trading: bool = True
    # ...

config = Settings()  # Singleton instance
```

**Benefits**:
- Single source of configuration truth
- Lazy loading of environment variables
- Type-safe settings with Pydantic

---

### 2. Lazy Loading Pattern (Dependencies)

```python
# trade_executor.py
class TradeExecutor:
    _mt5 = None
    _db = None

    @property
    def mt5(self) -> MT5Client:
        if self._mt5 is None:
            self._mt5 = MT5Client()
        return self._mt5

    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = Database()
        return self._db
```

**Benefits**:
- Delays expensive initialization until needed
- Avoids circular dependencies
- Clean DI without framework overhead
- Testable with mock injection

---

### 3. State Machine Pattern (Trailing Stop)

```python
# trailing_stop_manager.py
class TrailingState(Enum):
    INACTIVE = "inactive"      # Initial state
    ACTIVATED = "activated"    # TP1 hit or 1R profit
    TRAILING = "trailing"      # Actively trailing

# Transitions with validation
def check_position(trade):
    if trade['state'] == TrailingState.INACTIVE:
        if meets_activation_criteria(trade):
            activate_trailing_stop(trade)

    elif trade['state'] == TrailingState.ACTIVATED:
        if meets_trail_criteria(trade):
            start_trailing(trade)
```

**Benefits**:
- Clear state transitions
- Prevents invalid state changes
- Self-documenting code
- Easy to test state paths

---

### 4. Context Manager Pattern (Database)

```python
# database.py
def get_open_trades(self):
    with sqlite3.connect(self.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM trades WHERE status = 'open'").fetchall()
        return [dict(row) for row in rows]
    # Connection auto-closes
```

**Benefits**:
- Automatic resource cleanup
- No connection leaks
- Exception-safe

---

### 5. Strategy Pattern (Signal Execution)

```python
# signal_parser.py - Multiple extraction strategies
def extract_json_from_response(response):
    # Strategy 1: Look for code block
    json_block = find_json_block(response)
    if json_block:
        return parse_json(json_block)

    # Strategy 2: Find raw JSON
    raw_json = find_json_object(response)
    if raw_json:
        return parse_json(raw_json)

    # Strategy 3: Recursively ask Claude
    return ask_claude_for_json(response)
```

**Benefits**:
- Multiple fallback approaches
- Resilient to Claude response variations
- Easy to add new strategies

---

### 6. Repository Pattern (Database Access)

```python
# database.py acts as repository
class Database:
    def save_signal(self, signal):
        # Database is only way to persist signals

    def get_open_trades(self):
        # Database is only way to query trades

# Trade executor only knows about Database interface
executor = TradeExecutor()
trades = executor.db.get_open_trades()
```

**Benefits**:
- Single database access layer
- Testable with mock DB
- Loose coupling to storage backend

---

## Module Dependencies

### Dependency Hierarchy

```
Level 3 (User Interface)
    └─ telegram_bot.py

Level 2 (Business Logic)
    ├─ trade_executor.py
    ├─ trailing_stop_manager.py
    ├─ signal_parser.py
    └─ claude_client.py

Level 1 (Data & Broker)
    ├─ mt5_client.py
    └─ database.py

Level 0 (Infrastructure)
    └─ config.py
```

### Inversion of Control

All modules depend on config for settings:

```python
# Every module imports config
from src.config import config

# Avoids tight coupling
class MT5Client:
    def __init__(self):
        self.symbol = config.trading_symbol
        self.risk_percent = config.risk_percent
```

**Benefits**:
- Configuration changes don't require code changes
- Testable with different config values
- Environment-specific settings via .env

---

## State Machines

### 1. Trailing Stop State Machine

```
┌─────────────────────────────────────────────────────────────┐
│                   POSITION LIFECYCLE                         │
└─────────────────────────────────────────────────────────────┘

    INACTIVE
    ├─ Entry: Order placed with TP1 at X, TP2 at Y, TP3 at Z
    ├─ Monitor: Two activation criteria
    │   ├─ Criterion A: TP1 target hit → partial close
    │   └─ Criterion B: Unrealized profit > 1R
    │
    ├─ Activation trigger:
    │   ├─ If TP1 hit OR profit > 1R:
    │   │   ├─ Move SL to breakeven + 5 pips
    │   │   ├─ Update DB: state = "activated"
    │   │   └─ Send Telegram notification
    │   └─ Transition to ACTIVATED
    │
    ▼
    ACTIVATED
    ├─ SL is at breakeven + buffer
    ├─ Monitor: ATR-based retracement
    │   ├─ Calculate 1.5 × ATR (trail distance)
    │   └─ Check: current_high > (peak_high - 1.5×ATR)
    │
    ├─ Trail trigger:
    │   ├─ If price retraces 1.5×ATR:
    │   │   ├─ Calculate new SL = peak_high - (1.5×ATR)
    │   │   ├─ Only move SL UP (never down)
    │   │   ├─ MT5 modify position
    │   │   ├─ Update DB: state = "trailing"
    │   │   └─ Send notification
    │   └─ Transition to TRAILING
    │
    ▼
    TRAILING
    ├─ SL follows price (peaks follow)
    ├─ Monitor: Every check cycle
    │   ├─ Track current high
    │   ├─ Check: new_high > old_high
    │   └─ If yes: SL = new_high - (1.5×ATR)
    │
    └─ Continue until:
        ├─ SL hit → Position closed (profit locked)
        ├─ TP3 hit → Position closed (max profit)
        └─ Manual intervention → State updated
```

### 2. Signal Status Flow

```
PENDING
    ├─ Signal received and validated
    ├─ Confidence >= 50% threshold
    └─ Awaiting execution

    ├─ Path A: Confidence >= 50%
    │   └─ Transition to EXECUTED
    │
    └─ Path B: Confidence < 50% OR error
        └─ Transition to SKIPPED or EXPIRED
```

---

## Database Schema

### Tables and Relationships

```sql
-- Trading signals received
CREATE TABLE signals (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,                 -- When signal received
    symbol TEXT,                    -- Trading symbol
    action TEXT,                    -- "BUY" or "SELL"
    entry_price REAL,
    stop_loss REAL,
    take_profit_1 REAL,
    take_profit_2 REAL,
    take_profit_3 REAL,
    confidence INTEGER,             -- 0-100
    status TEXT                     -- pending|executed|skipped|expired
);

-- Executed trades
CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    signal_id INTEGER,              -- FK to signals
    ticket INTEGER UNIQUE,          -- MT5 ticket number
    symbol TEXT,
    action TEXT,                    -- "BUY" or "SELL"
    volume REAL,                    -- Lot size executed
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,               -- Primary TP level
    open_time TEXT,
    close_time TEXT,
    close_price REAL,
    profit REAL,                    -- P&L in USD
    status TEXT,                    -- open|closed|stopped_out
    trailing_state TEXT             -- inactive|activated|trailing
);

-- Take profit levels and tracking
CREATE TABLE tp_levels (
    id INTEGER PRIMARY KEY,
    trade_id INTEGER,               -- FK to trades
    level TEXT,                     -- "TP1", "TP2", "TP3"
    price REAL,
    close_percent INTEGER,          -- % of volume to close
    triggered INTEGER DEFAULT 0     -- 1 if TP hit and closed
);

-- Signal hashes for duplicate detection
CREATE TABLE signal_hashes (
    id INTEGER PRIMARY KEY,
    hash TEXT NOT NULL,             -- MD5 hash of signal content
    symbol TEXT NOT NULL,           -- Trading symbol
    action TEXT NOT NULL,           -- "BUY" or "SELL"
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_trades_ticket ON trades(ticket);
CREATE INDEX idx_signals_status ON signals(status);
CREATE INDEX idx_signal_hash ON signal_hashes(hash);
CREATE INDEX idx_signal_hash_created ON signal_hashes(created_at);
```

### Data Flow in Database

```
Telegram /signal
    │
    ├─→ signals table (INSERT)
    │   └─→ status = "pending"
    │
    ├─→ Signal validated
    │   └─→ signals table (UPDATE status = "executed")
    │
    ├─→ trades table (INSERT)
    │   ├─→ signal_id (foreign key)
    │   ├─→ ticket = -1 (paper mode) or actual ticket
    │   ├─→ status = "open"
    │   └─→ trailing_state = "inactive"
    │
    ├─→ tp_levels table (INSERT for each TP)
    │   ├─→ trade_id (foreign key)
    │   ├─→ level ("TP1", "TP2", "TP3")
    │   ├─→ price
    │   └─→ close_percent (25, 35, 40)
    │
    └─→ Monitor cycle:
        ├─→ trades table (SELECT open trades)
        ├─→ On state change: trades (UPDATE trailing_state)
        └─→ On close: trades (UPDATE status, close_price, close_time)
```

---

## Security Architecture

### 1. Paper Trading Enforcement

**Layer 1: Configuration Default**
```python
# config.py
paper_trading: bool = True  # Default safe
```

**Layer 2: Execution Boundary Check**
```python
# mt5_client.py - Every order operation
def place_market_order(...):
    if config.paper_trading:
        logger.info(f"PAPER: {order_type} {volume}")
        return -1  # Fake ticket, no actual order
    # Real execution below
```

**Layer 3: Database Recording**
```python
# database.py
# All trades recorded regardless of mode
# Paper trades have ticket = -1
```

---

### 2. Input Validation

**Pydantic Models** validate all inputs:

```python
# signal_parser.py
class TradingSignal(BaseModel):
    timestamp: datetime            # Type checked
    symbol: str                    # Required
    signal: TradeInstruction       # Nested validation

class TradeInstruction(BaseModel):
    action: Literal["BUY", "SELL"] # Only these values
    entry_price: float = Field(gt=0)  # Must be positive
    confidence: int = Field(ge=0, le=100)  # 0-100 range
```

---

### 3. Database Security

**Parameterized Queries** (no SQL injection):

```python
# database.py
# SAFE: Parameters separated from query
conn.execute(
    "INSERT INTO trades (symbol, action) VALUES (?, ?)",
    (symbol, action)  # Parameters
)

# UNSAFE (never used):
# conn.execute(f"INSERT INTO trades VALUES ('{symbol}', '{action}')")
```

---

### 4. Telegram Authorization

```python
# telegram_bot.py
async def process_message(self, message):
    if message.chat.id != config.allowed_chat_id:
        logger.warning(f"Unauthorized access: {message.chat.id}")
        return
    # Process only authorized user
```

---

### 5. Magic Number Isolation

```python
# mt5_client.py
# Only trades with matching magic number are tracked
positions = mt5.positions_get()
our_positions = [p for p in positions if p.magic == 123456]
```

---

## Scalability & Performance

### Current Capacity (Phase 5)

| Metric | Capacity | Notes |
|--------|----------|-------|
| Open positions | 5-20 | Sequential checking |
| Database queries/sec | 100+ | SQLite single writer |
| Telegram messages/sec | 30 | API rate limit |
| MT5 API calls/sec | 5-10 | Broker dependent |

### Bottlenecks

1. **MT5 API Latency** (10-50ms per call)
   - Solution: Cache recent data
   - Impact: Acceptable for current scale

2. **SQLite Single-Writer**
   - Current: Acceptable for single-process
   - Phase 6: Consider WAL mode for concurrency

3. **Trailing Stop Latency**
   - Current: Check interval 5-10 seconds
   - Impact: May miss micro-movements
   - Solution: Increase frequency if needed

### Performance Optimization Opportunities

1. **Connection Pooling**
   ```python
   # Current: New connection per query
   # Better: Reuse connections
   conn_pool = ConnectionPool(max_size=5)
   ```

2. **Caching**
   ```python
   # Cache ATR for 1-2 seconds
   # Cache account info between position sizing calls
   ```

3. **Batch Updates**
   ```python
   # Instead of: update each position individually
   # Better: batch update multiple positions
   ```

---

## Deployment Architecture

### Current: Single-Process Local

```
┌─────────────────────────────────┐
│     Single Windows PC            │
│  ┌──────────────────────────┐   │
│  │  Python Process          │   │
│  │  ├─ trade_executor.py    │   │
│  │  ├─ telegram_bot.py      │   │
│  │  ├─ trailing_stop_manager│   │
│  │  └─ mt5_client.py        │   │
│  └──────────────────────────┘   │
│           ▲                       │
│           │                       │
│  ┌────────┴──────────────────┐   │
│  │   MT5 Terminal Installed  │   │
│  │   (terminal64.exe)        │   │
│  └──────────────────────────┘   │
│                                  │
│  ┌──────────────────────────┐   │
│  │  SQLite Database         │   │
│  │  (trades.db)             │   │
│  └──────────────────────────┘   │
└─────────────────────────────────┘
        │
        ├─→ Telegram API (messaging)
        ├─→ Claude API (signals)
        └─→ Broker (FX/Commodities)
```

### Future: Distributed (Phase 9+)

```
┌──────────────────────────────────────────────────┐
│          Load Balancer / Scheduler               │
└──────────────────────────────────────────────────┘
    │
    ├─→ Signal Generator (Claude)
    │   └─ Runs on CPU-optimized VM
    │
    ├─→ Execution Service
    │   └─ Runs on trading VM (MT5)
    │
    ├─→ Monitoring Service
    │   └─ Trailing stop checks
    │
    └─→ API Service
        └─ REST API for dashboard

Database: PostgreSQL (horizontal scaling)
Message Queue: Redis (decoupling)
Monitoring: Prometheus + Grafana
```

---

## Error Handling Strategy

### Error Classification

```
┌─────────────────────────────┐
│ Critical Errors (stop app)  │
│ ├─ MT5 connection loss      │
│ ├─ Database corruption      │
│ └─ Unauthorized access      │
└─────────────────────────────┘

┌─────────────────────────────┐
│ Major Errors (skip signal)  │
│ ├─ Invalid signal format    │
│ ├─ Position sizing error    │
│ └─ Insufficient margin      │
└─────────────────────────────┘

┌─────────────────────────────┐
│ Minor Errors (retry)        │
│ ├─ Requote on order         │
│ ├─ Network timeout          │
│ └─ Telegram send failed     │
└─────────────────────────────┘
```

### Error Recovery

```
Signal Processing Error:
    ├─ Log error
    ├─ Update signal status to "skipped"
    ├─ Send Telegram alert
    └─ Continue with next signal

Order Placement Error:
    ├─ Retry with fresh price (up to 3x)
    ├─ If still fails:
    │   ├─ Log error details
    │   ├─ Send Telegram alert
    │   └─ Mark signal as "failed"
    └─ Manual intervention required

Database Error:
    ├─ Close connection
    ├─ Log error
    ├─ Alert user
    └─ Attempt to reconnect on next cycle
```

---

## Testing Architecture

### Unit Test Pyramid

```
         ▲
        /│\
       / │ \  Integration Tests (3)
      /  │  \
     ┌───┴───┐
     │  ││ │ │ Unit Tests (45)
     │  ││ │ │
     │  ││ │ │
     └───┴───┘
      ├─│─┤
      Config
      MT5
      Signals
      Database
      Executor
      Trailing
      Claude
      Telegram
```

### Test Organization

```
tests/
├─ test_config.py              (Configuration)
├─ test_mt5.py                 (MT5 Client)
├─ test_signal_parser.py       (Signal Processing)
├─ test_claude_client.py       (AI Integration)
├─ test_database.py            (Persistence - 16 tests)
├─ test_trade_executor.py      (Execution - 13 tests)
├─ test_trailing_stop.py       (State Machine - 16 tests)
└─ test_telegram.py            (UI)

Coverage:
├─ database.py        96%
├─ trade_executor.py  87%
└─ trailing_stop.py   84%

Total: 45/45 passing (100%)
```

### Test Strategy

1. **Unit Tests**: Isolated component testing with mocks
2. **State Machine Tests**: Verify all state transitions
3. **Integration Tests**: Component interaction (planned Phase 6)
4. **End-to-End Tests**: Full workflow (with demo account)

---

## Monitoring & Observability

### Logging Levels

```python
# debug: Low-level details (not in production)
logger.debug(f"ATR calculated: {atr}")

# info: Normal operations
logger.info(f"Order placed: ticket {ticket}")

# warning: Unexpected but recoverable
logger.warning(f"Low confidence signal: {confidence}%")

# error: Serious issues requiring attention
logger.error(f"Order failed: {error_code}")

# critical: System-level failures
logger.critical(f"Database connection lost")
```

### Metrics to Track (Phase 7+)

```python
# Trading Metrics
├─ Win rate %
├─ Average profit per trade
├─ Drawdown maximum
├─ Sharpe ratio
└─ Profit factor

# System Metrics
├─ Signal latency (ms)
├─ Order execution time (ms)
├─ Database query time (ms)
└─ Trailing stop update frequency

# Risk Metrics
├─ Maximum position size (lots)
├─ Portfolio heat (total risk %)
├─ Margin utilization %
└─ Stopped out trades count
```

---

## Deployment Checklist

Before production deployment:

```
Configuration
├─ [ ] MT5 path verified
├─ [ ] Trading symbol configured
├─ [ ] Risk parameters reviewed
├─ [ ] Telegram credentials set
└─ [ ] .env file secured

Testing
├─ [ ] All 45 tests passing
├─ [ ] Manual smoke tests completed
├─ [ ] Paper trading validation
└─ [ ] Demo account trial (optional)

Security
├─ [ ] Paper trading mode verified (ON)
├─ [ ] Magic number documented
├─ [ ] Max position size limit set
├─ [ ] Telegram chat ID authorized
└─ [ ] Database backups configured

Monitoring
├─ [ ] Logging configured
├─ [ ] Error alerts set up
├─ [ ] Daily check routine established
└─ [ ] Backup/recovery plan documented
```

---

## Summary

This architecture provides:

✅ **Modularity**: Each component has single responsibility
✅ **Testability**: Dependency injection enables mocking
✅ **Security**: Multi-layer protection (paper mode, validation, authorization)
✅ **Maintainability**: Clear separation of concerns, documented patterns
✅ **Scalability**: Designed for growth (queue-based in Phase 9)
✅ **Reliability**: Error handling, retry logic, state persistence
✅ **Observability**: Comprehensive logging and future monitoring

---

**Architecture Version**: 1.0
**Last Updated**: 2026-01-04
**Next Review**: After Phase 6 completion
