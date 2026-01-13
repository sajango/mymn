"""Unit tests for market observer functionality (Phase 1).

Tests volatility spike detection, key level proximity, and observer state management.
"""

import sys
import time
from dataclasses import field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock MetaTrader5 before any imports that might need it
sys.modules["MetaTrader5"] = MagicMock()

from src.config import get_settings


class TestObserverStateDataclass:
    """Test ObserverState dataclass initialization and defaults."""

    def test_import_observer_state(self):
        """ObserverState can be imported from main."""
        from src.main import ObserverState

        assert ObserverState is not None

    def test_default_values(self):
        """ObserverState initializes with correct defaults."""
        from src.main import ObserverState

        state = ObserverState()

        assert state.last_triggered_analysis == 0.0
        assert state.in_spike is False
        assert state.spike_start_time == 0.0
        assert state.atr_baseline_m30 == 10.0  # Gold typical
        assert state.key_levels == []
        assert state.last_baseline_update == 0.0
        assert state.last_key_level_update == 0.0

    def test_custom_values(self):
        """ObserverState accepts custom initialization."""
        from src.main import ObserverState

        state = ObserverState(
            last_triggered_analysis=1000.0,
            in_spike=True,
            spike_start_time=900.0,
            atr_baseline_m30=15.0,
            key_levels=[2700.0, 2750.0],
            last_baseline_update=800.0,
            last_key_level_update=700.0,
        )

        assert state.last_triggered_analysis == 1000.0
        assert state.in_spike is True
        assert state.spike_start_time == 900.0
        assert state.atr_baseline_m30 == 15.0
        assert state.key_levels == [2700.0, 2750.0]
        assert state.last_baseline_update == 800.0
        assert state.last_key_level_update == 700.0


class TestObserverConfig:
    """Test observer configuration settings."""

    def test_observer_settings_exist(self):
        """Observer settings are defined in config."""
        settings = get_settings()

        assert hasattr(settings, "observer_enabled")
        assert hasattr(settings, "observer_cooldown_seconds")
        assert hasattr(settings, "observer_spike_threshold")
        assert hasattr(settings, "observer_key_level_atr_factor")
        assert hasattr(settings, "observer_baseline_update_seconds")

    def test_observer_defaults(self):
        """Observer settings have expected default values."""
        settings = get_settings()

        assert settings.observer_enabled is True
        assert settings.observer_cooldown_seconds == 900  # 15 minutes
        assert settings.observer_spike_threshold == 1.8
        assert settings.observer_key_level_atr_factor == 1.0
        assert settings.observer_baseline_update_seconds == 3600  # 1 hour


class TestKeyLevelProximity:
    """Test key level proximity detection logic via KeyLevelObserver (Phase 2).

    Note: Phase 1 methods (_check_key_level_proximity) have been migrated to
    the Phase 2 KeyLevelObserver module. These tests now use the module directly.
    """

    def test_no_levels_returns_false(self):
        """No key levels means no proximity trigger."""
        from src.observers.key_level_observer import KeyLevelObserver

        observer = KeyLevelObserver(atr_factor=1.0, cooldown_seconds=900)
        # No levels set by default

        result = observer.check({"current_price": 2700.0})

        assert result is None

    def test_price_within_buffer_returns_true(self):
        """Price within ATR buffer of level triggers proximity."""
        from src.observers.key_level_observer import KeyLevelObserver

        observer = KeyLevelObserver(atr_factor=1.0, cooldown_seconds=900)
        observer.update_levels([2700.0])
        observer.update_atr_baseline(10.0)  # 10 point ATR

        # Price at 2705, level at 2700, buffer is 10 (1.0x ATR)
        result = observer.check({"current_price": 2705.0})

        assert result is not None
        assert result.data["level"] == 2700.0

    def test_price_outside_buffer_returns_false(self):
        """Price outside ATR buffer does not trigger."""
        from src.observers.key_level_observer import KeyLevelObserver

        observer = KeyLevelObserver(atr_factor=1.0, cooldown_seconds=900)
        observer.update_levels([2700.0])
        observer.update_atr_baseline(10.0)

        # Price at 2720, level at 2700, buffer is 10 - outside range
        result = observer.check({"current_price": 2720.0})

        assert result is None

    def test_multiple_levels_any_match(self):
        """Proximity to any level triggers."""
        from src.observers.key_level_observer import KeyLevelObserver

        observer = KeyLevelObserver(atr_factor=1.0, cooldown_seconds=900)
        observer.update_levels([2650.0, 2700.0, 2750.0])
        observer.update_atr_baseline(10.0)

        # Price near second level
        result = observer.check({"current_price": 2702.0})

        assert result is not None
        assert result.data["level"] == 2700.0


class TestCooldownLogic:
    """Test observer cooldown behavior."""

    def test_cooldown_blocks_trigger(self):
        """Observer respects cooldown period."""
        from src.main import ObserverState

        state = ObserverState(last_triggered_analysis=time.time() - 300)  # 5 min ago

        config = get_settings()
        now = time.time()
        cooldown_remaining = (
            config.observer_cooldown_seconds
            - (now - state.last_triggered_analysis)
        )

        # With 15 min cooldown and 5 min elapsed, should still be in cooldown
        assert cooldown_remaining > 0

    def test_cooldown_expired_allows_trigger(self):
        """Observer allows trigger after cooldown expires."""
        from src.main import ObserverState

        state = ObserverState(
            last_triggered_analysis=time.time() - 1000
        )  # 16+ min ago

        config = get_settings()
        now = time.time()
        cooldown_remaining = (
            config.observer_cooldown_seconds
            - (now - state.last_triggered_analysis)
        )

        # With 15 min (900s) cooldown and 1000s elapsed, should be clear
        assert cooldown_remaining <= 0


class TestSpikeDetectionLogic:
    """Test volatility spike detection logic."""

    def test_spike_ratio_calculation(self):
        """Spike ratio calculated correctly."""
        current_atr = 18.0
        baseline = 10.0

        ratio = current_atr / baseline

        assert ratio == 1.8

    def test_spike_threshold_check(self):
        """Spike threshold determines trigger."""
        config = get_settings()
        threshold = config.observer_spike_threshold  # 1.8

        # Just above threshold
        assert 1.81 > threshold
        # Just below threshold
        assert 1.79 < threshold


class TestOrchestratorObserverState:
    """Test TradingOrchestrator observer state initialization."""

    def test_orchestrator_has_observer_state(self):
        """TradingOrchestrator initializes with observer state."""
        from src.main import ObserverState, TradingOrchestrator

        orchestrator = TradingOrchestrator()

        assert hasattr(orchestrator, "_observer_state")
        assert isinstance(orchestrator._observer_state, ObserverState)

    def test_observer_methods_exist(self):
        """Observer methods are defined on orchestrator.

        Note: Phase 1 methods (_check_volatility_spike, _check_key_level_proximity)
        have been migrated to Phase 2 observer module. Orchestrator now uses
        market_observer property and observer_job for Phase 2 functionality.
        """
        from src.main import TradingOrchestrator

        orchestrator = TradingOrchestrator()

        # Phase 1 legacy methods still present
        assert hasattr(orchestrator, "_get_current_price")
        assert hasattr(orchestrator, "_update_observer_baseline")
        assert hasattr(orchestrator, "_update_key_levels")
        assert hasattr(orchestrator, "_check_observer_conditions")

        # Phase 2 methods
        assert hasattr(orchestrator, "market_observer")
        assert hasattr(orchestrator, "observer_job")
        assert hasattr(orchestrator, "_on_observer_event")


# ============================================================================
# Phase 2: Full Observer Module Tests
# ============================================================================


class TestObserverEventDataclass:
    """Tests for ObserverEvent dataclass (Phase 2)."""

    def test_event_creation(self):
        """Test basic event creation."""
        from src.observers.base_observer import ObserverEvent, ObserverEventType

        event = ObserverEvent(
            event_type=ObserverEventType.VOLATILITY_SPIKE,
            timestamp=time.time(),
            data={"ratio": 2.0},
            confidence=0.8,
        )

        assert event.event_type == ObserverEventType.VOLATILITY_SPIKE
        assert event.data["ratio"] == 2.0
        assert event.confidence == 0.8

    def test_confidence_clamping_high(self):
        """Test confidence is clamped to max 1.0."""
        from src.observers.base_observer import ObserverEvent, ObserverEventType

        event = ObserverEvent(
            event_type=ObserverEventType.VOLATILITY_SPIKE,
            timestamp=time.time(),
            confidence=1.5,
        )
        assert event.confidence == 1.0

    def test_confidence_clamping_low(self):
        """Test confidence is clamped to min 0.0."""
        from src.observers.base_observer import ObserverEvent, ObserverEventType

        event = ObserverEvent(
            event_type=ObserverEventType.KEY_LEVEL_PROXIMITY,
            timestamp=time.time(),
            confidence=-0.5,
        )
        assert event.confidence == 0.0


class TestVolatilitySpikeObserverModule:
    """Tests for VolatilitySpikeObserver module (Phase 2)."""

    def test_init_defaults(self):
        """Test default initialization values."""
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = VolatilitySpikeObserver()

        assert obs.name == "volatility_spike"
        assert obs.spike_threshold == 1.8
        assert obs.cooldown_seconds == 900
        assert obs.enabled is True
        assert obs._in_spike is False

    def test_no_event_below_threshold(self):
        """Test no event when ATR ratio below threshold."""
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = VolatilitySpikeObserver(spike_threshold=1.8)
        obs.set_baseline(10.0)

        result = obs.check({"atr_current": 15.0})

        assert result is None
        assert obs._in_spike is False

    def test_spike_detected(self):
        """Test spike detection when ratio exceeds threshold."""
        from src.observers.base_observer import ObserverEventType
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = VolatilitySpikeObserver(spike_threshold=1.8)
        obs.set_baseline(10.0)

        result = obs.check({"atr_current": 20.0})

        assert result is not None
        assert result.event_type == ObserverEventType.VOLATILITY_SPIKE
        assert result.data["ratio"] == 2.0
        assert obs._in_spike is True

    def test_no_repeat_spike_while_in_state(self):
        """Test no repeat event while already in spike state."""
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = VolatilitySpikeObserver(spike_threshold=1.8, cooldown_seconds=0)
        obs.set_baseline(10.0)

        result1 = obs.check({"atr_current": 20.0})
        assert result1 is not None

        result2 = obs.check({"atr_current": 22.0})
        assert result2 is None

    def test_spike_reset_on_ratio_drop(self):
        """Test spike state resets when ratio drops below threshold."""
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = VolatilitySpikeObserver(spike_threshold=1.8, cooldown_seconds=0)
        obs.set_baseline(10.0)

        obs.check({"atr_current": 20.0})
        assert obs._in_spike is True

        obs.check({"atr_current": 15.0})
        assert obs._in_spike is False

        result = obs.check({"atr_current": 20.0})
        assert result is not None

    def test_cooldown_prevents_trigger(self):
        """Test cooldown prevents immediate re-trigger."""
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = VolatilitySpikeObserver(spike_threshold=1.8, cooldown_seconds=60)
        obs.set_baseline(10.0)

        result1 = obs.check({"atr_current": 20.0})
        assert result1 is not None

        obs._in_spike = False

        result2 = obs.check({"atr_current": 20.0})
        assert result2 is None

    def test_baseline_update(self):
        """Test ATR baseline update from values."""
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = VolatilitySpikeObserver()

        obs.update_baseline([10.0, 12.0, 8.0, 10.0])
        assert obs._atr_baseline == 10.0

    def test_needs_baseline_update(self):
        """Test baseline staleness detection."""
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = VolatilitySpikeObserver(baseline_update_interval=60)
        obs.set_baseline(10.0)

        assert obs.needs_baseline_update() is False

        obs._last_baseline_update = time.time() - 120
        assert obs.needs_baseline_update() is True

    def test_disabled_observer(self):
        """Test disabled observer returns None."""
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = VolatilitySpikeObserver()
        obs.set_baseline(10.0)
        obs.enabled = False

        result = obs.check({"atr_current": 50.0})
        assert result is None


class TestKeyLevelObserverModule:
    """Tests for KeyLevelObserver module (Phase 2)."""

    def test_init_defaults(self):
        """Test default initialization."""
        from src.observers.key_level_observer import KeyLevelObserver

        obs = KeyLevelObserver()

        assert obs.name == "key_level"
        assert obs.atr_factor == 1.0
        assert obs.cooldown_seconds == 900
        assert obs._key_levels == []

    def test_no_event_without_levels(self):
        """Test no event when no levels configured."""
        from src.observers.key_level_observer import KeyLevelObserver

        obs = KeyLevelObserver()

        result = obs.check({"current_price": 2650.0})
        assert result is None

    def test_no_event_outside_buffer(self):
        """Test no event when price outside buffer zone."""
        from src.observers.key_level_observer import KeyLevelObserver

        obs = KeyLevelObserver(atr_factor=1.0)
        obs.update_levels([2700.0])
        obs.update_atr_baseline(10.0)

        result = obs.check({"current_price": 2650.0})
        assert result is None

    def test_proximity_detected(self):
        """Test proximity detection within buffer."""
        from src.observers.base_observer import ObserverEventType
        from src.observers.key_level_observer import KeyLevelObserver

        obs = KeyLevelObserver(atr_factor=1.0, cooldown_seconds=0)
        obs.update_levels([2700.0])
        obs.update_atr_baseline(10.0)

        result = obs.check({"current_price": 2695.0})

        assert result is not None
        assert result.event_type == ObserverEventType.KEY_LEVEL_PROXIMITY
        assert result.data["level"] == 2700.0
        assert result.data["distance"] == 5.0

    def test_per_level_cooldown(self):
        """Test each level has independent cooldown."""
        from src.observers.key_level_observer import KeyLevelObserver

        obs = KeyLevelObserver(atr_factor=1.0, cooldown_seconds=60)
        obs.update_levels([2700.0, 2650.0])
        obs.update_atr_baseline(10.0)

        result1 = obs.check({"current_price": 2695.0})
        assert result1 is not None
        assert result1.data["level"] == 2700.0

        result2 = obs.check({"current_price": 2655.0})
        assert result2 is not None
        assert result2.data["level"] == 2650.0

    def test_same_level_cooldown(self):
        """Test same level respects cooldown."""
        from src.observers.key_level_observer import KeyLevelObserver

        obs = KeyLevelObserver(atr_factor=1.0, cooldown_seconds=60)
        obs.update_levels([2700.0])
        obs.update_atr_baseline(10.0)

        result1 = obs.check({"current_price": 2695.0})
        assert result1 is not None

        result2 = obs.check({"current_price": 2698.0})
        assert result2 is None

    def test_add_remove_level(self):
        """Test adding and removing individual levels."""
        from src.observers.key_level_observer import KeyLevelObserver

        obs = KeyLevelObserver()

        obs.add_level(2700.0)
        obs.add_level(2650.0)
        assert len(obs._key_levels) == 2

        obs.remove_level(2700.0)
        assert obs._key_levels == [2650.0]

    def test_get_nearest_level(self):
        """Test finding nearest level to price."""
        from src.observers.key_level_observer import KeyLevelObserver

        obs = KeyLevelObserver(atr_factor=1.0)
        obs.update_levels([2700.0, 2600.0, 2650.0])
        obs.update_atr_baseline(10.0)

        result = obs.get_nearest_level(2655.0)

        assert result["level"] == 2650.0
        assert result["distance"] == 5.0
        assert result["within_buffer"] is True


class TestMarketObserverModule:
    """Tests for MarketObserver orchestrator module (Phase 2)."""

    def setup_method(self):
        """Reset singleton before each test."""
        from src.observers.market_observer import reset_market_observer

        reset_market_observer()

    def test_init_empty(self):
        """Test initialization with no observers."""
        from src.observers.market_observer import MarketObserver

        obs = MarketObserver()

        assert len(obs._observers) == 0
        assert len(obs._subscribers) == 0
        assert obs._state.events_emitted == 0

    def test_register_observer(self):
        """Test observer registration."""
        from src.observers.market_observer import MarketObserver
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = MarketObserver()
        vol_obs = VolatilitySpikeObserver()

        obs.register_observer(vol_obs)

        assert len(obs._observers) == 1
        assert obs._state.active_observers == 1

    def test_subscribe_callback(self):
        """Test subscriber receives events."""
        from src.observers.market_observer import MarketObserver
        from src.observers.volatility_observer import VolatilitySpikeObserver
        from src.observers.base_observer import ObserverEventType

        obs = MarketObserver()
        vol_obs = VolatilitySpikeObserver(spike_threshold=1.8, cooldown_seconds=0)
        vol_obs.set_baseline(10.0)
        obs.register_observer(vol_obs)

        received_events = []
        obs.subscribe(lambda e: received_events.append(e))

        obs.check_all({"atr_current": 20.0})

        assert len(received_events) == 1
        assert received_events[0].event_type == ObserverEventType.VOLATILITY_SPIKE

    def test_check_all_returns_events(self):
        """Test check_all returns list of triggered events."""
        from src.observers.market_observer import MarketObserver
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = MarketObserver()
        vol_obs = VolatilitySpikeObserver(spike_threshold=1.8, cooldown_seconds=0)
        vol_obs.set_baseline(10.0)
        obs.register_observer(vol_obs)

        events = obs.check_all({"atr_current": 20.0})

        assert len(events) == 1

    def test_get_observer_by_name(self):
        """Test retrieving observer by name."""
        from src.observers.market_observer import MarketObserver
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = MarketObserver()
        vol_obs = VolatilitySpikeObserver()
        obs.register_observer(vol_obs)

        result = obs.get_observer("volatility_spike")
        assert result is vol_obs

        result = obs.get_observer("nonexistent")
        assert result is None

    def test_enable_disable_all(self):
        """Test bulk enable/disable observers."""
        from src.observers.market_observer import MarketObserver
        from src.observers.volatility_observer import VolatilitySpikeObserver
        from src.observers.key_level_observer import KeyLevelObserver

        obs = MarketObserver()
        vol_obs = VolatilitySpikeObserver()
        key_obs = KeyLevelObserver()
        obs.register_observer(vol_obs)
        obs.register_observer(key_obs)

        obs.disable_all()
        assert vol_obs.enabled is False
        assert key_obs.enabled is False

        obs.enable_all()
        assert vol_obs.enabled is True
        assert key_obs.enabled is True

    def test_get_status(self):
        """Test comprehensive status report."""
        from src.observers.market_observer import MarketObserver
        from src.observers.volatility_observer import VolatilitySpikeObserver

        obs = MarketObserver()
        vol_obs = VolatilitySpikeObserver()
        obs.register_observer(vol_obs)

        status = obs.get_status()

        assert status["active_observers"] == 1
        assert status["events_emitted"] == 0
        assert len(status["observers"]) == 1


class TestSchedulerTrigger:
    """Tests for scheduler trigger function (Phase 2)."""

    def test_observer_trigger_interval(self):
        """Test observer trigger is 10 second interval."""
        from src.scheduler import get_observer_trigger

        trigger = get_observer_trigger()

        assert trigger.interval.total_seconds() == 10.0


class TestOrchestratorPhase2Integration:
    """Test TradingOrchestrator Phase 2 observer integration."""

    def test_orchestrator_has_market_observer_property(self):
        """TradingOrchestrator has market_observer lazy property."""
        from src.main import TradingOrchestrator

        orchestrator = TradingOrchestrator()

        assert hasattr(orchestrator, "market_observer")
        assert hasattr(orchestrator, "_market_observer")

    def test_orchestrator_has_observer_job(self):
        """TradingOrchestrator has observer_job method."""
        from src.main import TradingOrchestrator

        orchestrator = TradingOrchestrator()

        assert hasattr(orchestrator, "observer_job")
        assert callable(orchestrator.observer_job)

    def test_orchestrator_has_event_callback(self):
        """TradingOrchestrator has _on_observer_event callback."""
        from src.main import TradingOrchestrator

        orchestrator = TradingOrchestrator()

        assert hasattr(orchestrator, "_on_observer_event")
        assert callable(orchestrator._on_observer_event)
