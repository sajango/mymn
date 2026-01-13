"""Event persistence for observer events using SQLite.

Provides immutable event storage, replay capability, and query support.
Phase 04 - Observer Enhancements.

Features:
- Batch inserts for efficiency (100 events/batch default)
- Sequence numbers for ordering guarantee
- Time-based queries and event type filtering
- Replay with speed control for backtesting
- Auto-prune for bounded storage
"""

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, List, Optional

from src.observers.base_observer import ObserverEvent, ObserverEventType

logger = logging.getLogger(__name__)


# SQLite schema with indexes for efficient queries
CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS observer_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    timestamp_ns INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    data TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_timestamp ON observer_events(timestamp_ns);
CREATE INDEX IF NOT EXISTS idx_event_type ON observer_events(event_type);
CREATE INDEX IF NOT EXISTS idx_sequence ON observer_events(sequence_number);
"""


@dataclass
class StoredEvent:
    """Event record from database.

    Attributes:
        id: Database primary key
        event_id: Unique event identifier
        timestamp_ns: Event timestamp in nanoseconds
        event_type: Event type string
        confidence: Event confidence 0-1
        data: Event data dictionary
        sequence_number: Ordering sequence number
    """

    id: int
    event_id: str
    timestamp_ns: int
    event_type: str
    confidence: float
    data: dict
    sequence_number: int

    def to_observer_event(self) -> ObserverEvent:
        """Convert to ObserverEvent.

        Returns:
            ObserverEvent with timestamp converted from nanoseconds
        """
        return ObserverEvent(
            event_type=ObserverEventType(self.event_type),
            timestamp=self.timestamp_ns / 1_000_000_000,
            data=self.data,
            confidence=self.confidence,
        )


class EventStore:
    """SQLite-based event storage with batch inserts.

    Thread-safe, supports concurrent reads and batched writes.
    Uses buffering to reduce database writes and improve performance.

    Example:
        store = EventStore("data/events.db")
        store.store(observer_event)
        events = store.query(start_time=time.time() - 3600)
        store.flush()  # Force write pending events
    """

    def __init__(
        self,
        db_path: str = "data/observer_events.db",
        batch_size: int = 100,
    ):
        """Initialize event store.

        Args:
            db_path: Path to SQLite database
            batch_size: Events to buffer before batch insert (10-1000)
        """
        self.db_path = Path(db_path)
        self.batch_size = max(10, min(batch_size, 1000))  # Enforce 10-1000 range

        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # State
        self._buffer: List[tuple] = []
        self._sequence = 0
        self._lock = threading.RLock()

        # Initialize database
        self._init_db()

    def _init_db(self):
        """Initialize database schema and recover sequence."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(CREATE_EVENTS_TABLE)
            conn.commit()

            # Recover max sequence number
            cursor = conn.execute(
                "SELECT MAX(sequence_number) FROM observer_events"
            )
            result = cursor.fetchone()[0]
            self._sequence = result + 1 if result else 0

        logger.info(f"EventStore initialized: {self.db_path}, sequence={self._sequence}")

    def store(self, event: ObserverEvent) -> str:
        """Store event (buffered for batch insert).

        Args:
            event: ObserverEvent to store

        Returns:
            Event ID for reference
        """
        with self._lock:
            # Generate unique event ID
            event_id = f"{event.event_type.value}_{int(event.timestamp * 1000)}_{self._sequence}"

            # Add to buffer
            self._buffer.append((
                event_id,
                int(event.timestamp * 1_000_000_000),  # Convert to nanoseconds
                event.event_type.value,
                event.confidence,
                json.dumps(event.data),
                self._sequence,
            ))
            self._sequence += 1

            # Flush if batch size reached
            if len(self._buffer) >= self.batch_size:
                self._flush()

            return event_id

    def _flush(self):
        """Flush buffered events to database."""
        if not self._buffer:
            return

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO observer_events
                    (event_id, timestamp_ns, event_type, confidence, data, sequence_number)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    self._buffer
                )
                conn.commit()

            logger.debug(f"Flushed {len(self._buffer)} events to database")
        except Exception as e:
            logger.error(f"EventStore flush failed: {e}")
        finally:
            self._buffer.clear()

    def flush(self):
        """Public flush method (for shutdown/testing)."""
        with self._lock:
            self._flush()

    def query(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        event_types: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[StoredEvent]:
        """Query stored events.

        Args:
            start_time: Start timestamp in seconds (inclusive)
            end_time: End timestamp in seconds (inclusive)
            event_types: Filter by event type values
            limit: Max events to return

        Returns:
            List of StoredEvent ordered by sequence
        """
        # Flush before query to include recent events
        self.flush()

        conditions = []
        params: List = []

        if start_time is not None:
            conditions.append("timestamp_ns >= ?")
            params.append(int(start_time * 1_000_000_000))

        if end_time is not None:
            conditions.append("timestamp_ns <= ?")
            params.append(int(end_time * 1_000_000_000))

        if event_types:
            placeholders = ",".join("?" for _ in event_types)
            conditions.append(f"event_type IN ({placeholders})")
            params.extend(event_types)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query_sql = f"""
            SELECT id, event_id, timestamp_ns, event_type, confidence, data, sequence_number
            FROM observer_events
            WHERE {where_clause}
            ORDER BY sequence_number ASC
            LIMIT ?
        """
        params.append(limit)

        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query_sql, params)

                for row in cursor:
                    results.append(StoredEvent(
                        id=row["id"],
                        event_id=row["event_id"],
                        timestamp_ns=row["timestamp_ns"],
                        event_type=row["event_type"],
                        confidence=row["confidence"],
                        data=json.loads(row["data"]),
                        sequence_number=row["sequence_number"],
                    ))
        except Exception as e:
            logger.error(f"EventStore query failed: {e}")

        return results

    def count(self) -> int:
        """Get total event count.

        Returns:
            Number of events in database
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM observer_events")
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"EventStore count failed: {e}")
            return 0

    def prune_old_events(self, max_age_days: int = 7) -> int:
        """Delete events older than max_age_days.

        Args:
            max_age_days: Delete events older than this

        Returns:
            Number of events deleted
        """
        cutoff_ns = int((time.time() - (max_age_days * 86400)) * 1_000_000_000)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM observer_events WHERE timestamp_ns < ?",
                    (cutoff_ns,)
                )
                deleted = cursor.rowcount
                conn.commit()

            if deleted > 0:
                logger.info(f"Pruned {deleted} events older than {max_age_days} days")

            return deleted
        except Exception as e:
            logger.error(f"EventStore prune failed: {e}")
            return 0

    def get_status(self) -> dict:
        """Get store status summary.

        Returns:
            Dict with db_path, total_events, buffered_events, sequence, batch_size
        """
        with self._lock:
            return {
                "db_path": str(self.db_path),
                "total_events": self.count(),
                "buffered_events": len(self._buffer),
                "current_sequence": self._sequence,
                "batch_size": self.batch_size,
            }


class EventReplayer:
    """Replay stored events for backtesting and debugging.

    Supports variable playback speed and callback invocation.
    Iterates events in chronological order based on sequence number.

    Example:
        replayer = EventReplayer(store)
        for event in replayer.replay(start, end, speed=10.0):
            process(event)
    """

    def __init__(self, store: EventStore):
        """Initialize replayer.

        Args:
            store: EventStore to replay from
        """
        self.store = store

    def replay(
        self,
        start_time: float,
        end_time: float,
        event_types: Optional[List[str]] = None,
        callback: Optional[Callable[[ObserverEvent], None]] = None,
        speed: float = 1.0,
    ) -> Iterator[ObserverEvent]:
        """Replay events in chronological order.

        Args:
            start_time: Start timestamp in seconds
            end_time: End timestamp in seconds
            event_types: Filter by event types
            callback: Optional callback for each event
            speed: Playback speed (1.0 = real-time, 10.0 = 10x speed, 0 = no delay)

        Yields:
            ObserverEvent in chronological order
        """
        events = self.store.query(
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
            limit=100000,  # High limit for replay
        )

        if not events:
            logger.info("No events to replay")
            return

        logger.info(f"Replaying {len(events)} events at {speed}x speed")

        last_timestamp_ns = None
        for stored in events:
            # Simulate timing between events
            if last_timestamp_ns is not None and speed > 0:
                delta_ns = stored.timestamp_ns - last_timestamp_ns
                delay_seconds = (delta_ns / 1_000_000_000) / speed
                # Cap delay at 10 seconds to prevent long waits
                if delay_seconds > 0 and delay_seconds < 10:
                    time.sleep(delay_seconds)

            event = stored.to_observer_event()

            if callback:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Replay callback error: {e}")

            yield event
            last_timestamp_ns = stored.timestamp_ns

    def get_time_range(self) -> tuple[Optional[float], Optional[float]]:
        """Get min and max timestamps in store.

        Returns:
            (min_time, max_time) in seconds, or (None, None) if empty
        """
        try:
            with sqlite3.connect(self.store.db_path) as conn:
                cursor = conn.execute(
                    "SELECT MIN(timestamp_ns), MAX(timestamp_ns) FROM observer_events"
                )
                row = cursor.fetchone()

                if row[0] is None:
                    return None, None

                return row[0] / 1_000_000_000, row[1] / 1_000_000_000
        except Exception as e:
            logger.error(f"EventReplayer get_time_range failed: {e}")
            return None, None


# Singleton instance for global access
_event_store: Optional[EventStore] = None


def get_event_store(
    db_path: Optional[str] = None,
    batch_size: Optional[int] = None,
) -> EventStore:
    """Get or create event store singleton.

    Args:
        db_path: Path to database (uses config default if None)
        batch_size: Batch size (uses config default if None)

    Returns:
        EventStore singleton instance
    """
    global _event_store
    if _event_store is None:
        from src.config import get_settings
        config = get_settings()

        _event_store = EventStore(
            db_path=db_path or config.observer_persistence_db_path,
            batch_size=batch_size or config.observer_persistence_batch_size,
        )
    return _event_store


def reset_event_store():
    """Reset event store singleton (for testing)."""
    global _event_store
    if _event_store:
        _event_store.flush()
    _event_store = None
