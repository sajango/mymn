# Phase 3: Claude Code CLI Integration

## Context Links
- [Plan Overview](./plan.md)
- [Phase 2: MT5 Data Export](./phase-02-mt5-data-export.md)
- [instructions.md](../../instructions.md) - Analysis prompt

## Overview
- **Priority**: P1
- **Status**: ✅ Done (2026-01-04)
- **Effort**: 5h (+1h for enhanced parsing)
- **Description**: Integrate Claude Code CLI for Elliott Wave analysis and signal generation
- **Review**: [Code Review Report](../reports/code-reviewer-260104-1725-phase3-claude-integration.md)

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

- [x] Create src/signal_parser.py with Pydantic models ✅
- [x] Create src/claude_client.py with CLI wrapper ✅
- [x] Implement JSON extraction (code block + fallback) ✅
- [x] Implement retry with exponential backoff ✅
- [x] Write tests/test_claude.py ✅ (49 tests passing)
- [x] Verify Claude CLI is installed and authenticated ✅
- [x] Test with real CLI call ✅
- [x] **Add SessionContext model** ✅ (lines 67-78)
- [x] **Add SpreadCheck model** ✅ (lines 81-93)
- [x] **Add TrailingStopConfig model** ✅ (lines 34-45)
- [x] **Add ConfidenceBreakdown model** ✅ (lines 188-203)
- [x] **Add ExecutionInstructions model** ✅ (lines 205-217)

### Security Fixes Completed
- [x] **Fix command injection vulnerability** - sanitized file paths in _build_command()
- [x] **Remove response logging** - removed strategy details leak
- [x] **Document --dangerously-skip-permissions** - removed flag

## Success Criteria

- [x] CLI call succeeds with valid response ✅
- [x] JSON correctly extracted from response ✅ (3 strategies)
- [x] Pydantic validation passes ✅ (comprehensive models)
- [x] Retry works on failures ✅ (exponential backoff)
- [x] Subprocess timeout works ✅ (configurable timeout)

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
