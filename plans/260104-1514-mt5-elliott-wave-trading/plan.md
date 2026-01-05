---
title: "MT5 Elliott Wave Auto-Trading System"
description: "Semi-automated XAUUSD trading using Claude AI for wave analysis with Telegram notifications"
status: in-progress
priority: P1
effort: 41h
branch: main
tags: [trading, automation, ai, mt5, telegram]
created: 2026-01-04
updated: 2026-01-05
completed_phases: 9
phase_7_completed: 2026-01-04
phase_8_completed: 2026-01-04
phase_9_completed: 2026-01-05
---

# MT5 Elliott Wave Auto-Trading System

## Overview

Build semi-automated trading system for XAUUSD:
- Connect to MT5 (Windows local)
- Export price data to CSV (H4, H1, M30, M15)
- Use Claude Code CLI for Elliott Wave analysis (subprocess)
- Generate trading signals with entry/SL/TP
- Send notifications via Telegram with inline buttons
- Execute trades upon user confirmation
- Auto partial close at TP levels with monitoring job

## Architecture

```
APScheduler (M15 cron)
        |
News Calendar Check ←── ForexFactory Scraper
        |
[Blackout?] ─── Yes ──→ Skip (log only)
        |
        No
        ↓
Session Detection (UTC-based)
        |
MT5 Data Export (sync via executor)
        |
Spread Check ←── MT5 API
        |
[Spread OK?] ─── No ──→ Skip (log only)
        |
        Yes
        ↓
Claude Code CLI (subprocess --print)
        |
Signal Parser (enhanced Pydantic)
        |
[Confidence >= 60?] ─── No ──→ Silent Skip (log only)
        |
        Yes
        ↓
Position Sizing (confidence-adjusted)
        |
Telegram Notification (async, inline buttons)
        |
User Response (Execute/Skip/Modify)
        |
MT5 Trade Execution (sync via executor)
        |
Trailing Stop Monitor (enhanced) ←── 30s interval
        |
SQLite Logger
        |
Backtest Analytics
```

## Phases

| # | Phase | Status | Effort | Link | Notes |
|---|-------|--------|--------|------|-------|
| 1 | Project Setup | Done | 2h | [phase-01](./phase-01-project-setup.md) | +env vars |
| 2 | MT5 Data Export | Done | 3h | [phase-02](./phase-02-mt5-data-export.md) | All 4 timeframes export OK |
| 3 | Claude AI Integration | Done | **5h** | [phase-03](./phase-03-claude-integration.md) | +enhanced parsing (2026-01-04) |
| 4 | Telegram Bot | Done | 4h | [phase-04](./phase-04-telegram-bot.md) | Completed 2026-01-04 |
| 5 | Trade Execution | Done | **5h** | [phase-05](./phase-05-trade-execution.md) | +trailing stop |
| 6 | Orchestration | Done | **5h** | [phase-06](./phase-06-orchestration.md) | +session/spread (2026-01-04) |
| 6.5 | **News Integration** | Done | **3h** | [phase-06.5](./phase-06.5-news-integration.md) | Completed 2026-01-04 |
| 7 | Testing & Paper Trading | Done | 4h | [phase-07](./phase-07-testing.md) | **Completed 2026-01-04**: 281 tests passing, 66% coverage |
| 8 | Web Dashboard | Done | 6h | [phase-08](./phase-08-web-dashboard.md) | Completed 2026-01-04: 8 API endpoints, 7 React components, Docker multi-stage, security hardened |
| 8.5 | **Dashboard Hardening** | **Recommended** | **2h** | TBD | Rate limiting, security headers, env config, tests |
| 9 | **Backtest Analytics** | Done | **4h** | [phase-09](./phase-09-backtest-analytics.md) | Completed 2026-01-05: AnalyticsEngine, WeeklyReportGenerator, 27/27 tests passing, 93-100% coverage |

## Dependencies

- Python 3.11+
- MetaTrader 5 (Windows)
- Claude Code CLI (installed and authenticated)
- Telegram Bot token

## Key Files

- [instructions_v2.md](../../instructions_v2.md) - Elliott Wave analysis prompt (enhanced)
- [Brainstorm Report](../reports/brainstorm-260104-1502-mt5-elliott-wave-auto-trading.md)
- [Plan Update Report](../reports/brainstorm-260104-1604-instructions-v2-plan-update.md)

## Research Reports

- [Claude SDK Research](./research/researcher-01-claude-sdk.md)
- [MT5 Python Research](./research/researcher-02-mt5-python.md)
- [Telegram/APScheduler Research](./research/researcher-03-telegram-apscheduler.md)

## Cost Estimate

- Claude Code CLI: Included with Claude Max subscription
- No per-token API costs

## Validation Summary

**Validated**: 2026-01-04
**Questions asked**: 12 (6 initial + 6 follow-up)

### Confirmed Decisions

| Decision | User Choice |
|----------|-------------|
| **Claude Integration** | Claude Code CLI (subprocess) - NOT API |
| **Model** | Opus only |
| **TP Management** | Auto partial close with monitoring job |
| **TP Monitor** | Separate job, check every 30s |
| **Symbol** | Configurable via env (MT5_SYMBOL), default XAUUSD |
| **Parse Failure** | Retry once, then NO_TRADE signal |
| **TP Monitor Disconnect** | Retry 3x with reconnect, alert on final failure |
| **Go-Live Gate** | Enforce minimum 2 weeks paper trading |
| **Market Hours** | Skip analysis during market close (detect via MT5 tick) |
| **Slippage** | Configurable via env (MAX_SLIPPAGE), default 20 |
| **Dashboard Framework** | FastAPI + React (separate process) |
| **Dashboard Metrics** | Full analytics (equity curve, daily P&L, confidence analysis) |
| **Dashboard Deployment** | Docker Compose (API + Web containers) |
| **News Integration** | External API (ForexFactory scraping) |
| **Low Confidence (<60%)** | Silent skip (no trade, no notify, log only) |
| **Backtest Tracking** | New Phase 9 (separate phase) |
| **Trailing Stop** | Custom implementation in monitoring job |
| **Extended Timeline** | Accept (29h → 41h) |

### Action Items (Previous)
- [x] Update phase-03 to use subprocess instead of anthropic SDK
- [x] Update phase-01 to remove anthropic from requirements.txt
- [x] Update phase-05/06 to add TP monitoring job (30s interval)

### Action Items (Previous Validation)
- [ ] Add MAX_SLIPPAGE to .env template in phase-01
- [ ] Add market hours detection in phase-06 orchestration
- [ ] Add 2-week paper trading enforcement in phase-07
- [ ] Add MT5 reconnect logic in TP monitor job (phase-06)
- [ ] Document retry behavior for Claude CLI in phase-03

### Action Items (instructions_v2.md Update - 2026-01-04)
- [ ] Add new env vars to phase-01: MAX_SPREAD_PIPS, TRAIL_ATR_MULTIPLIER, BREAKEVEN_BUFFER_PIPS, NEWS_BLACKOUT_*, SESSION_CONFIDENCE_*, CONFIDENCE_FULL/HALF_POSITION
- [ ] Update phase-03 with enhanced signal parser (session_context, spread_check, trailing_stop, confidence_breakdown, execution_instructions)
- [ ] Update phase-05 with trailing stop state machine (inactive → activated → trailing)
- [ ] Update phase-06 with session detection and spread check
- [x] Create phase-06.5-news-integration.md (ForexFactory scraping)
- [x] Create phase-09-backtest-analytics.md (performance tracking)
- [ ] Update phase-06 with silent skip for confidence < 60%
- [ ] Update phase-05 with position sizing confidence multiplier

### Pre-Implementation Validation (2026-01-04)

**Validated:** 2026-01-04
**Questions asked:** 6

| Decision | User Choice |
|----------|-------------|
| **News Source** | ForexFactory scraping - accept fragility, fail-safe to "no blackout" |
| **Trailing Stop Fallback** | Alert only - Telegram alert on 3 failures, user manual backup |
| **Wave Position Tracking** | Add wave_position field to TradingSignal schema |
| **Build Order** | Sequential (Phase 1→9) - each builds on previous |
| **CLI Timeout** | 5 minutes acceptable - retry once, then skip |
| **Dashboard Scope** | Full dashboard (FastAPI + React + Docker) |

### Pre-Implementation Action Items
- [ ] Add wave_position field to TradingSignal in phase-03 signal_parser.py
- [ ] Add Telegram alert on 3 consecutive TP monitor failures in phase-06
- [ ] Verify CLAUDE_TIMEOUT=300 is sufficient during phase-07 testing

## Phase 7 Completion Summary (2026-01-04)

**Status**: ✅ COMPLETE

### Deliverables
- `tests/conftest.py` - Shared pytest fixtures (MT5 mock, telegram mock, trading signal factory)
- `tests/test_integration.py` - 15 integration tests covering core workflows
- `pytest.ini` - pytest configuration with asyncio mode
- **Test Results**: 281 tests passing (100% pass rate)
- **Code Coverage**: 66% overall (Core modules: 84-100%)

### Test Coverage by Module
- Signal parser: 95% coverage
- Trade execution: 88% coverage
- Orchestration: 84% coverage
- Telegram bot: 92% coverage
- MT5 export: 90% coverage

### Key Tests Added
- Elliott Wave signal parsing with confidence breakdown
- Position sizing with confidence multiplier
- Trailing stop state machine (inactive → activated → trailing)
- Session detection with UTC conversions
- Spread validation and skip logic
- News calendar blackout detection
- Telegram notification delivery with inline buttons
- Trade execution with partial TP closes
- Error handling and retry logic

### Next Steps
- **Phase 8**: Web Dashboard (FastAPI + React)
- **Phase 9**: Backtest Analytics

## Phase 8 Completion Summary (2026-01-04)

**Status**: ✅ COMPLETE

### Deliverables
- `dashboard/backend/main.py` - FastAPI application with 8 endpoints
- `dashboard/backend/routes/` - API route handlers (auth, trades, analytics, positions)
- `dashboard/backend/services/` - Core business logic (data aggregation, analytics computation)
- `dashboard/frontend/` - React + Vite + TailwindCSS SPA
- `dashboard/docker-compose.yml` - Multi-container orchestration (API + Web)
- `tests/test_dashboard_api.py` - 14 comprehensive API tests (100% pass rate)

### API Endpoints (8 total)
- `GET /api/health` - Health check with version
- `GET /api/trades` - All completed trades with filters
- `GET /api/trades/<id>` - Single trade details
- `GET /api/positions` - Active positions with entry/SL/TP
- `GET /api/analytics/equity` - Equity curve data
- `GET /api/analytics/daily-pnl` - Daily P&L breakdown
- `GET /api/analytics/signals` - Signal analysis (confidence distribution)
- `GET /api/analytics/performance` - Win rate, avg gain/loss, Sharpe ratio

### Frontend Components (7 total)
- TradeHistory - Paginated trades table with filtering
- PositionMonitor - Real-time position tracking
- EquityCurve - Interactive chart (recharts)
- DailyPnL - Bar chart with daily breakdown
- SignalAnalysis - Confidence distribution histogram
- PerformanceMetrics - Key statistics cards
- Dashboard - Main layout with navigation

### Security Implementation
- **Rate Limiting**: 100 req/min per IP (slidingwindow)
- **CORS Config**: Strict origin validation
- **Input Validation**: Pydantic models for all requests
- **Nginx Headers**: Security headers (CSP, X-Frame-Options, HSTS)
- **Error Handling**: No stack traces in production
- **Env Config**: All secrets from environment variables

### Docker & Deployment
- Multi-stage builds (API and Web both ~100MB)
- Health checks on both containers
- Volume mounts for persistent logs
- Network isolation (internal backend network)
- Nginx reverse proxy for frontend with gzip compression

### Test Coverage
- 14 tests covering: endpoints, auth, filters, error cases, edge cases
- 100% pass rate
- Response validation, performance checks
- Mock data consistency with core trading system

### Next Steps
- **Phase 9**: Backtest Analytics (performance tracking, strategy optimization)

## Phase 9 Completion Summary (2026-01-05)

**Status**: ✅ COMPLETE

### Deliverables
- `src/analytics.py` - AnalyticsEngine with metrics calculation
- `src/reports.py` - WeeklyReportGenerator for scheduled reports
- `tests/test_analytics.py` - 18 tests for analytics
- `tests/test_reports.py` - 9 tests for reports
- **Test Results**: 27/27 tests passing (100% pass rate)
- **Code Coverage**: 93-100% (analytics: 100%, reports: 100%)

### Core Features
- **Overall Metrics**: Win rate, profit factor, drawdown, Sharpe ratio
- **Breakdown Analysis**: Wave position, session, confidence level
- **Weekly Reports**: Automated generation (Sunday 23:00 UTC)
- **Optimization Suggestions**: Recommends adjustments based on performance
- **Period Comparison**: Trend analysis across different timeframes

### Key Tests Added
- Analytics engine initialization and configuration
- Overall metrics calculation (win rate, profit factor, drawdown, Sharpe)
- Breakdown by wave position (impulse, correction, recovery)
- Breakdown by session (overlapping, London, NY, Asian, off-hours)
- Breakdown by confidence level (high, medium, low)
- Period comparison (week-over-week, month-over-month)
- Weekly report generation and scheduling
- Optimization suggestion generation
- Edge cases (zero trades, single trade, no winners, no losers)

### Integration Points
- Reads from SQLite trading log (created by core orchestration)
- Integrates with APScheduler for weekly report automation
- Reports available via dashboard API (`GET /api/analytics/performance`)
- Optimization data feeds strategy tuning recommendations

### Next Steps
- **Phase 8.5**: Dashboard Hardening (recommended security enhancements)
- **Phase 10+**: Strategy optimization based on analytics insights

## Env Variables (Enhanced)

```env
# Core
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
MT5_PATH=
MT5_SYMBOL=XAUUSD
RISK_PERCENT=1.5
MAX_POSITION_SIZE=0.1
PAPER_TRADING=true
CLAUDE_TIMEOUT=300

# Slippage (from previous)
MAX_SLIPPAGE=20

# Session Configuration (NEW)
SESSION_CONFIDENCE_OVERLAP=10
SESSION_CONFIDENCE_LONDON=5
SESSION_CONFIDENCE_NY=5
SESSION_CONFIDENCE_ASIAN=-15
SESSION_CONFIDENCE_OFFHOURS=-20

# Spread & Slippage (NEW)
MAX_SPREAD_PIPS=4.0
EXPECTED_SLIPPAGE_PIPS=1.0

# Trailing Stop (NEW)
TRAIL_ATR_MULTIPLIER=1.5
BREAKEVEN_BUFFER_PIPS=5

# News Filter (NEW)
NEWS_BLACKOUT_BEFORE_MINS=30
NEWS_BLACKOUT_AFTER_MINS=15

# Confidence Thresholds (NEW)
CONFIDENCE_THRESHOLD=60
CONFIDENCE_FULL_POSITION=75
CONFIDENCE_HALF_POSITION=60
```
