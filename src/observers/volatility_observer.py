"""Volatility spike observer for ATR-based detection.

Detects volatility spikes by comparing current ATR to cached baseline.
Triggers when ratio exceeds threshold and implements state change detection
to avoid repeat triggers during sustained spike periods.
"""

import logging
import time
from typing import List, Optional

from src.observers.base_observer import BaseObserver, ObserverEvent, ObserverEventType

logger = logging.getLogger(__name__)


class VolatilitySpikeObserver(BaseObserver):
    """Detects volatility spikes using ATR ratio method.

    Triggers when:
    - ATR_current / ATR_baseline > spike_threshold
    - Not already in spike state (state change detection)

    Attributes:
        spike_threshold: Ratio threshold for spike detection (default 1.8)
        baseline_update_interval: Seconds between baseline refreshes (default 3600)
    """

    def __init__(
        self,
        spike_threshold: float = 1.8,
        cooldown_seconds: int = 900,
        baseline_update_interval: int = 3600,
    ):
        """Initialize volatility spike observer.

        Args:
            spike_threshold: ATR ratio threshold for spike detection
            cooldown_seconds: Cooldown between triggers (default 15 min)
            baseline_update_interval: Interval to refresh ATR baseline (default 1 hour)
        """
        super().__init__(name="volatility_spike", cooldown_seconds=cooldown_seconds)
        self.spike_threshold = spike_threshold
        self.baseline_update_interval = baseline_update_interval

        # Internal state
        self._in_spike = False
        self._spike_start_time = 0.0
        self._atr_baseline = 10.0  # Gold typical default
        self._last_baseline_update = 0.0

    def check(self, market_data: dict) -> Optional[ObserverEvent]:
        """Check for volatility spike.

        Args:
            market_data: Must contain 'atr_current' key

        Returns:
            ObserverEvent if spike detected (state change), None otherwise
        """
        if not self.enabled or self.is_cooldown_active():
            return None

        atr_current = market_data.get("atr_current", 0)
        if atr_current <= 0 or self._atr_baseline <= 0:
            return None

        # Calculate ratio
        ratio = atr_current / self._atr_baseline

        # Detect spike start (state change only)
        if ratio > self.spike_threshold:
            if not self._in_spike:
                self._in_spike = True
                self._spike_start_time = time.time()
                self.mark_triggered()

                logger.info(
                    f"Volatility spike detected: ratio={ratio:.2f}, "
                    f"threshold={self.spike_threshold}"
                )

                # Calculate confidence based on how much ratio exceeds threshold
                confidence = min(1.0, (ratio - self.spike_threshold) / 0.5)

                return ObserverEvent(
                    event_type=ObserverEventType.VOLATILITY_SPIKE,
                    timestamp=time.time(),
                    data={
                        "ratio": round(ratio, 3),
                        "threshold": self.spike_threshold,
                        "atr_current": round(atr_current, 2),
                        "atr_baseline": round(self._atr_baseline, 2),
                    },
                    confidence=confidence,
                )
        else:
            # Reset spike state when ratio drops
            self._in_spike = False

        return None

    def update_baseline(self, atr_values: List[float]):
        """Update ATR baseline from recent values.

        Args:
            atr_values: List of recent ATR values (recommend last 20 candles)
        """
        if atr_values:
            self._atr_baseline = sum(atr_values) / len(atr_values)
            self._last_baseline_update = time.time()
            logger.debug(f"Volatility baseline updated: {self._atr_baseline:.2f}")

    def set_baseline(self, baseline: float):
        """Directly set ATR baseline value.

        Args:
            baseline: ATR baseline value
        """
        if baseline > 0:
            self._atr_baseline = baseline
            self._last_baseline_update = time.time()

    def needs_baseline_update(self) -> bool:
        """Check if baseline needs refreshing.

        Returns:
            True if baseline is stale and needs update
        """
        return time.time() - self._last_baseline_update > self.baseline_update_interval

    def reset_state(self):
        """Reset observer internal state."""
        self._in_spike = False
        self._spike_start_time = 0.0

    def get_status(self) -> dict:
        """Get extended status with volatility-specific info.

        Returns:
            Status dict with spike state and baseline info
        """
        status = super().get_status()
        status.update(
            {
                "in_spike": self._in_spike,
                "spike_duration": (
                    time.time() - self._spike_start_time if self._in_spike else 0
                ),
                "atr_baseline": round(self._atr_baseline, 2),
                "baseline_age_seconds": round(
                    time.time() - self._last_baseline_update, 0
                ),
                "needs_baseline_update": self.needs_baseline_update(),
            }
        )
        return status
