"""Tests for database module."""

import gc
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.database import (
    Database,
    SignalStatus,
    TradeStatus,
    TrailingState,
)
from src.signal_parser import (
    Signal,
    SignalAction,
    TakeProfit,
    TradingSignal,
)


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for testing."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    yield db
    # Force close any open connections
    gc.collect()


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


class TestDatabaseInit:
    """Test database initialization."""

    def test_creates_tables(self, temp_db):
        """Should create all required tables."""
        conn = temp_db._get_connection()

        # Check tables exist
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t["name"] for t in tables]

        assert "signals" in table_names
        assert "trades" in table_names
        assert "tp_levels" in table_names
        assert "trade_events" in table_names

    def test_creates_indexes(self, temp_db):
        """Should create performance indexes."""
        conn = temp_db._get_connection()

        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        index_names = [i["name"] for i in indexes]

        assert "idx_trades_status" in index_names
        assert "idx_trades_ticket" in index_names


class TestSignalOperations:
    """Test signal CRUD operations."""

    def test_save_signal(self, temp_db, sample_signal):
        """Should save signal and return ID."""
        signal_id = temp_db.save_signal(sample_signal)

        assert signal_id > 0

        # Verify saved data
        conn = temp_db._get_connection()
        row = conn.execute(
            "SELECT * FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()

        assert row["symbol"] == "XAUUSD"
        assert row["action"] == "BUY"
        assert row["entry_price"] == 3350.00
        assert row["confidence"] == 75
        assert row["status"] == "pending"

    def test_save_signal_with_tps(self, temp_db, sample_signal):
        """Should save all TP levels."""
        signal_id = temp_db.save_signal(sample_signal)

        conn = temp_db._get_connection()
        row = conn.execute(
            "SELECT * FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()

        assert row["take_profit_1"] == 3360.00
        assert row["take_profit_2"] == 3375.00
        assert row["take_profit_3"] == 3390.00

    def test_update_signal_status(self, temp_db, sample_signal):
        """Should update signal status."""
        signal_id = temp_db.save_signal(sample_signal)
        temp_db.update_signal_status(signal_id, SignalStatus.EXECUTED)

        conn = temp_db._get_connection()
        row = conn.execute(
            "SELECT status FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()

        assert row["status"] == "executed"

    def test_get_recent_signals(self, temp_db, sample_signal):
        """Should return recent signals."""
        # Save multiple signals
        for _ in range(5):
            temp_db.save_signal(sample_signal)

        signals = temp_db.get_recent_signals(limit=3)
        assert len(signals) == 3


class TestTradeOperations:
    """Test trade CRUD operations."""

    def test_save_trade(self, temp_db, sample_signal):
        """Should save trade with all fields."""
        signal_id = temp_db.save_signal(sample_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.05,
            signal=sample_signal,
        )

        assert trade_id > 0

        trade = temp_db.get_trade_by_id(trade_id)
        assert trade["ticket"] == 12345
        assert trade["volume"] == 0.05
        assert trade["entry_price"] == 3350.00
        assert trade["trailing_state"] == "inactive"
        assert trade["status"] == "open"

    def test_save_trade_creates_tp_levels(self, temp_db, sample_signal):
        """Should create TP level entries."""
        signal_id = temp_db.save_signal(sample_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.05,
            signal=sample_signal,
        )

        tp_levels = temp_db.get_tp_levels(trade_id)
        assert len(tp_levels) == 3
        assert tp_levels[0]["level"] == "TP1"
        assert tp_levels[0]["triggered"] == 0

    def test_get_open_trades(self, temp_db, sample_signal):
        """Should return only open trades."""
        signal_id = temp_db.save_signal(sample_signal)

        # Create open trade
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.05,
            signal=sample_signal,
        )

        # Close it
        temp_db.close_trade(trade_id, 3365.00, 50.00)

        # Create another open trade
        temp_db.save_trade(
            signal_id=signal_id,
            ticket=12346,
            volume=0.03,
            signal=sample_signal,
        )

        open_trades = temp_db.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0]["ticket"] == 12346

    def test_get_trade_by_ticket(self, temp_db, sample_signal):
        """Should find trade by MT5 ticket."""
        signal_id = temp_db.save_signal(sample_signal)
        temp_db.save_trade(
            signal_id=signal_id,
            ticket=99999,
            volume=0.05,
            signal=sample_signal,
        )

        trade = temp_db.get_trade_by_ticket(99999)
        assert trade is not None
        assert trade["ticket"] == 99999


class TestTrailingStopState:
    """Test trailing stop state management."""

    def test_update_trailing_state(self, temp_db, sample_signal):
        """Should update trailing state."""
        signal_id = temp_db.save_signal(sample_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.05,
            signal=sample_signal,
        )

        temp_db.update_trailing_state(
            trade_id,
            TrailingState.ACTIVATED,
            trailing_stop_price=3350.00,
            breakeven_price=3350.50,
        )

        trade = temp_db.get_trade_by_id(trade_id)
        assert trade["trailing_state"] == "activated"
        assert trade["trailing_stop_price"] == 3350.00
        assert trade["breakeven_price"] == 3350.50

    def test_trailing_state_creates_event(self, temp_db, sample_signal):
        """Should log trailing state changes."""
        signal_id = temp_db.save_signal(sample_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.05,
            signal=sample_signal,
        )

        temp_db.update_trailing_state(trade_id, TrailingState.ACTIVATED)

        events = temp_db.get_trade_events(trade_id)
        event_types = [e["event_type"] for e in events]

        assert "OPENED" in event_types
        assert "TRAILING_ACTIVATED" in event_types


class TestTPLevels:
    """Test TP level operations."""

    def test_mark_tp_triggered(self, temp_db, sample_signal):
        """Should mark TP level as triggered."""
        signal_id = temp_db.save_signal(sample_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.05,
            signal=sample_signal,
        )

        temp_db.mark_tp_triggered(trade_id, "TP1")

        tp_levels = temp_db.get_tp_levels(trade_id)
        tp1 = next(tp for tp in tp_levels if tp["level"] == "TP1")

        assert tp1["triggered"] == 1
        assert tp1["triggered_at"] is not None

    def test_update_trade_volume(self, temp_db, sample_signal):
        """Should update volume after partial close."""
        signal_id = temp_db.save_signal(sample_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.10,
            signal=sample_signal,
        )

        temp_db.update_trade_volume(trade_id, 0.06)

        trade = temp_db.get_trade_by_id(trade_id)
        assert trade["volume"] == 0.06
        assert trade["status"] == "partial"


class TestTradeClose:
    """Test trade closing operations."""

    def test_close_trade(self, temp_db, sample_signal):
        """Should close trade with final P&L."""
        signal_id = temp_db.save_signal(sample_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.05,
            signal=sample_signal,
        )

        temp_db.close_trade(trade_id, 3380.00, 150.00)

        trade = temp_db.get_trade_by_id(trade_id)
        assert trade["status"] == "closed"
        assert trade["close_price"] == 3380.00
        assert trade["profit"] == 150.00
        assert trade["close_time"] is not None

    def test_get_trade_summary(self, temp_db, sample_signal):
        """Should calculate trade statistics."""
        signal_id = temp_db.save_signal(sample_signal)

        # Create and close winning trade
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.05,
            signal=sample_signal,
        )
        temp_db.close_trade(trade_id, 3380.00, 100.00)

        # Create and close losing trade
        trade_id2 = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12346,
            volume=0.05,
            signal=sample_signal,
        )
        temp_db.close_trade(trade_id2, 3340.00, -50.00)

        summary = temp_db.get_trade_summary()
        assert summary["total_trades"] == 2
        assert summary["wins"] == 1
        assert summary["losses"] == 1
        assert summary["total_profit"] == 50.00


class TestSignalContext:
    """Test signal context retrieval for Claude prompt."""

    def test_get_signal_context_empty_database(self, temp_db):
        """Test signal context with no signals."""
        context = temp_db.get_signal_context()
        assert context is None

    def test_get_signal_context_with_signals(self, temp_db, sample_signal):
        """Test signal context retrieval with existing signals."""
        # Save multiple BUY signals
        temp_db.save_signal(sample_signal)
        temp_db.save_signal(sample_signal)

        context = temp_db.get_signal_context(limit=3)

        assert context is not None
        assert context["last_action"] == "BUY"  # Most recent
        assert "BUY" in context["recent_sequence"]
        assert context["last_confidence"] == 75
        assert "minutes_since_last" in context
        assert context["wave_position"] is None  # sample_signal has no wave_analysis

    def test_get_signal_context_only_trades_buy_sell(self, temp_db):
        """Test that context only includes BUY/SELL signals."""
        # Manually insert a NO_TRADE signal
        with temp_db._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO signals (timestamp, symbol, action, confidence)
                VALUES (?, ?, ?, ?)
                """,
                ("2026-01-07T10:00:00Z", "XAUUSD", "NO_TRADE", 50),
            )
            conn.commit()

        context = temp_db.get_signal_context()
        assert context is None  # Should not include NO_TRADE

    def test_get_signal_context_respects_limit(self, temp_db, sample_signal):
        """Test that context respects limit parameter."""
        # Save 5 signals
        for _ in range(5):
            temp_db.save_signal(sample_signal)

        context = temp_db.get_signal_context(limit=2)

        # Sequence should only have 2 entries
        arrows = context["recent_sequence"].count("→")
        assert arrows == 1  # 2 items = 1 arrow
