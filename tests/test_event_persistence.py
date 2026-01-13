"""Tests for event_persistence module - Phase 04 Observer Enhancements.

Tests EventStore, EventReplayer, and StoredEvent functionality.
"""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.observers.base_observer import ObserverEvent, ObserverEventType
from src.observers.event_persistence import (
    EventReplayer,
    EventStore,
    StoredEvent,
    get_event_store,
    reset_event_store,
)


# ===== Fixtures =====


@pytest.fixture
def temp_db_path():
    """Create temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test_events.db")


@pytest.fixture
def event_store(temp_db_path):
    """Create EventStore with temp database."""
    return EventStore(db_path=temp_db_path, batch_size=10)


@pytest.fixture
def sample_event():
    """Create sample ObserverEvent."""
    return ObserverEvent(
        event_type=ObserverEventType.VOLATILITY_SPIKE,
        timestamp=time.time(),
        data={"atr_ratio": 2.0, "current_price": 2350.0},
        confidence=0.85,
    )


@pytest.fixture
def multiple_events():
    """Create multiple sample events."""
    base_time = time.time()
    events = []
    for i in range(15):
        event = ObserverEvent(
            event_type=ObserverEventType.VOLATILITY_SPIKE if i % 2 == 0 else ObserverEventType.KEY_LEVEL_PROXIMITY,
            timestamp=base_time + i,
            data={"index": i, "value": i * 10.0},
            confidence=0.5 + (i * 0.03),
        )
        events.append(event)
    return events


# ===== StoredEvent Tests =====


class TestStoredEvent:
    """Tests for StoredEvent dataclass."""

    def test_to_observer_event_conversion(self):
        """StoredEvent converts to ObserverEvent correctly."""
        timestamp_ns = int(time.time() * 1_000_000_000)
        stored = StoredEvent(
            id=1,
            event_id="volatility_spike_123_0",
            timestamp_ns=timestamp_ns,
            event_type="volatility_spike",
            confidence=0.85,
            data={"key": "value"},
            sequence_number=0,
        )

        event = stored.to_observer_event()

        assert event.event_type == ObserverEventType.VOLATILITY_SPIKE
        assert event.confidence == 0.85
        assert event.data == {"key": "value"}
        assert abs(event.timestamp - (timestamp_ns / 1_000_000_000)) < 0.001

    def test_nanosecond_precision_preserved(self):
        """Nanosecond timestamp precision preserved in conversion."""
        timestamp_ns = 1704067200123456789
        stored = StoredEvent(
            id=1,
            event_id="test",
            timestamp_ns=timestamp_ns,
            event_type="volatility_spike",
            confidence=0.5,
            data={},
            sequence_number=0,
        )

        event = stored.to_observer_event()
        expected = timestamp_ns / 1_000_000_000

        assert abs(event.timestamp - expected) < 1e-9


# ===== EventStore Tests =====


class TestEventStore:
    """Tests for EventStore class."""

    def test_init_creates_database(self, temp_db_path):
        """EventStore creates database file on init."""
        store = EventStore(db_path=temp_db_path)

        assert Path(temp_db_path).exists()
        assert store.count() == 0

    def test_init_creates_directory(self):
        """EventStore creates parent directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = os.path.join(tmpdir, "subdir", "deep", "events.db")
            store = EventStore(db_path=nested_path)

            assert Path(nested_path).exists()

    def test_store_returns_event_id(self, event_store, sample_event):
        """store() returns unique event ID."""
        event_id = event_store.store(sample_event)

        assert event_id is not None
        assert "volatility_spike" in event_id

    def test_store_increments_sequence(self, event_store, sample_event):
        """store() increments sequence number for each event."""
        id1 = event_store.store(sample_event)
        id2 = event_store.store(sample_event)

        # Sequence numbers should be different
        assert id1 != id2
        assert "_0" in id1
        assert "_1" in id2

    def test_batch_flush_at_threshold(self, event_store, multiple_events):
        """Events flushed when batch_size reached."""
        event_store.batch_size = 5

        # Store 4 events - should not flush yet
        for i in range(4):
            event_store.store(multiple_events[i])

        # Buffered, not yet in DB
        assert len(event_store._buffer) == 4

        # Store 5th event - triggers flush
        event_store.store(multiple_events[4])

        # Buffer should be empty after flush
        assert len(event_store._buffer) == 0

    def test_manual_flush(self, event_store, sample_event):
        """flush() writes buffered events to database."""
        event_store.store(sample_event)
        assert len(event_store._buffer) == 1

        event_store.flush()

        assert len(event_store._buffer) == 0
        assert event_store.count() == 1

    def test_query_returns_stored_events(self, event_store, multiple_events):
        """query() returns stored events."""
        for event in multiple_events[:5]:
            event_store.store(event)
        event_store.flush()

        results = event_store.query()

        assert len(results) == 5
        assert all(isinstance(r, StoredEvent) for r in results)

    def test_query_filter_by_time_range(self, event_store, multiple_events):
        """query() filters by time range."""
        base_time = multiple_events[0].timestamp

        for event in multiple_events:
            event_store.store(event)
        event_store.flush()

        # Query middle range
        results = event_store.query(
            start_time=base_time + 2,
            end_time=base_time + 7,
        )

        # Should get events with index 2-7
        assert len(results) >= 5

    def test_query_filter_by_event_type(self, event_store, multiple_events):
        """query() filters by event types."""
        for event in multiple_events:
            event_store.store(event)
        event_store.flush()

        results = event_store.query(
            event_types=["volatility_spike"]
        )

        # All results should be volatility_spike type
        assert all(r.event_type == "volatility_spike" for r in results)

    def test_query_respects_limit(self, event_store, multiple_events):
        """query() respects limit parameter."""
        for event in multiple_events:
            event_store.store(event)
        event_store.flush()

        results = event_store.query(limit=3)

        assert len(results) == 3

    def test_query_orders_by_sequence(self, event_store, multiple_events):
        """query() returns events ordered by sequence."""
        for event in multiple_events[:5]:
            event_store.store(event)
        event_store.flush()

        results = event_store.query()

        sequences = [r.sequence_number for r in results]
        assert sequences == sorted(sequences)

    def test_count_returns_total_events(self, event_store, multiple_events):
        """count() returns total event count."""
        for event in multiple_events[:7]:
            event_store.store(event)
        event_store.flush()

        assert event_store.count() == 7

    def test_prune_old_events(self, event_store):
        """prune_old_events() deletes old events."""
        # Create event with old timestamp
        old_event = ObserverEvent(
            event_type=ObserverEventType.VOLATILITY_SPIKE,
            timestamp=time.time() - (10 * 86400),  # 10 days ago
            data={},
            confidence=0.5,
        )
        recent_event = ObserverEvent(
            event_type=ObserverEventType.VOLATILITY_SPIKE,
            timestamp=time.time(),  # now
            data={},
            confidence=0.5,
        )

        event_store.store(old_event)
        event_store.store(recent_event)
        event_store.flush()

        assert event_store.count() == 2

        # Prune events older than 7 days
        deleted = event_store.prune_old_events(max_age_days=7)

        assert deleted == 1
        assert event_store.count() == 1

    def test_get_status(self, event_store, sample_event):
        """get_status() returns store status."""
        event_store.store(sample_event)

        status = event_store.get_status()

        assert "db_path" in status
        assert "total_events" in status
        assert "buffered_events" in status
        assert "current_sequence" in status
        assert status["buffered_events"] == 1

    def test_sequence_recovery_on_init(self, temp_db_path, sample_event):
        """EventStore recovers sequence number on restart."""
        # First store
        store1 = EventStore(db_path=temp_db_path, batch_size=1)
        store1.store(sample_event)
        store1.store(sample_event)
        store1.store(sample_event)
        store1.flush()

        # Create new store instance
        store2 = EventStore(db_path=temp_db_path, batch_size=1)

        # Sequence should continue from where we left off
        assert store2._sequence == 3


# ===== EventReplayer Tests =====


class TestEventReplayer:
    """Tests for EventReplayer class."""

    def test_replay_empty_store(self, event_store):
        """replay() handles empty store gracefully."""
        replayer = EventReplayer(event_store)

        events = list(replayer.replay(
            start_time=time.time() - 3600,
            end_time=time.time(),
        ))

        assert events == []

    def test_replay_returns_events(self, event_store, multiple_events):
        """replay() yields stored events."""
        for event in multiple_events[:5]:
            event_store.store(event)
        event_store.flush()

        replayer = EventReplayer(event_store)
        base_time = multiple_events[0].timestamp

        events = list(replayer.replay(
            start_time=base_time - 1,
            end_time=base_time + 100,
            speed=0,  # No delay
        ))

        assert len(events) == 5
        assert all(isinstance(e, ObserverEvent) for e in events)

    def test_replay_invokes_callback(self, event_store, sample_event):
        """replay() calls callback for each event."""
        event_store.store(sample_event)
        event_store.flush()

        replayer = EventReplayer(event_store)
        callback = Mock()

        list(replayer.replay(
            start_time=sample_event.timestamp - 1,
            end_time=sample_event.timestamp + 1,
            callback=callback,
            speed=0,
        ))

        assert callback.called
        assert callback.call_count == 1

    def test_replay_filters_by_event_type(self, event_store, multiple_events):
        """replay() filters by event types."""
        for event in multiple_events:
            event_store.store(event)
        event_store.flush()

        replayer = EventReplayer(event_store)
        base_time = multiple_events[0].timestamp

        events = list(replayer.replay(
            start_time=base_time - 1,
            end_time=base_time + 100,
            event_types=["key_level_proximity"],
            speed=0,
        ))

        # Should only get key_level_proximity events
        assert all(e.event_type == ObserverEventType.KEY_LEVEL_PROXIMITY for e in events)

    def test_replay_callback_error_handled(self, event_store, sample_event):
        """replay() handles callback errors gracefully."""
        event_store.store(sample_event)
        event_store.flush()

        replayer = EventReplayer(event_store)
        callback = Mock(side_effect=Exception("callback error"))

        # Should not raise exception
        events = list(replayer.replay(
            start_time=sample_event.timestamp - 1,
            end_time=sample_event.timestamp + 1,
            callback=callback,
            speed=0,
        ))

        assert len(events) == 1

    def test_get_time_range_empty(self, event_store):
        """get_time_range() returns None for empty store."""
        replayer = EventReplayer(event_store)

        min_time, max_time = replayer.get_time_range()

        assert min_time is None
        assert max_time is None

    def test_get_time_range_with_events(self, event_store, multiple_events):
        """get_time_range() returns correct min/max timestamps."""
        for event in multiple_events[:5]:
            event_store.store(event)
        event_store.flush()

        replayer = EventReplayer(event_store)
        min_time, max_time = replayer.get_time_range()

        expected_min = multiple_events[0].timestamp
        expected_max = multiple_events[4].timestamp

        assert min_time is not None
        assert max_time is not None
        assert abs(min_time - expected_min) < 0.001
        assert abs(max_time - expected_max) < 0.001


# ===== Singleton Tests =====


class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_event_store_singleton(self):
        """get_event_store() returns same instance."""
        reset_event_store()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "singleton.db")

            with patch("src.config.get_settings") as mock_settings:
                mock_settings.return_value = Mock(
                    observer_persistence_db_path=db_path,
                    observer_persistence_batch_size=100,
                )

                store1 = get_event_store()
                store2 = get_event_store()

                assert store1 is store2

        reset_event_store()

    def test_reset_event_store(self):
        """reset_event_store() clears singleton."""
        reset_event_store()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reset.db")

            with patch("src.config.get_settings") as mock_settings:
                mock_settings.return_value = Mock(
                    observer_persistence_db_path=db_path,
                    observer_persistence_batch_size=100,
                )

                store1 = get_event_store()
                reset_event_store()
                store2 = get_event_store()

                assert store1 is not store2

        reset_event_store()


# ===== Integration Tests =====


class TestIntegration:
    """Integration tests for persistence system."""

    def test_store_query_replay_workflow(self, temp_db_path):
        """Full workflow: store -> query -> replay."""
        store = EventStore(db_path=temp_db_path, batch_size=100)

        # Store events
        base_time = time.time()
        for i in range(10):
            event = ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE,
                timestamp=base_time + i,
                data={"index": i},
                confidence=0.5 + (i * 0.05),
            )
            store.store(event)
        store.flush()

        # Query events
        results = store.query(
            start_time=base_time,
            end_time=base_time + 20,
        )
        assert len(results) == 10

        # Replay events
        replayer = EventReplayer(store)
        replayed = []

        for event in replayer.replay(
            start_time=base_time,
            end_time=base_time + 20,
            speed=0,
        ):
            replayed.append(event)

        assert len(replayed) == 10

        # Verify data integrity
        for i, event in enumerate(replayed):
            assert event.data.get("index") == i

    def test_persistence_across_sessions(self, temp_db_path):
        """Events persist across EventStore instances."""
        # Session 1: Store events
        store1 = EventStore(db_path=temp_db_path, batch_size=1)
        for i in range(5):
            store1.store(ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE,
                timestamp=time.time() + i,
                data={"session": 1, "index": i},
                confidence=0.5,
            ))
        store1.flush()  # Ensure all events persisted before session 2

        # Session 2: Store more events
        store2 = EventStore(db_path=temp_db_path, batch_size=1)
        for i in range(5):
            store2.store(ObserverEvent(
                event_type=ObserverEventType.KEY_LEVEL_PROXIMITY,
                timestamp=time.time() + 10 + i,
                data={"session": 2, "index": i},
                confidence=0.6,
            ))

        # Verify all events preserved
        results = store2.query(limit=100)
        assert len(results) == 10

        # Check both sessions present
        session1_events = [r for r in results if r.data.get("session") == 1]
        session2_events = [r for r in results if r.data.get("session") == 2]

        assert len(session1_events) == 5
        assert len(session2_events) == 5
