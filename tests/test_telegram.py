"""Tests for Telegram bot module."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.signal_parser import (
    TradingSignal,
    Signal,
    SignalAction,
    TakeProfit,
    WaveAnalysis,
    ConfidenceBreakdown,
)
from src.telegram_bot import TradingBot


@pytest.fixture
def bot():
    """Create a TradingBot instance."""
    with patch("src.telegram_bot.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            telegram_bot_token="test_token",
            telegram_chat_id="123456",
            mt5_symbol="XAUUSD",
            paper_trading=True,
            signal_timeout=300,
        )
        return TradingBot()


@pytest.fixture
def buy_signal():
    """Create a sample BUY signal."""
    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.BUY,
            entry_price=3340.0,
            stop_loss=3310.0,
            stop_loss_atr=3312.5,
            take_profit=[
                TakeProfit(level="TP1", price=3380.0, close_percent=50),
                TakeProfit(level="TP2", price=3420.0, close_percent=30),
                TakeProfit(level="TP3", price=3460.0, close_percent=20),
            ],
            risk_reward=2.67,
            confidence=78,
        ),
        wave_analysis=WaveAnalysis(
            h4_trend="Bullish",
            current_wave="Wave 3 impulse",
            invalidation_price=3290.0,
        ),
    )


@pytest.fixture
def sell_signal():
    """Create a sample SELL signal."""
    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.SELL,
            entry_price=3340.0,
            stop_loss=3370.0,
            take_profit=[
                TakeProfit(level="TP1", price=3300.0, close_percent=50),
            ],
            risk_reward=1.33,
            confidence=65,
        ),
    )


@pytest.fixture
def no_trade_signal():
    """Create a NO_TRADE signal."""
    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.NO_TRADE,
            confidence=30,
            reason="Unclear wave structure",
        ),
    )


@pytest.fixture
def wait_signal():
    """Create a WAIT signal."""
    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.WAIT,
            confidence=55,
            details="Waiting for wave completion",
        ),
    )


class TestMessageFormatting:
    """Tests for signal message formatting."""

    def test_format_buy_signal(self, bot, buy_signal):
        """Test formatting of BUY signal message."""
        message = bot.format_signal_message(buy_signal)

        assert "BUY SIGNAL" in message
        assert "3340.00" in message  # entry
        assert "3310.00" in message  # stop loss
        assert "3380.00" in message  # TP1
        assert "78%" in message  # confidence
        assert "XAUUSD" in message
        assert "Wave 3 impulse" in message
        assert "Bullish" in message

    def test_format_sell_signal(self, bot, sell_signal):
        """Test formatting of SELL signal message."""
        message = bot.format_signal_message(sell_signal)

        assert "SELL SIGNAL" in message
        assert "3340.00" in message  # entry
        assert "3370.00" in message  # stop loss
        assert "3300.00" in message  # TP1
        assert "65%" in message  # confidence

    def test_format_no_trade_signal(self, bot, no_trade_signal):
        """Test formatting of NO_TRADE signal message."""
        message = bot.format_signal_message(no_trade_signal)

        assert "NO TRADE" in message
        assert "30%" in message
        assert "Unclear wave structure" in message

    def test_format_wait_signal(self, bot, wait_signal):
        """Test formatting of WAIT signal message."""
        message = bot.format_signal_message(wait_signal)

        assert "WAIT SIGNAL" in message
        assert "55%" in message
        assert "Waiting for wave completion" in message

    def test_format_signal_with_confidence_breakdown(self, bot):
        """Test formatting signal with confidence breakdown."""
        signal = TradingSignal(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="XAUUSD",
            signal=Signal(
                action=SignalAction.BUY,
                entry_price=3340.0,
                stop_loss=3310.0,
                take_profit=[TakeProfit(level="TP1", price=3380.0, close_percent=100)],
                risk_reward=1.33,
                confidence=78,
            ),
            confidence_breakdown=ConfidenceBreakdown(
                base_score=50,
                timeframe_alignment=10,
                fibonacci_confluence=8,
                session_bonus=5,
                penalties=-5,
                total=78,
            ),
        )
        message = bot.format_signal_message(signal)

        assert "Confidence Breakdown" in message
        assert "Base: 50" in message
        assert "+10 TF" in message
        assert "+8 Fib" in message

    def test_format_signal_without_wave_analysis(self, bot, sell_signal):
        """Test formatting signal without wave analysis section."""
        message = bot.format_signal_message(sell_signal)

        # Should not crash, just skip wave section
        assert "SELL SIGNAL" in message
        assert "Wave Analysis" not in message


class TestInlineKeyboard:
    """Tests for inline keyboard creation."""

    def test_get_signal_keyboard(self, bot):
        """Test keyboard button creation."""
        keyboard = bot.get_signal_keyboard()

        # Verify structure
        assert len(keyboard.inline_keyboard) == 2
        assert len(keyboard.inline_keyboard[0]) == 2  # Execute, Skip
        assert len(keyboard.inline_keyboard[1]) == 1  # Modify

        # Verify button data
        buttons = keyboard.inline_keyboard
        assert buttons[0][0].callback_data == "execute"
        assert buttons[0][1].callback_data == "skip"
        assert buttons[1][0].callback_data == "modify"


class TestPendingSignals:
    """Tests for pending signal management."""

    def test_pending_signals_dict(self, bot):
        """Test pending signals dictionary initialization."""
        assert bot.pending_signals == {}

    def test_set_execute_callback(self, bot):
        """Test setting execute callback."""
        callback = AsyncMock()
        bot.set_execute_callback(callback)
        assert bot._on_execute == callback

    def test_set_modify_callback(self, bot):
        """Test setting modify callback."""
        callback = AsyncMock()
        bot.set_modify_callback(callback)
        assert bot._on_modify == callback


class TestSignalProperties:
    """Tests for signal helper properties."""

    def test_buy_signal_is_tradeable(self, buy_signal):
        """Test is_tradeable for BUY signal."""
        assert buy_signal.is_tradeable is True
        assert buy_signal.is_buy is True
        assert buy_signal.is_sell is False

    def test_sell_signal_is_tradeable(self, sell_signal):
        """Test is_tradeable for SELL signal."""
        assert sell_signal.is_tradeable is True
        assert sell_signal.is_buy is False
        assert sell_signal.is_sell is True

    def test_no_trade_not_tradeable(self, no_trade_signal):
        """Test is_tradeable for NO_TRADE signal."""
        assert no_trade_signal.is_tradeable is False

    def test_wait_not_tradeable(self, wait_signal):
        """Test is_tradeable for WAIT signal."""
        assert wait_signal.is_tradeable is False


class TestBotInitialization:
    """Tests for bot initialization."""

    def test_bot_initial_state(self, bot):
        """Test bot initial state."""
        assert bot.app is None
        assert bot.pending_signals == {}
        assert bot._on_execute is None
        assert bot._on_modify is None

    @pytest.mark.asyncio
    async def test_send_signal_without_init(self, bot, buy_signal):
        """Test send_signal returns None when bot not initialized."""
        result = await bot.send_signal(buy_signal)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_message_without_init(self, bot):
        """Test send_message doesn't crash when bot not initialized."""
        # Should log error but not raise
        await bot.send_message("test")


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_format_signal_missing_optional_fields(self, bot):
        """Test formatting signal with minimal fields."""
        signal = TradingSignal(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="XAUUSD",
            signal=Signal(
                action=SignalAction.BUY,
                confidence=60,
            ),
        )
        message = bot.format_signal_message(signal)

        # Should handle None values gracefully
        assert "BUY SIGNAL" in message
        assert "0.00" in message  # Default entry/stop
        assert "60%" in message

    def test_format_signal_empty_take_profit(self, bot):
        """Test formatting signal with no take profit levels."""
        signal = TradingSignal(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="XAUUSD",
            signal=Signal(
                action=SignalAction.BUY,
                entry_price=3340.0,
                stop_loss=3310.0,
                take_profit=[],
                confidence=70,
            ),
        )
        message = bot.format_signal_message(signal)

        assert "BUY SIGNAL" in message
        assert "Take Profits" in message


class TestAuthorization:
    """Tests for authorization checks."""

    def test_is_authorized_correct_chat_id(self, bot):
        """Test authorization passes for correct chat ID."""
        update = MagicMock()
        update.effective_chat.id = 123456
        assert bot._is_authorized(update) is True

    def test_is_authorized_wrong_chat_id(self, bot):
        """Test authorization fails for wrong chat ID."""
        update = MagicMock()
        update.effective_chat.id = 999999
        assert bot._is_authorized(update) is False

    def test_is_authorized_no_chat(self, bot):
        """Test authorization fails when no chat."""
        update = MagicMock()
        update.effective_chat = None
        assert bot._is_authorized(update) is False


class TestMarkdownEscaping:
    """Tests for markdown escaping."""

    def test_escape_markdown_special_chars(self, bot):
        """Test escaping special markdown characters."""
        text = "Wave 3 [impulse] with *strong* momentum"
        escaped = bot._escape_markdown(text)

        assert "\\[" in escaped
        assert "\\]" in escaped
        assert "\\*" in escaped

    def test_escape_markdown_preserves_normal_text(self, bot):
        """Test normal text is preserved."""
        text = "Normal wave analysis"
        escaped = bot._escape_markdown(text)

        assert escaped == text

    def test_format_signal_escapes_wave_analysis(self, bot):
        """Test wave analysis text is escaped in message."""
        signal = TradingSignal(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="XAUUSD",
            signal=Signal(
                action=SignalAction.BUY,
                entry_price=3340.0,
                stop_loss=3310.0,
                take_profit=[TakeProfit(level="TP1", price=3380.0, close_percent=100)],
                confidence=70,
            ),
            wave_analysis=WaveAnalysis(
                h4_trend="Bullish",
                current_wave="Wave [3] of (5)",  # Contains markdown chars
            ),
        )
        message = bot.format_signal_message(signal)

        # Wave text should be escaped
        assert "\\[3\\]" in message


class TestBackgroundTasks:
    """Tests for background task tracking."""

    def test_background_tasks_initialized_empty(self, bot):
        """Test background tasks set is initialized empty."""
        assert bot._background_tasks == set()
        assert len(bot._background_tasks) == 0
