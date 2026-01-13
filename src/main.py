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
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from src.claude_client import claude_client
from src.config import get_settings
from src.database import SignalStatus, get_database
from src.market_regime import get_regime_detector
from src.mt5_client import mt5_client
from src.news_calendar import get_news_calendar
from src.signal_parser import TradingSignal
from src.scheduler import (
    create_scheduler,
    get_event_prune_trigger,
    get_m15_trigger,
    get_observer_trigger,
    get_tp_monitor_trigger,
    get_weekly_report_trigger,
)
from src.session_detector import get_session_detector
from src.spread_checker import get_spread_checker
from src.telegram_bot import get_trading_bot
from src.trade_executor import get_trade_executor
from src.trailing_stop_manager import get_trailing_manager
from src.reports import get_weekly_reporter
from src.volatility_manager import get_volatility_manager
from src.observers.market_observer import get_market_observer
from src.observers.base_observer import ObserverEvent
from src.observers.event_aggregator import AggregatedEvent

# Configure logging with UTF-8 support for emoji handling on Windows
settings = get_settings()
_log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Create handlers with proper encoding for Windows compatibility
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(logging.Formatter(_log_format))
_stream_handler.stream = open(1, "w", encoding="utf-8", errors="replace", closefd=False)

_file_handler = logging.FileHandler(settings.log_file, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(_log_format))

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format=_log_format,
    handlers=[_stream_handler, _file_handler],
)
logger = logging.getLogger(__name__)

# Thread pool for sync operations (MT5, Claude CLI)
executor = ThreadPoolExecutor(max_workers=2)


@dataclass
class ObserverState:
    """In-memory observer state for event-driven analysis triggers.

    Tracks volatility spike detection, key level proximity, and cooldowns.
    Not persisted to DB - resets on restart.
    """

    last_triggered_analysis: float = 0.0  # timestamp of last triggered analysis
    in_spike: bool = False  # currently in volatility spike
    spike_start_time: float = 0.0  # when spike was first detected
    atr_baseline_m30: float = 10.0  # cached M30 ATR baseline (Gold typical)
    key_levels: List[float] = field(default_factory=list)  # cached key levels
    last_baseline_update: float = 0.0  # last ATR baseline update timestamp
    last_key_level_update: float = 0.0  # last key level update timestamp


class TradingOrchestrator:
    """Main orchestrator for the trading system.

    Manages:
    - Component initialization and shutdown
    - Scheduled analysis jobs (M15)
    - TP monitoring jobs (30s)
    - Trade execution callbacks
    - Circuit breaker for failures
    - Auto-trade execution for high-confidence signals
    """

    def __init__(self):
        self.scheduler = create_scheduler()
        self.running = False
        self._consecutive_failures = 0
        self._max_failures = 5
        self._tp_monitor_failures = 0
        self._max_tp_failures = 3
        self._daily_auto_trades = 0
        self._last_trade_date = None

        # Component references (lazy loaded)
        self._db = None
        self._bot = None
        self._trade_executor = None
        self._trailing_manager = None
        self._session_detector = None
        self._spread_checker = None
        self._news_calendar = None
        self._weekly_reporter = None
        self._regime_detector = None
        self._volatility_manager = None
        self._market_observer = None

        # Observer state (in-memory only, not persisted)
        self._observer_state = ObserverState()

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
    
    @property
    def regime_detector(self):
        """Lazy load regime detector."""
        if self._regime_detector is None:
            self._regime_detector = get_regime_detector()
        return self._regime_detector
    
    @property
    def volatility_manager(self):
        """Lazy load volatility manager."""
        if self._volatility_manager is None:
            self._volatility_manager = get_volatility_manager()
        return self._volatility_manager

    @property
    def market_observer(self):
        """Lazy load market observer with event subscription."""
        if self._market_observer is None:
            self._market_observer = get_market_observer()
            # Subscribe to raw events - triggers analysis when observer detects conditions
            self._market_observer.subscribe(self._on_observer_event)
            # Subscribe to aggregated events (Phase 02 - Observer Enhancements)
            self._market_observer.subscribe_aggregated(self._on_aggregated_event)
        return self._market_observer

    def _on_observer_event(self, event: ObserverEvent):
        """Handle observer events synchronously - logs event for async trigger.

        Actual analysis is triggered in observer_job to avoid blocking.
        This callback runs in the same thread as observer_job, so it must be fast.

        Args:
            event: ObserverEvent from observer check
        """
        try:
            logger.info(
                f"Observer event received: {event.event_type.value} "
                f"(confidence={event.confidence:.2f})"
            )

            # Store event metadata for potential use by analysis_job
            self._observer_state.last_triggered_analysis = time.time()

        except Exception as e:
            # Log but don't propagate - observer system should be resilient
            logger.warning(f"Observer event handler error (non-blocking): {e}")

    def _on_aggregated_event(self, agg_event: AggregatedEvent):
        """Handle aggregated observer events (Phase 02 - Observer Enhancements).

        Called when aggregation window closes with correlated events.
        Strong signals (confidence >= 0.75, count >= 2) may trigger priority analysis.

        Args:
            agg_event: AggregatedEvent from EventAggregator
        """
        try:
            logger.info(
                f"Aggregated event received: {agg_event.count} events, "
                f"types={agg_event.unique_event_types}, "
                f"correlation={agg_event.correlation_type}, "
                f"confidence={agg_event.confidence:.2f}"
            )

            if agg_event.is_strong_signal:
                logger.info(
                    f"Strong aggregated signal detected: "
                    f"{agg_event.count} correlated events, confidence={agg_event.confidence:.2f}"
                )
                # Could trigger priority analysis here in future enhancements
                # For now, logging for monitoring/debugging

        except Exception as e:
            # Log but don't propagate - aggregation system should be resilient
            logger.warning(f"Aggregated event handler error (non-blocking): {e}")

    def _reset_daily_counter_if_needed(self):
        """Reset daily auto-trade counter at midnight."""
        from datetime import date
        today = date.today()
        if self._last_trade_date != today:
            self._daily_auto_trades = 0
            self._last_trade_date = today
            logger.debug("Daily auto-trade counter reset")

    def _can_auto_trade(self, confidence: int) -> tuple[bool, str]:
        """Check if auto-trading conditions are met.

        Args:
            confidence: Signal confidence percentage

        Returns:
            Tuple of (can_trade, reason)
        """
        config = get_settings()

        if not config.auto_trade_enabled:
            return False, "auto_trade_disabled"

        self._reset_daily_counter_if_needed()

        if self._daily_auto_trades >= config.auto_trade_max_daily:
            return False, f"daily_limit_reached ({config.auto_trade_max_daily})"

        if confidence < config.auto_trade_confidence:
            return False, f"confidence_below_threshold ({confidence}% < {config.auto_trade_confidence}%)"

        return True, "conditions_met"

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

        # Set database reference on claude_client for signal context
        claude_client.set_database(self.db)

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

            # 5a. Detect market regime
            try:
                # Load CSV data for regime detection
                import pandas as pd
                h4_data = pd.read_csv(csv_files['H4'])
                h1_data = pd.read_csv(csv_files['H1'])
                m30_data = pd.read_csv(csv_files['M30']) if 'M30' in csv_files else None
                
                # Detect regime
                regime = self.regime_detector.detect_regime(h4_data, h1_data)
                logger.info(
                    f"Market regime: {regime.regime_type.value} "
                    f"(confidence: {regime.confidence}%, volatility: {regime.volatility_state})"
                )
                
                # Save regime to market memory
                self.db.save_market_memory(
                    memory_type="market_regime",
                    key="current_regime",
                    value=regime.regime_type.value,
                    confidence=regime.confidence,
                    expires_hours=4  # Regime valid for 4 hours
                )
            except Exception as e:
                logger.warning(f"Regime detection failed: {e}")
                regime = None
            
            # 5b. Analyze volatility
            volatility_profile = None
            try:
                if m30_data is not None:
                    volatility_profile = self.volatility_manager.analyze_volatility(
                        h4_data, h1_data, m30_data
                    )
                    logger.info(
                        f"Volatility: {volatility_profile.state.value} "
                        f"(percentile: {volatility_profile.atr_percentile}%, "
                        f"trend: {volatility_profile.volatility_trend})"
                    )
                    
                    # Log volatility dashboard
                    dashboard = self.volatility_manager.get_volatility_dashboard(volatility_profile)
                    logger.debug(dashboard)
                    
                    # Check entry filter
                    if volatility_profile.entry_filter == "avoid":
                        logger.warning("Volatility too extreme - avoiding new entries")
                        self.db.save_skipped_signal(
                            reason="extreme_volatility",
                            details=volatility_profile.description,
                            session=session_info.session.value,
                        )
                        return
                    
                    # Save volatility state to memory
                    self.db.save_market_memory(
                        memory_type="volatility",
                        key="current_state", 
                        value=f"{volatility_profile.state.value} ({volatility_profile.volatility_trend})",
                        confidence=volatility_profile.atr_percentile,
                        expires_hours=2  # Volatility memory expires faster
                    )
                        
            except Exception as e:
                logger.warning(f"Volatility analysis failed: {e}")

            # 6. Run Claude analysis
            # Prepare regime dict for Claude if available
            regime_dict = None
            if regime:
                regime_dict = {
                    'regime_type': regime.regime_type.value,
                    'confidence': regime.confidence,
                    'trend_strength': regime.trend_strength,
                    'volatility_state': regime.volatility_state,
                    'volatility_percentile': regime.volatility_percentile,
                    'direction_bias': regime.direction_bias,
                    'description': regime.description
                }
            
            # Prepare volatility dict for Claude if available
            volatility_dict = None
            if volatility_profile:
                volatility_dict = {
                    'state': volatility_profile.state.value,
                    'atr_percentile': volatility_profile.atr_percentile,
                    'trend': volatility_profile.volatility_trend,
                    'entry_filter': volatility_profile.entry_filter,
                    'expansion': volatility_profile.expansion_signal
                }
            
            signal = await loop.run_in_executor(
                executor, claude_client.analyze, csv_files, regime_dict, volatility_dict
            )
            if signal is None:
                logger.error("Claude analysis returned None")
                self._consecutive_failures += 1
                return

            # 7. Apply session modifier to confidence
            original_conf = signal.signal.confidence
            session_adjusted = self.session_detector.apply_session_modifier(
                original_conf, session_info
            )
            
            # 7a. Apply regime modifier to confidence
            if regime:
                regime_adjusted = session_adjusted + regime.confidence_modifier
                regime_adjusted = max(min(regime_adjusted, 100), 0)
                
                # 7b. Apply volatility modifier
                if volatility_profile:
                    final_adjusted = regime_adjusted + volatility_profile.confidence_impact
                    final_adjusted = max(min(final_adjusted, 100), 0)
                    logger.info(
                        f"Confidence adjustments: {original_conf} "
                        f"{session_info.modifier:+d} (session) "
                        f"{regime.confidence_modifier:+d} (regime) "
                        f"{volatility_profile.confidence_impact:+d} (volatility) "
                        f"= {final_adjusted}"
                    )
                    signal.signal.confidence = final_adjusted
                    adjusted_conf = final_adjusted
                else:
                    logger.info(
                        f"Confidence adjustments: {original_conf} "
                        f"{session_info.modifier:+d} (session) "
                        f"{regime.confidence_modifier:+d} (regime) "
                        f"= {regime_adjusted}"
                    )
                    signal.signal.confidence = regime_adjusted
                    adjusted_conf = regime_adjusted
            else:
                # No regime data, but check volatility
                if volatility_profile:
                    vol_adjusted = session_adjusted + volatility_profile.confidence_impact
                    vol_adjusted = max(min(vol_adjusted, 100), 0)
                    logger.info(
                        f"Confidence adjustments: {original_conf} "
                        f"{session_info.modifier:+d} (session) "
                        f"{volatility_profile.confidence_impact:+d} (volatility) "
                        f"= {vol_adjusted}"
                    )
                    signal.signal.confidence = vol_adjusted
                    adjusted_conf = vol_adjusted
                else:
                    signal.signal.confidence = session_adjusted
                    adjusted_conf = session_adjusted
                    logger.info(
                        f"Confidence: {original_conf} {session_info.modifier:+d} = {adjusted_conf}"
                    )

            # 8. Save signal to database
            signal_id = self.db.save_signal(signal)
            logger.info(f"Signal saved: id={signal_id}, action={signal.signal.action}")

            # 8a. Save market memories from signal
            self._save_signal_memories(signal, adjusted_conf)

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

            # 11. Check auto-trade conditions
            can_auto, auto_reason = self._can_auto_trade(adjusted_conf)

            if can_auto:
                # Auto-execute trade
                logger.info(f"Auto-executing trade: confidence={adjusted_conf}%")
                result = await self.trade_executor.execute_signal(signal)

                if result.get("status") == "executed":
                    self._daily_auto_trades += 1
                    await self.bot.send_message(
                        f"*AUTO-TRADE Executed*\n\n"
                        f"Action: {signal.signal.action.value}\n"
                        f"Confidence: {adjusted_conf}%\n"
                        f"Volume: {result.get('volume')} lots\n"
                        f"Entry: {result.get('entry_price')}\n"
                        f"SL: {result.get('stop_loss')}\n"
                        f"TP1: {result.get('take_profit')}\n"
                        f"Daily trades: {self._daily_auto_trades}/{config.auto_trade_max_daily}"
                    )
                    logger.info(f"Auto-trade executed: ticket={result.get('ticket')}")
                else:
                    await self.bot.send_message(
                        f"*AUTO-TRADE Failed*\n\n"
                        f"Reason: {result.get('reason', 'unknown')}\n"
                        f"Signal sent for manual review."
                    )
                    # Fall back to manual - send notification
                    self.bot.pending_signals_meta = {"signal_id": signal_id}
                    await self.bot.send_signal(signal)
            else:
                # Manual mode - send notification with inline buttons
                logger.info(f"Manual mode: {auto_reason}")
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
        - Observer conditions (volatility spike, key level proximity)
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

            # Observer checks - non-blocking, triggers analysis on market events
            await self._check_observer_conditions()

        except Exception as e:
            logger.error(f"TP monitor job failed: {e}")
            self._tp_monitor_failures += 1

    async def observer_job(self):
        """Market observer job - runs every 10 seconds.

        Dedicated observer check with lower latency than tp_monitor.
        Updates baselines, checks all observers, triggers analysis on events.
        """
        config = get_settings()

        if not config.observer_enabled:
            return

        if not self.session_detector.is_market_open():
            return

        try:
            loop = asyncio.get_event_loop()

            # Gather market data
            current_price = await loop.run_in_executor(
                executor, self._get_current_price
            )
            if current_price is None:
                return

            # Update baseline cache if stale
            volatility_obs = self.market_observer.get_observer("volatility_spike")
            if volatility_obs and volatility_obs.needs_baseline_update():
                await self._update_observer_baseline()

            # Get last 2 candles for compression observer (high/low/prev_close)
            candles = await loop.run_in_executor(
                executor,
                mt5_client.get_last_candles,
                config.mt5_symbol,
                "M15",
                2,
            )

            # Prepare market data for observers
            market_data = {
                "current_price": current_price,
                "atr_current": self._observer_state.atr_baseline_m30,
            }

            # Add OHLC data for compression observer if available
            if candles and len(candles) >= 2:
                latest = candles[-1]
                prev = candles[-2]
                market_data.update({
                    "close": latest["close"],
                    "high": latest["high"],
                    "low": latest["low"],
                    "prev_close": prev["close"],
                })

            # Check all observers - events handled via subscription callback
            events = self.market_observer.check_all(market_data)

            # If any events triggered and cooldown passed, run analysis
            if events:
                now = time.time()
                cooldown_remaining = (
                    config.observer_cooldown_seconds
                    - (now - self._observer_state.last_triggered_analysis)
                )
                if cooldown_remaining <= 0:
                    trigger_reasons = [e.event_type.value for e in events]
                    logger.info(f"Observer triggered analysis: {trigger_reasons}")
                    self._observer_state.last_triggered_analysis = now
                    await self.analysis_job()

        except Exception as e:
            # Observer errors should never block main operation
            logger.debug(f"Observer job failed (non-blocking): {e}")

    async def event_prune_job(self):
        """Prune old observer events - runs daily at 03:00 UTC.

        Removes events older than observer_persistence_max_age_days.
        """
        config = get_settings()

        if not config.observer_persistence_enabled:
            return

        try:
            from src.observers.event_persistence import get_event_store

            store = get_event_store()
            deleted = store.prune_old_events(
                max_age_days=config.observer_persistence_max_age_days
            )

            if deleted > 0:
                logger.info(f"Event prune job: removed {deleted} old events")

        except Exception as e:
            logger.error(f"Event prune job failed: {e}")

    async def weekly_report_job(self):
        """Weekly report job - runs every Sunday at 23:00 UTC.

        Generates performance report and sends summary via Telegram.
        """
        try:
            logger.info("Generating weekly report...")
            
            # Use new performance analytics
            from src.performance_analytics import get_performance_analytics
            analytics = get_performance_analytics()
            
            # Generate comprehensive report
            report = analytics.generate_performance_report()
            
            # Save report to file
            from pathlib import Path
            import json
            reports_dir = Path("data/reports")
            reports_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
            report_path = reports_dir / f"weekly_report_{timestamp}.json"
            
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            logger.info(f"Weekly report saved to: {report_path}")
            
            # Extract key metrics for notification
            metrics = report.get('overall_metrics', {})
            insights = report.get('optimization_insights', {})
            
            # Build summary message
            message = [
                "*📊 Weekly Performance Report*\n",
                f"📈 *Results*",
                f"Trades: {metrics.get('total_trades', 0)}",
                f"Win Rate: {metrics.get('win_rate', 0):.1f}%",
                f"Profit Factor: {metrics.get('profit_factor', 0):.2f}",
                f"Total P&L: ${metrics.get('total_pnl', 0):.2f}",
                f"Max DD: {metrics.get('max_drawdown_percent', 0):.1f}%",
                f"Sharpe: {metrics.get('sharpe_ratio', 0):.2f}"
            ]
            
            # Add top performing pattern
            patterns = report.get('pattern_performance', [])
            if patterns:
                best_pattern = patterns[0]
                message.extend([
                    "",
                    f"🌊 *Best Pattern*",
                    f"{best_pattern['pattern']}: {best_pattern['win_rate']:.0f}% win rate"
                ])
            
            # Add recommendations
            if insights.get('recommendations'):
                message.extend(["", "*💡 Insights*"])
                for rec in insights['recommendations'][:2]:
                    message.append(f"• {rec}")
            
            await self.bot.send_message("\n".join(message))
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

    def _save_signal_memories(self, signal: TradingSignal, confidence: int):
        """Save important signal data to market memory.
        
        Args:
            signal: Trading signal with wave analysis
            confidence: Adjusted confidence score
        """
        try:
            # Save wave position if available
            if signal.wave_analysis and signal.wave_analysis.wave_position:
                self.db.save_market_memory(
                    memory_type="wave_count",
                    key="current_wave",
                    value=signal.wave_analysis.wave_position,
                    confidence=confidence,
                    expires_hours=24  # Wave counts valid for 24 hours
                )
            
            # Save identified pattern
            if signal.signal.action != "NO_TRADE":
                pattern_desc = f"{signal.signal.action} signal at {signal.signal.entry_price}"
                self.db.save_market_memory(
                    memory_type="pattern",
                    key=f"signal_{signal.signal.action}",
                    value=pattern_desc,
                    confidence=confidence,
                    expires_hours=12  # Patterns valid for 12 hours
                )
            
            # Save key levels from signal
            if signal.signal.stop_loss:
                self.db.save_market_memory(
                    memory_type="key_level",
                    key="recent_sl",
                    value=str(signal.signal.stop_loss),
                    confidence=90,  # Stop levels are important
                    expires_hours=48
                )
                
            logger.debug("Signal memories saved to database")
            
        except Exception as e:
            logger.warning(f"Failed to save signal memories: {e}")

    def _can_auto_trade(self, confidence: int) -> tuple[bool, str]:
        """Check if signal should be auto-traded.
        
        Args:
            confidence: Signal confidence level
            
        Returns:
            Tuple of (can_auto_trade, reason)
        """
        config = get_settings()
        
        # Check if auto-trading is enabled
        if not config.auto_trade_enabled:
            return False, "Auto-trading disabled"
            
        # Check confidence threshold
        if confidence < config.auto_trade_confidence:
            return False, f"Confidence {confidence}% below auto-trade threshold {config.auto_trade_confidence}%"
            
        # Check daily limit
        today = datetime.now(timezone.utc).date()
        if self._last_trade_date != today:
            self._daily_auto_trades = 0
            self._last_trade_date = today
            
        if self._daily_auto_trades >= config.auto_trade_max_daily:
            return False, f"Daily auto-trade limit reached ({config.auto_trade_max_daily})"
            
        # Check drawdown state
        drawdown_state = self.db.get_latest_drawdown_state()
        if drawdown_state and drawdown_state.get('trading_paused'):
            return False, "Trading paused due to drawdown"
            
        return True, "All conditions met"

    # ===== Observer Methods (Event-Driven Market Analysis) =====

    def _get_current_price(self) -> Optional[float]:
        """Get current bid price from MT5 (sync).

        Returns:
            Current bid price or None if unavailable
        """
        tick = mt5_client.get_tick(get_settings().mt5_symbol)
        return tick.get("bid") if tick else None

    async def _update_observer_baseline(self):
        """Update cached ATR baseline for spike detection.

        Called hourly to refresh baseline without excessive API calls.
        Uses M30 ATR average of last 20 candles as baseline.
        """
        config = get_settings()
        loop = asyncio.get_event_loop()

        try:
            # Export minimal CSV for ATR calculation
            csv_files = await loop.run_in_executor(
                executor, mt5_client.export_csv, config.mt5_symbol
            )

            if csv_files and "M30" in csv_files:
                import pandas as pd

                m30_data = pd.read_csv(csv_files["M30"])

                if "atr_14" in m30_data.columns and len(m30_data) >= 20:
                    # Use last 20 candles for baseline
                    atr_values = m30_data["atr_14"].tail(20)
                    self._observer_state.atr_baseline_m30 = atr_values.mean()
                    self._observer_state.last_baseline_update = time.time()

                    logger.debug(
                        f"Observer baseline updated: ATR={self._observer_state.atr_baseline_m30:.2f}"
                    )

            # Update key levels from database
            await self._update_key_levels()

        except Exception as e:
            logger.debug(f"Observer baseline update failed: {e}")

    async def _update_key_levels(self):
        """Update cached key levels from market_memory table.

        Extracts recent stop loss levels and any custom key levels
        stored in the database.
        """
        try:
            memories = self.db.get_market_memory(memory_type="key_level")

            # Extract price values
            levels = []
            for mem in memories:
                try:
                    level = float(mem.get("memory_value", 0))
                    if level > 0:
                        levels.append(level)
                except (ValueError, TypeError):
                    pass

            self._observer_state.key_levels = levels
            self._observer_state.last_key_level_update = time.time()

            logger.debug(f"Observer key levels updated: {len(levels)} levels")

        except Exception as e:
            logger.debug(f"Key level update failed: {e}")

    async def _check_observer_conditions(self):
        """Legacy Phase 1 observer check - now delegated to Phase 2 observer_job.

        Called every 30s from tp_monitor_job. Phase 2 observer_job runs every 10s
        and provides full observer system functionality.

        Note: This method is kept for backward compatibility but does minimal work.
        The dedicated observer_job (10s) handles all observer checks.
        """
        # Phase 2 observer_job handles all observer checks
        # This legacy method only logs if observer system detected something
        # to maintain backward compatibility with tp_monitor_job
        pass

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

        # Schedule market observer job (10s interval) - Phase 2 full observer system
        if config.observer_enabled:
            self.scheduler.add_job(
                self.observer_job,
                get_observer_trigger(),
                id="market_observer",
                replace_existing=True,
            )
            logger.info("Market observer job scheduled (10s interval)")

        # Schedule event prune job (daily 03:00 UTC) - Phase 04 Observer Enhancements
        if config.observer_persistence_enabled:
            self.scheduler.add_job(
                self.event_prune_job,
                get_event_prune_trigger(),
                id="event_prune",
                replace_existing=True,
            )
            logger.info("Event prune job scheduled (daily 03:00 UTC)")

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
