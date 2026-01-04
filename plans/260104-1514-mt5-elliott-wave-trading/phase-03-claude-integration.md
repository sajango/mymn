# Phase 3: Claude Code CLI Integration

## Context Links
- [Plan Overview](./plan.md)
- [Phase 2: MT5 Data Export](./phase-02-mt5-data-export.md)
- [instructions.md](../../instructions.md) - Analysis prompt

## Overview
- **Priority**: P1
- **Status**: Pending
- **Effort**: 5h (+1h for enhanced parsing)
- **Description**: Integrate Claude Code CLI for Elliott Wave analysis and signal generation

## Key Insights
- Use claude CLI via subprocess (NOT anthropic Python SDK)
- Pass CSV data and instructions.md as file context
- Use --print flag for non-interactive output
- Parse JSON from stdout
- Pydantic for validation
- Implement retry with exponential backoff

## Requirements

### Functional
- Load instructions_v2.md as system context
- Combine 4 CSV files into prompt
- Call Claude Code CLI via subprocess
- Extract and validate JSON signal (enhanced format)
- Handle parsing failures gracefully
- Parse new JSON fields: session_context, spread_check, trailing_stop, confidence_breakdown, execution_instructions

### Non-Functional
- Subprocess timeout handling
- Retry on failures
- Logging of all CLI calls

## Architecture

### Data Flow
Build prompt with CSV data
        |
subprocess.run(["claude", "--print", "-p", prompt])
        |
Parse stdout for JSON response
        |
Pydantic Signal model validation
        |
Return TradingSignal or None

### Claude CLI Command
claude --print -p "Analyze..." --add-file data/csv/H4.csv --system-prompt instructions.md

## Related Code Files

### Files to Create
- src/claude_client.py - Claude CLI wrapper
- src/signal_parser.py - Pydantic models and parsing

## Implementation Steps

1. **Create src/signal_parser.py** - Pydantic models for TradingSignal validation
2. **Create src/claude_client.py** - ClaudeClient class using subprocess

## Todo List

- [ ] Create src/signal_parser.py with Pydantic models
- [ ] Create src/claude_client.py with CLI wrapper
- [ ] Implement JSON extraction (code block + fallback)
- [ ] Implement retry with exponential backoff
- [ ] Write tests/test_claude.py
- [ ] Verify Claude CLI is installed and authenticated
- [ ] Test with real CLI call
- [ ] **Add SessionContext model** (current_session, session_quality, confidence_modifier)
- [ ] **Add SpreadCheck model** (current_spread_pips, max_allowed_pips, spread_ok, adjusted_entry/tp)
- [ ] **Add TrailingStopConfig model** (activation_trigger, trail_distance_atr, breakeven_buffer_pips)
- [ ] **Add ConfidenceBreakdown model** (base_score, timeframe_alignment, fib_confluence, rsi/ema/macd confirmation, session_bonus, penalties)
- [ ] **Add ExecutionInstructions model** (order_type, valid_until, cancel_if, post_fill_actions)

## Success Criteria

- [ ] CLI call succeeds with valid response
- [ ] JSON correctly extracted from response
- [ ] Pydantic validation passes
- [ ] Retry works on failures
- [ ] Subprocess timeout works

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Invalid JSON response | Medium | Medium | Retry once, fallback to NO_TRADE |
| CLI not installed | Low | High | Check on startup, show clear error |
| Subprocess timeout | Low | Medium | Configurable timeout, retry |
| CLI authentication expired | Low | High | Check before analysis |

## Security Considerations

- No API keys needed (CLI uses existing auth)
- No logging of full response (may contain strategy)
- Subprocess runs with same user permissions

## Next Steps

-> [Phase 4: Telegram Bot](./phase-04-telegram-bot.md)
