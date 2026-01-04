# MT5 Elliott Wave Auto-Trading System

An automated trading system for MetaTrader 5 that uses Elliott Wave analysis to identify trading opportunities on gold (XAUUSD) with Telegram notifications and paper trading support.

**Current Status**: Phase 3 Complete ✓ (Claude Integration)

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
  __init__.py          # Package initialization
  config.py            # Settings management (Pydantic)
  mt5_client.py        # MT5 client & indicator calculations
  signal_parser.py     # Trading signal models & parsing
  claude_client.py     # Claude CLI wrapper

tests/
  __init__.py          # Test package initialization
  test_config.py       # Configuration tests
  test_mt5.py          # MT5 client & indicator tests
  test_signal_parser.py # Signal parsing & validation tests
  test_claude_client.py # Claude client & CLI integration tests

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

- Phase 4: Telegram Bot & Signal Notifications
- Phase 5: Trade Execution & Risk Management
- Phase 6: System Orchestration
- Phase 7: Backtesting & Analytics
- Phase 8: Web Dashboard & Reporting

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
