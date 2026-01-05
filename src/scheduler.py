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
    """Get cron trigger for M15 candle analysis.

    Triggers at :01, :16, :31, :46 of every hour (1 min after candle close).
    Delay allows broker to finalize candle data.

    Returns:
        CronTrigger for M15 schedule
    """
    return CronTrigger(minute="1,16,31,46")


def get_m30_trigger() -> CronTrigger:
    """Get cron trigger for M30 candle analysis.

    Triggers at :01, :31 of every hour (1 min after candle close).
    Delay allows broker to finalize candle data.

    Returns:
        CronTrigger for M30 schedule
    """
    return CronTrigger(minute="1,31")


def get_tp_monitor_trigger() -> IntervalTrigger:
    """Get interval trigger for TP monitoring.

    Triggers every 30 seconds for trailing stop updates.

    Returns:
        IntervalTrigger for 30-second intervals
    """
    return IntervalTrigger(seconds=30)


def get_weekly_report_trigger() -> CronTrigger:
    """Get cron trigger for weekly report generation.

    Triggers every Sunday at 23:00 UTC.

    Returns:
        CronTrigger for weekly schedule
    """
    return CronTrigger(day_of_week="sun", hour=23, minute=0)
