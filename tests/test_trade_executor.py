"""Tests for trade executor module."""

import gc
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database import Database, SignalStatus
from src.risk_guard import RiskCheckResult
from src.signal_filter import FilterResult
from src.signal_parser import (
    Signal,
    SignalAction,
    TakeProfit,
    TradingSignal,
)
from src.trade_executor import TradeExecutor


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
    mock.config.risk_percent = 1.5
    mock.config.max_position_size = 0.1
    mock.config.confidence_full_position = 75
    mock.config.confidence_half_position = 60
    mock.calculate_position_size.return_value = 0.05
    mock.place_market_order.return_value = -1  # Paper trade ticket
    return mock


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    mock = MagicMock()
    mock.paper_trading = True
    return mock


@pytest.fixture
def mock_risk_guard():
    """Create mock risk guard that passes all checks."""
    mock = MagicMock()
    mock.validate = AsyncMock(return_value=RiskCheckResult(passed=True))
    return mock


@pytest.fixture
def mock_signal_filter():
    """Create mock signal filter that passes all checks."""
    mock = MagicMock()
    mock.check.return_value = FilterResult(passed=True, message="test_bypass")
    return mock


@pytest.fixture
def executor(mock_mt5, temp_db, mock_settings, mock_risk_guard, mock_signal_filter):
    """Create executor with mocks."""
    exec = TradeExecutor(
        mt5=mock_mt5, db=temp_db, settings=mock_settings, risk_guard=mock_risk_guard
    )
    exec._signal_filter = mock_signal_filter
    return exec


@pytest.fixture
def buy_signal():
    """Create sample buy signal."""
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
def no_trade_signal():
    """Create NO_TRADE signal."""
    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.NO_TRADE,
            confidence=0,
            reason="No clear wave structure",
        ),
    )


class TestExecuteSignal:
    """Test signal execution."""

    @pytest.mark.asyncio
    async def test_execute_buy_signal(self, executor, buy_signal):
        """Should execute buy signal."""
        result = await executor.execute_signal(buy_signal)

        assert result["status"] == "executed"
        assert result["ticket"] == -1  # Paper trade
        assert result["volume"] == 0.05
        assert result["order_type"] == "BUY"
        assert result["paper_mode"] is True

    @pytest.mark.asyncio
    async def test_skip_no_trade_signal(self, executor, no_trade_signal):
        """Should skip NO_TRADE signals."""
        result = await executor.execute_signal(no_trade_signal)

        assert result["status"] == "skipped"
        assert result["reason"] == "not_tradeable"

    @pytest.mark.asyncio
    async def test_saves_signal_to_db(self, executor, buy_signal, temp_db):
        """Should save signal to database."""
        result = await executor.execute_signal(buy_signal)

        signals = temp_db.get_recent_signals(1)
        assert len(signals) == 1
        assert signals[0]["action"] == "BUY"

    @pytest.mark.asyncio
    async def test_saves_trade_to_db(self, executor, buy_signal, temp_db):
        """Should save trade to database."""
        result = await executor.execute_signal(buy_signal)

        trades = temp_db.get_open_trades()
        assert len(trades) == 1
        assert trades[0]["volume"] == 0.05

    @pytest.mark.asyncio
    async def test_updates_signal_status(self, executor, buy_signal, temp_db):
        """Should mark signal as executed."""
        result = await executor.execute_signal(buy_signal)

        signals = temp_db.get_recent_signals(1)
        assert signals[0]["status"] == "executed"

    @pytest.mark.asyncio
    async def test_rejects_missing_entry(self, executor, temp_db):
        """Should reject signal without entry price."""
        signal = TradingSignal(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="XAUUSD",
            signal=Signal(
                action=SignalAction.BUY,
                entry_price=None,  # Missing
                stop_loss=3340.00,
                confidence=75,
            ),
        )

        result = await executor.execute_signal(signal)

        assert result["status"] == "rejected"
        assert result["reason"] == "missing_entry_or_sl"


class TestPositionSizing:
    """Test position sizing with confidence."""

    @pytest.mark.asyncio
    async def test_calls_position_size_with_confidence(
        self, executor, buy_signal, mock_mt5
    ):
        """Should pass confidence to position sizing."""
        await executor.execute_signal(buy_signal)

        mock_mt5.calculate_position_size.assert_called_once_with(
            symbol="XAUUSD",
            entry_price=3350.00,
            stop_loss=3340.00,
            confidence=75,
        )


class TestOrderPlacement:
    """Test order placement."""

    @pytest.mark.asyncio
    async def test_places_market_order(self, executor, buy_signal, mock_mt5):
        """Should place market order with correct params."""
        await executor.execute_signal(buy_signal)

        mock_mt5.place_market_order.assert_called_once()
        call_kwargs = mock_mt5.place_market_order.call_args.kwargs

        assert call_kwargs["symbol"] == "XAUUSD"
        assert call_kwargs["order_type"] == "BUY"
        assert call_kwargs["volume"] == 0.05
        assert call_kwargs["stop_loss"] == 3340.00
        assert call_kwargs["take_profit"] == 3360.00  # TP1

    @pytest.mark.asyncio
    async def test_handles_order_failure(self, executor, buy_signal, mock_mt5, temp_db):
        """Should handle order placement failure."""
        mock_mt5.place_market_order.return_value = None

        result = await executor.execute_signal(buy_signal)

        assert result["status"] == "rejected"
        assert result["reason"] == "order_failed"

        # Signal should be marked rejected
        signals = temp_db.get_recent_signals(1)
        assert signals[0]["status"] == "rejected"


class TestSellSignal:
    """Test sell signal execution."""

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
                confidence=80,
            ),
        )

    @pytest.mark.asyncio
    async def test_execute_sell_signal(self, executor, sell_signal, mock_mt5):
        """Should execute sell signal."""
        result = await executor.execute_signal(sell_signal)

        assert result["status"] == "executed"
        assert result["order_type"] == "SELL"

        call_kwargs = mock_mt5.place_market_order.call_args.kwargs
        assert call_kwargs["order_type"] == "SELL"


class TestSkipSignal:
    """Test signal skipping."""

    def test_skip_signal(self, executor, buy_signal, temp_db):
        """Should mark signal as skipped."""
        signal_id = executor.skip_signal(buy_signal, "user_declined")

        signals = temp_db.get_recent_signals(1)
        assert signals[0]["status"] == "skipped"


class TestPositionsSummary:
    """Test positions summary."""

    def test_no_positions(self, executor, temp_db):
        """Should return no positions message."""
        summary = executor.get_open_positions_summary()
        assert summary == "No open positions"

    @pytest.mark.asyncio
    async def test_with_positions(self, executor, buy_signal, temp_db):
        """Should return formatted positions."""
        await executor.execute_signal(buy_signal)

        summary = executor.get_open_positions_summary()

        assert "XAUUSD" in summary
        assert "0.05" in summary
        assert "3350.00" in summary
