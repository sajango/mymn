# PERFORMANCE CONTEXT

## Historical Performance Summary

### Overall Statistics
- **Win Rate**: {{WIN_RATE}}% ({{WIN_RATE_COMMENT}})
- **Total Trades**: Collecting data...

### Performance by Wave Position
- **Best Performing**: {{BEST_WAVE}}
- **Worst Performing**: {{WORST_WAVE}}

### Performance by Session
- **Best Session**: {{BEST_SESSION}}
- **Worst Session**: {{WORST_SESSION}}

## Confidence-Based Win Rates

| Confidence Level | Win Rate | Sample Size |
|------------------|----------|-------------|
| 80%+ | {{WIN_RATE_80}}% | {{SAMPLE_80}} trades |
| 70%+ | {{WIN_RATE_70}}% | {{SAMPLE_70}} trades |
| 60%+ | {{WIN_RATE_60}}% | {{SAMPLE_60}} trades |
| 50%+ | {{WIN_RATE_50}}% | {{SAMPLE_50}} trades |

## Calibrated Thresholds

Based on historical performance:
- **Minimum Confidence for Entry**: {{CALIBRATED_MIN}}%

## Current Streak Status

{{STREAK_WARNING}}

## Trading Adjustments

Based on performance data, apply these rules:

1. **If Win Rate < 45%**: Only signal 75%+ confidence
2. **If Losing Streak ≥ 2**: Increase selectivity, require extra confirmation
3. **If Best Wave Known**: Prioritize that wave position
4. **If Worst Session Known**: Reduce position size or skip signals in that session

## Data Collection Status

**Note**: Performance context improves with more data. Minimum 50 trades needed for reliable statistics. Until then, use conservative defaults.

- [ ] 50 trades for baseline
- [ ] 100 trades for confidence calibration
- [ ] 200 trades for session optimization
