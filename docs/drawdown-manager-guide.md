# DrawdownManager - Real-Time Risk Management Guide

**Last Updated**: 2026-01-08
**Phase**: Phase 3 Implementation
**Reference**: instruction_v4.md Section 8.7

## Table of Contents

1. [Overview](#overview)
2. [Configuration](#configuration)
3. [API Reference](#api-reference)
4. [Limit Enforcement](#limit-enforcement)
5. [Status States](#status-states)
6. [Integration](#integration)
7. [Examples](#examples)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The DrawdownManager implements real-time, multi-timeframe drawdown tracking and enforcement per instruction_v4 Section 8.7. It prevents catastrophic account losses through five independent limit checks, automatic recovery mode, and persistent state management.

### Key Features

✅ **Daily Limits**
- Maximum loss: 3% of day-start balance
- Maximum trades: 5 per day
- Consecutive loss pause: 3 losses trigger trading pause

✅ **Weekly Limits**
- Maximum loss: 6% of week-start balance

✅ **Monthly Limits**
- Maximum drawdown from peak: 10%

✅ **Recovery Mode**
- Automatically triggers at 5% drawdown from peak
- Reduces position size to 0.5x
- Gradually increases based on consecutive losses

✅ **State Persistence**
- All state stored in `drawdown_state` database table
- Survives application restarts
- Daily state creation and weekly resets

---

## Configuration

All DrawdownManager settings are configured via `.env` file using Pydantic Settings.

### Configuration Options

```python
# Daily limits
daily_max_loss_percent: float = Field(
    default=3.0,
    ge=0.5, le=10.0,
    description="Maximum daily loss percentage before trading pause"
)

daily_max_trades: int = Field(
    default=5,
    ge=1, le=20,
    description="Maximum trades allowed per day"
)

consecutive_loss_limit: int = Field(
    default=3,
    ge=1, le=10,
    description="Consecutive losses before 4-hour pause"
)

# Weekly limit
weekly_max_loss_percent: float = Field(
    default=6.0,
    ge=1.0, le=20.0,
    description="Maximum weekly loss percentage"
)

# Monthly limit
monthly_max_drawdown_percent: float = Field(
    default=10.0,
    ge=2.0, le=30.0,
    description="Maximum monthly drawdown from peak"
)

# Recovery mode
recovery_mode_threshold: float = Field(
    default=5.0,
    ge=1.0, le=15.0,
    description="Drawdown % to trigger recovery mode (0.5x position)"
)
```

### Example .env Configuration

```ini
# Drawdown Manager Settings
DAILY_MAX_LOSS_PERCENT=3.0
DAILY_MAX_TRADES=5
CONSECUTIVE_LOSS_LIMIT=3
WEEKLY_MAX_LOSS_PERCENT=6.0
MONTHLY_MAX_DRAWDOWN_PERCENT=10.0
RECOVERY_MODE_THRESHOLD=5.0
```

---

## API Reference

### DrawdownManager Class

```python
from src.drawdown_manager import DrawdownManager, get_drawdown_manager

# Get singleton instance
manager = get_drawdown_manager()

# Or create with dependencies
from src.database import Database
from src.config import get_settings

manager = DrawdownManager(
    db=Database(),
    settings=get_settings()
)
```

### Methods

#### validate(account_balance: float) -> DrawdownCheckResult

Checks if trading is allowed based on current drawdown state.

**Parameters**:
- `account_balance` (float): Current account balance in USD

**Returns**: DrawdownCheckResult with:
- `trading_allowed` (bool): Whether trading is permitted
- `status` (DrawdownStatus): Current risk state
- `position_size_modifier` (float): Multiplier for position size (0.0-1.0)
- `pause_reason` (str): Why trading is paused (if paused)
- `limits_remaining` (dict): Remaining capacity before limits trigger

**Example**:
```python
result = manager.validate(account_balance=10000.0)

if result.trading_allowed:
    position_size = base_position * result.position_size_modifier
    print(f"Trading allowed. Use {result.position_size_modifier:.2f}x position")
else:
    print(f"Trading paused: {result.pause_reason}")
    notify_user(result.pause_reason)
```

---

#### record_trade_result(pnl: float, is_win: bool, balance: float)

Records a trade result and updates all counters.

**Parameters**:
- `pnl` (float): Profit/loss amount in USD
- `is_win` (bool): Whether trade was profitable
- `balance` (float): Account balance after trade

**Example**:
```python
# After trade closes
profit_loss = 150.0  # or -75.0 for loss
is_profitable = profit_loss > 0
new_balance = 10150.0

manager.record_trade_result(
    pnl=profit_loss,
    is_win=is_profitable,
    balance=new_balance
)
```

---

#### reset_daily(current_balance: float)

Resets daily counters. Call at start of trading day.

**Parameters**:
- `current_balance` (float): Current account balance

**Reset Behavior**:
- Clears daily_pnl, daily_trades, consecutive_losses
- Lifts any trading pause
- Sets daily_start_balance for new calculations
- Preserves peak_balance (monthly drawdown tracking)
- Preserves weekly counters

**Example**:
```python
# Call at 00:00 UTC or start of trading session
manager.reset_daily(current_balance=10000.0)
```

---

#### reset_weekly(current_balance: float)

Resets weekly counters. Call at start of trading week (Monday).

**Parameters**:
- `current_balance` (float): Current account balance

**Reset Behavior**:
- Clears weekly_pnl, weekly_trades
- Sets weekly_start_balance for new calculations
- Does NOT clear daily counters
- Preserves peak_balance

**Example**:
```python
# Call on Monday at 00:00 UTC
if datetime.now().weekday() == 0:  # Monday
    manager.reset_weekly(current_balance=current_balance)
```

---

#### get_status_summary() -> dict

Returns current drawdown status without validation.

**Returns**:
```python
{
    "date": "2026-01-08",
    "daily_pnl": -150.50,
    "daily_trades": 3,
    "weekly_pnl": -450.25,
    "consecutive_losses": 2,
    "trading_paused": False,
    "pause_reason": None,
    "peak_balance": 10500.00
}
```

**Example**:
```python
summary = manager.get_status_summary()
print(f"Today: {summary['daily_pnl']:+.2f} ({summary['daily_trades']} trades)")
print(f"Peak balance: ${summary['peak_balance']:.2f}")
```

---

### DrawdownStatus Enum

```python
from src.drawdown_manager import DrawdownStatus

class DrawdownStatus(str, Enum):
    NORMAL = "normal"           # All checks passing, 1.0x position
    HIGH_ALERT = "high_alert"   # Approaching limits, 0.75x or 0.5x
    RECOVERY = "recovery"       # In recovery mode, 0.5x position
    PAUSED = "paused"          # Trading paused, 0x position
```

---

### DrawdownCheckResult Dataclass

```python
from src.drawdown_manager import DrawdownCheckResult

@dataclass
class DrawdownCheckResult:
    trading_allowed: bool           # Can execute trades?
    status: DrawdownStatus          # Current risk state
    position_size_modifier: float   # Position size multiplier
    pause_reason: Optional[str]     # Why paused (if paused)
    limits_remaining: dict          # Capacity before limits
```

---

## Limit Enforcement

### Daily Loss Limit (3% Max)

**Trigger**: Daily P&L ≤ -3% of day-start balance

```python
# Example: $10,000 starting balance
daily_loss_threshold = 10000 * 0.03  # = $300
# If cumulative loss >= $300 → trading paused

daily_loss_percent = (daily_pnl / daily_start_balance) * 100
if daily_loss_percent <= -3.0:
    # PAUSE TRADING
```

**Pause Reason**: "DAILY_LIMIT: -3.25% loss today (limit -3%)"

---

### Daily Trade Limit (5 Max)

**Trigger**: Number of trades executed ≥ 5

```python
# If 5 trades already executed today:
# - 6th trade request → BLOCKED

if daily_trades >= 5:
    # PAUSE TRADING
```

**Pause Reason**: "DAILY_TRADES: 5 trades today (limit 5)"

---

### Consecutive Loss Limit (3)

**Trigger**: 3 consecutive losing trades

```python
# Loss → Loss → Loss → PAUSE

if consecutive_losses >= 3:
    # PAUSE TRADING
```

**Pause Reason**: "CONSECUTIVE_LOSSES: 3 losses in a row (limit 3)"

**Recovery**: Win resets counter to 0

---

### Weekly Loss Limit (6% Max)

**Trigger**: Weekly P&L ≤ -6% of week-start balance

```python
# Example: $10,000 starting balance
weekly_loss_threshold = 10000 * 0.06  # = $600
# If cumulative loss >= $600 → trading paused

weekly_loss_percent = (weekly_pnl / weekly_start_balance) * 100
if weekly_loss_percent <= -6.0:
    # PAUSE TRADING
```

**Pause Reason**: "WEEKLY_LIMIT: -6.50% loss this week (limit -6%)"

---

### Monthly Drawdown Limit (10% From Peak)

**Trigger**: Current balance ≤ 90% of peak balance

```python
# Peak balance: $11,000
# Drawdown limit: 10% = $1,100
# Pause threshold: $11,000 - $1,100 = $9,900

# If current balance drops to $9,900 or below:
# PAUSE TRADING

drawdown_pct = ((peak - balance) / peak) * 100
if drawdown_pct >= 10.0:
    # PAUSE TRADING
```

**Pause Reason**: "MAX_DRAWDOWN: 10.25% from peak (limit 10%)"

**Peak Tracking**: Updated whenever new high balance achieved

---

## Status States

### NORMAL (1.0x Position)
- All limits have capacity
- Normal trading allowed
- Full position size
- Conditions:
  - Daily loss < 70% of threshold
  - Consecutive losses < 2
  - Weekly loss < 50% of threshold

### HIGH_ALERT (0.75x or 0.5x Position)
- Approaching or breaching limits
- Position size reduced
- Still trading allowed
- Triggers:
  - 1 consecutive loss → 0.75x
  - 2+ consecutive losses → 0.5x
  - Daily loss > 70% of threshold → 0.5x
  - 5%+ drawdown from peak → 0.5x

### RECOVERY (0.5x Position)
- Active drawdown recovery mode
- Triggered at 5% drawdown from peak
- Automatic position reduction
- Must wait for drawdown to improve

### PAUSED (0x Position)
- Trading completely stopped
- Pause reason documented
- Will resume after:
  - Limits reset (daily, weekly)
  - Consecutive loss counter resets (on win)
  - Manual override (not recommended)

---

## Integration

### With RiskGuard (Phase 9)

DrawdownManager integrates with RiskGuard for pre-execution validation:

```python
# In risk_guard.py
from src.drawdown_manager import get_drawdown_manager

def validate_signal(signal, account_balance):
    drawdown_mgr = get_drawdown_manager()

    # Check drawdown limits first
    drawdown_result = drawdown_mgr.validate(account_balance)
    if not drawdown_result.trading_allowed:
        return False, f"Drawdown: {drawdown_result.pause_reason}"

    # Continue with other validations
    # Apply position modifier
    position_multiplier = drawdown_result.position_size_modifier
```

### With TradeExecutor

TradeExecutor applies position modifier:

```python
# In trade_executor.py
def calculate_position_size(signal, account_balance):
    drawdown_mgr = get_drawdown_manager()

    result = drawdown_mgr.validate(account_balance)
    if not result.trading_allowed:
        return None  # Can't trade

    # Calculate base position size
    base_size = calculate_base_size(signal, account_balance)

    # Apply drawdown modifier
    actual_size = base_size * result.position_size_modifier

    return actual_size
```

### With TrailingStopManager

After trade completes:

```python
# In trailing_stop_manager.py or trade_executor.py
def close_position(trade):
    pnl = calculate_pnl(trade)
    is_win = pnl > 0
    new_balance = get_account_balance()

    # Record result for drawdown tracking
    drawdown_mgr = get_drawdown_manager()
    drawdown_mgr.record_trade_result(
        pnl=pnl,
        is_win=is_win,
        balance=new_balance
    )
```

### Daily Reset Hook

Call at start of each day:

```python
# In main event loop or scheduler
from datetime import datetime
from src.drawdown_manager import get_drawdown_manager
from src.mt5_client import get_mt5_client

def daily_maintenance():
    if datetime.now().hour == 0 and datetime.now().minute < 5:
        mt5 = get_mt5_client()
        balance = mt5.get_account_balance()

        mgr = get_drawdown_manager()
        mgr.reset_daily(balance)
        logger.info("Daily reset completed")

def weekly_maintenance():
    if datetime.now().weekday() == 0 and datetime.now().hour == 0:
        mt5 = get_mt5_client()
        balance = mt5.get_account_balance()

        mgr = get_drawdown_manager()
        mgr.reset_weekly(balance)
        logger.info("Weekly reset completed")
```

---

## Examples

### Example 1: Basic Trading Validation

```python
from src.drawdown_manager import get_drawdown_manager

def can_trade(account_balance):
    manager = get_drawdown_manager()
    result = manager.validate(account_balance)

    if not result.trading_allowed:
        print(f"❌ Trading paused: {result.pause_reason}")
        return False

    print(f"✅ Trading allowed ({result.status.value})")
    print(f"   Position size: {result.position_size_modifier:.2f}x")
    print(f"   Daily loss remaining: {result.limits_remaining['daily_loss_remaining_pct']:.2f}%")
    print(f"   Trades remaining: {result.limits_remaining['daily_trades_remaining']}")

    return True
```

### Example 2: Recording Trade Results

```python
def execute_and_track_trade(signal, initial_balance):
    # Execute trade (pseudo code)
    entry_price = signal.entry
    exit_price = market_price_at_exit

    # Calculate P&L
    direction_multiplier = 1 if signal.action == "BUY" else -1
    pnl = (exit_price - entry_price) * volume * direction_multiplier

    # Get new balance
    new_balance = initial_balance + pnl
    is_win = pnl > 0

    # Record for drawdown tracking
    manager = get_drawdown_manager()
    manager.record_trade_result(pnl=pnl, is_win=is_win, balance=new_balance)

    # Check status
    status_summary = manager.get_status_summary()
    print(f"Trade Result: {pnl:+.2f}")
    print(f"Daily P&L: {status_summary['daily_pnl']:+.2f} ({status_summary['daily_trades']} trades)")
    print(f"Consecutive losses: {status_summary['consecutive_losses']}")
```

### Example 3: Position Size with Drawdown Modifier

```python
def calculate_position_size(signal, account_balance, risk_percent=1.0):
    # Base position calculation
    sl_distance = abs(signal.entry - signal.stop_loss)
    risk_amount = account_balance * (risk_percent / 100)
    base_size = risk_amount / sl_distance

    # Apply drawdown modifier
    manager = get_drawdown_manager()
    result = manager.validate(account_balance)

    if not result.trading_allowed:
        return 0  # Can't trade at all

    # Reduce size based on drawdown status
    final_size = base_size * result.position_size_modifier

    print(f"Base size: {base_size:.2f} lots")
    print(f"Modifier: {result.position_size_modifier:.2f}x ({result.status.value})")
    print(f"Final size: {final_size:.2f} lots")

    return final_size
```

### Example 4: Status Dashboard

```python
def print_drawdown_dashboard():
    manager = get_drawdown_manager()

    # Validate current balance
    balance = 10000.0
    result = manager.validate(balance)

    # Get detailed summary
    summary = manager.get_status_summary()

    print("=" * 50)
    print("DRAWDOWN MANAGER STATUS")
    print("=" * 50)
    print(f"Date: {summary['date']}")
    print(f"Status: {result.status.value.upper()}")
    print(f"Trading Allowed: {'✅ YES' if result.trading_allowed else '❌ NO'}")
    if not result.trading_allowed:
        print(f"Reason: {result.pause_reason}")
    print()
    print("DAILY METRICS")
    print(f"  P&L: {summary['daily_pnl']:+.2f}")
    print(f"  Trades: {summary['daily_trades']}/5")
    print(f"  Consecutive Losses: {summary['consecutive_losses']}/3")
    print()
    print("WEEKLY METRICS")
    print(f"  P&L: {summary['weekly_pnl']:+.2f}")
    print()
    print("POSITION SIZING")
    print(f"  Modifier: {result.position_size_modifier:.2f}x")
    print(f"  Trades Remaining: {result.limits_remaining['daily_trades_remaining']}")
    print(f"  Loss Remaining: {result.limits_remaining['daily_loss_remaining_pct']:.2f}%")
    print()
    print("PEAK TRACKING")
    print(f"  Peak Balance: ${summary['peak_balance']:.2f}")
    drawdown = ((summary['peak_balance'] - balance) / summary['peak_balance']) * 100
    print(f"  Current Drawdown: {drawdown:.2f}% (10% limit)")
    print("=" * 50)
```

---

## Troubleshooting

### Issue: Trading is paused but I think the limit is wrong

**Solution**: Check the pause reason:
```python
manager = get_drawdown_manager()
result = manager.validate(account_balance)
print(f"Pause reason: {result.pause_reason}")
```

The pause reason includes exact numbers and calculations.

---

### Issue: Position sizes are 0.5x or 0.75x

**Solution**: This is intentional recovery mode:

```python
result = manager.validate(account_balance)
print(f"Status: {result.status.value}")  # Check if RECOVERY or HIGH_ALERT

# Status explanation:
# RECOVERY: 5%+ drawdown from peak, reduce position
# HIGH_ALERT: 2+ consecutive losses or approaching limits
# NORMAL: All clear, 1.0x position
```

---

### Issue: Consecutive losses reset unexpectedly

**Solution**: A winning trade resets the counter. Check your trade results:

```python
summary = manager.get_status_summary()
print(f"Consecutive losses: {summary['consecutive_losses']}")

# If it shows 0, your last trade was a win
# Record it again if tracking issue suspected
```

---

### Issue: Daily limit calculated incorrectly

**Solution**: Verify your calculation:

```python
# Daily loss limit = 3% of day-start balance
# Example: Started day with $10,000
# 3% loss threshold = $300

start_balance = 10000.0
threshold = start_balance * 0.03  # = $300

# If daily_pnl <= -$300 → pause

# Verify in database:
# SELECT daily_start_balance, daily_pnl FROM drawdown_state WHERE date = '2026-01-08'
```

---

### Issue: State not persisting after restart

**Solution**: Verify database connection and schema:

```python
from src.database import get_database

db = get_database()

# Check if table exists
result = db.db_path.exists()
print(f"Database file exists: {result}")

# Verify state is saved
state = db.get_latest_drawdown_state()
print(f"Latest state: {state}")

# If missing, table may not be created - run schema init
```

---

## Related Documentation

- [System Architecture](./system-architecture.md) - Section 8 (Design Patterns)
- [Code Standards](./code-standards.md) - Module organization
- [instruction_v4.md](../instruction_v4.md) - Section 8.7 (Requirements)
- [Database Schema](./system-architecture.md#database-schema) - drawdown_state table

---

**Last Updated**: 2026-01-08
**Author**: Documentation System
**Status**: Phase 3 Complete
