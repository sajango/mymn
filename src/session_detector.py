"""Trading session detector with confidence modifiers.

Sessions (UTC-based):
- Asian: 23:00-08:00 UTC (Tokyo/Sydney)
- London: 08:00-16:00 UTC
- New York: 13:00-21:00 UTC
- Overlap (London+NY): 13:00-16:00 UTC
- Off-hours: 21:00-23:00 UTC

Confidence modifiers from config:
- Overlap: +10 (best liquidity)
- London: +5
- NY: +5
- Asian: -15 (low liquidity for gold)
- Off-hours: -20
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from src.config import get_settings

logger = logging.getLogger(__name__)


class TradingSession(str, Enum):
    """Trading session names."""

    ASIAN = "asian"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "overlap"  # London + NY
    OFF_HOURS = "off_hours"


@dataclass
class SessionInfo:
    """Session detection result."""

    session: TradingSession
    quality: str  # high, medium, low
    modifier: int  # Confidence adjustment
    minutes_to_end: Optional[int] = None


class SessionDetector:
    """Detects current trading session and applies confidence modifiers.

    Uses UTC time for consistent session detection across timezones.
    Session boundaries and modifiers are configurable via settings.
    """

    # Session hours (UTC) - start and end hours
    SESSION_HOURS = {
        TradingSession.ASIAN: (23, 8),  # 23:00-08:00 (crosses midnight)
        TradingSession.LONDON: (8, 16),  # 08:00-16:00
        TradingSession.NEW_YORK: (13, 21),  # 13:00-21:00
        TradingSession.OVERLAP: (13, 16),  # 13:00-16:00 (London + NY)
        TradingSession.OFF_HOURS: (21, 23),  # 21:00-23:00
    }

    SESSION_QUALITY = {
        TradingSession.OVERLAP: "high",
        TradingSession.LONDON: "high",
        TradingSession.NEW_YORK: "high",
        TradingSession.ASIAN: "low",
        TradingSession.OFF_HOURS: "low",
    }

    def __init__(self, settings=None):
        self._settings = settings

    @property
    def settings(self):
        """Lazy load settings."""
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    def _get_modifier(self, session: TradingSession) -> int:
        """Get confidence modifier for session.

        Args:
            session: Trading session

        Returns:
            Confidence modifier (positive or negative)
        """
        modifiers = {
            TradingSession.OVERLAP: self.settings.session_confidence_overlap,
            TradingSession.LONDON: self.settings.session_confidence_london,
            TradingSession.NEW_YORK: self.settings.session_confidence_ny,
            TradingSession.ASIAN: self.settings.session_confidence_asian,
            TradingSession.OFF_HOURS: self.settings.session_confidence_offhours,
        }
        return modifiers.get(session, 0)

    def _is_in_session(self, hour: int, session: TradingSession) -> bool:
        """Check if hour falls within session.

        Args:
            hour: UTC hour (0-23)
            session: Session to check

        Returns:
            True if hour is in session
        """
        start, end = self.SESSION_HOURS[session]

        # Handle sessions that cross midnight (e.g., Asian: 23-08)
        if start > end:
            return hour >= start or hour < end
        return start <= hour < end

    def _minutes_until_session_end(
        self, now: datetime, session: TradingSession
    ) -> int:
        """Calculate minutes until session ends.

        Args:
            now: Current UTC datetime
            session: Current session

        Returns:
            Minutes until session end
        """
        _, end = self.SESSION_HOURS[session]
        current_hour = now.hour
        current_minute = now.minute

        if current_hour < end:
            minutes_left = (end - current_hour - 1) * 60 + (60 - current_minute)
        else:
            # Session ends next day (for Asian session)
            hours_until_midnight = 24 - current_hour
            minutes_left = (hours_until_midnight + end) * 60 - current_minute

        return max(0, minutes_left)

    def get_current_session(
        self, now: Optional[datetime] = None
    ) -> SessionInfo:
        """Detect current trading session.

        Args:
            now: UTC datetime (defaults to current time)

        Returns:
            SessionInfo with session details
        """
        if now is None:
            now = datetime.now(timezone.utc)

        hour = now.hour

        # Check overlap first (highest priority)
        if self._is_in_session(hour, TradingSession.OVERLAP):
            session = TradingSession.OVERLAP
        elif self._is_in_session(hour, TradingSession.LONDON):
            session = TradingSession.LONDON
        elif self._is_in_session(hour, TradingSession.NEW_YORK):
            session = TradingSession.NEW_YORK
        elif self._is_in_session(hour, TradingSession.OFF_HOURS):
            session = TradingSession.OFF_HOURS
        else:
            session = TradingSession.ASIAN

        minutes_to_end = self._minutes_until_session_end(now, session)

        info = SessionInfo(
            session=session,
            quality=self.SESSION_QUALITY[session],
            modifier=self._get_modifier(session),
            minutes_to_end=minutes_to_end,
        )

        logger.debug(
            f"Session: {session.value}, quality={info.quality}, "
            f"modifier={info.modifier:+d}, ends in {minutes_to_end}m"
        )

        return info

    def apply_session_modifier(
        self, base_confidence: int, session_info: Optional[SessionInfo] = None
    ) -> int:
        """Apply session modifier to confidence score.

        Args:
            base_confidence: Original confidence score (0-100)
            session_info: Session info (fetched if None)

        Returns:
            Adjusted confidence score (0-100)
        """
        if session_info is None:
            session_info = self.get_current_session()

        adjusted = base_confidence + session_info.modifier

        # Clamp to 0-100
        result = max(0, min(100, adjusted))

        logger.debug(
            f"Confidence: {base_confidence} {session_info.modifier:+d} = {result}"
        )

        return result

    def is_market_open(self, now: Optional[datetime] = None) -> bool:
        """Check if forex market is open.

        Market closed Saturday 21:00 UTC to Sunday 21:00 UTC.

        Args:
            now: UTC datetime (defaults to current time)

        Returns:
            True if market is open
        """
        if now is None:
            now = datetime.now(timezone.utc)

        weekday = now.weekday()  # 0=Monday, 6=Sunday
        hour = now.hour

        # Saturday after 21:00 UTC -> closed
        if weekday == 5 and hour >= 21:
            return False

        # All day Sunday -> closed
        if weekday == 6:
            return False

        # Sunday before 21:00 is handled above (weekday==6)
        return True


# Lazy singleton
_session_detector: Optional[SessionDetector] = None


def get_session_detector() -> SessionDetector:
    """Get or create session detector singleton."""
    global _session_detector
    if _session_detector is None:
        _session_detector = SessionDetector()
    return _session_detector
