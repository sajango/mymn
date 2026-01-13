"""Volatility compression observer for squeeze detection.

Detects low volatility consolidation periods using dual approach:
1. Bollinger Band squeeze (bandwidth < threshold)
2. ATR compression (ATR < baseline × threshold)

Market principle: Low volatility periods act like "coiled springs" - quiet
before major moves. Squeeze breakouts precede 50-80% of significant moves.
"""

import logging
import statistics
import time
from collections import deque
from typing import Optional

from src.observers.base_observer import BaseObserver, ObserverEvent, ObserverEventType

logger = logging.getLogger(__name__)


class VolatilityCompressionObserver(BaseObserver):
    """Detects volatility compression (squeeze) patterns.

    Triggers when:
    - Bollinger BandWidth < threshold (default 4%)
    - ATR ratio < threshold (default 0.7)
    - Both conditions met for min_bars consecutive bars

    Attributes:
        bb_threshold: Bollinger BandWidth squeeze threshold (%)
        atr_threshold: ATR compression ratio threshold
        min_bars: Minimum consecutive compression bars for trigger
    """

    def __init__(
        self,
        bb_threshold: float = 4.0,
        atr_threshold: float = 0.7,
        min_bars: int = 3,
        cooldown_seconds: int = 900,
        bb_period: int = 20,
        atr_period: int = 14,
    ):
        """Initialize compression observer.

        Args:
            bb_threshold: BandWidth % below which squeeze detected
            atr_threshold: ATR ratio below which compression detected
            min_bars: Consecutive bars needed for high confidence
            cooldown_seconds: Cooldown between triggers (default 15 min)
            bb_period: Bollinger Band SMA period
            atr_period: ATR calculation period
        """
        super().__init__(name="compression", cooldown_seconds=cooldown_seconds)
        self.bb_threshold = bb_threshold
        self.atr_threshold = atr_threshold
        self.min_bars = min_bars
        self.bb_period = bb_period
        self.atr_period = atr_period

        # Internal state - bounded deques prevent memory leaks
        self._closes: deque = deque(maxlen=bb_period)
        self._true_ranges: deque = deque(maxlen=atr_period)
        self._atr_history: deque = deque(maxlen=20)  # For baseline calculation
        self._compression_bars = 0
        self._last_bb_width = 0.0
        self._last_atr_ratio = 1.0

    def check(self, market_data: dict) -> Optional[ObserverEvent]:
        """Check for volatility compression.

        Args:
            market_data: Must contain 'close', 'high', 'low', 'prev_close'
                - close: Current bar close price (required, must be positive)
                - high: Current bar high price (required, must be positive)
                - low: Current bar low price (required, must be positive)
                - prev_close: Previous bar close price (optional, defaults to close)

        Returns:
            ObserverEvent if compression detected, None otherwise
        """
        if not self.enabled:
            return None

        # Extract and validate required data
        close = market_data.get("close")
        high = market_data.get("high")
        low = market_data.get("low")
        prev_close = market_data.get("prev_close")

        # Validate required fields
        if close is None or high is None or low is None:
            return None

        # Type and value validation
        try:
            close = float(close)
            high = float(high)
            low = float(low)
            prev_close = float(prev_close) if prev_close is not None else close
        except (TypeError, ValueError):
            logger.debug("Invalid price data types")
            return None

        # Sanity checks for price data
        if close <= 0 or high <= 0 or low <= 0:
            return None

        if high < low:
            logger.debug("Invalid bar: high < low")
            return None

        # Update price history
        self._closes.append(close)

        # Calculate True Range
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        self._true_ranges.append(tr)

        # Need enough data for calculations
        if len(self._closes) < self.bb_period:
            return None

        # Calculate Bollinger BandWidth
        bb_squeezed, bb_width = self._check_bb_squeeze()

        # Calculate ATR compression
        atr_compressed, atr_ratio = self._check_atr_compression()

        # Store for status
        self._last_bb_width = bb_width
        self._last_atr_ratio = atr_ratio

        # Check dual confirmation
        if bb_squeezed and atr_compressed:
            self._compression_bars += 1

            # Check if met minimum bar requirement
            if self._compression_bars >= self.min_bars:
                if not self.is_cooldown_active():
                    self.mark_triggered()

                    # Calculate confidence (increases with compression duration)
                    confidence = min(1.0, self._compression_bars / 10)

                    # Determine severity based on strength
                    if bb_width < 2.0 or atr_ratio < 0.5:
                        severity = "extreme"
                    elif bb_width < 3.0 or atr_ratio < 0.65:
                        severity = "high"
                    else:
                        severity = "moderate"

                    logger.info(
                        f"Compression detected: bb_width={bb_width:.2f}%, "
                        f"atr_ratio={atr_ratio:.3f}, bars={self._compression_bars}"
                    )

                    return ObserverEvent(
                        event_type=ObserverEventType.VOLATILITY_COMPRESSION,
                        timestamp=time.time(),
                        data={
                            "bb_width": round(bb_width, 2),
                            "atr_ratio": round(atr_ratio, 3),
                            "bars_in_compression": self._compression_bars,
                            "severity": severity,
                            "current_price": round(close, 2),
                        },
                        confidence=confidence,
                    )
        else:
            # Reset compression counter when condition breaks
            self._compression_bars = 0

        return None

    def _check_bb_squeeze(self) -> tuple[bool, float]:
        """Check for Bollinger Band squeeze.

        Returns:
            (is_squeezed, bandwidth_percentage)
        """
        closes = list(self._closes)
        sma = statistics.mean(closes)
        std_dev = statistics.stdev(closes) if len(closes) > 1 else 0

        if sma <= 0:
            return False, 0.0

        # Calculate bandwidth as percentage
        upper = sma + (2 * std_dev)
        lower = sma - (2 * std_dev)
        bandwidth = ((upper - lower) / sma) * 100

        return bandwidth < self.bb_threshold, bandwidth

    def _check_atr_compression(self) -> tuple[bool, float]:
        """Check for ATR compression.

        Returns:
            (is_compressed, atr_ratio)
        """
        if len(self._true_ranges) < self.atr_period:
            return False, 1.0

        current_atr = statistics.mean(self._true_ranges)
        self._atr_history.append(current_atr)

        if len(self._atr_history) < 5:
            return False, 1.0

        atr_baseline = statistics.mean(self._atr_history)
        if atr_baseline <= 0:
            return False, 1.0

        atr_ratio = current_atr / atr_baseline
        return atr_ratio < self.atr_threshold, atr_ratio

    def reset_state(self):
        """Reset observer state."""
        self._closes.clear()
        self._true_ranges.clear()
        self._atr_history.clear()
        self._compression_bars = 0
        self._last_bb_width = 0.0
        self._last_atr_ratio = 1.0

    def get_status(self) -> dict:
        """Get extended status with compression info.

        Returns:
            Status dict with compression metrics
        """
        status = super().get_status()
        status.update(
            {
                "bb_width": round(self._last_bb_width, 2),
                "atr_ratio": round(self._last_atr_ratio, 3),
                "compression_bars": self._compression_bars,
                "bb_threshold": self.bb_threshold,
                "atr_threshold": self.atr_threshold,
                "min_bars": self.min_bars,
                "data_points": len(self._closes),
            }
        )
        return status
