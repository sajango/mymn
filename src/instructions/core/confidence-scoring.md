# CONFIDENCE SCORING SYSTEM

## BASE SCORE

Start with **50 points** as the base confidence score.

---

## SCORING COMPONENTS

### Positive Modifiers (Bonuses)

| Factor | Points | Condition |
|--------|--------|-----------|
| Timeframe Alignment | +10 to +15 | H4, H1, M30 wave counts agree on direction |
| Fibonacci Confluence | +10 | Entry at multiple Fibonacci levels |
| RSI Confirmation | +8 to +10 | RSI in optimal zone for wave position |
| RSI/MACD Divergence | +15 | Divergence detected at Wave 5/C completion |
| EMA Alignment | +10 | Price near EMA support/resistance, trend aligned |
| MACD Confirmation | +5 | MACD histogram confirms wave direction |
| Volume Confirmation | +5 | Volume pattern matches wave characteristics |
| Session Bonus | +5 to +10 | London, NY, or London/NY overlap |
| Regime Bonus | +5 to +15 | Strong trending market (ADX ≥ 25) |
| Spread OK | +3 | Spread within acceptable limits |

### Negative Modifiers (Penalties)

| Factor | Points | Condition |
|--------|--------|-----------|
| High Ambiguity | -15 | Alternative scenario probability > 40% |
| Low Volatility | -10 | ATR regime = low_volatility |
| Extreme Volatility | -5 | ATR regime = extreme |
| Poor Session | -15 to -20 | Asian or off-hours trading |
| Weak Regime | -15 to -30 | Ranging or choppy market (ADX < 15) |
| Rule Violation | -100 | ANY Elliott Wave rule violated → Signal INVALID |

---

## CONFIDENCE BREAKDOWN FORMAT

```json
{
  "confidence_breakdown": {
    "base_score": 50,
    "wave_rules_valid": 0,
    "timeframe_alignment": 10,
    "fibonacci_confluence": 10,
    "rsi_confirmation": 8,
    "ema_alignment": 10,
    "macd_confirmation": 5,
    "session_bonus": 10,
    "regime_bonus": 15,
    "penalties": {
      "alternative_30pct": -15,
      "subtotal": -15
    },
    "bonuses": {
      "spread_ok": 3,
      "subtotal": 3
    },
    "total": 78,
    "grade": "B+",
    "recommendation": "TRADE_WITH_STANDARD_SIZE"
  }
}
```

---

## SCORE INTERPRETATION

| Score Range | Grade | Action |
|-------------|-------|--------|
| 75-100 | A/A+ | **Full position** - High confidence trade |
| 60-74 | B/B+ | **Half position** - Medium confidence |
| 45-59 | C | **Alert only** - No auto-trade, monitor |
| 0-44 | D/F | **No trade** - Skip this signal |
| 0 | INVALID | Rule violation detected |

---

## POSITION SIZE MODIFIERS

| Confidence | Size Modifier | Risk % |
|------------|---------------|--------|
| 75-100% | 1.0x (Full) | Standard 1.5% |
| 60-74% | 0.5x (Half) | Reduced 0.75% |
| 45-59% | 0x (None) | Alert only |
| < 45% | 0x (None) | No trade |

### Additional Size Adjustments

| Condition | Size Modifier |
|-----------|---------------|
| High volatility (ATR > 2x avg) | 0.5x |
| Losing streak (≥ 2 consecutive) | 0.5x |
| Recovery mode active | 0.5x |
| Exceptional confluence (score ≥ 90) | 1.25x |

---

## RECOMMENDATION MAPPING

| Total Score | Recommendation |
|-------------|----------------|
| ≥ 90 | STRONG_BUY / STRONG_SELL |
| 75-89 | TRADE_WITH_STANDARD_SIZE |
| 60-74 | TRADE_WITH_REDUCED_SIZE |
| 45-59 | ALERT_ONLY |
| < 45 | NO_TRADE |
| 0 | INVALID_SIGNAL |

---

## CALCULATION SUMMARY

```
total_confidence = base_score (50)
                 + timeframe_alignment (0 to +15)
                 + fibonacci_confluence (0 to +10)
                 + rsi_confirmation (0 to +10)
                 + divergence_bonus (0 to +15)
                 + ema_alignment (0 to +10)
                 + macd_confirmation (0 to +5)
                 + volume_confirmation (0 to +5)
                 + session_modifier (-20 to +10)
                 + regime_modifier (-30 to +15)
                 - ambiguity_penalty (0 to -15)
                 - volatility_penalty (0 to -10)

# Clamp result to 0-100 range
final_confidence = min(max(total_confidence, 0), 100)

# Rule violation override
if any_rule_violated:
    final_confidence = 0
```
