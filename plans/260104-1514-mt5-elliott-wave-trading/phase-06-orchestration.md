# Phase 6: Orchestration

## Context Links
- [Plan Overview](./plan.md)
- [Phase 5: Trade Execution](./phase-05-trade-execution.md)

## Overview
- **Priority**: P1
- **Status**: Done (2026-01-04)
- **Effort**: 5h (+2h for session/spread/confidence)
- **Description**: Main orchestrator with scheduler, session detection, spread checks, and async/sync bridge

## Key Insights
- APScheduler for M15 cron triggers
- asyncio event loop for Telegram
- run_in_executor for sync MT5/Claude CLI calls
- Graceful shutdown handling
- Circuit breaker for consecutive failures
- **TP Monitoring Job**: Separate 30s interval job for auto partial close
- **Session Detection**: UTC-based, apply confidence modifiers (+10 overlap, -15 Asian)
- **Spread Check**: Skip if spread > MAX_SPREAD_PIPS
- **Confidence Check**: Silent skip if < 60% (no trade, no notify, log only)

## Requirements

### Functional
- Schedule analysis every M15 close
- Coordinate MT5 → Claude CLI → Telegram flow
- Handle Execute callback from Telegram
- **TP monitoring every 30s for auto partial close**
- Graceful startup/shutdown
- Health monitoring
- **Session detection (UTC)**: Determine current session and apply confidence modifier
- **Spread check before analysis**: Get spread from MT5, skip if > MAX_SPREAD_PIPS
- **Confidence gate**: Silent skip if signal confidence < 60%
- **News blackout integration**: Check ForexFactory calendar before analysis

### Non-Functional
- Single process operation
- Async main loop
- Proper signal handling (SIGINT)

## Architecture

### Main Loop
```
main()
├── Initialize components
│   ├── MT5 connect
│   ├── Load instructions
│   ├── Telegram bot start
│   └── Scheduler start
│
├── Schedule M15 job
│   └── analysis_job()
│       ├── Export CSV (executor)
│       ├── Call Claude (executor)
│       ├── Parse signal
│       ├── Save to database
│       └── Send Telegram notification
│
├── Handle callbacks
│   └── on_execute(signal)
│       └── Place order (executor)
│
└── Wait for shutdown
```

## Related Code Files

### Files to Create
- `src/scheduler.py` - APScheduler setup
- `src/main.py` - Entry point

## Implementation Steps

1. **Create src/scheduler.py**

```python
"""APScheduler configuration"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure scheduler"""
    scheduler = AsyncIOScheduler()

    # Configure defaults
    scheduler.configure(
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }
    )

    return scheduler


def get_m15_trigger() -> CronTrigger:
    """Get cron trigger for M15 candle closes"""
    # Trigger at :00, :15, :30, :45
    return CronTrigger(minute="0,15,30,45")


def get_m30_trigger() -> CronTrigger:
    """Get cron trigger for M30 (reduced frequency)"""
    return CronTrigger(minute="0,30")


def get_tp_monitor_interval():
    """Get interval trigger for TP monitoring (every 30s)"""
    from apscheduler.triggers.interval import IntervalTrigger
    return IntervalTrigger(seconds=30)
```

2. **Create src/main.py**

```python
"""Main entry point and orchestrator"""
import asyncio
import signal
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.config import config
from src.mt5_client import mt5_client
from src.claude_client import claude_client
from src.telegram_bot import trading_bot
from src.database import database
from src.scheduler import create_scheduler, get_m15_trigger

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.logs_dir / "trading.log"),
    ],
)
logger = logging.getLogger(__name__)

# Thread pool for sync operations
executor = ThreadPoolExecutor(max_workers=2)


class TradingOrchestrator:
    def __init__(self):
        self.scheduler = create_scheduler()
        self.running = False
        self._consecutive_failures = 0
        self._max_failures = 5

    async def initialize(self) -> bool:
        """Initialize all components"""
        logger.info("Initializing trading system...")

        # Ensure directories exist
        config.csv_dir.mkdir(parents=True, exist_ok=True)
        config.logs_dir.mkdir(parents=True, exist_ok=True)

        # Initialize MT5
        loop = asyncio.get_event_loop()
        mt5_ok = await loop.run_in_executor(executor, mt5_client.initialize)
        if not mt5_ok:
            logger.error("Failed to initialize MT5")
            return False

        # Validate symbol
        symbol_ok = await loop.run_in_executor(
            executor, mt5_client.validate_symbol, config.mt5_symbol
        )
        if not symbol_ok:
            logger.error(f"Symbol {config.mt5_symbol} not valid")
            return False

        # Initialize Telegram bot
        await trading_bot.initialize()
        trading_bot.set_execute_callback(self.on_execute)

        logger.info("All components initialized")
        return True

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down...")
        self.running = False

        self.scheduler.shutdown(wait=False)
        await trading_bot.shutdown()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, mt5_client.shutdown)

        executor.shutdown(wait=True)
        logger.info("Shutdown complete")

    async def analysis_job(self):
        """Main analysis job - called every M15"""
        if self._consecutive_failures >= self._max_failures:
            logger.error("Circuit breaker tripped - pausing analysis")
            await trading_bot.send_message("🚨 *Circuit Breaker*\nToo many failures, pausing analysis")
            return

        logger.info("Starting M15 analysis...")
        loop = asyncio.get_event_loop()

        try:
            # 1. Check MT5 connection
            if not await loop.run_in_executor(executor, mt5_client.is_connected):
                logger.warning("MT5 disconnected, reconnecting...")
                await loop.run_in_executor(executor, mt5_client.initialize)

            # 2. Export CSV files
            csv_files = await loop.run_in_executor(
                executor, mt5_client.export_csv, config.mt5_symbol
            )

            if not csv_files:
                logger.error("Failed to export CSV files")
                self._consecutive_failures += 1
                return

            # 3. Call Claude for analysis
            signal = await loop.run_in_executor(
                executor, claude_client.analyze, csv_files
            )

            if signal is None:
                logger.error("Failed to get signal from Claude")
                self._consecutive_failures += 1
                return

            # 4. Save signal to database
            signal_id = database.save_signal(signal)
            logger.info(f"Signal saved: id={signal_id}, action={signal.signal.action}")

            # 5. Check confidence threshold
            if signal.signal.confidence < config.confidence_threshold:
                logger.info(f"Signal below threshold ({signal.signal.confidence}% < {config.confidence_threshold}%)")
                database.update_signal_status(signal_id, "low_confidence")
                return

            # 6. Send Telegram notification
            if signal.signal.action != "NO_TRADE":
                # Store signal_id for callback
                trading_bot.pending_signals_meta = {
                    "signal_id": signal_id,
                }
                await trading_bot.send_signal(signal)
            else:
                database.update_signal_status(signal_id, "no_trade")

            self._consecutive_failures = 0  # Reset on success

        except Exception as e:
            logger.exception(f"Analysis job failed: {e}")
            self._consecutive_failures += 1

    async def tp_monitor_job(self):
        """Monitor open positions for TP levels - every 30s"""
        loop = asyncio.get_event_loop()
        
        try:
            # Get open trades from database
            open_trades = database.get_open_trades()
            if not open_trades:
                return
                
            for trade in open_trades:
                # Get current price
                positions = await loop.run_in_executor(
                    executor, mt5_client.get_positions
                )
                
                pos = next((p for p in positions if p["ticket"] == trade["ticket"]), None)
                if not pos:
                    # Position closed externally
                    database.update_trade_status(trade["id"], "closed")
                    continue
                    
                current_price = pos["current_price"]
                is_buy = trade["action"] == "BUY"
                
                # Get untriggered TP levels
                tp_levels = database.get_tp_levels(trade["id"])
                
                for tp in tp_levels:
                    if tp["triggered"]:
                        continue
                        
                    # Check if TP hit
                    tp_hit = (is_buy and current_price >= tp["price"]) or                              (not is_buy and current_price <= tp["price"])
                    
                    if tp_hit:
                        # Calculate volume to close
                        close_volume = pos["volume"] * (tp["close_percent"] / 100)
                        close_volume = round(close_volume, 2)
                        
                        # Partial close
                        success = await loop.run_in_executor(
                            executor,
                            mt5_client.close_partial,
                            trade["ticket"],
                            close_volume
                        )
                        
                        if success:
                            database.mark_tp_triggered(tp["id"])
                            logger.info(f"TP {tp['level']} hit: closed {close_volume} lots")
                            await trading_bot.send_message(
                                f"✅ *{tp['level']} Hit*
Closed {close_volume} lots at {current_price}"
                            )
                            
        except Exception as e:
            logger.exception(f"TP monitor failed: {e}")

    async def on_execute(self, signal) -> bool:
        """Callback when user clicks Execute"""
        logger.info(f"Executing trade: {signal.signal.action}")
        loop = asyncio.get_event_loop()

        try:
            # Calculate position size
            volume = await loop.run_in_executor(
                executor,
                mt5_client.calculate_position_size,
                signal.symbol,
                signal.signal.entry_price,
                signal.signal.stop_loss,
            )

            # Use first TP for initial order
            tp1 = signal.signal.take_profit[0].price if signal.signal.take_profit else None

            # Place order
            ticket = await loop.run_in_executor(
                executor,
                mt5_client.place_market_order,
                signal.symbol,
                signal.signal.action,
                volume,
                signal.signal.stop_loss,
                tp1,
            )

            if ticket:
                # Save trade to database
                signal_id = getattr(trading_bot, "pending_signals_meta", {}).get("signal_id")
                if signal_id:
                    database.save_trade(signal_id, ticket, volume, signal)
                    database.update_signal_status(signal_id, "executed")

                return True

            return False

        except Exception as e:
            logger.exception(f"Trade execution failed: {e}")
            return False

    async def run(self):
        """Main run loop"""
        if not await self.initialize():
            logger.error("Initialization failed")
            return

        self.running = True

        # Add scheduled jobs
        self.scheduler.add_job(
            self.analysis_job,
            get_m15_trigger(),
            id="m15_analysis",
            replace_existing=True,
        )
        
        # Add TP monitoring job (every 30s)
        from src.scheduler import get_tp_monitor_interval
        self.scheduler.add_job(
            self.tp_monitor_job,
            get_tp_monitor_interval(),
            id="tp_monitor",
            replace_existing=True,
        )
        
        self.scheduler.start()

        logger.info("Trading system started")
        mode = "PAPER" if config.paper_trading else "LIVE"
        await trading_bot.send_message(f"🚀 *Trading Bot Started*\nMode: {mode}")

        # Run initial analysis
        await self.analysis_job()

        # Keep running
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

        await self.shutdown()


def main():
    """Entry point"""
    orchestrator = TradingOrchestrator()

    # Handle SIGINT
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        orchestrator.running = False

    signal.signal(signal.SIGINT, signal_handler)

    # Run
    try:
        asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
```

3. **Update src/__init__.py**

```python
"""Elliott Wave Auto-Trading System"""
__version__ = "0.1.0"
```

## Todo List

- [x] Create src/scheduler.py with M15 and 30s interval triggers
- [x] Create src/main.py with orchestrator
- [x] Implement analysis_job flow
- [x] Implement on_execute callback
- [x] **Implement tp_monitor_job for auto partial close**
- [x] Add circuit breaker
- [x] Add graceful shutdown
- [x] Test full flow end-to-end
- [x] **Create SessionDetector class** (get_current_session, get_confidence_modifier)
- [x] **Create SpreadChecker class** (get_current_spread, is_spread_ok)
- [x] **Add session check to analysis_job flow**
- [x] **Add spread check to analysis_job flow**
- [x] **Implement silent skip for confidence < 60%**
- [x] **Add logging for skipped signals (session, spread, confidence)**
- [x] **Create skipped_signals table in database**
- [x] **Integrate with Phase 6.5 news_blackout_check**

## Success Criteria

- [ ] M15 job triggers correctly
- [ ] Full flow: MT5 → Claude → Telegram works
- [ ] Execute callback places order
- [ ] Graceful shutdown on Ctrl+C
- [ ] Circuit breaker stops on failures

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Deadlock in executor | Low | High | Timeout on calls |
| Missed M15 trigger | Low | Low | misfire_grace_time |
| Runaway failures | Medium | Medium | Circuit breaker |

## Security Considerations

- All credentials from env
- Paper trading default
- Logging excludes secrets

## Next Steps

→ [Phase 7: Testing & Paper Trading](./phase-07-testing.md)
