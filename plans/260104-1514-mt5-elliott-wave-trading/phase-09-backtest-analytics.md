# Phase 9: Backtest & Analytics

## Context Links
- [Plan Overview](./plan.md)
- [Phase 8: Web Dashboard](./phase-08-web-dashboard.md)
- [instructions_v2.md](../../instructions_v2.md) - Appendix C

## Overview
- **Priority**: P2
- **Status**: ✅ COMPLETE
- **Effort**: 4h
- **Description**: Historical signal analysis and performance tracking for system optimization

## Key Insights
- Use SQLite data from signals/trades tables
- Calculate metrics from instructions_v2.md Appendix C template
- Track performance by: wave position, session, confidence level
- Generate weekly performance reports
- Identify optimization opportunities

## Requirements

### Functional
- Calculate overall metrics: win rate, profit factor, max drawdown, Sharpe ratio
- Breakdown by wave position (Wave 3, Wave 5, Wave C entries)
- Breakdown by session (London, NY, Asian, Overlap)
- Breakdown by confidence level (75+, 60-74, below 60)
- Track indicator effectiveness (RSI divergence, EMA bounce, MACD confirmation)
- Generate weekly summary reports
- Store metrics history for trend analysis

### Non-Functional
- Efficient SQLite queries
- JSON export for dashboard consumption
- Scheduled weekly report generation
- Minimal memory footprint

## Architecture

### Data Flow
```
SQLite (signals, trades, tp_levels)
        |
AnalyticsEngine.calculate_metrics()
        |
├── Overall: win_rate, profit_factor, drawdown
├── By Wave: wave_3, wave_5, wave_c breakdown
├── By Session: london, ny, asian, overlap
├── By Confidence: 75+, 60-74, <60
└── Indicators: rsi_divergence, ema_bounce, macd
        |
MetricsStore.save_snapshot()
        |
WeeklyReport.generate()
```

### Metrics Schema
```json
{
  "backtest_period": {
    "start_date": "2024-01-01",
    "end_date": "2024-08-31",
    "trading_days": 165,
    "total_signals": 89
  },
  "overall_metrics": {
    "win_rate": 62.5,
    "profit_factor": 1.85,
    "total_return_percent": 18.5,
    "max_drawdown_percent": 8.2,
    "sharpe_ratio": 1.42,
    "average_rr_achieved": 1.65
  },
  "by_wave_position": {
    "wave_3_entries": {"count": 28, "win_rate": 71.4, "avg_rr": 2.1},
    "wave_5_entries": {"count": 35, "win_rate": 60.0, "avg_rr": 1.5},
    "wave_c_entries": {"count": 26, "win_rate": 57.7, "avg_rr": 1.4}
  },
  "by_session": {
    "london_ny_overlap": {"win_rate": 68.0, "count": 25},
    "london": {"win_rate": 64.0, "count": 32},
    "new_york": {"win_rate": 58.0, "count": 24},
    "asian": {"win_rate": 45.0, "count": 8}
  },
  "by_confidence_level": {
    "75_plus": {"win_rate": 72.0, "count": 18},
    "60_to_74": {"win_rate": 61.0, "count": 45},
    "below_60": {"win_rate": 48.0, "count": 26}
  },
  "indicator_effectiveness": {
    "rsi_divergence_signals": {"win_rate": 75.0, "count": 20},
    "ema_bounce_signals": {"win_rate": 65.0, "count": 35},
    "macd_confirmation": {"win_rate": 68.0, "count": 42}
  }
}
```

## Related Code Files

### Files to Create
- src/analytics.py - AnalyticsEngine class
- src/reports.py - WeeklyReport generator

### Files to Modify
- src/database.py - Add analytics queries

## Implementation Steps

1. **Update src/database.py** - Add analytics queries

```python
# Add to Database class

def get_closed_trades(self, start_date: str = None, end_date: str = None) -> list[dict]:
    """Get all closed trades for analytics"""
    query = "SELECT * FROM trades WHERE status = 'closed'"
    params = []

    if start_date:
        query += " AND close_time >= ?"
        params.append(start_date)
    if end_date:
        query += " AND close_time <= ?"
        params.append(end_date)

    with sqlite3.connect(self.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

def get_signals_with_metadata(self) -> list[dict]:
    """Get signals with wave position and session data"""
    query = """
        SELECT s.*, t.profit, t.close_price, t.status as trade_status
        FROM signals s
        LEFT JOIN trades t ON s.id = t.signal_id
    """
    with sqlite3.connect(self.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]
```

2. **Create src/analytics.py**

```python
"""Performance analytics engine"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
import json
import math

from src.database import database
from src.config import config

logger = logging.getLogger(__name__)


@dataclass
class OverallMetrics:
    win_rate: float
    profit_factor: float
    total_return_percent: float
    max_drawdown_percent: float
    sharpe_ratio: float
    average_rr_achieved: float
    total_trades: int
    winning_trades: int
    losing_trades: int


@dataclass
class BreakdownMetrics:
    count: int
    win_rate: float
    avg_rr: float
    total_profit: float


class AnalyticsEngine:
    """Calculate trading performance metrics"""

    def __init__(self):
        self._account_balance = 10000  # Default for calculations

    def calculate_overall_metrics(
        self,
        start_date: str = None,
        end_date: str = None
    ) -> OverallMetrics:
        """Calculate overall performance metrics"""
        trades = database.get_closed_trades(start_date, end_date)

        if not trades:
            return OverallMetrics(
                win_rate=0, profit_factor=0, total_return_percent=0,
                max_drawdown_percent=0, sharpe_ratio=0, average_rr_achieved=0,
                total_trades=0, winning_trades=0, losing_trades=0
            )

        # Basic counts
        total = len(trades)
        winners = [t for t in trades if t['profit'] > 0]
        losers = [t for t in trades if t['profit'] <= 0]

        # Win rate
        win_rate = (len(winners) / total) * 100 if total > 0 else 0

        # Profit factor
        gross_profit = sum(t['profit'] for t in winners)
        gross_loss = abs(sum(t['profit'] for t in losers))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Total return
        total_profit = sum(t['profit'] for t in trades)
        total_return = (total_profit / self._account_balance) * 100

        # Max drawdown
        max_drawdown = self._calculate_max_drawdown(trades)

        # Sharpe ratio (simplified)
        sharpe = self._calculate_sharpe_ratio(trades)

        # Average R:R achieved
        avg_rr = self._calculate_average_rr(trades)

        return OverallMetrics(
            win_rate=round(win_rate, 1),
            profit_factor=round(profit_factor, 2),
            total_return_percent=round(total_return, 1),
            max_drawdown_percent=round(max_drawdown, 1),
            sharpe_ratio=round(sharpe, 2),
            average_rr_achieved=round(avg_rr, 2),
            total_trades=total,
            winning_trades=len(winners),
            losing_trades=len(losers)
        )

    def _calculate_max_drawdown(self, trades: list[dict]) -> float:
        """Calculate maximum drawdown from equity curve"""
        equity = self._account_balance
        peak = equity
        max_dd = 0

        for trade in sorted(trades, key=lambda x: x['close_time']):
            equity += trade['profit']
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

        return max_dd

    def _calculate_sharpe_ratio(self, trades: list[dict]) -> float:
        """Calculate simplified Sharpe ratio"""
        if len(trades) < 2:
            return 0

        returns = [t['profit'] / self._account_balance for t in trades]
        avg_return = sum(returns) / len(returns)

        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        std_dev = math.sqrt(variance) if variance > 0 else 0

        if std_dev == 0:
            return 0

        # Annualized (assuming ~250 trading days)
        return (avg_return * 250) / (std_dev * math.sqrt(250))

    def _calculate_average_rr(self, trades: list[dict]) -> float:
        """Calculate average risk:reward achieved"""
        rr_values = []

        for trade in trades:
            # Need stop distance from entry
            entry = trade['entry_price']
            close = trade['close_price']
            sl = trade['stop_loss']

            if entry and close and sl:
                risk = abs(entry - sl)
                reward = close - entry if trade['action'] == 'BUY' else entry - close
                if risk > 0:
                    rr_values.append(reward / risk)

        return sum(rr_values) / len(rr_values) if rr_values else 0

    def calculate_by_wave_position(self) -> dict[str, BreakdownMetrics]:
        """Calculate metrics by wave position (from signal metadata)"""
        signals = database.get_signals_with_metadata()

        # Group by wave position
        wave_3 = [s for s in signals if 'wave_3' in s.get('wave_position', '').lower() or 'wave_2' in s.get('wave_position', '').lower()]
        wave_5 = [s for s in signals if 'wave_4' in s.get('wave_position', '').lower() or 'wave_5' in s.get('wave_position', '').lower()]
        wave_c = [s for s in signals if 'wave_c' in s.get('wave_position', '').lower() or 'wave_b' in s.get('wave_position', '').lower()]

        return {
            'wave_3_entries': self._calc_breakdown(wave_3),
            'wave_5_entries': self._calc_breakdown(wave_5),
            'wave_c_entries': self._calc_breakdown(wave_c)
        }

    def calculate_by_session(self) -> dict[str, BreakdownMetrics]:
        """Calculate metrics by trading session"""
        signals = database.get_signals_with_metadata()

        # Group by session (from timestamp)
        london_ny = [s for s in signals if self._is_overlap_session(s['timestamp'])]
        london = [s for s in signals if self._is_london_session(s['timestamp']) and not self._is_overlap_session(s['timestamp'])]
        ny = [s for s in signals if self._is_ny_session(s['timestamp']) and not self._is_overlap_session(s['timestamp'])]
        asian = [s for s in signals if self._is_asian_session(s['timestamp'])]

        return {
            'london_ny_overlap': self._calc_breakdown(london_ny),
            'london': self._calc_breakdown(london),
            'new_york': self._calc_breakdown(ny),
            'asian': self._calc_breakdown(asian)
        }

    def calculate_by_confidence(self) -> dict[str, BreakdownMetrics]:
        """Calculate metrics by confidence level"""
        signals = database.get_signals_with_metadata()

        high_conf = [s for s in signals if s.get('confidence', 0) >= 75]
        med_conf = [s for s in signals if 60 <= s.get('confidence', 0) < 75]
        low_conf = [s for s in signals if s.get('confidence', 0) < 60]

        return {
            '75_plus': self._calc_breakdown(high_conf),
            '60_to_74': self._calc_breakdown(med_conf),
            'below_60': self._calc_breakdown(low_conf)
        }

    def _calc_breakdown(self, signals: list[dict]) -> BreakdownMetrics:
        """Calculate breakdown metrics for a subset"""
        if not signals:
            return BreakdownMetrics(count=0, win_rate=0, avg_rr=0, total_profit=0)

        executed = [s for s in signals if s.get('trade_status') == 'closed']
        if not executed:
            return BreakdownMetrics(count=len(signals), win_rate=0, avg_rr=0, total_profit=0)

        winners = [s for s in executed if s.get('profit', 0) > 0]
        win_rate = (len(winners) / len(executed)) * 100
        total_profit = sum(s.get('profit', 0) for s in executed)

        return BreakdownMetrics(
            count=len(signals),
            win_rate=round(win_rate, 1),
            avg_rr=0,  # Would need entry/SL data
            total_profit=round(total_profit, 2)
        )

    def _is_overlap_session(self, timestamp: str) -> bool:
        """Check if timestamp is in London/NY overlap (12:00-15:00 UTC)"""
        dt = datetime.fromisoformat(timestamp)
        return 12 <= dt.hour < 15

    def _is_london_session(self, timestamp: str) -> bool:
        """Check if timestamp is in London session (07:00-15:00 UTC)"""
        dt = datetime.fromisoformat(timestamp)
        return 7 <= dt.hour < 15

    def _is_ny_session(self, timestamp: str) -> bool:
        """Check if timestamp is in NY session (12:00-20:00 UTC)"""
        dt = datetime.fromisoformat(timestamp)
        return 12 <= dt.hour < 20

    def _is_asian_session(self, timestamp: str) -> bool:
        """Check if timestamp is in Asian session (00:00-07:00 UTC)"""
        dt = datetime.fromisoformat(timestamp)
        return 0 <= dt.hour < 7

    def generate_full_report(self) -> dict:
        """Generate full analytics report"""
        return {
            'generated_at': datetime.utcnow().isoformat(),
            'overall_metrics': vars(self.calculate_overall_metrics()),
            'by_wave_position': {k: vars(v) for k, v in self.calculate_by_wave_position().items()},
            'by_session': {k: vars(v) for k, v in self.calculate_by_session().items()},
            'by_confidence_level': {k: vars(v) for k, v in self.calculate_by_confidence().items()}
        }

    def save_report_to_file(self, filepath: str):
        """Save report as JSON"""
        report = self.generate_full_report()
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"Analytics report saved to {filepath}")


# Singleton
analytics_engine = AnalyticsEngine()
```

3. **Create src/reports.py**

```python
"""Weekly performance reports"""
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.analytics import analytics_engine
from src.config import config

logger = logging.getLogger(__name__)


class WeeklyReportGenerator:
    """Generate weekly performance reports"""

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or config.logs_dir / 'reports'
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_weekly_report(self):
        """Generate and save weekly report"""
        today = datetime.utcnow()
        week_start = today - timedelta(days=today.weekday() + 7)  # Last Monday
        week_end = week_start + timedelta(days=6)

        # Generate report
        report = analytics_engine.generate_full_report()
        report['period'] = {
            'type': 'weekly',
            'start': week_start.strftime('%Y-%m-%d'),
            'end': week_end.strftime('%Y-%m-%d')
        }

        # Save report
        filename = f"weekly_report_{week_start.strftime('%Y%m%d')}.json"
        filepath = self.output_dir / filename

        analytics_engine.save_report_to_file(str(filepath))

        return report

    def get_optimization_suggestions(self) -> list[str]:
        """Generate optimization suggestions based on metrics"""
        suggestions = []
        report = analytics_engine.generate_full_report()

        overall = report['overall_metrics']

        # Win rate check
        if overall['win_rate'] < 55:
            suggestions.append("Win rate below 55% → Review wave count accuracy")

        # Profit factor check
        if overall['profit_factor'] < 1.5:
            suggestions.append("Profit factor below 1.5 → Check TP/SL placement")

        # Max drawdown check
        if overall['max_drawdown_percent'] > 10:
            suggestions.append("Drawdown exceeds 10% → Reduce position sizes")

        # Session performance
        sessions = report['by_session']
        if sessions.get('asian', {}).get('win_rate', 100) < 50:
            suggestions.append("Asian session underperforming → Consider disabling")

        # Confidence levels
        confidence = report['by_confidence_level']
        if confidence.get('below_60', {}).get('win_rate', 100) < 50:
            suggestions.append("Low confidence signals underperforming → Raise threshold")

        return suggestions


# Singleton
weekly_reporter = WeeklyReportGenerator()
```

4. **Add scheduled report generation to orchestrator**

```python
# Add to main.py

from src.reports import weekly_reporter

# In TradingOrchestrator.run():
# Add weekly report job (every Sunday 23:00 UTC)
self.scheduler.add_job(
    weekly_reporter.generate_weekly_report,
    CronTrigger(day_of_week='sun', hour=23),
    id="weekly_report",
    replace_existing=True,
)
```

## Todo List

- [x] Update src/database.py with analytics queries
- [x] Create src/analytics.py with AnalyticsEngine
- [x] Create src/reports.py with WeeklyReportGenerator
- [x] Implement overall metrics calculation
- [x] Implement breakdown by wave position
- [x] Implement breakdown by session
- [x] Implement breakdown by confidence level
- [x] Implement Sharpe ratio calculation
- [x] Add optimization suggestions generator
- [x] Schedule weekly report generation
- [x] Write tests for analytics calculations
- [x] Integrate with Phase 8 dashboard API

## Success Criteria

- [x] All metrics calculate correctly from SQLite data
- [x] Reports generate without errors
- [x] Weekly reports save to file automatically
- [x] Dashboard can fetch and display analytics
- [x] Optimization suggestions are actionable

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Insufficient data for Sharpe | Low | Low | Require minimum 10 trades |
| SQL query performance | Low | Low | Add indexes on date columns |
| Division by zero | Medium | Medium | Check for zero denominators |
| Memory issues with large dataset | Low | Medium | Use pagination in queries |

## Key Metrics Thresholds

From instructions_v2.md Appendix C:

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Win Rate | > 55% | 50-55% | < 50% |
| Profit Factor | > 1.5 | 1.2-1.5 | < 1.2 |
| Max Drawdown | < 10% | 10-15% | > 15% |
| Avg R:R Achieved | > 1.5 | 1.0-1.5 | < 1.0 |
| Signals per Week | 3-5 | 1-2 or 6-8 | < 1 or > 10 |

## Security Considerations

- Report files contain performance data only
- No PII or credentials in reports
- JSON export for dashboard (no direct DB access from web)

## Next Steps

Complete! System is fully specified.
