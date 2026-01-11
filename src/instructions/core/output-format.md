# OUTPUT FORMAT FOR AUTO-TRADING

## CRITICAL: RESPONSE FORMAT

You MUST respond with ONLY a JSON code block. **NO OTHER TEXT.**

```json
{"timestamp": "...", "symbol": "XAUUSD", "signal": {...}}
```

### VIOLATIONS THAT CAUSE SYSTEM CRASH

- ANY text before the ```json block = CRASH
- ANY markdown headers (##, ###) = CRASH
- ANY tables (|---|) = CRASH
- ANY prose or analysis = CRASH
- ANY text after ```json block closes = CRASH

---

## COMPLETE SIGNAL STRUCTURE

### Trade Signal (BUY/SELL)

```json
{
  "timestamp": "2024-08-21T14:30:00Z",
  "symbol": "XAUUSD",

  "signal": {
    "action": "BUY",
    "entry_price": 3340.00,
    "stop_loss": 3310.00,
    "take_profit": [
      {"level": "TP1", "price": 3380.00, "close_percent": 40},
      {"level": "TP2", "price": 3418.00, "close_percent": 35},
      {"level": "TP3", "price": 3455.00, "close_percent": 25}
    ],
    "trailing_stop": {
      "activation_trigger": "TP1_HIT",
      "trail_distance_atr": 1.5,
      "breakeven_buffer_pips": 5
    },
    "risk_reward": 2.45,
    "confidence": 78,
    "reason": "Wave 4 complete, entering Wave 5"
  },

  "wave_analysis": {
    "h4_trend": "bullish",
    "current_wave": "wave_4_complete",
    "wave_position": "entering_wave_5",
    "wave_count_valid": true,
    "rules_check": {
      "rule_1_wave2_valid": true,
      "rule_2_wave3_not_shortest": true,
      "rule_3_wave4_no_overlap": true
    },
    "invalidation_price": 3310.00,
    "primary_scenario": {
      "description": "Wave 5 targeting 3418-3455",
      "probability": 70
    },
    "alternative_scenario": {
      "description": "Complex correction W-X-Y, deeper to 3300",
      "probability": 30
    }
  },

  "indicators": {
    "rsi": {"value": 42.5, "zone": "neutral", "divergence": false},
    "ema": {"ema_34": 3345.00, "ema_89": 3360.00, "trend_alignment": "bullish"},
    "macd": {"histogram": 1.5, "divergence": false, "momentum": "recovering"},
    "atr": {"value": 13.75, "regime": "normal"},
    "adx": {"value": 32.5, "trend_strength": "strong"}
  },

  "confidence_breakdown": {
    "base_score": 50,
    "timeframe_alignment": 10,
    "fibonacci_confluence": 10,
    "rsi_confirmation": 8,
    "ema_alignment": 10,
    "macd_confirmation": 5,
    "session_bonus": 10,
    "regime_bonus": 15,
    "penalties": {"alternative_30pct": -15, "subtotal": -15},
    "bonuses": {"spread_ok": 3, "subtotal": 3},
    "total": 78,
    "grade": "B+",
    "recommendation": "TRADE_WITH_STANDARD_SIZE"
  },

  "session_context": {
    "current_session": "london_ny_overlap",
    "session_quality": "optimal",
    "session_modifier": 10
  },

  "spread_check": {
    "current_spread_pips": 2.5,
    "max_allowed_pips": 4.0,
    "spread_ok": true
  }
}
```

---

### No-Trade Signal

```json
{
  "timestamp": "2024-08-21T14:30:00Z",
  "symbol": "XAUUSD",
  "signal": {
    "action": "NO_TRADE",
    "confidence": 0,
    "reason": "ambiguous_wave_count"
  },
  "wave_analysis": {
    "h4_trend": "unclear",
    "current_wave": "uncertain",
    "primary_scenario": {"description": "Wave 3 extension", "probability": 50},
    "alternative_scenario": {"description": "Wave 5 truncation", "probability": 50},
    "wait_for": "Break above 3400 or below 3320 for confirmation"
  }
}
```

---

## REQUIRED FIELDS

### Always Required

| Field | Type | Description |
|-------|------|-------------|
| timestamp | ISO 8601 | Signal generation time |
| symbol | string | Always "XAUUSD" |
| signal.action | string | "BUY", "SELL", or "NO_TRADE" |
| signal.confidence | int | 0-100 |
| signal.reason | string | Brief explanation |

### Required for BUY/SELL

| Field | Type | Description |
|-------|------|-------------|
| signal.entry_price | float | Entry price (2 decimals) |
| signal.stop_loss | float | Stop loss price |
| signal.take_profit | array | Array of TP levels |
| signal.risk_reward | float | Overall R:R ratio |
| wave_analysis.h4_trend | string | "bullish" or "bearish" |
| wave_analysis.current_wave | string | Wave position description |
| wave_analysis.rules_check | object | Validation of 3 EW rules |
| wave_analysis.invalidation_price | float | Price that invalidates count |
| confidence_breakdown | object | Score breakdown |

### Required for NO_TRADE

| Field | Type | Description |
|-------|------|-------------|
| signal.reason | string | Reason code for no trade |
| wave_analysis.wait_for | string | Condition to re-evaluate |

---

## VALID REASON CODES

### For NO_TRADE Actions

| Code | Description |
|------|-------------|
| ambiguous_wave_count | Multiple valid interpretations |
| mid_wave_position | Not at wave completion |
| low_confidence | Confidence < 45% |
| rule_violation | Elliott Wave rule violated |
| poor_regime | Ranging/choppy market |
| wrong_session | Asian/off-hours trading |
| high_spread | Spread exceeds limit |
| news_blackout | High-impact news pending |

---

## TAKE-PROFIT STRUCTURE

Each TP level must include:

```json
{
  "level": "TP1",
  "price": 3380.00,
  "fib_basis": "61.8% of Wave 1",
  "probability": 80,
  "close_percent": 40,
  "risk_reward": 1.73
}
```

| Field | Description |
|-------|-------------|
| level | TP1, TP2, or TP3 |
| price | Target price |
| fib_basis | Fibonacci level used |
| probability | Likelihood of reaching (%) |
| close_percent | Position % to close |
| risk_reward | R:R at this level |

---

## TRAILING STOP STRUCTURE

```json
{
  "trailing_stop": {
    "activation_trigger": "TP1_HIT",
    "trail_distance_atr": 1.5,
    "breakeven_buffer_pips": 5
  }
}
```

| Field | Description |
|-------|-------------|
| activation_trigger | When to activate ("TP1_HIT" or "PROFIT_1R") |
| trail_distance_atr | ATR multiplier for trail |
| breakeven_buffer_pips | Pips above entry for BE move |

---

## WAVE ANALYSIS DETAIL

```json
{
  "wave_analysis": {
    "h4_trend": "bullish",
    "current_wave": "wave_4_complete",
    "wave_position": "entering_wave_5",
    "wave_count_valid": true,
    "rules_check": {
      "rule_1_wave2_valid": true,
      "rule_2_wave3_not_shortest": true,
      "rule_3_wave4_no_overlap": true
    },
    "wave_measurements": {
      "wave_1": {"start": 3280, "end": 3350, "length": 70},
      "wave_2": {"start": 3350, "end": 3310, "retrace_pct": 57.1},
      "wave_3": {"start": 3310, "end": 3420, "extension_pct": 157.1},
      "wave_4": {"start": 3420, "end": 3340, "retrace_pct": 36.4}
    },
    "invalidation_price": 3310.00,
    "primary_scenario": {
      "description": "Wave 5 targeting 3418-3455",
      "probability": 70
    },
    "alternative_scenario": {
      "description": "Complex correction W-X-Y",
      "probability": 30
    }
  }
}
```

---

## INDICATOR FORMAT

```json
{
  "indicators": {
    "rsi": {
      "value": 42.5,
      "zone": "neutral",
      "divergence": false,
      "confirmation": "bullish_ok"
    },
    "ema": {
      "ema_34": 3345.00,
      "ema_89": 3360.00,
      "price_position": "near_ema_34_support",
      "trend_alignment": "bullish"
    },
    "macd": {
      "macd_line": -2.5,
      "signal_line": -4.0,
      "histogram": 1.5,
      "divergence": false,
      "momentum": "recovering"
    },
    "atr": {
      "value": 13.75,
      "avg_20": 14.50,
      "regime": "normal"
    },
    "adx": {
      "value": 32.5,
      "di_plus": 28.0,
      "di_minus": 15.0,
      "trend_strength": "strong"
    }
  }
}
```

---

## VALIDATION CHECKLIST

Before outputting signal, verify:

1. [ ] Response is ONLY a JSON code block
2. [ ] All required fields present
3. [ ] Prices have 2 decimal places
4. [ ] Confidence is 0-100 integer
5. [ ] TP percentages sum to 100
6. [ ] Stop loss is beyond invalidation price
7. [ ] Risk:Reward > 1.5 for valid trades
8. [ ] rules_check all true for BUY/SELL signals
