"""Tests for Session/Wave Performance Modifiers (Phase 02).

Tests SessionWaveModifiers dataclass, modifier calculations, and SignalFilter integration.
"""

import gc
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Mock MetaTrader5 before any imports that might need it
sys.modules['MetaTrader5'] = MagicMock()

from src.adaptive_confidence import (
    AdaptiveConfidenceManager,
    SessionWaveModifiers,
    get_adaptive_confidence_manager,
)
from src.database import Database
from src.signal_filter import (
    FilterResult,
    FilterReason,
    SignalConsistencyFilter,
)
from src.signal_parser import (
    MarketRegime,
    SessionContext,
    Signal,
    SignalAction,
    TakeProfit,
    TradingSignal,
    WaveAnalysis,
)


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for testing."""
    db_path = tmp_path / "test_modifiers.db"
    db = Database(db_path)
    yield db
    gc.collect()


@pytest.fixture
def mock_config():
    """Create mock config with modifier settings."""
    config = MagicMock()
    # Adaptive settings
    config.adaptive_threshold_enabled = True
    config.adaptive_modifiers_enabled = True
    config.adaptive_cache_ttl_minutes = 60
    config.adaptive_min_trades = 50
    config.adaptive_invalidation_trades = 50
    # Modifier settings
    config.session_modifier_max = 15
    config.session_modifier_min = -20
    config.wave_modifier_max = 15
    config.wave_modifier_min = -20
    config.modifier_min_sample_size = 10
    # Confidence thresholds
    config.confidence_threshold = 50
    config.confidence_full_position = 75
    config.direction_change_min_confidence = 80
    config.direction_change_cooldown_minutes = 60
    config.rapid_flip_threshold_minutes = 30
    return config


@pytest.fixture
def manager(temp_db, mock_config):
    """Create AdaptiveConfidenceManager with temp database and mock config."""
    return AdaptiveConfidenceManager(db=temp_db, config=mock_config)


def create_test_signal(
    confidence: int = 70,
    session: str = "london",
    wave: str = "wave_3",
    regime: str = "trending_strong",
    action: str = "BUY",
) -> TradingSignal:
    """Helper to create test signals with session/wave attributes."""
    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction(action),
            confidence=confidence,
            entry_price=2650.0,
            stop_loss=2640.0,
            take_profits=[
                TakeProfit(level="TP1", price=2660.0, close_percent=50),
                TakeProfit(level="TP2", price=2670.0, close_percent=50),
            ],
        ),
        session_context=SessionContext(
            current_session=session,
            session_quality="high",
            session_modifier=0,
        ),
        wave_analysis=WaveAnalysis(
            h4_trend="bullish",
            current_wave="wave_3",
            wave_position=wave,
        ),
        market_regime=MarketRegime(
            classification=regime,
            trend_direction="bullish",
            trend_strength="strong",
            volatility_regime="normal",
        ),
    )


# =============================================================================
# SessionWaveModifiers Dataclass Tests
# =============================================================================


class TestSessionWaveModifiers:
    """Tests for SessionWaveModifiers dataclass."""

    def test_default_values(self):
        """Test default modifier values are zero."""
        modifiers = SessionWaveModifiers()
        assert modifiers.session_modifier == 0
        assert modifiers.wave_modifier == 0
        assert modifiers.regime_modifier == 0
        assert modifiers.combined_modifier == 0

    def test_bounds_clamping_session_max(self):
        """Test session modifier clamped to +15."""
        modifiers = SessionWaveModifiers(session_modifier=30)
        assert modifiers.session_modifier == 15

    def test_bounds_clamping_session_min(self):
        """Test session modifier clamped to -20."""
        modifiers = SessionWaveModifiers(session_modifier=-30)
        assert modifiers.session_modifier == -20

    def test_bounds_clamping_wave_max(self):
        """Test wave modifier clamped to +15."""
        modifiers = SessionWaveModifiers(wave_modifier=25)
        assert modifiers.wave_modifier == 15

    def test_bounds_clamping_wave_min(self):
        """Test wave modifier clamped to -20."""
        modifiers = SessionWaveModifiers(wave_modifier=-25)
        assert modifiers.wave_modifier == -20

    def test_bounds_clamping_regime_max(self):
        """Test regime modifier clamped to +10."""
        modifiers = SessionWaveModifiers(regime_modifier=20)
        assert modifiers.regime_modifier == 10

    def test_bounds_clamping_regime_min(self):
        """Test regime modifier clamped to -15."""
        modifiers = SessionWaveModifiers(regime_modifier=-25)
        assert modifiers.regime_modifier == -15

    def test_combined_modifier_calculation(self):
        """Test combined modifier is sum of individual modifiers."""
        modifiers = SessionWaveModifiers(
            session_modifier=10,
            wave_modifier=5,
            regime_modifier=5,
        )
        assert modifiers.combined_modifier == 20

    def test_combined_modifier_clamping_max(self):
        """Test combined modifier clamped to +25."""
        modifiers = SessionWaveModifiers(
            session_modifier=15,
            wave_modifier=15,
            regime_modifier=10,
        )
        # Sum would be 40, clamped to 25
        assert modifiers.combined_modifier == 25

    def test_combined_modifier_clamping_min(self):
        """Test combined modifier clamped to -30."""
        modifiers = SessionWaveModifiers(
            session_modifier=-20,
            wave_modifier=-20,
            regime_modifier=-15,
        )
        # Sum would be -55, clamped to -30
        assert modifiers.combined_modifier == -30

    def test_combined_with_mixed_modifiers(self):
        """Test combined modifier with positive and negative values."""
        modifiers = SessionWaveModifiers(
            session_modifier=10,
            wave_modifier=-5,
            regime_modifier=0,
        )
        assert modifiers.combined_modifier == 5


# =============================================================================
# Modifier Calculation Tests
# =============================================================================


class TestModifierCalculation:
    """Tests for modifier calculation methods."""

    def test_calculate_session_modifier_high_win_rate(self, manager):
        """Test session modifier for >65% win rate."""
        modifier = manager._calculate_session_modifier(70)
        assert modifier == 10

    def test_calculate_session_modifier_above_average(self, manager):
        """Test session modifier for 55-65% win rate."""
        modifier = manager._calculate_session_modifier(60)
        assert modifier == 5

    def test_calculate_session_modifier_neutral(self, manager):
        """Test session modifier for 45-55% win rate."""
        modifier = manager._calculate_session_modifier(50)
        assert modifier == 0

    def test_calculate_session_modifier_below_average(self, manager):
        """Test session modifier for 35-45% win rate."""
        modifier = manager._calculate_session_modifier(40)
        assert modifier == -10

    def test_calculate_session_modifier_poor(self, manager):
        """Test session modifier for <35% win rate."""
        modifier = manager._calculate_session_modifier(30)
        assert modifier == -15

    def test_calculate_wave_modifier_high_win_rate(self, manager):
        """Test wave modifier for >65% win rate."""
        modifier = manager._calculate_wave_modifier(70)
        assert modifier == 10

    def test_calculate_wave_modifier_below_average(self, manager):
        """Test wave modifier for 35-45% win rate."""
        modifier = manager._calculate_wave_modifier(40)
        assert modifier == -10

    def test_calculate_regime_modifier_high_win_rate(self, manager):
        """Test regime modifier for >65% win rate."""
        modifier = manager._calculate_regime_modifier(70)
        assert modifier == 10

    def test_calculate_regime_modifier_poor(self, manager):
        """Test regime modifier for <35% win rate."""
        modifier = manager._calculate_regime_modifier(30)
        assert modifier == -15


# =============================================================================
# get_session_wave_modifiers Tests
# =============================================================================


class TestGetSessionWaveModifiers:
    """Tests for get_session_wave_modifiers method."""

    def test_returns_zero_when_disabled(self, manager, mock_config):
        """Test returns zero modifiers when disabled."""
        mock_config.adaptive_modifiers_enabled = False

        modifiers = manager.get_session_wave_modifiers(
            session="london",
            wave="wave_3",
            regime="trending",
        )

        assert modifiers.combined_modifier == 0

    def test_returns_zero_for_unknown_session(self, manager):
        """Test returns zero for unknown session."""
        with patch.object(
            manager.calibration_analyzer,
            'analyze_by_session',
            return_value={"london": {"total": 15, "win_rate": 70}}
        ):
            modifiers = manager.get_session_wave_modifiers(
                session="unknown_session",
                wave=None,
                regime=None,
            )
            assert modifiers.session_modifier == 0

    def test_returns_zero_below_min_sample_size(self, manager, mock_config):
        """Test returns zero when sample size below minimum."""
        mock_config.modifier_min_sample_size = 10

        with patch.object(
            manager.calibration_analyzer,
            'analyze_by_session',
            return_value={"london": {"total": 5, "win_rate": 70}}  # Only 5 trades
        ):
            modifiers = manager.get_session_wave_modifiers(
                session="london",
                wave=None,
                regime=None,
            )
            assert modifiers.session_modifier == 0

    def test_calculates_session_modifier_with_sufficient_data(self, manager, mock_config):
        """Test calculates session modifier with sufficient trades."""
        mock_config.modifier_min_sample_size = 10

        with patch.object(
            manager.calibration_analyzer,
            'analyze_by_session',
            return_value={"london": {"total": 15, "win_rate": 70}}
        ), patch.object(
            manager.calibration_analyzer,
            'analyze_by_wave',
            return_value={}
        ), patch.object(
            manager.calibration_analyzer,
            'analyze_by_regime',
            return_value={}
        ):
            modifiers = manager.get_session_wave_modifiers(
                session="london",
                wave=None,
                regime=None,
            )
            assert modifiers.session_modifier == 10  # 70% win rate = +10
            assert modifiers.session_sample_size == 15

    def test_calculates_combined_modifiers(self, manager, mock_config):
        """Test calculates combined modifiers from all categories."""
        mock_config.modifier_min_sample_size = 10

        with patch.object(
            manager.calibration_analyzer,
            'analyze_by_session',
            return_value={"london": {"total": 15, "win_rate": 70}}  # +10
        ), patch.object(
            manager.calibration_analyzer,
            'analyze_by_wave',
            return_value={"wave_3": {"total": 12, "win_rate": 60}}  # +5
        ), patch.object(
            manager.calibration_analyzer,
            'analyze_by_regime',
            return_value={"trending": {"total": 20, "win_rate": 40}}  # -10
        ):
            modifiers = manager.get_session_wave_modifiers(
                session="london",
                wave="wave_3",
                regime="trending",
            )
            assert modifiers.session_modifier == 10
            assert modifiers.wave_modifier == 5
            assert modifiers.regime_modifier == -10
            assert modifiers.combined_modifier == 5  # 10 + 5 + (-10)

    def test_handles_none_parameters(self, manager):
        """Test handles None parameters gracefully."""
        modifiers = manager.get_session_wave_modifiers(
            session=None,
            wave=None,
            regime=None,
        )
        assert modifiers.combined_modifier == 0

    def test_case_insensitive_session_matching(self, manager, mock_config):
        """Test session matching is case insensitive."""
        mock_config.modifier_min_sample_size = 10

        with patch.object(
            manager.calibration_analyzer,
            'analyze_by_session',
            return_value={"london": {"total": 15, "win_rate": 70}}
        ), patch.object(
            manager.calibration_analyzer,
            'analyze_by_wave',
            return_value={}
        ), patch.object(
            manager.calibration_analyzer,
            'analyze_by_regime',
            return_value={}
        ):
            modifiers = manager.get_session_wave_modifiers(
                session="LONDON",  # Uppercase
                wave=None,
                regime=None,
            )
            assert modifiers.session_modifier == 10


# =============================================================================
# SignalFilter Integration Tests
# =============================================================================


class TestSignalFilterModifierIntegration:
    """Tests for SignalFilter integration with modifiers."""

    def test_filter_result_includes_modifier_info(self, temp_db, mock_config):
        """Test FilterResult includes modifier information."""
        with patch('src.signal_filter.get_settings', return_value=mock_config), \
             patch('src.signal_filter.get_adaptive_confidence_manager') as mock_get_manager:

            mock_manager = MagicMock()
            mock_manager.get_session_wave_modifiers.return_value = SessionWaveModifiers(
                session_modifier=10,
                wave_modifier=5,
                regime_modifier=0,
            )
            mock_get_manager.return_value = mock_manager

            signal_filter = SignalConsistencyFilter(db=temp_db)
            signal = create_test_signal(confidence=60)

            result = signal_filter.check(signal)

            assert result.original_confidence == 60
            assert result.adjusted_confidence == 75  # 60 + 15
            assert result.modifier_applied == 15

    def test_modifier_disabled_keeps_original_confidence(self, temp_db, mock_config):
        """Test modifiers disabled keeps original confidence."""
        mock_config.adaptive_modifiers_enabled = False

        with patch('src.signal_filter.get_settings', return_value=mock_config):
            signal_filter = SignalConsistencyFilter(db=temp_db)
            signal = create_test_signal(confidence=60)

            result = signal_filter.check(signal)

            assert result.original_confidence == 60
            assert result.adjusted_confidence == 60
            assert result.modifier_applied == 0

    def test_negative_modifier_reduces_confidence(self, temp_db, mock_config):
        """Test negative modifier reduces confidence."""
        with patch('src.signal_filter.get_settings', return_value=mock_config), \
             patch('src.signal_filter.get_adaptive_confidence_manager') as mock_get_manager:

            mock_manager = MagicMock()
            mock_manager.get_session_wave_modifiers.return_value = SessionWaveModifiers(
                session_modifier=-15,
                wave_modifier=-10,
                regime_modifier=0,
            )
            mock_get_manager.return_value = mock_manager

            signal_filter = SignalConsistencyFilter(db=temp_db)
            signal = create_test_signal(confidence=70)

            result = signal_filter.check(signal)

            assert result.original_confidence == 70
            assert result.adjusted_confidence == 45  # 70 - 25
            assert result.modifier_applied == -25

    def test_confidence_clamped_to_zero_minimum(self, temp_db, mock_config):
        """Test adjusted confidence doesn't go below 0."""
        with patch('src.signal_filter.get_settings', return_value=mock_config), \
             patch('src.signal_filter.get_adaptive_confidence_manager') as mock_get_manager:

            mock_manager = MagicMock()
            mock_manager.get_session_wave_modifiers.return_value = SessionWaveModifiers(
                session_modifier=-20,
                wave_modifier=-20,
                regime_modifier=-15,
            )
            mock_get_manager.return_value = mock_manager

            signal_filter = SignalConsistencyFilter(db=temp_db)
            signal = create_test_signal(confidence=20)

            result = signal_filter.check(signal)

            assert result.original_confidence == 20
            assert result.adjusted_confidence == 0  # Clamped to 0
            assert result.modifier_applied == -30  # Clamped combined

    def test_confidence_clamped_to_hundred_maximum(self, temp_db, mock_config):
        """Test adjusted confidence doesn't exceed 100."""
        with patch('src.signal_filter.get_settings', return_value=mock_config), \
             patch('src.signal_filter.get_adaptive_confidence_manager') as mock_get_manager:

            mock_manager = MagicMock()
            mock_manager.get_session_wave_modifiers.return_value = SessionWaveModifiers(
                session_modifier=15,
                wave_modifier=15,
                regime_modifier=10,
            )
            mock_get_manager.return_value = mock_manager

            signal_filter = SignalConsistencyFilter(db=temp_db)
            signal = create_test_signal(confidence=90)

            result = signal_filter.check(signal)

            assert result.original_confidence == 90
            assert result.adjusted_confidence == 100  # Clamped to 100

    def test_modifier_applied_before_reversal_check(self, temp_db, mock_config):
        """Test modifier is applied before reversal confidence check."""
        with patch('src.signal_filter.get_settings', return_value=mock_config), \
             patch('src.signal_filter.get_adaptive_confidence_manager') as mock_get_manager:

            mock_manager = MagicMock()
            mock_manager.get_session_wave_modifiers.return_value = SessionWaveModifiers(
                session_modifier=10,
                wave_modifier=10,
                regime_modifier=0,
            )
            mock_get_manager.return_value = mock_manager

            # Add a previous signal to trigger reversal check (use TradingSignal object)
            previous_signal = create_test_signal(confidence=75, action="SELL")
            temp_db.save_signal(previous_signal)

            signal_filter = SignalConsistencyFilter(db=temp_db)
            # Signal with 60% confidence would fail 80% reversal threshold
            # But with +20 modifier, becomes 80% and should pass (if after cooldown)
            signal = create_test_signal(confidence=60, action="BUY")

            result = signal_filter.check(signal)

            # Verify modifier was applied
            assert result.original_confidence == 60
            assert result.adjusted_confidence == 80  # 60 + 20
            assert result.modifier_applied == 20

    def test_modifier_error_continues_with_original_confidence(self, temp_db, mock_config):
        """Test continues with original confidence on modifier error."""
        with patch('src.signal_filter.get_settings', return_value=mock_config), \
             patch('src.signal_filter.get_adaptive_confidence_manager') as mock_get_manager:

            mock_get_manager.side_effect = Exception("Modifier calculation failed")

            signal_filter = SignalConsistencyFilter(db=temp_db)
            signal = create_test_signal(confidence=70)

            result = signal_filter.check(signal)

            # Should continue with original confidence
            assert result.passed is True


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestModifierEdgeCases:
    """Tests for edge cases in modifier calculation."""

    def test_boundary_win_rate_65_percent(self, manager):
        """Test boundary condition at 65% win rate."""
        modifier = manager._calculate_session_modifier(65)
        assert modifier == 5  # Should be "above average" not "high"

    def test_boundary_win_rate_55_percent(self, manager):
        """Test boundary condition at 55% win rate."""
        modifier = manager._calculate_session_modifier(55)
        assert modifier == 0  # Should be "neutral" not "above average"

    def test_boundary_win_rate_45_percent(self, manager):
        """Test boundary condition at 45% win rate."""
        modifier = manager._calculate_session_modifier(45)
        assert modifier == -10  # Should be "below average" not "neutral"

    def test_boundary_win_rate_35_percent(self, manager):
        """Test boundary condition at 35% win rate."""
        modifier = manager._calculate_session_modifier(35)
        assert modifier == -15  # Should be "poor" not "below average"

    def test_zero_win_rate(self, manager):
        """Test zero win rate returns maximum penalty."""
        modifier = manager._calculate_session_modifier(0)
        assert modifier == -15

    def test_hundred_win_rate(self, manager):
        """Test 100% win rate returns maximum bonus."""
        modifier = manager._calculate_session_modifier(100)
        assert modifier == 10

    def test_signal_without_session_context(self, temp_db, mock_config):
        """Test signal without session context."""
        with patch('src.signal_filter.get_settings', return_value=mock_config), \
             patch('src.signal_filter.get_adaptive_confidence_manager') as mock_get_manager:

            mock_manager = MagicMock()
            mock_manager.get_session_wave_modifiers.return_value = SessionWaveModifiers()
            mock_get_manager.return_value = mock_manager

            signal_filter = SignalConsistencyFilter(db=temp_db)
            signal = TradingSignal(
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol="XAUUSD",
                signal=Signal(
                    action=SignalAction.BUY,
                    confidence=70,
                    entry_price=2650.0,
                    stop_loss=2640.0,
                    take_profits=[TakeProfit(level="TP1", price=2660.0, close_percent=100)],
                ),
                # No session_context, wave_analysis, or market_regime
            )

            result = signal_filter.check(signal)

            # Should handle gracefully
            assert result.passed is True
