---
title: "MT5 Elliott Wave Auto-Trading System"
description: "Semi-automated XAUUSD trading using Claude AI for wave analysis with Telegram notifications"
status: in-progress
priority: P1
effort: 41h
branch: main
tags: [trading, automation, ai, mt5, telegram]
created: 2026-01-04
updated: 2026-01-04
completed_phases: 7
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
| 7 | Testing & Paper Trading | Pending | 4h | [phase-07](./phase-07-testing.md) | |
| 8 | Web Dashboard | Pending | 6h | [phase-08](./phase-08-web-dashboard.md) | |
| 9 | **Backtest Analytics** | Pending | **4h** | [phase-09](./phase-09-backtest-analytics.md) | **NEW** |

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
