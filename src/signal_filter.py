"""Signal consistency filter - prevents rapid direction flip-flopping.

Applies hysteresis logic:
- Same direction signals: always allowed
- Direction reversals: require cooldown + higher confidence

Integrates with RiskGuard as additional validation layer.

Phase 02 Enhancement: Applies session/wave confidence modifiers before validation.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from src.config import get_settings
from src.database import Database, get_database
from src.signal_parser import TradingSignal
from src.adaptive_confidence import get_adaptive_confidence_manager

logger = logging.getLogger(__name__)


class FilterReason(str, Enum):
    """Filter rejection reasons."""
    DIRECTION_COOLDOWN = "direction_cooldown"
    LOW_CONFIDENCE_REVERSAL = "low_confidence_reversal"
    RAPID_FLIP = "rapid_flip"


@dataclass
class FilterResult:
    """Result of signal consistency check."""
    passed: bool
    reason: Optional[FilterReason] = None
    message: str = ""
    previous_action: Optional[str] = None
    minutes_since_last: Optional[int] = None
    adjusted_confidence: Optional[int] = None  # Phase 02: Adjusted confidence after modifiers
    original_confidence: Optional[int] = None  # Phase 02: Original confidence before modifiers
    modifier_applied: int = 0  # Phase 02: Total modifier applied


class SignalConsistencyFilter:
    """Filter that prevents rapid signal direction changes.

    Logic:
    1. Same direction as recent signals -> ALLOW
    2. Direction change within cooldown period -> BLOCK
    3. Direction change with low confidence -> BLOCK
    4. Direction change after cooldown with high confidence -> ALLOW

    Configuration via Settings:
    - direction_change_cooldown_minutes: Min time before direction change
    - direction_change_min_confidence: Min confidence for reversal
    - rapid_flip_threshold_minutes: Detect rapid flip-flop pattern
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        direction_change_cooldown_minutes: Optional[int] = None,
        direction_change_min_confidence: Optional[int] = None,
        rapid_flip_threshold_minutes: Optional[int] = None,
    ):
        self._db = db
        settings = get_settings()
        
        # Use config values or provided overrides
        self.direction_change_cooldown_minutes = (
            direction_change_cooldown_minutes 
            if direction_change_cooldown_minutes is not None
            else settings.direction_change_cooldown_minutes
        )
        self.direction_change_min_confidence = (
            direction_change_min_confidence
            if direction_change_min_confidence is not None
            else settings.direction_change_min_confidence
        )
        self.rapid_flip_threshold_minutes = (
            rapid_flip_threshold_minutes
            if rapid_flip_threshold_minutes is not None
            else settings.rapid_flip_threshold_minutes
        )

    @property
    def db(self) -> Database:
        """Lazy load database."""
        if self._db is None:
            self._db = get_database()
        return self._db

    def check(self, signal: TradingSignal) -> FilterResult:
        """Check if signal passes consistency filter.

        Applies session/wave confidence modifiers before validation
        when adaptive_modifiers_enabled is True.

        Args:
            signal: Trading signal to validate

        Returns:
            FilterResult with pass/fail and reason
        """
        # Skip filter for NO_TRADE signals
        if not signal.is_tradeable:
            return FilterResult(passed=True, message="not_tradeable_skip")

        # Phase 02: Apply session/wave modifiers to confidence
        original_confidence = signal.signal.confidence
        adjusted_confidence = original_confidence
        modifier_applied = 0

        settings = get_settings()
        if getattr(settings, 'adaptive_modifiers_enabled', True):
            try:
                adaptive_manager = get_adaptive_confidence_manager()

                # Extract session/wave/regime from signal
                session = None
                wave = None
                regime = None

                if signal.session_context:
                    session = signal.session_context.current_session
                if signal.wave_analysis:
                    wave = signal.wave_analysis.wave_position or signal.wave_analysis.current_wave
                if signal.market_regime:
                    regime = signal.market_regime.classification

                # Get modifiers
                modifiers = adaptive_manager.get_session_wave_modifiers(
                    session=session,
                    wave=wave,
                    regime=regime
                )

                modifier_applied = modifiers.combined_modifier
                adjusted_confidence = max(0, min(100, original_confidence + modifier_applied))

                if modifier_applied != 0:
                    logger.info(
                        f"[SignalFilter] Confidence adjusted: {original_confidence} + {modifier_applied} = "
                        f"{adjusted_confidence} (session={session}, wave={wave}, regime={regime})"
                    )

                # Update signal confidence for downstream validation
                signal.signal.confidence = adjusted_confidence

            except Exception as e:
                logger.warning(f"[SignalFilter] Failed to apply modifiers: {e}")
                # Continue with original confidence on error

        # Get recent tradeable signals
        recent = self._get_recent_tradeable_signals(limit=5)

        if not recent:
            logger.info("[SignalFilter] No recent signals, allowing")
            return FilterResult(
                passed=True,
                message="no_history",
                adjusted_confidence=adjusted_confidence,
                original_confidence=original_confidence,
                modifier_applied=modifier_applied,
            )

        last_signal = recent[0]
        last_action = last_signal["action"]
        current_action = signal.signal.action.value

        # Same direction - always allow
        if self._is_same_direction(current_action, last_action):
            logger.info(f"[SignalFilter] Same direction ({current_action}), allowing")
            return FilterResult(
                passed=True,
                message="same_direction",
                previous_action=last_action,
                adjusted_confidence=adjusted_confidence,
                original_confidence=original_confidence,
                modifier_applied=modifier_applied,
            )

        # Direction reversal - apply hysteresis
        minutes_since = self._minutes_since(last_signal["created_at"])

        logger.info(
            f"[SignalFilter] Direction change: {last_action} -> {current_action}, "
            f"{minutes_since}min since last"
        )

        # Check cooldown
        if minutes_since < self.direction_change_cooldown_minutes:
            logger.warning(
                f"[SignalFilter] BLOCKED: Cooldown active "
                f"({minutes_since}min < {self.direction_change_cooldown_minutes}min)"
            )
            return FilterResult(
                passed=False,
                reason=FilterReason.DIRECTION_COOLDOWN,
                message=(
                    f"Direction change blocked: {minutes_since}min since last "
                    f"{last_action}, need {self.direction_change_cooldown_minutes}min cooldown"
                ),
                previous_action=last_action,
                minutes_since_last=minutes_since,
                adjusted_confidence=adjusted_confidence,
                original_confidence=original_confidence,
                modifier_applied=modifier_applied,
            )

        # Check confidence for reversal (uses adjusted confidence)
        confidence = signal.signal.confidence
        if confidence < self.direction_change_min_confidence:
            logger.warning(
                f"[SignalFilter] BLOCKED: Low confidence reversal "
                f"({confidence}% < {self.direction_change_min_confidence}%)"
            )
            return FilterResult(
                passed=False,
                reason=FilterReason.LOW_CONFIDENCE_REVERSAL,
                message=(
                    f"Reversal blocked: confidence {confidence}% below "
                    f"{self.direction_change_min_confidence}% threshold"
                ),
                previous_action=last_action,
                minutes_since_last=minutes_since,
                adjusted_confidence=adjusted_confidence,
                original_confidence=original_confidence,
                modifier_applied=modifier_applied,
            )

        # Check for rapid flip-flop pattern
        if self._is_rapid_flip_pattern(recent, current_action):
            logger.warning("[SignalFilter] BLOCKED: Rapid flip-flop pattern detected")
            return FilterResult(
                passed=False,
                reason=FilterReason.RAPID_FLIP,
                message="Rapid flip-flop pattern detected in recent signals",
                previous_action=last_action,
                minutes_since_last=minutes_since,
                adjusted_confidence=adjusted_confidence,
                original_confidence=original_confidence,
                modifier_applied=modifier_applied,
            )

        # Reversal approved
        logger.info(
            f"[SignalFilter] Direction change approved: {last_action} -> {current_action} "
            f"(cooldown passed, confidence {confidence}%)"
        )
        return FilterResult(
            passed=True,
            message="reversal_approved",
            previous_action=last_action,
            minutes_since_last=minutes_since,
            adjusted_confidence=adjusted_confidence,
            original_confidence=original_confidence,
            modifier_applied=modifier_applied,
        )

    def _get_recent_tradeable_signals(self, limit: int = 5) -> list[dict]:
        """Get recent tradeable signals (BUY/SELL only).

        Args:
            limit: Maximum signals to return

        Returns:
            List of signal dicts, newest first
        """
        all_recent = self.db.get_recent_signals(limit=limit * 2)

        tradeable = [
            s for s in all_recent
            if s["action"] in ("BUY", "BUY_LIMIT", "SELL", "SELL_LIMIT")
        ]

        return tradeable[:limit]

    def _is_same_direction(self, action1: str, action2: str) -> bool:
        """Check if two actions are same direction.

        Args:
            action1: First action
            action2: Second action

        Returns:
            True if both BUY-ish or both SELL-ish
        """
        buy_actions = {"BUY", "BUY_LIMIT"}
        sell_actions = {"SELL", "SELL_LIMIT"}

        action1_is_buy = action1 in buy_actions
        action2_is_buy = action2 in buy_actions

        return action1_is_buy == action2_is_buy

    def _minutes_since(self, timestamp_str: str) -> int:
        """Calculate minutes since timestamp.

        Args:
            timestamp_str: ISO format timestamp string

        Returns:
            Minutes elapsed
        """
        try:
            # Handle various timestamp formats
            ts_str = timestamp_str.replace("Z", "+00:00")
            if " " in ts_str and "T" not in ts_str:
                ts_str = ts_str.replace(" ", "T")
            if "+" not in ts_str and "-" not in ts_str[-6:]:
                ts_str += "+00:00"

            ts = datetime.fromisoformat(ts_str)
            now = datetime.now(timezone.utc)

            # Handle naive datetime
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            delta = now - ts
            return int(delta.total_seconds() / 60)
        except Exception as e:
            logger.warning(f"Failed to parse timestamp {timestamp_str}: {e}")
            return 999  # Large number to allow signal through

    def _is_rapid_flip_pattern(
        self, recent_signals: list[dict], current_action: str
    ) -> bool:
        """Detect rapid flip-flop pattern in recent signals.

        Pattern: A -> B -> A within threshold period

        Args:
            recent_signals: Recent signals, newest first
            current_action: Current signal action

        Returns:
            True if flip-flop pattern detected
        """
        if len(recent_signals) < 2:
            return False

        # Check if we're flip-flopping: current matches 2-signals-ago
        # and middle signal is opposite
        last_action = recent_signals[0]["action"]
        prev_action = recent_signals[1]["action"]

        # Pattern: current same as prev_prev, but different from last
        current_is_buy = current_action in ("BUY", "BUY_LIMIT")
        prev_is_buy = prev_action in ("BUY", "BUY_LIMIT")
        last_is_buy = last_action in ("BUY", "BUY_LIMIT")

        is_flip_flop = (
            current_is_buy == prev_is_buy and  # Current matches 2-ago
            current_is_buy != last_is_buy       # Different from last
        )

        if not is_flip_flop:
            return False

        # Check if all happened within threshold
        oldest_time = recent_signals[1]["created_at"]
        minutes_span = self._minutes_since(oldest_time)

        return minutes_span < self.rapid_flip_threshold_minutes * 2


# Lazy singleton
_signal_filter: Optional[SignalConsistencyFilter] = None


def get_signal_filter() -> SignalConsistencyFilter:
    """Get or create SignalConsistencyFilter singleton."""
    global _signal_filter
    if _signal_filter is None:
        from src.config import get_settings
        settings = get_settings()
        _signal_filter = SignalConsistencyFilter(
            direction_change_cooldown_minutes=getattr(
                settings, "direction_change_cooldown_minutes", 60
            ),
            direction_change_min_confidence=getattr(
                settings, "direction_change_min_confidence", 75
            ),
            rapid_flip_threshold_minutes=getattr(
                settings, "rapid_flip_threshold_minutes", 30
            ),
        )
    return _signal_filter
