# Brainstorm: Instructions V2 Plan Update

**Date**: 2026-01-04
**Status**: Completed
**Related**: [plan.md](../260104-1514-mt5-elliott-wave-trading/plan.md), [instructions_v2.md](../../instructions_v2.md)

---

## Problem Statement

User cải tiến `instructions_v2.md` với nhiều features mới cho Elliott Wave analysis. Cần cập nhật plan để reflect các features này.

## Key Additions in instructions_v2.md

### Section 1.4 - Trading Session Configuration
- Session times (UTC): Asian 00:00-07:00, London 07:00-15:00, NY 12:00-20:00
- Confidence modifiers: +10 overlap, +5 London/NY, -15 Asian, -20 off-hours

### Section 1.5 - News and Event Filter
- Blackout: 30min before, 15min after high-impact news
- Events: FOMC, NFP, CPI, Fed Chair Speech, ECB Rate, GDP

### Section 1.6 - Spread and Slippage
- Max spread: 4 pips
- Expected slippage: 1 pip
- Entry/TP adjustment formulas

### Section 3 - Enhanced Pivot Detection
- ATR-based filtering algorithm
- Significance levels: major/intermediate/minor/noise

### Section 5 - Technical Indicators
- RSI divergence detection with wave correlation
- EMA position analysis (34/89)
- MACD divergence detection
- ATR volatility filter (low/normal/extreme)
- Indicator confluence scoring (+40 max possible)

### Section 8.5 - Trailing Stop Management
- Activation: After TP1 hit or profit > 1R
- Breakeven: Entry + 5 pips buffer
- Trail distance: 1.5 ATR (configurable)

### Section 8.6 - Position Sizing
- 75%+ confidence: full position
- 60-74% confidence: half position
- <60% confidence: no trade

### Section 9 - Enhanced Output Format
- New fields: session_context, spread_check, trailing_stop, confidence_breakdown, execution_instructions

### Appendix C - Backtest Metrics Template
- Win rate by wave position, session, confidence
- Profit factor, Sharpe ratio, max drawdown

---

## User Decisions

| Question | Answer |
|----------|--------|
| News Calendar Integration | External API (ForexFactory scraping) |
| Low Confidence (<60%) Action | Silent skip (no trade, no notify, log only) |
| Backtest Tracking | New Phase 9 (separate phase) |
| Extended Timeline (29h → 40h) | Accept |
| Trailing Stop Implementation | Custom implementation in monitoring job |
| News Data Source | ForexFactory scraping |

---

## Plan Updates Required

### Modified Phases

#### Phase 03 - Claude Integration (+1h → 5h)
- [ ] Add parser for `session_context` JSON field
- [ ] Add parser for `spread_check` JSON field
- [ ] Add parser for `trailing_stop` config field
- [ ] Add parser for `confidence_breakdown` field
- [ ] Add parser for `execution_instructions` field
- [ ] Handle new output format validation

#### Phase 05 - Trade Execution (+2h → 5h)
- [ ] Implement trailing stop state machine (inactive → activated → trailing)
- [ ] Add breakeven + buffer logic after TP1 hit
- [ ] Add ATR-based trail distance calculation
- [ ] Position sizing with confidence multiplier
- [ ] Spread-adjusted entry/TP calculation

#### Phase 06 - Orchestration (+2h → 5h)
- [ ] Add session detection (time-based UTC check)
- [ ] Apply session confidence modifiers
- [ ] Add spread check before entry (skip if > MAX_SPREAD_PIPS)
- [ ] Implement silent skip for confidence < 60%
- [ ] Log skipped signals to SQLite

### New Phases

#### Phase 6.5 - News Integration (3h)
- [ ] ForexFactory calendar scraper
- [ ] Parse upcoming high-impact events
- [ ] Blackout period detection logic
- [ ] Cache mechanism (avoid repeated requests)
- [ ] Integration with orchestrator

#### Phase 9 - Backtest & Analytics (4h)
- [ ] Historical signal analysis from SQLite logs
- [ ] Win rate calculation (by wave, session, confidence)
- [ ] Profit factor, Sharpe ratio computation
- [ ] Max drawdown tracking
- [ ] Indicator effectiveness analysis
- [ ] Weekly performance reports

### Updated Phase Table

| # | Phase | Status | Effort | Notes |
|---|-------|--------|--------|-------|
| 1 | Project Setup | Pending | 2h | |
| 2 | MT5 Data Export | Pending | 3h | |
| 3 | Claude AI Integration | Pending | **5h** | +1h for enhanced parsing |
| 4 | Telegram Bot | Pending | 4h | |
| 5 | Trade Execution | Pending | **5h** | +2h for trailing stop |
| 6 | Orchestration | Pending | **5h** | +2h for session/spread |
| 6.5 | **News Integration** | **NEW** | **3h** | ForexFactory scraping |
| 7 | Testing & Paper Trading | Pending | 4h | |
| 8 | Web Dashboard | Pending | 6h | |
| 9 | **Backtest & Analytics** | **NEW** | **4h** | Performance tracking |

**Total: 41h** (was 29h)

---

## New Action Items

- [ ] Add MAX_SPREAD_PIPS to .env template (Phase 01)
- [ ] Add TRAIL_ATR_MULTIPLIER to .env template (Phase 01)
- [ ] Add NEWS_BLACKOUT_BEFORE_MINS to .env template (Phase 01)
- [ ] Add NEWS_BLACKOUT_AFTER_MINS to .env template (Phase 01)
- [ ] Create Phase 6.5 detailed spec
- [ ] Create Phase 9 detailed spec
- [ ] Update architecture diagram with news integration

---

## Env Variables to Add

```env
# Session Configuration
SESSION_CONFIDENCE_OVERLAP=10
SESSION_CONFIDENCE_LONDON=5
SESSION_CONFIDENCE_NY=5
SESSION_CONFIDENCE_ASIAN=-15
SESSION_CONFIDENCE_OFFHOURS=-20

# Spread & Slippage
MAX_SPREAD_PIPS=4.0
EXPECTED_SLIPPAGE_PIPS=1.0

# Trailing Stop
TRAIL_ATR_MULTIPLIER=1.5
BREAKEVEN_BUFFER_PIPS=5

# News Filter
NEWS_BLACKOUT_BEFORE_MINS=30
NEWS_BLACKOUT_AFTER_MINS=15

# Confidence Thresholds
CONFIDENCE_FULL_POSITION=75
CONFIDENCE_HALF_POSITION=60
```

---

## Architecture Update

```
APScheduler (M15 cron)
        |
News Calendar Check ←── ForexFactory Scraper (new)
        |
[Blackout?] ─── Yes ──→ Skip (log only)
        |
        No
        ↓
Session Detection (new)
        |
MT5 Data Export
        |
Spread Check ←── MT5 API (new)
        |
[Spread OK?] ─── No ──→ Skip (log only)
        |
        Yes
        ↓
Claude Code CLI
        |
Signal Parser (enhanced)
        |
[Confidence >= 60?] ─── No ──→ Silent Skip (log only)
        |
        Yes
        ↓
Position Sizing (confidence-adjusted)
        |
Telegram Notification
        |
User Response
        |
MT5 Trade Execution
        |
Trailing Stop Monitor (enhanced) ←── 30s interval
        |
SQLite Logger
        |
Backtest Analytics (new Phase 9)
```

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| ForexFactory blocks scraping | Cache aggressively, use backup source |
| Trailing stop logic bugs | Extensive paper trading with edge cases |
| Session timezone confusion | Use UTC internally, convert for display only |
| Spread spikes during news | Double-check spread before execution |

---

## Next Steps

1. Update plan.md with new phases and efforts
2. Create phase-06.5-news-integration.md spec
3. Create phase-09-backtest-analytics.md spec
4. Update phase-03, phase-05, phase-06 with new tasks
5. Update phase-01 with new env variables

---

## Unresolved Questions

None - all critical questions answered by user.
