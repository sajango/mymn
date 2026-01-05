"""Performance analytics engine for trading system.

Calculates:
- Overall metrics (win rate, profit factor, drawdown, Sharpe ratio)
- Breakdown by wave position (Wave 3, Wave 5, Wave C)
- Breakdown by session (London, NY, Asian, Overlap)
- Breakdown by confidence level (75+, 60-74, <60)
- Indicator effectiveness metrics
"""

import logging
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

from src.config import get_settings
from src.database import get_database

logger = logging.getLogger(__name__)


@dataclass
class OverallMetrics:
    """Overall trading performance metrics."""

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
    """Metrics for a specific breakdown category."""

    count: int
    win_rate: float
    avg_rr: float
    total_profit: float


class AnalyticsEngine:
    """Calculate trading performance metrics from database."""

    def __init__(self, account_balance: float = 10000.0):
        """Initialize analytics engine.

        Args:
            account_balance: Starting account balance for return calculations
        """
        self._account_balance = account_balance
        self._db = None

    @property
    def db(self):
        """Lazy load database."""
        if self._db is None:
            self._db = get_database()
        return self._db

    def calculate_overall_metrics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> OverallMetrics:
        """Calculate overall performance metrics.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            OverallMetrics with all key performance indicators
        """
        trades = self.db.get_closed_trades(start_date, end_date)

        if not trades:
            return OverallMetrics(
                win_rate=0,
                profit_factor=0,
                total_return_percent=0,
                max_drawdown_percent=0,
                sharpe_ratio=0,
                average_rr_achieved=0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
            )

        # Basic counts
        total = len(trades)
        winners = [t for t in trades if (t.get("profit") or 0) > 0]
        losers = [t for t in trades if (t.get("profit") or 0) <= 0]

        # Win rate
        win_rate = (len(winners) / total) * 100 if total > 0 else 0

        # Profit factor (gross profit / gross loss)
        gross_profit = sum(t.get("profit", 0) for t in winners)
        gross_loss = abs(sum(t.get("profit", 0) for t in losers))
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0 else float("inf")
        )

        # Total return
        total_profit = sum(t.get("profit", 0) for t in trades)
        total_return = (total_profit / self._account_balance) * 100

        # Max drawdown
        max_drawdown = self._calculate_max_drawdown(trades)

        # Sharpe ratio
        sharpe = self._calculate_sharpe_ratio(trades)

        # Average R:R achieved
        avg_rr = self._calculate_average_rr(trades)

        return OverallMetrics(
            win_rate=round(win_rate, 1),
            profit_factor=(
                round(profit_factor, 2) if profit_factor != float("inf") else 999.99
            ),
            total_return_percent=round(total_return, 1),
            max_drawdown_percent=round(max_drawdown, 1),
            sharpe_ratio=round(sharpe, 2),
            average_rr_achieved=round(avg_rr, 2),
            total_trades=total,
            winning_trades=len(winners),
            losing_trades=len(losers),
        )

    def _calculate_max_drawdown(self, trades: list[dict]) -> float:
        """Calculate maximum drawdown from equity curve.

        Args:
            trades: List of closed trades

        Returns:
            Maximum drawdown as percentage
        """
        if not trades:
            return 0

        equity = self._account_balance
        peak = equity
        max_dd = 0

        # Sort by close time
        sorted_trades = sorted(
            trades, key=lambda x: x.get("close_time") or ""
        )

        for trade in sorted_trades:
            equity += trade.get("profit", 0)
            if equity > peak:
                peak = equity
            if peak > 0:
                dd = (peak - equity) / peak * 100
                max_dd = max(max_dd, dd)

        return max_dd

    def _calculate_sharpe_ratio(self, trades: list[dict]) -> float:
        """Calculate simplified Sharpe ratio.

        Uses trade returns, annualized assuming ~250 trading days.

        Args:
            trades: List of closed trades

        Returns:
            Annualized Sharpe ratio
        """
        if len(trades) < 2:
            return 0

        returns = [
            t.get("profit", 0) / self._account_balance for t in trades
        ]
        avg_return = sum(returns) / len(returns)

        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        std_dev = math.sqrt(variance) if variance > 0 else 0

        if std_dev == 0:
            return 0

        # Annualized (assuming ~250 trading days)
        return (avg_return * 250) / (std_dev * math.sqrt(250))

    def _calculate_average_rr(self, trades: list[dict]) -> float:
        """Calculate average risk:reward achieved.

        Args:
            trades: List of closed trades

        Returns:
            Average R:R ratio
        """
        rr_values = []

        for trade in trades:
            entry = trade.get("entry_price")
            close = trade.get("close_price")
            sl = trade.get("initial_stop_loss") or trade.get("stop_loss")

            if entry and close and sl and entry != sl:
                risk = abs(entry - sl)
                action = trade.get("action", "BUY")
                reward = (
                    close - entry if action == "BUY" else entry - close
                )
                if risk > 0:
                    rr_values.append(reward / risk)

        return sum(rr_values) / len(rr_values) if rr_values else 0

    def calculate_by_wave_position(self) -> dict[str, BreakdownMetrics]:
        """Calculate metrics by wave position.

        Returns:
            Dict mapping wave type to BreakdownMetrics
        """
        signals = self.db.get_signals_with_trades()

        # Group by wave position
        wave_3 = [
            s
            for s in signals
            if any(
                w in (s.get("wave_position") or "").lower()
                for w in ["wave 3", "wave_3", "wave 2", "wave_2"]
            )
        ]
        wave_5 = [
            s
            for s in signals
            if any(
                w in (s.get("wave_position") or "").lower()
                for w in ["wave 5", "wave_5", "wave 4", "wave_4"]
            )
        ]
        wave_c = [
            s
            for s in signals
            if any(
                w in (s.get("wave_position") or "").lower()
                for w in ["wave c", "wave_c", "wave b", "wave_b"]
            )
        ]

        return {
            "wave_3_entries": self._calc_breakdown(wave_3),
            "wave_5_entries": self._calc_breakdown(wave_5),
            "wave_c_entries": self._calc_breakdown(wave_c),
        }

    def calculate_by_session(self) -> dict[str, BreakdownMetrics]:
        """Calculate metrics by trading session.

        Returns:
            Dict mapping session name to BreakdownMetrics
        """
        signals = self.db.get_signals_with_trades()

        london_ny = [
            s for s in signals if self._is_overlap_session(s.get("timestamp"))
        ]
        london = [
            s
            for s in signals
            if self._is_london_session(s.get("timestamp"))
            and not self._is_overlap_session(s.get("timestamp"))
        ]
        ny = [
            s
            for s in signals
            if self._is_ny_session(s.get("timestamp"))
            and not self._is_overlap_session(s.get("timestamp"))
        ]
        asian = [
            s for s in signals if self._is_asian_session(s.get("timestamp"))
        ]

        return {
            "london_ny_overlap": self._calc_breakdown(london_ny),
            "london": self._calc_breakdown(london),
            "new_york": self._calc_breakdown(ny),
            "asian": self._calc_breakdown(asian),
        }

    def calculate_by_confidence(self) -> dict[str, BreakdownMetrics]:
        """Calculate metrics by confidence level.

        Returns:
            Dict mapping confidence band to BreakdownMetrics
        """
        signals = self.db.get_signals_with_trades()

        high_conf = [
            s for s in signals if (s.get("confidence") or 0) >= 75
        ]
        med_conf = [
            s for s in signals if 60 <= (s.get("confidence") or 0) < 75
        ]
        low_conf = [s for s in signals if (s.get("confidence") or 0) < 60]

        return {
            "75_plus": self._calc_breakdown(high_conf),
            "60_to_74": self._calc_breakdown(med_conf),
            "below_60": self._calc_breakdown(low_conf),
        }

    def _calc_breakdown(self, signals: list[dict]) -> BreakdownMetrics:
        """Calculate breakdown metrics for a subset of signals.

        Args:
            signals: List of signals with trade data

        Returns:
            BreakdownMetrics for the subset
        """
        if not signals:
            return BreakdownMetrics(count=0, win_rate=0, avg_rr=0, total_profit=0)

        # Only count executed trades
        executed = [
            s for s in signals if s.get("trade_status") == "closed"
        ]
        if not executed:
            return BreakdownMetrics(
                count=len(signals), win_rate=0, avg_rr=0, total_profit=0
            )

        winners = [s for s in executed if (s.get("profit") or 0) > 0]
        win_rate = (len(winners) / len(executed)) * 100
        total_profit = sum(s.get("profit", 0) for s in executed)

        # Calculate avg R:R if we have entry/SL data
        rr_values = []
        for s in executed:
            entry = s.get("trade_entry")
            close = s.get("close_price")
            sl = s.get("trade_sl")
            if entry and close and sl and entry != sl:
                risk = abs(entry - sl)
                action = s.get("action", "BUY")
                reward = close - entry if action == "BUY" else entry - close
                if risk > 0:
                    rr_values.append(reward / risk)

        avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0

        return BreakdownMetrics(
            count=len(signals),
            win_rate=round(win_rate, 1),
            avg_rr=round(avg_rr, 2),
            total_profit=round(total_profit, 2),
        )

    def _is_overlap_session(self, timestamp: Optional[str]) -> bool:
        """Check if timestamp is in London/NY overlap (12:00-15:00 UTC)."""
        if not timestamp:
            return False
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return 12 <= dt.hour < 15
        except (ValueError, AttributeError):
            return False

    def _is_london_session(self, timestamp: Optional[str]) -> bool:
        """Check if timestamp is in London session (07:00-15:00 UTC)."""
        if not timestamp:
            return False
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return 7 <= dt.hour < 15
        except (ValueError, AttributeError):
            return False

    def _is_ny_session(self, timestamp: Optional[str]) -> bool:
        """Check if timestamp is in NY session (12:00-20:00 UTC)."""
        if not timestamp:
            return False
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return 12 <= dt.hour < 20
        except (ValueError, AttributeError):
            return False

    def _is_asian_session(self, timestamp: Optional[str]) -> bool:
        """Check if timestamp is in Asian session (00:00-07:00 UTC)."""
        if not timestamp:
            return False
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return 0 <= dt.hour < 7
        except (ValueError, AttributeError):
            return False

    def generate_full_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Generate full analytics report.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Complete analytics report as dict
        """
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "period": {"start_date": start_date, "end_date": end_date},
            "overall_metrics": asdict(
                self.calculate_overall_metrics(start_date, end_date)
            ),
            "by_wave_position": {
                k: asdict(v) for k, v in self.calculate_by_wave_position().items()
            },
            "by_session": {
                k: asdict(v) for k, v in self.calculate_by_session().items()
            },
            "by_confidence_level": {
                k: asdict(v) for k, v in self.calculate_by_confidence().items()
            },
        }

    def get_optimization_suggestions(self) -> list[str]:
        """Generate optimization suggestions based on metrics.

        Returns:
            List of actionable suggestions
        """
        suggestions = []
        overall = self.calculate_overall_metrics()

        # Win rate check
        if overall.win_rate < 55:
            suggestions.append(
                "Win rate below 55% → Review wave count accuracy"
            )

        # Profit factor check
        if overall.profit_factor < 1.5:
            suggestions.append(
                "Profit factor below 1.5 → Check TP/SL placement"
            )

        # Max drawdown check
        if overall.max_drawdown_percent > 10:
            suggestions.append(
                "Drawdown exceeds 10% → Reduce position sizes"
            )

        # Session performance
        sessions = self.calculate_by_session()
        asian = sessions.get("asian")
        if asian and asian.win_rate < 50 and asian.count > 5:
            suggestions.append(
                "Asian session underperforming → Consider disabling"
            )

        # Confidence levels
        confidence = self.calculate_by_confidence()
        low_conf = confidence.get("below_60")
        if low_conf and low_conf.win_rate < 50 and low_conf.count > 5:
            suggestions.append(
                "Low confidence signals underperforming → Raise threshold"
            )

        # Average R:R check
        if overall.average_rr_achieved < 1.0 and overall.total_trades > 5:
            suggestions.append(
                "Average R:R below 1.0 → Review TP targets and exit timing"
            )

        return suggestions


# Lazy singleton
_analytics_engine: Optional[AnalyticsEngine] = None


def get_analytics_engine() -> AnalyticsEngine:
    """Get or create analytics engine singleton."""
    global _analytics_engine
    if _analytics_engine is None:
        _analytics_engine = AnalyticsEngine()
    return _analytics_engine
