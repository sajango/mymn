# HIGH VOLATILITY MARKET REGIME

## Regime Identification

| Indicator | Threshold | Current Status |
|-----------|-----------|----------------|
| ATR | > 2.0x average | Extreme volatility |
| ATR Percentile | > 80th | Top quintile volatility |
| Price Swings | > 3 ATR per candle | Large moves |

**Regime Classification**: `volatile`
**Elliott Wave Reliability**: CONDITIONAL
**Recommended Action**: WIDE STOPS, REDUCED SIZE

---

## TRADING APPROACH

### Volatility-Adjusted Analysis

High volatility requires significant adjustments:

1. **Wide Stops Required**: Standard stops will get hit
2. **Reduced Position Size**: 50% or less
3. **Wait for Clarity**: Noise obscures patterns
4. **Confidence Modifier**: -5 to -10 points

### When to Trade

| ATR Condition | Action |
|---------------|--------|
| 2.0x - 2.5x avg | Trade with 50% size, wide stops |
| 2.5x - 3.0x avg | Alert only, no auto-trade |
| > 3.0x avg | NO TRADE - market too chaotic |

---

## STOP LOSS ADJUSTMENTS

### Standard vs Volatile Stops

| Position | Standard Stop | Volatile Stop |
|----------|---------------|---------------|
| After Wave 2 | ATR × 2.0 | ATR × 3.0 |
| After Wave 4 | ATR × 1.5 | ATR × 2.5 |
| After Wave 5 | ATR × 1.5 | ATR × 2.5 |

### Buffer Calculation

```
volatile_stop = standard_stop × volatility_multiplier

volatility_multiplier = min(atr_current / atr_avg, 2.0)
```

---

## POSITION SIZING

### Reduced Risk Allocation

| ATR Ratio | Position Size | Risk % |
|-----------|---------------|--------|
| 2.0x - 2.5x | 50% standard | 0.75% |
| 2.5x - 3.0x | 25% standard | 0.5% |
| > 3.0x | 0% (no trade) | 0% |

### Lot Size Formula

```
adjusted_lots = standard_lots × (1 / volatility_multiplier)
```

---

## WAVE COUNTING ADJUSTMENTS

### Pattern Recognition

In high volatility:
- Wave structures may be exaggerated
- Corrections can be deeper than guidelines
- Extensions can be more extreme

### Fibonacci Adjustments

| Level | Standard | Volatile |
|-------|----------|----------|
| Wave 2 retracement | 50-78.6% | 38.2-88.6% (wider range) |
| Wave 3 extension | 161.8-261.8% | 100-300%+ (wider range) |
| Wave 4 retracement | 23.6-50% | 38.2-61.8% (deeper) |

---

## TAKE-PROFIT STRATEGY

### Faster Profit Taking

In volatile markets, take profits sooner:

| Standard TP | Volatile TP | Rationale |
|-------------|-------------|-----------|
| 40% at TP1 | 50% at TP1 | Secure profits faster |
| 35% at TP2 | 35% at TP2 | Standard |
| 25% at TP3 | 15% at TP3 | Reduced runner |

### Trailing Stop

| Standard Trail | Volatile Trail |
|----------------|----------------|
| ATR × 1.5 | ATR × 2.0-2.5 |

---

## OUTPUT FORMAT

When in `volatile` regime:

```json
{
  "market_regime": {
    "classification": "volatile",
    "atr_current": 28.50,
    "atr_avg_20": 14.25,
    "atr_ratio": 2.0,
    "atr_percentile": 85,
    "volatility_state": "high",
    "confidence_modifier": -5,
    "recommended_action": "trade_with_caution",
    "adjustments": {
      "stop_multiplier": 1.5,
      "position_size_modifier": 0.5,
      "trail_distance_modifier": 1.5
    },
    "warnings": [
      "High volatility detected",
      "Stops widened to 1.5x standard",
      "Position size reduced to 50%"
    ]
  }
}
```

---

## ENTRY TIMING

### Wait for Volatility Pause

Best entries in volatile markets:
- After a volatility spike subsides
- During consolidation within the move
- At major Fibonacci levels (more likely to hold)

### Avoid

- Chasing moves immediately after spikes
- Trading during news releases
- Counter-trend entries (momentum too strong)

---

## NEWS AND EVENTS

### Volatility Causes

High volatility often caused by:
- FOMC / Fed announcements
- NFP releases
- CPI data
- Geopolitical events

### Action During News

| Phase | Action |
|-------|--------|
| 30 min before | Close or reduce positions |
| During event | NO NEW TRADES |
| 15 min after | Wait for dust to settle |
| Settled | Assess new regime, trade if appropriate |

---

## REGIME TRANSITION

### Volatility Declining

Watch for:
- ATR returning to normal (< 1.5x avg)
- Smaller candle ranges
- Consolidation patterns

**Action**: Gradually return to standard parameters

### Volatility Spiking

Watch for:
- ATR breaking above 2x avg
- News event approaching
- Major level breakout

**Action**: Immediately reduce size or close positions

---

## CRITICAL RULES

1. **Never use standard stops** in volatile markets
2. **Never use full position size** - 50% maximum
3. **Never fight the volatility** - go with momentum
4. **Never enter during spikes** - wait for pullback
5. **Never ignore the regime** - adjust or sit out
