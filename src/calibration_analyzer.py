"""Confidence calibration analysis for Phase B.

Analyzes trade outcomes by confidence bucket to identify optimal thresholds
and factor weights for improving win rate.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceBucketStats:
    """Statistics for a confidence bucket."""

    bucket: str
    total: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    win_rate: float = 0.0
    avg_r_multiple: float = 0.0
    expectancy: float = 0.0


@dataclass
class FactorCorrelation:
    """Correlation between a factor and win rate."""

    factor: str
    correlation: float = 0.0
    avg_contribution: float = 0.0
    sample_size: int = 0
    significant: bool = False


@dataclass
class CalibrationReport:
    """Complete calibration analysis report."""

    total_trades: int = 0
    overall_win_rate: float = 0.0
    confidence_buckets: Dict[str, ConfidenceBucketStats] = field(default_factory=dict)
    factor_correlations: List[FactorCorrelation] = field(default_factory=list)
    optimal_threshold: int = 60
    recommendations: List[str] = field(default_factory=list)


class CalibrationAnalyzer:
    """Analyzes trade data to calibrate confidence scoring."""

    def __init__(self, db=None):
        """Initialize CalibrationAnalyzer.

        Args:
            db: Optional Database instance for testing. If None, uses singleton.
        """
        if db is not None:
            self.db = db
        else:
            from src.database import get_database
            self.db = get_database()

    def get_calibration_data(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get trades with calibration metadata.

        Args:
            days: Number of days to look back

        Returns:
            List of trade dicts with confidence breakdown data
        """
        with self.db._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.id as trade_id,
                    t.entry_price,
                    t.close_price,
                    t.profit,
                    t.outcome,
                    t.r_multiple,
                    t.signal_confidence,
                    s.confidence,
                    s.confidence_breakdown,
                    s.regime_type,
                    s.session,
                    s.wave_position,
                    s.action
                FROM trades t
                JOIN signals s ON t.signal_id = s.id
                WHERE t.status = 'closed'
                    AND t.close_time >= datetime('now', ? || ' days')
                ORDER BY t.close_time DESC
                """,
                (f"-{days}",),
            ).fetchall()

            return [dict(row) for row in rows]

    def analyze_confidence_buckets(self, days: int = 30) -> Dict[str, ConfidenceBucketStats]:
        """Analyze win rates by confidence bucket.

        Args:
            days: Number of days to look back

        Returns:
            Dict mapping bucket name to stats
        """
        with self.db._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    CASE
                        WHEN s.confidence >= 90 THEN '90+'
                        WHEN s.confidence >= 80 THEN '80-89'
                        WHEN s.confidence >= 70 THEN '70-79'
                        WHEN s.confidence >= 60 THEN '60-69'
                        WHEN s.confidence >= 50 THEN '50-59'
                        ELSE '<50'
                    END as bucket,
                    COUNT(*) as total,
                    SUM(CASE WHEN t.outcome = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN t.outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN t.outcome = 'breakeven' THEN 1 ELSE 0 END) as breakeven,
                    AVG(t.r_multiple) as avg_r,
                    AVG(CASE WHEN t.outcome = 'win' THEN t.r_multiple ELSE 0 END) as avg_win_r,
                    AVG(CASE WHEN t.outcome = 'loss' THEN ABS(t.r_multiple) ELSE 0 END) as avg_loss_r
                FROM trades t
                JOIN signals s ON t.signal_id = s.id
                WHERE t.status = 'closed'
                    AND t.close_time >= datetime('now', ? || ' days')
                GROUP BY bucket
                ORDER BY bucket DESC
                """,
                (f"-{days}",),
            ).fetchall()

            buckets = {}
            for row in rows:
                total = row["total"]
                wins = row["wins"] or 0
                losses = row["losses"] or 0
                breakeven = row["breakeven"] or 0
                win_rate = (wins / total * 100) if total > 0 else 0
                avg_win_r = row["avg_win_r"] or 0
                avg_loss_r = row["avg_loss_r"] or 0

                # Expectancy: (win_rate * avg_win) - (loss_rate * avg_loss)
                loss_rate = (losses / total) if total > 0 else 0
                expectancy = (win_rate / 100 * avg_win_r) - (loss_rate * avg_loss_r)

                buckets[row["bucket"]] = ConfidenceBucketStats(
                    bucket=row["bucket"],
                    total=total,
                    wins=wins,
                    losses=losses,
                    breakeven=breakeven,
                    win_rate=round(win_rate, 1),
                    avg_r_multiple=round(row["avg_r"] or 0, 2),
                    expectancy=round(expectancy, 3),
                )

            return buckets

    def analyze_factor_impact(self, days: int = 30) -> List[FactorCorrelation]:
        """Analyze correlation between confidence factors and outcomes.

        Args:
            days: Number of days to look back

        Returns:
            List of factor correlations sorted by significance
        """
        trades = self.get_calibration_data(days)
        if not trades:
            return []

        # Parse confidence breakdowns and correlate with outcomes
        factors = [
            "timeframe_alignment",
            "fibonacci_confluence",
            "rsi_confirmation",
            "ema_alignment",
            "macd_confirmation",
            "session_bonus",
            "penalties",
        ]

        factor_data = {f: {"values": [], "outcomes": []} for f in factors}

        for trade in trades:
            if not trade.get("confidence_breakdown"):
                continue

            try:
                breakdown = json.loads(trade["confidence_breakdown"])
            except (json.JSONDecodeError, TypeError):
                continue

            outcome_value = 1 if trade.get("outcome") == "win" else 0

            for factor in factors:
                value = breakdown.get(factor, 0)
                factor_data[factor]["values"].append(value)
                factor_data[factor]["outcomes"].append(outcome_value)

        correlations = []
        for factor, data in factor_data.items():
            if len(data["values"]) < 10:
                continue

            # Calculate point-biserial correlation approximation
            values = data["values"]
            outcomes = data["outcomes"]

            win_values = [v for v, o in zip(values, outcomes) if o == 1]
            loss_values = [v for v, o in zip(values, outcomes) if o == 0]

            if not win_values or not loss_values:
                continue

            avg_win = sum(win_values) / len(win_values)
            avg_loss = sum(loss_values) / len(loss_values)
            avg_all = sum(values) / len(values)

            # Correlation approximation
            std_all = (
                sum((v - avg_all) ** 2 for v in values) / len(values)
            ) ** 0.5
            if std_all > 0:
                correlation = (avg_win - avg_loss) / std_all
            else:
                correlation = 0

            correlations.append(
                FactorCorrelation(
                    factor=factor,
                    correlation=round(correlation, 3),
                    avg_contribution=round(avg_all, 1),
                    sample_size=len(values),
                    significant=abs(correlation) > 0.1 and len(values) >= 20,
                )
            )

        # Sort by absolute correlation
        correlations.sort(key=lambda x: abs(x.correlation), reverse=True)
        return correlations

    def analyze_by_session(self, days: int = 30) -> Dict[str, Dict[str, float]]:
        """Analyze win rates by trading session.

        Args:
            days: Number of days to look back

        Returns:
            Dict mapping session to stats
        """
        with self.db._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    COALESCE(s.session, 'unknown') as session,
                    COUNT(*) as total,
                    SUM(CASE WHEN t.outcome = 'win' THEN 1 ELSE 0 END) as wins,
                    AVG(t.r_multiple) as avg_r
                FROM trades t
                JOIN signals s ON t.signal_id = s.id
                WHERE t.status = 'closed'
                    AND t.close_time >= datetime('now', ? || ' days')
                GROUP BY session
                ORDER BY total DESC
                """,
                (f"-{days}",),
            ).fetchall()

            result = {}
            for row in rows:
                total = row["total"]
                wins = row["wins"] or 0
                result[row["session"]] = {
                    "total": total,
                    "wins": wins,
                    "win_rate": round((wins / total * 100) if total > 0 else 0, 1),
                    "avg_r": round(row["avg_r"] or 0, 2),
                }

            return result

    def analyze_by_regime(self, days: int = 30) -> Dict[str, Dict[str, float]]:
        """Analyze win rates by market regime.

        Args:
            days: Number of days to look back

        Returns:
            Dict mapping regime to stats
        """
        with self.db._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    COALESCE(s.regime_type, 'unknown') as regime,
                    COUNT(*) as total,
                    SUM(CASE WHEN t.outcome = 'win' THEN 1 ELSE 0 END) as wins,
                    AVG(t.r_multiple) as avg_r
                FROM trades t
                JOIN signals s ON t.signal_id = s.id
                WHERE t.status = 'closed'
                    AND t.close_time >= datetime('now', ? || ' days')
                GROUP BY regime
                ORDER BY total DESC
                """,
                (f"-{days}",),
            ).fetchall()

            result = {}
            for row in rows:
                total = row["total"]
                wins = row["wins"] or 0
                result[row["regime"]] = {
                    "total": total,
                    "wins": wins,
                    "win_rate": round((wins / total * 100) if total > 0 else 0, 1),
                    "avg_r": round(row["avg_r"] or 0, 2),
                }

            return result

    def analyze_by_wave(self, days: int = 30) -> Dict[str, Dict[str, float]]:
        """Analyze win rates by wave position.

        Args:
            days: Number of days to look back

        Returns:
            Dict mapping wave position to stats
        """
        with self.db._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    COALESCE(s.wave_position, 'unknown') as wave,
                    COUNT(*) as total,
                    SUM(CASE WHEN t.outcome = 'win' THEN 1 ELSE 0 END) as wins,
                    AVG(t.r_multiple) as avg_r
                FROM trades t
                JOIN signals s ON t.signal_id = s.id
                WHERE t.status = 'closed'
                    AND t.close_time >= datetime('now', ? || ' days')
                GROUP BY wave
                ORDER BY total DESC
                """,
                (f"-{days}",),
            ).fetchall()

            result = {}
            for row in rows:
                total = row["total"]
                wins = row["wins"] or 0
                result[row["wave"]] = {
                    "total": total,
                    "wins": wins,
                    "win_rate": round((wins / total * 100) if total > 0 else 0, 1),
                    "avg_r": round(row["avg_r"] or 0, 2),
                }

            return result

    def find_optimal_threshold(self, days: int = 30) -> Dict[str, Any]:
        """Find confidence threshold that maximizes expectancy.

        Args:
            days: Number of days to look back

        Returns:
            Dict with optimal threshold and metrics
        """
        trades = self.get_calibration_data(days)
        if not trades:
            return {"optimal_threshold": 60, "expectancy": 0, "trade_count": 0}

        best_threshold = 60
        best_expectancy = -999
        results = {}

        for threshold in range(50, 90, 5):
            qualifying = [t for t in trades if (t.get("confidence") or 0) >= threshold]
            if len(qualifying) < 5:
                continue

            wins = sum(1 for t in qualifying if t.get("outcome") == "win")
            win_rate = wins / len(qualifying)

            win_rs = [t.get("r_multiple", 0) for t in qualifying if t.get("outcome") == "win"]
            loss_rs = [
                abs(t.get("r_multiple", 0)) for t in qualifying if t.get("outcome") == "loss"
            ]

            avg_win = sum(win_rs) / len(win_rs) if win_rs else 0
            avg_loss = sum(loss_rs) / len(loss_rs) if loss_rs else 0

            # Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
            expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

            results[threshold] = {
                "trades": len(qualifying),
                "win_rate": round(win_rate * 100, 1),
                "avg_win_r": round(avg_win, 2),
                "avg_loss_r": round(avg_loss, 2),
                "expectancy": round(expectancy, 3),
            }

            if expectancy > best_expectancy:
                best_expectancy = expectancy
                best_threshold = threshold

        return {
            "optimal_threshold": best_threshold,
            "expectancy": round(best_expectancy, 3),
            "trade_count": len(trades),
            "threshold_results": results,
        }

    def generate_calibration_report(self, days: int = 30) -> CalibrationReport:
        """Generate comprehensive calibration report.

        Args:
            days: Number of days to analyze

        Returns:
            CalibrationReport with all analysis
        """
        trades = self.get_calibration_data(days)
        if not trades:
            return CalibrationReport(recommendations=["Insufficient data. Need 50+ trades."])

        # Overall stats
        total_trades = len(trades)
        wins = sum(1 for t in trades if t.get("outcome") == "win")
        overall_win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        # Get bucket analysis
        buckets = self.analyze_confidence_buckets(days)

        # Get factor analysis
        factor_correlations = self.analyze_factor_impact(days)

        # Find optimal threshold
        threshold_result = self.find_optimal_threshold(days)
        optimal_threshold = threshold_result["optimal_threshold"]

        # Generate recommendations
        recommendations = []

        if total_trades < 50:
            recommendations.append(
                f"Data limited ({total_trades} trades). Collect {50 - total_trades} more trades."
            )

        if overall_win_rate < 50:
            recommendations.append(
                f"Overall win rate ({overall_win_rate:.1f}%) below target. "
                f"Consider raising confidence threshold to {optimal_threshold}%."
            )

        # Check high confidence bucket
        if "80-89" in buckets and buckets["80-89"].total >= 10:
            if buckets["80-89"].win_rate < 55:
                recommendations.append(
                    f"80-89% bucket only {buckets['80-89'].win_rate}% win rate. "
                    "Review confidence scoring weights."
                )

        # Factor recommendations
        for fc in factor_correlations[:3]:
            if fc.significant and fc.correlation < 0:
                recommendations.append(
                    f"Factor '{fc.factor}' has negative correlation ({fc.correlation}). "
                    "Consider reducing its weight."
                )
            elif fc.significant and fc.correlation > 0.2:
                recommendations.append(
                    f"Factor '{fc.factor}' strongly predicts wins ({fc.correlation}). "
                    "Consider increasing its weight."
                )

        return CalibrationReport(
            total_trades=total_trades,
            overall_win_rate=round(overall_win_rate, 1),
            confidence_buckets=buckets,
            factor_correlations=factor_correlations,
            optimal_threshold=optimal_threshold,
            recommendations=recommendations,
        )

    def get_performance_context_for_instructions(self, days: int = 30) -> Dict[str, Any]:
        """Get performance context formatted for InstructionBuilder.

        This method provides the signal_context dict expected by
        InstructionBuilder._build_performance_context().

        Args:
            days: Number of days to analyze

        Returns:
            Dict compatible with InstructionBuilder signal_context
        """
        report = self.generate_calibration_report(days)
        session_stats = self.analyze_by_session(days)
        wave_stats = self.analyze_by_wave(days)

        # Find best/worst sessions
        best_session = None
        worst_session = None
        best_session_rate = 0
        worst_session_rate = 100

        for session, stats in session_stats.items():
            if session != "unknown" and stats["total"] >= 5:
                if stats["win_rate"] > best_session_rate:
                    best_session_rate = stats["win_rate"]
                    best_session = session
                if stats["win_rate"] < worst_session_rate:
                    worst_session_rate = stats["win_rate"]
                    worst_session = session

        # Find best/worst wave positions
        best_wave = None
        worst_wave = None
        best_wave_rate = 0
        worst_wave_rate = 100

        for wave, stats in wave_stats.items():
            if wave != "unknown" and stats["total"] >= 5:
                if stats["win_rate"] > best_wave_rate:
                    best_wave_rate = stats["win_rate"]
                    best_wave = wave
                if stats["win_rate"] < worst_wave_rate:
                    worst_wave_rate = stats["win_rate"]
                    worst_wave = wave

        # Format confidence buckets for template
        confidence_performance = {}
        for bucket, stats in report.confidence_buckets.items():
            confidence_performance[bucket] = {
                "win_rate": stats.win_rate,
                "total": stats.total,
            }

        # Get current streak from database
        streak_info = self.db._get_current_streak()

        return {
            "overall_win_rate": report.overall_win_rate,
            "confidence_performance": confidence_performance,
            "best_session": best_session,
            "worst_session": worst_session,
            "best_wave_position": best_wave,
            "worst_wave_position": worst_wave,
            "calibrated_min_confidence": report.optimal_threshold,
            "current_streak": streak_info,
            "looking_for": "entry",  # Default, can be overridden
            "wave_ambiguity": 0,  # Default
        }


# Singleton instance
_calibration_analyzer: Optional[CalibrationAnalyzer] = None


def get_calibration_analyzer() -> CalibrationAnalyzer:
    """Get or create CalibrationAnalyzer singleton."""
    global _calibration_analyzer
    if _calibration_analyzer is None:
        _calibration_analyzer = CalibrationAnalyzer()
    return _calibration_analyzer
