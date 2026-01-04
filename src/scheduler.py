"""APScheduler configuration for trading system.

Provides:
- M15 cron trigger for analysis jobs
- 30-second interval trigger for TP monitoring
- M30 trigger for reduced frequency option
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure async scheduler.

    Returns:
        Configured AsyncIOScheduler instance
    """
    scheduler = AsyncIOScheduler()

    scheduler.configure(
        job_defaults={
            "coalesce": True,  # Combine missed runs
            "max_instances": 1,  # Only one instance per job
            "misfire_grace_time": 60,  # 60s grace period
        }
    )

    return scheduler


def get_m15_trigger() -> CronTrigger:
    """Get cron trigger for M15 candle closes.

    Triggers at :00, :15, :30, :45 of every hour.

    Returns:
        CronTrigger for M15 schedule
    """
    return CronTrigger(minute="0,15,30,45")


def get_m30_trigger() -> CronTrigger:
    """Get cron trigger for M30 candle closes.

    Triggers at :00, :30 of every hour.

    Returns:
        CronTrigger for M30 schedule
    """
    return CronTrigger(minute="0,30")


def get_tp_monitor_trigger() -> IntervalTrigger:
    """Get interval trigger for TP monitoring.

    Triggers every 30 seconds for trailing stop updates.

    Returns:
        IntervalTrigger for 30-second intervals
    """
    return IntervalTrigger(seconds=30)
