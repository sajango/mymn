"""Observer telemetry for metrics, latency tracking, and health monitoring.

Zero external dependencies - uses only dataclasses and standard library.
Provides MetricsCollector, LatencyTracer, and HealthChecker classes.

Phase 03 - Observer Enhancements:
- Counters: events_processed, errors, signals_generated
- Gauges: queue_depth, active_observers, memory_usage
- Histograms: processing_latency_ms with percentiles
- Health checks: error rate, latency, event loss
"""

import logging
import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricsCollector:
    """Lightweight metrics collection using dataclasses.

    Thread-safe counters, gauges, and histograms with JSON export.
    Uses bounded buffers for histograms to prevent memory leaks.

    Example:
        collector = MetricsCollector(name="observer")
        collector.increment("events_processed")
        collector.set_gauge("active_observers", 3)
        collector.record("latency_ms", 1.5)
        summary = collector.get_summary()
    """

    name: str
    counters: Dict[str, int] = field(default_factory=dict)
    gauges: Dict[str, float] = field(default_factory=dict)
    histograms: Dict[str, List[float]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _histogram_max_size: int = field(default=1000, repr=False)

    def increment(
        self, metric: str, value: int = 1, tags: Optional[Dict[str, Any]] = None
    ):
        """Increment counter.

        Args:
            metric: Counter name
            value: Increment amount (default 1)
            tags: Optional tags for metric key
        """
        key = self._make_key(metric, tags)
        with self._lock:
            self.counters[key] = self.counters.get(key, 0) + value

    def decrement(
        self, metric: str, value: int = 1, tags: Optional[Dict[str, Any]] = None
    ):
        """Decrement counter.

        Args:
            metric: Counter name
            value: Decrement amount (default 1)
            tags: Optional tags for metric key
        """
        self.increment(metric, -value, tags)

    def set_gauge(
        self, metric: str, value: float, tags: Optional[Dict[str, Any]] = None
    ):
        """Set gauge value.

        Args:
            metric: Gauge name
            value: Current value
            tags: Optional tags for metric key
        """
        key = self._make_key(metric, tags)
        with self._lock:
            self.gauges[key] = value

    def record(
        self, metric: str, value: float, tags: Optional[Dict[str, Any]] = None
    ):
        """Record histogram value.

        Args:
            metric: Histogram name
            value: Value to record
            tags: Optional tags for metric key
        """
        key = self._make_key(metric, tags)
        with self._lock:
            if key not in self.histograms:
                self.histograms[key] = []

            hist = self.histograms[key]
            hist.append(value)

            # Trim oldest values if exceeds max size
            if len(hist) > self._histogram_max_size:
                self.histograms[key] = hist[-self._histogram_max_size :]

    @staticmethod
    def _make_key(metric: str, tags: Optional[Dict[str, Any]]) -> str:
        """Create metric key with tags.

        Args:
            metric: Base metric name
            tags: Optional tags dictionary

        Returns:
            Formatted key like "metric{tag1=val1,tag2=val2}"
        """
        if not tags:
            return metric
        tags_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{metric}{{{tags_str}}}"

    def get_counter(
        self, metric: str, tags: Optional[Dict[str, Any]] = None
    ) -> int:
        """Get current counter value.

        Args:
            metric: Counter name
            tags: Optional tags

        Returns:
            Current counter value (0 if not exists)
        """
        key = self._make_key(metric, tags)
        with self._lock:
            return self.counters.get(key, 0)

    def get_gauge(
        self, metric: str, tags: Optional[Dict[str, Any]] = None
    ) -> float:
        """Get current gauge value.

        Args:
            metric: Gauge name
            tags: Optional tags

        Returns:
            Current gauge value (0.0 if not exists)
        """
        key = self._make_key(metric, tags)
        with self._lock:
            return self.gauges.get(key, 0.0)

    def get_histogram_stats(
        self, metric: str, tags: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get histogram statistics.

        Args:
            metric: Histogram name
            tags: Optional tags

        Returns:
            Dict with count, min, max, avg, p50, p95, p99
        """
        key = self._make_key(metric, tags)
        with self._lock:
            values = list(self.histograms.get(key, []))

        if not values:
            return {"count": 0}

        sorted_values = sorted(values)
        n = len(sorted_values)

        # Calculate percentile indices (handle edge cases)
        p50_idx = min(int(n * 0.50), n - 1)
        p95_idx = min(int(n * 0.95), n - 1)
        p99_idx = min(int(n * 0.99), n - 1)

        return {
            "count": n,
            "min": round(min(values), 3),
            "max": round(max(values), 3),
            "avg": round(statistics.mean(values), 3),
            "p50": round(sorted_values[p50_idx], 3),
            "p95": round(sorted_values[p95_idx], 3),
            "p99": round(sorted_values[p99_idx], 3),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get complete metrics summary as JSON-serializable dict.

        Returns:
            Dict with name, timestamp, counters, gauges, histograms
        """
        with self._lock:
            counters_copy = dict(self.counters)
            gauges_copy = dict(self.gauges)
            histogram_keys = list(self.histograms.keys())

        histogram_stats = {}
        for key in histogram_keys:
            histogram_stats[key] = self.get_histogram_stats(key)

        return {
            "name": self.name,
            "timestamp": time.time(),
            "counters": counters_copy,
            "gauges": gauges_copy,
            "histograms": histogram_stats,
        }

    def reset(self):
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self.counters.clear()
            self.gauges.clear()
            self.histograms.clear()


class LatencyTracer:
    """Context manager for latency measurement.

    Records elapsed time to histogram on exit. Uses nanosecond precision.

    Example:
        with LatencyTracer(collector, "processing_latency_ms"):
            # ... work ...
        # elapsed time automatically recorded

        # Or access elapsed during execution:
        with LatencyTracer(collector, "processing_latency_ms") as tracer:
            # ... work ...
            if tracer.elapsed_ms > 100:
                logger.warning("Slow operation")
    """

    def __init__(
        self,
        collector: MetricsCollector,
        metric_name: str,
        tags: Optional[Dict[str, Any]] = None,
    ):
        """Initialize tracer.

        Args:
            collector: MetricsCollector to record to
            metric_name: Histogram metric name
            tags: Optional metric tags
        """
        self.collector = collector
        self.metric_name = metric_name
        self.tags = tags
        self._start_ns: Optional[int] = None
        self._elapsed_ms: float = 0.0

    def __enter__(self) -> "LatencyTracer":
        """Start timing."""
        self._start_ns = time.time_ns()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Record elapsed time."""
        if self._start_ns is not None:
            elapsed_ns = time.time_ns() - self._start_ns
            self._elapsed_ms = elapsed_ns / 1_000_000
            self.collector.record(self.metric_name, self._elapsed_ms, self.tags)
        return False  # Don't suppress exceptions

    @property
    def elapsed_ms(self) -> float:
        """Get elapsed time so far (for inspection during execution).

        Returns:
            Elapsed milliseconds since __enter__
        """
        if self._start_ns is None:
            return 0.0
        return (time.time_ns() - self._start_ns) / 1_000_000


@dataclass
class HealthStatus:
    """Observer health status.

    Attributes:
        healthy: Overall health (True if critical checks pass)
        status: "healthy", "degraded", or "unhealthy"
        error_rate: Current error rate (0-1)
        avg_latency_ms: Average processing latency
        checks: Individual check results
        message: Human-readable status message
    """

    healthy: bool
    status: str
    error_rate: float
    avg_latency_ms: float
    checks: Dict[str, bool] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "healthy": self.healthy,
            "status": self.status,
            "error_rate": self.error_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "checks": self.checks,
            "message": self.message,
        }


class HealthChecker:
    """Check observer health based on metrics.

    Thresholds:
    - Error rate < 1%: healthy
    - Error rate < 5%: degraded
    - Error rate >= 5%: unhealthy
    - Latency < 50ms: healthy

    Example:
        checker = HealthChecker(max_error_rate=0.01, max_latency_ms=50.0)
        status = checker.check(metrics_collector)
        if not status.healthy:
            alert(status.message)
    """

    def __init__(
        self,
        max_error_rate: float = 0.01,
        max_latency_ms: float = 50.0,
        degraded_error_rate: float = 0.05,
    ):
        """Initialize health checker.

        Args:
            max_error_rate: Maximum acceptable error rate (default 1%)
            max_latency_ms: Maximum acceptable latency (default 50ms)
            degraded_error_rate: Error rate threshold for degraded (default 5%)
        """
        self.max_error_rate = max_error_rate
        self.max_latency_ms = max_latency_ms
        self.degraded_error_rate = degraded_error_rate

    def check(self, metrics: MetricsCollector) -> HealthStatus:
        """Check health based on collected metrics.

        Args:
            metrics: MetricsCollector with observer metrics

        Returns:
            HealthStatus with overall status and individual checks
        """
        summary = metrics.get_summary()
        counters = summary.get("counters", {})
        histograms = summary.get("histograms", {})

        checks = {}

        # Check 1: Error rate
        total_processed = counters.get("events_processed", 0)
        total_errors = counters.get("errors", 0)
        error_rate = total_errors / max(total_processed, 1)
        checks["error_rate"] = error_rate < self.max_error_rate

        # Check 2: Latency
        latency_stats = histograms.get("processing_latency_ms", {})
        avg_latency = latency_stats.get("avg", 0.0)
        checks["latency"] = avg_latency < self.max_latency_ms

        # Check 3: Event loss (should always be 0)
        event_loss = counters.get("event_loss", 0)
        checks["event_loss"] = event_loss == 0

        # Determine overall status
        all_pass = all(checks.values())
        critical_pass = checks.get("error_rate", True) and checks.get(
            "event_loss", True
        )

        if all_pass:
            status = "healthy"
            healthy = True
            message = "All checks passed"
        elif critical_pass:
            status = "degraded"
            healthy = True
            failed = [k for k, v in checks.items() if not v]
            message = f"Non-critical checks failed: {failed}"
        else:
            status = "unhealthy"
            healthy = False
            failed = [k for k, v in checks.items() if not v]
            message = f"Critical checks failed: {failed}"

        return HealthStatus(
            healthy=healthy,
            status=status,
            error_rate=round(error_rate, 4),
            avg_latency_ms=round(avg_latency, 3),
            checks=checks,
            message=message,
        )


# Singleton metrics collector for observer module
_observer_metrics: Optional[MetricsCollector] = None
_metrics_lock = threading.Lock()


def get_observer_metrics() -> MetricsCollector:
    """Get or create observer metrics singleton.

    Returns:
        Shared MetricsCollector instance for observer module
    """
    global _observer_metrics
    with _metrics_lock:
        if _observer_metrics is None:
            _observer_metrics = MetricsCollector(name="observer")
    return _observer_metrics


def reset_observer_metrics():
    """Reset observer metrics singleton (for testing)."""
    global _observer_metrics
    with _metrics_lock:
        _observer_metrics = None
