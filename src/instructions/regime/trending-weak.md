# WEAK TRENDING MARKET REGIME

## Regime Identification

| Indicator | Threshold | Current Status |
|-----------|-----------|----------------|
| ADX | 15 - 24 | Trend present but weak |
| EMA Spread | 0.3% - 0.8% | EMAs moderately separated |
| ATR | Normal to Low | May be compressing |

**Regime Classification**: `trending_weak`
**Elliott Wave Reliability**: MEDIUM
**Recommended Action**: CAUTIOUS ANALYSIS

---

## TRADING APPROACH

### Cautious Elliott Wave Analysis

In weak trending markets, Elliott Wave requires extra confirmation:

1. **Require More Confluence**: Multiple confirmations needed
2. **Wait for Clear Setups**: Avoid ambiguous patterns
3. **Reduced Position Size**: 50-75% of standard
4. **Confidence Modifier**: +5 points

### Entry Strategy

| Wave Position | Entry Quality | Action |
|---------------|---------------|--------|
| Wave 2 Complete | Good | BUY/SELL with extra confirmation |
| Wave 4 Complete | Good | BUY/SELL with extra confirmation |
| Wave 5 Complete | Moderate | Reversal with caution |
| Mid-Wave | Skip | DO NOT TRADE |

### Required Extra Confirmations

Before entering, require at least 3 of 5:
- [ ] RSI in optimal zone (35-50 for buy, 50-65 for sell)
- [ ] Price at key Fibonacci level (50-78.6%)
- [ ] EMA support/resistance test
- [ ] MACD histogram direction change
- [ ] Volume confirmation

---

## FIBONACCI TARGETS

Use conservative targets:
- **Primary Target**: 100% of Wave 1 (not 161.8%)
- **Extended Target**: 127.2% of Wave 1
- **Avoid**: 200%+ targets in weak trends

### Target Probability Adjustment

| Target | Strong Trend | Weak Trend |
|--------|--------------|------------|
| 100% | 85% | 75% |
| 127% | 70% | 55% |
| 161.8% | 60% | 35% |
| 200% | 45% | 20% |

---

## STOP LOSS PLACEMENT

Wider stops needed in weak trends:

| Position | Stop Placement | ATR Alternative |
|----------|----------------|-----------------|
| After Wave 2 | Below Wave 2 low - buffer | Entry - (ATR × 2.5) |
| After Wave 4 | Below Wave 4 low - buffer | Entry - (ATR × 2.0) |

**Buffer**: Add 5-10 pips extra to account for noise

---

## INDICATOR ALIGNMENT

### Stricter Requirements

For BUY signals:
- Price > EMA 89 (not just > EMA 34)
- RSI 35-50 (must be oversold territory for reversal)
- MACD histogram already turning (not just about to)
- ADX 15-24 but stable or rising

For SELL signals:
- Price < EMA 89
- RSI 50-65
- MACD histogram clearly negative and extending
- ADX 15-24 with stable or rising reading

### Pattern Preference

Prefer higher-probability patterns:
- Zigzag corrections (clear A-B-C)
- Triangle breakouts (Wave 4 in triangle)
- Avoid complex corrections (W-X-Y, double combinations)

---

## RISK PARAMETERS

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Position Size | 50-75% standard | Lower confidence regime |
| Risk per Trade | 0.75-1.0% | Reduced allocation |
| R:R Minimum | 2.0:1 | Higher requirement |
| Trailing Stop | ATR × 2.0 | Wider trail for noise |
| Confidence Modifier | +5 | Small regime bonus |

---

## WAVE COUNTING GUIDANCE

### Wave 3 in Weak Trends

- May NOT reach 161.8% extension
- Target 100-127% of Wave 1
- Take partial profits earlier (at 100%)

### Wave 5 Behavior

- Truncation more common
- May NOT exceed Wave 3 high
- Exit on first sign of divergence

### Correction Depth

- Wave 2 often deeper (61.8-78.6%)
- Wave 4 may overlap slightly with Wave 1 (validate carefully)

---

## OUTPUT MODIFIERS

When in `trending_weak` regime:

```json
{
  "market_regime": {
    "classification": "trending_weak",
    "adx_14": 18.5,
    "trend_strength": "moderate",
    "ema_spread_percent": 0.5,
    "elliott_wave_reliability": "medium",
    "confidence_modifier": 5,
    "recommended_action": "cautious_analysis",
    "warnings": ["Weak trend - require extra confirmation"]
  }
}
```

---

## TRANSITION MONITORING

### Watch for Regime Change

**To Strong Trend (ADX rising above 25)**:
- Action: Resume standard position sizing
- Pattern: Look for impulse wave resumption

**To Ranging (ADX falling below 15)**:
- Action: Switch to support/resistance strategy
- Pattern: Elliott Wave less reliable

### Early Warning Signs

- ADX declining for 3+ periods
- EMA spread narrowing rapidly
- Price whipsawing around EMAs
- False breakouts increasing

---

## COMMON MISTAKES TO AVOID

1. **Overtrading**: Fewer setups qualify in weak trends
2. **Full Position Size**: Always reduce in weak trends
3. **Extended Targets**: Use conservative projections
4. **Ignoring Confirmations**: Extra confluences are mandatory
5. **Fighting the Regime**: Accept lower trading frequency
