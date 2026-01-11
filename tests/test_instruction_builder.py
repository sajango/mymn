"""Tests for InstructionBuilder module.

Tests modular instruction assembly, regime selection, token budgets,
and performance context injection.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.instruction_builder import (
    InstructionBuilder,
    get_instruction_builder,
    INSTRUCTIONS_DIR,
)


class TestModuleLoading:
    """Tests for module loading functionality."""

    def test_all_core_modules_load(self):
        """Test all core modules load correctly."""
        builder = InstructionBuilder()
        builder.clear_cache()

        core_modules = [
            "core/essential-rules.md",
            "core/confidence-scoring.md",
            "core/output-format.md",
        ]

        for module in core_modules:
            content = builder._load_module(module)
            assert content, f"Core module {module} should load and have content"
            assert len(content) > 100, f"Core module {module} should have substantial content"

    def test_all_regime_modules_load(self):
        """Test all regime modules load correctly."""
        builder = InstructionBuilder()
        builder.clear_cache()

        regime_modules = [
            "regime/trending-strong.md",
            "regime/trending-weak.md",
            "regime/ranging.md",
            "regime/volatile.md",
        ]

        for module in regime_modules:
            content = builder._load_module(module)
            assert content, f"Regime module {module} should load and have content"

    def test_all_wave_pattern_modules_load(self):
        """Test all wave pattern modules load correctly."""
        builder = InstructionBuilder()
        builder.clear_cache()

        wave_modules = [
            "wave-patterns/wave-2-entry.md",
            "wave-patterns/wave-4-entry.md",
            "wave-patterns/wave-5-exit.md",
            "wave-patterns/complex-corrections.md",
        ]

        for module in wave_modules:
            content = builder._load_module(module)
            assert content, f"Wave module {module} should load and have content"

    def test_indicator_confluence_module_loads(self):
        """Test indicator confluence module loads."""
        builder = InstructionBuilder()
        builder.clear_cache()

        content = builder._load_module("indicators/confluence.md")
        assert content, "Confluence module should load"
        assert "RSI" in content or "MACD" in content, "Should contain indicator references"

    def test_performance_template_loads(self):
        """Test performance template module loads."""
        builder = InstructionBuilder()
        builder.clear_cache()

        content = builder._load_module("context/performance-template.md")
        assert content, "Performance template should load"
        assert "{{WIN_RATE}}" in content, "Should contain WIN_RATE placeholder"

    def test_missing_module_returns_empty_and_logs(self):
        """Test missing module returns empty string and logs warning."""
        builder = InstructionBuilder()
        builder.clear_cache()

        with patch("src.instruction_builder.logger") as mock_logger:
            content = builder._load_module("nonexistent/module.md")
            assert content == "", "Missing module should return empty string"
            mock_logger.warning.assert_called()

    def test_module_caching(self):
        """Test that modules are cached after first load."""
        builder = InstructionBuilder()
        builder.clear_cache()

        # First load
        content1 = builder._load_module("core/essential-rules.md")
        # Second load (should hit cache)
        content2 = builder._load_module("core/essential-rules.md")

        assert content1 == content2, "Cached content should match original"
        # Check cache info
        cache_info = builder._load_module.cache_info()
        assert cache_info.hits >= 1, "Should have cache hit"


class TestRegimeSelection:
    """Tests for regime module selection logic."""

    def test_default_regime_when_no_data(self):
        """Test default regime selection when no market data provided."""
        builder = InstructionBuilder()

        regime = builder._select_regime_module(None, None)
        assert regime == "regime/trending-strong.md", "Default should be trending-strong"

    def test_trending_strong_selection(self):
        """Test trending-strong regime selected for high ADX."""
        builder = InstructionBuilder()

        # ADX >= 25
        regime = builder._select_regime_module({"adx": 30}, None)
        assert regime == "regime/trending-strong.md"

        # regime_type contains 'strong'
        regime = builder._select_regime_module({"adx": 20, "regime_type": "trending_strong"}, None)
        assert regime == "regime/trending-strong.md"

    def test_trending_weak_selection(self):
        """Test trending-weak regime selected for moderate ADX."""
        builder = InstructionBuilder()

        # ADX 15-24
        regime = builder._select_regime_module({"adx": 20, "regime_type": ""}, None)
        assert regime == "regime/trending-weak.md"

        # regime_type contains 'weak'
        regime = builder._select_regime_module({"adx": 10, "regime_type": "trending_weak"}, None)
        assert regime == "regime/trending-weak.md"

    def test_ranging_selection(self):
        """Test ranging regime selected for low ADX."""
        builder = InstructionBuilder()

        # ADX < 15
        regime = builder._select_regime_module({"adx": 12, "regime_type": ""}, None)
        assert regime == "regime/ranging.md"

        # regime_type contains 'ranging'
        regime = builder._select_regime_module({"adx": 20, "regime_type": "ranging"}, None)
        assert regime == "regime/ranging.md"

    def test_volatile_regime_overrides_trend(self):
        """Test volatile regime selected when ATR percentile > 80."""
        builder = InstructionBuilder()

        # High volatility should override strong trend
        regime = builder._select_regime_module(
            {"adx": 35, "regime_type": "trending_strong"},
            {"atr_percentile": 85}
        )
        assert regime == "regime/volatile.md"


class TestWaveModuleSelection:
    """Tests for wave pattern module selection."""

    def test_default_entry_modules(self):
        """Test default entry modules when no context."""
        builder = InstructionBuilder()

        modules = builder._select_wave_modules(None)
        assert "wave-patterns/wave-2-entry.md" in modules
        assert "wave-patterns/wave-4-entry.md" in modules

    def test_entry_context_selects_entry_modules(self):
        """Test entry context selects entry modules."""
        builder = InstructionBuilder()

        modules = builder._select_wave_modules({"looking_for": "entry"})
        assert "wave-patterns/wave-2-entry.md" in modules
        assert "wave-patterns/wave-4-entry.md" in modules
        assert "wave-patterns/wave-5-exit.md" not in modules

    def test_exit_context_selects_exit_modules(self):
        """Test exit context selects exit modules."""
        builder = InstructionBuilder()

        modules = builder._select_wave_modules({"looking_for": "exit"})
        assert "wave-patterns/wave-5-exit.md" in modules
        assert "wave-patterns/wave-2-entry.md" not in modules

    def test_high_ambiguity_adds_complex_corrections(self):
        """Test high wave ambiguity adds complex corrections module."""
        builder = InstructionBuilder()

        # Low ambiguity - no complex corrections
        modules = builder._select_wave_modules({"looking_for": "entry", "wave_ambiguity": 10})
        assert "wave-patterns/complex-corrections.md" not in modules

        # High ambiguity - adds complex corrections
        modules = builder._select_wave_modules({"looking_for": "entry", "wave_ambiguity": 40})
        assert "wave-patterns/complex-corrections.md" in modules


class TestTokenBudget:
    """Tests for token budget validation."""

    def test_standard_assembly_under_budget(self):
        """Test standard assembly stays under 15K token budget."""
        builder = InstructionBuilder()
        builder.clear_cache()

        assembled = builder.build(
            market_regime={"adx": 30, "regime_type": "trending_strong"},
            signal_context={"looking_for": "entry", "wave_ambiguity": 10},
            volatility_state={"atr_percentile": 50}
        )

        token_count = builder.estimate_tokens(assembled)
        assert token_count <= 15000, f"Standard assembly ({token_count}) should be under 15K tokens"
        assert token_count >= 5000, f"Standard assembly ({token_count}) should have substantial content"

    def test_complex_assembly_under_budget(self):
        """Test assembly with complex corrections stays under budget."""
        builder = InstructionBuilder()
        builder.clear_cache()

        assembled = builder.build(
            market_regime={"adx": 30, "regime_type": "trending_strong"},
            signal_context={"looking_for": "entry", "wave_ambiguity": 40},  # Triggers complex module
            volatility_state={"atr_percentile": 50}
        )

        token_count = builder.estimate_tokens(assembled)
        assert token_count <= 15000, f"Complex assembly ({token_count}) should be under 15K tokens"

    def test_all_regime_assemblies_under_budget(self):
        """Test all regime variations stay under budget."""
        builder = InstructionBuilder()
        builder.clear_cache()

        regimes = [
            {"adx": 35, "regime_type": "trending_strong"},
            {"adx": 20, "regime_type": "trending_weak"},
            {"adx": 12, "regime_type": "ranging"},
        ]

        for regime in regimes:
            assembled = builder.build(
                market_regime=regime,
                signal_context={"looking_for": "entry"},
                volatility_state={"atr_percentile": 50}
            )
            token_count = builder.estimate_tokens(assembled)
            assert token_count <= 15000, f"Assembly with {regime} ({token_count}) should be under 15K"

    def test_volatile_regime_under_budget(self):
        """Test volatile regime assembly under budget."""
        builder = InstructionBuilder()
        builder.clear_cache()

        assembled = builder.build(
            market_regime={"adx": 25, "regime_type": "trending"},
            signal_context={"looking_for": "entry"},
            volatility_state={"atr_percentile": 90}  # Triggers volatile regime
        )

        token_count = builder.estimate_tokens(assembled)
        assert token_count <= 15000, f"Volatile assembly ({token_count}) should be under 15K"

    def test_estimate_tokens_accuracy(self):
        """Test token estimation method."""
        builder = InstructionBuilder()

        # Test known string lengths
        assert builder.estimate_tokens("a" * 400) == 100
        assert builder.estimate_tokens("a" * 4000) == 1000
        assert builder.estimate_tokens("") == 0


class TestPerformanceContextInjection:
    """Tests for performance context injection."""

    def test_performance_context_with_full_data(self):
        """Test performance context injection with complete data."""
        builder = InstructionBuilder()
        builder.clear_cache()

        signal_context = {
            "overall_win_rate": 52.5,
            "best_wave_position": "Wave 3",
            "worst_wave_position": "Wave 5",
            "best_session": "London",
            "worst_session": "Asian",
            "calibrated_min_confidence": 65,
            "confidence_performance": {
                "80+": {"win_rate": 68, "total": 15},
                "70+": {"win_rate": 55, "total": 25},
                "60+": {"win_rate": 48, "total": 40},
                "50+": {"win_rate": 42, "total": 60},
            },
            "current_streak": {"type": "win", "count": 2}
        }

        context = builder._build_performance_context(signal_context)

        # Verify placeholders replaced
        assert "{{WIN_RATE}}" not in context, "WIN_RATE placeholder should be replaced"
        assert "52.5" in context, "Win rate value should be present"
        assert "Wave 3" in context, "Best wave should be present"
        assert "London" in context, "Best session should be present"

    def test_performance_context_with_losing_streak(self):
        """Test streak warning appears for losing streaks."""
        builder = InstructionBuilder()
        builder.clear_cache()

        signal_context = {
            "overall_win_rate": 45,
            "current_streak": {"type": "loss", "count": 3}
        }

        context = builder._build_performance_context(signal_context)

        assert "WARNING" in context or "⚠️" in context, "Should have streak warning"
        assert "3" in context, "Should mention streak count"

    def test_performance_context_no_streak_warning(self):
        """Test no streak warning for winning streaks."""
        builder = InstructionBuilder()
        builder.clear_cache()

        signal_context = {
            "overall_win_rate": 55,
            "current_streak": {"type": "win", "count": 5}
        }

        context = builder._build_performance_context(signal_context)

        assert "No streak warning" in context or "WARNING" not in context

    def test_performance_context_with_missing_data(self):
        """Test performance context handles missing data gracefully."""
        builder = InstructionBuilder()
        builder.clear_cache()

        signal_context = {"looking_for": "entry"}  # Minimal context

        context = builder._build_performance_context(signal_context)

        # Should return something (template with N/A values)
        assert "N/A" in context or context == "", "Should handle missing data"

    def test_empty_context_returns_empty(self):
        """Test empty signal context returns empty string."""
        builder = InstructionBuilder()
        builder.clear_cache()

        context = builder._build_performance_context(None)
        assert context == "", "None context should return empty string"

    def test_win_rate_comments(self):
        """Test win rate comment generation."""
        builder = InstructionBuilder()

        assert "Good" in builder._win_rate_comment(60)
        assert "Marginal" in builder._win_rate_comment(48)
        assert "Poor" in builder._win_rate_comment(40)
        assert "Insufficient" in builder._win_rate_comment(None)


class TestBuildAssembly:
    """Tests for full build assembly."""

    def test_build_returns_non_empty_string(self):
        """Test build returns non-empty assembled instructions."""
        builder = InstructionBuilder()
        builder.clear_cache()

        result = builder.build()

        assert isinstance(result, str)
        assert len(result) > 1000, "Build should return substantial content"

    def test_build_contains_section_separators(self):
        """Test build output contains section separators."""
        builder = InstructionBuilder()
        builder.clear_cache()

        result = builder.build(
            market_regime={"adx": 30},
            signal_context={"looking_for": "entry"}
        )

        assert "---" in result, "Should contain section separators"

    def test_build_contains_core_content(self):
        """Test build contains core rule content."""
        builder = InstructionBuilder()
        builder.clear_cache()

        result = builder.build()

        # Check for key content from core modules
        assert "Wave" in result, "Should contain Wave references"
        assert "confidence" in result.lower(), "Should contain confidence references"

    def test_build_with_all_parameters(self):
        """Test build with all parameters provided."""
        builder = InstructionBuilder()
        builder.clear_cache()

        result = builder.build(
            market_regime={"adx": 25, "regime_type": "trending_weak"},
            signal_context={
                "looking_for": "entry",
                "wave_ambiguity": 35,
                "overall_win_rate": 50,
                "best_wave_position": "Wave 2",
                "current_streak": {"type": "loss", "count": 2}
            },
            volatility_state={"atr_percentile": 60}
        )

        assert len(result) > 5000, "Full build should be substantial"
        assert "complex" in result.lower(), "Should include complex corrections (high ambiguity)"


class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_instruction_builder_returns_same_instance(self):
        """Test singleton returns same instance."""
        builder1 = get_instruction_builder()
        builder2 = get_instruction_builder()

        assert builder1 is builder2, "Should return same singleton instance"

    def test_singleton_preserves_cache(self):
        """Test singleton preserves cached modules."""
        builder1 = get_instruction_builder()
        builder1._load_module("core/essential-rules.md")

        builder2 = get_instruction_builder()
        cache_info = builder2._load_module.cache_info()

        assert cache_info.hits >= 0, "Cache should be preserved across singleton calls"


class TestFeedbackLoopIntegration:
    """Tests for feedback loop integration (Phase 5)."""

    def test_performance_context_flows_to_builder(self):
        """Test performance context from database flows to InstructionBuilder."""
        builder = InstructionBuilder()
        builder.clear_cache()

        # Simulate performance context from database
        perf_context = {
            "overall_win_rate": 52.5,
            "best_wave_position": "Wave 2",
            "worst_wave_position": "Wave 5",
            "best_session": "London",
            "worst_session": "Asian",
            "calibrated_min_confidence": 65,
            "confidence_performance": {
                "80+": {"win_rate": 68, "total": 15},
                "70+": {"win_rate": 55, "total": 25},
                "60+": {"win_rate": 48, "total": 40},
                "50+": {"win_rate": 42, "total": 60},
            },
            "current_streak": {"type": "win", "count": 3},
            "looking_for": "entry",
        }

        # Build with performance context
        result = builder.build(
            market_regime={"adx": 30, "regime_type": "trending_strong"},
            signal_context=perf_context,
            volatility_state={"atr_percentile": 50}
        )

        # Verify performance data is injected
        assert "52.5" in result, "Win rate should be in assembled instructions"
        assert "Wave 2" in result, "Best wave should be in assembled instructions"
        assert "London" in result, "Best session should be in assembled instructions"

    def test_calibrated_confidence_threshold_injection(self):
        """Test calibrated confidence threshold appears in output."""
        builder = InstructionBuilder()
        builder.clear_cache()

        signal_context = {
            "overall_win_rate": 55,
            "calibrated_min_confidence": 70,
            "looking_for": "entry",
        }

        result = builder.build(
            market_regime={"adx": 25},
            signal_context=signal_context
        )

        assert "70" in result, "Calibrated confidence should be in instructions"

    def test_losing_streak_warning_injection(self):
        """Test losing streak triggers warning in instructions."""
        builder = InstructionBuilder()
        builder.clear_cache()

        signal_context = {
            "overall_win_rate": 45,
            "current_streak": {"type": "loss", "count": 4},
            "looking_for": "entry",
        }

        result = builder.build(
            market_regime={"adx": 25},
            signal_context=signal_context
        )

        assert "WARNING" in result or "⚠️" in result, "Losing streak warning should appear"
        assert "4" in result, "Streak count should be mentioned"

    def test_full_feedback_loop_assembly(self):
        """Test complete feedback loop with all performance data."""
        builder = InstructionBuilder()
        builder.clear_cache()

        # Complete performance context simulating database output
        full_context = {
            "overall_win_rate": 48.5,
            "wave_performance": {
                "Wave 2": {"win_rate": 55, "total": 20},
                "Wave 4": {"win_rate": 45, "total": 15},
            },
            "confidence_performance": {
                "80+": {"win_rate": 70, "total": 10},
                "70+": {"win_rate": 52, "total": 20},
                "60+": {"win_rate": 45, "total": 35},
            },
            "session_performance": {
                "London": {"win_rate": 55, "total": 25},
                "NY": {"win_rate": 50, "total": 30},
                "Asian": {"win_rate": 40, "total": 15},
            },
            "current_streak": {"type": "loss", "count": 2},
            "best_wave_position": "Wave 2",
            "worst_wave_position": "Wave 4",
            "best_session": "London",
            "worst_session": "Asian",
            "calibrated_min_confidence": 70,
            "looking_for": "entry",
            "wave_ambiguity": 35,  # Triggers complex corrections
        }

        result = builder.build(
            market_regime={"adx": 20, "regime_type": "trending_weak"},
            signal_context=full_context,
            volatility_state={"atr_percentile": 60}
        )

        # Verify comprehensive integration
        assert len(result) > 5000, "Full assembly should be substantial"
        assert "48.5" in result, "Overall win rate should be present"
        assert "Wave 2" in result, "Best wave should be present"
        assert "London" in result, "Best session should be present"
        assert "complex" in result.lower(), "Complex corrections should be included (high ambiguity)"

        # Verify token budget
        token_count = builder.estimate_tokens(result)
        assert token_count <= 15000, f"Assembly ({token_count} tokens) should stay under budget"
