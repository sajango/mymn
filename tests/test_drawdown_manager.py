"""Tests for DrawdownManager real-time risk tracking.

Tests:
- Daily loss limit (3% max)
- Daily trade limit (5 max)
- Consecutive loss pause (3 → pause)
- Weekly limit (6% max)
- Monthly drawdown (10% from peak)
- Recovery mode (5% → 0.5x position)
- State persistence across restarts
"""

import pytest
from datetime import date
from unittest.mock import MagicMock, patch

from src.drawdown_manager import (
    DrawdownManager,
    DrawdownStatus,
    DrawdownCheckResult,
    get_drawdown_manager,
)


@pytest.fixture
def mock_config():
    """Create mock config with default drawdown limits."""
    config = MagicMock()
    config.daily_max_loss_percent = 3.0
    config.daily_max_trades = 5
    config.consecutive_loss_limit = 3
    config.weekly_max_loss_percent = 6.0
    config.monthly_max_drawdown_percent = 10.0
    config.recovery_mode_threshold = 5.0
    return config


@pytest.fixture
def drawdown_manager(temp_db, mock_config):
    """Create DrawdownManager with temp database."""
    manager = DrawdownManager(db=temp_db, settings=mock_config)
    return manager


class TestDrawdownValidation:
    """Test drawdown validation checks."""

    def test_normal_trading_allowed(self, drawdown_manager):
        """Trading allowed when no limits breached."""
        result = drawdown_manager.validate(10000.0)

        assert result.trading_allowed is True
        assert result.status == DrawdownStatus.NORMAL
        assert result.position_size_modifier == 1.0

    def test_zero_balance_rejected(self, drawdown_manager):
        """Trading rejected with zero balance."""
        result = drawdown_manager.validate(0)

        assert result.trading_allowed is False
        assert result.status == DrawdownStatus.PAUSED
        assert "INVALID_BALANCE" in result.pause_reason

    def test_negative_balance_rejected(self, drawdown_manager):
        """Trading rejected with negative balance."""
        result = drawdown_manager.validate(-100)

        assert result.trading_allowed is False
        assert result.status == DrawdownStatus.PAUSED


class TestDailyLimits:
    """Test daily loss and trade limits."""

    def test_daily_loss_limit_triggers_pause(self, drawdown_manager):
        """3% daily loss triggers trading pause."""
        # Initial state with 10000 balance
        result = drawdown_manager.validate(10000.0)
        assert result.trading_allowed is True

        # Record losses totaling 3%+ of 10000 = 300+
        drawdown_manager.record_trade_result(-150.0, is_win=False, balance=9850)
        drawdown_manager.record_trade_result(-160.0, is_win=False, balance=9690)

        # Should now be paused
        result = drawdown_manager.validate(9690.0)
        assert result.trading_allowed is False
        assert "DAILY_LIMIT" in result.pause_reason

    def test_daily_trade_limit_triggers_pause(self, drawdown_manager):
        """5 trades per day triggers pause."""
        # Initial state
        balance = 10000.0
        drawdown_manager.validate(balance)

        # Record 5 trades (all wins to not trigger loss limit)
        for i in range(5):
            drawdown_manager.record_trade_result(50.0, is_win=True, balance=balance)
            balance += 50

        # 6th trade should be blocked
        result = drawdown_manager.validate(balance)
        assert result.trading_allowed is False
        assert "DAILY_TRADES" in result.pause_reason


class TestConsecutiveLosses:
    """Test consecutive loss tracking."""

    def test_3_consecutive_losses_triggers_pause(self, drawdown_manager):
        """3 consecutive losses triggers trading pause."""
        balance = 10000.0
        drawdown_manager.validate(balance)

        # Record 3 consecutive losses
        drawdown_manager.record_trade_result(-50.0, is_win=False, balance=9950)
        drawdown_manager.record_trade_result(-50.0, is_win=False, balance=9900)
        drawdown_manager.record_trade_result(-50.0, is_win=False, balance=9850)

        # Should be paused
        result = drawdown_manager.validate(9850)
        assert result.trading_allowed is False
        assert "CONSECUTIVE_LOSSES" in result.pause_reason

    def test_win_resets_consecutive_losses(self, drawdown_manager):
        """Winning trade resets consecutive loss counter."""
        balance = 10000.0
        drawdown_manager.validate(balance)

        # Record 2 losses
        drawdown_manager.record_trade_result(-50.0, is_win=False, balance=9950)
        drawdown_manager.record_trade_result(-50.0, is_win=False, balance=9900)

        # Win resets counter
        drawdown_manager.record_trade_result(100.0, is_win=True, balance=10000)

        # Should still be allowed (counter reset)
        result = drawdown_manager.validate(10000)
        assert result.trading_allowed is True


class TestWeeklyLimit:
    """Test weekly loss limit."""

    def test_weekly_loss_limit_triggers_pause(self, drawdown_manager):
        """6% weekly loss triggers pause."""
        balance = 10000.0
        drawdown_manager.validate(balance)

        # Record large losses over multiple days (6%+ = 600+)
        drawdown_manager.record_trade_result(-200.0, is_win=False, balance=9800)
        drawdown_manager.record_trade_result(-200.0, is_win=False, balance=9600)
        drawdown_manager.record_trade_result(-210.0, is_win=False, balance=9390)

        # Should be paused due to weekly limit
        result = drawdown_manager.validate(9390)
        # May be paused by daily OR weekly - both are valid
        assert result.trading_allowed is False


class TestMonthlyDrawdown:
    """Test monthly drawdown from peak."""

    def test_10_percent_drawdown_triggers_pause(self, drawdown_manager, temp_db):
        """10% drawdown from peak triggers pause."""
        # Create initial state with peak balance
        state = {
            "date": date.today().isoformat(),
            "daily_start_balance": 10000.0,
            "daily_pnl": 0,
            "daily_trades": 0,
            "weekly_start_balance": 10000.0,
            "weekly_pnl": 0,
            "weekly_trades": 0,
            "peak_balance": 10000.0,
            "consecutive_losses": 0,
            "recovery_mode": 0,
            "trading_paused": 0,
            "pause_reason": None,
        }
        temp_db.save_drawdown_state(state)

        # Balance dropped to 9000 (10% drawdown)
        result = drawdown_manager.validate(9000.0)

        assert result.trading_allowed is False
        assert "MAX_DRAWDOWN" in result.pause_reason


class TestPositionModifier:
    """Test position size modifier calculation."""

    def test_recovery_mode_reduces_position(self, drawdown_manager, temp_db):
        """5% drawdown triggers 0.5x position modifier."""
        # Create state with peak balance
        state = {
            "date": date.today().isoformat(),
            "daily_start_balance": 10000.0,
            "daily_pnl": 0,
            "daily_trades": 0,
            "weekly_start_balance": 10000.0,
            "weekly_pnl": 0,
            "weekly_trades": 0,
            "peak_balance": 10000.0,
            "consecutive_losses": 0,
            "recovery_mode": 0,
            "trading_paused": 0,
            "pause_reason": None,
        }
        temp_db.save_drawdown_state(state)

        # Balance dropped to 9500 (5% drawdown)
        result = drawdown_manager.validate(9500.0)

        assert result.trading_allowed is True
        assert result.position_size_modifier == 0.5
        assert result.status == DrawdownStatus.RECOVERY

    def test_2_consecutive_losses_reduces_position(self, drawdown_manager):
        """2 consecutive losses triggers 0.5x position modifier."""
        balance = 10000.0
        drawdown_manager.validate(balance)

        # Record 2 consecutive losses
        drawdown_manager.record_trade_result(-50.0, is_win=False, balance=9950)
        drawdown_manager.record_trade_result(-50.0, is_win=False, balance=9900)

        result = drawdown_manager.validate(9900)
        assert result.trading_allowed is True
        assert result.position_size_modifier == 0.5

    def test_1_consecutive_loss_reduces_position(self, drawdown_manager):
        """1 consecutive loss triggers 0.75x position modifier."""
        balance = 10000.0
        drawdown_manager.validate(balance)

        # Record 1 loss
        drawdown_manager.record_trade_result(-50.0, is_win=False, balance=9950)

        result = drawdown_manager.validate(9950)
        assert result.trading_allowed is True
        assert result.position_size_modifier == 0.75


class TestDailyReset:
    """Test daily counter reset."""

    def test_reset_daily_clears_counters(self, drawdown_manager):
        """Daily reset clears all daily counters."""
        balance = 10000.0
        drawdown_manager.validate(balance)

        # Record some activity
        drawdown_manager.record_trade_result(-100.0, is_win=False, balance=9900)
        drawdown_manager.record_trade_result(-100.0, is_win=False, balance=9800)

        # Reset daily
        drawdown_manager.reset_daily(9800.0)

        # Should be able to trade again
        result = drawdown_manager.validate(9800)
        assert result.trading_allowed is True
        assert result.limits_remaining["daily_trades_remaining"] == 5
        assert result.limits_remaining["consecutive_losses_remaining"] == 3


class TestWeeklyReset:
    """Test weekly counter reset."""

    def test_reset_weekly_clears_weekly_counters(self, drawdown_manager):
        """Weekly reset clears weekly P&L and trades."""
        balance = 10000.0
        drawdown_manager.validate(balance)

        # Record weekly losses
        drawdown_manager.record_trade_result(-200.0, is_win=False, balance=9800)

        # Reset weekly
        drawdown_manager.reset_weekly(9800.0)

        # Weekly counters should be reset
        summary = drawdown_manager.get_status_summary()
        assert summary["weekly_pnl"] == 0


class TestStatePersistence:
    """Test state persistence across restarts."""

    def test_state_persists_to_database(self, drawdown_manager, temp_db):
        """State is persisted to database."""
        balance = 10000.0
        drawdown_manager.validate(balance)
        drawdown_manager.record_trade_result(-100.0, is_win=False, balance=9900)

        # Create new manager with same DB
        new_manager = DrawdownManager(db=temp_db, settings=drawdown_manager.config)

        # State should persist
        summary = new_manager.get_status_summary()
        assert summary["daily_pnl"] == -100.0
        assert summary["consecutive_losses"] == 1

    def test_new_day_creates_new_state(self, temp_db, mock_config):
        """New day creates fresh state while preserving peak."""
        # Create old state
        old_state = {
            "date": "2025-01-01",  # Old date
            "daily_start_balance": 10000.0,
            "daily_pnl": -200.0,
            "daily_trades": 3,
            "weekly_start_balance": 10000.0,
            "weekly_pnl": -200.0,
            "weekly_trades": 3,
            "peak_balance": 11000.0,
            "consecutive_losses": 2,
            "recovery_mode": 0,
            "trading_paused": 0,
            "pause_reason": None,
        }
        temp_db.save_drawdown_state(old_state)

        # Create manager - should create new day state
        manager = DrawdownManager(db=temp_db, settings=mock_config)
        result = manager.validate(9800.0)

        # Should create new state for today
        summary = manager.get_status_summary()
        assert summary["date"] == date.today().isoformat()
        assert summary["daily_trades"] == 0
        # Peak balance should be preserved/updated
        assert summary["peak_balance"] >= 9800.0


class TestLimitsRemaining:
    """Test limits_remaining calculation."""

    def test_limits_remaining_accurate(self, drawdown_manager):
        """Limits remaining accurately reflects state."""
        balance = 10000.0
        drawdown_manager.validate(balance)

        # Record 2 trades and 1 loss
        drawdown_manager.record_trade_result(50.0, is_win=True, balance=10050)
        drawdown_manager.record_trade_result(-100.0, is_win=False, balance=9950)

        result = drawdown_manager.validate(9950)

        assert result.limits_remaining["daily_trades_remaining"] == 3
        assert result.limits_remaining["consecutive_losses_remaining"] == 2
        assert result.limits_remaining["daily_loss_remaining_pct"] > 0


class TestStatusSummary:
    """Test status summary reporting."""

    def test_status_summary_complete(self, drawdown_manager):
        """Status summary includes all required fields."""
        drawdown_manager.validate(10000.0)

        summary = drawdown_manager.get_status_summary()

        assert "date" in summary
        assert "daily_pnl" in summary
        assert "daily_trades" in summary
        assert "weekly_pnl" in summary
        assert "consecutive_losses" in summary
        assert "trading_paused" in summary
        assert "peak_balance" in summary


class TestSingleton:
    """Test singleton pattern."""

    def test_get_drawdown_manager_singleton(self):
        """get_drawdown_manager returns singleton instance."""
        # Reset singleton for test
        import src.drawdown_manager as dm
        dm._drawdown_manager = None

        manager1 = get_drawdown_manager()
        manager2 = get_drawdown_manager()

        assert manager1 is manager2

        # Clean up
        dm._drawdown_manager = None
