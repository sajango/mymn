# Root Cause Analysis: KeyError 'last_action'

**Date:** 2026-01-12
**Error:** `KeyError: 'last_action'` in claude_client.py line 269
**Impact:** Analysis job crashes immediately on execution

---

## Executive Summary

Analysis job fails when attempting to build Claude prompt due to missing 'last_action' key in `signal_context` dict. Root cause: database has zero signals, so `get_enhanced_signal_context()` returns None, but `get_instruction_performance_context()` returns dict without 'last_action' key. Code merges performance context into signal_context when enhanced context is None, creating incomplete context dict that fails validation in `_build_prompt()`.

**Critical Flow:**
```
No signals in DB
→ get_enhanced_signal_context() returns None
→ get_instruction_performance_context() returns dict (no last_action)
→ signal_context = perf_context (line 725)
→ _build_prompt() expects last_action (line 269)
→ KeyError crash
```

---

## Technical Analysis

### Timeline of Events

1. `main.py:434` - Analysis job starts, calls `claude_client.analyze()`
2. `claude_client.py:702` - Calls `_db.get_enhanced_signal_context(limit=5)`
3. `database.py:1476` - Calls internal `get_signal_context(limit)`
4. `database.py:811` - Query returns empty (0 signals in DB)
5. `database.py:812` - Returns `None` (no signals exist)
6. `database.py:1477` - Enhanced context returns `None`
7. `claude_client.py:719` - Dynamic instructions enabled, calls `get_instruction_performance_context()`
8. `database.py:1767-1779` - Returns dict with performance keys BUT no 'last_action'
9. `claude_client.py:724-725` - Since `signal_context is None`, sets `signal_context = perf_context`
10. `claude_client.py:741` - Passes incomplete signal_context to `_retry_with_backoff()`
11. `claude_client.py:604` - Calls `_build_prompt()` with signal_context
12. `claude_client.py:269` - **CRASH**: Tries to access `signal_context['last_action']` - key doesn't exist

---

## Code Evidence

### Database Query (Empty Result)
```bash
Total signals: 0
Recent BUY/SELL signals: (none)
```

### Signal Context Sources

**Enhanced Signal Context** (`database.py:1465-1504`)
- Calls `get_signal_context()` first
- If no signals exist, returns `None` at line 1477
- Includes: last_action, last_confidence, last_time, minutes_since_last, recent_sequence, wave_position

**Performance Context** (`database.py:1705-1779`)
- Always returns dict (never None)
- Includes: overall_win_rate, confidence_performance, session_performance, current_streak, best_wave_position, worst_wave_position, calibrated_min_confidence, looking_for
- **MISSING**: last_action, last_confidence, last_time, minutes_since_last, recent_sequence, wave_position

### Problematic Merge Logic (`claude_client.py:724-727`)
```python
if signal_context is None:
    signal_context = perf_context  # ← Sets incomplete dict
else:
    signal_context.update(perf_context)  # ← Would work if signal_context existed
```

### Expected Keys in _build_prompt (`claude_client.py:269-273`)
```python
if signal_context:
    prompt_parts.extend([
        "## PREVIOUS ANALYSIS CONTEXT",
        "",
        f"**Last Signal:** {signal_context['last_action']} "  # ← REQUIRED
        f"(confidence: {signal_context['last_confidence']}%) "  # ← REQUIRED
        f"at {signal_context['last_time']}",  # ← REQUIRED
        f"**Time Since Last:** {signal_context['minutes_since_last']} minutes",  # ← REQUIRED
        f"**Recent Sequence:** {signal_context['recent_sequence']}",  # ← REQUIRED
    ])
```

---

## Data Structure Comparison

### Enhanced Signal Context (Complete)
```python
{
    'last_action': 'BUY',              # ← From get_signal_context()
    'last_confidence': 75,             # ← From get_signal_context()
    'last_time': '2026-01-12T...',     # ← From get_signal_context()
    'minutes_since_last': 15,          # ← From get_signal_context()
    'recent_sequence': 'SELL → BUY',   # ← From get_signal_context()
    'wave_position': 'Wave 3',         # ← From get_signal_context()
    'session_performance': {...},      # ← Enhanced additions
    'current_streak': {...},
    'market_memory': [...],
    'key_levels': [...],
    'total_signals_today': 0
}
```

### Performance Context (Incomplete)
```python
{
    'overall_win_rate': None,
    'wave_performance': {...},
    'confidence_performance': {...},
    'session_performance': {...},
    'current_streak': {...},
    'best_wave_position': None,
    'worst_wave_position': None,
    'best_session': None,
    'worst_session': None,
    'calibrated_min_confidence': 60,
    'looking_for': 'entry'
    # ← MISSING: last_action, last_confidence, last_time, etc.
}
```

---

## Root Cause Summary

**Primary Cause:** Schema mismatch between two context sources
**Trigger Condition:** Empty signals table (first run or fresh database)
**Code Logic Flaw:** Merge logic assumes both contexts have compatible schemas

### Why It Happens
1. `get_enhanced_signal_context()` includes basic signal data (last_action, etc.) from `get_signal_context()`
2. `get_instruction_performance_context()` only includes performance metrics (win rates, streaks)
3. When no signals exist, enhanced context returns None
4. Performance context always returns dict (even with empty data)
5. Code replaces None with performance context, creating incomplete dict
6. `_build_prompt()` unconditionally accesses keys that only exist in enhanced context

### Design Assumption Violated
Code assumes: "If signal_context exists, it contains last_action"
Reality: "signal_context can exist but be missing last_action when sourced from performance context only"

---

## Impact Assessment

**Severity:** Critical - Blocks all analysis operations
**Frequency:** 100% when database has zero signals
**Blast Radius:** System cannot perform any trading analysis
**Data Loss:** None
**Recovery:** Requires code fix

---

## Supporting Evidence

### File: `claude_client.py`
- Line 269: KeyError occurs when accessing `signal_context['last_action']`
- Lines 724-727: Merge logic creates incomplete context
- Line 702: Enhanced context call that returns None

### File: `database.py`
- Lines 785-849: `get_signal_context()` returns None when no signals
- Lines 1465-1504: `get_enhanced_signal_context()` wraps get_signal_context()
- Lines 1705-1779: `get_instruction_performance_context()` returns dict without signal keys

### File: `main.py`
- Line 434: Entry point where analysis job starts
- No defensive checks for signal_context schema

### Database State
- 0 signals in signals table
- First run or fresh database scenario
- No historical data for context building

---

## Unresolved Questions

1. Why was `get_instruction_performance_context()` designed to return dict without signal keys?
   - Was it intended to be merged only with existing signal context?
   - Should it return None when no trades exist?

2. Should `_build_prompt()` check for required keys before accessing?
   - Add defensive `.get()` calls?
   - Separate prompts for first-run vs ongoing scenarios?

3. Is there a first-run initialization sequence that was missed?
   - Should system seed initial signal context?
   - Special handling for zero-signal state?

4. Why does performance context include `looking_for` and `wave_ambiguity` fields?
   - These seem signal-specific but appear in performance context
   - Suggests original design intended different separation

---

## Recommended Investigation Areas

1. Review commit history for when `get_instruction_performance_context()` was added
2. Check if there's test coverage for first-run scenario (zero signals)
3. Examine if CalibrationAnalyzer has similar patterns that work correctly
4. Verify if InstructionBuilder has defensive handling for missing keys
5. Assess if other code paths use signal_context and expect these keys

---

**Report Generated:** 2026-01-12
**Analysis Duration:** ~5 minutes
**Evidence Quality:** High (direct DB query + code trace)
**Confidence Level:** 100% (reproducible, definitive root cause identified)
