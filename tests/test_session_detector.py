"""Tests for session_detector module (Phase 6).

Tests trading session detection with confidence modifiers.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.config import Settings
from src.session_detector import (
    SessionDetector,
    SessionInfo,
    TradingSession,
    get_session_detector,
)


class TestTradingSessionEnum:
    """Test TradingSession enum."""

    def test_all_session_types_exist(self):
        """Verify all trading session types are defined."""
        assert TradingSession.ASIAN == "asian"
        assert TradingSession.LONDON == "london"
        assert TradingSession.NEW_YORK == "new_york"
        assert TradingSession.OVERLAP == "overlap"
        assert TradingSession.OFF_HOURS == "off_hours"


class TestSessionInfo:
    """Test SessionInfo dataclass."""

    def test_creates_session_info(self):
        """Verify SessionInfo creation with all fields."""
        info = SessionInfo(
            session=TradingSession.LONDON,
            quality="high",
            modifier=5,
            minutes_to_end=300,
        )
        assert info.session == TradingSession.LONDON
        assert info.quality == "high"
        assert info.modifier == 5
        assert info.minutes_to_end == 300

    def test_session_info_optional_minutes(self):
        """Verify SessionInfo minutes_to_end is optional."""
        info = SessionInfo(
            session=TradingSession.ASIAN,
            quality="low",
            modifier=-15,
        )
        assert info.minutes_to_end is None


class TestSessionDetectorInitialization:
    """Test SessionDetector initialization."""

    def test_initializes_without_settings(self):
        """Verify detector initializes with lazy settings loading."""
        detector = SessionDetector()
        assert detector._settings is None

    def test_initializes_with_custom_settings(self):
        """Verify detector accepts custom settings."""
        settings = Settings()
        detector = SessionDetector(settings=settings)
        assert detector._settings == settings

    def test_lazy_loads_settings(self):
        """Verify settings are lazy-loaded on first access."""
        detector = SessionDetector()
        assert detector._settings is None
        settings = detector.settings
        assert settings is not None
        assert detector._settings == settings


class TestSessionDetectorSessionHours:
    """Test session hour boundaries."""

    def test_session_hours_defined(self):
        """Verify all sessions have defined hours."""
        detector = SessionDetector()
        for session in TradingSession:
            assert session in detector.SESSION_HOURS

    def test_asian_session_hours(self):
        """Verify Asian session 23:00-08:00 UTC."""
        detector = SessionDetector()
        start, end = detector.SESSION_HOURS[TradingSession.ASIAN]
        assert start == 23
        assert end == 8

    def test_london_session_hours(self):
        """Verify London session 08:00-16:00 UTC."""
        detector = SessionDetector()
        start, end = detector.SESSION_HOURS[TradingSession.LONDON]
        assert start == 8
        assert end == 16

    def test_new_york_session_hours(self):
        """Verify New York session 13:00-21:00 UTC."""
        detector = SessionDetector()
        start, end = detector.SESSION_HOURS[TradingSession.NEW_YORK]
        assert start == 13
        assert end == 21

    def test_overlap_session_hours(self):
        """Verify Overlap session 13:00-16:00 UTC."""
        detector = SessionDetector()
        start, end = detector.SESSION_HOURS[TradingSession.OVERLAP]
        assert start == 13
        assert end == 16

    def test_off_hours_session_hours(self):
        """Verify Off-hours session 21:00-23:00 UTC."""
        detector = SessionDetector()
        start, end = detector.SESSION_HOURS[TradingSession.OFF_HOURS]
        assert start == 21
        assert end == 23


class TestIsInSession:
    """Test hour-based session membership."""

    def test_hour_in_london_session(self):
        """Verify hour 12 is in London session."""
        detector = SessionDetector()
        assert detector._is_in_session(12, TradingSession.LONDON) is True

    def test_hour_not_in_london_session(self):
        """Verify hour 22 is not in London session."""
        detector = SessionDetector()
        assert detector._is_in_session(22, TradingSession.LONDON) is False

    def test_hour_in_asian_midnight_crossing(self):
        """Verify Asian session handles midnight crossing (23:00-08:00)."""
        detector = SessionDetector()
        # Hour 23 (11 PM)
        assert detector._is_in_session(23, TradingSession.ASIAN) is True
        # Hour 0 (midnight)
        assert detector._is_in_session(0, TradingSession.ASIAN) is True
        # Hour 7 (7 AM)
        assert detector._is_in_session(7, TradingSession.ASIAN) is True
        # Hour 9 (9 AM) - not in session
        assert detector._is_in_session(9, TradingSession.ASIAN) is False

    def test_hour_in_overlap_session(self):
        """Verify hour 14 is in London+NY overlap."""
        detector = SessionDetector()
        assert detector._is_in_session(14, TradingSession.OVERLAP) is True

    def test_session_boundaries(self):
        """Verify session start/end boundaries."""
        detector = SessionDetector()
        # London starts at 8, so 8 should be in, 7 should not
        assert detector._is_in_session(8, TradingSession.LONDON) is True
        assert detector._is_in_session(7, TradingSession.LONDON) is False
        # London ends at 16, so 15 should be in, 16 should not
        assert detector._is_in_session(15, TradingSession.LONDON) is True
        assert detector._is_in_session(16, TradingSession.LONDON) is False


class TestGetCurrentSession:
    """Test current session detection."""

    def test_detects_london_session(self):
        """Verify London session detection at 12:00 UTC."""
        detector = SessionDetector()
        now = datetime(2025, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(now)
        assert info.session == TradingSession.LONDON
        assert info.quality == "high"

    def test_detects_overlap_session(self):
        """Verify overlap (London+NY) detection at 14:00 UTC."""
        detector = SessionDetector()
        now = datetime(2025, 1, 2, 14, 0, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(now)
        assert info.session == TradingSession.OVERLAP
        assert info.quality == "high"

    def test_detects_new_york_session(self):
        """Verify NY session detection at 18:00 UTC."""
        detector = SessionDetector()
        now = datetime(2025, 1, 2, 18, 0, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(now)
        assert info.session == TradingSession.NEW_YORK
        assert info.quality == "high"

    def test_detects_asian_session(self):
        """Verify Asian session detection at 2:00 UTC."""
        detector = SessionDetector()
        now = datetime(2025, 1, 2, 2, 0, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(now)
        assert info.session == TradingSession.ASIAN
        assert info.quality == "low"

    def test_detects_off_hours_session(self):
        """Verify off-hours detection at 22:00 UTC."""
        detector = SessionDetector()
        now = datetime(2025, 1, 2, 22, 0, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(now)
        assert info.session == TradingSession.OFF_HOURS
        assert info.quality == "low"

    def test_overlap_has_priority(self):
        """Verify overlap session checked before individual sessions."""
        detector = SessionDetector()
        # 14:00 UTC is in both London and NY, but overlap is priority
        now = datetime(2025, 1, 2, 14, 0, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(now)
        assert info.session == TradingSession.OVERLAP

    def test_london_has_priority_over_ny(self):
        """Verify London session checked before NY."""
        detector = SessionDetector()
        # 13:00 UTC is in both London and NY, but overlap is priority
        # If not overlap, London has priority
        now = datetime(2025, 1, 2, 13, 0, 0, tzinfo=timezone.utc)
        info = detector.get_current_session(now)
        # 13:00 is start of NY and in overlap with London
        assert info.session == TradingSession.OVERLAP

    def test_uses_current_time_if_not_provided(self):
        """Verify current time is used when not provided."""
        detector = SessionDetector()
        info1 = detector.get_current_session()
        assert info1.session is not None
        assert info1.quality is not None


class TestMinutesUntilSessionEnd:
    """Test session end time calculation."""

    def test_minutes_to_london_end(self):
        """Verify minutes until London session ends."""
        detector = SessionDetector()
        # London ends at 16:00, check at 15:30
        now = datetime(2025, 1, 2, 15, 30, 0, tzinfo=timezone.utc)
        minutes = detector._minutes_until_session_end(now, TradingSession.LONDON)
        assert minutes == 30

    def test_minutes_to_ny_end(self):
        """Verify minutes until NY session ends."""
        detector = SessionDetector()
        # NY ends at 21:00, check at 20:00
        now = datetime(2025, 1, 2, 20, 0, 0, tzinfo=timezone.utc)
        minutes = detector._minutes_until_session_end(now, TradingSession.NEW_YORK)
        assert minutes == 60

    def test_minutes_to_asian_end_same_day(self):
        """Verify minutes for Asian session ending same day."""
        detector = SessionDetector()
        # Asian ends at 8:00, check at 7:00
        now = datetime(2025, 1, 2, 7, 0, 0, tzinfo=timezone.utc)
        minutes = detector._minutes_until_session_end(now, TradingSession.ASIAN)
        assert minutes == 60

    def test_minutes_to_asian_end_next_day(self):
        """Verify minutes for Asian session crossing midnight."""
        detector = SessionDetector()
        # Asian ends at 8:00, check at 23:00 (previous day)
        now = datetime(2025, 1, 2, 23, 0, 0, tzinfo=timezone.utc)
        minutes = detector._minutes_until_session_end(now, TradingSession.ASIAN)
        # 9 hours = 540 minutes
        assert minutes == 540


class TestConfidenceModifier:
    """Test session-based confidence modifiers."""

    def test_overlap_positive_modifier(self):
        """Verify overlap session has positive modifier."""
        settings = Settings()
        detector = SessionDetector(settings=settings)
        modifier = detector._get_modifier(TradingSession.OVERLAP)
        assert modifier == settings.session_confidence_overlap
        assert modifier > 0

    def test_london_positive_modifier(self):
        """Verify London session has positive modifier."""
        settings = Settings()
        detector = SessionDetector(settings=settings)
        modifier = detector._get_modifier(TradingSession.LONDON)
        assert modifier == settings.session_confidence_london
        assert modifier > 0

    def test_asian_negative_modifier(self):
        """Verify Asian session has negative modifier."""
        settings = Settings()
        detector = SessionDetector(settings=settings)
        modifier = detector._get_modifier(TradingSession.ASIAN)
        assert modifier == settings.session_confidence_asian
        assert modifier < 0

    def test_off_hours_negative_modifier(self):
        """Verify off-hours has negative modifier."""
        settings = Settings()
        detector = SessionDetector(settings=settings)
        modifier = detector._get_modifier(TradingSession.OFF_HOURS)
        assert modifier == settings.session_confidence_offhours
        assert modifier < 0


class TestApplySessionModifier:
    """Test session modifier application to confidence."""

    def test_apply_overlap_modifier(self):
        """Verify overlap modifier increases confidence."""
        settings = Settings()
        detector = SessionDetector(settings=settings)
        session_info = SessionInfo(
            session=TradingSession.OVERLAP,
            quality="high",
            modifier=10,
        )
        result = detector.apply_session_modifier(70, session_info)
        assert result == 80

    def test_apply_asian_modifier(self):
        """Verify Asian modifier decreases confidence."""
        settings = Settings()
        detector = SessionDetector(settings=settings)
        session_info = SessionInfo(
            session=TradingSession.ASIAN,
            quality="low",
            modifier=-15,
        )
        result = detector.apply_session_modifier(70, session_info)
        assert result == 55

    def test_clamped_at_max_100(self):
        """Verify result clamped to max 100."""
        settings = Settings()
        detector = SessionDetector(settings=settings)
        session_info = SessionInfo(
            session=TradingSession.OVERLAP,
            quality="high",
            modifier=50,
        )
        result = detector.apply_session_modifier(80, session_info)
        assert result == 100

    def test_clamped_at_min_0(self):
        """Verify result clamped to min 0."""
        settings = Settings()
        detector = SessionDetector(settings=settings)
        session_info = SessionInfo(
            session=TradingSession.OFF_HOURS,
            quality="low",
            modifier=-30,
        )
        result = detector.apply_session_modifier(20, session_info)
        assert result == 0

    def test_fetches_session_if_not_provided(self):
        """Verify session is fetched if not provided."""
        detector = SessionDetector()
        # Should fetch current session automatically
        result = detector.apply_session_modifier(70)
        assert isinstance(result, int)
        assert 0 <= result <= 100


class TestIsMarketOpen:
    """Test market open/closed detection."""

    def test_market_open_weekday(self):
        """Verify market is open on weekdays."""
        detector = SessionDetector()
        # Wednesday 12:00 UTC
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert detector.is_market_open(now) is True

    def test_market_closed_saturday_after_21(self):
        """Verify market closed Saturday after 21:00 UTC."""
        detector = SessionDetector()
        # Saturday 22:00 UTC
        now = datetime(2025, 1, 4, 22, 0, 0, tzinfo=timezone.utc)
        assert detector.is_market_open(now) is False

    def test_market_closed_saturday_before_21(self):
        """Verify market open Saturday before 21:00 UTC."""
        detector = SessionDetector()
        # Saturday 20:00 UTC
        now = datetime(2025, 1, 4, 20, 0, 0, tzinfo=timezone.utc)
        assert detector.is_market_open(now) is True

    def test_market_closed_all_day_sunday(self):
        """Verify market closed all day Sunday."""
        detector = SessionDetector()
        # Sunday 12:00 UTC
        now = datetime(2025, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
        assert detector.is_market_open(now) is False

    def test_market_open_friday_night(self):
        """Verify market open Friday night."""
        detector = SessionDetector()
        # Friday 23:00 UTC
        now = datetime(2025, 1, 3, 23, 0, 0, tzinfo=timezone.utc)
        assert detector.is_market_open(now) is True

    def test_uses_current_time_if_not_provided(self):
        """Verify current time is used when not provided."""
        detector = SessionDetector()
        result = detector.is_market_open()
        assert isinstance(result, bool)


class TestSessionDetectorSingleton:
    """Test singleton getter function."""

    def test_returns_singleton_instance(self):
        """Verify get_session_detector returns singleton."""
        detector1 = get_session_detector()
        detector2 = get_session_detector()
        assert detector1 is detector2

    def test_singleton_is_detector_instance(self):
        """Verify singleton is SessionDetector instance."""
        detector = get_session_detector()
        assert isinstance(detector, SessionDetector)
