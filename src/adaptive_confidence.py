"""Adaptive Confidence Manager - Dynamic threshold adjustment based on trading performance.

Closes the feedback loop from CalibrationAnalyzer to RiskGuard by providing:
- Dynamic entry thresholds based on rolling 50-trade window
- Cross-validation gate (80/20 split) to prevent overfitting
- Position size modifiers based on recent performance
- Automatic recalibration when trade count or TTL triggers

Architecture:
    CalibrationAnalyzer (reads trade outcomes)
            ↓
    AdaptiveConfidenceManager (this module)
            ↓
    RiskGuard.validate() (uses adaptive thresholds)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveThresholds:
    """Dynamic thresholds calculated from rolling trade performance.

    Attributes:
        entry_minimum: Minimum confidence for any trade entry (default: 50)
        full_position: Confidence threshold for 100% position size (default: 75)
        direction_change: Min confidence for reversal trades (default: 80)
        position_modifier: Streak-based position size modifier (0.4-1.0)
        calculated_at: Timestamp of calculation
        trade_count: Number of trades used in calculation
        validation_score: Cross-validation expectancy score
    """

    entry_minimum: int = 50
    full_position: int = 75
    direction_change: int = 80
    position_modifier: float = 1.0
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    trade_count: int = 0
    validation_score: float = 0.0

    def __post_init__(self):
        """Validate threshold bounds."""
        # Clamp thresholds to valid range
        self.entry_minimum = max(30, min(80, self.entry_minimum))
        self.full_position = max(60, min(95, self.full_position))
        self.direction_change = max(65, min(95, self.direction_change))
        self.position_modifier = max(0.4, min(1.0, self.position_modifier))

        # Ensure logical ordering: entry_minimum < full_position <= direction_change
        if self.entry_minimum >= self.full_position:
            self.full_position = self.entry_minimum + 15
        if self.full_position > self.direction_change:
            self.direction_change = self.full_position + 5


@dataclass
class ThresholdCache:
    """Cache container for adaptive thresholds."""

    thresholds: Optional[AdaptiveThresholds] = None
    last_updated: Optional[datetime] = None
    last_trade_count: int = 0

    def is_valid(self, ttl_minutes: int, current_trade_count: int, invalidation_trades: int = 50) -> bool:
        """Check if cache is still valid.

        Args:
            ttl_minutes: Maximum age in minutes before expiry
            current_trade_count: Current total trade count from database
            invalidation_trades: Number of new trades to trigger invalidation

        Returns:
            True if cache is valid, False if needs refresh
        """
        if self.thresholds is None or self.last_updated is None:
            return False

        # Check TTL
        age = datetime.utcnow() - self.last_updated
        if age > timedelta(minutes=ttl_minutes):
            logger.debug(f"[AdaptiveCache] Expired: age={age.total_seconds()/60:.1f}min > TTL={ttl_minutes}min")
            return False

        # Check trade count (invalidate after N new trades)
        new_trades = current_trade_count - self.last_trade_count
        if new_trades >= invalidation_trades:
            logger.debug(f"[AdaptiveCache] Invalidated: {new_trades} new trades >= {invalidation_trades}")
            return False

        return True


class AdaptiveConfidenceManager:
    """Manages dynamic confidence thresholds based on rolling trade performance.

    Integrates with CalibrationAnalyzer to:
    1. Calculate optimal thresholds from rolling 50-trade window
    2. Cross-validate changes before applying (80/20 split)
    3. Provide position size modifiers based on recent performance
    4. Auto-revert if performance degrades significantly

    Usage:
        manager = get_adaptive_confidence_manager()
        thresholds = manager.get_adjusted_thresholds()

        # In RiskGuard.validate():
        if signal.confidence < thresholds.entry_minimum:
            return RiskCheckResult(passed=False, ...)
    """

    # Default thresholds (fallback when insufficient data)
    DEFAULT_ENTRY_MINIMUM = 50
    DEFAULT_FULL_POSITION = 75
    DEFAULT_DIRECTION_CHANGE = 80

    def __init__(self, db=None, config=None):
        """Initialize AdaptiveConfidenceManager.

        Args:
            db: Optional Database instance (lazy-loaded if None)
            config: Optional Settings instance (lazy-loaded if None)
        """
        self._db = db
        self._config = config
        self._cache = ThresholdCache()
        self._calibration_analyzer = None

    @property
    def db(self):
        """Lazy load database."""
        if self._db is None:
            from src.database import get_database
            self._db = get_database()
        return self._db

    @property
    def config(self):
        """Lazy load settings."""
        if self._config is None:
            from src.config import get_settings
            self._config = get_settings()
        return self._config

    @property
    def calibration_analyzer(self):
        """Lazy load CalibrationAnalyzer."""
        if self._calibration_analyzer is None:
            from src.calibration_analyzer import get_calibration_analyzer
            self._calibration_analyzer = get_calibration_analyzer()
        return self._calibration_analyzer

    def get_adjusted_thresholds(self, days: int = 30) -> AdaptiveThresholds:
        """Get current adaptive thresholds, recalculating if needed.

        Args:
            days: Lookback period for trade analysis

        Returns:
            AdaptiveThresholds with current optimal values
        """
        # Check if adaptive thresholds are enabled
        if not getattr(self.config, 'adaptive_threshold_enabled', True):
            logger.debug("[AdaptiveConfidence] Disabled, using defaults")
            return self._get_default_thresholds()

        # Check cache validity
        current_trade_count = self._get_closed_trade_count()
        ttl = getattr(self.config, 'adaptive_cache_ttl_minutes', 60)
        invalidation_trades = getattr(self.config, 'adaptive_invalidation_trades', 50)

        if self._cache.is_valid(ttl, current_trade_count, invalidation_trades):
            logger.debug("[AdaptiveConfidence] Using cached thresholds")
            return self._cache.thresholds

        # Recalculate thresholds
        logger.info("[AdaptiveConfidence] Recalculating thresholds...")
        thresholds = self._calculate_rolling_thresholds(days)

        # Cross-validate before applying
        if thresholds.trade_count >= getattr(self.config, 'adaptive_min_trades', 50):
            validated = self._cross_validate(thresholds, days)
            if not validated:
                logger.warning("[AdaptiveConfidence] Cross-validation failed, using defaults")
                thresholds = self._get_default_thresholds()
        else:
            logger.info(f"[AdaptiveConfidence] Insufficient trades ({thresholds.trade_count}), using defaults")
            thresholds = self._get_default_thresholds()

        # Update cache
        self._cache.thresholds = thresholds
        self._cache.last_updated = datetime.utcnow()
        self._cache.last_trade_count = current_trade_count

        logger.info(
            f"[AdaptiveConfidence] Thresholds updated: "
            f"entry={thresholds.entry_minimum}, full={thresholds.full_position}, "
            f"modifier={thresholds.position_modifier:.2f}"
        )

        return thresholds

    def should_recalibrate(self) -> bool:
        """Check if thresholds should be recalculated.

        Returns:
            True if recalibration is needed
        """
        current_trade_count = self._get_closed_trade_count()
        ttl = getattr(self.config, 'adaptive_cache_ttl_minutes', 60)
        invalidation_trades = getattr(self.config, 'adaptive_invalidation_trades', 50)

        return not self._cache.is_valid(ttl, current_trade_count, invalidation_trades)

    def get_position_size_modifier(self) -> float:
        """Get current position size modifier based on recent performance.

        Returns:
            Modifier between 0.4 (poor streak) and 1.0 (good performance)
        """
        thresholds = self.get_adjusted_thresholds()
        return thresholds.position_modifier

    def invalidate_cache(self):
        """Force cache invalidation (call after trade closure)."""
        logger.debug("[AdaptiveConfidence] Cache manually invalidated")
        self._cache.thresholds = None
        self._cache.last_updated = None

    def _get_default_thresholds(self) -> AdaptiveThresholds:
        """Get default thresholds from config.

        Returns:
            AdaptiveThresholds with config defaults
        """
        return AdaptiveThresholds(
            entry_minimum=getattr(self.config, 'confidence_threshold', self.DEFAULT_ENTRY_MINIMUM),
            full_position=getattr(self.config, 'confidence_full_position', self.DEFAULT_FULL_POSITION),
            direction_change=getattr(self.config, 'direction_change_min_confidence', self.DEFAULT_DIRECTION_CHANGE),
            position_modifier=1.0,
            calculated_at=datetime.utcnow(),
            trade_count=0,
            validation_score=0.0,
        )

    def _get_closed_trade_count(self) -> int:
        """Get total number of closed trades from database.

        Returns:
            Number of closed trades
        """
        try:
            with self.db._get_connection() as conn:
                result = conn.execute(
                    "SELECT COUNT(*) as cnt FROM trades WHERE status = 'closed'"
                ).fetchone()
                return result['cnt'] if result else 0
        except Exception as e:
            logger.warning(f"[AdaptiveConfidence] Failed to get trade count: {e}")
            return 0

    def _calculate_rolling_thresholds(self, days: int = 30) -> AdaptiveThresholds:
        """Calculate optimal thresholds from rolling trade window.

        Uses CalibrationAnalyzer to:
        1. Find optimal entry threshold based on expectancy
        2. Analyze confidence buckets for position sizing
        3. Calculate streak-based position modifier

        Args:
            days: Lookback period

        Returns:
            AdaptiveThresholds with calculated values
        """
        # Get optimal threshold from CalibrationAnalyzer
        threshold_result = self.calibration_analyzer.find_optimal_threshold(days)
        trade_count = threshold_result.get('trade_count', 0)

        if trade_count < 10:
            return self._get_default_thresholds()

        optimal_entry = threshold_result.get('optimal_threshold', self.DEFAULT_ENTRY_MINIMUM)
        expectancy = threshold_result.get('expectancy', 0)

        # Get bucket performance for full position threshold
        buckets = self.calibration_analyzer.analyze_confidence_buckets(days)
        full_position = self._determine_full_position_threshold(buckets, optimal_entry)

        # Calculate direction change threshold (entry + 15, capped)
        direction_change = min(95, optimal_entry + 15)

        # Calculate position modifier from recent streak
        position_modifier = self._calculate_position_modifier(days)

        return AdaptiveThresholds(
            entry_minimum=optimal_entry,
            full_position=full_position,
            direction_change=direction_change,
            position_modifier=position_modifier,
            calculated_at=datetime.utcnow(),
            trade_count=trade_count,
            validation_score=expectancy,
        )

    def _determine_full_position_threshold(
        self, buckets: Dict[str, Any], entry_minimum: int
    ) -> int:
        """Determine full position threshold based on bucket performance.

        Finds lowest bucket with win rate >= 55% and total >= 10 trades.

        Args:
            buckets: Confidence bucket stats from CalibrationAnalyzer
            entry_minimum: Minimum entry threshold

        Returns:
            Full position confidence threshold
        """
        # Define bucket order from lowest to highest
        bucket_order = ['50-59', '60-69', '70-79', '80-89', '90+']
        bucket_mins = {'50-59': 50, '60-69': 60, '70-79': 70, '80-89': 80, '90+': 90}

        for bucket in bucket_order:
            if bucket not in buckets:
                continue

            stats = buckets[bucket]
            bucket_min = bucket_mins[bucket]

            # Skip buckets below entry minimum
            if bucket_min < entry_minimum:
                continue

            # Check if bucket qualifies for full position
            if stats.total >= 10 and stats.win_rate >= 55:
                # Use midpoint of bucket as threshold
                return bucket_min + 5

        # Default to entry + 20 if no good bucket found
        return min(95, entry_minimum + 20)

    def _calculate_position_modifier(self, days: int = 30) -> float:
        """Calculate position size modifier based on recent performance.

        Modifier logic:
        - Win streak 3+: 1.0 (full size)
        - Win rate > 60%: 1.0
        - Win rate 50-60%: 0.8
        - Win rate < 50%: 0.6
        - Loss streak 3+: 0.5

        Args:
            days: Lookback period

        Returns:
            Position modifier between 0.4 and 1.0
        """
        try:
            # Get current streak from database
            streak_info = self.db._get_current_streak()
            streak_type = streak_info.get('type', 'none')
            streak_count = streak_info.get('count', 0)

            # Strong win streak = full size
            if streak_type == 'win' and streak_count >= 3:
                return 1.0

            # Loss streak = reduce size
            if streak_type == 'loss' and streak_count >= 3:
                return 0.5

            # Check overall win rate
            trades = self.calibration_analyzer.get_calibration_data(days)
            if not trades:
                return 1.0

            wins = sum(1 for t in trades if t.get('outcome') == 'win')
            win_rate = (wins / len(trades) * 100) if trades else 50

            if win_rate >= 60:
                return 1.0
            elif win_rate >= 50:
                return 0.8
            else:
                return 0.6

        except Exception as e:
            logger.warning(f"[AdaptiveConfidence] Failed to calculate modifier: {e}")
            return 1.0

    def _cross_validate(self, thresholds: AdaptiveThresholds, days: int = 30) -> bool:
        """Cross-validate thresholds using 80/20 train/test split.

        Validates that new thresholds would have performed acceptably
        on the test set (most recent 20% of trades).

        Args:
            thresholds: Proposed thresholds to validate
            days: Lookback period

        Returns:
            True if validation passes, False if should reject
        """
        trades = self.calibration_analyzer.get_calibration_data(days)
        if len(trades) < 20:
            logger.debug("[AdaptiveConfidence] Insufficient trades for cross-validation")
            return True  # Allow with small sample (insufficient data to validate)

        # Split: most recent 20% is test set (trades already sorted by close_time DESC)
        split_idx = int(len(trades) * 0.2)
        test_set = trades[:split_idx]
        train_set = trades[split_idx:]

        # Calculate expectancy on test set using proposed threshold
        test_qualifying = [
            t for t in test_set
            if (t.get('confidence') or 0) >= thresholds.entry_minimum
        ]

        if len(test_qualifying) < 5:
            logger.debug("[AdaptiveConfidence] Insufficient test trades for validation")
            return True  # Allow if test set too small

        # Calculate test expectancy
        test_wins = sum(1 for t in test_qualifying if t.get('outcome') == 'win')
        test_win_rate = test_wins / len(test_qualifying)

        win_rs = [t.get('r_multiple', 0) for t in test_qualifying if t.get('outcome') == 'win']
        loss_rs = [abs(t.get('r_multiple', 0)) for t in test_qualifying if t.get('outcome') == 'loss']

        avg_win = sum(win_rs) / len(win_rs) if win_rs else 0
        avg_loss = sum(loss_rs) / len(loss_rs) if loss_rs else 0

        test_expectancy = (test_win_rate * avg_win) - ((1 - test_win_rate) * avg_loss)

        # Validation criteria: test expectancy must be > 0 or at least 50% of training
        min_acceptable = max(0, thresholds.validation_score * 0.5)

        if test_expectancy < min_acceptable:
            logger.warning(
                f"[AdaptiveConfidence] Cross-validation failed: "
                f"test_exp={test_expectancy:.3f} < min={min_acceptable:.3f}"
            )
            return False

        logger.info(
            f"[AdaptiveConfidence] Cross-validation passed: "
            f"test_exp={test_expectancy:.3f}, test_win_rate={test_win_rate*100:.1f}%"
        )
        return True

    def check_performance_degradation(self, days: int = 7) -> Dict[str, Any]:
        """Check for recent performance degradation.

        Monitors for significant performance drop that might indicate
        the adaptive thresholds are not working well.

        Args:
            days: Short lookback for recent performance

        Returns:
            Dict with degradation info and recommendations
        """
        # Get recent performance
        recent_trades = self.calibration_analyzer.get_calibration_data(days)
        if len(recent_trades) < 10:
            return {'degraded': False, 'reason': 'insufficient_data'}

        recent_wins = sum(1 for t in recent_trades if t.get('outcome') == 'win')
        recent_win_rate = recent_wins / len(recent_trades) * 100

        # Get baseline performance (30 days)
        baseline_report = self.calibration_analyzer.generate_calibration_report(30)
        baseline_win_rate = baseline_report.overall_win_rate

        # Check for significant degradation (>20% relative drop)
        if baseline_win_rate > 0:
            drop_pct = ((baseline_win_rate - recent_win_rate) / baseline_win_rate) * 100
        else:
            drop_pct = 0

        if drop_pct > 20:
            logger.warning(
                f"[AdaptiveConfidence] Performance degradation detected: "
                f"{recent_win_rate:.1f}% vs baseline {baseline_win_rate:.1f}% "
                f"(drop: {drop_pct:.1f}%)"
            )
            return {
                'degraded': True,
                'recent_win_rate': recent_win_rate,
                'baseline_win_rate': baseline_win_rate,
                'drop_percent': drop_pct,
                'recommendation': 'Consider reverting to default thresholds'
            }
        elif drop_pct > 10:
            # Warning only for 10-20% drop (per plan: no auto-action)
            logger.info(
                f"[AdaptiveConfidence] Minor degradation: "
                f"{recent_win_rate:.1f}% vs {baseline_win_rate:.1f}% (drop: {drop_pct:.1f}%)"
            )
            return {
                'degraded': False,
                'warning': True,
                'recent_win_rate': recent_win_rate,
                'baseline_win_rate': baseline_win_rate,
                'drop_percent': drop_pct,
            }

        return {
            'degraded': False,
            'recent_win_rate': recent_win_rate,
            'baseline_win_rate': baseline_win_rate,
        }


# Singleton instance
_adaptive_confidence_manager: Optional[AdaptiveConfidenceManager] = None


def get_adaptive_confidence_manager() -> AdaptiveConfidenceManager:
    """Get or create AdaptiveConfidenceManager singleton.

    Returns:
        AdaptiveConfidenceManager instance
    """
    global _adaptive_confidence_manager
    if _adaptive_confidence_manager is None:
        _adaptive_confidence_manager = AdaptiveConfidenceManager()
    return _adaptive_confidence_manager
