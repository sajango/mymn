"""Integration tests for the MT5 Elliott Wave Trading system.

Tests the complete trading flow from signal generation through execution
with mocked external dependencies (MT5, Telegram, Claude CLI).
"""

import gc
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.risk_guard import RiskCheckResult
from src.signal_filter import SignalConsistencyFilter

# Ensure env vars set before imports
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")


class TestSignalToExecutionFlow:
    """Test complete signal to execution flow."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create temporary database."""
        from src.database import Database

        db_path = tmp_path / "test.db"
        db = Database(db_path)
        yield db
        gc.collect()

    @pytest.fixture
    def mock_mt5(self):
        """Create mock MT5 client."""
        mock = MagicMock()
        mock.config = MagicMock()
        mock.config.paper_trading = True
        mock.config.risk_percent = 1.5
        mock.config.max_position_size = 0.1
        mock._initialized = True
        mock.is_connected.return_value = True
        mock.calculate_position_size.return_value = 0.05
        mock.place_market_order.return_value = 12345
        mock.get_current_spread.return_value = 2.0
        mock.get_current_atr.return_value = 10.0
        mock.modify_position.return_value = True
        mock.close_partial.return_value = True
        return mock

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        from src.config import Settings

        return Settings(
            _env_file=None,
            mt5_symbol="XAUUSD",
            paper_trading=True,
            risk_percent=1.5,
            max_spread_pips=4.0,
            confidence_threshold=60,
        )

    @pytest.fixture
    def buy_signal(self):
        """Create sample buy signal."""
        from src.signal_parser import (
            Signal,
            SignalAction,
            TakeProfit,
            TradingSignal,
        )

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
    def mock_risk_guard(self):
        """Create mock risk guard that passes all checks."""
        mock = MagicMock()
        mock.validate = AsyncMock(return_value=RiskCheckResult(passed=True))
        return mock

    @pytest.fixture
    def permissive_signal_filter(self, temp_db):
        """Create signal filter that allows all signals (no cooldown)."""
        return SignalConsistencyFilter(
            db=temp_db,
            direction_change_cooldown_minutes=0,
            direction_change_min_confidence=0,
            rapid_flip_threshold_minutes=0,
        )

    @pytest.mark.asyncio
    async def test_full_signal_execution_flow(
        self, temp_db, mock_mt5, mock_settings, buy_signal, mock_risk_guard, permissive_signal_filter
    ):
        """Test complete flow: signal → execution → db save."""
        from src.trade_executor import TradeExecutor

        executor = TradeExecutor(
            mt5=mock_mt5, db=temp_db, settings=mock_settings, risk_guard=mock_risk_guard,
            signal_filter=permissive_signal_filter
        )

        # Execute signal
        result = await executor.execute_signal(buy_signal)

        # Verify execution
        assert result["status"] == "executed"
        assert result["ticket"] == 12345
        assert result["volume"] == 0.05

        # Verify signal saved
        signals = temp_db.get_recent_signals(1)
        assert len(signals) == 1
        assert signals[0]["action"] == "BUY"
        assert signals[0]["status"] == "executed"

        # Verify trade saved
        trades = temp_db.get_open_trades()
        assert len(trades) == 1
        assert trades[0]["volume"] == 0.05

    @pytest.mark.asyncio
    async def test_trailing_stop_activation_flow(
        self, temp_db, mock_mt5, mock_settings, buy_signal, mock_risk_guard, permissive_signal_filter
    ):
        """Test trailing stop activates when TP1 hit."""
        from src.trade_executor import TradeExecutor
        from src.trailing_stop_manager import TrailingStopManager

        # Execute trade first
        executor = TradeExecutor(
            mt5=mock_mt5, db=temp_db, settings=mock_settings, risk_guard=mock_risk_guard,
            signal_filter=permissive_signal_filter
        )
        await executor.execute_signal(buy_signal)

        # Mock MT5 position at TP1
        mock_mt5.get_position_by_ticket.return_value = {
            "ticket": 12345,
            "current_price": 3365.00,  # Above TP1
            "sl": 3340.00,
            "volume": 0.05,
        }

        # Check trailing stop
        trail_manager = TrailingStopManager(
            mt5=mock_mt5, db=temp_db, settings=mock_settings
        )
        trades = temp_db.get_open_trades()
        result = trail_manager.check_position(trades[0]["id"])

        # Should activate trailing
        assert "activated" in result.get("action", "").lower() or result.get(
            "status"
        ) in ["ok", "activated"]
        trade = temp_db.get_trade_by_id(trades[0]["id"])
        assert trade["trailing_state"] in ["activated", "trailing"]


class TestSpreadAndSessionChecks:
    """Test spread and session validation integration."""

    def test_spread_check_before_execution(self, tmp_path):
        """Test spread validation before trade execution."""
        from src.spread_checker import SpreadChecker
        from unittest.mock import MagicMock

        mock_mt5 = MagicMock()
        mock_mt5.get_current_spread.return_value = 2.0

        from src.config import Settings

        settings = Settings(_env_file=None, max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mock_mt5, settings=settings)
        result = checker.check_spread(symbol="XAUUSD")

        assert result.spread_ok is True
        assert result.current_spread_pips == 2.0

    def test_spread_blocks_high_spread(self, tmp_path):
        """Test high spread blocks execution."""
        from src.spread_checker import SpreadChecker
        from unittest.mock import MagicMock

        mock_mt5 = MagicMock()
        mock_mt5.get_current_spread.return_value = 6.0  # Too high

        from src.config import Settings

        settings = Settings(_env_file=None, max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mock_mt5, settings=settings)
        result = checker.check_spread(symbol="XAUUSD")

        assert result.spread_ok is False
        assert "Spread" in result.message

    def test_session_modifier_integration(self):
        """Test session detection provides confidence modifier."""
        from datetime import datetime, timezone

        from src.session_detector import SessionDetector

        detector = SessionDetector()

        # Test during London session (12:00 UTC)
        london_time = datetime(2025, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(london_time)

        assert info.session.value == "london"
        assert info.modifier > 0  # Should have positive modifier


class TestNewsBlackoutIntegration:
    """Test news blackout integration."""

    @patch("src.news_calendar.get_settings")
    def test_blackout_prevents_trading(self, mock_settings):
        """Test news blackout prevents trade entry."""
        from datetime import datetime, timedelta, timezone

        from src.news_calendar import NewsCalendar, NewsEvent

        mock_settings.return_value = MagicMock(
            news_blackout_before_mins=30,
            news_blackout_after_mins=15,
        )

        calendar = NewsCalendar()
        now = datetime.now(timezone.utc)

        # Add upcoming high-impact event
        calendar._cache = [
            NewsEvent(
                timestamp=now + timedelta(minutes=15),
                currency="USD",
                impact="high",
                event_name="FOMC",
            )
        ]
        calendar._cache_time = now

        result = calendar.is_in_blackout()

        assert result.in_blackout is True
        assert result.event.event_name == "FOMC"


class TestDatabaseIntegration:
    """Test database operations integration."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create temporary database."""
        from src.database import Database

        db_path = tmp_path / "test.db"
        db = Database(db_path)
        yield db
        gc.collect()

    def test_signal_to_trade_lifecycle(self, temp_db):
        """Test full signal -> trade -> close lifecycle."""
        from src.signal_parser import (
            Signal,
            SignalAction,
            TakeProfit,
            TradingSignal,
        )

        # Create signal
        signal = TradingSignal(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="XAUUSD",
            signal=Signal(
                action=SignalAction.BUY,
                entry_price=3350.00,
                stop_loss=3340.00,
                take_profit=[
                    TakeProfit(level="TP1", price=3360.00, close_percent=40),
                ],
                confidence=75,
            ),
        )

        # Save signal
        signal_id = temp_db.save_signal(signal)
        assert signal_id > 0

        # Execute as trade
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.05,
            signal=signal,
        )
        assert trade_id > 0

        # Verify trade
        trades = temp_db.get_open_trades()
        assert len(trades) == 1
        assert trades[0]["ticket"] == 12345

        # Close trade
        temp_db.close_trade(trade_id, close_price=3360.00, profit=50.00)

        # Verify closed
        open_trades = temp_db.get_open_trades()
        assert len(open_trades) == 0

    def test_trailing_state_transitions(self, temp_db):
        """Test trailing stop state machine transitions."""
        from src.database import TrailingState
        from src.signal_parser import (
            Signal,
            SignalAction,
            TakeProfit,
            TradingSignal,
        )

        # Create and save trade
        signal = TradingSignal(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="XAUUSD",
            signal=Signal(
                action=SignalAction.BUY,
                entry_price=3350.00,
                stop_loss=3340.00,
                take_profit=[
                    TakeProfit(level="TP1", price=3360.00, close_percent=40),
                ],
                confidence=75,
            ),
        )
        signal_id = temp_db.save_signal(signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=12345,
            volume=0.05,
            signal=signal,
        )

        # Initial state
        trade = temp_db.get_trade_by_id(trade_id)
        assert trade["trailing_state"] == "inactive"

        # Activate
        temp_db.update_trailing_state(
            trade_id, TrailingState.ACTIVATED, breakeven_price=3350.50
        )
        trade = temp_db.get_trade_by_id(trade_id)
        assert trade["trailing_state"] == "activated"

        # Start trailing
        temp_db.update_trailing_state(
            trade_id, TrailingState.TRAILING, trailing_stop_price=3355.00
        )
        trade = temp_db.get_trade_by_id(trade_id)
        assert trade["trailing_state"] == "trailing"


class TestErrorHandling:
    """Test error handling across components."""

    def test_signal_parser_handles_invalid_json(self):
        """Test signal parser gracefully handles invalid input."""
        from src.signal_parser import parse_trading_signal

        result = parse_trading_signal("not valid json at all")
        assert result is None

    def test_signal_parser_handles_missing_fields(self):
        """Test signal parser handles incomplete data."""
        from src.signal_parser import parse_trading_signal

        # Missing required fields
        incomplete = '{"timestamp": "2024-01-01T00:00:00Z"}'
        result = parse_trading_signal(incomplete)
        assert result is None

    @pytest.mark.asyncio
    async def test_executor_handles_mt5_failure(self, tmp_path):
        """Test executor handles MT5 order failure gracefully."""
        import gc

        from src.database import Database
        from src.signal_parser import (
            Signal,
            SignalAction,
            TakeProfit,
            TradingSignal,
        )
        from src.trade_executor import TradeExecutor

        # Setup
        db = Database(tmp_path / "test.db")
        mock_mt5 = MagicMock()
        mock_mt5.config = MagicMock(paper_trading=True)
        mock_mt5.calculate_position_size.return_value = 0.05
        mock_mt5.place_market_order.return_value = None  # Failure

        from src.config import Settings

        settings = Settings(_env_file=None, paper_trading=True)

        # Mock risk guard to pass validation
        mock_risk_guard = MagicMock()
        mock_risk_guard.validate = AsyncMock(return_value=RiskCheckResult(passed=True))

        # Create permissive signal filter to bypass cooldown
        permissive_filter = SignalConsistencyFilter(
            db=db,
            direction_change_cooldown_minutes=0,
            direction_change_min_confidence=0,
            rapid_flip_threshold_minutes=0,
        )

        signal = TradingSignal(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="XAUUSD",
            signal=Signal(
                action=SignalAction.BUY,
                entry_price=3350.00,
                stop_loss=3340.00,
                take_profit=[
                    TakeProfit(level="TP1", price=3360.00, close_percent=40),
                ],
                confidence=75,
            ),
        )

        executor = TradeExecutor(
            mt5=mock_mt5, db=db, settings=settings, risk_guard=mock_risk_guard,
            signal_filter=permissive_filter
        )
        result = await executor.execute_signal(signal)

        assert result["status"] == "rejected"
        assert result["reason"] == "order_failed"

        gc.collect()


class TestConfigurationIntegration:
    """Test configuration loading and validation."""

    def test_settings_validation(self):
        """Test settings validates configuration values."""
        from src.config import Settings

        settings = Settings(
            _env_file=None,
            mt5_symbol="XAUUSD",
            risk_percent=1.5,
            max_spread_pips=4.0,
        )

        assert settings.mt5_symbol == "XAUUSD"
        assert settings.risk_percent == 1.5
        assert settings.paper_trading is True  # Default

    def test_settings_project_root_detection(self):
        """Test project root is correctly detected."""
        from src.config import Settings

        settings = Settings(_env_file=None)
        assert settings.project_root.exists()
        assert "mymn" in str(settings.project_root).lower()


class TestClaudeClientIntegration:
    """Test Claude client integration."""

    @patch("src.claude_client.subprocess.run")
    def test_cli_verification(self, mock_run):
        """Test CLI installation verification."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="claude version 1.0.0"
        )

        from src.claude_client import ClaudeClient

        client = ClaudeClient()
        assert client.verify_cli_installed() is True

    @patch("src.claude_client.subprocess.run")
    def test_analysis_with_valid_response(self, mock_run, tmp_path):
        """Test analysis returns valid signal."""
        valid_response = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "entry_price": 3340.00,
                "stop_loss": 3310.00,
                "confidence": 78
            }
        }
        ```'''
        mock_run.return_value = MagicMock(returncode=0, stdout=valid_response)

        # Create test files
        instructions = tmp_path / "instructions.md"
        instructions.write_text("test")
        h4_csv = tmp_path / "xauusd_h4.csv"
        h4_csv.write_text("data")

        from src.claude_client import ClaudeClient

        client = ClaudeClient(instructions_path=instructions)
        signal = client.analyze({"H4": h4_csv})

        assert signal.signal.action.value == "BUY"
        assert signal.signal.confidence == 78
