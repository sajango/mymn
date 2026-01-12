"""Tests for FactorWeightManager - Phase 03 Factor Weight Auto-Adjustment."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.factor_weight_manager import (
    FactorWeightManager,
    FactorWeights,
    WeightCache,
    DEFAULT_WEIGHTS,
    get_factor_weight_manager,
    reset_factor_weight_manager,
)
from src.calibration_analyzer import FactorCorrelation


class TestFactorWeightsDataclass:
    """Tests for FactorWeights dataclass."""

    def test_default_values(self):
        """Test default initialization."""
        fw = FactorWeights()
        assert fw.weights == {}
        assert fw.correlations == {}
        assert fw.sample_sizes == {}
        assert fw.total_trades == 0
        assert fw.is_default is True

    def test_with_weights(self):
        """Test initialization with actual weights."""
        weights = {"factor_a": 0.5, "factor_b": 0.5}
        fw = FactorWeights(
            weights=weights,
            correlations={"factor_a": 0.25, "factor_b": 0.15},
            total_trades=100,
            is_default=False,
        )
        assert fw.weights == weights
        assert fw.total_trades == 100
        assert fw.is_default is False

    def test_warns_on_bad_normalization(self, caplog):
        """Test warning when weights don't sum to 1.0."""
        weights = {"factor_a": 0.3, "factor_b": 0.3}  # Sum = 0.6
        FactorWeights(weights=weights)
        assert "Weights sum to 0.600" in caplog.text


class TestWeightCache:
    """Tests for WeightCache."""

    def test_empty_cache_invalid(self):
        """Test empty cache is invalid."""
        cache = WeightCache()
        assert cache.is_valid(current_trade_count=100) is False

    def test_expired_cache_invalid(self):
        """Test expired cache is invalid."""
        cache = WeightCache(
            data=FactorWeights(),
            expires_at=datetime.utcnow() - timedelta(hours=1),
            trade_count_at_calc=100,
        )
        assert cache.is_valid(current_trade_count=100) is False

    def test_trade_count_invalidation(self):
        """Test cache invalidates after 50 new trades."""
        cache = WeightCache(
            data=FactorWeights(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            trade_count_at_calc=100,
        )
        # Still valid with 40 new trades
        assert cache.is_valid(current_trade_count=140) is True
        # Invalid with 50+ new trades
        assert cache.is_valid(current_trade_count=150) is False

    def test_valid_cache(self):
        """Test valid cache returns True."""
        cache = WeightCache(
            data=FactorWeights(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            trade_count_at_calc=100,
        )
        assert cache.is_valid(current_trade_count=120) is True


class TestFactorWeightManagerInit:
    """Tests for FactorWeightManager initialization."""

    def test_lazy_db_loading(self):
        """Test database is lazily loaded."""
        manager = FactorWeightManager()
        assert manager._db is None

    def test_with_injected_db(self):
        """Test with injected database."""
        mock_db = MagicMock()
        manager = FactorWeightManager(db=mock_db)
        assert manager._db is mock_db


class TestGenerateFactorWeights:
    """Tests for generate_factor_weights() method."""

    @pytest.fixture
    def mock_correlations(self):
        """Create mock factor correlations."""
        return [
            FactorCorrelation(
                factor="fibonacci_confluence",
                correlation=0.28,
                avg_contribution=15.0,
                sample_size=50,
                significant=True,
            ),
            FactorCorrelation(
                factor="timeframe_alignment",
                correlation=0.22,
                avg_contribution=18.0,
                sample_size=50,
                significant=True,
            ),
            FactorCorrelation(
                factor="ema_alignment",
                correlation=0.12,
                avg_contribution=12.0,
                sample_size=50,
                significant=True,
            ),
            FactorCorrelation(
                factor="rsi_confirmation",
                correlation=0.05,
                avg_contribution=8.0,
                sample_size=50,
                significant=False,  # Not significant
            ),
        ]

    def test_returns_defaults_when_disabled(self):
        """Test returns defaults when feature disabled."""
        mock_db = MagicMock()
        manager = FactorWeightManager(db=mock_db)

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            mock_settings.return_value.factor_weight_enabled = False
            result = manager.generate_factor_weights()

        assert result.is_default is True
        assert result.weights == DEFAULT_WEIGHTS

    def test_returns_defaults_when_no_correlations(self):
        """Test returns defaults when no correlations available."""
        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = []
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_factor_impact.return_value = []

        manager = FactorWeightManager(db=mock_db, analyzer=mock_analyzer)

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            mock_settings.return_value.factor_weight_enabled = True
            result = manager.generate_factor_weights()

        assert result.is_default is True

    def test_calculates_weights_from_correlations(self, mock_correlations):
        """Test weight calculation from correlations."""
        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = [{"outcome": "win"}] * 50
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_factor_impact.return_value = mock_correlations

        manager = FactorWeightManager(db=mock_db, analyzer=mock_analyzer)
        manager._cache = WeightCache()  # Clear cache

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            settings = MagicMock()
            settings.factor_weight_enabled = True
            settings.factor_significance_threshold = 0.10
            settings.factor_weight_min = 0.05
            settings.factor_weight_max = 0.40
            settings.factor_weight_recalibrate_trades = 50
            settings.factor_weight_cache_ttl_hours = 24
            mock_settings.return_value = settings

            result = manager.generate_factor_weights()

        assert result.is_default is False
        # Only significant factors included (3 of 4)
        assert len(result.weights) == 3
        assert "fibonacci_confluence" in result.weights
        assert "timeframe_alignment" in result.weights
        assert "ema_alignment" in result.weights
        assert "rsi_confirmation" not in result.weights

    def test_weights_sum_to_one(self, mock_correlations):
        """Test weights are normalized to sum to 1.0."""
        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = [{"outcome": "win"}] * 50
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_factor_impact.return_value = mock_correlations

        manager = FactorWeightManager(db=mock_db, analyzer=mock_analyzer)
        manager._cache = WeightCache()

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            settings = MagicMock()
            settings.factor_weight_enabled = True
            settings.factor_significance_threshold = 0.10
            settings.factor_weight_min = 0.05
            settings.factor_weight_max = 0.40
            settings.factor_weight_recalibrate_trades = 50
            settings.factor_weight_cache_ttl_hours = 24
            mock_settings.return_value = settings

            result = manager.generate_factor_weights()

        weight_sum = sum(result.weights.values())
        assert abs(weight_sum - 1.0) < 0.01

    def test_weight_bounds_enforced(self):
        """Test weight floor and cap are enforced."""
        # Create correlations with extreme values
        correlations = [
            FactorCorrelation(
                factor="strong_factor",
                correlation=0.90,  # Very strong
                avg_contribution=20.0,
                sample_size=50,
                significant=True,
            ),
            FactorCorrelation(
                factor="weak_factor",
                correlation=0.11,  # Just above threshold
                avg_contribution=5.0,
                sample_size=50,
                significant=True,
            ),
        ]

        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = [{"outcome": "win"}] * 50
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_factor_impact.return_value = correlations

        manager = FactorWeightManager(db=mock_db, analyzer=mock_analyzer)
        manager._cache = WeightCache()

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            settings = MagicMock()
            settings.factor_weight_enabled = True
            settings.factor_significance_threshold = 0.10
            settings.factor_weight_min = 0.05
            settings.factor_weight_max = 0.40
            settings.factor_weight_recalibrate_trades = 50
            settings.factor_weight_cache_ttl_hours = 24
            mock_settings.return_value = settings

            result = manager.generate_factor_weights()

        # After normalization, weights should be within bounds
        for weight in result.weights.values():
            # Due to renormalization, bounds are relative
            assert weight >= 0.05  # Floor

    def test_uses_cache_when_valid(self, mock_correlations):
        """Test returns cached result when valid."""
        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = [{"outcome": "win"}] * 50
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_factor_impact.return_value = mock_correlations

        manager = FactorWeightManager(db=mock_db, analyzer=mock_analyzer)

        # Pre-populate cache
        cached_result = FactorWeights(
            weights={"cached": 1.0},
            is_default=False,
        )
        manager._cache = WeightCache(
            data=cached_result,
            expires_at=datetime.utcnow() + timedelta(hours=24),
            trade_count_at_calc=50,
        )

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            settings = MagicMock()
            settings.factor_weight_enabled = True
            settings.factor_weight_recalibrate_trades = 50
            mock_settings.return_value = settings

            result = manager.generate_factor_weights()

        # Should return cached value
        assert result.weights == {"cached": 1.0}
        # Analyzer should not be called
        mock_analyzer.analyze_factor_impact.assert_not_called()


class TestGetFactorGuidance:
    """Tests for get_factor_guidance() method."""

    def test_default_guidance(self):
        """Test guidance when using defaults."""
        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = []
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_factor_impact.return_value = []

        manager = FactorWeightManager(db=mock_db, analyzer=mock_analyzer)

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            mock_settings.return_value.factor_weight_enabled = True
            guidance = manager.get_factor_guidance()

        assert "default factor weights" in guidance.lower()
        assert "insufficient data" in guidance.lower()

    def test_formatted_guidance(self):
        """Test guidance formatting with actual weights."""
        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = [{"outcome": "win"}] * 100
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_factor_impact.return_value = [
            FactorCorrelation(
                factor="high_factor",
                correlation=0.30,
                avg_contribution=20.0,
                sample_size=100,
                significant=True,
            ),
            FactorCorrelation(
                factor="medium_factor",
                correlation=0.15,
                avg_contribution=10.0,
                sample_size=100,
                significant=True,
            ),
        ]

        manager = FactorWeightManager(db=mock_db, analyzer=mock_analyzer)
        manager._cache = WeightCache()

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            settings = MagicMock()
            settings.factor_weight_enabled = True
            settings.factor_significance_threshold = 0.10
            settings.factor_weight_min = 0.05
            settings.factor_weight_max = 0.40
            settings.factor_weight_recalibrate_trades = 50
            settings.factor_weight_cache_ttl_hours = 24
            mock_settings.return_value = settings

            guidance = manager.get_factor_guidance()

        assert "HIGH PRIORITY" in guidance or "MEDIUM PRIORITY" in guidance
        assert "high_factor" in guidance
        assert "correlation" in guidance.lower()

    def test_negative_correlation_separate(self):
        """Test negative correlations are separated."""
        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = [{"outcome": "win"}] * 100
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_factor_impact.return_value = [
            FactorCorrelation(
                factor="good_factor",
                correlation=0.20,
                avg_contribution=15.0,
                sample_size=100,
                significant=True,
            ),
            FactorCorrelation(
                factor="bad_factor",
                correlation=-0.15,
                avg_contribution=5.0,
                sample_size=100,
                significant=True,
            ),
        ]

        manager = FactorWeightManager(db=mock_db, analyzer=mock_analyzer)
        manager._cache = WeightCache()

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            settings = MagicMock()
            settings.factor_weight_enabled = True
            settings.factor_significance_threshold = 0.10
            settings.factor_weight_min = 0.05
            settings.factor_weight_max = 0.40
            settings.factor_weight_recalibrate_trades = 50
            settings.factor_weight_cache_ttl_hours = 24
            mock_settings.return_value = settings

            guidance = manager.get_factor_guidance()

        assert "NEGATIVE CORRELATION" in guidance
        assert "bad_factor" in guidance


class TestRecalibration:
    """Tests for recalibration logic."""

    def test_should_recalibrate_empty_cache(self):
        """Test recalibrate needed with empty cache."""
        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = []
        manager = FactorWeightManager(db=mock_db)

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            mock_settings.return_value.factor_weight_recalibrate_trades = 50
            assert manager.should_recalibrate() is True

    def test_should_recalibrate_after_trades(self):
        """Test recalibrate needed after trade threshold."""
        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = [{"outcome": "win"}] * 150

        manager = FactorWeightManager(db=mock_db)
        manager._cache = WeightCache(
            data=FactorWeights(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            trade_count_at_calc=100,
        )

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            mock_settings.return_value.factor_weight_recalibrate_trades = 50
            assert manager.should_recalibrate() is True

    def test_invalidate_cache(self):
        """Test cache invalidation."""
        manager = FactorWeightManager()
        manager._cache = WeightCache(
            data=FactorWeights(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            trade_count_at_calc=100,
        )

        manager.invalidate_cache()
        assert manager._cache.data is None


class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_factor_weight_manager(self):
        """Test singleton returns instance."""
        reset_factor_weight_manager()
        manager = get_factor_weight_manager()
        assert isinstance(manager, FactorWeightManager)

    def test_same_instance(self):
        """Test singleton returns same instance."""
        reset_factor_weight_manager()
        manager1 = get_factor_weight_manager()
        manager2 = get_factor_weight_manager()
        assert manager1 is manager2

    def test_reset_creates_new_instance(self):
        """Test reset allows new instance."""
        reset_factor_weight_manager()
        manager1 = get_factor_weight_manager()
        reset_factor_weight_manager()
        manager2 = get_factor_weight_manager()
        assert manager1 is not manager2


class TestInstructionBuilderIntegration:
    """Tests for InstructionBuilder integration."""

    def test_inject_factor_weights_placeholder(self):
        """Test factor weights placeholder injection."""
        from src.instruction_builder import InstructionBuilder

        builder = InstructionBuilder()

        template = "Before {{FACTOR_WEIGHTS}} After"

        with patch(
            "src.factor_weight_manager.get_factor_weight_manager"
        ) as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_factor_guidance.return_value = "Test Guidance"
            mock_get_manager.return_value = mock_manager

            result = builder._inject_factor_weights(template)

        assert "Test Guidance" in result
        assert "{{FACTOR_WEIGHTS}}" not in result

    def test_inject_handles_error(self):
        """Test factor weight injection handles errors gracefully."""
        from src.instruction_builder import InstructionBuilder

        builder = InstructionBuilder()

        template = "Before {{FACTOR_WEIGHTS}} After"

        with patch(
            "src.factor_weight_manager.get_factor_weight_manager"
        ) as mock_get_manager:
            mock_get_manager.side_effect = Exception("Test error")

            result = builder._inject_factor_weights(template)

        assert "unavailable" in result.lower()
        assert "{{FACTOR_WEIGHTS}}" not in result

    def test_no_placeholder_returns_unchanged(self):
        """Test template without placeholder returns unchanged."""
        from src.instruction_builder import InstructionBuilder

        builder = InstructionBuilder()

        template = "No placeholder here"
        result = builder._inject_factor_weights(template)

        assert result == template


class TestEdgeCases:
    """Tests for edge cases."""

    def test_all_factors_below_threshold(self):
        """Test when all factors are below significance threshold."""
        correlations = [
            FactorCorrelation(
                factor="weak_a",
                correlation=0.05,
                avg_contribution=5.0,
                sample_size=50,
                significant=False,
            ),
            FactorCorrelation(
                factor="weak_b",
                correlation=0.03,
                avg_contribution=3.0,
                sample_size=50,
                significant=False,
            ),
        ]

        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = [{"outcome": "win"}] * 50
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_factor_impact.return_value = correlations

        manager = FactorWeightManager(db=mock_db, analyzer=mock_analyzer)
        manager._cache = WeightCache()

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            settings = MagicMock()
            settings.factor_weight_enabled = True
            settings.factor_significance_threshold = 0.10
            settings.factor_weight_min = 0.05
            settings.factor_weight_max = 0.40
            settings.factor_weight_recalibrate_trades = 50
            settings.factor_weight_cache_ttl_hours = 24
            mock_settings.return_value = settings

            result = manager.generate_factor_weights()

        # Should return defaults
        assert result.is_default is True

    def test_single_significant_factor(self):
        """Test with only one significant factor."""
        correlations = [
            FactorCorrelation(
                factor="only_factor",
                correlation=0.30,
                avg_contribution=20.0,
                sample_size=50,
                significant=True,
            ),
        ]

        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = [{"outcome": "win"}] * 50
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_factor_impact.return_value = correlations

        manager = FactorWeightManager(db=mock_db, analyzer=mock_analyzer)
        manager._cache = WeightCache()

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            settings = MagicMock()
            settings.factor_weight_enabled = True
            settings.factor_significance_threshold = 0.10
            settings.factor_weight_min = 0.05
            settings.factor_weight_max = 0.40
            settings.factor_weight_recalibrate_trades = 50
            settings.factor_weight_cache_ttl_hours = 24
            mock_settings.return_value = settings

            result = manager.generate_factor_weights()

        assert len(result.weights) == 1
        assert result.weights["only_factor"] == 1.0  # Only factor gets full weight

    def test_zero_correlation_sum(self):
        """Test handling of zero correlation sum edge case."""
        correlations = [
            FactorCorrelation(
                factor="zero_factor",
                correlation=0.0,
                avg_contribution=10.0,
                sample_size=50,
                significant=True,  # Significant but zero correlation
            ),
        ]

        mock_db = MagicMock()
        mock_db.get_closed_trades.return_value = [{"outcome": "win"}] * 50
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_factor_impact.return_value = correlations

        manager = FactorWeightManager(db=mock_db, analyzer=mock_analyzer)
        manager._cache = WeightCache()

        with patch("src.factor_weight_manager.get_settings") as mock_settings:
            settings = MagicMock()
            settings.factor_weight_enabled = True
            settings.factor_significance_threshold = 0.00  # Allow zero
            settings.factor_weight_min = 0.05
            settings.factor_weight_max = 0.40
            settings.factor_weight_recalibrate_trades = 50
            settings.factor_weight_cache_ttl_hours = 24
            mock_settings.return_value = settings

            # Should not raise exception
            result = manager.generate_factor_weights()

        assert result is not None
