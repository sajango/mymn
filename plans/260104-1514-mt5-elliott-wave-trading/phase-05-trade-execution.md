# Phase 5: Trade Execution

## Context Links
- [Plan Overview](./plan.md)
- [Phase 4: Telegram Bot](./phase-04-telegram-bot.md)
- [MT5 Research](./research/researcher-02-mt5-python.md)

## Overview
- **Priority**: P1
- **Status**: ✅ Complete (Code Review: 2026-01-04)
- **Effort**: 5h (+2h for trailing stop)
- **Description**: Execute trades via MT5 with position management and trailing stop
- **Review**: [Code Review Report](../reports/code-reviewer-260104-1823-phase5-trade-execution.md)

## Key Insights
- Use order_send() for market orders
- Multiple TP levels require partial close strategy
- Paper trading mode for testing
- Magic number for order identification
- Position sizing based on risk % AND confidence level
- **Trailing stop**: custom implementation (not MT5 native)
- **Trailing stop state machine**: inactive → activated → trailing

## Requirements

### Functional
- Execute market orders with SL/TP
- Position sizing from risk percentage AND confidence multiplier
- Partial close at TP levels
- Modify SL/TP on existing positions
- Track positions by magic number
- **Trailing stop activation after TP1 or profit > 1R**
- **Breakeven + buffer (5 pips) after activation**
- **Trail at 1.5 ATR distance**
- **Confidence-based sizing: 75%+ = full, 60-74% = half**

### Non-Functional
- Sync operations (via executor in async context)
- Slippage protection (deviation parameter)
- Retry on requote

## Architecture

### Trade Flow
```
TradingSignal
        ↓
Calculate position size (risk %)
        ↓
Place market order with SL/TP1
        ↓
Store order ticket + TP levels
        ↓
Monitor price (via scheduler)
        ↓
Partial close at TP levels
```

### Position Sizing Formula
```
Risk Amount = Account Balance × Risk %
Stop Distance = Entry - Stop Loss
Position Size = Risk Amount / (Stop Distance × Pip Value)
```

## Related Code Files

### Files to Modify
- `src/mt5_client.py` - Add execution methods

### Files to Create
- `src/database.py` - Position tracking

## Implementation Steps

1. **Add execution methods to src/mt5_client.py**

```python
# Add to MT5Client class

def get_account_info(self) -> Optional[dict]:
    """Get account balance and margin info"""
    info = mt5.account_info()
    if info is None:
        return None
    return {
        "balance": info.balance,
        "equity": info.equity,
        "margin": info.margin,
        "free_margin": info.margin_free,
        "currency": info.currency,
    }

def calculate_position_size(
    self,
    symbol: str,
    entry_price: float,
    stop_loss: float,
    risk_percent: float = None,
) -> float:
    """Calculate lot size based on risk percentage"""
    risk_percent = risk_percent or config.risk_percent

    account = self.get_account_info()
    if account is None:
        logger.error("Cannot get account info for position sizing")
        return 0.01  # Minimum fallback

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return 0.01

    risk_amount = account["balance"] * (risk_percent / 100)
    stop_distance = abs(entry_price - stop_loss)

    # XAUUSD: 1 lot = 100 oz, $1 per 0.01 move
    pip_value = symbol_info.trade_contract_size * 0.01

    lot_size = risk_amount / (stop_distance * 100)

    # Apply limits
    lot_size = max(symbol_info.volume_min, lot_size)
    lot_size = min(symbol_info.volume_max, lot_size)
    lot_size = min(config.max_position_size, lot_size)

    # Round to step
    lot_size = round(lot_size / symbol_info.volume_step) * symbol_info.volume_step

    logger.info(f"Position size: {lot_size} lots (risk: {risk_percent}%, amount: ${risk_amount:.2f})")
    return lot_size

def place_market_order(
    self,
    symbol: str,
    order_type: str,  # "BUY" or "SELL"
    volume: float,
    stop_loss: float,
    take_profit: float,
    comment: str = "EW Auto",
    magic: int = 123456,
) -> Optional[int]:
    """Place market order with SL/TP"""
    if config.paper_trading:
        logger.info(f"PAPER TRADE: {order_type} {volume} {symbol} SL:{stop_loss} TP:{take_profit}")
        return -1  # Fake ticket for paper trading

    # Get current price
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.error(f"Failed to get tick: {mt5.last_error()}")
        return None

    mt5_type = mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if order_type == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5_type,
        "price": price,
        "sl": stop_loss,
        "tp": take_profit,
        "deviation": 20,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    # Retry on requote
    for attempt in range(3):
        result = mt5.order_send(request)

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Order placed: ticket={result.order}")
            return result.order

        if result.retcode == mt5.TRADE_RETCODE_REQUOTE:
            # Refresh price
            tick = mt5.symbol_info_tick(symbol)
            request["price"] = tick.ask if order_type == "BUY" else tick.bid
            continue

        logger.error(f"Order failed: {result.retcode} - {result.comment}")
        break

    return None

def get_positions(self, magic: int = 123456) -> list[dict]:
    """Get open positions by magic number"""
    positions = mt5.positions_get()
    if positions is None:
        return []

    return [
        {
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": "BUY" if p.type == 0 else "SELL",
            "volume": p.volume,
            "open_price": p.price_open,
            "current_price": p.price_current,
            "sl": p.sl,
            "tp": p.tp,
            "profit": p.profit,
            "magic": p.magic,
        }
        for p in positions
        if p.magic == magic
    ]

def modify_position(
    self,
    ticket: int,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> bool:
    """Modify position SL/TP"""
    if config.paper_trading:
        logger.info(f"PAPER: Modify position {ticket} SL:{stop_loss} TP:{take_profit}")
        return True

    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        logger.error(f"Position not found: {ticket}")
        return False

    pos = positions[0]

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "sl": stop_loss if stop_loss else pos.sl,
        "tp": take_profit if take_profit else pos.tp,
    }

    result = mt5.order_send(request)
    success = result.retcode == mt5.TRADE_RETCODE_DONE

    if success:
        logger.info(f"Position modified: {ticket}")
    else:
        logger.error(f"Modify failed: {result.comment}")

    return success

def close_partial(self, ticket: int, volume: float) -> bool:
    """Close partial position volume"""
    if config.paper_trading:
        logger.info(f"PAPER: Partial close {ticket} volume={volume}")
        return True

    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False

    pos = positions[0]
    tick = mt5.symbol_info_tick(pos.symbol)

    close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    price = tick.bid if pos.type == 0 else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": ticket,
        "symbol": pos.symbol,
        "volume": volume,
        "type": close_type,
        "price": price,
        "deviation": 20,
        "magic": pos.magic,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    success = result.retcode == mt5.TRADE_RETCODE_DONE

    if success:
        logger.info(f"Partial close: {ticket} volume={volume}")
    else:
        logger.error(f"Partial close failed: {result.comment}")

    return success
```

2. **Create src/database.py**

```python
"""SQLite database for trade tracking"""
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from src.config import config

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or config.db_path
        self._init_db()

    def _init_db(self):
        """Initialize database tables"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT,
                    symbol TEXT,
                    action TEXT,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit_1 REAL,
                    take_profit_2 REAL,
                    take_profit_3 REAL,
                    confidence INTEGER,
                    status TEXT DEFAULT 'pending'
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY,
                    signal_id INTEGER,
                    ticket INTEGER,
                    symbol TEXT,
                    action TEXT,
                    volume REAL,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    open_time TEXT,
                    close_time TEXT,
                    close_price REAL,
                    profit REAL,
                    status TEXT DEFAULT 'open',
                    FOREIGN KEY (signal_id) REFERENCES signals (id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS tp_levels (
                    id INTEGER PRIMARY KEY,
                    trade_id INTEGER,
                    level TEXT,
                    price REAL,
                    close_percent INTEGER,
                    triggered INTEGER DEFAULT 0,
                    FOREIGN KEY (trade_id) REFERENCES trades (id)
                )
            """)

    def save_signal(self, signal) -> int:
        """Save signal to database"""
        s = signal.signal
        tps = s.take_profit or []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO signals (timestamp, symbol, action, entry_price, stop_loss,
                    take_profit_1, take_profit_2, take_profit_3, confidence, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.timestamp.isoformat(),
                signal.symbol,
                s.action,
                s.entry_price,
                s.stop_loss,
                tps[0].price if len(tps) > 0 else None,
                tps[1].price if len(tps) > 1 else None,
                tps[2].price if len(tps) > 2 else None,
                s.confidence,
                "pending",
            ))
            return cursor.lastrowid

    def save_trade(self, signal_id: int, ticket: int, volume: float, signal) -> int:
        """Save executed trade"""
        s = signal.signal

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO trades (signal_id, ticket, symbol, action, volume,
                    entry_price, stop_loss, take_profit, open_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id,
                ticket,
                signal.symbol,
                s.action,
                volume,
                s.entry_price,
                s.stop_loss,
                s.take_profit[0].price if s.take_profit else None,
                datetime.utcnow().isoformat(),
                "open",
            ))
            trade_id = cursor.lastrowid

            # Save TP levels
            if s.take_profit:
                for tp in s.take_profit:
                    conn.execute("""
                        INSERT INTO tp_levels (trade_id, level, price, close_percent)
                        VALUES (?, ?, ?, ?)
                    """, (trade_id, tp.level, tp.price, tp.close_percent))

            return trade_id

    def update_signal_status(self, signal_id: int, status: str):
        """Update signal status (executed, skipped, expired)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE signals SET status = ? WHERE id = ?",
                (status, signal_id)
            )

    def get_open_trades(self) -> list[dict]:
        """Get all open trades"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'open'"
            ).fetchall()
            return [dict(row) for row in rows]


# Singleton
database = Database()
```

## Todo List

- [x] Add execution methods to mt5_client.py ✅
- [x] Implement position sizing with confidence adjustment ✅
- [x] Implement partial close ✅
- [x] Create src/database.py with full schema ✅
- [x] Add paper trading mode ✅
- [x] Write tests (45 tests, 100% pass) ✅
- [x] **Implement TrailingStopManager class** ✅
- [x] **Add trailing_state column to trades table (inactive/activated/trailing)** ✅
- [x] **Implement activation logic (TP1 hit OR profit > 1R)** ✅
- [x] **Implement breakeven + buffer logic** ✅
- [x] **Implement ATR-based trail distance calculation** ✅
- [x] **Add confidence multiplier to position sizing** ✅
- [x] **Test trailing stop with paper trades** ✅
- [ ] Test with demo account (requires live MT5 connection)
- [ ] Address code review findings #1, #3, #5

## Success Criteria

- [x] Orders placed correctly ✅
- [x] Position sizing matches risk % with confidence adjustment ✅
- [x] Partial close works ✅
- [x] Paper trading logs correctly ✅
- [x] Database tracks all trades with trailing state ✅
- [x] Trailing stop state machine functional ✅
- [x] All tests passing (45/45) ✅

## Risk Assessment

| Risk | Probability | Impact | Mitigation | Status |
|------|-------------|--------|------------|--------|
| Wrong lot size | Medium | High | Double-check formula | ✅ Tested, formula verified |
| Order rejected | Low | Medium | Retry with fresh price | ✅ Implemented with 3 retries |
| Paper mode leak | Low | Critical | Check flag on every call | ✅ Checked at all entry points |
| Database connection leak | Medium | Medium | Add explicit close pattern | ⚠️ Review Finding #1 |
| Position sizing fallback | Medium | Medium | Alert on fallback to min size | ⚠️ Review Finding #3 |
| Multi-symbol bugs | Low | Medium | Test with forex symbols | ⚠️ Review Finding #5 |

## Security Considerations

- ✅ Paper trading default for safety
- ✅ Max position size limit enforced
- ✅ Magic number for position identification
- ✅ Parameterized SQL queries (no injection risk)
- ✅ Telegram authorization checks

## Code Review Summary

**Overall Grade**: A- (Excellent with minor improvements)

**Strengths**:
- Comprehensive test coverage (96% database, 87% executor, 84% trailing)
- Clean state machine architecture
- Strong security posture
- All 45 tests passing

**Areas for Improvement**:
1. Database connection resource management
2. Position sizing error alerting
3. Multi-symbol support verification

See [Full Review Report](../reports/code-reviewer-260104-1823-phase5-trade-execution.md)

## Next Steps

→ [Phase 6: Orchestration](./phase-06-orchestration.md)

**Recommended Before Phase 6**:
1. Fix database connection leak (Finding #1)
2. Add alerts for position sizing fallbacks (Finding #3)
3. Test with demo account on live MT5 connection
