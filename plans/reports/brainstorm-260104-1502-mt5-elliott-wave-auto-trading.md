# Elliott Wave Auto-Trading System - Brainstorm Report

**Date**: 2026-01-04
**Status**: Architecture Approved
**Stakeholder**: User (Experienced EW Trader)

---

## 1. Problem Statement

Build semi-automated trading system for XAUUSD that:
- Connects to MT5 (Windows local)
- Exports price data to CSV (H4, H1, M30, M15)
- Uses Claude Opus via CLI to analyze Elliott Wave patterns
- Generates trading signals with entry/SL/TP
- Sends notifications via Telegram for user confirmation
- Executes trades automatically upon confirmation

---

## 2. Requirements Summary

| Requirement | Decision |
|-------------|----------|
| Automation Level | Semi-Auto (signal → confirm → execute) |
| AI Interface | Claude Code CLI (Max subscription) |
| Model | Opus only |
| Notification | Telegram with inline buttons |
| Analysis Frequency | Every M15 close (~96/day) |
| MT5 Platform | Windows local |
| Budget | $500+/month |
| User Experience | Experienced EW trader |

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                      WINDOWS LOCAL MACHINE                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  MT5 Terminal ──▶ Python Orchestrator ──▶ Claude Code (SDK)         │
│       │                   │                      │                   │
│       │                   ▼                      ▼                   │
│       │           ┌─────────────┐        ┌─────────────┐            │
│       │           │  Scheduler  │        │  Analyzer   │            │
│       │           │  (M15 cron) │        │ (EW Logic)  │            │
│       │           └─────────────┘        └─────────────┘            │
│       │                   │                      │                   │
│       ▼                   ▼                      ▼                   │
│  ┌─────────┐      ┌─────────────┐        ┌─────────────┐            │
│  │   CSV   │ ───▶ │   Parser    │ ◀───── │   Signal    │            │
│  │  Files  │      │   (JSON)    │        │   Output    │            │
│  └─────────┘      └─────────────┘        └─────────────┘            │
│                          │                                          │
│                          ▼                                          │
│                  ┌─────────────┐                                    │
│                  │  Telegram   │ ──────▶ User Phone                 │
│                  │    Bot      │ ◀────── User Response              │
│                  └─────────────┘                                    │
│                          │                                          │
│                          ▼                                          │
│                  ┌─────────────┐        ┌─────────────┐            │
│                  │  Executor   │ ──────▶│   Logger    │            │
│                  │  (MT5 API)  │        │  (SQLite)   │            │
│                  └─────────────┘        └─────────────┘            │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Component Specifications

### 4.1 MT5 Data Exporter
- **Library**: MetaTrader5 (official Python package)
- **Output**: 4 CSV files per analysis
  - `xauusd_h4.csv` (200 candles)
  - `xauusd_h1.csv` (200 candles)
  - `xauusd_m30.csv` (200 candles)
  - `xauusd_m15.csv` (200 candles)
- **Columns**: timestamp, OHLC, tick_volume, RSI, EMA34, EMA89, MACD, ATR

### 4.2 Claude Code Integration
- **Method**: Claude Code SDK (not raw CLI subprocess)
- **Subscription**: Claude Max ($200/mo)
- **Model**: Opus only
- **Input**: instructions.md + 4 CSV files
- **Output**: Structured JSON signal

### 4.3 Signal Parser
- **Validation**: Pydantic models for schema enforcement
- **Fallback**: Retry with clarification prompt if invalid JSON
- **Error Handling**: Log and alert on parse failures

### 4.4 Telegram Bot
- **Library**: python-telegram-bot v20+
- **Features**:
  - Rich signal formatting with all parameters
  - Inline keyboard buttons (Execute/Skip/Modify)
  - Confirmation timeout (5 minutes default)
  - Position modification interface

### 4.5 Trade Executor
- **Library**: MetaTrader5 (order_send)
- **Features**:
  - Multiple TP levels with partial close
  - ATR-based stop loss option
  - Position sizing based on risk %
  - Slippage protection

### 4.6 Logging System
- **Database**: SQLite (local, simple)
- **Tables**:
  - `signals`: All generated signals
  - `confirmations`: User responses
  - `trades`: Executed orders
  - `performance`: P&L tracking

---

## 5. Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Runtime | Python | 3.11+ |
| MT5 Integration | MetaTrader5 | Latest |
| AI Interface | claude-code-sdk | Latest |
| Scheduling | APScheduler | 3.10+ |
| Telegram | python-telegram-bot | 20+ |
| Validation | Pydantic | 2.0+ |
| Database | SQLite3 | Built-in |
| Config | python-dotenv | Latest |

---

## 6. Project Structure

```
mymn/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── config.py               # Settings & environment
│   │
│   ├── mt5/
│   │   ├── __init__.py
│   │   ├── connector.py        # MT5 connection management
│   │   ├── exporter.py         # CSV data export
│   │   ├── executor.py         # Trade execution
│   │   └── models.py           # MT5 data types
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── claude_client.py    # Claude Code SDK wrapper
│   │   ├── signal_parser.py    # JSON response parsing
│   │   └── prompts.py          # Prompt management
│   │
│   ├── telegram/
│   │   ├── __init__.py
│   │   ├── bot.py              # Bot initialization
│   │   ├── handlers.py         # Command & callback handlers
│   │   └── formatters.py       # Message formatting
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── jobs.py             # Scheduled analysis jobs
│   │
│   └── storage/
│       ├── __init__.py
│       ├── database.py         # SQLite operations
│       └── models.py           # DB schemas
│
├── config/
│   ├── settings.yaml           # App configuration
│   └── logging.yaml            # Logging configuration
│
├── data/
│   └── csv/                    # Exported CSV files
│
├── logs/                       # Application logs
│
├── tests/
│   ├── test_mt5.py
│   ├── test_ai.py
│   └── test_telegram.py
│
├── instructions.md             # Elliott Wave analysis prompt
├── requirements.txt
├── .env.example
└── README.md
```

---

## 7. Data Flow

### 7.1 Analysis Cycle (Every M15)

```
1. Scheduler triggers at M15 close
        ↓
2. MT5 Connector exports 4 CSV files
        ↓
3. Claude Client sends to Claude Code:
   - System: instructions.md
   - User: "Analyze these CSV files and output JSON signal"
   - Attachments: 4 CSV files
        ↓
4. Signal Parser validates JSON response
        ↓
5. If valid signal (confidence ≥ 60%):
   - Format Telegram message
   - Send with inline buttons
        ↓
6. User receives notification on phone
        ↓
7. User taps [Execute] / [Skip] / [Modify]
        ↓
8. If Execute:
   - MT5 Executor places order
   - Logger records trade
        ↓
9. Cycle completes, wait for next M15
```

### 7.2 Signal JSON Schema

```json
{
  "timestamp": "2026-01-04T15:00:00Z",
  "symbol": "XAUUSD",
  "signal": {
    "action": "BUY|SELL|NO_TRADE",
    "entry_price": 3340.00,
    "stop_loss": 3310.00,
    "stop_loss_atr": 3312.50,
    "take_profit": [
      {"level": "TP1", "price": 3380.00, "close_percent": 50},
      {"level": "TP2", "price": 3420.00, "close_percent": 30},
      {"level": "TP3", "price": 3450.00, "close_percent": 20}
    ],
    "risk_reward": 2.67,
    "confidence": 78
  },
  "wave_analysis": {
    "h4_trend": "bullish|bearish",
    "current_wave": "wave_4_complete",
    "primary_scenario": {
      "description": "Wave 5 targeting 3450",
      "probability": 70
    },
    "invalidation_price": 3310.00
  },
  "indicators": {
    "rsi": {"value": 42.5, "zone": "neutral"},
    "ema": {"trend_alignment": "bullish"},
    "macd": {"momentum": "recovering"},
    "atr": {"value": 13.75, "regime": "normal"}
  }
}
```

---

## 8. Risk Management

### 8.1 Technical Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Claude rate limit | Medium | High | Queue signals, reduce frequency adaptively |
| Invalid JSON output | Low | Medium | Retry with structured prompt, fallback to NO_TRADE |
| MT5 disconnection | Low | High | Auto-reconnect, alert user, pause trading |
| Telegram delivery failure | Low | Medium | Retry 3x, log for manual review |
| Parse errors | Low | Medium | Strict Pydantic validation, reject invalid signals |

### 8.2 Trading Risks & Safeguards

| Safeguard | Implementation |
|-----------|---------------|
| Paper trading first | 2-4 weeks minimum before live |
| Max position size | Configurable hard limit (e.g., 0.1 lot) |
| Daily loss limit | Auto-stop if daily loss > X% of equity |
| Circuit breaker | Stop after N consecutive losses |
| Confidence threshold | Only notify if confidence ≥ 60% |
| Confirmation timeout | Auto-expire signals after 5 minutes |
| Human confirmation | Required for all trades (semi-auto) |

---

## 9. Cost Analysis

### 9.1 Monthly Costs

| Item | Cost |
|------|------|
| Claude Max subscription | $200/mo |
| VPS (optional, 24/7 operation) | $20-50/mo |
| Telegram (free tier) | $0 |
| MT5 (broker provided) | $0 |
| **Total** | **$200-250/mo** |

### 9.2 Comparison with API Approach

| Approach | Cost/mo | Pros | Cons |
|----------|---------|------|------|
| Claude Max (CLI) | $200 | Fixed cost, interactive | Usage caps, parse complexity |
| Claude API | $900+ | Structured JSON, reliable | High variable cost |
| Hybrid | $200-400 | Best of both | Complex implementation |

**Recommendation**: Start with Claude Max, monitor usage caps, add API fallback if needed.

---

## 10. Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Set up project structure
- [ ] MT5 connection & CSV export
- [ ] Claude Code SDK integration
- [ ] Basic JSON parsing
- [ ] Local testing with sample data

### Phase 2: Notification (Week 3)
- [ ] Telegram bot setup
- [ ] Signal message formatting
- [ ] Inline keyboard buttons
- [ ] Callback handling

### Phase 3: Execution (Week 4)
- [ ] MT5 order execution
- [ ] Position sizing logic
- [ ] Multi-TP management
- [ ] Error handling

### Phase 4: Automation (Week 5)
- [ ] APScheduler integration
- [ ] M15 trigger setup
- [ ] Rate limit handling
- [ ] Logging & monitoring

### Phase 5: Paper Trading (Week 6-9)
- [ ] Paper trading mode
- [ ] Performance tracking
- [ ] Signal accuracy validation
- [ ] System tuning

### Phase 6: Live Trading (Week 10+)
- [ ] Small position sizes initially
- [ ] Gradual scale-up
- [ ] Continuous monitoring
- [ ] Performance optimization

---

## 11. Success Metrics

### 11.1 Technical Metrics
- System uptime: > 99%
- Signal delivery latency: < 30 seconds
- Parse success rate: > 95%
- Execution success rate: > 99%

### 11.2 Trading Metrics
- Signal accuracy (paper trading): > 60%
- Risk-reward achieved: > 1.5:1
- Maximum drawdown: < 10%
- Win rate: > 50%

---

## 12. Open Questions

1. **Claude Code SDK availability**: Need to verify SDK supports headless automation with Claude Max
2. **Rate limit specifics**: Exact caps for Claude Max with Opus model
3. **MT5 broker compatibility**: Verify MetaTrader5 Python lib works with user's broker
4. **Timezone handling**: User's trading hours vs market sessions

---

## 13. Next Steps

1. ✅ Architecture approved
2. ⏳ Create detailed implementation plan
3. ⏳ Set up development environment
4. ⏳ Begin Phase 1 implementation

---

## 14. References

- [instructions.md](../instructions.md) - Elliott Wave analysis system prompt
- [MetaTrader5 Python](https://pypi.org/project/MetaTrader5/)
- [Claude Code SDK](https://docs.anthropic.com/en/docs/claude-code)
- [python-telegram-bot](https://python-telegram-bot.org/)

---

*Report generated by Claude Code Brainstorming Session*
