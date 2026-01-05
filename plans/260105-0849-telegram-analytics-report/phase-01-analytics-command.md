# Phase 01: Analytics Command Implementation

## Context
- Parent: [plan.md](./plan.md)
- Dependencies: `src/analytics.py`, `src/telegram_bot.py`

## Overview
- **Date**: 2026-01-05
- **Priority**: P2
- **Implementation Status**: done
- **Review Status**: approved

## Requirements

1. Add `/analytics` command to Telegram bot
2. Format analytics data into readable Telegram messages
3. Keep messages under 4096 char limit
4. Include: overall stats, confidence breakdown, time analysis, suggestions
5. Make method callable for scheduled reports

## Architecture

```
User → /analytics → TradingBot._handle_analytics()
                          ↓
              AnalyticsEngine.generate_full_report()
                          ↓
              format_analytics_message()
                          ↓
              send_message() → Telegram
```

## Related Code Files

- `src/telegram_bot.py:59-75` - Command handler registration
- `src/telegram_bot.py:402-420` - send_message/send_alert methods
- `src/analytics.py:407-436` - generate_full_report()
- `src/analytics.py:438-487` - get_optimization_suggestions()

## Implementation Steps

### Step 1: Add analytics command handler
```python
# In TradingBot.initialize()
self.app.add_handler(CommandHandler("analytics", self._handle_analytics))
```

### Step 2: Create _handle_analytics method
- Check authorization
- Call AnalyticsEngine.generate_full_report()
- Format and send messages

### Step 3: Create format methods
- `_format_overall_stats(metrics: dict) -> str`
- `_format_confidence_breakdown(data: dict) -> str`
- `_format_time_analysis(sessions: dict) -> str`

### Step 4: Add send_analytics_report() public method
- For use by scheduled jobs
- Combines all formatted sections

## Todo List

- [ ] Add `/analytics` command handler registration
- [ ] Implement `_handle_analytics()` method
- [ ] Create `_format_overall_stats()` formatter
- [ ] Create `_format_confidence_breakdown()` formatter
- [ ] Create `_format_session_analysis()` formatter
- [ ] Add `send_analytics_report()` public method
- [ ] Add logging
- [ ] Test with bot

## Success Criteria

- [ ] `/analytics` command works in Telegram
- [ ] Message displays overall stats (win rate, PF, PnL, DD)
- [ ] Confidence breakdown shown with win rates
- [ ] Session/time analysis included
- [ ] Optimization suggestions displayed
- [ ] Messages stay under 4096 chars
- [ ] Existing tests pass

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Message too long | Medium | Split into multiple messages |
| No data | Low | Handle empty state gracefully |

## Security Considerations

- Authorization check required (existing pattern)
- No sensitive data exposure
