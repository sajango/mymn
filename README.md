# MT5 Elliott Wave Auto-Trading System

An automated trading system for MetaTrader 5 that uses Elliott Wave analysis to identify trading opportunities on gold (XAUUSD) with Telegram notifications and paper trading support.

**Current Status**: Phase 5 Complete ✓ (Trade Execution)

## Quick Start

1. **Setup Environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Settings**
   ```bash
   cp .env.example .env
   # Edit .env with your MT5 path, Telegram credentials, and trading parameters
   ```

3. **Run Tests**
   ```bash
   pytest tests/
   ```

## Project Structure

```
src/
  __init__.py              # Package initialization
  config.py               # Settings management (Pydantic)
  mt5_client.py           # MT5 client & indicator calculations
  signal_parser.py        # Trading signal models & parsing
  claude_client.py        # Claude CLI wrapper
  database.py             # SQLite trade persistence (NEW Phase 5)
  trade_executor.py       # Signal execution coordinator (NEW Phase 5)
  trailing_stop_manager.py # Trailing stop state machine (NEW Phase 5)
  telegram_bot.py         # Telegram bot interface (Phase 4)

tests/
  __init__.py             # Test package initialization
  test_config.py          # Configuration tests
  test_mt5.py             # MT5 client & indicator tests
  test_signal_parser.py   # Signal parsing & validation tests
  test_claude_client.py   # Claude client & CLI integration tests
  test_database.py        # Database CRUD tests (NEW Phase 5, 16 tests)
  test_trade_executor.py  # Execution workflow tests (NEW Phase 5, 13 tests)
  test_trailing_stop.py   # State machine tests (NEW Phase 5, 16 tests)
  test_telegram.py        # Bot command tests (Phase 4)

docs/                     # Comprehensive documentation (NEW Phase 5)
  codebase-summary.md     # Architecture overview
  api-documentation.md    # API reference
  system-architecture.md  # Technical design
  project-overview-pdr.md # Requirements & planning

data/                  # Trade data and CSV exports
logs/                  # Application logs
plans/                 # Development phase plans and reviews
```

## Phase 1: Foundation (Complete)

- ✓ Configuration system using Pydantic Settings
- ✓ Environment variable management (.env support)
- ✓ Risk management parameters
- ✓ Trading session confidence adjustments
- ✓ News filter and spread settings
- ✓ Logging infrastructure
- ✓ Database path configuration
- ✓ Unit tests for configuration

## Phase 2: MT5 Data Export (Complete)

- ✓ MT5 client with connection management
- ✓ OHLCV data fetching from MT5 (H4, H1, M30, M15)
- ✓ Technical indicators: RSI, EMA, MACD, ATR
- ✓ CSV export with indicators for all timeframes
- ✓ Symbol validation and spread monitoring
- ✓ Comprehensive indicator tests (16+ test cases)
- ✓ Graceful MT5 initialization with retry logic

## Phase 3: Claude Code CLI Integration (Complete)

- ✓ Claude CLI subprocess wrapper (claude_client.py)
- ✓ Comprehensive Pydantic models for trading signals (signal_parser.py)
- ✓ JSON extraction from Claude responses (3 fallback strategies)
- ✓ Signal parsing and validation with 30+ fields
- ✓ Session context, spread checks, trailing stops, confidence breakdown
- ✓ Execution instructions and metadata tracking
- ✓ Retry logic with exponential backoff
- ✓ Path validation and security checks
- ✓ 46 test cases for signal parsing + 24 tests for Claude client (70 total)

## Phase 4: Telegram Bot & Signal Notifications (Complete)

- ✓ Telegram bot with aiogram 3.x
- ✓ /start, /signal, /positions, /trades, /balance commands
- ✓ Real-time trade notifications
- ✓ Authorization checks (chat_id validation)
- ✓ Order confirmation messages
- ✓ Position monitoring alerts
- ✓ Account balance queries
- ✓ User-friendly formatting
- ✓ Complete integration with executor

## Phase 5: Trade Execution & Risk Management (Complete)

- ✓ Market order placement (BUY/SELL) via MT5
- ✓ Dynamic position sizing with risk percentage
- ✓ Confidence-based position multipliers (75%+ = full, 60-74% = half)
- ✓ Stop loss and take profit placement
- ✓ Partial position closing at TP levels
- ✓ Position SL/TP modification
- ✓ SQLite database for trade persistence
- ✓ **NEW**: Trailing stop state machine (inactive → activated → trailing)
- ✓ **NEW**: Trailing stop activation (TP1 hit OR profit > 1R)
- ✓ **NEW**: Breakeven + buffer logic (5 pips)
- ✓ **NEW**: ATR-based trail distance (1.5x ATR)
- ✓ **NEW**: Paper trading mode (default safe)
- ✓ **NEW**: Magic number for order identification
- ✓ **NEW**: Complete trade schema with trailing_state tracking
- ✓ 45 comprehensive unit tests (database: 16, executor: 13, trailing: 16)
- ✓ Test coverage: 84-96% across modules
- ✓ Code review: A- (Excellent with 5 non-blocking findings)

## Key Features

- **Configurable Risk Management**: Risk percentage, max position size, stop loss management
- **Session-Based Confidence**: Automatic confidence adjustments for London, NY, and Asian sessions
- **News Filtering**: Blackout periods before and after high-impact news
- **Spread Management**: Maximum spread thresholds for trade entry
- **Paper Trading Support**: Safe testing mode before live trading
- **Telegram Notifications**: Trade signals and alerts via Telegram bot

## Configuration Parameters

All settings are loaded from `.env` file. Key categories:

- **Core**: Bot token, MT5 path, trading symbol, position sizes
- **Slippage**: Max slippage tolerance and expectations
- **Sessions**: Confidence adjustments for market sessions
- **Spread**: Maximum spread to enter trades
- **Trailing Stop**: ATR-based stop loss management
- **News Filter**: Blackout periods for high-impact news
- **Thresholds**: Confidence levels for full/half positions
- **Logging**: Log level and file paths

## Development

See `plans/` directory for detailed phase implementations and code reviews.

## Next Phases

- Phase 6: System Orchestration (APScheduler, background workers, error recovery)
- Phase 6.5: News Integration (Economic calendar, blackout periods)
- Phase 7: Comprehensive Testing Framework (Backtesting engine, performance metrics)
- Phase 8: Web Dashboard (FastAPI + React, real-time monitoring)
- Phase 9: Advanced Analytics (Trade statistics, optimization, reporting)

## Environment Setup

```bash
# Required for .env file to work
python-dotenv>=1.0.0
pydantic>=2.0.0
pydantic-settings>=2.0.0

# See requirements.txt for full dependency list
```

## License

This project is part of the MT5 Elliott Wave Auto-Trading System.
