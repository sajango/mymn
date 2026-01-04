# API Documentation - MT5 Elliott Wave Trading System

**Last Updated**: 2026-01-04
**Current Phase**: Phase 8 Complete (Web Dashboard)

## Table of Contents

1. [MT5 Client API](#mt5-client-api)
2. [Signal Parser API](#signal-parser-api)
3. [Database API](#database-api)
4. [Trade Executor API](#trade-executor-api)
5. [Trailing Stop Manager API](#trailing-stop-manager-api)
6. [Claude Client API](#claude-client-api)
7. [Telegram Bot API](#telegram-bot-api)
8. [Dashboard API (Phase 8)](#dashboard-api-phase-8)

---

## MT5 Client API

### Overview
The MT5 Client provides integration with MetaTrader 5 for market data fetching, technical indicators calculation, and trade execution.

### Class: `MT5Client`

```python
class MT5Client:
    def initialize(self) -> bool
    def shutdown(self) -> bool
    def is_connected(self) -> bool
    def fetch_ohlcv(symbol, timeframe, limit) -> Optional[DataFrame]
    def calculate_indicators(df) -> DataFrame
    def get_account_info() -> Optional[dict]
    def calculate_position_size(symbol, entry_price, stop_loss, risk_percent) -> float
    def place_market_order(symbol, order_type, volume, stop_loss, take_profit, comment, magic) -> Optional[int]
    def get_positions(magic) -> list[dict]
    def modify_position(ticket, stop_loss, take_profit) -> bool
    def close_partial(ticket, volume) -> bool
    def get_current_atr(symbol, period) -> Optional[float]
    def validate_symbol(symbol) -> bool
```

#### Methods

##### `initialize() -> bool`
Initialize MT5 connection.

**Parameters**: None

**Returns**:
- `True` if successful
- `False` if connection failed

**Raises**: None

**Example**:
```python
mt5 = MT5Client()
if mt5.initialize():
    print("MT5 connected")
else:
    print("Failed to connect")
```

---

##### `shutdown() -> bool`
Close MT5 connection and cleanup.

**Parameters**: None

**Returns**: `True` if successful

**Example**:
```python
mt5.shutdown()
```

---

##### `is_connected() -> bool`
Check current MT5 connection status.

**Parameters**: None

**Returns**: `True` if connected, `False` otherwise

**Example**:
```python
if mt5.is_connected():
    data = mt5.fetch_ohlcv("XAUUSD", "H1", 100)
```

---

##### `fetch_ohlcv(symbol: str, timeframe: str, limit: int) -> Optional[DataFrame]`
Fetch OHLCV data from MT5.

**Parameters**:
- `symbol` (str): Trading symbol (e.g., "XAUUSD", "EURUSD")
- `timeframe` (str): Timeframe code ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
- `limit` (int): Number of bars to fetch (default: 100)

**Returns**:
- `DataFrame` with columns: Open, High, Low, Close, Volume, Time
- `None` if fetch failed

**Raises**: None

**Example**:
```python
df = mt5.fetch_ohlcv("XAUUSD", "H1", 100)
if df is not None:
    print(f"Fetched {len(df)} bars")
    print(df.tail())
```

---

##### `calculate_indicators(df: DataFrame) -> DataFrame`
Calculate technical indicators on OHLCV data.

**Parameters**:
- `df` (DataFrame): Input OHLCV data with columns [Open, High, Low, Close, Volume]

**Returns**:
- `DataFrame` with original columns + indicator columns:
  - `rsi_14`: RSI(14)
  - `ema_12`: EMA(12)
  - `ema_26`: EMA(26)
  - `macd`: MACD line
  - `macd_signal`: Signal line
  - `atr_14`: ATR(14)

**Example**:
```python
df = mt5.fetch_ohlcv("XAUUSD", "H1", 100)
df = mt5.calculate_indicators(df)
print(f"RSI: {df['rsi_14'].iloc[-1]:.2f}")
print(f"ATR: {df['atr_14'].iloc[-1]:.2f}")
```

---

##### `get_account_info() -> Optional[dict]`
Retrieve current account information.

**Parameters**: None

**Returns**:
- `dict` with keys:
  - `balance` (float): Account balance in USD
  - `equity` (float): Current equity
  - `margin` (float): Used margin
  - `free_margin` (float): Available margin
  - `currency` (str): Account currency
- `None` if retrieval failed

**Example**:
```python
info = mt5.get_account_info()
if info:
    print(f"Balance: ${info['balance']:.2f}")
    print(f"Free Margin: ${info['free_margin']:.2f}")
```

---

##### `calculate_position_size(symbol: str, entry_price: float, stop_loss: float, risk_percent: float = None) -> float`
Calculate position size based on risk percentage.

**Parameters**:
- `symbol` (str): Trading symbol
- `entry_price` (float): Planned entry price
- `stop_loss` (float): Stop loss price
- `risk_percent` (float, optional): Risk percentage (default: from config)

**Returns**:
- `float`: Lot size to trade (e.g., 0.05)

**Notes**:
- Position size = (account_balance × risk%) / (stop_distance × pip_value)
- Respects symbol min/max volumes and config max_position_size
- Confidence multiplier applied: 75%+ = 1.0x, 60-74% = 0.5x, <60% = 0.0x

**Example**:
```python
# Buy XAUUSD at 2000.00 with SL at 1990.00, risk 1%
size = mt5.calculate_position_size(
    symbol="XAUUSD",
    entry_price=2000.00,
    stop_loss=1990.00,
    risk_percent=1.0
)
print(f"Position size: {size} lots")
```

---

##### `place_market_order(symbol: str, order_type: str, volume: float, stop_loss: float, take_profit: float, comment: str = "EW Auto", magic: int = 123456) -> Optional[int]`
Execute a market order on MT5.

**Parameters**:
- `symbol` (str): Trading symbol (e.g., "XAUUSD")
- `order_type` (str): "BUY" or "SELL"
- `volume` (float): Lot size (e.g., 0.05)
- `stop_loss` (float): Stop loss price
- `take_profit` (float): Take profit price
- `comment` (str, optional): Order comment for tracking
- `magic` (int, optional): Magic number for identification

**Returns**:
- `int`: Order ticket number if successful
- `-1`: Fake ticket in paper trading mode
- `None`: If order failed

**Paper Trading Mode**:
- If `config.paper_trading = True`, order is logged but not executed

**Example**:
```python
ticket = mt5.place_market_order(
    symbol="XAUUSD",
    order_type="BUY",
    volume=0.05,
    stop_loss=1990.00,
    take_profit=2010.00,
    comment="Elliott Wave Setup"
)
if ticket:
    print(f"Order placed: ticket {ticket}")
```

---

##### `get_positions(magic: int = 123456) -> list[dict]`
Get all open positions matching magic number.

**Parameters**:
- `magic` (int, optional): Magic number filter (default: 123456)

**Returns**:
- `list[dict]`: List of positions, each dict contains:
  - `ticket` (int): Position ticket
  - `symbol` (str): Trading symbol
  - `type` (str): "BUY" or "SELL"
  - `volume` (float): Open volume
  - `open_price` (float): Entry price
  - `current_price` (float): Current market price
  - `sl` (float): Stop loss level
  - `tp` (float): Take profit level
  - `profit` (float): Unrealized profit/loss in USD
  - `magic` (int): Magic number

**Example**:
```python
positions = mt5.get_positions()
for pos in positions:
    print(f"Ticket {pos['ticket']}: {pos['type']} {pos['volume']} {pos['symbol']}")
    print(f"  Entry: {pos['open_price']}, Current: {pos['current_price']}")
    print(f"  P&L: ${pos['profit']:.2f}")
```

---

##### `modify_position(ticket: int, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> bool`
Modify SL/TP on existing position.

**Parameters**:
- `ticket` (int): Position ticket
- `stop_loss` (float, optional): New stop loss price
- `take_profit` (float, optional): New take profit price

**Returns**: `True` if successful, `False` if failed

**Notes**:
- At least one of stop_loss or take_profit must be provided
- In paper trading mode, returns `True` with logging

**Example**:
```python
# Move stop loss to breakeven + 5 pips
if mt5.modify_position(ticket=12345, stop_loss=2005.0):
    print("Position modified")
else:
    print("Failed to modify position")
```

---

##### `close_partial(ticket: int, volume: float) -> bool`
Close partial position volume.

**Parameters**:
- `ticket` (int): Position ticket
- `volume` (float): Volume to close (must be <= open volume)

**Returns**: `True` if successful, `False` if failed

**Example**:
```python
# Close 50% of position at take profit
if mt5.close_partial(ticket=12345, volume=0.025):
    print("Position partially closed")
```

---

##### `get_current_atr(symbol: str, period: int = 14) -> Optional[float]`
Get current ATR value for position sizing.

**Parameters**:
- `symbol` (str): Trading symbol
- `period` (int, optional): ATR period (default: 14)

**Returns**:
- `float`: Current ATR value
- `None`: If calculation failed

**Notes**:
- Uses H1 timeframe for calculation
- Returns `None` if insufficient data

**Example**:
```python
atr = mt5.get_current_atr("XAUUSD")
if atr:
    trail_distance = atr * 1.5  # Trail at 1.5x ATR
    print(f"Trailing distance: {trail_distance:.2f} pips")
```

---

##### `validate_symbol(symbol: str) -> bool`
Check if symbol exists and is tradeable.

**Parameters**:
- `symbol` (str): Symbol to validate

**Returns**: `True` if symbol is valid, `False` otherwise

**Example**:
```python
if mt5.validate_symbol("XAUUSD"):
    print("Symbol is valid")
```

---

## Signal Parser API

### Overview
Handles trading signal models, JSON extraction, and validation.

### Classes and Functions

#### `class TradingSignal(BaseModel)`
Main trading signal model.

**Fields**:
```python
timestamp: datetime          # When signal was generated
symbol: str                 # Trading symbol
signal: TradeInstruction    # Trade details
metadata: SignalMetadata    # Additional context
execution_instructions: Optional[str]  # Special instructions
```

#### `class TradeInstruction(BaseModel)`
Core trade instruction details.

**Fields**:
```python
action: Literal["BUY", "SELL"]     # Trade direction
entry_price: float                 # Entry price
stop_loss: float                   # Stop loss price
take_profit: list[TradeLevel]     # TP levels (TP1, TP2, TP3)
confidence: int                    # Confidence 0-100
```

#### `class TradeLevel(BaseModel)`
Take profit level definition.

**Fields**:
```python
level: str              # "TP1", "TP2", or "TP3"
price: float           # Price level
close_percent: int     # % of position to close (0-100)
```

#### `class SignalMetadata(BaseModel)`
Signal context information.

**Fields**:
```python
session: str                    # Trading session (London, NY, Asian)
spread_check: bool             # Spread acceptable
confidence_breakdown: dict     # Score components
timeframe_analysis: str        # Which timeframes used
wave_count: Optional[str]      # Elliott Wave count
```

#### `extract_json_from_response(response: str) -> Optional[dict]`
Extract JSON from Claude response with fallback strategies.

**Parameters**:
- `response` (str): Claude API response text

**Returns**:
- `dict`: Parsed JSON
- `None`: If all extraction strategies failed

**Strategies** (in order):
1. Find JSON block (```json ... ```)
2. Find raw JSON object/array
3. Ask Claude to extract JSON (recursive)

**Example**:
```python
response = "Here is the signal: ```json {\"action\": \"BUY\", ...} ```"
data = extract_json_from_response(response)
signal = TradingSignal.model_validate(data)
```

#### `parse_signal(data: dict) -> TradingSignal`
Convert raw data to validated TradingSignal.

**Parameters**:
- `data` (dict): Signal data (from JSON extraction)

**Returns**: `TradingSignal` object

**Raises**: `ValueError` if validation fails

**Example**:
```python
signal = parse_signal({
    "timestamp": "2026-01-04T12:00:00Z",
    "symbol": "XAUUSD",
    "signal": {
        "action": "BUY",
        "entry_price": 2000.00,
        "stop_loss": 1990.00,
        "take_profit": [
            {"level": "TP1", "price": 2010.00, "close_percent": 25},
            {"level": "TP2", "price": 2020.00, "close_percent": 35},
            {"level": "TP3", "price": 2030.00, "close_percent": 40}
        ],
        "confidence": 85
    },
    "metadata": {...}
})
```

---

## Database API

### Overview
SQLite database for persistent trade and signal tracking.

### Class: `Database`

```python
class Database:
    def save_signal(signal: TradingSignal) -> int
    def save_trade(signal_id: int, ticket: int, volume: float, signal: TradingSignal) -> int
    def update_signal_status(signal_id: int, status: str) -> None
    def update_trailing_state(ticket: int, state: str) -> None
    def update_trade_status(ticket: int, status: str) -> None
    def get_trade_by_ticket(ticket: int) -> Optional[dict]
    def get_open_trades() -> list[dict]
    def get_signal_by_id(signal_id: int) -> Optional[dict]
```

#### Methods

##### `save_signal(signal: TradingSignal) -> int`
Store incoming trading signal.

**Parameters**:
- `signal` (TradingSignal): Signal object to save

**Returns**: Signal ID (auto-incremented)

**Database Impact**:
- Inserts into `signals` table with status = 'pending'

**Example**:
```python
signal_id = db.save_signal(signal_obj)
print(f"Signal stored with ID: {signal_id}")
```

---

##### `save_trade(signal_id: int, ticket: int, volume: float, signal: TradingSignal) -> int`
Record executed trade.

**Parameters**:
- `signal_id` (int): Reference to source signal
- `ticket` (int): MT5 position ticket
- `volume` (float): Executed volume
- `signal` (TradingSignal): Signal object

**Returns**: Trade ID (auto-incremented)

**Database Impact**:
- Inserts into `trades` table with status = 'open'
- Inserts take profit levels into `tp_levels` table
- Creates trading_state = 'inactive'

**Example**:
```python
trade_id = db.save_trade(
    signal_id=1,
    ticket=12345,
    volume=0.05,
    signal=signal_obj
)
```

---

##### `update_signal_status(signal_id: int, status: str)`
Update signal execution status.

**Parameters**:
- `signal_id` (int): Signal to update
- `status` (str): New status ("pending", "executed", "skipped", "expired")

**Example**:
```python
db.update_signal_status(signal_id=1, status="executed")
```

---

##### `update_trailing_state(ticket: int, state: str)`
Update position trailing stop state.

**Parameters**:
- `ticket` (int): Position ticket
- `state` (str): New state ("inactive", "activated", "trailing")

**Example**:
```python
db.update_trailing_state(ticket=12345, state="activated")
```

---

##### `update_trade_status(ticket: int, status: str)`
Update trade status.

**Parameters**:
- `ticket` (int): Position ticket
- `status` (str): New status ("open", "closed", "stopped_out")

**Example**:
```python
db.update_trade_status(ticket=12345, status="closed")
```

---

##### `get_trade_by_ticket(ticket: int) -> Optional[dict]`
Retrieve trade details by ticket.

**Parameters**:
- `ticket` (int): MT5 position ticket

**Returns**:
- `dict` with trade details (id, signal_id, ticket, symbol, action, volume, entry_price, etc.)
- `None` if not found

**Example**:
```python
trade = db.get_trade_by_ticket(12345)
if trade:
    print(f"Entry: {trade['entry_price']}, Current P&L: {trade['profit']}")
```

---

##### `get_open_trades() -> list[dict]`
Get all open trades from database.

**Parameters**: None

**Returns**: List of open trade dicts

**Example**:
```python
open_trades = db.get_open_trades()
for trade in open_trades:
    print(f"Ticket {trade['ticket']}: {trade['symbol']}")
```

---

## Trade Executor API

### Overview
Orchestrates signal execution and position management.

### Class: `TradeExecutor`

```python
class TradeExecutor:
    def execute_signal(signal: TradingSignal) -> bool
    def execute_order_async(signal: TradingSignal) -> None
```

#### Methods

##### `execute_signal(signal: TradingSignal) -> bool`
Execute trading signal with full workflow.

**Parameters**:
- `signal` (TradingSignal): Signal to execute

**Returns**: `True` if execution started, `False` if rejected

**Workflow**:
1. Validate signal
2. Check confidence threshold
3. Save signal to database
4. Calculate position size
5. Place market order
6. Save trade to database
7. Schedule trailing stop monitoring

**Example**:
```python
executor = TradeExecutor()
if executor.execute_signal(signal):
    print("Signal execution started")
else:
    print("Signal rejected")
```

---

##### `execute_order_async(signal: TradingSignal) -> None`
Async wrapper for order execution.

**Parameters**:
- `signal` (TradingSignal): Signal to execute

**Notes**:
- Runs synchronous execution in thread pool
- Handles exceptions silently with logging

**Example**:
```python
asyncio.create_task(executor.execute_order_async(signal))
```

---

## Trailing Stop Manager API

### Overview
Manages trailing stop loss state machine.

### Class: `TrailingStopManager`

```python
class TrailingStopManager:
    def check_all_positions() -> None
    def _check_position(trade: dict) -> None
    def _activate_trailing_stop(trade: dict) -> None
    def _trail_stop_loss(trade: dict) -> None
```

### State Machine

```
INACTIVE state:
├─ Trigger: TP1 hit OR profit > 1R
├─ Action: Move SL to breakeven + 5 pips
└─ Next state: ACTIVATED

ACTIVATED state:
├─ Trigger: Price retraces 1.5 × ATR
├─ Action: Update SL to new high - 1.5 × ATR
└─ Next state: TRAILING

TRAILING state:
├─ Trigger: Every check cycle
├─ Action: Update SL if new high reached
└─ Next state: TRAILING (continues)
```

#### Methods

##### `check_all_positions() -> None`
Check all open positions for trailing stop updates.

**Parameters**: None

**Returns**: None

**Process**:
1. Get all open trades from database
2. For each trade:
   - Fetch current position from MT5
   - Check activation criteria
   - Update SL if needed
   - Update database state

**Example**:
```python
manager = TrailingStopManager()
manager.check_all_positions()
```

---

## Claude Client API

### Overview
Wrapper for Claude CLI subprocess calls.

### Function: `get_trading_signal(symbol: str, timeframes: list[str], indicators: dict) -> Optional[TradingSignal]`
Get trading signal from Claude AI.

**Parameters**:
- `symbol` (str): Trading symbol (e.g., "XAUUSD")
- `timeframes` (list[str]): Timeframes to analyze (e.g., ["H4", "H1"])
- `indicators` (dict): Current indicator values with timeframe data

**Returns**:
- `TradingSignal`: Parsed and validated signal
- `None`: If Claude call failed or signal invalid

**Process**:
1. Format message with Elliott Wave context
2. Call Claude with retry logic
3. Extract JSON from response
4. Validate signal
5. Return parsed TradingSignal

**Example**:
```python
signal = get_trading_signal(
    symbol="XAUUSD",
    timeframes=["H4", "H1"],
    indicators={
        "H4": {"rsi": 65, "atr": 2.5},
        "H1": {"rsi": 72, "atr": 1.8}
    }
)
if signal and signal.signal.confidence >= 60:
    executor.execute_signal(signal)
```

---

## Telegram Bot API

### Overview
User interface for signal input, position monitoring, and alerts.

### Class: `TradingBot`

```python
class TradingBot(BaseMiddleware):
    async def process_message(message: types.Message) -> None
```

### Commands

#### `/start`
Initialize bot and request authorization.

**Response**:
```
Welcome to MT5 Elliott Wave Bot!
Use /help for commands
```

---

#### `/signal <JSON_DATA>`
Send trading signal.

**Parameters**:
- JSON-formatted signal data

**Payload Structure**:
```json
{
    "action": "BUY",
    "entry_price": 2000.00,
    "stop_loss": 1990.00,
    "take_profit": [
        {"level": "TP1", "price": 2010.00, "close_percent": 25},
        {"level": "TP2", "price": 2020.00, "close_percent": 35},
        {"level": "TP3", "price": 2030.00, "close_percent": 40}
    ],
    "confidence": 85
}
```

**Response**:
- ✅ Signal executed and ticket returned
- ❌ Error message if invalid

**Example**:
```
/signal {"action": "BUY", "entry_price": 2000, "stop_loss": 1990, "take_profit": [...], "confidence": 85}
```

---

#### `/positions`
View all open positions.

**Response**:
```
📊 Open Positions (3):
1. XAUUSD BUY 0.05 lots
   Entry: 2000.00 | Current: 2005.00
   P&L: +$25.00 | State: trailing

2. XAUUSD SELL 0.03 lots
   Entry: 2010.00 | Current: 2008.00
   P&L: +$6.00 | State: inactive
```

---

#### `/trades`
Get recent trades.

**Response**:
```
📈 Last 10 Trades:
1. XAUUSD BUY: 2000.00 → 2015.00 (+0.75R) [Closed]
2. XAUUSD SELL: 2010.00 → 1995.00 (+0.75R) [Closed]
```

---

#### `/balance`
Display account balance.

**Response**:
```
💰 Account Balance:
Balance: $10,000.00
Equity: $10,150.00
Used Margin: $500.00
Free Margin: $9,500.00
```

---

## Error Handling

### Common Error Scenarios

#### MT5 Connection Error
```python
try:
    mt5.initialize()
except Exception as e:
    logger.error(f"MT5 init failed: {e}")
    # Fallback to paper trading mode
```

#### Insufficient Margin
```python
# Position sizing returns minimum (0.01 lots)
size = mt5.calculate_position_size(...)  # Returns 0.01 if margin insufficient
logger.error("Insufficient margin for full position")
```

#### Signal Parsing Failure
```python
try:
    signal = parse_signal(raw_data)
except ValueError as e:
    logger.error(f"Signal validation failed: {e}")
    # Signal is skipped, not executed
```

#### Database Connection
```python
with sqlite3.connect(db_path) as conn:
    # Connection auto-closes on exit
    cursor = conn.execute(query)
```

---

## Constants and Defaults

### Magic Number
```python
MAGIC_NUMBER = 123456  # Order identification
```

### Timeframes
```python
TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
```

### Position States
```python
TRAILING_STATES = ["inactive", "activated", "trailing"]
TRADE_STATUSES = ["open", "closed", "stopped_out"]
SIGNAL_STATUSES = ["pending", "executed", "skipped", "expired"]
```

### Confidence Levels
```python
FULL_POSITION_THRESHOLD = 75    # >= 75% = full size
HALF_POSITION_THRESHOLD = 60    # 60-74% = half size
MIN_CONFIDENCE = 50             # < 50% = skip
```

---

## Data Models Reference

### TradingSignal (Complete)
```python
{
    "timestamp": "2026-01-04T12:00:00Z",
    "symbol": "XAUUSD",
    "signal": {
        "action": "BUY",
        "entry_price": 2000.00,
        "stop_loss": 1990.00,
        "take_profit": [
            {
                "level": "TP1",
                "price": 2010.00,
                "close_percent": 25
            },
            {
                "level": "TP2",
                "price": 2020.00,
                "close_percent": 35
            },
            {
                "level": "TP3",
                "price": 2030.00,
                "close_percent": 40
            }
        ],
        "confidence": 85
    },
    "metadata": {
        "session": "London",
        "spread_check": true,
        "confidence_breakdown": {
            "pattern": 80,
            "confluence": 90,
            "trend": 85
        },
        "timeframe_analysis": "H4 and H1",
        "wave_count": "Wave 5 up"
    },
    "execution_instructions": "Market order only, no limits"
}
```

### Trade Record (Database)
```python
{
    "id": 1,
    "signal_id": 1,
    "ticket": 12345,
    "symbol": "XAUUSD",
    "action": "BUY",
    "volume": 0.05,
    "entry_price": 2000.00,
    "stop_loss": 1990.00,
    "take_profit": 2010.00,
    "open_time": "2026-01-04T12:00:00Z",
    "close_time": null,
    "close_price": null,
    "profit": 25.00,
    "status": "open",
    "trailing_state": "activated"
}
```

---

## Performance Notes

### API Call Frequencies
| Operation | Frequency | Duration |
|-----------|-----------|----------|
| fetch_ohlcv | Per analysis | 50-100ms |
| place_market_order | Per signal | 100-500ms |
| get_positions | Per check cycle | 20-50ms |
| Database insert | Per trade | 5-20ms |
| Telegram message | Per event | <500ms |

### Rate Limits
- MT5 order calls: ~2 per second (broker dependent)
- Database: SQLite single-writer
- Claude API: Standard tier limits
- Telegram: 30 messages/second

---

## Changelog

### Phase 5 Additions (2026-01-04)
- Trade execution with SL/TP
- Position sizing with confidence multiplier
- Trailing stop state machine
- Database schema with trade tracking
- Paper trading mode

### Phase 4 (Previous)
- Telegram bot
- Signal notifications

### Phase 3 (Previous)
- Claude integration
- Signal parsing

---

## Dashboard API (Phase 8)

### Overview
RESTful API for the MT5 Trading Dashboard - provides read-only access to trading data for analytics and visualization. Built with FastAPI, deployed in Docker containers.

**Base URL**: `http://localhost:8000/api`

### Authentication
None required (local use only)

### Rate Limiting
- 60 requests per minute per IP address
- Returns HTTP 429 when limit exceeded

### Endpoints

#### `GET /stats`
Get overall performance statistics

**Response**:
```json
{
  "total_trades": 150,
  "win_rate": 55.3,
  "total_pnl": 2450.75,
  "wins": 83,
  "losses": 67,
  "profit_factor": 1.85,
  "avg_win": 45.2,
  "avg_loss": -32.8,
  "consecutive_wins": 5,
  "consecutive_losses": 2,
  "max_drawdown": -520.0,
  "sharpe_ratio": 1.42
}
```

---

#### `GET /trades`
Get paginated trade history

**Query Parameters**:
- `limit` (int, default: 50): Number of trades to return
- `offset` (int, default: 0): Pagination offset
- `status` (str, optional): Filter by status ("open", "closed", "partial")
- `symbol` (str, optional): Filter by trading symbol

**Response**:
```json
[
  {
    "id": 1,
    "symbol": "XAUUSD",
    "entry_price": 2050.45,
    "exit_price": 2055.30,
    "volume": 0.5,
    "profit": 24.25,
    "open_time": "2025-01-04T10:30:00",
    "close_time": "2025-01-04T11:45:00",
    "status": "closed",
    "signal_confidence": 72.5,
    "signal_action": "BUY"
  }
]
```

---

#### `GET /equity`
Get equity curve data points

**Response**:
```json
[
  {
    "time": "2025-01-01T00:00:00",
    "equity": 0.0
  },
  {
    "time": "2025-01-01T10:30:00",
    "equity": 120.50
  },
  {
    "time": "2025-01-01T11:45:00",
    "equity": 144.75
  }
]
```

---

#### `GET /daily-pnl`
Get daily P&L summary

**Response**:
```json
[
  {
    "date": "2025-01-01",
    "pnl": 245.30,
    "trades_count": 8,
    "win_rate": 62.5
  },
  {
    "date": "2025-01-02",
    "pnl": -85.20,
    "trades_count": 5,
    "win_rate": 40.0
  }
]
```

---

#### `GET /confidence-analysis`
Analyze signal confidence vs actual outcome

**Response**:
```json
[
  {
    "confidence_band": "High (75-100)",
    "total": 45,
    "wins": 32,
    "win_rate": 71.1,
    "avg_profit": 52.3
  },
  {
    "confidence_band": "Medium (60-74)",
    "total": 62,
    "wins": 33,
    "win_rate": 53.2,
    "avg_profit": 28.5
  },
  {
    "confidence_band": "Low (45-59)",
    "total": 43,
    "wins": 18,
    "win_rate": 41.9,
    "avg_profit": 12.1
  }
]
```

---

#### `GET /time-analysis`
Performance by hour of day and day of week

**Response**:
```json
{
  "by_hour": {
    "0": {"trades": 8, "win_rate": 50.0, "avg_profit": 15.2},
    "1": {"trades": 12, "win_rate": 58.3, "avg_profit": 22.5},
    ...
    "23": {"trades": 10, "win_rate": 55.0, "avg_profit": 18.8}
  },
  "by_weekday": {
    "Monday": {"trades": 22, "win_rate": 54.5, "avg_profit": 28.3},
    "Tuesday": {"trades": 25, "win_rate": 56.0, "avg_profit": 31.2},
    ...
    "Friday": {"trades": 28, "win_rate": 58.9, "avg_profit": 35.1}
  }
}
```

---

#### `GET /positions`
Get current open positions

**Response**:
```json
[
  {
    "ticket": 12345,
    "symbol": "XAUUSD",
    "type": "BUY",
    "volume": 0.5,
    "entry_price": 2050.45,
    "current_price": 2053.20,
    "profit": 13.75,
    "stop_loss": 2045.00,
    "take_profit": 2065.00,
    "open_time": "2025-01-04T10:30:00"
  }
]
```

---

#### `GET /signals`
Get signal history with outcomes

**Response**:
```json
[
  {
    "id": 42,
    "timestamp": "2025-01-04T10:15:00",
    "action": "BUY",
    "symbol": "XAUUSD",
    "confidence": 78.5,
    "reasoning": "Elliott wave count suggests uptrend continuation",
    "trade_id": 1,
    "trade_outcome": "WIN",
    "trade_profit": 24.25
  }
]
```

---

#### `GET /health`
Health check endpoint

**Response**:
```json
{
  "status": "ok",
  "database": "connected",
  "timestamp": "2025-01-04T15:30:00"
}
```

---

### Error Responses

**400 Bad Request**
```json
{
  "detail": "Invalid query parameters"
}
```

**429 Too Many Requests**
```json
{
  "detail": "Rate limit exceeded"
}
```

**500 Internal Server Error**
```json
{
  "detail": "Internal server error"
}
```

---

### Implementation Details

#### FastAPI Configuration
- Framework: FastAPI 0.104+
- Server: Uvicorn
- Rate Limiter: slowapi
- CORS: Configured for localhost:3000 (React frontend)

#### Database
- Type: SQLite (read-only)
- Path: `/data/trading.db`
- Connection Mode: URI with read-only flag
- Transaction Isolation: WAL (Write-Ahead Logging)

#### Performance
- Response times: < 100ms for most endpoints
- Max pagination limit: 500 trades
- Auto-refresh recommended: 30 seconds
- Database queries optimized with indexes

---

### Frontend Integration

The React dashboard (`localhost:3000`) consumes these endpoints via Axios:

```typescript
const api = axios.create({
  baseURL: '/api',
  timeout: 5000,
})

// Example: Fetch stats with React Query
const { data: stats } = useQuery({
  queryKey: ['stats'],
  queryFn: () => api.get('/stats').then(res => res.data),
  refetchInterval: 30000, // 30 second auto-refresh
})
```

---

### Components Using Each Endpoint

| Component | Endpoint |
|-----------|----------|
| StatsCards | `/stats` |
| EquityCurve | `/equity` |
| DailyPnLChart | `/daily-pnl` |
| ConfidenceChart | `/confidence-analysis` |
| TimeHeatmap | `/time-analysis` |
| OpenPositions | `/positions` |
| TradesTable | `/trades` |

---

### Deployment

#### Docker Compose
```bash
cd dashboard
docker-compose up -d --build
```

#### Environment Variables
- `API_PORT`: Backend port (default: 8000)
- `WEB_PORT`: Frontend port (default: 3000)
- `DB_PATH`: Path to trading database
- `CORS_ORIGINS`: Comma-separated CORS origins

---

**Last Updated**: 2026-01-04
**API Version**: 1.0
**Status**: Production Ready (Phase 8)
