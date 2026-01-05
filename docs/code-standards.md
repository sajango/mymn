# Code Standards & Guidelines

**Last Updated**: 2026-01-05
**Project**: MT5 Elliott Wave Trading System
**Phase**: 9 (RiskGuard Phase 1 Configuration)

## Table of Contents

1. [Coding Standards](#coding-standards)
2. [Project Structure](#project-structure)
3. [Naming Conventions](#naming-conventions)
4. [Code Organization](#code-organization)
5. [Type Hints & Documentation](#type-hints--documentation)
6. [Error Handling](#error-handling)
7. [Testing Standards](#testing-standards)
8. [Performance Guidelines](#performance-guidelines)
9. [Security Guidelines](#security-guidelines)
10. [Configuration Management](#configuration-management)
11. [Code Review Checklist](#code-review-checklist)

---

## Coding Standards

### Language & Framework
- **Python Version**: 3.10+ (required for type hints)
- **Type Checking**: mypy (static type checking)
- **Formatting**: black (auto-formatter, 88 char line length)
- **Linting**: pylint/flake8 (code quality)
- **Imports**: isort (consistent import ordering)

### Code Quality Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Test Coverage | >80% | 66% overall, 84-100% core ✅ |
| Test Cases | >100 | 281 ✅ |
| Type Hints | 100% | 100% ✅ |
| Docstrings | All public | 50+ ✅ |
| Line Length | <100 chars | 88 chars ✅ |
| Cyclomatic Complexity | <10 | <8 ✅ |
| Test Pass Rate | 100% | 281/281 (100%) ✅ |

### Style Guide

#### Imports
```python
# Order: stdlib, third-party, local
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import pandas as pd
from pydantic import BaseModel, Field

from src.config import config
from src.mt5_client import MT5Client
```

#### Class Definition
```python
class TradeExecutor:
    """Orchestrates signal execution and position management.

    This class handles:
    - Signal validation and filtering
    - Position size calculation
    - Order placement with MT5
    - Trade tracking in database

    Attributes:
        _mt5 (MT5Client): Lazy-loaded MT5 client
        _db (Database): Lazy-loaded database

    Example:
        >>> executor = TradeExecutor()
        >>> signal = TradingSignal(...)
        >>> executor.execute_signal(signal)
    """

    _mt5 = None
    _db = None

    @property
    def mt5(self) -> MT5Client:
        """Lazy-load MT5 client."""
        if self._mt5 is None:
            self._mt5 = MT5Client()
        return self._mt5
```

#### Function Definition
```python
def calculate_position_size(
    self,
    symbol: str,
    entry_price: float,
    stop_loss: float,
    risk_percent: float = None,
) -> float:
    """Calculate position size based on risk percentage.

    Calculates the number of lots to trade based on:
    - Account balance
    - Risk percentage (default: config.risk_percent)
    - Stop loss distance
    - Symbol contract size
    - Confidence level multiplier

    Args:
        symbol (str): Trading symbol (e.g., "XAUUSD")
        entry_price (float): Planned entry price
        stop_loss (float): Stop loss price
        risk_percent (float, optional): Risk % (default: config)

    Returns:
        float: Lot size (e.g., 0.05)

    Notes:
        - Applies confidence multiplier (75%+ = 1.0x, 60-74% = 0.5x)
        - Respects max_position_size limit
        - Rounds to symbol volume_step

    Raises:
        ValueError: If stop_loss equals entry_price

    Example:
        >>> size = executor.calculate_position_size(
        ...     symbol="XAUUSD",
        ...     entry_price=2000.00,
        ...     stop_loss=1990.00,
        ...     risk_percent=1.0
        ... )
        >>> print(f"Position size: {size} lots")
        Position size: 0.05 lots
    """
```

---

## Project Structure

### Directory Organization

```
mt5-trading-system/
├── src/                     # Implementation modules
│   ├── __init__.py
│   ├── config.py           # Configuration (Settings)
│   ├── mt5_client.py       # MT5 integration
│   ├── signal_parser.py    # Signal models & parsing
│   ├── claude_client.py    # Claude AI wrapper
│   ├── database.py         # SQLite persistence
│   ├── trade_executor.py   # Order execution
│   └── trailing_stop_manager.py  # Stop loss management
│
├── tests/                   # Test suite
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_mt5.py
│   ├── test_signal_parser.py
│   ├── test_claude_client.py
│   ├── test_database.py
│   ├── test_trade_executor.py
│   ├── test_trailing_stop.py
│   └── test_telegram.py
│
├── docs/                    # Documentation
│   ├── codebase-summary.md
│   ├── api-documentation.md
│   ├── system-architecture.md
│   ├── project-overview-pdr.md
│   └── code-standards.md
│
├── plans/                   # Development plans
│   └── 260104-1514-mt5-elliott-wave-trading/
│       ├── phase-01-project-setup.md
│       ├── phase-02-mt5-data-export.md
│       ├── ... (phases 3-9)
│       └── reports/
│           ├── code-reviewer-*.md
│           └── docs-manager-*.md
│
├── data/                    # Trade data outputs
│   ├── ohlcv_export_*.csv
│   └── trades.db
│
├── logs/                    # Application logs
│   └── trading_*.log
│
├── .env                     # Environment variables (gitignored)
├── .env.example             # Template for .env
├── .gitignore              # Git ignore patterns
├── requirements.txt        # Python dependencies
└── README.md               # Project overview
```

### Module Naming

| Type | Pattern | Example |
|------|---------|---------|
| Module | `snake_case` | `mt5_client.py` |
| Class | `PascalCase` | `MT5Client` |
| Function | `snake_case` | `calculate_position_size()` |
| Constant | `UPPER_CASE` | `MAGIC_NUMBER = 123456` |
| Private | `_leading_underscore` | `_get_connection()` |
| Parameter | `snake_case` | `entry_price: float` |

---

## Naming Conventions

### Variables & Functions

```python
# Good: descriptive names
account_balance = 10000.00
position_size = 0.05
def calculate_position_size(...): pass

# Bad: ambiguous abbreviations
acct_bal = 10000.00
pos_sz = 0.05
def calc_pos(...): pass
```

### Classes

```python
# Good: PascalCase, descriptive
class MT5Client:
    pass

class TradeExecutor:
    pass

class TrailingStopManager:
    pass

# Bad: Not descriptive enough
class Client:
    pass

class Executor:
    pass
```

### Constants

```python
# Good: UPPER_CASE with underscore
MAGIC_NUMBER = 123456
PAPER_TRADING_TICKET = -1
MAX_RETRIES = 3

# Bad: lowercase or mixed case
magic_number = 123456
Magic_Number = 123456
```

### Boolean Variables

```python
# Good: is_*, has_*, should_*
is_connected: bool = True
has_sufficient_margin: bool = False
should_activate_trailing: bool = True

# Bad: unclear intent
connected: bool = True
margin: bool = False
trailing: bool = True
```

---

## Code Organization

### Module Layout

Every module should follow this order:

```python
"""Module docstring explaining purpose."""

# 1. Imports (stdlib, third-party, local)
import logging
from typing import Optional

import pandas as pd
from pydantic import BaseModel

from src.config import config

logger = logging.getLogger(__name__)

# 2. Constants
MAGIC_NUMBER = 123456
DEFAULT_TIMEFRAME = "H1"

# 3. Enums (if any)
from enum import Enum

class TradeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"

# 4. Type aliases
TradeDict = dict[str, float]

# 5. Classes
class MT5Client:
    """Main MT5 integration class."""
    pass

# 6. Functions
def connect_mt5() -> bool:
    """Connect to MT5 terminal."""
    pass

# 7. Main (if executable)
if __name__ == "__main__":
    pass
```

### Class Organization

```python
class TradeExecutor:
    """Main executor class."""

    # 1. Class variables
    _instance = None

    # 2. __init__
    def __init__(self):
        self._mt5 = None
        self._db = None

    # 3. Properties (lazy loading)
    @property
    def mt5(self) -> MT5Client:
        if self._mt5 is None:
            self._mt5 = MT5Client()
        return self._mt5

    # 4. Public methods
    def execute_signal(self, signal: TradingSignal) -> bool:
        """Execute trading signal."""
        pass

    # 5. Private methods
    def _validate_signal(self, signal: TradingSignal) -> bool:
        """Validate signal before execution."""
        pass

    # 6. Special methods (__str__, __repr__, etc.)
    def __repr__(self) -> str:
        return f"<TradeExecutor>"
```

---

## Type Hints & Documentation

### Type Hints (Required for all public methods)

```python
# Good: Full type hints
def place_order(
    self,
    symbol: str,
    order_type: str,
    volume: float,
    stop_loss: float,
) -> Optional[int]:
    """Place market order."""
    pass

# Bad: Missing type hints
def place_order(self, symbol, order_type, volume, stop_loss):
    """Place market order."""
    pass
```

### Union Types

```python
from typing import Union, Optional

# Use Optional for nullable
config_value: Optional[str] = None

# Use Union for multiple types
def process_data(data: Union[str, int, float]) -> bool:
    """Process various data types."""
    pass

# Alternative (Python 3.10+)
def process_data(data: str | int | float) -> bool:
    """Process various data types."""
    pass
```

### Collection Types

```python
from typing import List, Dict, Tuple, Set

# Good: Specify element types
positions: List[Dict[str, float]] = []
trades: Dict[int, dict] = {}
tp_levels: List[Tuple[str, float]] = [("TP1", 2010.0)]

# Acceptable (Python 3.9+)
positions: list[dict[str, float]] = []
```

### Docstring Format

```python
def calculate_position_size(
    self,
    symbol: str,
    entry_price: float,
    stop_loss: float,
) -> float:
    """Calculate position size based on risk percentage.

    Detailed explanation of what this function does,
    including the algorithm and any important side effects.

    Args:
        symbol (str): Trading symbol (e.g., "XAUUSD")
        entry_price (float): Planned entry price
        stop_loss (float): Stop loss price

    Returns:
        float: Lot size to trade (e.g., 0.05)

    Raises:
        ValueError: If stop_loss >= entry_price

    Example:
        >>> size = client.calculate_position_size(
        ...     "XAUUSD", 2000.00, 1990.00
        ... )
        >>> print(size)
        0.05
    """
```

### Class Docstrings

```python
class MT5Client:
    """MetaTrader 5 integration client.

    Handles all communication with MT5 terminal including:
    - Connection management
    - OHLCV data fetching
    - Order placement and management
    - Position monitoring

    Attributes:
        initialized (bool): Connection status
        symbol (str): Default trading symbol

    Example:
        >>> mt5 = MT5Client()
        >>> mt5.initialize()
        >>> df = mt5.fetch_ohlcv("XAUUSD", "H1", 100)
    """
```

---

## Error Handling

### Exception Hierarchy

```python
# Standard exceptions (when appropriate)
raise ValueError("Invalid entry price")
raise TypeError("Expected float, got str")
raise RuntimeError("MT5 connection failed")

# Custom exceptions (for domain-specific errors)
class MT5ConnectionError(Exception):
    """Raised when MT5 connection fails."""
    pass

class PositionSizingError(Exception):
    """Raised when position sizing calculation fails."""
    pass
```

### Error Handling Patterns

#### Pattern 1: Try-Except with Recovery
```python
def place_market_order(...) -> Optional[int]:
    """Place order with retries."""
    for attempt in range(3):
        try:
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"Order placed: {result.order}")
                return result.order
            elif result.retcode == mt5.TRADE_RETCODE_REQUOTE:
                logger.warning("Requote, refreshing price...")
                tick = mt5.symbol_info_tick(symbol)
                request["price"] = tick.ask
                continue
            else:
                logger.error(f"Order failed: {result.comment}")
                return None
        except Exception as e:
            logger.error(f"Exception on attempt {attempt}: {e}")
    return None
```

#### Pattern 2: Context Manager for Resources
```python
def get_open_trades(self) -> List[dict]:
    """Get all open trades."""
    try:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'open'"
            ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return []
```

#### Pattern 3: Validation Before Operation
```python
def execute_signal(self, signal: TradingSignal) -> bool:
    """Execute signal after validation."""
    # Validate signal
    if not signal or signal.signal.confidence < config.min_confidence:
        logger.warning(f"Signal rejected: low confidence")
        return False

    # Validate state
    if not self.mt5.is_connected():
        logger.error("MT5 not connected")
        return False

    # Execute
    try:
        return self._execute_order(signal)
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        return False
```

---

## Testing Standards

### Test File Organization

```python
"""Tests for trade_executor.py module."""

import pytest
from unittest.mock import Mock, patch

from src.trade_executor import TradeExecutor
from src.signal_parser import TradingSignal

# 1. Fixtures
@pytest.fixture
def executor():
    """Create TradeExecutor with mocked dependencies."""
    with patch('src.trade_executor.MT5Client'), \
         patch('src.trade_executor.Database'):
        return TradeExecutor()

@pytest.fixture
def sample_signal():
    """Create sample trading signal."""
    return TradingSignal(
        timestamp=...,
        symbol="XAUUSD",
        signal=...,
        ...
    )

# 2. Test classes
class TestExecuteSignal:
    """Tests for execute_signal method."""

    def test_execute_signal_success(self, executor, sample_signal):
        """Test successful signal execution."""
        executor.mt5.place_market_order = Mock(return_value=12345)
        result = executor.execute_signal(sample_signal)
        assert result is True

    def test_execute_signal_low_confidence(self, executor, sample_signal):
        """Test rejection of low-confidence signals."""
        sample_signal.signal.confidence = 30
        result = executor.execute_signal(sample_signal)
        assert result is False

# 3. Test functions
def test_position_sizing_full_confidence(executor, sample_signal):
    """Test position sizing with full confidence."""
    size = executor.calculate_position_size(
        symbol="XAUUSD",
        entry_price=2000.00,
        stop_loss=1990.00,
        confidence=85
    )
    assert size > 0
```

### Test Naming Conventions

```python
# Good: Clear intent
def test_position_sizing_with_full_confidence():
    pass

def test_trailing_stop_activation_on_tp_hit():
    pass

def test_order_rejected_with_low_confidence():
    pass

# Bad: Vague names
def test_sizing():
    pass

def test_trailing():
    pass

def test_order():
    pass
```

### Test Infrastructure (Phase 7)

**Configuration File**: `pytest.ini`
```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

**Centralized Fixtures** (`tests/conftest.py`):
- `temp_db`: Temporary SQLite database per test
- `mock_mt5`: Mocked MT5 client with configurable responses
- `mock_settings`: Test settings with defaults
- Environment variable setup for Telegram credentials

**Test Categories**:
- Unit tests: Individual module functionality
- Integration tests: Signal → execution flow
- Database tests: CRUD operations and transactions
- State machine tests: Trailing stop state transitions

### Test Coverage Goals

```
Phase 5-6: >85% core modules required
Phase 7+: 66% overall, 84-100% critical modules
Phase 8+: >80% overall coverage

Critical paths: 100% coverage (trade execution, trailing stops, signal parsing)
Core modules target: 91-100% (config, database, signal_parser, etc.)
```

**Current Metrics (Phase 7)**:
- Total tests: 281 (100% passing)
- Overall coverage: 66%
- Core module coverage: 84-100%
- Execution time: 9.21 seconds
- Critical modules 100% covered: config, scheduler, session_detector

---

## Performance Guidelines

### Optimization Priority

1. **Correctness**: Ensure algorithm works
2. **Simplicity**: Use straightforward implementation
3. **Testing**: Validate with tests
4. **Optimization**: Only if profiler shows bottleneck

### Performance Patterns

#### 1. Lazy Loading
```python
@property
def mt5(self) -> MT5Client:
    """Lazy-load expensive resource."""
    if self._mt5 is None:
        self._mt5 = MT5Client()
    return self._mt5
```

#### 2. Caching
```python
# Cache account info for 1-2 seconds
_account_cache = None
_cache_timestamp = 0

def get_account_info(self):
    """Get account with caching."""
    now = time.time()
    if self._account_cache and (now - self._cache_timestamp) < 2:
        return self._account_cache

    self._account_cache = mt5.account_info()
    self._cache_timestamp = now
    return self._account_cache
```

#### 3. Batch Operations
```python
# Bad: Multiple queries
for ticket in tickets:
    trade = db.get_trade_by_ticket(ticket)
    # Process

# Good: Single batch query
trades = db.get_open_trades()
for trade in trades:
    # Process
```

---

## Security Guidelines

### Input Validation

```python
from pydantic import BaseModel, Field

class TradingSignal(BaseModel):
    """Validated trading signal."""

    action: str = Field(pattern="^(BUY|SELL)$")
    entry_price: float = Field(gt=0)
    confidence: int = Field(ge=0, le=100)

    # Automatic validation
    # TradingSignal(action="BUY", entry_price=-100)  # Raises ValidationError
```

### SQL Injection Prevention

```python
# Good: Parameterized queries
conn.execute(
    "INSERT INTO trades (symbol, action) VALUES (?, ?)",
    (symbol, action)  # Parameters kept separate
)

# Bad: String interpolation (NEVER USE)
conn.execute(f"INSERT INTO trades VALUES ('{symbol}', '{action}')")
```

### Sensitive Data

```python
# Good: Use environment variables
api_key = config.claude_api_key  # From .env

# Bad: Hardcoded in source
api_key = "sk-..."
```

### Authorization

```python
# Good: Explicit authorization check
if message.chat_id not in config.authorized_chat_ids:
    logger.warning(f"Unauthorized: {message.chat_id}")
    return

# Bad: Missing authorization
# (Execute blindly)
```

---

## Code Review Checklist

### Before Submitting PR

- [ ] All tests passing (pytest)
- [ ] Type hints complete (mypy clean)
- [ ] Code formatted (black applied)
- [ ] Docstrings for public methods
- [ ] No hardcoded values (use config)
- [ ] Error handling for edge cases
- [ ] Logging for debugging
- [ ] No print statements (use logging)
- [ ] Secrets not committed (.env)

### Reviewer Checklist

#### Correctness
- [ ] Logic implements requirement correctly
- [ ] Edge cases handled
- [ ] Error cases covered
- [ ] No infinite loops
- [ ] No off-by-one errors

#### Security
- [ ] Input validation present
- [ ] No SQL injection
- [ ] No hardcoded secrets
- [ ] Authorization checks in place
- [ ] Paper trading enforced

#### Performance
- [ ] O(n) complexity reasonable
- [ ] No unnecessary loops
- [ ] Caching where appropriate
- [ ] Database queries optimized
- [ ] No resource leaks

#### Maintainability
- [ ] Clear variable names
- [ ] Functions <30 lines
- [ ] Comments explain why, not what
- [ ] DRY principle applied
- [ ] No dead code

#### Testing
- [ ] >80% coverage
- [ ] Edge cases tested
- [ ] Error paths tested
- [ ] Mocks properly configured
- [ ] No flaky tests

---

## Examples

### Good Code Example

```python
def calculate_position_size(
    self,
    symbol: str,
    entry_price: float,
    stop_loss: float,
    risk_percent: Optional[float] = None,
) -> float:
    """Calculate position size based on risk percentage.

    Uses the formula:
        Position Size = Risk Amount / Stop Distance

    Args:
        symbol (str): Trading symbol
        entry_price (float): Entry price (must be > 0)
        stop_loss (float): Stop loss price
        risk_percent (float, optional): Risk % of balance

    Returns:
        float: Lot size to trade

    Raises:
        ValueError: If entry_price <= stop_loss
    """
    # Validate inputs
    if entry_price <= stop_loss:
        raise ValueError("Entry must be above stop loss")

    # Use default if not provided
    risk_percent = risk_percent or config.risk_percent

    # Get account info
    account = self.get_account_info()
    if not account:
        logger.error("Cannot get account info")
        return 0.01  # Fallback minimum

    # Calculate risk amount
    risk_amount = account["balance"] * (risk_percent / 100)
    stop_distance = abs(entry_price - stop_loss)

    # Get symbol info
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        logger.error(f"Symbol not found: {symbol}")
        return 0.01

    # Calculate position size
    pip_value = symbol_info.trade_contract_size * 0.01
    lot_size = risk_amount / (stop_distance * 100)

    # Apply constraints
    lot_size = max(symbol_info.volume_min, lot_size)
    lot_size = min(symbol_info.volume_max, lot_size)
    lot_size = min(config.max_position_size, lot_size)

    # Round to step
    lot_size = round(lot_size / symbol_info.volume_step) * symbol_info.volume_step

    # Apply confidence multiplier
    if hasattr(self, 'current_confidence'):
        confidence = self.current_confidence
        if confidence >= 75:
            multiplier = 1.0
        elif confidence >= 60:
            multiplier = 0.5
        else:
            multiplier = 0.0
        lot_size *= multiplier

    logger.info(f"Position size: {lot_size} lots")
    return lot_size
```

### Bad Code Example (to avoid)

```python
def calc_pos_size(s, e, sl):  # Missing type hints, vague names
    """Calculate position size."""  # Insufficient docstring
    bal = 10000  # Hardcoded value
    r = bal * 0.01  # Unclear variable
    d = e - sl
    ps = r / (d * 100)  # Abbreviated names
    return ps  # No validation, no logging, no error handling
```

---

## Configuration Management

### Overview

Configuration is managed via `src/config.py` using Pydantic Settings with environment variable loading from `.env`. All settings are validated on initialization with type checking and range constraints.

### Configuration Structure

**Settings Location**: `src/config.py`
**Environment File**: `.env` (copy from `.env.example`)
**Singleton Access**: `from src.config import get_settings; config = get_settings()`

### RiskGuard Phase 1 Settings

The RiskGuard module implements multi-layer position management with 5 core settings:

#### 1. Max Concurrent Positions
```python
MAX_CONCURRENT_POSITIONS: int = 2  # (range: 1-10)
```
- **Purpose**: Limits open positions simultaneously
- **Default**: 2 positions max
- **Use Case**: Prevent over-exposure when signals overlap
- **Impact**: Rejects new signals when limit reached

#### 2. Max Total Lots
```python
MAX_TOTAL_LOTS: float = 0.2  # (range: 0.01-5.0)
```
- **Purpose**: Cap total lot exposure across all positions
- **Default**: 0.2 lots maximum
- **Use Case**: Account-wide leverage protection
- **Impact**: Scales down position size if total exceeds limit

#### 3. Max Account Risk Percent
```python
MAX_ACCOUNT_RISK_PERCENT: float = 3.0  # (range: 0.5-10.0)
```
- **Purpose**: Absolute max account risk across all positions
- **Default**: 3% of account balance
- **Use Case**: Risk-of-ruin prevention
- **Impact**: Blocks trade if total risk exceeds threshold

#### 4. Opposite Position Policy
```python
OPPOSITE_POSITION_POLICY: Literal["reject", "close_first", "hedge"] = "close_first"
```
- **Purpose**: Handle signals opposite to existing positions
- **Options**:
  - `"reject"`: Skip opposite signal, log warning
  - `"close_first"`: Close existing, execute new signal
  - `"hedge"`: Allow both positions simultaneously (advanced)
- **Default**: `"close_first"` (safe default)
- **Use Case**: Conflict resolution strategy

#### 5. Duplicate Cooldown Minutes
```python
DUPLICATE_COOLDOWN_MINUTES: int = 15  # (range: 1-120)
```
- **Purpose**: Prevent duplicate signal spam
- **Default**: 15-minute cooldown between same signals
- **Use Case**: Avoid redundant entries on same symbol
- **Impact**: Blocks duplicate signals within window

### Configuration Validation Rules

| Setting | Min | Max | Validation |
|---------|-----|-----|-----------|
| `max_concurrent_positions` | 1 | 10 | ≥1 required |
| `max_total_lots` | 0.01 | 5.0 | Must be positive |
| `max_account_risk_percent` | 0.5 | 10.0 | Percentage bounds |
| `opposite_position_policy` | - | - | Enum: reject\|close_first\|hedge |
| `duplicate_cooldown_minutes` | 1 | 120 | Minutes integer |

### Loading Configuration

```python
# Automatic on import (singleton pattern)
from src.config import get_settings
config = get_settings()

# Access RiskGuard settings
max_positions = config.max_concurrent_positions
max_risk = config.max_account_risk_percent
policy = config.opposite_position_policy

# Validate in trading logic
if current_positions >= config.max_concurrent_positions:
    logger.warning("Position limit reached, skipping signal")
```

### Environment Variable Naming

All settings use uppercase with underscores in `.env`:

```bash
# RiskGuard Settings
MAX_CONCURRENT_POSITIONS=2
MAX_TOTAL_LOTS=0.2
MAX_ACCOUNT_RISK_PERCENT=3.0
OPPOSITE_POSITION_POLICY=close_first
DUPLICATE_COOLDOWN_MINUTES=15
```

### Integration Points

**Core Trading Module** (`trade_executor.py`):
- Checks `max_concurrent_positions` before executing
- Validates total risk vs `max_account_risk_percent`
- Applies `opposite_position_policy` logic
- Enforces `duplicate_cooldown_minutes` window

**Risk Management**:
- RiskGuard enforces settings before order submission
- Position sizing respects `max_total_lots` constraint
- Multi-layer validation prevents account blow-up

### Best Practices

1. **Conservative Defaults**: Start with safe values, increase after validation
2. **Account-Appropriate**: Adjust based on account size and risk tolerance
3. **Testing First**: Validate with paper trading before live
4. **Gradual Increase**: Increase exposure only after proving profitability
5. **Documentation**: Document reasoning for custom values in team notes

---

## Summary

Adhering to these standards ensures:
- **Readability**: Others (and future you) can understand code
- **Maintainability**: Changes are safe and localized
- **Testability**: Code can be thoroughly tested
- **Reliability**: Fewer bugs and faster debugging
- **Scalability**: Code grows with the project

---

**Document Version**: 1.1
**Last Updated**: 2026-01-05
**Next Review**: After Phase 6
