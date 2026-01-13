"""Performance benchmarks for observer enhancements - Phase 05.

Validates performance targets:
- Observer check cycle: < 5ms
- Event aggregation: < 1ms
- Telemetry overhead: < 0.5ms
- Event persistence: < 5ms (batched)
"""

import os
import tempfile
import time
from pathlib import Path

import pytest

from src.observers.base_observer import ObserverEvent, ObserverEventType


# ===== Performance Benchmark Tests =====


class TestObserverCheckLatency:
    """Benchmark observer check cycle latency."""

    def test_compression_observer_check_latency(self):
        """Compression observer check should complete < 5ms."""
        from src.observers.compression_observer import VolatilityCompressionObserver

        observer = VolatilityCompressionObserver()

        # Warm up with 50 iterations
        for i in range(50):
            observer.check({
                "close": 2700 + i,
                "high": 2705,
                "low": 2695,
                "prev_close": 2699,
            })

        # Benchmark 1000 iterations
        start = time.perf_counter()
        iterations = 1000
        for i in range(iterations):
            observer.check({
                "close": 2700,
                "high": 2705,
                "low": 2695,
                "prev_close": 2699,
            })
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nCompression observer check: {avg_ms:.4f}ms avg ({iterations} iterations)")
        assert avg_ms < 5, f"Observer check too slow: {avg_ms:.2f}ms (target: <5ms)"

    def test_volatility_spike_observer_check_latency(self):
        """Volatility spike observer check should complete < 5ms."""
        from src.observers.volatility_observer import VolatilitySpikeObserver

        observer = VolatilitySpikeObserver()

        # Warm up
        for i in range(50):
            observer.check({
                "atr_ratio": 1.5 + (i % 10) * 0.1,
                "current_price": 2700,
            })

        # Benchmark
        start = time.perf_counter()
        iterations = 1000
        for i in range(iterations):
            observer.check({
                "atr_ratio": 2.0,
                "current_price": 2700,
            })
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nVolatility spike observer check: {avg_ms:.4f}ms avg ({iterations} iterations)")
        assert avg_ms < 5, f"Observer check too slow: {avg_ms:.2f}ms (target: <5ms)"

    def test_key_level_observer_check_latency(self):
        """Key level observer check should complete < 5ms."""
        from src.observers.key_level_observer import KeyLevelObserver

        observer = KeyLevelObserver()

        # Warm up
        for i in range(50):
            observer.check({
                "current_price": 2700 + i,
                "key_levels": [2650, 2700, 2750],
            })

        # Benchmark
        start = time.perf_counter()
        iterations = 1000
        for i in range(iterations):
            observer.check({
                "current_price": 2700,
                "key_levels": [2650, 2700, 2750],
            })
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nKey level observer check: {avg_ms:.4f}ms avg ({iterations} iterations)")
        assert avg_ms < 5, f"Observer check too slow: {avg_ms:.2f}ms (target: <5ms)"


class TestEventAggregationLatency:
    """Benchmark event aggregation latency."""

    def test_aggregator_add_event_latency(self):
        """Aggregator add_event should complete < 1ms."""
        from src.observers.event_aggregator import EventAggregator

        aggregator = EventAggregator(dedup_enabled=True)

        # Warm up
        for i in range(100):
            event = ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE,
                timestamp=time.time(),
                data={"ratio": 2.0, "current_price": 2700 + i},
                confidence=0.8,
            )
            aggregator.add_event(event)

        # Benchmark
        start = time.perf_counter()
        iterations = 1000
        for i in range(iterations):
            event = ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE,
                timestamp=time.time(),
                data={"ratio": 2.0, "current_price": 2700 + i},
                confidence=0.8,
            )
            aggregator.add_event(event)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nAggregator add_event: {avg_ms:.4f}ms avg ({iterations} iterations)")
        assert avg_ms < 1, f"Aggregator too slow: {avg_ms:.2f}ms (target: <1ms)"

    def test_duplicate_detector_latency(self):
        """Duplicate detector should complete < 0.5ms."""
        from src.observers.event_aggregator import DuplicateDetector

        detector = DuplicateDetector(dedup_window_seconds=30)

        # Warm up with different events
        for i in range(100):
            event = ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE,
                timestamp=time.time(),
                data={"ratio": 2.0, "current_price": 2700 + i},
                confidence=0.8,
            )
            detector.is_duplicate(event)

        # Benchmark with mixed duplicates and new events
        start = time.perf_counter()
        iterations = 1000
        for i in range(iterations):
            event = ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE,
                timestamp=time.time(),
                data={"ratio": 2.0, "current_price": 2700 + (i % 50)},  # 50 unique, 950 dups
                confidence=0.8,
            )
            detector.is_duplicate(event)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nDuplicate detector check: {avg_ms:.4f}ms avg ({iterations} iterations)")
        assert avg_ms < 0.5, f"Duplicate detector too slow: {avg_ms:.2f}ms (target: <0.5ms)"

    def test_event_correlator_latency(self):
        """Event correlator should complete < 1ms for small event sets."""
        from src.observers.event_aggregator import EventCorrelator

        correlator = EventCorrelator()

        # Create sample events
        base_time = time.time()
        events = [
            ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE,
                timestamp=base_time,
                data={"current_price": 2700},
                confidence=0.8,
            ),
            ObserverEvent(
                event_type=ObserverEventType.KEY_LEVEL_PROXIMITY,
                timestamp=base_time + 1,
                data={"current_price": 2702},
                confidence=0.9,
            ),
            ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_COMPRESSION,
                timestamp=base_time + 2,
                data={"current_price": 2705},
                confidence=0.85,
            ),
        ]

        # Benchmark
        start = time.perf_counter()
        iterations = 1000
        for _ in range(iterations):
            correlator.correlate(events)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nEvent correlator: {avg_ms:.4f}ms avg ({iterations} iterations, 3 events)")
        assert avg_ms < 1, f"Correlator too slow: {avg_ms:.2f}ms (target: <1ms)"


class TestTelemetryOverhead:
    """Benchmark telemetry overhead."""

    def test_metrics_collector_overhead(self):
        """Metrics collector operations should complete < 0.5ms."""
        from src.observers.observer_telemetry import MetricsCollector

        collector = MetricsCollector(name="benchmark")

        # Warm up
        for _ in range(100):
            collector.increment("count")
            collector.set_gauge("gauge", 1.0)
            collector.record("histogram", 10.0)

        # Benchmark combined operations
        start = time.perf_counter()
        iterations = 1000
        for i in range(iterations):
            collector.increment("events_processed")
            collector.set_gauge("active_connections", i)
            collector.record("latency_ms", float(i % 100))
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nMetrics collector (3 ops): {avg_ms:.4f}ms avg ({iterations} iterations)")
        assert avg_ms < 0.5, f"Metrics collector too slow: {avg_ms:.2f}ms (target: <0.5ms)"

    def test_latency_tracer_overhead(self):
        """Latency tracer should add < 0.5ms overhead."""
        from src.observers.observer_telemetry import MetricsCollector, LatencyTracer

        collector = MetricsCollector(name="benchmark")

        # Benchmark tracer with minimal work
        start = time.perf_counter()
        iterations = 1000
        for _ in range(iterations):
            with LatencyTracer(collector, "test_op"):
                pass  # Minimal work inside
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nLatency tracer overhead: {avg_ms:.4f}ms avg ({iterations} iterations)")
        assert avg_ms < 0.5, f"Latency tracer overhead too high: {avg_ms:.2f}ms (target: <0.5ms)"

    def test_health_checker_overhead(self):
        """Health checker should complete quickly."""
        from src.observers.observer_telemetry import MetricsCollector, HealthChecker

        collector = MetricsCollector(name="benchmark")
        checker = HealthChecker()

        # Pre-populate metrics
        for i in range(100):
            collector.increment("events_processed")
            collector.record("processing_latency_ms", float(i % 50))

        # Benchmark health check
        start = time.perf_counter()
        iterations = 1000
        for _ in range(iterations):
            checker.check(collector)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nHealth checker: {avg_ms:.4f}ms avg ({iterations} iterations)")
        assert avg_ms < 0.5, f"Health checker too slow: {avg_ms:.2f}ms (target: <0.5ms)"


class TestEventPersistenceLatency:
    """Benchmark event persistence latency."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.join(tmpdir, "benchmark_events.db")

    def test_event_store_latency_unbatched(self, temp_db_path):
        """EventStore store() should complete < 5ms (unbatched add to buffer)."""
        from src.observers.event_persistence import EventStore

        store = EventStore(db_path=temp_db_path, batch_size=1000)  # Large batch to avoid flush

        # Warm up
        for i in range(50):
            event = ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE,
                timestamp=time.time() + i * 0.001,
                data={"index": i},
                confidence=0.8,
            )
            store.store(event)

        # Benchmark store (buffer add only)
        start = time.perf_counter()
        iterations = 1000
        for i in range(iterations):
            event = ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE,
                timestamp=time.time() + i * 0.001,
                data={"index": i},
                confidence=0.8,
            )
            store.store(event)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nEventStore store (unbatched): {avg_ms:.4f}ms avg ({iterations} iterations)")
        assert avg_ms < 1, f"Store too slow: {avg_ms:.2f}ms (target: <1ms unbatched)"

    def test_event_store_latency_batched(self, temp_db_path):
        """EventStore batch insert should complete < 5ms per event."""
        from src.observers.event_persistence import EventStore

        store = EventStore(db_path=temp_db_path, batch_size=100)

        # Benchmark 1000 events (10 batch flushes)
        start = time.perf_counter()
        iterations = 1000
        for i in range(iterations):
            event = ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE,
                timestamp=time.time() + i * 0.001,
                data={"index": i},
                confidence=0.8,
            )
            store.store(event)
        store.flush()  # Ensure all flushed
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nEventStore store (batched): {avg_ms:.4f}ms avg ({iterations} iterations)")
        assert avg_ms < 5, f"Batched store too slow: {avg_ms:.2f}ms (target: <5ms)"

    def test_event_store_query_latency(self, temp_db_path):
        """EventStore query should complete reasonably fast."""
        from src.observers.event_persistence import EventStore

        store = EventStore(db_path=temp_db_path, batch_size=100)

        # Insert 1000 events
        base_time = time.time()
        for i in range(1000):
            event = ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE if i % 2 == 0 else ObserverEventType.KEY_LEVEL_PROXIMITY,
                timestamp=base_time + i,
                data={"index": i},
                confidence=0.5 + (i % 50) * 0.01,
            )
            store.store(event)
        store.flush()

        # Benchmark query
        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            store.query(
                start_time=base_time,
                end_time=base_time + 500,
                event_types=["volatility_spike"],
                limit=100,
            )
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nEventStore query: {avg_ms:.2f}ms avg ({iterations} iterations)")
        assert avg_ms < 100, f"Query too slow: {avg_ms:.2f}ms (target: <100ms)"

    def test_event_replayer_latency(self, temp_db_path):
        """EventReplayer should iterate events efficiently."""
        from src.observers.event_persistence import EventStore, EventReplayer

        store = EventStore(db_path=temp_db_path, batch_size=100)

        # Insert 500 events
        base_time = time.time()
        for i in range(500):
            event = ObserverEvent(
                event_type=ObserverEventType.VOLATILITY_SPIKE,
                timestamp=base_time + i,
                data={"index": i},
                confidence=0.8,
            )
            store.store(event)
        store.flush()

        replayer = EventReplayer(store)

        # Benchmark replay (no delay)
        start = time.perf_counter()
        events = list(replayer.replay(
            start_time=base_time - 1,
            end_time=base_time + 600,
            speed=0,  # No delay
        ))
        elapsed = time.perf_counter() - start

        assert len(events) == 500
        avg_ms_per_event = (elapsed / len(events)) * 1000
        print(f"\nEventReplayer: {avg_ms_per_event:.4f}ms per event ({len(events)} events)")
        assert avg_ms_per_event < 1, f"Replay too slow: {avg_ms_per_event:.2f}ms per event"


class TestCombinedWorkflow:
    """Benchmark complete observer workflow."""

    def test_full_observer_cycle_latency(self):
        """Complete observer cycle should complete < 10ms total."""
        from src.observers.compression_observer import VolatilityCompressionObserver
        from src.observers.event_aggregator import EventAggregator
        from src.observers.observer_telemetry import MetricsCollector, LatencyTracer

        observer = VolatilityCompressionObserver()
        aggregator = EventAggregator(dedup_enabled=True)
        metrics = MetricsCollector(name="benchmark")

        # Warm up
        for i in range(50):
            with LatencyTracer(metrics, "cycle"):
                result = observer.check({
                    "close": 2700 + i,
                    "high": 2705,
                    "low": 2695,
                    "prev_close": 2699,
                })
                if result:
                    aggregator.add_event(result)
                metrics.increment("cycles")

        # Benchmark complete cycle
        start = time.perf_counter()
        iterations = 1000
        for i in range(iterations):
            with LatencyTracer(metrics, "cycle"):
                result = observer.check({
                    "close": 2700 + (i % 10),
                    "high": 2705,
                    "low": 2695,
                    "prev_close": 2699,
                })
                if result:
                    aggregator.add_event(result)
                metrics.increment("cycles")
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nFull observer cycle: {avg_ms:.4f}ms avg ({iterations} iterations)")
        assert avg_ms < 10, f"Full cycle too slow: {avg_ms:.2f}ms (target: <10ms)"


# ===== Benchmark Summary =====


@pytest.fixture(scope="module", autouse=True)
def benchmark_summary():
    """Print benchmark summary at end."""
    yield
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    print("Target performance metrics:")
    print("  - Observer check cycle: < 5ms")
    print("  - Event aggregation: < 1ms")
    print("  - Telemetry overhead: < 0.5ms")
    print("  - Event persistence: < 5ms (batched)")
    print("=" * 60)
