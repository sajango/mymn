# Phase 1: Project Setup

## Context Links
- [Plan Overview](./plan.md)
- [Brainstorm Report](../reports/brainstorm-260104-1502-mt5-elliott-wave-auto-trading.md)

## Overview
- **Priority**: P1
- **Status**: ✅ Complete (with minor improvements recommended)
- **Review**: [Code Review Report](../reports/code-reviewer-260104-1644-phase01-setup.md)
- **Effort**: 2h (actual: 1.5h)
- **Description**: Initialize project structure, dependencies, and configuration

## Key Insights
- Greenfield project - no existing codebase
- Flattened structure for simplicity (KISS)
- Use python-dotenv for env management
- SQLite for simple persistence
- Claude Code CLI via subprocess (no anthropic package needed)

## Requirements

### Functional
- Project directory structure
- Virtual environment with all dependencies
- Environment variable management
- Basic logging configuration

### Non-Functional
- Python 3.11+ compatibility
- Windows-compatible paths
- Clean separation of config from code

## Architecture

### Project Structure
mymn/
  src/
    __init__.py
    main.py              # Entry point
    config.py            # Settings
    mt5_client.py        # MT5 operations
    claude_client.py     # Claude CLI wrapper
    signal_parser.py     # Pydantic models
    telegram_bot.py      # Telegram bot
    scheduler.py         # APScheduler
    database.py          # SQLite
  data/
    csv/                  # CSV exports
  logs/                   # Logs
  tests/
  instructions.md         # Exists
  requirements.txt

## Related Code Files

### Files to Create
- src/__init__.py - Package init
- src/config.py - Configuration management
- requirements.txt - Dependencies
- dotenv example file - Environment template

## Implementation Steps

1. **Create directory structure**

2. **Create requirements.txt**
   python-dotenv>=1.0.0
   pydantic>=2.0.0
   MetaTrader5>=5.0.45
   pandas>=2.0.0
   numpy>=1.24.0
   python-telegram-bot[job-queue]>=20.0
   APScheduler>=3.10.0
   pytest>=7.0.0
   pytest-asyncio>=0.21.0

   NOTE: Claude Code CLI - No Python package needed (uses subprocess)

3. **Create environment template with these vars:**

   **Core Settings:**
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_CHAT_ID
   - MT5_PATH
   - MT5_SYMBOL=XAUUSD
   - RISK_PERCENT=1.5
   - MAX_POSITION_SIZE=0.1
   - PAPER_TRADING=true
   - CLAUDE_TIMEOUT=300
   - MAX_SLIPPAGE=20

   **Session Configuration (NEW):**
   - SESSION_CONFIDENCE_OVERLAP=10
   - SESSION_CONFIDENCE_LONDON=5
   - SESSION_CONFIDENCE_NY=5
   - SESSION_CONFIDENCE_ASIAN=-15
   - SESSION_CONFIDENCE_OFFHOURS=-20

   **Spread & Slippage (NEW):**
   - MAX_SPREAD_PIPS=4.0
   - EXPECTED_SLIPPAGE_PIPS=1.0

   **Trailing Stop (NEW):**
   - TRAIL_ATR_MULTIPLIER=1.5
   - BREAKEVEN_BUFFER_PIPS=5

   **News Filter (NEW):**
   - NEWS_BLACKOUT_BEFORE_MINS=30
   - NEWS_BLACKOUT_AFTER_MINS=15

   **Confidence Thresholds (NEW):**
   - CONFIDENCE_THRESHOLD=60
   - CONFIDENCE_FULL_POSITION=75
   - CONFIDENCE_HALF_POSITION=60

4. **Create src/config.py** with Pydantic BaseModel

5. **Create virtual environment and install**

## Todo List

- [x] Create directory structure
- [x] Write requirements.txt (no anthropic package)
- [x] Write environment template
- [x] Write src/config.py
- [x] Create virtual environment
- [x] Install dependencies
- [ ] Verify Claude CLI is installed (run: claude --version)

## Success Criteria

- [x] All directories exist
- [x] pip install succeeds
- [x] Config imports work
- [ ] claude --version returns valid version

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Python version mismatch | Low | Medium | Specify 3.11+ in docs |
| Package conflicts | Low | Low | Use fresh venv |
| Claude CLI not installed | Low | High | Check on startup |

## Security Considerations

- Environment file excluded from git
- No API keys needed (CLI handles auth)

## Next Steps

-> [Phase 2: MT5 Data Export](./phase-02-mt5-data-export.md)
