"""Tests for analytics engine and performance calculations.

Tests:
- Overall metrics calculation (win rate, profit factor, drawdown, Sharpe)
- Breakdown by wave position, session, confidence level
- Edge cases: empty data, division by zero, missing fields
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestOverallMetrics:
    """Test overall metrics calculation."""

    def test_empty_trades_returns_zero_metrics(self, temp_db):
        """Empty database returns zero metrics."""
        from src.analytics import AnalyticsEngine

        engine = AnalyticsEngine()
        engine._db = temp_db

        metrics = engine.calculate_overall_metrics()

        assert metrics.total_trades == 0
        assert metrics.win_rate == 0
        assert metrics.profit_factor == 0
        assert metrics.sharpe_ratio == 0

    def test_win_rate_calculation(self, temp_db, buy_signal):
        """Win rate calculated correctly."""
        from src.analytics import AnalyticsEngine

        # Save signal and 3 trades: 2 wins, 1 loss
        signal_id = temp_db.save_signal(buy_signal)
        for i, profit in enumerate([100.0, 50.0, -30.0]):
            trade_id = temp_db.save_trade(
                signal_id=signal_id,
                ticket=1000 + i,
                volume=0.1,
                signal=buy_signal,
            )
            temp_db.close_trade(trade_id, 3400.0, profit)

        engine = AnalyticsEngine()
        engine._db = temp_db

        metrics = engine.calculate_overall_metrics()

        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 1
        assert metrics.win_rate == pytest.approx(66.7, rel=0.1)

    def test_profit_factor_calculation(self, temp_db, buy_signal):
        """Profit factor: gross profit / gross loss."""
        from src.analytics import AnalyticsEngine

        signal_id = temp_db.save_signal(buy_signal)
        # 2 winners: +100, +200 = +300
        # 2 losers: -50, -100 = -150
        for i, profit in enumerate([100.0, 200.0, -50.0, -100.0]):
            trade_id = temp_db.save_trade(
                signal_id=signal_id,
                ticket=1000 + i,
                volume=0.1,
                signal=buy_signal,
            )
            temp_db.close_trade(trade_id, 3400.0, profit)

        engine = AnalyticsEngine()
        engine._db = temp_db

        metrics = engine.calculate_overall_metrics()

        # PF = 300/150 = 2.0
        assert metrics.profit_factor == 2.0

    def test_profit_factor_with_no_losses(self, temp_db, buy_signal):
        """Profit factor infinity when no losses."""
        from src.analytics import AnalyticsEngine

        signal_id = temp_db.save_signal(buy_signal)
        for i in range(3):
            trade_id = temp_db.save_trade(
                signal_id=signal_id,
                ticket=1000 + i,
                volume=0.1,
                signal=buy_signal,
            )
            temp_db.close_trade(trade_id, 3400.0, 100.0)

        engine = AnalyticsEngine()
        engine._db = temp_db

        metrics = engine.calculate_overall_metrics()

        # Should cap at 999.99
        assert metrics.profit_factor == 999.99

    def test_max_drawdown_calculation(self, temp_db, buy_signal):
        """Max drawdown calculated from equity curve."""
        from src.analytics import AnalyticsEngine

        signal_id = temp_db.save_signal(buy_signal)
        # Sequence: +100, +50, -200, +50
        # Equity: 10100, 10150 (peak), 9950, 10000
        # Drawdown: (10150-9950)/10150 = 1.97%
        profits = [100.0, 50.0, -200.0, 50.0]
        for i, profit in enumerate(profits):
            trade_id = temp_db.save_trade(
                signal_id=signal_id,
                ticket=1000 + i,
                volume=0.1,
                signal=buy_signal,
            )
            temp_db.close_trade(trade_id, 3400.0, profit)

        engine = AnalyticsEngine(account_balance=10000.0)
        engine._db = temp_db

        metrics = engine.calculate_overall_metrics()

        assert metrics.max_drawdown_percent == pytest.approx(2.0, rel=0.1)

    def test_total_return_calculation(self, temp_db, buy_signal):
        """Total return as percentage of starting balance."""
        from src.analytics import AnalyticsEngine

        signal_id = temp_db.save_signal(buy_signal)
        # Total profit: +500 on 10000 balance = 5%
        for i, profit in enumerate([200.0, 150.0, 150.0]):
            trade_id = temp_db.save_trade(
                signal_id=signal_id,
                ticket=1000 + i,
                volume=0.1,
                signal=buy_signal,
            )
            temp_db.close_trade(trade_id, 3400.0, profit)

        engine = AnalyticsEngine(account_balance=10000.0)
        engine._db = temp_db

        metrics = engine.calculate_overall_metrics()

        assert metrics.total_return_percent == 5.0

    def test_sharpe_ratio_requires_min_trades(self, temp_db, buy_signal):
        """Sharpe ratio needs at least 2 trades."""
        from src.analytics import AnalyticsEngine

        signal_id = temp_db.save_signal(buy_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=1000,
            volume=0.1,
            signal=buy_signal,
        )
        temp_db.close_trade(trade_id, 3400.0, 100.0)

        engine = AnalyticsEngine()
        engine._db = temp_db

        metrics = engine.calculate_overall_metrics()

        assert metrics.sharpe_ratio == 0


class TestBreakdownBySession:
    """Test session-based breakdown."""

    def test_overlap_session_detection(self):
        """London/NY overlap: 12:00-15:00 UTC."""
        from src.analytics import AnalyticsEngine

        engine = AnalyticsEngine()

        assert engine._is_overlap_session("2024-01-15T12:30:00Z")
        assert engine._is_overlap_session("2024-01-15T14:59:00Z")
        assert not engine._is_overlap_session("2024-01-15T15:00:00Z")
        assert not engine._is_overlap_session("2024-01-15T11:59:00Z")

    def test_london_session_detection(self):
        """London session: 07:00-15:00 UTC."""
        from src.analytics import AnalyticsEngine

        engine = AnalyticsEngine()

        assert engine._is_london_session("2024-01-15T08:00:00Z")
        assert engine._is_london_session("2024-01-15T14:00:00Z")
        assert not engine._is_london_session("2024-01-15T06:00:00Z")
        assert not engine._is_london_session("2024-01-15T16:00:00Z")

    def test_ny_session_detection(self):
        """NY session: 12:00-20:00 UTC."""
        from src.analytics import AnalyticsEngine

        engine = AnalyticsEngine()

        assert engine._is_ny_session("2024-01-15T15:00:00Z")
        assert engine._is_ny_session("2024-01-15T19:00:00Z")
        assert not engine._is_ny_session("2024-01-15T11:00:00Z")
        assert not engine._is_ny_session("2024-01-15T21:00:00Z")

    def test_asian_session_detection(self):
        """Asian session: 00:00-07:00 UTC."""
        from src.analytics import AnalyticsEngine

        engine = AnalyticsEngine()

        assert engine._is_asian_session("2024-01-15T02:00:00Z")
        assert engine._is_asian_session("2024-01-15T06:00:00Z")
        assert not engine._is_asian_session("2024-01-15T08:00:00Z")

    def test_session_handles_none_timestamp(self):
        """Session detection handles None gracefully."""
        from src.analytics import AnalyticsEngine

        engine = AnalyticsEngine()

        assert not engine._is_overlap_session(None)
        assert not engine._is_london_session(None)
        assert not engine._is_ny_session(None)
        assert not engine._is_asian_session(None)


class TestBreakdownByConfidence:
    """Test confidence level breakdown."""

    def test_confidence_bucketing(self, temp_db):
        """Confidence levels grouped correctly."""
        from src.analytics import AnalyticsEngine
        from src.signal_parser import Signal, SignalAction, TradingSignal

        engine = AnalyticsEngine()
        engine._db = temp_db

        # Create signals with different confidence levels
        for conf in [80, 70, 50]:
            signal = TradingSignal(
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol="XAUUSD",
                signal=Signal(
                    action=SignalAction.BUY,
                    entry_price=3340.0,
                    stop_loss=3310.0,
                    confidence=conf,
                ),
            )
            temp_db.save_signal(signal)

        result = engine.calculate_by_confidence()

        assert result["75_plus"].count == 1  # 80
        assert result["60_to_74"].count == 1  # 70
        assert result["below_60"].count == 1  # 50


class TestOptimizationSuggestions:
    """Test optimization suggestions."""

    def test_low_win_rate_suggestion(self, temp_db, buy_signal):
        """Suggestion for win rate below 55%."""
        from src.analytics import AnalyticsEngine

        signal_id = temp_db.save_signal(buy_signal)
        # 2 wins, 3 losses = 40% win rate
        for i, profit in enumerate([100.0, 50.0, -30.0, -40.0, -50.0]):
            trade_id = temp_db.save_trade(
                signal_id=signal_id,
                ticket=1000 + i,
                volume=0.1,
                signal=buy_signal,
            )
            temp_db.close_trade(trade_id, 3400.0, profit)

        engine = AnalyticsEngine()
        engine._db = temp_db

        suggestions = engine.get_optimization_suggestions()

        assert any("Win rate" in s for s in suggestions)

    def test_low_profit_factor_suggestion(self, temp_db, buy_signal):
        """Suggestion for profit factor below 1.5."""
        from src.analytics import AnalyticsEngine

        signal_id = temp_db.save_signal(buy_signal)
        # PF = 100/80 = 1.25
        for i, profit in enumerate([100.0, -80.0]):
            trade_id = temp_db.save_trade(
                signal_id=signal_id,
                ticket=1000 + i,
                volume=0.1,
                signal=buy_signal,
            )
            temp_db.close_trade(trade_id, 3400.0, profit)

        engine = AnalyticsEngine()
        engine._db = temp_db

        suggestions = engine.get_optimization_suggestions()

        assert any("Profit factor" in s for s in suggestions)


class TestFullReport:
    """Test full report generation."""

    def test_full_report_structure(self, temp_db, buy_signal):
        """Full report contains all sections."""
        from src.analytics import AnalyticsEngine

        signal_id = temp_db.save_signal(buy_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=1000,
            volume=0.1,
            signal=buy_signal,
        )
        temp_db.close_trade(trade_id, 3400.0, 100.0)

        engine = AnalyticsEngine()
        engine._db = temp_db

        report = engine.generate_full_report()

        assert "generated_at" in report
        assert "overall_metrics" in report
        assert "by_wave_position" in report
        assert "by_session" in report
        assert "by_confidence_level" in report

    def test_full_report_with_date_range(self, temp_db, buy_signal):
        """Full report respects date range filter."""
        from src.analytics import AnalyticsEngine

        engine = AnalyticsEngine()
        engine._db = temp_db

        report = engine.generate_full_report(
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        assert report["period"]["start_date"] == "2024-01-01"
        assert report["period"]["end_date"] == "2024-12-31"


class TestSingleton:
    """Test analytics engine singleton."""

    def test_get_analytics_engine_returns_same_instance(self):
        """get_analytics_engine returns singleton."""
        from src.analytics import _analytics_engine, get_analytics_engine

        # Reset singleton for test
        import src.analytics

        src.analytics._analytics_engine = None

        engine1 = get_analytics_engine()
        engine2 = get_analytics_engine()

        assert engine1 is engine2
