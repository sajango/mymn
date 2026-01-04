# MT5 Elliott Wave Auto-Trading System

An automated trading system for MetaTrader 5 that uses Elliott Wave analysis to identify trading opportunities on gold (XAUUSD) with Telegram notifications and paper trading support.

**Current Status**: Phase 1 Complete ✓

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

tests/
  __init__.py          # Test package initialization
  test_config.py       # Configuration tests

data/                  # Trade data and CSV exports
logs/                  # Application logs
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

See `/docs/PHASE_1.md` for detailed implementation notes.

## Next Phases

- Phase 2: MT5 Integration & Data Collection
- Phase 3: Elliott Wave Pattern Recognition
- Phase 4: Signal Generation Engine
- Phase 5: Risk Management & Order Execution
- Phase 6: Telegram Bot & Notifications
- Phase 7: Performance Monitoring & Optimization
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
