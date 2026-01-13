"""Event aggregation and deduplication for observer events.

Phase 02 - Observer Enhancements:
- Time-window based event grouping
- Hash-based duplicate detection
- Multi-factor event correlation

Provides:
- DuplicateDetector: Hash-based dedup with configurable window
- EventCorrelator: Multi-factor correlation scoring
- EventAggregator: Window-based aggregation with callbacks
"""

import hashlib
import logging
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Deque, Dict, List, Optional

from src.observers.base_observer import ObserverEvent

logger = logging.getLogger(__name__)


@dataclass
class AggregatedEvent:
    """Event aggregated from multiple observer events.

    Attributes:
        event_types: List of event type values from source events
        count: Number of events in this aggregation
        window_start: Unix timestamp when window started
        window_end: Unix timestamp when window closed
        confidence: Combined confidence score (0-1)
        correlation_type: Type of correlation detected
        source_events: Original ObserverEvents in this window
    """

    event_types: List[str]
    count: int
    window_start: float
    window_end: float
    confidence: float
    correlation_type: str
    source_events: List[ObserverEvent] = field(default_factory=list)

    @property
    def is_strong_signal(self) -> bool:
        """Check if aggregated event represents strong signal.

        Strong signal: confidence >= 0.75 AND count >= 2
        """
        return self.confidence >= 0.75 and self.count >= 2

    @property
    def unique_event_types(self) -> set:
        """Get unique event types in this aggregation."""
        return set(self.event_types)


class CorrelationType(str, Enum):
    """Types of event correlation."""

    SAME_IMPULSE = "same_impulse"  # Same market move triggering multiple observers
    COMPOSITE = "composite"  # Multiple confirming signals from different sources
    INDEPENDENT = "independent"  # Unrelated events in same window


class DuplicateDetector:
    """Detect and suppress duplicate events within time window.

    Uses hash-based idempotency keys to identify duplicates.
    Thread-safe with RLock pattern.
    """

    def __init__(self, dedup_window_seconds: int = 30):
        """Initialize duplicate detector.

        Args:
            dedup_window_seconds: Time window for duplicate detection
        """
        self.dedup_window = dedup_window_seconds
        self._seen_events: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._duplicates_suppressed = 0

    def create_idempotency_key(self, event: ObserverEvent) -> str:
        """Create unique key for event.

        Uses event type and critical data fields, ignoring timestamp.
        Price rounded to nearest 10 to allow minor fluctuations.

        Args:
            event: ObserverEvent to create key for

        Returns:
            16-char MD5 hash of key components
        """
        key_parts = [
            event.event_type.value,
            str(event.data.get("level", "")),
            str(event.data.get("ratio", "")),
            str(round(event.data.get("current_price", 0), -1)),  # Round to 10s
        ]
        key_data = ":".join(key_parts)
        return hashlib.md5(key_data.encode()).hexdigest()[:16]

    def is_duplicate(self, event: ObserverEvent) -> bool:
        """Check if event is duplicate within window.

        Args:
            event: ObserverEvent to check

        Returns:
            True if duplicate (should be suppressed)
        """
        with self._lock:
            key = self.create_idempotency_key(event)
            current_time = time.time()

            # Clean stale entries
            self._cleanup_stale_entries(current_time)

            # Check for duplicate
            if key in self._seen_events:
                self._duplicates_suppressed += 1
                logger.debug(f"Duplicate event suppressed: {event.event_type.value}")
                return True

            # Record event
            self._seen_events[key] = current_time
            return False

    def _cleanup_stale_entries(self, current_time: float):
        """Remove expired entries from seen events."""
        self._seen_events = {
            k: t
            for k, t in self._seen_events.items()
            if current_time - t < self.dedup_window
        }

    def get_status(self) -> dict:
        """Get detector status.

        Returns:
            Dict with tracked_keys, dedup_window, duplicates_suppressed
        """
        with self._lock:
            return {
                "tracked_keys": len(self._seen_events),
                "dedup_window_seconds": self.dedup_window,
                "duplicates_suppressed": self._duplicates_suppressed,
            }

    def reset(self):
        """Reset detector state (for testing)."""
        with self._lock:
            self._seen_events.clear()
            self._duplicates_suppressed = 0


class EventCorrelator:
    """Correlate events across multiple observers.

    Uses multi-factor scoring:
    - Event type diversity (35%)
    - Time proximity (40%)
    - Price proximity (25%)
    """

    def __init__(self, correlation_window_seconds: int = 30):
        """Initialize correlator.

        Args:
            correlation_window_seconds: Max time span for correlation
        """
        self.window = correlation_window_seconds

    def correlate(self, events: List[ObserverEvent]) -> tuple[CorrelationType, float]:
        """Determine if events are correlated.

        Args:
            events: List of ObserverEvents to correlate

        Returns:
            Tuple of (correlation_type, confidence_score)
        """
        if not events or len(events) < 2:
            return CorrelationType.INDEPENDENT, 0.0

        # Calculate time span
        timestamps = [e.timestamp for e in events]
        time_span = max(timestamps) - min(timestamps)

        # Calculate confidence factors
        confidence = 0.0

        # Factor 1: Event type diversity (35%)
        event_types = set(e.event_type.value for e in events)
        if len(event_types) > 1:
            confidence += 0.35

        # Factor 2: Time proximity (40%)
        if time_span < 10:
            confidence += 0.40
        elif time_span < 30:
            confidence += 0.25
        elif time_span < 60:
            confidence += 0.10

        # Factor 3: Price proximity (25%)
        prices = [
            e.data.get("current_price", 0)
            for e in events
            if "current_price" in e.data
        ]
        if len(prices) > 1:
            price_range = max(prices) - min(prices)
            if price_range < 5:  # Within 5 points on XAUUSD
                confidence += 0.25
            elif price_range < 10:
                confidence += 0.15

        # Determine correlation type
        if confidence >= 0.75:
            return CorrelationType.SAME_IMPULSE, min(1.0, confidence)
        elif confidence >= 0.4:
            return CorrelationType.COMPOSITE, confidence
        else:
            return CorrelationType.INDEPENDENT, confidence


class EventAggregator:
    """Aggregate observer events within time windows.

    Features:
    - Configurable window size (default 60s)
    - Duplicate detection (optional)
    - Event correlation scoring
    - Subscriber callbacks for aggregated events
    - Memory bounded with deque (max_history)
    """

    def __init__(
        self,
        window_size_seconds: int = 60,
        max_history: int = 100,
        dedup_enabled: bool = True,
        dedup_window_seconds: int = 30,
        correlation_window_seconds: int = 30,
    ):
        """Initialize event aggregator.

        Args:
            window_size_seconds: Aggregation window duration
            max_history: Max aggregated events to keep in history
            dedup_enabled: Enable duplicate detection
            dedup_window_seconds: Deduplication window
            correlation_window_seconds: Correlation window for scoring
        """
        self.window_size = window_size_seconds
        self.max_history = max_history

        self._current_window_events: List[ObserverEvent] = []
        self._window_start_time = time.time()
        self._aggregated_history: Deque[AggregatedEvent] = deque(maxlen=max_history)
        self._lock = threading.RLock()

        # Callbacks
        self._aggregated_callbacks: List[Callable[[AggregatedEvent], None]] = []

        # Components
        self._dedup_enabled = dedup_enabled
        self._dedup = (
            DuplicateDetector(dedup_window_seconds) if dedup_enabled else None
        )
        self._correlator = EventCorrelator(correlation_window_seconds)

        # Statistics
        self._total_events_received = 0
        self._total_aggregations_emitted = 0

    def add_event(self, event: ObserverEvent) -> bool:
        """Add event to current window.

        Args:
            event: ObserverEvent to add

        Returns:
            True if event was added, False if duplicate
        """
        with self._lock:
            self._total_events_received += 1

            # Check for duplicates
            if self._dedup_enabled and self._dedup and self._dedup.is_duplicate(event):
                return False

            current_time = time.time()

            # Check if window expired
            if current_time - self._window_start_time > self.window_size:
                # Emit previous window
                self._emit_aggregated_event()

                # Start new window
                self._current_window_events = []
                self._window_start_time = current_time

            # Add to current window
            self._current_window_events.append(event)
            return True

    def _emit_aggregated_event(self):
        """Emit aggregated event for current window."""
        if not self._current_window_events:
            return

        events = self._current_window_events

        # Calculate correlation
        corr_type, corr_confidence = self._correlator.correlate(events)

        # Calculate aggregate confidence
        event_confidences = [e.confidence for e in events]
        avg_confidence = (
            statistics.mean(event_confidences) if event_confidences else 0.0
        )

        # Combine correlation and event confidence
        final_confidence = (avg_confidence * 0.6) + (corr_confidence * 0.4)

        aggregated = AggregatedEvent(
            event_types=[e.event_type.value for e in events],
            count=len(events),
            window_start=self._window_start_time,
            window_end=time.time(),
            confidence=round(final_confidence, 3),
            correlation_type=corr_type.value,
            source_events=list(events),  # Copy to preserve
        )

        # Store in history
        self._aggregated_history.append(aggregated)
        self._total_aggregations_emitted += 1

        # Notify subscribers
        self._notify_subscribers(aggregated)

        logger.info(
            f"Aggregated event emitted: {len(events)} events, "
            f"types={set(aggregated.event_types)}, "
            f"correlation={corr_type.value}, confidence={final_confidence:.2f}"
        )

    def _notify_subscribers(self, aggregated: AggregatedEvent):
        """Notify all aggregated event subscribers."""
        # Copy list to avoid lock during callbacks
        with self._lock:
            callbacks = list(self._aggregated_callbacks)

        for callback in callbacks:
            try:
                callback(aggregated)
            except Exception as e:
                logger.error(f"Aggregated callback error: {e}")

    def subscribe_aggregated(self, callback: Callable[[AggregatedEvent], None]):
        """Subscribe to aggregated events.

        Args:
            callback: Function to call with AggregatedEvent
        """
        with self._lock:
            self._aggregated_callbacks.append(callback)
        logger.debug(f"Aggregated subscriber added. Total: {len(self._aggregated_callbacks)}")

    def unsubscribe_aggregated(
        self, callback: Callable[[AggregatedEvent], None]
    ) -> bool:
        """Unsubscribe from aggregated events.

        Args:
            callback: Function to remove

        Returns:
            True if callback was removed
        """
        with self._lock:
            try:
                self._aggregated_callbacks.remove(callback)
                return True
            except ValueError:
                return False

    def flush(self):
        """Force emit current window (for testing or shutdown)."""
        with self._lock:
            if self._current_window_events:
                self._emit_aggregated_event()
                self._current_window_events = []
                self._window_start_time = time.time()

    def get_recent_aggregations(self, count: int = 10) -> List[AggregatedEvent]:
        """Get recent aggregated events.

        Args:
            count: Number of recent events to return

        Returns:
            List of recent AggregatedEvents (newest first)
        """
        with self._lock:
            return list(self._aggregated_history)[-count:][::-1]

    def get_status(self) -> dict:
        """Get aggregator status.

        Returns:
            Dict with window state, history count, subscriber count, dedup status
        """
        with self._lock:
            return {
                "events_in_current_window": len(self._current_window_events),
                "window_age_seconds": round(time.time() - self._window_start_time, 1),
                "window_size_seconds": self.window_size,
                "aggregated_history_count": len(self._aggregated_history),
                "subscribers_count": len(self._aggregated_callbacks),
                "total_events_received": self._total_events_received,
                "total_aggregations_emitted": self._total_aggregations_emitted,
                "dedup_enabled": self._dedup_enabled,
                "dedup_status": self._dedup.get_status() if self._dedup else None,
            }

    def reset(self):
        """Reset aggregator state (for testing)."""
        with self._lock:
            self._current_window_events = []
            self._window_start_time = time.time()
            self._aggregated_history.clear()
            self._total_events_received = 0
            self._total_aggregations_emitted = 0
            if self._dedup:
                self._dedup.reset()
