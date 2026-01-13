"""Market observer orchestrator - manages all observers.

Provides pub/sub pattern for event notifications and centralized management
of all market observers. Supports lazy loading via singleton factory.
Thread-safe for concurrent access from scheduler jobs.

Phase 02 - Observer Enhancements:
- Event aggregation and deduplication integration
- Aggregated event subscriptions

Phase 03 - Observer Telemetry:
- Metrics collection (counters, gauges, histograms)
- Latency tracking with nanosecond precision
- Health monitoring with pass/degraded/unhealthy status
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from src.observers.base_observer import BaseObserver, ObserverEvent
from src.observers.event_aggregator import AggregatedEvent, EventAggregator
from src.observers.observer_telemetry import (
    HealthChecker,
    LatencyTracer,
    get_observer_metrics,
)

logger = logging.getLogger(__name__)


@dataclass
class MarketObserverState:
    """Aggregate state for market observer.

    Attributes:
        events_emitted: Total events emitted since startup
        last_event_time: Timestamp of last emitted event
        active_observers: Number of registered observers
    """

    events_emitted: int = 0
    last_event_time: float = 0.0
    active_observers: int = 0


class MarketObserver:
    """Orchestrates multiple market observers.

    Manages observer lifecycle, event aggregation, and subscriber notifications.
    Implements pub/sub pattern - subscribers receive ObserverEvent via callback.

    Example:
        observer = MarketObserver()
        observer.register_observer(VolatilitySpikeObserver())
        observer.subscribe(my_callback)
        events = observer.check_all({"atr_current": 15.0})
    """

    def __init__(self, enable_telemetry: bool = True):
        """Initialize market observer orchestrator.

        Args:
            enable_telemetry: Enable metrics/telemetry collection (default True)
        """
        self._observers: List[BaseObserver] = []
        self._subscribers: List[Callable[[ObserverEvent], None]] = []
        self._state = MarketObserverState()
        self._lock = threading.RLock()  # Thread-safe access to lists
        self._aggregator: Optional[EventAggregator] = None
        self._enable_telemetry = enable_telemetry
        self._health_checker = HealthChecker()

    def register_observer(self, observer: BaseObserver):
        """Register an observer for monitoring.

        Args:
            observer: Observer instance to register
        """
        with self._lock:
            self._observers.append(observer)
            self._state.active_observers = len(self._observers)
        logger.info(f"Observer registered: {observer.name}")

    def unregister_observer(self, name: str) -> bool:
        """Unregister an observer by name.

        Args:
            name: Observer name to remove

        Returns:
            True if observer was found and removed
        """
        with self._lock:
            for i, obs in enumerate(self._observers):
                if obs.name == name:
                    self._observers.pop(i)
                    self._state.active_observers = len(self._observers)
                    logger.info(f"Observer unregistered: {name}")
                    return True
        return False

    def subscribe(self, callback: Callable[[ObserverEvent], None]):
        """Subscribe to observer events.

        Args:
            callback: Function to call when event occurs
        """
        with self._lock:
            self._subscribers.append(callback)
            count = len(self._subscribers)
        logger.debug(f"Subscriber added. Total: {count}")

    def unsubscribe(self, callback: Callable[[ObserverEvent], None]) -> bool:
        """Unsubscribe from observer events.

        Args:
            callback: Function to remove from subscribers

        Returns:
            True if callback was found and removed
        """
        with self._lock:
            try:
                self._subscribers.remove(callback)
                return True
            except ValueError:
                return False

    def enable_aggregation(
        self,
        window_size_seconds: int = 60,
        dedup_enabled: bool = True,
        dedup_window_seconds: int = 30,
        correlation_window_seconds: int = 30,
    ):
        """Enable event aggregation and deduplication.

        Args:
            window_size_seconds: Aggregation window duration
            dedup_enabled: Enable duplicate detection
            dedup_window_seconds: Deduplication window
            correlation_window_seconds: Correlation window for scoring
        """
        self._aggregator = EventAggregator(
            window_size_seconds=window_size_seconds,
            dedup_enabled=dedup_enabled,
            dedup_window_seconds=dedup_window_seconds,
            correlation_window_seconds=correlation_window_seconds,
        )
        logger.info(
            f"Event aggregation enabled: window={window_size_seconds}s, "
            f"dedup={dedup_enabled}, dedup_window={dedup_window_seconds}s"
        )

    def disable_aggregation(self):
        """Disable event aggregation."""
        if self._aggregator:
            self._aggregator.flush()  # Emit any pending events
            self._aggregator = None
            logger.info("Event aggregation disabled")

    def subscribe_aggregated(
        self, callback: Callable[[AggregatedEvent], None]
    ):
        """Subscribe to aggregated events.

        Args:
            callback: Function to call with AggregatedEvent
        """
        if self._aggregator:
            self._aggregator.subscribe_aggregated(callback)
        else:
            logger.warning("Aggregation not enabled, subscribe_aggregated ignored")

    def unsubscribe_aggregated(
        self, callback: Callable[[AggregatedEvent], None]
    ) -> bool:
        """Unsubscribe from aggregated events.

        Returns:
            True if callback was removed
        """
        if self._aggregator:
            return self._aggregator.unsubscribe_aggregated(callback)
        return False

    def flush_aggregation(self):
        """Force emit current aggregation window."""
        if self._aggregator:
            self._aggregator.flush()

    def check_all(self, market_data: dict) -> List[ObserverEvent]:
        """Check all observers for triggered conditions.

        Args:
            market_data: Current market data dict

        Returns:
            List of triggered ObserverEvents
        """
        events = []
        metrics = get_observer_metrics() if self._enable_telemetry else None

        # Copy list to avoid holding lock during check
        with self._lock:
            observers = list(self._observers)

        for observer in observers:
            if not observer.enabled:
                continue

            try:
                # Wrap check with latency tracing if telemetry enabled
                if metrics:
                    tags = {"observer": observer.name}
                    with LatencyTracer(metrics, "processing_latency_ms", tags):
                        event = observer.check(market_data)
                    metrics.increment("events_processed", tags=tags)
                else:
                    event = observer.check(market_data)

                if event:
                    events.append(event)
                    self._emit_event(event)
                    if metrics:
                        metrics.increment(
                            "signals_generated", tags={"observer": observer.name}
                        )

            except Exception as e:
                logger.error(f"Observer {observer.name} check failed: {e}")
                if metrics:
                    metrics.increment(
                        "errors",
                        tags={"observer": observer.name, "error": type(e).__name__},
                    )

        # Update gauges if telemetry enabled
        if metrics:
            metrics.set_gauge("active_observers", len(observers))
            metrics.set_gauge("events_in_batch", len(events))

        return events

    def _emit_event(self, event: ObserverEvent):
        """Emit event to all subscribers and aggregator.

        Args:
            event: ObserverEvent to emit
        """
        self._state.events_emitted += 1
        self._state.last_event_time = time.time()

        # Copy list to avoid holding lock during callbacks
        with self._lock:
            subscribers = list(self._subscribers)

        for subscriber in subscribers:
            try:
                subscriber(event)
            except Exception as e:
                logger.error(f"Subscriber callback failed: {e}")

        # Add to aggregator if enabled (outside lock to avoid deadlock)
        if self._aggregator:
            self._aggregator.add_event(event)

    def get_observer(self, name: str) -> Optional[BaseObserver]:
        """Get observer by name.

        Args:
            name: Observer name

        Returns:
            Observer instance or None
        """
        with self._lock:
            for observer in self._observers:
                if observer.name == name:
                    return observer
        return None

    def enable_all(self):
        """Enable all registered observers."""
        with self._lock:
            for observer in self._observers:
                observer.enabled = True
        logger.info("All observers enabled")

    def disable_all(self):
        """Disable all registered observers."""
        with self._lock:
            for observer in self._observers:
                observer.enabled = False
        logger.info("All observers disabled")

    def reset_all_states(self):
        """Reset state of all observers."""
        with self._lock:
            for observer in self._observers:
                observer.reset_state()
        logger.info("All observer states reset")

    def get_status(self) -> dict:
        """Get overall observer system status.

        Returns:
            Dict with system status and per-observer status
        """
        with self._lock:
            observer_statuses = [obs.get_status() for obs in self._observers]
            subscribers_count = len(self._subscribers)

        return {
            "events_emitted": self._state.events_emitted,
            "last_event_time": self._state.last_event_time,
            "active_observers": self._state.active_observers,
            "subscribers_count": subscribers_count,
            "observers": observer_statuses,
            "aggregator": self._aggregator.get_status() if self._aggregator else None,
        }

    def get_health(self) -> Dict[str, Any]:
        """Get observer health status.

        Returns:
            Dict with healthy, status, error_rate, avg_latency_ms, checks, message
        """
        if not self._enable_telemetry:
            return {
                "healthy": True,
                "status": "unknown",
                "error_rate": 0.0,
                "avg_latency_ms": 0.0,
                "checks": {},
                "message": "Telemetry disabled",
            }

        metrics = get_observer_metrics()
        health = self._health_checker.check(metrics)
        return health.to_dict()

    def get_metrics(self) -> Dict[str, Any]:
        """Get observer metrics summary.

        Returns:
            Dict with name, timestamp, counters, gauges, histograms
        """
        if not self._enable_telemetry:
            return {
                "name": "observer",
                "timestamp": time.time(),
                "counters": {},
                "gauges": {},
                "histograms": {},
                "message": "Telemetry disabled",
            }

        return get_observer_metrics().get_summary()


# Singleton pattern for global access
_market_observer: Optional[MarketObserver] = None


def get_market_observer() -> MarketObserver:
    """Get or create MarketObserver singleton.

    Initializes default observers from config settings on first call.

    Returns:
        MarketObserver singleton instance
    """
    global _market_observer

    if _market_observer is None:
        _market_observer = MarketObserver()

        # Import here to avoid circular imports
        from src.config import get_settings
        from src.observers.compression_observer import VolatilityCompressionObserver
        from src.observers.key_level_observer import KeyLevelObserver
        from src.observers.volatility_observer import VolatilitySpikeObserver

        config = get_settings()

        # Register default observers with config settings
        _market_observer.register_observer(
            VolatilitySpikeObserver(
                spike_threshold=config.observer_spike_threshold,
                cooldown_seconds=config.observer_cooldown_seconds,
                baseline_update_interval=config.observer_baseline_update_seconds,
            )
        )

        _market_observer.register_observer(
            KeyLevelObserver(
                atr_factor=config.observer_key_level_atr_factor,
                cooldown_seconds=config.observer_cooldown_seconds,
            )
        )

        # Register compression observer (Phase 01 - Observer Enhancements)
        if config.observer_compression_enabled:
            _market_observer.register_observer(
                VolatilityCompressionObserver(
                    bb_threshold=config.observer_compression_bb_threshold,
                    atr_threshold=config.observer_compression_atr_threshold,
                    min_bars=config.observer_compression_min_bars,
                    cooldown_seconds=config.observer_cooldown_seconds,
                )
            )

        # Enable aggregation (Phase 02 - Observer Enhancements)
        if config.observer_aggregation_enabled:
            _market_observer.enable_aggregation(
                window_size_seconds=config.observer_aggregation_window_seconds,
                dedup_enabled=True,
                dedup_window_seconds=config.observer_dedup_window_seconds,
                correlation_window_seconds=config.observer_correlation_window_seconds,
            )

        logger.info("MarketObserver initialized with default observers")

    return _market_observer


def reset_market_observer():
    """Reset the singleton instance (for testing)."""
    global _market_observer
    _market_observer = None
