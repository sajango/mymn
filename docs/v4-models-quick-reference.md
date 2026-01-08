# v4 Models - Quick Reference Guide
**Last Updated**: 2026-01-08
**Version**: Phase 2 - Model Updates

---

## New v4 Model Classes (6 total)

### 1. MarketRegime
Market condition classification and recommendations.

```python
classification: str  # trending_strong|trending_weak|ranging|choppy
trend_direction: str # bullish|bearish|neutral
confidence_modifier: int  # Adjustment to signal confidence (-20 to +20)
```

**Use Case**: Adjust signal quality based on market conditions
**Example**: `trending_strong` → +10 confidence bonus

---

### 2. TimeframeWave
Single timeframe Elliott Wave analysis.

```python
degree: str           # Primary|Intermediate|Minor|Minute
current_wave: str     # Wave label: (3), 4, [c], etc.
wave_label: str       # Full context: "(3) of Primary"
position_in_sequence: str  # Sequence: impulse_wave_3_of_5
structure: str        # impulse|corrective
```

**Use Case**: Track wave structure across multiple timeframes
**Example**: H4 in Wave 3 of primary impulse

---

### 3. WaveStructure
Multi-timeframe wave alignment (H4/H1/M30/M15).

```python
h4: Optional[TimeframeWave]       # Highest timeframe
h1: Optional[TimeframeWave]       # Mid timeframe
m30: Optional[TimeframeWave]      # Lower timeframe
m15: Optional[TimeframeWave]      # Lowest timeframe
alignment_status: str              # ALIGNED|CONFLICT|WARNING
alignment_confidence_modifier: int # Multi-TF alignment bonus/penalty
```

**Use Case**: Validate wave counts across timeframe hierarchy
**Example**:
- H4 in Wave 3
- H1 in Wave 3 (aligned)
- M30 in sub-Wave 1 (nested)
- Status: ALIGNED (+15 confidence)

---

### 4. TakeProfitConfluence
Confluence factor tracking for TP levels.

```python
count: int                 # Number of confluence factors
details: list[str]        # Factor descriptions
```

**Use Case**: Document why a TP level is selected
**Example**:
- Count: 3
- Details: ["0.618 Fib", "Swing High", "EMA Resistance"]

---

### 5. PreTradeChecks
Pre-execution validation summary.

```python
trading_allowed: bool          # Overall permission
regime_suitable: bool          # Market regime OK
session_suitable: bool         # Trading session OK
spread_ok: bool                # Spread within limits
risk_budget_available: bool    # Risk budget remaining
all_checks_passed: bool        # All validations passed
```

**Use Case**: Quick validation summary before execution
**Example**: Check if market regime recommends skipping Elliott Wave

---

### 6. TrailingStopConfig & PositionSize
Position management and sizing.

```python
# TrailingStopConfig
activation_trigger: str    # TP1_HIT|profit_1R
trail_distance_atr: float  # 1.5x ATR typical

# PositionSize
recommended_lots: float    # 0.05, 0.1, etc.
risk_percent: float        # 1.0, 1.5, 2.0%
risk_amount_usd: float     # Dollar risk amount
atr_based: bool           # Calculated by ATR
```

---

## Enhanced Fields in Existing Models

### TakeProfit - NEW v4 Fields (6)

```python
# Fibonacci and confluence tracking
fib_basis: Optional[str]           # "0.618", "1.0", "1.618"
confluence_count: Optional[int]    # 1-5 factors

# Probability and risk metrics
probability: Optional[int]         # 0-100% hit probability
risk_reward: Optional[float]       # R:R for this specific level
rr_adjusted: bool                  # Min threshold adjustment applied
note: Optional[str]                # Additional notes
```

**Example**:
```python
{
  "level": "TP1",
  "price": 2010.0,
  "close_percent": 40,
  "fib_basis": "0.618",
  "confluence_count": 3,
  "probability": 85,
  "risk_reward": 1.5,
  "note": "Strong resistance cluster"
}
```

---

### TradingSignal - NEW v4 Top-Level Fields (3)

```python
# Market context
market_regime: Optional[MarketRegime]      # Market condition
wave_structure: Optional[WaveStructure]    # Multi-TF waves
pre_trade_checks: Optional[PreTradeChecks] # Validation summary
```

**Usage**: Optional but recommended for v4 signals

---

### Signal (Trade Instruction) - NEW Fields

```python
stop_loss_atr: Optional[float]              # ATR-based SL distance
trailing_stop: Optional[TrailingStopConfig] # Trailing config
position_size: Optional[PositionSize]       # Size details
```

---

### WaveAnalysis - NEW Field

```python
wave_position: Optional[str]  # Detailed position: "Wave 3 of (3) of Primary"
```

**Note**: Extracted from `signal.elliott_wave_analysis` during normalization

---

## Data Normalization (v4 Extended)

### 6-Step Process in parse_trading_signal()

| Step | Handles | Example |
|------|---------|---------|
| 1 | Direction → Action | BULLISH → BUY |
| 2 | Confidence format | 0.85 → 85, "HIGH" → 80 |
| 3 | R:R extraction | "1:3.5" → 3.5, dict → float |
| 4 | Wave position | Multiple locations → single source |
| 5 | TP array consolidation | take_profit_1/2/3 → array |
| 6 | v4 field preservation | New fields passed through |

---

## Backward Compatibility

### All v4 Features Are Optional

```python
# v3 minimal signal - still works
signal = {
  "timestamp": "2026-01-08T10:00:00Z",
  "symbol": "XAUUSD",
  "signal": {
    "action": "BUY",
    "entry_price": 2000.0,
    "confidence": 85
  }
}

# v4 extended signal - all new fields optional
signal_v4 = {
  **signal,  # v3 core
  "market_regime": {...},    # NEW
  "wave_structure": {...},   # NEW
  "pre_trade_checks": {...}, # NEW
  "signal": {
    **signal["signal"],      # v3 core
    "trailing_stop": {...},  # NEW
    "position_size": {...}   # NEW
  }
}
```

---

## Integration Checklist

When implementing v4 signal output:

- [ ] Include `market_regime` classification
- [ ] Add `wave_structure` for multi-timeframe context
- [ ] Provide `pre_trade_checks` validation summary
- [ ] Enhance TakeProfit with `fib_basis` and `confluence_count`
- [ ] Set `trailing_stop` configuration if applicable
- [ ] Include `position_size` recommendations
- [ ] Populate `wave_position` in WaveAnalysis
- [ ] Calculate `confidence_modifier` from regime
- [ ] Document `penalty_reasons` in ConfidenceBreakdown

---

## Example v4 Complete Signal

```json
{
  "timestamp": "2026-01-08T10:30:00Z",
  "symbol": "XAUUSD",
  "signal": {
    "action": "BUY",
    "entry_price": 2000.00,
    "stop_loss": 1990.00,
    "take_profit": [
      {
        "level": "TP1",
        "price": 2010.00,
        "close_percent": 40,
        "fib_basis": "0.618",
        "confluence_count": 3,
        "probability": 85,
        "risk_reward": 1.5
      }
    ],
    "confidence": 85,
    "trailing_stop": {
      "activation_trigger": "TP1_HIT",
      "trail_distance_atr": 1.5
    },
    "position_size": {
      "recommended_lots": 0.05,
      "risk_percent": 1.5,
      "atr_based": true
    }
  },
  "market_regime": {
    "classification": "trending_strong",
    "trend_direction": "bullish",
    "confidence_modifier": 10,
    "elliott_wave_reliability": "high"
  },
  "wave_structure": {
    "h4": {
      "current_wave": "3",
      "degree": "Primary",
      "structure": "impulse"
    },
    "h1": {
      "current_wave": "3",
      "degree": "Intermediate",
      "structure": "impulse"
    },
    "alignment_status": "ALIGNED",
    "alignment_confidence_modifier": 15
  },
  "wave_analysis": {
    "h4_trend": "bullish",
    "current_wave": "3",
    "wave_position": "Wave 3 of Primary up"
  },
  "pre_trade_checks": {
    "trading_allowed": true,
    "regime_suitable": true,
    "all_checks_passed": true
  }
}
```

---

## Documentation Links

- **Full API Docs**: `docs/api-documentation.md` (Lines 351-634)
- **Signal Parser Code**: `src/signal_parser.py`
- **Data Models**: `src/signal_parser.py` (Lines 26-391)

---

**Status**: Ready for integration
**Compatibility**: 100% backward compatible
**Version**: Elliott Wave v4.0
