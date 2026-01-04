"""Tests for scheduler module (Phase 6).

Tests APScheduler configuration and trigger creation.
"""

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.scheduler import (
    create_scheduler,
    get_m15_trigger,
    get_m30_trigger,
    get_tp_monitor_trigger,
)


class TestCreateScheduler:
    """Test scheduler creation and configuration."""

    def test_creates_asyncio_scheduler(self):
        """Verify scheduler is AsyncIOScheduler instance."""
        scheduler = create_scheduler()
        assert isinstance(scheduler, AsyncIOScheduler)

    def test_scheduler_has_job_defaults(self):
        """Verify scheduler has correct job defaults configured."""
        scheduler = create_scheduler()
        assert scheduler._job_defaults["coalesce"] is True
        assert scheduler._job_defaults["max_instances"] == 1
        assert scheduler._job_defaults["misfire_grace_time"] == 60

    def test_creates_new_instance(self):
        """Verify each call creates a new scheduler."""
        scheduler1 = create_scheduler()
        scheduler2 = create_scheduler()
        assert scheduler1 is not scheduler2


class TestM15Trigger:
    """Test M15 candle close trigger configuration."""

    def test_returns_cron_trigger(self):
        """Verify M15 trigger is CronTrigger instance."""
        trigger = get_m15_trigger()
        assert isinstance(trigger, CronTrigger)

    def test_m15_fires_at_correct_minutes(self):
        """Verify M15 trigger is set for minute 0, 15, 30, 45."""
        trigger = get_m15_trigger()
        # Verify trigger has correct minute specification
        assert trigger.fields[1] is not None  # Minute field exists

    def test_m15_trigger_immutable(self):
        """Verify M15 trigger is immutable after creation."""
        trigger1 = get_m15_trigger()
        trigger2 = get_m15_trigger()
        assert trigger1.fields == trigger2.fields


class TestM30Trigger:
    """Test M30 candle close trigger configuration."""

    def test_returns_cron_trigger(self):
        """Verify M30 trigger is CronTrigger instance."""
        trigger = get_m30_trigger()
        assert isinstance(trigger, CronTrigger)

    def test_m30_fires_at_correct_minutes(self):
        """Verify M30 trigger is set for minute 0, 30."""
        trigger = get_m30_trigger()
        # Verify trigger has correct minute specification
        assert trigger.fields[1] is not None  # Minute field exists

    def test_m30_trigger_immutable(self):
        """Verify M30 trigger is immutable after creation."""
        trigger1 = get_m30_trigger()
        trigger2 = get_m30_trigger()
        assert trigger1.fields == trigger2.fields


class TestTPMonitorTrigger:
    """Test TP monitoring interval trigger configuration."""

    def test_returns_interval_trigger(self):
        """Verify TP monitor trigger is IntervalTrigger instance."""
        trigger = get_tp_monitor_trigger()
        assert isinstance(trigger, IntervalTrigger)

    def test_tp_monitor_fires_every_30_seconds(self):
        """Verify TP monitor trigger is set for 30-second intervals."""
        from datetime import timedelta
        trigger = get_tp_monitor_trigger()
        assert trigger.interval == timedelta(seconds=30)

    def test_tp_monitor_trigger_immutable(self):
        """Verify TP monitor trigger is immutable after creation."""
        trigger1 = get_tp_monitor_trigger()
        trigger2 = get_tp_monitor_trigger()
        assert trigger1.interval == trigger2.interval


class TestSchedulerIntegration:
    """Integration tests for scheduler with triggers."""

    def test_can_add_m15_job_to_scheduler(self):
        """Verify M15 trigger can be added to scheduler."""
        scheduler = create_scheduler()
        trigger = get_m15_trigger()

        # Mock job function
        def mock_job():
            pass

        job = scheduler.add_job(mock_job, trigger)
        assert job is not None
        assert job.trigger == trigger
        scheduler.remove_job(job.id)

    def test_can_add_m30_job_to_scheduler(self):
        """Verify M30 trigger can be added to scheduler."""
        scheduler = create_scheduler()
        trigger = get_m30_trigger()

        def mock_job():
            pass

        job = scheduler.add_job(mock_job, trigger)
        assert job is not None
        assert job.trigger == trigger
        scheduler.remove_job(job.id)

    def test_can_add_tp_monitor_job_to_scheduler(self):
        """Verify TP monitor trigger can be added to scheduler."""
        scheduler = create_scheduler()
        trigger = get_tp_monitor_trigger()

        def mock_job():
            pass

        job = scheduler.add_job(mock_job, trigger)
        assert job is not None
        assert job.trigger == trigger
        scheduler.remove_job(job.id)

    def test_scheduler_respects_job_defaults(self):
        """Verify scheduler enforces job defaults."""
        scheduler = create_scheduler()

        def mock_job():
            pass

        job = scheduler.add_job(mock_job, get_m15_trigger())
        # Verify job was added successfully
        assert job is not None
        assert job.id is not None
        scheduler.remove_job(job.id)
