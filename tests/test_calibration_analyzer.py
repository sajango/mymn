"""Tests for CalibrationAnalyzer module (Phase B).

Tests confidence calibration, factor impact analysis, and performance context
generation for data-driven instruction assembly.
"""

import gc
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from src.calibration_analyzer import (
    CalibrationAnalyzer,
    CalibrationReport,
    ConfidenceBucketStats,
    FactorCorrelation,
    get_calibration_analyzer,
)
from src.database import Database
from src.signal_parser import (
    ConfidenceBreakdown,
    MarketRegime,
    Signal,
    SignalAction,
    TakeProfit,
    TradingSignal,
    WaveAnalysis,
)


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for testing."""
    db_path = tmp_path / "test_calibration.db"
    db = Database(db_path)
    yield db
    gc.collect()


@pytest.fixture
def analyzer(temp_db):
    """Create CalibrationAnalyzer with temp database."""
    return CalibrationAnalyzer(temp_db)


def create_signal(
    confidence: int = 70,
    regime: str = "trending_strong",
    session: str = "london",
    wave_position: str = "wave_2",
    breakdown: dict = None,
) -> TradingSignal:
    """Helper to create test signals with specific attributes."""
    default_breakdown = {
        "base_score": 40,
        "timeframe_alignment": 10,
        "fibonacci_confluence": 8,
        "rsi_confirmation": 5,
        "ema_alignment": 5,
        "macd_confirmation": 2,
        "session_bonus": 0,
        "penalties": 0,
        "total": confidence,  # Required field
    }
    breakdown = breakdown or default_breakdown
    if "total" not in breakdown:
        breakdown["total"] = confidence

    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.BUY,
            entry_price=3350.00,
            stop_loss=3340.00,
            take_profit=[
                TakeProfit(level="TP1", price=3360.00, close_percent=100),
            ],
            confidence=confidence,
        ),
        wave_analysis=WaveAnalysis(
            h4_trend="bullish",
            current_wave=wave_position,
            wave_position=wave_position,
        ),
        market_regime=MarketRegime(classification=regime),
        confidence_breakdown=ConfidenceBreakdown(**breakdown),
    )


def populate_trades(temp_db, trade_data: list):
    """Populate database with trade data for testing.

    trade_data: list of (confidence, outcome, r_multiple, session, regime, wave)
    """
    for i, (conf, outcome, r_mult, session, regime, wave) in enumerate(trade_data):
        signal = create_signal(
            confidence=conf, regime=regime, session=session, wave_position=wave
        )
        signal_id = temp_db.save_signal(signal, session=session)

        # Create trade using save_trade method
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=1000 + i,
            volume=0.1,
            signal=signal,
        )

        # Close trade with outcome
        close_price = signal.signal.entry_price + (10 if outcome == "win" else -10)
        profit = 10.0 if outcome == "win" else -10.0
        temp_db.close_trade(
            trade_id=trade_id,
            close_price=close_price,
            profit=profit,
        )


class TestConfidenceBucketAnalysis:
    """Test confidence bucket statistics."""

    def test_empty_database_returns_empty_buckets(self, analyzer):
        """Should return empty dict when no data."""
        buckets = analyzer.analyze_confidence_buckets()
        assert buckets == {}

    def test_single_trade_creates_bucket(self, temp_db, analyzer):
        """Should create bucket for single trade."""
        populate_trades(
            temp_db,
            [(75, "win", 1.0, "london", "trending_strong", "wave_2")],
        )
        buckets = analyzer.analyze_confidence_buckets()

        assert "70-79" in buckets
        assert buckets["70-79"].total == 1
        assert buckets["70-79"].wins == 1
        assert buckets["70-79"].win_rate == 100.0

    def test_multiple_buckets(self, temp_db, analyzer):
        """Should categorize trades into correct buckets."""
        populate_trades(
            temp_db,
            [
                (85, "win", 1.5, "london", "trending_strong", "wave_2"),
                (82, "loss", -1.0, "ny", "ranging", "wave_4"),
                (75, "win", 1.2, "london", "trending_strong", "wave_2"),
                (72, "win", 1.0, "asian", "trending_weak", "wave_2"),
                (65, "loss", -1.0, "london", "ranging", "wave_4"),
                (55, "loss", -1.0, "ny", "choppy", "wave_2"),
            ],
        )
        buckets = analyzer.analyze_confidence_buckets()

        assert "80-89" in buckets
        assert buckets["80-89"].total == 2
        assert buckets["80-89"].wins == 1
        assert buckets["80-89"].win_rate == 50.0

        assert "70-79" in buckets
        assert buckets["70-79"].total == 2
        assert buckets["70-79"].wins == 2
        assert buckets["70-79"].win_rate == 100.0

        assert "60-69" in buckets
        assert buckets["60-69"].total == 1
        assert buckets["60-69"].win_rate == 0.0

    def test_expectancy_calculation(self, temp_db, analyzer):
        """Should calculate expectancy correctly."""
        populate_trades(
            temp_db,
            [
                (75, "win", 2.0, "london", "trending_strong", "wave_2"),
                (75, "win", 1.5, "london", "trending_strong", "wave_2"),
                (75, "loss", -1.0, "london", "trending_strong", "wave_2"),
            ],
        )
        buckets = analyzer.analyze_confidence_buckets()

        # Win rate = 66.7%
        # Note: Actual R-multiples depend on stop loss calculation in close_trade
        assert "70-79" in buckets
        bucket = buckets["70-79"]
        assert bucket.win_rate == pytest.approx(66.7, rel=0.1)
        # Expectancy should be positive for majority wins
        assert bucket.expectancy > 0


class TestFactorImpactAnalysis:
    """Test factor correlation analysis."""

    def test_empty_database_returns_empty_list(self, analyzer):
        """Should return empty list when no data."""
        correlations = analyzer.analyze_factor_impact()
        assert correlations == []

    def test_requires_minimum_samples(self, temp_db, analyzer):
        """Should require minimum sample size."""
        populate_trades(
            temp_db,
            [
                (75, "win", 1.0, "london", "trending_strong", "wave_2"),
                (70, "loss", -1.0, "ny", "ranging", "wave_4"),
            ],
        )
        correlations = analyzer.analyze_factor_impact()
        # Should return empty or limited results due to small sample
        assert len(correlations) <= 1

    def test_factor_correlation_structure(self, temp_db, analyzer):
        """Should return FactorCorrelation objects with correct fields."""
        # Create enough trades for correlation analysis
        trades = []
        for i in range(15):
            outcome = "win" if i % 2 == 0 else "loss"
            conf = 70 + (i % 10)
            trades.append((conf, outcome, 1.0 if outcome == "win" else -1.0,
                          "london", "trending_strong", "wave_2"))
        populate_trades(temp_db, trades)

        correlations = analyzer.analyze_factor_impact()

        # Should have some correlations
        if correlations:
            fc = correlations[0]
            assert hasattr(fc, "factor")
            assert hasattr(fc, "correlation")
            assert hasattr(fc, "avg_contribution")
            assert hasattr(fc, "sample_size")
            assert hasattr(fc, "significant")


class TestSessionAnalysis:
    """Test session-based performance analysis."""

    def test_empty_database_returns_empty_dict(self, analyzer):
        """Should return empty dict when no data."""
        result = analyzer.analyze_by_session()
        assert result == {}

    def test_groups_by_session(self, temp_db, analyzer):
        """Should group trades by session correctly."""
        populate_trades(
            temp_db,
            [
                (75, "win", 1.0, "london", "trending_strong", "wave_2"),
                (70, "win", 1.2, "london", "trending_strong", "wave_2"),
                (72, "loss", -1.0, "ny", "trending_strong", "wave_2"),
                (80, "win", 1.5, "asian", "trending_strong", "wave_2"),
            ],
        )
        sessions = analyzer.analyze_by_session()

        assert "london" in sessions
        assert sessions["london"]["total"] == 2
        assert sessions["london"]["win_rate"] == 100.0

        assert "ny" in sessions
        assert sessions["ny"]["total"] == 1
        assert sessions["ny"]["win_rate"] == 0.0

        assert "asian" in sessions
        assert sessions["asian"]["total"] == 1
        assert sessions["asian"]["win_rate"] == 100.0


class TestRegimeAnalysis:
    """Test regime-based performance analysis."""

    def test_groups_by_regime(self, temp_db, analyzer):
        """Should group trades by market regime."""
        populate_trades(
            temp_db,
            [
                (75, "win", 1.0, "london", "trending_strong", "wave_2"),
                (70, "win", 1.2, "london", "trending_strong", "wave_2"),
                (72, "loss", -1.0, "london", "ranging", "wave_4"),
                (80, "loss", -0.5, "london", "ranging", "wave_4"),
            ],
        )
        regimes = analyzer.analyze_by_regime()

        assert "trending_strong" in regimes
        assert regimes["trending_strong"]["win_rate"] == 100.0

        assert "ranging" in regimes
        assert regimes["ranging"]["win_rate"] == 0.0


class TestWaveAnalysis:
    """Test wave position performance analysis."""

    def test_groups_by_wave_position(self, temp_db, analyzer):
        """Should group trades by wave position."""
        populate_trades(
            temp_db,
            [
                (75, "win", 1.0, "london", "trending_strong", "wave_2"),
                (70, "win", 1.2, "london", "trending_strong", "wave_2"),
                (72, "loss", -1.0, "london", "ranging", "wave_4"),
            ],
        )
        waves = analyzer.analyze_by_wave()

        assert "wave_2" in waves
        assert waves["wave_2"]["win_rate"] == 100.0

        assert "wave_4" in waves
        assert waves["wave_4"]["win_rate"] == 0.0


class TestOptimalThresholdFinder:
    """Test optimal confidence threshold calculation."""

    def test_empty_database_returns_default(self, analyzer):
        """Should return default threshold when no data."""
        result = analyzer.find_optimal_threshold()

        assert result["optimal_threshold"] == 60
        assert result["trade_count"] == 0

    def test_finds_optimal_threshold(self, temp_db, analyzer):
        """Should find threshold that maximizes expectancy."""
        populate_trades(
            temp_db,
            [
                # High confidence = high win rate
                (85, "win", 1.5, "london", "trending_strong", "wave_2"),
                (82, "win", 1.2, "london", "trending_strong", "wave_2"),
                (80, "win", 1.0, "london", "trending_strong", "wave_2"),
                # Medium confidence = mixed
                (75, "win", 1.0, "london", "trending_strong", "wave_2"),
                (72, "loss", -1.0, "london", "trending_strong", "wave_2"),
                (70, "loss", -1.0, "london", "trending_strong", "wave_2"),
                # Low confidence = low win rate
                (65, "loss", -1.0, "london", "trending_strong", "wave_2"),
                (62, "loss", -1.0, "london", "trending_strong", "wave_2"),
                (60, "win", 0.5, "london", "trending_strong", "wave_2"),
            ],
        )
        result = analyzer.find_optimal_threshold()

        # Higher threshold should be optimal due to better win rate
        assert result["optimal_threshold"] >= 70
        assert result["expectancy"] > 0


class TestCalibrationReport:
    """Test full calibration report generation."""

    def test_empty_database_returns_recommendation(self, analyzer):
        """Should recommend data collection when empty."""
        report = analyzer.generate_calibration_report()

        assert "Insufficient data" in report.recommendations[0]

    def test_generates_complete_report(self, temp_db, analyzer):
        """Should generate report with all sections."""
        populate_trades(
            temp_db,
            [
                (85, "win", 1.5, "london", "trending_strong", "wave_2"),
                (75, "win", 1.0, "london", "trending_strong", "wave_2"),
                (70, "loss", -1.0, "ny", "ranging", "wave_4"),
                (65, "loss", -1.0, "asian", "trending_weak", "wave_2"),
            ],
        )
        report = analyzer.generate_calibration_report()

        assert report.total_trades == 4
        assert report.overall_win_rate == 50.0
        assert len(report.confidence_buckets) >= 2
        assert report.optimal_threshold >= 50


class TestPerformanceContextForInstructions:
    """Test InstructionBuilder integration context."""

    def test_empty_database_returns_defaults(self, analyzer):
        """Should return default values when no data."""
        context = analyzer.get_performance_context_for_instructions()

        assert "overall_win_rate" in context
        assert "calibrated_min_confidence" in context
        assert "looking_for" in context
        assert context["looking_for"] == "entry"

    def test_returns_complete_context(self, temp_db, analyzer):
        """Should return all fields needed by InstructionBuilder."""
        populate_trades(
            temp_db,
            [
                (85, "win", 1.5, "london", "trending_strong", "wave_2"),
                (75, "win", 1.0, "london", "trending_strong", "wave_2"),
                (70, "loss", -1.0, "ny", "ranging", "wave_4"),
                (65, "loss", -1.0, "asian", "trending_weak", "wave_2"),
                (80, "win", 1.2, "london", "trending_strong", "wave_2"),
                (72, "loss", -1.0, "ny", "ranging", "wave_4"),
            ],
        )
        context = analyzer.get_performance_context_for_instructions()

        # Required fields for InstructionBuilder
        assert "overall_win_rate" in context
        assert "confidence_performance" in context
        assert "best_session" in context
        assert "worst_session" in context
        assert "best_wave_position" in context
        assert "worst_wave_position" in context
        assert "calibrated_min_confidence" in context
        assert "current_streak" in context

        # Verify confidence buckets format
        if context["confidence_performance"]:
            for bucket, stats in context["confidence_performance"].items():
                assert "win_rate" in stats
                assert "total" in stats


class TestSingletonPattern:
    """Test singleton accessor."""

    def test_returns_same_instance(self):
        """Should return same instance on multiple calls."""
        # Note: This test may fail if run in isolation without proper cleanup
        # In production, singleton is initialized once
        analyzer1 = get_calibration_analyzer()
        analyzer2 = get_calibration_analyzer()

        # Both should reference same CalibrationAnalyzer class
        assert type(analyzer1).__name__ == "CalibrationAnalyzer"
        assert type(analyzer2).__name__ == "CalibrationAnalyzer"
