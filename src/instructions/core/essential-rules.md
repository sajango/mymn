# ESSENTIAL ELLIOTT WAVE RULES

## INVIOLABLE RULES (Zero Tolerance for Violations)

These rules MUST NOT be violated. If violated, the wave count is INVALID and must be rejected.

### Rule 1: Wave 2 Cannot Retrace Beyond Wave 1 Start

| Validation | Bullish | Bearish |
|------------|---------|---------|
| Check | `wave2_low > wave1_start` | `wave2_high < wave1_start` |
| Action | If price breaks Wave 1 origin → INVALIDATE count immediately |
| Exception | NONE - this is absolute |

**Key Insight**: This is a hard stop. No "maybe" or "close enough" - if Wave 2 retraces 100% or more, the count is wrong.

### Rule 2: Wave 3 Cannot Be the Shortest Impulse Wave

| Measurement | Method |
|-------------|--------|
| Compare | Wave 1, Wave 3, Wave 5 lengths (in PRICE, not time) |
| Validation | `wave3_length >= wave1_length OR wave3_length >= wave5_length` |
| Action | If Wave 3 appears shorter than both → RECOUNT required |

**Key Insight**: Wave 3 is typically the longest. If it appears shortest, you've likely mislabeled the waves.

### Rule 3: Wave 4 Cannot Enter Wave 1 Price Territory

| Validation | Bullish | Bearish |
|------------|---------|---------|
| Check | `wave4_low > wave1_high` | `wave4_high < wave1_low` |
| Exception | Ending diagonal patterns (verify other diagonal characteristics) |

**Key Insight**: This maintains the impulse structure's integrity. Overlap suggests a correction, not an impulse.

---

## GUIDELINES (Strong Tendencies - 70-85% Probability)

| Guideline | Typical Behavior | Probability |
|-----------|------------------|-------------|
| Wave 2 retracement | 50% - 78.6% of Wave 1 | 85% |
| Wave 3 extension | 161.8% - 261.8% of Wave 1 | 80% |
| Wave 4 retracement | 23.6% - 38.2% of Wave 3 | 75% |
| Wave 5 length | 61.8% - 100% of Wave 1 | 70% |
| Alternation | Wave 2 and Wave 4 differ in pattern type | 80% |

---

## WAVE CHARACTERISTICS (Essential Reference)

### Wave 1: Initial Move
- Often weak, difficult to identify in real-time
- Volume: Low to moderate
- Confirmation: Break of previous trend structure

### Wave 2: Deep Retracement
- Typical retracement: 50-78.6% of Wave 1 (61.8% most common)
- **Never retraces 100%** (Rule 1)
- Volume: Lower than Wave 1
- RSI: Should NOT return to oversold if bullish trend

### Wave 3: Strongest and Longest
- Extension: 161.8% or 261.8% of Wave 1
- Volume: **HIGHEST** of all waves
- RSI: Peak reading (70-80+), often overbought but stays there
- MACD: **Peak histogram** bars
- Breaks through resistance, strong momentum

### Wave 4: Shallow Correction
- Typical retracement: 23.6-50% of Wave 3 (38.2% most common)
- **Must stay above Wave 1 territory** (Rule 3)
- Often forms triangle, flat, or zigzag pattern
- Volume: Lower than Wave 3
- RSI: Pullback to 45-55, stays above 40 in strong trend

### Wave 5: Final Push
- Length: Usually 61.8% - 100% of Wave 1
- Volume: **Lower** than Wave 3 (divergence)
- **RSI Divergence**: Price higher, RSI lower
- **MACD Divergence**: Lower peak than Wave 3
- Often shows momentum exhaustion

### Wave A: Correction Begins
- Structure: 5 waves or 3 waves
- Retracement: 38.2% - 61.8% of entire impulse
- Sharp drop in RSI (50 → 30)

### Wave B: Counter-trend Bounce (The Trap)
- Retracement: 38.2% - 78.6% of Wave A
- Often a "trap" (bull trap or bear trap)
- Weak RSI bounce (45-55), fails to reach overbought
- MACD: Weak positive

### Wave C: Correction Completes
- Structure: 5 waves
- Length: 100% - 161.8% of Wave A
- **Bullish divergence** expected (price lower low, RSI higher low)
- MACD: Extreme negative reading

---

## ENTRY TRIGGERS (Only These Qualify)

| Position | Signal Type | Required Confirmations |
|----------|-------------|------------------------|
| Wave 2 complete | BUY | Fib 50-78.6%, RSI 35-50, volume declining, price near EMA support |
| Wave 4 complete | BUY | Fib 38.2-61.8%, MACD histogram shrinking, above EMA 34 |
| Wave 5 complete | SELL | Extension 61.8-100% of W1, RSI/MACD divergence present |
| Wave C complete | SELL | ABC structure clear, momentum fading, bullish RSI divergence |

**Critical**: Do NOT enter mid-wave. Wait for wave COMPLETION signals.

---

## RULE VALIDATION BEFORE SIGNAL

Before generating any BUY/SELL signal, validate:

```json
{
  "rules_check": {
    "rule_1_wave2_valid": true,
    "rule_2_wave3_not_shortest": true,
    "rule_3_wave4_no_overlap": true
  },
  "all_rules_passed": true
}
```

**If ANY rule is false → Signal = NO_TRADE with reason "rule_violation"**
