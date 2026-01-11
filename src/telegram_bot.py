"""Telegram bot for trading signal notifications with inline buttons."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import NetworkError, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from src.config import get_settings
from src.signal_parser import TradingSignal, SignalAction
from src.analytics import get_analytics_engine

logger = logging.getLogger(__name__)


class TradingBot:
    """Telegram bot for trading signal notifications.

    Handles:
    - Signal notifications with inline buttons (Execute/Skip/Modify)
    - Signal expiration after configurable timeout
    - Bot commands (/start, /status, /help)
    - Callback handling for user actions

    Security:
    - Only responds to configured chat_id (single user)
    - Bot token loaded from environment only
    """

    def __init__(self):
        self.app: Optional[Application] = None
        self.pending_signals: dict[int, dict] = {}  # message_id -> signal data
        self._on_execute: Optional[Callable] = None
        self._on_modify: Optional[Callable] = None
        self._settings = get_settings()
        self._background_tasks: set = set()  # Track expiration tasks

    def _is_authorized(self, update: Update) -> bool:
        """Check if update is from authorized chat."""
        if not update.effective_chat:
            return False
        return str(update.effective_chat.id) == self._settings.telegram_chat_id

    def set_execute_callback(self, callback: Callable):
        """Set callback for Execute button."""
        self._on_execute = callback

    def set_modify_callback(self, callback: Callable):
        """Set callback for Modify button."""
        self._on_modify = callback

    async def initialize(self):
        """Initialize and start the bot application."""
        self.app = (
            Application.builder()
            .token(self._settings.telegram_bot_token)
            .build()
        )

        # Add command handlers
        self.app.add_handler(CommandHandler("start", self._handle_start))
        self.app.add_handler(CommandHandler("status", self._handle_status))
        self.app.add_handler(CommandHandler("help", self._handle_help))
        self.app.add_handler(CommandHandler("positions", self._handle_positions))
        self.app.add_handler(CommandHandler("analytics", self._handle_analytics))
        self.app.add_handler(CommandHandler("performance", self._handle_performance))
        self.app.add_handler(CommandHandler("risk", self._handle_risk))

        # Add callback handler for inline buttons
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))

        await self.app.initialize()
        await self.app.start()
        # drop_pending_updates=True clears stale updates from previous instances
        # This prevents "terminated by other getUpdates request" conflicts
        await self.app.updater.start_polling(drop_pending_updates=True)

        logger.info("Telegram bot started")

    async def shutdown(self):
        """Shutdown the bot gracefully."""
        # Cancel all background expiration tasks
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()

        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram bot stopped")

    @staticmethod
    def _escape_markdown(text: str) -> str:
        """Escape special Markdown characters in text."""
        escape_chars = ['_', '*', '[', ']', '`']
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text

    def format_signal_message(self, signal: TradingSignal) -> str:
        """Format trading signal as Telegram message with Markdown."""
        s = signal.signal

        if s.action == SignalAction.NO_TRADE:
            reason = s.reason or "Unclear wave structure"
            return (
                f"*NO TRADE SIGNAL*\n\n"
                f"*{signal.symbol}*\n"
                f"{signal.timestamp[:16].replace('T', ' ')}\n\n"
                f"Reason: {reason}\n"
                f"Confidence: {s.confidence}%"
            )

        if s.action == SignalAction.WAIT:
            details = s.details or "Waiting for better setup"
            return (
                f"*WAIT SIGNAL*\n\n"
                f"*{signal.symbol}*\n"
                f"{signal.timestamp[:16].replace('T', ' ')}\n\n"
                f"Details: {details}\n"
                f"Confidence: {s.confidence}%"
            )

        # BUY or SELL signal
        emoji = "BUY" if signal.is_buy else "SELL"
        arrow = "UP" if signal.is_buy else "DOWN"

        # Format take profits
        tp_lines = ""
        if s.take_profit:
            for tp in s.take_profit:
                tp_lines += f"  - {tp.level}: {tp.price:.2f} ({tp.close_percent}%)\n"

        # Wave analysis section (escape user-facing text)
        wave_info = ""
        if signal.wave_analysis:
            wa = signal.wave_analysis
            inv_price = f"{wa.invalidation_price:.2f}" if wa.invalidation_price else "N/A"
            h4_trend = self._escape_markdown(wa.h4_trend)
            current_wave = self._escape_markdown(wa.current_wave)
            wave_info = (
                f"\n*Wave Analysis*\n"
                f"  H4 Trend: {h4_trend}\n"
                f"  Current: {current_wave}\n"
                f"  Invalidation: {inv_price}\n"
            )

        # Confidence breakdown if available
        conf_info = ""
        if signal.confidence_breakdown:
            cb = signal.confidence_breakdown
            conf_info = f"\n*Confidence Breakdown*\n  Base: {cb.base_score}"
            if cb.timeframe_alignment:
                conf_info += f" +{cb.timeframe_alignment} TF"
            if cb.fibonacci_confluence:
                conf_info += f" +{cb.fibonacci_confluence} Fib"
            if cb.session_bonus:
                conf_info += f" {cb.session_bonus:+d} Session"
            if cb.penalties:
                conf_info += f" {cb.penalties} Penalties"
            conf_info += f"\n  Total: {cb.total}%\n"

        entry = s.entry_price or 0
        sl = s.stop_loss or 0
        sl_atr = f"{s.stop_loss_atr:.2f}" if s.stop_loss_atr else "N/A"
        rr = s.risk_reward or 0
        timeout_mins = self._settings.signal_timeout // 60

        return (
            f"*{emoji} SIGNAL* {arrow}\n\n"
            f"*{signal.symbol}*\n"
            f"{signal.timestamp[:16].replace('T', ' ')}\n\n"
            f"*Entry*: {entry:.2f}\n"
            f"*Stop Loss*: {sl:.2f}\n"
            f"*ATR SL*: {sl_atr}\n\n"
            f"*Take Profits*:\n{tp_lines}"
            f"*R:R*: {rr:.2f}\n"
            f"*Confidence*: {s.confidence}%\n"
            f"{wave_info}{conf_info}"
            f"_Expires in {timeout_mins} minutes_"
        )

    def get_signal_keyboard(self) -> InlineKeyboardMarkup:
        """Create inline keyboard for signal actions."""
        keyboard = [
            [
                InlineKeyboardButton("Execute", callback_data="execute"),
                InlineKeyboardButton("Skip", callback_data="skip"),
            ],
            [
                InlineKeyboardButton("Modify", callback_data="modify"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    async def send_signal(self, signal: TradingSignal) -> Optional[int]:
        """Send signal notification with action buttons.

        Args:
            signal: Trading signal to send

        Returns:
            Message ID if sent successfully, None otherwise
        """
        if not self.app:
            logger.error("Bot not initialized")
            return None

        text = self.format_signal_message(signal)
        keyboard = self.get_signal_keyboard()

        try:
            message = await self.app.bot.send_message(
                chat_id=self._settings.telegram_chat_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            # Store pending signal with expiration
            expires_at = datetime.now(timezone.utc).timestamp() + self._settings.signal_timeout
            self.pending_signals[message.message_id] = {
                "signal": signal,
                "expires": expires_at,
            }

            # Schedule expiration task with tracking
            task = asyncio.create_task(
                self._expire_signal(message.message_id, self._settings.signal_timeout)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

            logger.info(f"Signal sent: message_id={message.message_id}")
            return message.message_id

        except NetworkError as e:
            logger.error(f"Network error sending signal: {e}")
            return None
        except TelegramError as e:
            logger.error(f"Telegram error sending signal: {e}")
            return None

    async def _expire_signal(self, message_id: int, timeout: int):
        """Expire signal after timeout period."""
        await asyncio.sleep(timeout)

        if message_id in self.pending_signals:
            del self.pending_signals[message_id]

            try:
                await self.app.bot.edit_message_text(
                    chat_id=self._settings.telegram_chat_id,
                    message_id=message_id,
                    text="*Signal Expired*\n\n_No action taken (timeout)_",
                    parse_mode="Markdown",
                )
                logger.info(f"Signal expired: message_id={message_id}")
            except TelegramError:
                pass  # Message may have been deleted

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if not self._is_authorized(update):
            logger.warning(f"Unauthorized /start from {update.effective_chat.id}")
            return

        symbol = self._settings.mt5_symbol
        await update.message.reply_text(
            f"*Elliott Wave Trading Bot*\n\n"
            f"Trading signals for {symbol}.\n\n"
            f"Commands:\n"
            f"/status - System status\n"
            f"/positions - Active positions\n"
            f"/analytics - Performance report\n"
            f"/performance - Detailed analytics\n"
            f"/help - Help message",
            parse_mode="Markdown",
        )

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self._is_authorized(update):
            logger.warning(f"Unauthorized /status from {update.effective_chat.id}")
            return

        pending = len(self.pending_signals)
        mode = "Paper" if self._settings.paper_trading else "Live"
        symbol = self._settings.mt5_symbol

        await update.message.reply_text(
            f"*System Status*\n\n"
            f"Mode: {mode}\n"
            f"Symbol: {symbol}\n"
            f"Pending signals: {pending}\n"
            f"Bot: Running",
            parse_mode="Markdown",
        )

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not self._is_authorized(update):
            logger.warning(f"Unauthorized /help from {update.effective_chat.id}")
            return
        await self._handle_start(update, context)

    async def _handle_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command."""
        if not self._is_authorized(update):
            logger.warning(f"Unauthorized /positions from {update.effective_chat.id}")
            return

        # Import here to avoid circular imports
        from src.database import get_database

        db = get_database()
        trades = db.get_open_trades()

        if not trades:
            await update.message.reply_text(
                "*Active Positions*\n\n_No open positions_",
                parse_mode="Markdown",
            )
            return

        text = "*Active Positions*\n\n"
        for t in trades:
            emoji = "BUY" if t["action"] == "BUY" else "SELL"
            profit_sign = "+" if t.get("profit", 0) >= 0 else ""
            trail_state = t.get("trailing_state", "inactive")

            text += (
                f"*{t['symbol']}* {emoji}\n"
                f"  Ticket: {t['ticket']}\n"
                f"  Volume: {t['volume']}\n"
                f"  Entry: {t['entry_price']:.2f}\n"
                f"  SL: {t['stop_loss']:.2f}\n"
                f"  Trailing: {trail_state}\n\n"
            )

        await update.message.reply_text(text, parse_mode="Markdown")

    async def _handle_analytics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analytics command - send performance report."""
        if not self._is_authorized(update):
            logger.warning(f"Unauthorized /analytics from {update.effective_chat.id}")
            return

        logger.info("[ANALYTICS] Generating analytics report for Telegram...")
        await self.send_analytics_report()
    
    async def _handle_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /performance command - send detailed performance report."""
        if not self._is_authorized(update):
            logger.warning(f"Unauthorized /performance from {update.effective_chat.id}")
            return
        
        logger.info("[PERFORMANCE] Generating performance report...")
        
        try:
            from src.performance_analytics import get_performance_analytics
            analytics = get_performance_analytics()
            
            # Generate comprehensive report
            report = analytics.generate_performance_report()
            
            # Format for Telegram - Overall Metrics
            metrics = report['overall_metrics']
            msg_parts = [
                "*🎯 Performance Report*\n",
                f"📊 *Overall Stats*",
                f"Trades: {metrics['total_trades']} ({metrics['winning_trades']}W/{metrics['losing_trades']}L)",
                f"Win Rate: {metrics['win_rate']:.1f}%",
                f"Profit Factor: {metrics['profit_factor']:.2f}",
                f"Total P&L: ${metrics['total_pnl']:.2f}",
                f"Avg Win: ${metrics['average_win']:.2f}",
                f"Avg Loss: ${metrics['average_loss']:.2f}",
                f"Max DD: {metrics['max_drawdown_percent']:.1f}%\n",
                
                f"📈 *Risk-Adjusted Returns*",
                f"Sharpe: {metrics['sharpe_ratio']:.2f}",
                f"Sortino: {metrics['sortino_ratio']:.2f}",
                f"Calmar: {metrics['calmar_ratio']:.2f}\n"
            ]
            
            # Pattern Performance
            if report.get('pattern_performance'):
                msg_parts.append("🌊 *Top Wave Patterns*")
                for pattern in report['pattern_performance'][:3]:
                    msg_parts.append(
                        f"{pattern['pattern']}: {pattern['win_rate']:.0f}% win, "
                        f"${pattern['total_profit']:.0f} profit"
                    )
                msg_parts.append("")
            
            # Optimization Insights
            insights = report.get('optimization_insights', {})
            if insights.get('recommendations'):
                msg_parts.append("💡 *Optimization Insights*")
                for rec in insights['recommendations'][:3]:
                    msg_parts.append(f"• {rec}")
                msg_parts.append("")
            
            # Risk Analysis
            risk = report.get('risk_analysis', {})
            if risk:
                msg_parts.append("⚠️ *Risk Analysis*")
                msg_parts.append(f"VaR 95%: ${risk.get('var_95', 0):.2f}")
                msg_parts.append(f"Risk of Ruin: {risk.get('risk_of_ruin', 0):.1%}")
                msg_parts.append(f"Kelly %: {risk.get('kelly_criterion', 0):.1f}%")
                
            await update.message.reply_text(
                "\n".join(msg_parts),
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Performance report error: {e}")
            await update.message.reply_text(
                "Error generating performance report. Please try again later."
            )
    
    async def _handle_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /risk command - show portfolio risk report."""
        if not self._is_authorized(update):
            logger.warning(f"Unauthorized /risk from {update.effective_chat.id}")
            return
        
        logger.info("[RISK] Generating portfolio risk report...")
        
        try:
            from src.portfolio_risk_manager import get_portfolio_risk_manager
            risk_manager = get_portfolio_risk_manager()
            
            # Generate risk report
            report = risk_manager.get_risk_report()
            
            # Format for Telegram
            msg_parts = ["*⚠️ Portfolio Risk Report*\n"]
            
            # Portfolio Heat
            heat = report['portfolio_heat']
            heat_emoji = "🟢" if heat['status'] == 'green' else "🟡" if heat['status'] == 'yellow' else "🔴"
            
            msg_parts.extend([
                f"{heat_emoji} *Portfolio Heat*",
                f"Total Exposure: ${heat['total_exposure']:.2f}",
                f"Heat Level: {heat['heat_percentage']:.1f}%",
                f"Positions: {heat['position_count']}",
                f"Correlation Risk: +{heat['correlated_risk']:.1f}%\n"
            ])
            
            # Risk Adjustment
            adj = report['risk_adjustment']
            msg_parts.extend([
                "📊 *Risk Settings*",
                f"Current Risk: {adj['current_risk']:.1f}%",
                f"Recommended: {adj['recommended_risk']:.1f}%",
                f"Adjustment: {adj['adjustment_factor']:.2f}x",
                f"Reason: {adj['reason']}\n"
            ])
            
            # Trading Status
            status = report['trading_status']
            if status['paused']:
                msg_parts.extend([
                    "🚫 *TRADING PAUSED*",
                    f"Reason: {status['reason']}\n"
                ])
            else:
                msg_parts.append("✅ *Trading Active*\n")
            
            # Correlations
            if report.get('correlations'):
                msg_parts.append("🔗 *Correlation Risks*")
                for corr in report['correlations'][:3]:
                    corr_emoji = "⚠️" if corr['risk'] == 'High' else "📊"
                    msg_parts.append(
                        f"{corr_emoji} {corr['pair']}: {corr['correlation']:.0%}"
                    )
                msg_parts.append("")
            
            # Recommendations
            if report.get('recommendations'):
                msg_parts.append("💡 *Recommendations*")
                for rec in report['recommendations'][:5]:
                    msg_parts.append(rec)
            
            await update.message.reply_text(
                "\n".join(msg_parts),
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Risk report error: {e}")
            await update.message.reply_text(
                "Error generating risk report. Please try again later."
            )

    def _format_overall_stats(self, metrics: dict) -> str:
        """Format overall trading statistics for Telegram."""
        if metrics.get("total_trades", 0) == 0:
            return "*Overall Stats*\n\n_No trades yet_"

        return (
            f"*Overall Stats*\n\n"
            f"Trades: {metrics['total_trades']} "
            f"({metrics['winning_trades']}W / {metrics['losing_trades']}L)\n"
            f"Win Rate: {metrics['win_rate']}%\n"
            f"Profit Factor: {metrics['profit_factor']}\n"
            f"Return: {metrics['total_return_percent']}%\n"
            f"Max Drawdown: {metrics['max_drawdown_percent']}%\n"
            f"Sharpe Ratio: {metrics['sharpe_ratio']}\n"
            f"Avg R:R: {metrics['average_rr_achieved']}"
        )

    def _format_confidence_breakdown(self, data: dict) -> str:
        """Format confidence level breakdown for Telegram."""
        if not data:
            return "*Confidence Analysis*\n\n_No data_"

        lines = ["*Confidence Analysis*\n"]
        labels = {
            "75_plus": "High (75+)",
            "60_to_74": "Medium (60-74)",
            "below_60": "Low (<60)",
        }

        for key, label in labels.items():
            if key in data:
                d = data[key]
                if d["count"] > 0:
                    lines.append(
                        f"{label}: {d['count']} trades, "
                        f"{d['win_rate']}% win, ${d['total_profit']:.0f}"
                    )

        return "\n".join(lines) if len(lines) > 1 else "*Confidence Analysis*\n\n_No data_"

    def _format_session_analysis(self, data: dict) -> str:
        """Format session performance breakdown for Telegram."""
        if not data:
            return "*Session Analysis*\n\n_No data_"

        lines = ["*Session Analysis*\n"]
        labels = {
            "london_ny_overlap": "London/NY Overlap",
            "london": "London",
            "new_york": "New York",
            "asian": "Asian",
        }

        for key, label in labels.items():
            if key in data:
                d = data[key]
                if d["count"] > 0:
                    lines.append(
                        f"{label}: {d['count']} trades, "
                        f"{d['win_rate']}% win, ${d['total_profit']:.0f}"
                    )

        return "\n".join(lines) if len(lines) > 1 else "*Session Analysis*\n\n_No data_"

    def _format_suggestions(self, suggestions: list) -> str:
        """Format optimization suggestions for Telegram."""
        if not suggestions:
            return ""

        lines = ["*Suggestions*\n"]
        for s in suggestions[:5]:  # Limit to 5
            lines.append(f"- {s}")

        return "\n".join(lines)

    async def send_analytics_report(self):
        """Send analytics report to Telegram.

        Callable method for manual /analytics command and scheduled reports.
        Sends overall stats, confidence breakdown, session analysis, and suggestions.
        """
        if not self.app:
            logger.error("Bot not initialized")
            return

        try:
            engine = get_analytics_engine()
            report = engine.generate_full_report()
            suggestions = engine.get_optimization_suggestions()

            # Save to files (JSON + CSV)
            saved = engine.save_to_files()
            logger.info(f"[ANALYTICS] Saved files: {list(saved.keys())}")

            logger.info("[ANALYTICS] Report generated, formatting messages...")

            # Format sections
            stats_msg = self._format_overall_stats(report.get("overall_metrics", {}))
            conf_msg = self._format_confidence_breakdown(report.get("by_confidence_level", {}))
            session_msg = self._format_session_analysis(report.get("by_session", {}))
            suggest_msg = self._format_suggestions(suggestions)

            # Combine into single message (under 4096 chars)
            full_msg = f"{stats_msg}\n\n{conf_msg}\n\n{session_msg}"
            if suggest_msg:
                full_msg += f"\n\n{suggest_msg}"

            # Add timestamp
            generated = report.get("generated_at", "")[:16].replace("T", " ")
            full_msg += f"\n\n_Generated: {generated}_"

            await self.send_message(full_msg)
            logger.info("[ANALYTICS] Report sent successfully")

        except Exception as e:
            logger.error(f"[ANALYTICS] Failed to generate report: {e}")
            await self.send_message("*Analytics Error*\n\n_Failed to generate report_")

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks."""
        if not self._is_authorized(update):
            logger.warning(f"Unauthorized callback from {update.effective_chat.id}")
            return

        query = update.callback_query
        await query.answer()

        message_id = query.message.message_id
        signal_data = self.pending_signals.get(message_id)

        if signal_data is None:
            await query.edit_message_text("Signal expired or already processed")
            return

        signal = signal_data["signal"]
        action = query.data

        if action == "execute":
            del self.pending_signals[message_id]

            if self._on_execute:
                try:
                    result = await self._on_execute(signal)
                    status = "Executed" if result else "Execution Failed"
                except Exception as e:
                    logger.error(f"Execute callback error: {e}")
                    status = "Execution Error"
            else:
                status = "Executed (paper mode)"

            await query.edit_message_text(
                f"*{status}*\n\n"
                f"Action: {signal.signal.action.value}\n"
                f"Entry: {signal.signal.entry_price}",
                parse_mode="Markdown",
            )
            logger.info(f"Signal executed: {signal.signal.action}")

        elif action == "skip":
            del self.pending_signals[message_id]
            await query.edit_message_text("*Signal Skipped*", parse_mode="Markdown")
            logger.info("Signal skipped by user")

        elif action == "modify":
            await query.edit_message_text(
                "*Modify Signal*\n\n"
                "Send modifications:\n"
                "`sl=3310 tp1=3380`\n\n"
                "_Modification not yet implemented_",
                parse_mode="Markdown",
            )

    async def send_message(self, text: str, parse_mode: str = "Markdown"):
        """Send a simple message to the configured chat."""
        if not self.app:
            logger.error("Bot not initialized")
            return

        try:
            await self.app.bot.send_message(
                chat_id=self._settings.telegram_chat_id,
                text=text,
                parse_mode=parse_mode,
            )
        except TelegramError as e:
            logger.error(f"Error sending message: {e}")

    async def send_alert(self, title: str, message: str):
        """Send an alert message (for errors, warnings)."""
        text = f"*{title}*\n\n{message}"
        await self.send_message(text)


# Lazy singleton instance
_trading_bot: Optional[TradingBot] = None


def get_trading_bot() -> TradingBot:
    """Get or create the trading bot singleton."""
    global _trading_bot
    if _trading_bot is None:
        _trading_bot = TradingBot()
    return _trading_bot
