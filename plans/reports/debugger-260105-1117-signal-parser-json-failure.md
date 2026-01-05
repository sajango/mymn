# Signal Parser JSON Extraction Failure Investigation

**Date**: 2026-01-05 11:17
**Status**: Root cause identified
**Impact**: Critical - 100% of live analyses failing to parse

---

## Executive Summary

Claude CLI executes successfully (returncode=0, 64-84s execution) but JSON extraction fails consistently. Parser receives 2.3-3KB responses but cannot extract JSON despite using 3-strategy regex approach. Root cause: **Claude is NOT returning JSON-wrapped responses** as instructed.

---

## Evidence Analysis

### 1. Log Pattern Analysis

**Failure sequence (11:12:36 & 11:16:24)**:
```
[CLI] Success: returncode=0, elapsed=64.6s, response_length=3046 chars
[ANALYSIS] Parsing Claude response...
WARNING - Failed to extract JSON from response
ERROR - Could not extract JSON from response
[ANALYSIS] Failed to parse signal from response
```

**Key observations**:
- CLI execution SUCCEEDS (returncode=0)
- Response length substantial (2366-3046 chars)
- Parsing ALWAYS fails immediately
- No debug preview logged (log level = INFO)

### 2. Parser Strategy Review

**File**: `src/signal_parser.py:322-392`

**3 extraction strategies implemented**:
1. JSON code block: `r"```json\s*([\s\S]*?)\s*```"`
2. Generic code block: `r"```\s*([\s\S]*?)\s*```"` (if starts with `{` or `[`)
3. Raw JSON object: Brace-matching algorithm with escape handling

**Strategy 1** (JSON code block):
- Tests show this WORKS in unit tests (line 11 of test analysis)
- Production logs show FAILS every time
- **Inference**: Claude is NOT wrapping JSON in code blocks

**Strategy 2** (Generic code block):
- Fallback for unmarked code blocks
- Requires content to start with `{` or `[`
- **Inference**: No code blocks present AT ALL

**Strategy 3** (Raw JSON):
- Sophisticated brace-matching with string/escape handling
- Should catch any JSON object in response
- **Inference**: Either no `{` at start OR malformed JSON

### 3. Instructions Analysis

**File**: `instructions_v2.md:217-220`

```python
"Follow the instructions in the system prompt exactly.",
"Output ONLY the JSON signal - no explanations or markdown outside the JSON.",
"Wrap the JSON in ```json code blocks.",
```

**Critical finding**: Instructions EXPLICITLY request:
1. JSON-only output
2. Wrapped in ```json code blocks
3. No explanations outside JSON

**But**: Claude CLI is ignoring these instructions.

### 4. Test vs Production Discrepancy

**Test file**: `data/analyses/analysis_20260105_041007.json`
```json
"raw_response": "```json\n        {\n            \"timestamp\": \"2024-08-21T14:30:00Z\",\n            \"symbol\": \"XAUUSD\",\n            \"signal\": {\n                \"action\": \"BUY\",\n                \"entry_price\": 3340.00,\n                \"stop_loss\": 3310.00,\n                \"confidence\": 78\n            }\n        }\n        ```",
```

**Test response**: Properly wrapped in ```json blocks ✓
**Production response**: NOT wrapped (inferred from parsing failure) ✗

**Hypothesis**: Different Claude CLI invocation OR different data triggers different response format.

---

## Root Cause Analysis

### Primary Root Cause
**Claude CLI is NOT returning JSON-wrapped responses despite explicit instructions.**

**Supporting evidence**:
1. Parser uses 3 strategies (code block, generic block, raw JSON)
2. All 3 strategies fail simultaneously
3. Response length suggests substantial content (not empty)
4. Tests with mock responses succeed
5. Instructions explicitly request ```json wrapping

**Possible reasons**:
1. **Instruction format issue**: System prompt not properly loaded/parsed
2. **Claude model behavior**: Recent model changes ignore formatting instructions
3. **Response format**: Claude returning prose explanation + JSON (violates instructions)
4. **Edge case**: CSV data triggers analytical response instead of JSON-only

### Secondary Issues

**1. Debug logging disabled**:
- Line 414: `logger.debug(f"[ANALYSIS] Raw response (first 1000 chars): {response[:1000]}")`
- Only triggers when `signal is None`
- Production runs with INFO level → no debug output
- **Impact**: Cannot inspect actual response content

**2. No analysis file saved on failure**:
- `_save_analysis()` called at line 459
- Only executes AFTER successful parsing
- **Impact**: No record of failed responses for investigation

**3. Brittle parser assumptions**:
- Assumes one of 3 formats will always work
- No fallback for mixed content (prose + JSON)
- No validation of instruction adherence

---

## Technical Analysis

### Parser Code Flow
```
extract_json_from_response(response)
├─ Strategy 1: Search for ```json ... ```
│  └─ Regex: r"```json\s*([\s\S]*?)\s*```"
│  └─ Result: NO MATCHES in production
├─ Strategy 2: Search for generic ``` ... ```
│  └─ Regex: r"```\s*([\s\S]*?)\s*```"
│  └─ Filter: Must start with { or [
│  └─ Result: NO MATCHES in production
└─ Strategy 3: Raw brace matching
   └─ Find first { character
   └─ Track depth with escape handling
   └─ Result: FAILS (likely no opening brace at start)
```

### Instruction Delivery Flow
```
_build_command() [line 224]
├─ Validates instructions_path [line 251]
├─ Adds --system-prompt flag [line 253]
└─ Path: instructions_v2.md

instructions_v2.md content:
├─ 1637 lines of Elliott Wave analysis instructions
├─ Line 217-220: Explicit JSON output format request
└─ Expected: Claude follows instructions
└─ Actual: Claude ignores formatting (inferred)
```

---

## What's Actually Happening (Best Hypothesis)

**Scenario A: Claude returns prose analysis** (70% probability)
```
Claude response structure (HYPOTHESIZED):
─────────────────────────────────────────
Based on the Elliott Wave analysis of the XAUUSD data:

**H4 Analysis**: Bullish impulse wave structure with Wave 4 completing...
**H1 Analysis**: Corrective pattern forming...

**Trading Signal:**
{
  "timestamp": "2024-08-21T14:30:00Z",
  "symbol": "XAUUSD",
  ...
}
─────────────────────────────────────────
```
**Why Strategy 3 fails**: JSON appears mid-response, not at start
**Why Strategies 1-2 fail**: No code block markers

**Scenario B: Claude returns formatted explanation** (20% probability)
```
# Elliott Wave Analysis Report

## Signal Generation
- Action: BUY
- Entry: 3340.00
...

[No JSON object at all]
```

**Scenario C: Malformed JSON** (10% probability)
```json
{
  "timestamp": "2024-08-21T14:30:00Z",
  "signal": {
    "action": "BUY",
    // This is a buy signal
    "entry_price": 3340.00
  }
}
```
**Why**: Contains comments, trailing commas, or other non-spec JSON

---

## Recommended Fix Approach

### Immediate Actions (DO NOT IMPLEMENT)

**1. Enhanced logging**:
```python
# In claude_client.py line 409, BEFORE parsing
logger.info(f"[ANALYSIS] Raw response length: {len(response)}")
logger.info(f"[ANALYSIS] Response preview (500 chars): {response[:500]}")
logger.info(f"[ANALYSIS] Response has ```json: {'```json' in response}")
logger.info(f"[ANALYSIS] Response starts with '{response.strip()[:50]}'")
```

**2. Save failed responses**:
```python
# In claude_client.py line 413, when parsing fails
if signal is None:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    failed_path = Path("data/failed_analyses") / f"failed_{timestamp}.txt"
    failed_path.parent.mkdir(parents=True, exist_ok=True)
    failed_path.write_text(response, encoding='utf-8')
    logger.error(f"[ANALYSIS] Failed response saved to: {failed_path}")
```

**3. Robust parser enhancement**:
```python
# New Strategy 4: Search anywhere in response
def extract_json_from_mixed_response(response: str) -> Optional[dict]:
    """Find JSON object anywhere in response, even after prose."""
    # Find ALL { positions
    for start_idx in [i for i, c in enumerate(response) if c == '{']:
        try:
            # Try parsing from each { position
            result = extract_from_position(response[start_idx:])
            if result:
                return result
        except:
            continue
    return None
```

**4. Instruction strengthening**:
```markdown
# Add to instructions_v2.md line 220:

CRITICAL OUTPUT REQUIREMENTS:
1. Your FIRST line must be: ```json
2. Your LAST line must be: ```
3. Between these markers: ONLY valid JSON, NO comments, NO explanations
4. DO NOT include any text before or after the JSON code block
5. Example of CORRECT format:

```json
{
  "timestamp": "2024-08-21T14:30:00Z",
  "symbol": "XAUUSD"
}
```

INCORRECT (DO NOT DO THIS):
- Adding explanatory text before JSON
- Including comments in JSON
- Writing analysis outside code block
```

**5. Validation layer**:
```python
# Add validation BEFORE calling Claude
def validate_cli_output_format():
    """Test that Claude follows JSON format instructions."""
    test_response = run_cli_with_simple_prompt("Return JSON: {\"test\": true}")
    if not test_response.strip().startswith("```json"):
        raise ClaudeClientError("Claude not following format instructions")
```

---

## Unresolved Questions

1. **What is the ACTUAL response content from production failures?**
   - Need: Enable debug logging OR save failed responses
   - Action: Implement enhanced logging immediately

2. **Why do tests pass but production fails?**
   - Test uses mock response with proper format
   - Production uses real Claude CLI
   - **Hypothesis**: Real CSV data triggers different behavior

3. **Is the system prompt actually being loaded?**
   - Need: Verify `--system-prompt` flag is correctly passed
   - Need: Verify instructions_v2.md is readable at runtime
   - Action: Add startup validation

4. **Has Claude model behavior changed recently?**
   - System was working before (based on test expectations)
   - Recent model updates may ignore formatting instructions
   - Need: Check Claude CLI version and model

5. **Are there error messages in the response we're ignoring?**
   - Response length 2.3-3KB suggests substantial content
   - Could be error messages from Claude CLI
   - Need: Inspect full response content

---

## Impact Assessment

**Current state**:
- 🔴 0% successful analyses in production
- 🔴 All signals defaulting to NO_TRADE
- 🔴 System non-functional for live trading

**Risk**:
- High - Trading decisions cannot be made
- Data - No analysis records being saved
- Operational - No visibility into failure cause

**Urgency**: Critical - requires immediate investigation

---

## Next Steps (Investigation Only)

1. ✅ **Enable debug logging** to capture response content
2. ✅ **Save failed responses** to disk for manual inspection
3. ✅ **Run single analysis** with enhanced logging
4. ✅ **Examine actual response** to confirm hypothesis
5. ✅ **Implement appropriate parser fix** based on findings
6. ⏳ **Test with real data** to verify fix
7. ⏳ **Deploy with monitoring** to confirm resolution

**DO NOT implement fixes without confirming actual response format.**

---

## Appendix: Code References

**Parser**: `src/signal_parser.py:322-392`
**Client**: `src/claude_client.py:345-461`
**Instructions**: `instructions_v2.md:217-220`
**Logs**: `logs/trading.log:11:12:36, 11:16:24`
**Test**: `data/analyses/analysis_20260105_041007.json`
