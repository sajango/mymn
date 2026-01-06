"""Tests for trailing stop manager."""

import gc
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

from src.database import Database, TrailingState
from src.signal_parser import (
    Signal,
    SignalAction,
    TakeProfit,
    TradingSignal,
)
from src.trailing_stop_manager import TrailingStopManager


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for testing."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    yield db
    gc.collect()


@pytest.fixture
def mock_mt5():
    """Create mock MT5 client."""
    mock = MagicMock()
    mock.config = MagicMock()
    mock.config.paper_trading = True
    mock.config.trail_atr_multiplier = 1.5
    mock.config.breakeven_buffer_pips = 5
    mock.get_current_atr.return_value = 10.0  # ATR = $10
    mock.modify_position.return_value = True
    mock.validate_symbol.return_value = True
    mock.close_partial.return_value = True
    return mock


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    mock = MagicMock()
    mock.trail_atr_multiplier = 1.5
    mock.breakeven_buffer_pips = 5
    return mock


@pytest.fixture
def manager(mock_mt5, temp_db, mock_settings):
    """Create manager with mocks."""
    return TrailingStopManager(mt5=mock_mt5, db=temp_db, settings=mock_settings)


@pytest.fixture
def sample_signal():
    """Create sample trading signal."""
    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.BUY,
            entry_price=3350.00,
            stop_loss=3340.00,
            take_profit=[
                TakeProfit(level="TP1", price=3360.00, close_percent=40),
                TakeProfit(level="TP2", price=3375.00, close_percent=30),
                TakeProfit(level="TP3", price=3390.00, close_percent=30),
            ],
            confidence=75,
        ),
    )


@pytest.fixture
def open_trade(temp_db, sample_signal):
    """Create an open trade in database."""
    signal_id = temp_db.save_signal(sample_signal)
    trade_id = temp_db.save_trade(
        signal_id=signal_id,
        ticket=12345,
        volume=0.10,
        signal=sample_signal,
    )
    return trade_id


class TestCheckPosition:
    """Test position checking."""

    def test_trade_not_found(self, manager):
        """Should return error for missing trade."""
        result = manager.check_position(99999)
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_closed_trade_skipped(self, manager, temp_db, sample_signal):
        """Should skip closed trades."""
        signal_id = temp_db.save_signal(sample_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.10,
            signal=sample_signal,
        )
        temp_db.close_trade(trade_id, 3360.00, 100.00)

        result = manager.check_position(trade_id)
        assert result["status"] == "skipped"

    def test_position_not_in_mt5(self, manager, open_trade, mock_mt5):
        """Should sync externally closed position with conservative estimate."""
        mock_mt5.get_position_by_ticket.return_value = None
        mock_mt5.get_position_close_info.return_value = None  # No deal history

        result = manager.check_position(open_trade)
        assert result["status"] == "synced"
        assert result["close_reason"] == "unknown"
        # Conservative estimate: close at SL with calculated loss
        assert result["close_price"] == 3340.00
        assert result["profit"] == -100.0


class TestActivation:
    """Test trailing stop activation."""

    def test_activate_on_tp1_hit_buy(self, manager, open_trade, mock_mt5, temp_db):
        """Should activate when TP1 is hit for buy."""
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12345,
            "current_price": 3365.00,  # Above TP1 (3360)
            "sl": 3340.00,
        }

        result = manager.check_position(open_trade)

        assert result["action"].startswith("activated")
        trade = temp_db.get_trade_by_id(open_trade)
        assert trade["trailing_state"] == "activated"

    def test_activate_on_profit_1r(self, manager, open_trade, mock_mt5, temp_db):
        """Should activate when profit > 1R."""
        # 1R = entry - SL = 3350 - 3340 = 10
        # Current price = entry + 1R = 3350 + 10 = 3360
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12345,
            "current_price": 3359.00,  # Below TP1 but at 0.9R
            "sl": 3340.00,
        }

        result = manager.check_position(open_trade)
        # Should not activate yet
        trade = temp_db.get_trade_by_id(open_trade)
        assert trade["trailing_state"] == "inactive"

        # Now above 1R
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12345,
            "current_price": 3361.00,  # Above 1R
            "sl": 3340.00,
        }

        result = manager.check_position(open_trade)
        trade = temp_db.get_trade_by_id(open_trade)
        assert trade["trailing_state"] == "activated"

    def test_breakeven_with_buffer(self, manager, open_trade, mock_mt5, temp_db):
        """Should set SL to breakeven + buffer on activation."""
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12345,
            "current_price": 3365.00,
            "sl": 3340.00,
        }

        manager.check_position(open_trade)

        # Verify modify was called with breakeven + buffer
        # Entry = 3350, buffer = 5 pips = 0.5 for gold
        # Expected SL = 3350 + 0.5 = 3350.50
        mock_mt5.modify_position.assert_called()
        call_kwargs = mock_mt5.modify_position.call_args.kwargs
        assert call_kwargs["stop_loss"] == 3350.50


class TestTrailing:
    """Test trailing stop movement."""

    def test_start_trailing_after_activation(
        self, manager, open_trade, mock_mt5, temp_db
    ):
        """Should transition to trailing when price moves enough."""
        # First activate
        temp_db.update_trailing_state(
            open_trade,
            TrailingState.ACTIVATED,
            breakeven_price=3350.50,
        )

        # Price moved ATR * 1.5 beyond breakeven
        # breakeven = 3350.50, ATR = 10, trail trigger = 10 * 1.5 = 15
        # Required price = 3350.50 + 15 = 3365.50
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12345,
            "current_price": 3370.00,  # Beyond trigger
            "sl": 3350.50,
        }

        result = manager.check_position(open_trade)

        trade = temp_db.get_trade_by_id(open_trade)
        assert trade["trailing_state"] == "trailing"

    def test_trail_updates_sl(self, manager, open_trade, mock_mt5, temp_db):
        """Should move SL as price moves."""
        # Set to trailing state
        temp_db.update_trailing_state(
            open_trade,
            TrailingState.TRAILING,
            trailing_stop_price=3355.00,
        )
        temp_db.update_stop_loss(open_trade, 3355.00)

        # Price moved up
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12345,
            "current_price": 3380.00,
            "sl": 3355.00,
        }

        result = manager.check_position(open_trade)

        # New SL = current_price - (ATR * multiplier)
        # = 3380 - (10 * 1.5) = 3380 - 15 = 3365
        mock_mt5.modify_position.assert_called()
        call_kwargs = mock_mt5.modify_position.call_args.kwargs
        assert call_kwargs["stop_loss"] == 3365.00

    def test_trail_never_moves_backward(self, manager, open_trade, mock_mt5, temp_db):
        """Should never move SL against trade direction."""
        temp_db.update_trailing_state(
            open_trade,
            TrailingState.TRAILING,
            trailing_stop_price=3365.00,
        )
        temp_db.update_stop_loss(open_trade, 3365.00)

        # Price moved down but SL should stay
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12345,
            "current_price": 3370.00,  # Would calculate SL = 3355, but current is 3365
            "sl": 3365.00,
        }

        result = manager.check_position(open_trade)

        # Should not modify
        mock_mt5.modify_position.assert_not_called()


class TestSellPositions:
    """Test trailing for sell positions."""

    @pytest.fixture
    def sell_signal(self):
        """Create sample sell signal."""
        return TradingSignal(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="XAUUSD",
            signal=Signal(
                action=SignalAction.SELL,
                entry_price=3350.00,
                stop_loss=3360.00,
                take_profit=[
                    TakeProfit(level="TP1", price=3340.00, close_percent=40),
                ],
                confidence=75,
            ),
        )

    @pytest.fixture
    def sell_trade(self, temp_db, sell_signal):
        """Create an open sell trade."""
        signal_id = temp_db.save_signal(sell_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12346,
            volume=0.10,
            signal=sell_signal,
        )
        return trade_id

    def test_activate_sell_on_tp1(self, manager, sell_trade, mock_mt5, temp_db):
        """Should activate sell when TP1 hit."""
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12346,
            "current_price": 3335.00,  # Below TP1 (3340)
            "sl": 3360.00,
        }

        result = manager.check_position(sell_trade)

        trade = temp_db.get_trade_by_id(sell_trade)
        assert trade["trailing_state"] == "activated"

    def test_sell_breakeven_below_entry(self, manager, sell_trade, mock_mt5, temp_db):
        """Should set sell SL below entry for breakeven."""
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12346,
            "current_price": 3335.00,
            "sl": 3360.00,
        }

        manager.check_position(sell_trade)

        # Entry = 3350, buffer = 5 pips = 0.5
        # Expected SL = 3350 - 0.5 = 3349.50
        call_kwargs = mock_mt5.modify_position.call_args.kwargs
        assert call_kwargs["stop_loss"] == 3349.50


class TestTPLevels:
    """Test TP level management."""

    def test_check_tp_triggers_partial_close(
        self, manager, open_trade, mock_mt5, temp_db
    ):
        """Should trigger partial close when TP hit."""
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12345,
            "current_price": 3365.00,  # Above TP1 (3360)
            "volume": 0.10,
            "sl": 3340.00,
        }

        result = manager.check_tp_levels(open_trade)

        assert result["status"] == "ok"
        assert len(result["actions"]) == 1
        assert result["actions"][0]["level"] == "TP1"
        assert result["actions"][0]["status"] == "triggered"

        # Volume should be partially closed (40% of 0.10 = 0.04)
        mock_mt5.close_partial.assert_called_once_with(12345, 0.04)

    def test_marks_tp_triggered(self, manager, open_trade, mock_mt5, temp_db):
        """Should mark TP level as triggered in DB."""
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12345,
            "current_price": 3365.00,
            "volume": 0.10,
            "sl": 3340.00,
        }

        manager.check_tp_levels(open_trade)

        tp_levels = temp_db.get_tp_levels(open_trade)
        tp1 = next(tp for tp in tp_levels if tp["level"] == "TP1")
        assert tp1["triggered"] == 1


class TestFailureTracking:
    """Test consecutive failure tracking."""

    def test_track_failures(self, manager):
        """Should track consecutive failures."""
        manager._consecutive_failures = 2
        assert not manager.should_alert()

        manager._consecutive_failures = 3
        assert manager.should_alert()

    def test_reset_failures(self, manager):
        """Should reset failure counter."""
        manager._consecutive_failures = 5
        manager.reset_failures()
        assert manager._consecutive_failures == 0


class TestPositionSync:
    """Test position sync when MT5 closes position externally."""

    def test_sync_closed_position_with_deal_history(
        self, manager, open_trade, mock_mt5, temp_db
    ):
        """Should sync closed position using deal history."""
        mock_mt5.get_position_by_ticket.return_value = None
        mock_mt5.get_position_close_info.return_value = {
            "ticket": 12345,
            "close_price": 3365.00,
            "profit": 150.00,
            "commission": -1.50,
            "swap": -0.50,
            "close_time": datetime(2026, 1, 6, 12, 0, 0, tzinfo=timezone.utc),
            "close_reason": "tp",
            "deal_ticket": 99999,
        }

        result = manager.check_position(open_trade)

        assert result["status"] == "synced"
        assert result["close_reason"] == "tp"
        assert result["profit"] == 148.00  # 150 - 1.5 - 0.5

        # Verify DB updated
        trade = temp_db.get_trade_by_id(open_trade)
        assert trade["status"] == "closed"
        assert trade["close_price"] == 3365.00
        assert trade["profit"] == 148.00

    def test_sync_closed_position_sl_hit(
        self, manager, open_trade, mock_mt5, temp_db
    ):
        """Should sync position closed by stop loss."""
        mock_mt5.get_position_by_ticket.return_value = None
        mock_mt5.get_position_close_info.return_value = {
            "ticket": 12345,
            "close_price": 3340.00,
            "profit": -100.00,
            "commission": -1.50,
            "swap": 0,
            "close_time": datetime(2026, 1, 6, 12, 0, 0, tzinfo=timezone.utc),
            "close_reason": "sl",
            "deal_ticket": 99999,
        }

        result = manager.check_position(open_trade)

        assert result["status"] == "synced"
        assert result["close_reason"] == "sl"
        assert result["profit"] == -101.50

    def test_sync_closed_position_no_deal_history(
        self, manager, open_trade, mock_mt5, temp_db
    ):
        """Should handle missing deal history with conservative estimate."""
        mock_mt5.get_position_by_ticket.return_value = None
        mock_mt5.get_position_close_info.return_value = None

        result = manager.check_position(open_trade)

        assert result["status"] == "synced"
        assert result["close_reason"] == "unknown"
        assert "estimated" in result["message"].lower()

        # Should have estimated close at SL (3340 for BUY)
        assert result["close_price"] == 3340.00
        # Estimated profit: (3340 - 3350) * 0.10 * 100 = -100.0
        assert result["profit"] == -100.0

        # Trade should be marked closed with estimated values
        trade = temp_db.get_trade_by_id(open_trade)
        assert trade["status"] == "closed"
        assert trade["close_price"] == 3340.00
        assert trade["profit"] == -100.0

    def test_sync_updates_during_check_all(
        self, manager, temp_db, sample_signal, mock_mt5
    ):
        """Should sync closed positions during bulk check."""
        # Create 3 trades
        trade_ids = []
        for i in range(3):
            signal_id = temp_db.save_signal(sample_signal)
            trade_id = temp_db.save_trade(
                signal_id=signal_id,
                ticket=12345 + i,
                volume=0.10,
                signal=sample_signal,
            )
            trade_ids.append(trade_id)

        # First two positions still open, third closed by TP
        def mock_get_position(ticket):
            if ticket == 12347:  # Third position
                return None
            return {"ticket": ticket, "current_price": 3355.00, "sl": 3340.00}

        mock_mt5.get_position_by_ticket.side_effect = mock_get_position
        mock_mt5.get_position_close_info.return_value = {
            "ticket": 12347,
            "close_price": 3360.00,
            "profit": 100.00,
            "commission": 0,
            "swap": 0,
            "close_time": datetime(2026, 1, 6, 12, 0, 0, tzinfo=timezone.utc),
            "close_reason": "tp",
            "deal_ticket": 99999,
        }

        results = manager.check_all_positions()

        # Third trade should be synced
        synced = [r for r in results if r.get("status") == "synced"]
        assert len(synced) == 1
        assert synced[0]["close_reason"] == "tp"


class TestCheckAllPositions:
    """Test bulk position checking."""

    def test_check_all_positions(self, manager, temp_db, sample_signal, mock_mt5):
        """Should check all open positions."""
        # Create multiple trades
        for i in range(3):
            signal_id = temp_db.save_signal(sample_signal)
            temp_db.save_trade(
                signal_id=signal_id,
                ticket=12345 + i,
                volume=0.10,
                signal=sample_signal,
            )

        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12345,
            "current_price": 3355.00,
            "sl": 3340.00,
        }

        results = manager.check_all_positions()

        assert len(results) == 3
