# INDICATOR CONFLUENCE SCORING

## Purpose

Combine multiple technical indicators to **validate wave analysis** and adjust confidence scores. No single indicator is sufficient - confluence strengthens signals.

## Core Indicators

### RSI (Relative Strength Index)

| Wave | RSI Range | Signal |
|------|-----------|--------|
| Wave 2 end | 40-50 | Ready to rise, not oversold |
| Wave 4 end | 45-55 | Healthy correction |
| Wave 5 end | 60-70 | Divergence expected |
| Wave A end | 30-40 | Oversold bounce likely |
| Wave C end | 25-35 | Bullish divergence |

**Confluence Points**:
| Condition | Points |
|-----------|--------|
| RSI in optimal zone for wave | +10 |
| RSI divergence detected | +15 |
| RSI confirming momentum | +5 |

### EMA (34 & 89)

| Trend Structure | Description | Bias |
|-----------------|-------------|------|
| Price > EMA34 > EMA89 | Strong bullish | Long (+3) |
| Price > EMA89, < EMA34 | Weak bullish | Long (+2) |
| Price < EMA34 < EMA89 | Strong bearish | Short (+3) |
| Price < EMA89, > EMA34 | Weak bearish | Short (+2) |
| EMAs crossing | Transitioning | Neutral (+1) |

**Wave-Specific EMA Usage**:
| Wave | Expected EMA Behavior |
|------|----------------------|
| Wave 2 | Pullback to EMA 34 or EMA 89 = entry zone |
| Wave 4 | Pullback to EMA 34 = entry zone |
| Wave 5 | Price above both, momentum fading |

**Confluence Points**:
| Condition | Points |
|-----------|--------|
| Strong EMA alignment | +10 |
| Price at EMA support | +10 |
| Weak but aligned | +5 |

### MACD (12, 26, 9)

| Wave | Histogram Behavior | Signal |
|------|-------------------|--------|
| Wave 2 | Pulls toward zero, shrinking | Correction ending |
| Wave 3 | Peak bars, strongest | Impulse power |
| Wave 4 | Shrinks but stays positive | Healthy pullback |
| Wave 5 | Lower peak than Wave 3 | Divergence warning |

**MACD Interpretation**:
| Condition | Implication |
|-----------|-------------|
| Histogram confirms direction | Momentum aligned |
| Divergence detected | Reversal likely |
| Zero line cross | Trend change possible |
| Histogram shrinking | Correction ending |

**Confluence Points**:
| Condition | Points |
|-----------|--------|
| MACD confirms wave direction | +5 |
| MACD divergence detected | +15 |
| Histogram shrinking at correction end | +5 |

### ATR (Average True Range)

| Regime | Description | Action |
|--------|-------------|--------|
| Normal | ATR within average range | Standard stops |
| Low Volatility | ATR < 50th percentile | Reduce position, wider stops |
| High Volatility | ATR > 80th percentile | Wider stops, reduce size |
| Extreme | ATR > 2x average | Maximum caution |

**ATR Impact on Confidence**:
| Regime | Adjustment |
|--------|------------|
| Normal | +0 |
| Low Volatility | -10 |
| High Volatility | -5 |
| Extreme | -15 |

## Confluence Scoring Algorithm

```
Total Indicator Score = RSI_score + EMA_score + MACD_score + ATR_adjustment

Maximum possible: +40 points
```

### Scoring Matrix by Wave

| Wave Position | RSI Score | EMA Score | MACD Score | Max |
|---------------|-----------|-----------|------------|-----|
| Wave 2 end | +10 (35-50) | +10 (at EMA) | +5 (shrinking) | 25 |
| Wave 4 end | +10 (45-55) | +10 (at EMA34) | +5 (positive) | 25 |
| Wave 5 end | +5 (>65) | +5 (above) | +15 (divergence) | 25 |

## Combined Signal Validation

### BUY Signal Confluence

| Indicator | Required State | Points |
|-----------|---------------|--------|
| RSI | 35-50 range | +10 |
| EMA | Price at or above support | +10 |
| MACD | Histogram shrinking/positive | +5 |
| Divergence (any) | Present | +15 |
| **Total Required** | | **≥20** |

### SELL Signal Confluence

| Indicator | Required State | Points |
|-----------|---------------|--------|
| RSI | >65 or divergence | +10 |
| EMA | Price extended from EMAs | +5 |
| MACD | Divergence (lower peak) | +15 |
| Volume | Declining | +5 |
| **Total Required** | | **≥25** |

## Confluence with Fibonacci

**Fibonacci confluence adds reliability**:

| Confluence Type | Bonus |
|-----------------|-------|
| Fib level at pivot | +5 |
| Multiple Fibs align | +10 |
| Fib + EMA align | +10 |
| Triple confluence (Fib + EMA + round number) | +15 |

## Indicator Summary Table

| Wave | RSI | EMA 34 | EMA 89 | MACD | ATR |
|------|-----|--------|--------|------|-----|
| 1 | 30→50 | Crosses above | Approaches | Turns positive | Increasing |
| 2 | 40-50 | **Support** | **Support** | Shrinks | Decreasing |
| 3 | 70-80+ | Far above | Far above | **Peak** | **Highest** |
| 4 | 45-55 | **Support** | Above | Shrinks | Decreasing |
| 5 | 60-70 | Above | Above | **Lower peak** | Decreasing |
| A | 50→30 | Breaks below | Approaches | Negative | Increasing |
| B | 45-55 | Resistance | Resistance | Weak positive | Low |
| C | 25-35 | Below | Below | **Extreme negative** | High |

## Disqualifying Conditions

**REJECT signal if any present**:

| Condition | Disqualification |
|-----------|------------------|
| RSI returns to oversold in Wave 2 | Not Wave 2 |
| MACD crosses zero against trade | Momentum lost |
| EMA death cross forming | Trend reversing |
| ATR extreme (>2x) without adjustment | Risk too high |

## Final Confluence Score Integration

```
Base Confidence (from wave analysis): X points
+ Indicator Confluence Score: Y points
- ATR Regime Adjustment: Z points
= Final Confidence Score
```

**Signal only if Final Confidence ≥ 60%**
