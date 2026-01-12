"""Factor Weight Manager - Auto-adjusts factor weights based on correlation with trade outcomes.

Phase 03 of the Data-Driven Feedback Loop:
- Calculates optimal factor weights from historical correlation data
- Generates human-readable guidance for Claude instructions
- Implements 24h cache with 50-trade invalidation trigger

Weight calculation algorithm:
1. Get factor correlations from CalibrationAnalyzer.analyze_factor_impact()
2. Filter significant factors (|correlation| > threshold, sample >= 20)
3. Normalize by absolute correlation sum
4. Apply floor (0.05) and cap (0.40) bounds
5. Re-normalize to sum to 1.0
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.calibration_analyzer import CalibrationAnalyzer, FactorCorrelation
from src.config import get_settings
from src.database import Database, get_database

logger = logging.getLogger(__name__)


# Default weights when insufficient data available
DEFAULT_WEIGHTS: Dict[str, float] = {
    "timeframe_alignment": 0.20,
    "fibonacci_confluence": 0.20,
    "rsi_confirmation": 0.15,
    "ema_alignment": 0.15,
    "macd_confirmation": 0.15,
    "session_bonus": 0.10,
    "penalties": 0.05,
}


@dataclass
class FactorWeights:
    """Container for calculated factor weights with metadata."""

    weights: Dict[str, float] = field(default_factory=dict)
    correlations: Dict[str, float] = field(default_factory=dict)
    sample_sizes: Dict[str, int] = field(default_factory=dict)
    total_trades: int = 0
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    is_default: bool = True

    def __post_init__(self):
        """Validate weights sum to ~1.0."""
        if self.weights:
            total = sum(self.weights.values())
            if abs(total - 1.0) > 0.01:
                logger.warning(f"Weights sum to {total:.3f}, expected ~1.0")


@dataclass
class WeightCache:
    """Cache container for factor weights."""

    data: Optional[FactorWeights] = None
    expires_at: Optional[datetime] = None
    trade_count_at_calc: int = 0

    def is_valid(self, current_trade_count: int, invalidation_trades: int = 50) -> bool:
        """Check if cache is still valid.

        Args:
            current_trade_count: Current total trade count
            invalidation_trades: New trades threshold for invalidation

        Returns:
            True if cache is valid
        """
        if self.data is None or self.expires_at is None:
            return False

        # Check TTL expiry
        if datetime.utcnow() > self.expires_at:
            return False

        # Check trade count trigger
        trades_since = current_trade_count - self.trade_count_at_calc
        if trades_since >= invalidation_trades:
            return False

        return True


class FactorWeightManager:
    """Manages dynamic factor weight calculation and instruction generation.

    Uses correlation data from CalibrationAnalyzer to generate
    data-driven factor weights for Claude instructions.
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        analyzer: Optional[CalibrationAnalyzer] = None,
    ):
        """Initialize FactorWeightManager.

        Args:
            db: Optional Database instance for testing
            analyzer: Optional CalibrationAnalyzer instance for testing
        """
        self._db = db
        self._analyzer = analyzer
        self._cache = WeightCache()

    @property
    def db(self) -> Database:
        """Lazy load database."""
        if self._db is None:
            self._db = get_database()
        return self._db

    @property
    def analyzer(self) -> CalibrationAnalyzer:
        """Lazy load calibration analyzer."""
        if self._analyzer is None:
            self._analyzer = CalibrationAnalyzer(self.db)
        return self._analyzer

    def generate_factor_weights(self, days: int = 30) -> FactorWeights:
        """Generate normalized factor weights from historical correlation.

        Algorithm:
        1. Get factor correlations from CalibrationAnalyzer
        2. Filter to significant factors only (|correlation| > threshold, sample >= 20)
        3. Normalize weights by absolute correlation sum
        4. Apply minimum weight floor and maximum cap
        5. Re-normalize to sum to 1.0

        Args:
            days: Lookback period in days

        Returns:
            FactorWeights with normalized weights and metadata
        """
        settings = get_settings()

        # Check if feature is enabled
        if not getattr(settings, "factor_weight_enabled", True):
            logger.debug("Factor weight adjustment disabled, using defaults")
            return FactorWeights(
                weights=DEFAULT_WEIGHTS.copy(),
                is_default=True,
            )

        # Check cache first
        current_trade_count = self._get_trade_count()
        invalidation_trades = getattr(settings, "factor_weight_recalibrate_trades", 50)

        if self._cache.is_valid(current_trade_count, invalidation_trades):
            logger.debug("Using cached factor weights")
            return self._cache.data

        # Get correlations from analyzer
        correlations = self.analyzer.analyze_factor_impact(days)

        if not correlations:
            logger.info("No factor correlations available, using defaults")
            return self._create_default_weights(current_trade_count)

        # Get settings for thresholds
        significance_threshold = getattr(settings, "factor_significance_threshold", 0.10)
        weight_min = getattr(settings, "factor_weight_min", 0.05)
        weight_max = getattr(settings, "factor_weight_max", 0.40)

        # Filter significant factors
        significant = [
            c for c in correlations
            if c.significant and abs(c.correlation) >= significance_threshold
        ]

        if not significant:
            logger.info(
                f"No significant factors (threshold={significance_threshold}), using defaults"
            )
            return self._create_default_weights(current_trade_count)

        # Calculate raw weights from absolute correlations
        total_corr = sum(abs(c.correlation) for c in significant)
        raw_weights = {}

        for corr in significant:
            if total_corr > 0:
                raw_weight = abs(corr.correlation) / total_corr
            else:
                raw_weight = 1.0 / len(significant)
            raw_weights[corr.factor] = raw_weight

        # Apply floor and cap bounds
        bounded_weights = {}
        for factor, weight in raw_weights.items():
            bounded = max(weight_min, min(weight_max, weight))
            bounded_weights[factor] = bounded

        # Re-normalize to sum to 1.0
        weight_sum = sum(bounded_weights.values())
        normalized_weights = {
            f: w / weight_sum for f, w in bounded_weights.items()
        }

        # Build metadata - use max sample size as representative trade count
        total_trades = max((c.sample_size for c in correlations), default=0)
        correlation_map = {c.factor: c.correlation for c in correlations}
        sample_map = {c.factor: c.sample_size for c in correlations}

        result = FactorWeights(
            weights=normalized_weights,
            correlations=correlation_map,
            sample_sizes=sample_map,
            total_trades=total_trades,
            calculated_at=datetime.utcnow(),
            is_default=False,
        )

        # Update cache
        cache_ttl = getattr(settings, "factor_weight_cache_ttl_hours", 24)
        self._cache = WeightCache(
            data=result,
            expires_at=datetime.utcnow() + timedelta(hours=cache_ttl),
            trade_count_at_calc=current_trade_count,
        )

        logger.info(
            f"[FactorWeightManager] Generated weights from {len(significant)} "
            f"significant factors ({total_trades} trades)"
        )

        return result

    def get_factor_guidance(self, days: int = 30) -> str:
        """Generate human-readable factor guidance for instructions.

        Categorizes factors as HIGH/MEDIUM/LOW priority based on weights
        and formats as markdown for Claude consumption.

        Args:
            days: Lookback period in days

        Returns:
            Markdown-formatted factor priority guidance
        """
        factor_weights = self.generate_factor_weights(days)

        if factor_weights.is_default:
            return self._format_default_guidance()

        return self._format_guidance(factor_weights)

    def should_recalibrate(self) -> bool:
        """Check if factor weights should be recalculated.

        Returns:
            True if recalibration needed
        """
        settings = get_settings()
        current_trade_count = self._get_trade_count()
        invalidation_trades = getattr(settings, "factor_weight_recalibrate_trades", 50)

        return not self._cache.is_valid(current_trade_count, invalidation_trades)

    def invalidate_cache(self) -> None:
        """Force cache invalidation."""
        self._cache = WeightCache()
        logger.debug("Factor weight cache invalidated")

    def _get_trade_count(self) -> int:
        """Get current total closed trade count."""
        try:
            closed_trades = self.db.get_closed_trades()
            return len(closed_trades)
        except Exception as e:
            logger.warning(f"Failed to get trade count: {e}")
        return 0

    def _create_default_weights(self, trade_count: int) -> FactorWeights:
        """Create default weights result."""
        return FactorWeights(
            weights=DEFAULT_WEIGHTS.copy(),
            total_trades=trade_count,
            is_default=True,
        )

    def _format_guidance(self, factor_weights: FactorWeights) -> str:
        """Format factor weights as markdown guidance.

        Categorizes:
        - HIGH: weight >= 0.25
        - MEDIUM: 0.10 <= weight < 0.25
        - LOW: weight < 0.10
        - NEGATIVE: correlation < 0

        Args:
            factor_weights: Calculated factor weights

        Returns:
            Markdown-formatted guidance string
        """
        weights = factor_weights.weights
        correlations = factor_weights.correlations

        # Categorize factors
        high_priority = []
        medium_priority = []
        low_priority = []
        negative_corr = []

        for factor, weight in sorted(weights.items(), key=lambda x: -x[1]):
            corr = correlations.get(factor, 0)
            entry = f"- {factor}: Weight {weight:.2f} (correlation {corr:+.2f})"

            if corr < 0:
                negative_corr.append(entry)
            elif weight >= 0.25:
                high_priority.append(entry)
            elif weight >= 0.10:
                medium_priority.append(entry)
            else:
                low_priority.append(entry)

        # Build markdown
        lines = [
            f"Based on last {factor_weights.total_trades} trades:",
            "",
        ]

        if high_priority:
            lines.append("**HIGH PRIORITY** (strongly correlated with wins):")
            lines.extend(high_priority)
            lines.append("")

        if medium_priority:
            lines.append("**MEDIUM PRIORITY** (moderate correlation):")
            lines.extend(medium_priority)
            lines.append("")

        if low_priority:
            lines.append("**LOW PRIORITY** (weak correlation):")
            lines.extend(low_priority)
            lines.append("")

        if negative_corr:
            lines.append("**NEGATIVE CORRELATION** (reduce weight in decisions):")
            lines.extend(negative_corr)
            lines.append("")

        return "\n".join(lines)

    def _format_default_guidance(self) -> str:
        """Format guidance when using default weights."""
        return (
            "Using default factor weights (insufficient data for calibration):\n"
            "- All factors weighted equally\n"
            "- Collect more trades for data-driven recommendations\n"
        )


# Lazy singleton
_factor_weight_manager: Optional[FactorWeightManager] = None


def get_factor_weight_manager() -> FactorWeightManager:
    """Get or create FactorWeightManager singleton."""
    global _factor_weight_manager
    if _factor_weight_manager is None:
        _factor_weight_manager = FactorWeightManager()
    return _factor_weight_manager


def reset_factor_weight_manager() -> None:
    """Reset singleton for testing."""
    global _factor_weight_manager
    _factor_weight_manager = None
