"""Key level proximity observer for support/resistance detection.

Monitors price proximity to key support/resistance levels stored in database.
Uses ATR-normalized buffer zones for distance calculation.
"""

import logging
import time
from typing import Dict, List, Optional

from src.observers.base_observer import BaseObserver, ObserverEvent, ObserverEventType

logger = logging.getLogger(__name__)


class KeyLevelObserver(BaseObserver):
    """Detects proximity to key support/resistance levels.

    Triggers when:
    - Price within ATR * atr_factor of any key level
    - Level not already triggered in cooldown period (per-level cooldowns)

    Attributes:
        atr_factor: Multiplier for ATR-based buffer zone (default 1.0)
    """

    def __init__(
        self,
        atr_factor: float = 1.0,
        cooldown_seconds: int = 900,
    ):
        """Initialize key level observer.

        Args:
            atr_factor: ATR multiplier for proximity buffer calculation
            cooldown_seconds: Cooldown between triggers per level (default 15 min)
        """
        super().__init__(name="key_level", cooldown_seconds=cooldown_seconds)
        self.atr_factor = atr_factor

        # Internal state
        self._key_levels: List[float] = []
        self._triggered_levels: Dict[float, float] = {}  # level -> trigger timestamp
        self._atr_baseline = 10.0  # Default for Gold

    def check(self, market_data: dict) -> Optional[ObserverEvent]:
        """Check for key level proximity.

        Args:
            market_data: Must contain 'current_price' key

        Returns:
            ObserverEvent if proximity detected, None otherwise
        """
        if not self.enabled:
            return None

        current_price = market_data.get("current_price", 0)
        if current_price <= 0:
            return None

        # Calculate buffer zone
        buffer = self._atr_baseline * self.atr_factor

        # Check proximity to each level
        now = time.time()
        for level in self._key_levels:
            distance = abs(current_price - level)

            if distance <= buffer:
                # Check level-specific cooldown
                last_trigger = self._triggered_levels.get(level, 0)
                if now - last_trigger > self.cooldown_seconds:
                    # Trigger event for this level
                    self._triggered_levels[level] = now
                    self.mark_triggered()

                    # Calculate proximity percentage (100% = at level, 0% = at buffer edge)
                    proximity_pct = (1 - distance / buffer) * 100 if buffer > 0 else 100

                    logger.info(
                        f"Key level proximity detected: price={current_price:.2f}, "
                        f"level={level:.2f}, distance={distance:.2f}"
                    )

                    return ObserverEvent(
                        event_type=ObserverEventType.KEY_LEVEL_PROXIMITY,
                        timestamp=now,
                        data={
                            "level": round(level, 2),
                            "current_price": round(current_price, 2),
                            "distance": round(distance, 2),
                            "buffer": round(buffer, 2),
                            "proximity_percent": round(proximity_pct, 1),
                        },
                        confidence=proximity_pct / 100,
                    )

        return None

    def update_levels(self, levels: List[float]):
        """Update monitored key levels.

        Args:
            levels: List of price levels to monitor
        """
        self._key_levels = sorted(levels) if levels else []
        logger.debug(f"Key levels updated: {len(self._key_levels)} levels")

    def add_level(self, level: float):
        """Add a single key level to monitor.

        Args:
            level: Price level to add
        """
        if level > 0 and level not in self._key_levels:
            self._key_levels.append(level)
            self._key_levels.sort()

    def remove_level(self, level: float):
        """Remove a key level from monitoring.

        Args:
            level: Price level to remove
        """
        if level in self._key_levels:
            self._key_levels.remove(level)
            self._triggered_levels.pop(level, None)

    def update_atr_baseline(self, atr: float):
        """Update ATR baseline for buffer calculation.

        Args:
            atr: Current ATR value
        """
        if atr > 0:
            self._atr_baseline = atr

    def reset_state(self):
        """Reset observer state (clear level-specific cooldowns)."""
        self._triggered_levels = {}

    def clear_stale_triggers(self):
        """Remove expired triggers from tracking dict."""
        now = time.time()
        self._triggered_levels = {
            level: ts
            for level, ts in self._triggered_levels.items()
            if now - ts < self.cooldown_seconds
        }

    def get_status(self) -> dict:
        """Get extended status with level-specific info.

        Returns:
            Status dict with key levels and trigger info
        """
        status = super().get_status()
        status.update(
            {
                "key_levels_count": len(self._key_levels),
                "key_levels": [round(l, 2) for l in self._key_levels[:10]],  # Top 10
                "triggered_levels_count": len(self._triggered_levels),
                "atr_baseline": round(self._atr_baseline, 2),
                "buffer_distance": round(self._atr_baseline * self.atr_factor, 2),
            }
        )
        return status

    def get_nearest_level(self, price: float) -> Optional[dict]:
        """Find the nearest key level to current price.

        Args:
            price: Current price

        Returns:
            Dict with level and distance, or None if no levels
        """
        if not self._key_levels or price <= 0:
            return None

        nearest = min(self._key_levels, key=lambda l: abs(l - price))
        distance = abs(price - nearest)
        buffer = self._atr_baseline * self.atr_factor

        return {
            "level": round(nearest, 2),
            "distance": round(distance, 2),
            "within_buffer": distance <= buffer,
            "buffer": round(buffer, 2),
        }
