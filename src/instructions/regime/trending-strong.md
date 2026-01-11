# STRONG TRENDING MARKET REGIME

## Regime Identification

| Indicator | Threshold | Current Status |
|-----------|-----------|----------------|
| ADX | ≥ 25 | Strong trend present |
| EMA Spread | > 0.8% | EMAs clearly separated |
| ATR | Normal (0.5x - 2.0x avg) | Standard volatility |

**Regime Classification**: `trending_strong`
**Elliott Wave Reliability**: HIGH
**Recommended Action**: FULL ANALYSIS

---

## TRADING APPROACH

### Full Elliott Wave Analysis

In strong trending markets, Elliott Wave patterns are most reliable:

1. **Trust the Wave Count**: Primary counts have 70%+ probability
2. **Trend-Following Preferred**: Trade in direction of H4 trend
3. **Standard Position Size**: Full risk allocation (1.5%)
4. **Confidence Modifier**: +15 points

### Entry Strategy

| Wave Position | Entry Quality | Action |
|---------------|---------------|--------|
| Wave 2 Complete | Excellent | BUY (bullish) / SELL (bearish) |
| Wave 4 Complete | Excellent | BUY (bullish) / SELL (bearish) |
| Wave 5 Complete | Good | Reversal signal |
| Mid-Wave | Poor | WAIT |

### Fibonacci Targets

Use full extension levels for Wave 3:
- **Primary Target**: 161.8% of Wave 1
- **Extended Target**: 200% of Wave 1
- **Maximum Target**: 261.8% of Wave 1 (strong trends)

### Stop Loss Placement

| Position | Stop Placement | ATR Alternative |
|----------|----------------|-----------------|
| After Wave 2 | Below Wave 2 low | Entry - (ATR × 2.0) |
| After Wave 4 | Below Wave 4 low | Entry - (ATR × 1.5) |
| After Wave 5 | Above Wave 5 high | Entry + (ATR × 1.5) |

---

## INDICATOR ALIGNMENT

### Required Confirmations

For BUY signals in bullish trend:
- Price > EMA 34 > EMA 89 (strong bullish)
- RSI 40-60 at wave completion (room to rise)
- MACD histogram turning positive
- ADX > 25 with +DI > -DI

For SELL signals in bearish trend:
- Price < EMA 34 < EMA 89 (strong bearish)
- RSI 40-60 at wave completion (room to fall)
- MACD histogram turning negative
- ADX > 25 with -DI > +DI

### Divergence Handling

In strong trends, divergence is a WARNING but not immediate reversal:
- RSI divergence at Wave 5: Tighten stops, don't exit immediately
- Wait for price confirmation before counter-trend entry

---

## RISK PARAMETERS

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Position Size | 100% standard | High confidence regime |
| Risk per Trade | 1.5% | Standard allocation |
| R:R Minimum | 1.5:1 | Standard requirement |
| Trailing Stop | ATR × 1.5 | Standard trail |
| Confidence Modifier | +15 | Regime bonus |

---

## WAVE COUNTING GUIDANCE

### Wave 3 Characteristics (Strong Trends)

In strong trending markets, Wave 3:
- Often extends to 200-261.8% of Wave 1
- Volume should be HIGHEST of all waves
- RSI should reach 70-80 (overbought is OK)
- MACD should show peak histogram bars
- **Do NOT exit Wave 3 early** - let it run

### Wave 5 Characteristics

In strong trends, Wave 5:
- May extend rather than truncate
- Watch for divergence but don't anticipate
- Exit when divergence + momentum loss confirmed

---

## OUTPUT MODIFIERS

When in `trending_strong` regime, include:

```json
{
  "market_regime": {
    "classification": "trending_strong",
    "adx_14": 32.5,
    "trend_strength": "strong",
    "ema_spread_percent": 1.2,
    "elliott_wave_reliability": "high",
    "confidence_modifier": 15,
    "recommended_action": "full_analysis"
  }
}
```

---

## COMMON PATTERNS

### Impulse Extensions

Strong trends often show:
- Extended Wave 3 (most common)
- Extended Wave 5 (less common)
- Shallow Wave 2 and Wave 4 corrections

### Alternation

Expect clear alternation:
- If Wave 2 is sharp (zigzag) → Wave 4 is flat
- If Wave 2 is flat → Wave 4 is sharp (zigzag) or triangle

---

## WARNING SIGNS

Watch for regime transition when:
- ADX starts declining from peak (< 25)
- EMA spread narrowing
- Volume decreasing
- Successive wave extensions getting smaller

**Action**: Reduce position size, tighten stops, prepare for ranging regime
