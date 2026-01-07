"""Unit tests for SignalConsistencyFilter."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.signal_filter import (
    FilterReason,
    FilterResult,
    SignalConsistencyFilter,
)
from src.signal_parser import Signal, SignalAction, TradingSignal


def create_mock_signal(action: str, confidence: int = 70) -> TradingSignal:
    """Create mock trading signal for testing."""
    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction(action),
            confidence=confidence,
            entry_price=2650.0,
            stop_loss=2640.0,
        ),
    )


def create_recent_signal(action: str, minutes_ago: int) -> dict:
    """Create mock recent signal record from database."""
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {
        "id": 1,
        "action": action,
        "confidence": 70,
        "created_at": ts.isoformat(),
    }


class TestSignalConsistencyFilter:
    """Test SignalConsistencyFilter behavior."""

    def test_no_history_allows_signal(self):
        """Signal passes when no history exists."""
        mock_db = MagicMock()
        mock_db.get_recent_signals.return_value = []

        filter = SignalConsistencyFilter(db=mock_db)
        signal = create_mock_signal("BUY")

        result = filter.check(signal)

        assert result.passed is True
        assert result.message == "no_history"

    def test_same_direction_always_allowed(self):
        """Same direction signals always pass."""
        mock_db = MagicMock()
        mock_db.get_recent_signals.return_value = [
            create_recent_signal("BUY", minutes_ago=5)
        ]

        filter = SignalConsistencyFilter(db=mock_db)
        signal = create_mock_signal("BUY")

        result = filter.check(signal)

        assert result.passed is True
        assert result.message == "same_direction"

    def test_same_direction_buy_limit_allowed(self):
        """BUY_LIMIT after BUY is same direction."""
        mock_db = MagicMock()
        mock_db.get_recent_signals.return_value = [
            create_recent_signal("BUY", minutes_ago=5)
        ]

        filter = SignalConsistencyFilter(db=mock_db)
        signal = create_mock_signal("BUY_LIMIT")

        result = filter.check(signal)

        assert result.passed is True
        assert result.message == "same_direction"

    def test_direction_change_blocked_during_cooldown(self):
        """Direction change blocked within cooldown period."""
        mock_db = MagicMock()
        mock_db.get_recent_signals.return_value = [
            create_recent_signal("BUY", minutes_ago=30)  # Within 60min cooldown
        ]

        filter = SignalConsistencyFilter(
            db=mock_db,
            direction_change_cooldown_minutes=60,
        )
        signal = create_mock_signal("SELL", confidence=80)

        result = filter.check(signal)

        assert result.passed is False
        assert result.reason == FilterReason.DIRECTION_COOLDOWN
        assert result.previous_action == "BUY"
        assert result.minutes_since_last is not None

    def test_direction_change_blocked_low_confidence(self):
        """Direction change blocked with low confidence."""
        mock_db = MagicMock()
        mock_db.get_recent_signals.return_value = [
            create_recent_signal("BUY", minutes_ago=90)  # Past cooldown
        ]

        filter = SignalConsistencyFilter(
            db=mock_db,
            direction_change_cooldown_minutes=60,
            direction_change_min_confidence=75,
        )
        signal = create_mock_signal("SELL", confidence=65)  # Below threshold

        result = filter.check(signal)

        assert result.passed is False
        assert result.reason == FilterReason.LOW_CONFIDENCE_REVERSAL
        assert "65%" in result.message

    def test_direction_change_allowed_after_cooldown_high_confidence(self):
        """Direction change allowed after cooldown with high confidence."""
        mock_db = MagicMock()
        mock_db.get_recent_signals.return_value = [
            create_recent_signal("BUY", minutes_ago=90)  # Past cooldown
        ]

        filter = SignalConsistencyFilter(
            db=mock_db,
            direction_change_cooldown_minutes=60,
            direction_change_min_confidence=75,
        )
        signal = create_mock_signal("SELL", confidence=80)  # Above threshold

        result = filter.check(signal)

        assert result.passed is True
        assert result.message == "reversal_approved"

    def test_rapid_flip_flop_blocked(self):
        """Rapid flip-flop pattern detected and blocked."""
        mock_db = MagicMock()
        # Pattern: BUY (40min ago) -> SELL (20min ago) -> BUY (current)
        # All within 2 * 30min threshold = 60min
        mock_db.get_recent_signals.return_value = [
            create_recent_signal("SELL", minutes_ago=20),
            create_recent_signal("BUY", minutes_ago=40),
        ]

        filter = SignalConsistencyFilter(
            db=mock_db,
            direction_change_cooldown_minutes=15,  # Short cooldown to pass first check
            direction_change_min_confidence=70,
            rapid_flip_threshold_minutes=30,
        )
        signal = create_mock_signal("BUY", confidence=80)

        result = filter.check(signal)

        assert result.passed is False
        assert result.reason == FilterReason.RAPID_FLIP

    def test_not_tradeable_skipped(self):
        """NO_TRADE signals skip filter entirely."""
        mock_db = MagicMock()

        filter = SignalConsistencyFilter(db=mock_db)
        signal = create_mock_signal("NO_TRADE")

        result = filter.check(signal)

        assert result.passed is True
        assert result.message == "not_tradeable_skip"
        mock_db.get_recent_signals.assert_not_called()

    def test_wait_signal_skipped(self):
        """WAIT signals skip filter entirely."""
        mock_db = MagicMock()

        filter = SignalConsistencyFilter(db=mock_db)
        signal = create_mock_signal("WAIT")

        result = filter.check(signal)

        assert result.passed is True
        assert result.message == "not_tradeable_skip"
        mock_db.get_recent_signals.assert_not_called()

    def test_sell_to_sell_limit_same_direction(self):
        """SELL_LIMIT after SELL is same direction."""
        mock_db = MagicMock()
        mock_db.get_recent_signals.return_value = [
            create_recent_signal("SELL", minutes_ago=5)
        ]

        filter = SignalConsistencyFilter(db=mock_db)
        signal = create_mock_signal("SELL_LIMIT")

        result = filter.check(signal)

        assert result.passed is True
        assert result.message == "same_direction"

    def test_filters_non_tradeable_signals_from_history(self):
        """Filter ignores NO_TRADE signals in history."""
        mock_db = MagicMock()
        # History has NO_TRADE then BUY
        mock_db.get_recent_signals.return_value = [
            {"id": 2, "action": "NO_TRADE", "confidence": 50,
             "created_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()},
            create_recent_signal("BUY", minutes_ago=30),
        ]

        filter = SignalConsistencyFilter(db=mock_db)
        signal = create_mock_signal("BUY", confidence=70)

        result = filter.check(signal)

        # Should compare against BUY, not NO_TRADE
        assert result.passed is True
        assert result.message == "same_direction"

    def test_minutes_since_with_various_timestamp_formats(self):
        """Test timestamp parsing with various formats."""
        filter = SignalConsistencyFilter()

        # ISO format with Z
        ts_z = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        ) + "Z"
        assert filter._minutes_since(ts_z) >= 29

        # ISO format with +00:00
        ts_offset = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        assert filter._minutes_since(ts_offset) >= 29

        # Space separator format
        ts_space = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        assert filter._minutes_since(ts_space) >= 29

    def test_minutes_since_invalid_timestamp(self):
        """Invalid timestamp returns large value to allow signal."""
        filter = SignalConsistencyFilter()

        result = filter._minutes_since("invalid-timestamp")
        assert result == 999  # Should return large number


class TestFilterResult:
    """Test FilterResult dataclass."""

    def test_default_values(self):
        """Test FilterResult default values."""
        result = FilterResult(passed=True)

        assert result.passed is True
        assert result.reason is None
        assert result.message == ""
        assert result.previous_action is None
        assert result.minutes_since_last is None

    def test_with_all_values(self):
        """Test FilterResult with all values set."""
        result = FilterResult(
            passed=False,
            reason=FilterReason.DIRECTION_COOLDOWN,
            message="Test message",
            previous_action="BUY",
            minutes_since_last=30,
        )

        assert result.passed is False
        assert result.reason == FilterReason.DIRECTION_COOLDOWN
        assert result.message == "Test message"
        assert result.previous_action == "BUY"
        assert result.minutes_since_last == 30
