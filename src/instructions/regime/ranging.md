# RANGING MARKET REGIME

## Regime Identification

| Indicator | Threshold | Current Status |
|-----------|-----------|----------------|
| ADX | < 15 | No clear trend |
| EMA Spread | < 0.3% | EMAs converged/crossing |
| ATR | Low (< 0.5x avg) | Compressed volatility |

**Regime Classification**: `ranging`
**Elliott Wave Reliability**: LOW
**Recommended Action**: USE SUPPORT/RESISTANCE STRATEGY

---

## TRADING APPROACH

### Elliott Wave Limitations

In ranging markets, Elliott Wave analysis is NOT recommended:

1. **Wave Counts Unreliable**: Multiple valid interpretations
2. **False Breakouts Common**: Waves often fail
3. **Skip EW Analysis**: Use S/R levels instead
4. **Confidence Modifier**: -15 points

### Alternative Strategy

| Approach | Action |
|----------|--------|
| Primary | Trade bounces from support/resistance |
| Entry | Wait for price to reach range boundaries |
| Exit | Target opposite side of range |
| Stop | Just outside the range boundary |

---

## SUPPORT/RESISTANCE TRADING

### Identify Range Boundaries

```json
{
  "range_analysis": {
    "range_high": 3420.00,
    "range_low": 3340.00,
    "range_size_pips": 80,
    "midpoint": 3380.00,
    "boundaries_tested": {
      "high_tests": 3,
      "low_tests": 4
    }
  }
}
```

### Entry Conditions

**BUY at Range Low**:
- Price within 5-10 pips of range low
- RSI < 35 (oversold)
- Previous support holds
- Stop below range low (10-15 pips)
- Target: Range midpoint or high

**SELL at Range High**:
- Price within 5-10 pips of range high
- RSI > 65 (overbought)
- Previous resistance holds
- Stop above range high (10-15 pips)
- Target: Range midpoint or low

---

## RISK PARAMETERS

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Position Size | 50% standard | Low confidence |
| Risk per Trade | 0.5-0.75% | Reduced allocation |
| R:R Minimum | 1.5:1 | Tighter ranges |
| Confidence Modifier | -15 | Regime penalty |
| Max Trades/Day | 1-2 | Limited setups |

---

## WHEN TO SKIP TRADING

**No Trade Conditions**:
- Price in middle 60% of range
- RSI between 40-60
- No clear S/R level nearby
- Breakout attempt in progress (wait for confirmation)

---

## BREAKOUT MONITORING

### Prepare for Regime Change

Ranging markets eventually break out. Watch for:

| Signal | Indication |
|--------|------------|
| ADX rising above 15 | Trend developing |
| Volume surge | Breakout likely |
| EMA separation | Direction established |
| ATR expansion | Volatility returning |

### Breakout Confirmation

Do NOT chase initial breakout. Wait for:
1. Close above/below range boundary
2. Retest of broken level (new support/resistance)
3. ADX > 20 confirmation

---

## OUTPUT FORMAT

When in `ranging` regime:

```json
{
  "timestamp": "2024-08-21T14:30:00Z",
  "symbol": "XAUUSD",
  "signal": {
    "action": "NO_TRADE",
    "confidence": 35,
    "reason": "ranging_market"
  },
  "market_regime": {
    "classification": "ranging",
    "adx_14": 12.5,
    "trend_strength": "absent",
    "ema_spread_percent": 0.2,
    "elliott_wave_reliability": "not_recommended",
    "confidence_modifier": -15,
    "recommended_action": "wait",
    "alternative_strategy": "support_resistance_bounce"
  },
  "range_analysis": {
    "range_high": 3420.00,
    "range_low": 3340.00,
    "current_position": "mid_range",
    "wait_for": "price_at_boundary"
  }
}
```

---

## RANGE BOUNDARY SIGNAL

If price IS at range boundary:

```json
{
  "signal": {
    "action": "BUY",
    "entry_price": 3345.00,
    "stop_loss": 3330.00,
    "take_profit": [
      {"level": "TP1", "price": 3380.00, "close_percent": 60},
      {"level": "TP2", "price": 3415.00, "close_percent": 40}
    ],
    "confidence": 55,
    "reason": "range_low_bounce"
  },
  "wave_analysis": {
    "h4_trend": "ranging",
    "current_wave": "not_applicable",
    "strategy": "support_resistance"
  }
}
```

---

## WARNING SIGNS

### False Breakout Indicators

- Breakout on low volume
- Immediate reversal after break
- ADX still < 15 after "breakout"
- EMA still converged

### Action if Trapped

If caught in false breakout:
- Cut losses immediately
- Do NOT average down
- Wait for next range boundary

---

## PATIENCE REQUIRED

**Key Insight**: Ranging markets test patience. It's better to:
- Miss trades than force bad entries
- Wait for clear breakout than catch false ones
- Accept lower trading frequency

**Expected Trade Frequency**: 1-2 trades per day maximum
