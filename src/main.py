"""Main entry point and orchestrator for MT5 Elliott Wave trading system.

Coordinates:
- APScheduler for M15 analysis and 30s TP monitoring
- MT5 data export and trade execution (sync via executor)
- Claude CLI for wave analysis (sync via executor)
- Telegram bot for notifications (async)
- Session/spread validation before trading
- Circuit breaker for consecutive failures
"""

import asyncio
import logging
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from src.claude_client import claude_client
from src.analytics import get_analytics_engine
from src.config import get_settings
from src.database import SignalStatus, get_database
from src.mt5_client import mt5_client
from src.news_calendar import get_news_calendar
from src.scheduler import (
    create_scheduler,
    get_m15_trigger,
    get_tp_monitor_trigger,
    get_weekly_report_trigger,
)
from src.session_detector import get_session_detector
from src.spread_checker import get_spread_checker
from src.telegram_bot import get_trading_bot
from src.trade_executor import get_trade_executor
from src.trailing_stop_manager import get_trailing_manager
from src.reports import get_weekly_reporter

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.log_file),
    ],
)
logger = logging.getLogger(__name__)

# Thread pool for sync operations (MT5, Claude CLI)
executor = ThreadPoolExecutor(max_workers=2)


class TradingOrchestrator:
    """Main orchestrator for the trading system.

    Manages:
    - Component initialization and shutdown
    - Scheduled analysis jobs (M15)
    - TP monitoring jobs (30s)
    - Trade execution callbacks
    - Circuit breaker for failures
    """

    def __init__(self):
        self.scheduler = create_scheduler()
        self.running = False
        self._consecutive_failures = 0
        self._max_failures = 5
        self._tp_monitor_failures = 0
        self._max_tp_failures = 3

        # Component references (lazy loaded)
        self._db = None
        self._bot = None
        self._trade_executor = None
        self._trailing_manager = None
        self._session_detector = None
        self._spread_checker = None
        self._news_calendar = None
        self._weekly_reporter = None

    @property
    def db(self):
        """Lazy load database."""
        if self._db is None:
            self._db = get_database()
        return self._db

    @property
    def bot(self):
        """Lazy load Telegram bot."""
        if self._bot is None:
            self._bot = get_trading_bot()
        return self._bot

    @property
    def trade_executor(self):
        """Lazy load trade executor."""
        if self._trade_executor is None:
            self._trade_executor = get_trade_executor()
        return self._trade_executor

    @property
    def trailing_manager(self):
        """Lazy load trailing stop manager."""
        if self._trailing_manager is None:
            self._trailing_manager = get_trailing_manager()
        return self._trailing_manager

    @property
    def session_detector(self):
        """Lazy load session detector."""
        if self._session_detector is None:
            self._session_detector = get_session_detector()
        return self._session_detector

    @property
    def spread_checker(self):
        """Lazy load spread checker."""
        if self._spread_checker is None:
            self._spread_checker = get_spread_checker()
        return self._spread_checker

    @property
    def news_calendar(self):
        """Lazy load news calendar."""
        if self._news_calendar is None:
            self._news_calendar = get_news_calendar()
        return self._news_calendar

    @property
    def weekly_reporter(self):
        """Lazy load weekly reporter."""
        if self._weekly_reporter is None:
            self._weekly_reporter = get_weekly_reporter()
        return self._weekly_reporter

    async def initialize(self) -> bool:
        """Initialize all system components.

        Returns:
            True if initialization successful
        """
        logger.info("Initializing trading system...")

        config = get_settings()

        # Ensure directories exist
        config.csv_dir.mkdir(parents=True, exist_ok=True)
        config.logs_dir.mkdir(parents=True, exist_ok=True)
        config.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize MT5 (sync)
        loop = asyncio.get_event_loop()
        mt5_ok = await loop.run_in_executor(executor, mt5_client.initialize)
        if not mt5_ok:
            logger.error("Failed to initialize MT5")
            return False

        # Validate trading symbol
        symbol_ok = await loop.run_in_executor(
            executor, mt5_client.validate_symbol, config.mt5_symbol
        )
        if not symbol_ok:
            logger.error(f"Invalid symbol: {config.mt5_symbol}")
            return False

        # Initialize Telegram bot
        await self.bot.initialize()
        self.bot.set_execute_callback(self.on_execute)

        logger.info("All components initialized successfully")
        return True

    async def shutdown(self):
        """Graceful shutdown of all components."""
        logger.info("Shutting down trading system...")
        self.running = False

        # Stop scheduler
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        # Stop Telegram bot
        await self.bot.shutdown()

        # Shutdown MT5 (sync)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, mt5_client.shutdown)

        # Shutdown thread pool
        executor.shutdown(wait=True)

        logger.info("Shutdown complete")

    async def analysis_job(self):
        """Main analysis job - runs every M15.

        Flow:
        1. Check news blackout
        2. Check market open
        3. Check session quality
        4. Check spread
        5. Export CSV data
        6. Run Claude analysis
        7. Apply session modifier to confidence
        8. Check confidence threshold
        9. Send notification or skip
        """
        config = get_settings()
        symbol = config.mt5_symbol

        # Circuit breaker check
        if self._consecutive_failures >= self._max_failures:
            logger.error("Circuit breaker tripped - analysis paused")
            await self.bot.send_alert(
                "Circuit Breaker",
                f"Analysis paused after {self._max_failures} consecutive failures",
            )
            return

        logger.info("Starting M15 analysis...")
        loop = asyncio.get_event_loop()

        try:
            # 1. Check news blackout
            blackout = self.news_calendar.is_in_blackout()
            if blackout.in_blackout:
                logger.info(f"News blackout active: {blackout.message}")
                self.db.save_skipped_signal(
                    reason="news_blackout",
                    details=blackout.message,
                )
                return

            # 2. Check market open
            if not self.session_detector.is_market_open():
                logger.info("Market closed - skipping analysis")
                return

            # 3. Check MT5 connection
            connected = await loop.run_in_executor(
                executor, mt5_client.is_connected
            )
            if not connected:
                logger.warning("MT5 disconnected, reconnecting...")
                await loop.run_in_executor(executor, mt5_client.initialize)

            # 3. Get session info
            session_info = self.session_detector.get_current_session()
            logger.info(
                f"Session: {session_info.session.value} "
                f"(quality={session_info.quality}, modifier={session_info.modifier:+d})"
            )

            # 4. Check spread
            spread_result = self.spread_checker.check_spread(symbol)
            if not spread_result.spread_ok:
                logger.info(f"Spread too high: {spread_result.message}")
                self.db.save_skipped_signal(
                    reason="spread_high",
                    details=spread_result.message,
                    session=session_info.session.value,
                    spread_pips=spread_result.current_spread_pips,
                )
                return

            # 5. Export CSV files
            csv_files = await loop.run_in_executor(
                executor, mt5_client.export_csv, symbol
            )
            if not csv_files:
                logger.error("Failed to export CSV files")
                self._consecutive_failures += 1
                return

            # 6. Run Claude analysis
            signal = await loop.run_in_executor(
                executor, claude_client.analyze, csv_files
            )
            if signal is None:
                logger.error("Claude analysis returned None")
                self._consecutive_failures += 1
                return

            # 7. Apply session modifier to confidence
            original_conf = signal.signal.confidence
            adjusted_conf = self.session_detector.apply_session_modifier(
                original_conf, session_info
            )
            signal.signal.confidence = adjusted_conf
            logger.info(
                f"Confidence: {original_conf} {session_info.modifier:+d} = {adjusted_conf}"
            )

            # 8. Save signal to database
            signal_id = self.db.save_signal(signal)
            logger.info(f"Signal saved: id={signal_id}, action={signal.signal.action}")

            # 9. Check confidence threshold
            if adjusted_conf < config.confidence_threshold:
                logger.info(
                    f"Confidence {adjusted_conf}% below threshold {config.confidence_threshold}% - silent skip"
                )
                self.db.update_signal_status(signal_id, SignalStatus.SKIPPED)
                self.db.save_skipped_signal(
                    reason="low_confidence",
                    details=f"Confidence {adjusted_conf}% < {config.confidence_threshold}%",
                    session=session_info.session.value,
                    confidence=adjusted_conf,
                    signal_id=signal_id,
                )
                return

            # 10. Check if tradeable
            if not signal.is_tradeable:
                logger.info(f"No trade signal: {signal.signal.reason}")
                self.db.update_signal_status(signal_id, SignalStatus.SKIPPED)
                return

            # 11. Send notification with inline buttons
            self.bot.pending_signals_meta = {"signal_id": signal_id}
            await self.bot.send_signal(signal)

            # Reset failure counter on success
            self._consecutive_failures = 0

        except Exception as e:
            logger.exception(f"Analysis job failed: {e}")
            self._consecutive_failures += 1

    async def tp_monitor_job(self):
        """TP monitoring job - runs every 30 seconds.

        Checks open positions for:
        - TP level triggers (partial close)
        - Trailing stop updates
        - Position status sync with MT5
        """
        try:
            # Check trailing stops and TPs
            results = self.trailing_manager.check_all_positions()

            # Check for consecutive failures
            if self.trailing_manager.should_alert():
                self._tp_monitor_failures += 1
                if self._tp_monitor_failures >= self._max_tp_failures:
                    await self.bot.send_alert(
                        "TP Monitor Alert",
                        f"TP monitoring failed {self._max_tp_failures} consecutive times. "
                        "Manual intervention may be required.",
                    )
                    self.trailing_manager.reset_failures()
                    self._tp_monitor_failures = 0
            else:
                self._tp_monitor_failures = 0

            # Check TP levels for each open trade
            open_trades = self.db.get_open_trades()
            for trade in open_trades:
                tp_result = self.trailing_manager.check_tp_levels(trade["id"])
                if tp_result.get("actions"):
                    for action in tp_result["actions"]:
                        if action["status"] == "triggered":
                            await self.bot.send_message(
                                f"*{action['level']} Hit*\n"
                                f"Closed {action['volume_closed']} lots"
                            )

        except Exception as e:
            logger.error(f"TP monitor job failed: {e}")
            self._tp_monitor_failures += 1

    async def weekly_report_job(self):
        """Weekly report job - runs every Sunday at 23:00 UTC.

        Generates performance report and sends summary via Telegram.
        """
        try:
            logger.info("Generating weekly report...")
            report = self.weekly_reporter.generate_weekly_report()

            # Save to files (JSON + CSV)
            engine = get_analytics_engine()
            saved = engine.save_to_files()
            logger.info(f"Weekly report saved to: {list(saved.keys())}")

            # Extract key metrics for notification
            overall = report.get("overall_metrics", {})
            period = report.get("period", {})
            suggestions = report.get("suggestions", [])

            # Build summary message
            message = (
                f"*Weekly Performance Report*\n"
                f"Period: {period.get('start')} to {period.get('end')}\n\n"
                f"Trades: {overall.get('total_trades', 0)}\n"
                f"Win Rate: {overall.get('win_rate', 0)}%\n"
                f"Profit Factor: {overall.get('profit_factor', 0)}\n"
                f"Return: {overall.get('total_return_percent', 0)}%\n"
                f"Max DD: {overall.get('max_drawdown_percent', 0)}%\n"
                f"Sharpe: {overall.get('sharpe_ratio', 0)}"
            )

            if suggestions:
                message += "\n\n*Suggestions:*\n"
                for s in suggestions[:3]:  # Limit to 3 suggestions
                    message += f"• {s}\n"

            await self.bot.send_message(message)
            logger.info("Weekly report sent successfully")

        except Exception as e:
            logger.error(f"Weekly report job failed: {e}")

    async def on_execute(self, signal) -> bool:
        """Callback when user clicks Execute button.

        Args:
            signal: TradingSignal to execute

        Returns:
            True if execution successful
        """
        logger.info(f"Executing trade: {signal.signal.action}")

        try:
            result = await self.trade_executor.execute_signal(signal)

            if result.get("status") == "executed":
                logger.info(
                    f"Trade executed: ticket={result.get('ticket')}, "
                    f"volume={result.get('volume')}"
                )
                return True

            logger.warning(f"Trade execution result: {result}")
            return False

        except Exception as e:
            logger.exception(f"Trade execution failed: {e}")
            return False

    async def run(self):
        """Main run loop."""
        if not await self.initialize():
            logger.error("Initialization failed - exiting")
            return

        self.running = True
        config = get_settings()

        # Schedule M15 analysis job
        self.scheduler.add_job(
            self.analysis_job,
            get_m15_trigger(),
            id="m15_analysis",
            replace_existing=True,
        )

        # Schedule TP monitoring job (30s interval)
        self.scheduler.add_job(
            self.tp_monitor_job,
            get_tp_monitor_trigger(),
            id="tp_monitor",
            replace_existing=True,
        )

        # Schedule weekly report job (Sunday 23:00 UTC)
        self.scheduler.add_job(
            self.weekly_report_job,
            get_weekly_report_trigger(),
            id="weekly_report",
            replace_existing=True,
        )

        # Start scheduler
        self.scheduler.start()

        # Send startup notification
        mode = "PAPER" if config.paper_trading else "LIVE"
        await self.bot.send_message(
            f"*Trading Bot Started*\n\n"
            f"Mode: {mode}\n"
            f"Symbol: {config.mt5_symbol}\n"
            f"Risk: {config.risk_percent}%"
        )

        logger.info(f"Trading system started in {mode} mode")

        # Run initial analysis
        await self.analysis_job()

        # Keep running until shutdown
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

        await self.shutdown()


def main():
    """Application entry point."""
    orchestrator = TradingOrchestrator()

    # Handle SIGINT (Ctrl+C)
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        orchestrator.running = False

    signal.signal(signal.SIGINT, signal_handler)

    # Run main loop
    try:
        asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
