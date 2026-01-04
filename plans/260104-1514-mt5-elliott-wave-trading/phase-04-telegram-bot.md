# Phase 4: Telegram Bot

## Context Links
- [Plan Overview](./plan.md)
- [Phase 3: Claude Integration](./phase-03-claude-integration.md)
- [Telegram Research](./research/researcher-03-telegram-apscheduler.md)

## Overview
- **Priority**: P1
- **Status**: Pending
- **Effort**: 4h
- **Description**: Build Telegram bot for signal notifications with inline buttons

## Key Insights
- python-telegram-bot v20+ uses asyncio
- Inline keyboards for Execute/Skip/Modify
- 5-minute timeout for signal confirmation
- Single user design (user's chat ID)

## Requirements

### Functional
- Send formatted signal messages
- Inline buttons: Execute, Skip, Modify
- Handle button callbacks
- Signal timeout after 5 minutes
- Status commands (/start, /status, /positions)

### Non-Functional
- Async operation
- Retry on network errors
- Queue signals if bot offline

## Architecture

### Message Flow
```
Signal Generated
        ↓
Format message with Markdown
        ↓
Add InlineKeyboardMarkup
        ↓
Send to user
        ↓
Store pending signal with timeout
        ↓
CallbackQueryHandler processes response
        ↓
Execute/Skip/Modify action
```

### Button Layout
```
[✅ Execute] [⏭️ Skip]
    [✏️ Modify]
```

## Related Code Files

### Files to Create
- `src/telegram_bot.py` - Bot and handlers

## Implementation Steps

1. **Create src/telegram_bot.py**

```python
"""Telegram bot for trading signal notifications"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.error import TelegramError, NetworkError

from src.config import config
from src.signal_parser import TradingSignal

logger = logging.getLogger(__name__)


class TradingBot:
    def __init__(self):
        self.app: Optional[Application] = None
        self.pending_signals: dict[int, dict] = {}  # message_id -> signal data
        self._on_execute: Optional[Callable] = None
        self._on_modify: Optional[Callable] = None

    def set_execute_callback(self, callback: Callable):
        """Set callback for Execute button"""
        self._on_execute = callback

    def set_modify_callback(self, callback: Callable):
        """Set callback for Modify button"""
        self._on_modify = callback

    async def initialize(self):
        """Initialize the bot application"""
        self.app = (
            Application.builder()
            .token(config.telegram_token)
            .build()
        )

        # Add handlers
        self.app.add_handler(CommandHandler("start", self._handle_start))
        self.app.add_handler(CommandHandler("status", self._handle_status))
        self.app.add_handler(CommandHandler("help", self._handle_help))
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

        logger.info("Telegram bot started")

    async def shutdown(self):
        """Shutdown the bot"""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram bot stopped")

    def format_signal_message(self, signal: TradingSignal) -> str:
        """Format trading signal as Telegram message"""
        s = signal.signal

        if s.action == "NO_TRADE":
            return f"""
⚪ *NO TRADE SIGNAL*

📊 *{signal.symbol}*
🕐 {signal.timestamp.strftime("%Y-%m-%d %H:%M")}

📝 Reason: {signal.wave_analysis.current_wave if signal.wave_analysis else "Unclear wave structure"}
🎯 Confidence: {s.confidence}%
"""

        emoji = "🟢" if s.action == "BUY" else "🔴"
        arrow = "📈" if s.action == "BUY" else "📉"

        # Format take profits
        tp_lines = ""
        if s.take_profit:
            for tp in s.take_profit:
                tp_lines += f"  • {tp.level}: {tp.price:.2f} ({tp.close_percent}%)\n"

        # Wave analysis
        wave_info = ""
        if signal.wave_analysis:
            wa = signal.wave_analysis
            wave_info = f"""
📊 *Wave Analysis*
• H4 Trend: {wa.h4_trend}
• Current: {wa.current_wave}
• Invalidation: {wa.invalidation_price:.2f if wa.invalidation_price else 'N/A'}
"""

        return f"""
{emoji} *{s.action} SIGNAL* {arrow}

📊 *{signal.symbol}*
🕐 {signal.timestamp.strftime("%Y-%m-%d %H:%M")}

💰 *Entry*: {s.entry_price:.2f}
🛑 *Stop Loss*: {s.stop_loss:.2f}
📍 *ATR SL*: {s.stop_loss_atr:.2f if s.stop_loss_atr else 'N/A'}

🎯 *Take Profits*:
{tp_lines}
📊 *R:R*: {s.risk_reward:.2f}
🎯 *Confidence*: {s.confidence}%
{wave_info}
⏰ _Expires in 5 minutes_
"""

    def get_signal_keyboard(self) -> InlineKeyboardMarkup:
        """Create inline keyboard for signal"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Execute", callback_data="execute"),
                InlineKeyboardButton("⏭️ Skip", callback_data="skip"),
            ],
            [
                InlineKeyboardButton("✏️ Modify", callback_data="modify"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    async def send_signal(self, signal: TradingSignal) -> Optional[int]:
        """Send signal notification with buttons"""
        if not self.app:
            logger.error("Bot not initialized")
            return None

        text = self.format_signal_message(signal)
        keyboard = self.get_signal_keyboard()

        try:
            message = await self.app.bot.send_message(
                chat_id=config.telegram_chat_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            # Store pending signal
            self.pending_signals[message.message_id] = {
                "signal": signal,
                "expires": datetime.utcnow().timestamp() + config.signal_timeout,
            }

            # Schedule expiration
            asyncio.create_task(
                self._expire_signal(message.message_id, config.signal_timeout)
            )

            logger.info(f"Signal sent: message_id={message.message_id}")
            return message.message_id

        except TelegramError as e:
            logger.error(f"Failed to send signal: {e}")
            return None

    async def _expire_signal(self, message_id: int, timeout: int):
        """Expire signal after timeout"""
        await asyncio.sleep(timeout)

        if message_id in self.pending_signals:
            del self.pending_signals[message_id]

            try:
                await self.app.bot.edit_message_text(
                    chat_id=config.telegram_chat_id,
                    message_id=message_id,
                    text="⏰ *Signal Expired*\n\n_No action taken (5 min timeout)_",
                    parse_mode="Markdown",
                )
            except TelegramError:
                pass  # Message may have been deleted

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "🤖 *Elliott Wave Trading Bot*\n\n"
            "I will send you trading signals for XAUUSD.\n\n"
            "Commands:\n"
            "/status - Check system status\n"
            "/help - Show this message",
            parse_mode="Markdown",
        )

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        pending = len(self.pending_signals)
        mode = "📄 Paper" if config.paper_trading else "💰 Live"

        await update.message.reply_text(
            f"📊 *System Status*\n\n"
            f"Mode: {mode}\n"
            f"Pending signals: {pending}\n"
            f"Bot: ✅ Running",
            parse_mode="Markdown",
        )

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await self._handle_start(update, context)

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()

        message_id = query.message.message_id
        signal_data = self.pending_signals.get(message_id)

        if signal_data is None:
            await query.edit_message_text("⚠️ Signal expired or already processed")
            return

        signal = signal_data["signal"]
        action = query.data

        if action == "execute":
            del self.pending_signals[message_id]

            if self._on_execute:
                result = await self._on_execute(signal)
                status = "✅ Executed" if result else "❌ Failed"
            else:
                status = "✅ Executed (paper mode)"

            await query.edit_message_text(
                f"{status}\n\n"
                f"Action: {signal.signal.action}\n"
                f"Entry: {signal.signal.entry_price}",
                parse_mode="Markdown",
            )

        elif action == "skip":
            del self.pending_signals[message_id]
            await query.edit_message_text("⏭️ *Signal Skipped*", parse_mode="Markdown")

        elif action == "modify":
            await query.edit_message_text(
                "✏️ *Modify Signal*\n\n"
                "Send a message with modifications:\n"
                "`sl=3310 tp1=3380`\n\n"
                "_Not yet implemented_",
                parse_mode="Markdown",
            )

    async def send_message(self, text: str, parse_mode: str = "Markdown"):
        """Send a simple message"""
        if not self.app:
            return

        await self.app.bot.send_message(
            chat_id=config.telegram_chat_id,
            text=text,
            parse_mode=parse_mode,
        )


# Singleton instance
trading_bot = TradingBot()
```

2. **Add tests**

```python
# tests/test_telegram.py
import pytest
from datetime import datetime
from src.signal_parser import TradingSignal, Signal, TakeProfit
from src.telegram_bot import TradingBot


@pytest.fixture
def sample_signal():
    return TradingSignal(
        timestamp=datetime.utcnow(),
        symbol="XAUUSD",
        signal=Signal(
            action="BUY",
            entry_price=3340.0,
            stop_loss=3310.0,
            stop_loss_atr=3312.5,
            take_profit=[
                TakeProfit(level="TP1", price=3380.0, close_percent=50),
                TakeProfit(level="TP2", price=3420.0, close_percent=30),
            ],
            risk_reward=2.67,
            confidence=78,
        ),
    )


def test_format_buy_signal(sample_signal):
    bot = TradingBot()
    message = bot.format_signal_message(sample_signal)

    assert "BUY SIGNAL" in message
    assert "3340.00" in message
    assert "3310.00" in message
    assert "78%" in message


def test_format_no_trade_signal():
    signal = TradingSignal(
        timestamp=datetime.utcnow(),
        symbol="XAUUSD",
        signal=Signal(action="NO_TRADE", confidence=30),
    )
    bot = TradingBot()
    message = bot.format_signal_message(signal)

    assert "NO TRADE" in message
    assert "30%" in message
```

## Todo List

- [ ] Create src/telegram_bot.py
- [ ] Implement send_signal() with formatting
- [ ] Implement inline keyboard buttons
- [ ] Implement callback handlers
- [ ] Implement signal expiration
- [ ] Add /start, /status, /help commands
- [ ] Write tests/test_telegram.py
- [ ] Test with real bot

## Success Criteria

- [ ] Bot responds to /start
- [ ] Signal message formatted correctly
- [ ] Buttons work (Execute/Skip/Modify)
- [ ] Signal expires after 5 minutes
- [ ] Error handling on network issues

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Bot token invalid | Low | High | Check on startup |
| Network issues | Low | Medium | Retry on failure |
| Message too long | Low | Low | Truncate if needed |

## Security Considerations

- Bot token from environment only
- Chat ID restricted to single user
- No sensitive data in messages

## Next Steps

→ [Phase 5: Trade Execution](./phase-05-trade-execution.md)
