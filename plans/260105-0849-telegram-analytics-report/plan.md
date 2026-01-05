---
title: "Telegram Analytics Report Feature"
description: "Add /analytics command to send trading performance reports via Telegram"
status: done
priority: P2
effort: 1h
branch: master
tags: [telegram, analytics, feature]
created: 2026-01-05
completed: 2026-01-05
---

# Telegram Analytics Report Feature

## Overview

Add functionality to send trading analytics results to Telegram, including overall stats, confidence analysis, and time-based performance. Integrates with existing `telegram_bot.py` and `AnalyticsEngine`.

## Phases

| Phase | Description | Status | Link |
|-------|-------------|--------|------|
| 01 | Implement analytics command & formatter | done | [phase-01](./phase-01-analytics-command.md) |

## Key Deliverables

1. `/analytics` Telegram command handler
2. `send_analytics_report()` method in TradingBot
3. Formatted messages for overall stats, confidence, time analysis
4. Callable method for scheduled reports (weekly report integration)

## Files to Modify

- `src/telegram_bot.py` - Add command handler and formatting methods
- `src/main.py` - Wire analytics to weekly report job (optional)

## Dependencies

- Existing `src/analytics.py` AnalyticsEngine
- Existing `src/telegram_bot.py` TradingBot class
