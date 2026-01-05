"""Tests for news_calendar module (Phase 6.5).

Tests ForexFactory scraping and news blackout detection.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.news_calendar import (
    BlackoutResult,
    NewsCalendar,
    NewsEvent,
    get_news_calendar,
)


class TestNewsEvent:
    """Test NewsEvent model."""

    def test_creates_news_event(self):
        """Verify NewsEvent creation with all fields."""
        event = NewsEvent(
            timestamp=datetime(2026, 1, 4, 14, 30),
            currency="USD",
            impact="high",
            event_name="Non-Farm Payrolls",
        )
        assert event.currency == "USD"
        assert event.impact == "high"
        assert event.event_name == "Non-Farm Payrolls"

    def test_event_serializes_to_dict(self):
        """Verify event can be serialized."""
        event = NewsEvent(
            timestamp=datetime(2026, 1, 4, 14, 30),
            currency="USD",
            impact="high",
            event_name="FOMC",
        )
        d = event.model_dump()
        assert d["currency"] == "USD"
        assert d["impact"] == "high"


class TestBlackoutResult:
    """Test BlackoutResult model."""

    def test_not_in_blackout(self):
        """Verify BlackoutResult when not in blackout."""
        result = BlackoutResult(in_blackout=False, message="No active blackout")
        assert result.in_blackout is False
        assert result.event is None
        assert result.blackout_ends is None

    def test_in_blackout_with_event(self):
        """Verify BlackoutResult when in blackout."""
        event = NewsEvent(
            timestamp=datetime(2026, 1, 4, 14, 30),
            currency="USD",
            impact="high",
            event_name="CPI",
        )
        result = BlackoutResult(
            in_blackout=True,
            event=event,
            blackout_ends=datetime(2026, 1, 4, 14, 45),
            message="Blackout for CPI",
        )
        assert result.in_blackout is True
        assert result.event.event_name == "CPI"
        assert result.blackout_ends is not None


class TestNewsCalendarInit:
    """Test NewsCalendar initialization."""

    def test_initializes_with_empty_cache(self):
        """Verify cache starts empty."""
        calendar = NewsCalendar()
        assert calendar._cache == []
        assert calendar._cache_time is None

    def test_cache_duration_is_one_hour(self):
        """Verify cache duration is 1 hour."""
        calendar = NewsCalendar()
        assert calendar._cache_duration == timedelta(hours=1)

    def test_timeout_is_15_seconds(self):
        """Verify scraping timeout is 15 seconds (increased for fallback resilience)."""
        calendar = NewsCalendar()
        assert calendar._timeout == 15


class TestCacheRefresh:
    """Test cache refresh logic."""

    def test_should_refresh_when_empty(self):
        """Verify refresh needed when cache is empty."""
        calendar = NewsCalendar()
        assert calendar._should_refresh_cache() is True

    def test_should_not_refresh_when_fresh(self):
        """Verify no refresh when cache is fresh."""
        calendar = NewsCalendar()
        calendar._cache_time = datetime.now(timezone.utc)
        calendar._cache = []  # Even empty cache counts
        assert calendar._should_refresh_cache() is False

    def test_should_refresh_when_stale(self):
        """Verify refresh when cache is stale."""
        calendar = NewsCalendar()
        calendar._cache_time = datetime.now(timezone.utc) - timedelta(hours=2)
        calendar._cache = []
        assert calendar._should_refresh_cache() is True


class TestDateParsing:
    """Test date parsing functions."""

    def test_parses_weekday_date(self):
        """Verify parsing of date like 'Mon Jan 6'."""
        calendar = NewsCalendar()
        result = calendar._parse_date("Mon Jan 6")
        assert result.month == 1
        assert result.day == 6

    def test_parses_date_with_year_boundary(self):
        """Verify December date doesn't break year."""
        calendar = NewsCalendar()
        result = calendar._parse_date("Mon Dec 30")
        assert result.month == 12
        assert result.day == 30

    def test_returns_none_for_invalid_date(self):
        """Verify None returned for invalid date."""
        calendar = NewsCalendar()
        result = calendar._parse_date("Invalid Date")
        assert result is None


class TestTimeParsing:
    """Test time parsing functions."""

    def test_parses_am_time(self):
        """Verify parsing of '8:30am'."""
        calendar = NewsCalendar()
        base = datetime(2026, 1, 4)
        result = calendar._parse_time(base, "8:30am")
        assert result.hour == 8
        assert result.minute == 30

    def test_parses_pm_time(self):
        """Verify parsing of '2:30pm'."""
        calendar = NewsCalendar()
        base = datetime(2026, 1, 4)
        result = calendar._parse_time(base, "2:30pm")
        assert result.hour == 14
        assert result.minute == 30

    def test_parses_noon(self):
        """Verify parsing of '12:00pm'."""
        calendar = NewsCalendar()
        base = datetime(2026, 1, 4)
        result = calendar._parse_time(base, "12:00pm")
        assert result.hour == 12
        assert result.minute == 0

    def test_parses_midnight(self):
        """Verify parsing of '12:00am'."""
        calendar = NewsCalendar()
        base = datetime(2026, 1, 4)
        result = calendar._parse_time(base, "12:00am")
        assert result.hour == 0
        assert result.minute == 0

    def test_parses_all_day(self):
        """Verify parsing of 'All Day' returns midnight."""
        calendar = NewsCalendar()
        base = datetime(2026, 1, 4)
        result = calendar._parse_time(base, "All Day")
        assert result.hour == 0
        assert result.minute == 0

    def test_parses_tentative(self):
        """Verify parsing of 'Tentative' returns midnight."""
        calendar = NewsCalendar()
        base = datetime(2026, 1, 4)
        result = calendar._parse_time(base, "Tentative")
        assert result.hour == 0
        assert result.minute == 0

    def test_returns_none_for_invalid_time(self):
        """Verify None returned for invalid time format."""
        calendar = NewsCalendar()
        base = datetime(2026, 1, 4)
        result = calendar._parse_time(base, "invalid")
        assert result is None


class TestHighImpactKeywords:
    """Test high-impact event keyword detection."""

    def test_detects_fomc(self):
        """Verify FOMC is detected as high-impact."""
        calendar = NewsCalendar()
        assert calendar.is_high_impact_keyword("FOMC Rate Decision") is True

    def test_detects_nfp(self):
        """Verify NFP is detected as high-impact."""
        calendar = NewsCalendar()
        assert calendar.is_high_impact_keyword("Non-Farm Payrolls") is True

    def test_detects_cpi(self):
        """Verify CPI is detected as high-impact."""
        calendar = NewsCalendar()
        assert calendar.is_high_impact_keyword("CPI m/m") is True

    def test_does_not_detect_low_impact(self):
        """Verify low-impact events are not flagged."""
        calendar = NewsCalendar()
        assert calendar.is_high_impact_keyword("Consumer Sentiment") is False


class TestBlackoutDetection:
    """Test news blackout period detection."""

    @patch("src.news_calendar.get_settings")
    def test_not_in_blackout_when_no_events(self, mock_settings):
        """Verify no blackout when no events cached."""
        mock_settings.return_value = MagicMock(
            news_blackout_before_mins=30,
            news_blackout_after_mins=15,
        )
        calendar = NewsCalendar()
        calendar._cache = []
        calendar._cache_time = datetime.now(timezone.utc)

        result = calendar.is_in_blackout()
        assert result.in_blackout is False

    @patch("src.news_calendar.get_settings")
    def test_in_blackout_before_event(self, mock_settings):
        """Verify blackout 30 min before high-impact event."""
        mock_settings.return_value = MagicMock(
            news_blackout_before_mins=30,
            news_blackout_after_mins=15,
        )
        calendar = NewsCalendar()

        now = datetime.now(timezone.utc)
        event_time = now + timedelta(minutes=15)  # Event in 15 min
        calendar._cache = [
            NewsEvent(
                timestamp=event_time,
                currency="USD",
                impact="high",
                event_name="FOMC",
            )
        ]
        calendar._cache_time = now

        result = calendar.is_in_blackout()
        assert result.in_blackout is True
        assert result.event.event_name == "FOMC"

    @patch("src.news_calendar.get_settings")
    def test_in_blackout_after_event(self, mock_settings):
        """Verify blackout 15 min after high-impact event."""
        mock_settings.return_value = MagicMock(
            news_blackout_before_mins=30,
            news_blackout_after_mins=15,
        )
        calendar = NewsCalendar()

        now = datetime.now(timezone.utc)
        event_time = now - timedelta(minutes=10)  # Event was 10 min ago
        calendar._cache = [
            NewsEvent(
                timestamp=event_time,
                currency="USD",
                impact="high",
                event_name="NFP",
            )
        ]
        calendar._cache_time = now

        result = calendar.is_in_blackout()
        assert result.in_blackout is True

    @patch("src.news_calendar.get_settings")
    def test_not_in_blackout_outside_window(self, mock_settings):
        """Verify no blackout when outside window."""
        mock_settings.return_value = MagicMock(
            news_blackout_before_mins=30,
            news_blackout_after_mins=15,
        )
        calendar = NewsCalendar()

        now = datetime.now(timezone.utc)
        event_time = now + timedelta(hours=2)  # Event in 2 hours
        calendar._cache = [
            NewsEvent(
                timestamp=event_time,
                currency="USD",
                impact="high",
                event_name="GDP",
            )
        ]
        calendar._cache_time = now

        result = calendar.is_in_blackout()
        assert result.in_blackout is False

    @patch("src.news_calendar.get_settings")
    def test_ignores_medium_impact_events(self, mock_settings):
        """Verify medium-impact events don't trigger blackout."""
        mock_settings.return_value = MagicMock(
            news_blackout_before_mins=30,
            news_blackout_after_mins=15,
        )
        calendar = NewsCalendar()

        now = datetime.now(timezone.utc)
        event_time = now + timedelta(minutes=15)
        calendar._cache = [
            NewsEvent(
                timestamp=event_time,
                currency="USD",
                impact="medium",  # Not high
                event_name="Industrial Production",
            )
        ]
        calendar._cache_time = now

        result = calendar.is_in_blackout()
        assert result.in_blackout is False


class TestUpcomingEvents:
    """Test upcoming events retrieval."""

    def test_returns_high_impact_within_window(self):
        """Verify returns high-impact events within time window."""
        calendar = NewsCalendar()

        now = datetime.now(timezone.utc)
        calendar._cache = [
            NewsEvent(
                timestamp=now + timedelta(hours=2),
                currency="USD",
                impact="high",
                event_name="FOMC",
            ),
            NewsEvent(
                timestamp=now + timedelta(hours=6),
                currency="USD",
                impact="medium",
                event_name="Industrial",
            ),
        ]
        calendar._cache_time = now

        events = calendar.get_upcoming_events(hours_ahead=4)
        assert len(events) == 1
        assert events[0].event_name == "FOMC"

    def test_excludes_past_events(self):
        """Verify past events are excluded."""
        calendar = NewsCalendar()

        now = datetime.now(timezone.utc)
        calendar._cache = [
            NewsEvent(
                timestamp=now - timedelta(hours=1),  # Past
                currency="USD",
                impact="high",
                event_name="FOMC",
            ),
        ]
        calendar._cache_time = now

        events = calendar.get_upcoming_events(hours_ahead=4)
        assert len(events) == 0


class TestScrapeCalendar:
    """Test ForexFactory scraping with session-based requests."""

    @patch("src.news_calendar.requests.Session")
    def test_handles_timeout(self, mock_session_cls):
        """Verify timeout triggers fallback and returns empty on both failures."""
        import requests

        mock_session = MagicMock()
        mock_session.get.side_effect = requests.Timeout()
        mock_session_cls.return_value = mock_session

        calendar = NewsCalendar()
        result = calendar._scrape_calendar()
        # Fallback also fails with timeout, so result is empty
        assert result == []

    @patch("src.news_calendar.requests.Session")
    def test_handles_http_error(self, mock_session_cls):
        """Verify HTTP error triggers fallback and returns empty on both failures."""
        import requests

        mock_session = MagicMock()
        mock_session.get.side_effect = requests.HTTPError()
        mock_session_cls.return_value = mock_session

        calendar = NewsCalendar()
        result = calendar._scrape_calendar()
        # Fallback also fails, so result is empty
        assert result == []

    @patch("src.news_calendar.requests.Session")
    @patch("src.news_calendar.time.sleep")
    def test_parses_valid_html(self, mock_sleep, mock_session_cls):
        """Verify parsing of valid HTML response."""
        html = """
        <html><body>
        <tr class="calendar__row">
            <td class="calendar__date">Mon Jan 6</td>
            <td class="calendar__time">8:30am</td>
            <td class="calendar__currency">USD</td>
            <td class="calendar__impact">
                <span class="high"></span>
            </td>
            <td class="calendar__event">Non-Farm Payrolls</td>
        </tr>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        calendar = NewsCalendar()
        result = calendar._scrape_calendar()

        assert len(result) == 1
        assert result[0].currency == "USD"
        assert result[0].impact == "high"
        assert result[0].event_name == "Non-Farm Payrolls"

    @patch("src.news_calendar.requests.Session")
    @patch("src.news_calendar.time.sleep")
    def test_filters_non_usd_events(self, mock_sleep, mock_session_cls):
        """Verify non-USD events are filtered out."""
        html = """
        <html><body>
        <tr class="calendar__row">
            <td class="calendar__date">Mon Jan 6</td>
            <td class="calendar__time">8:30am</td>
            <td class="calendar__currency">EUR</td>
            <td class="calendar__impact">
                <span class="high"></span>
            </td>
            <td class="calendar__event">ECB Meeting</td>
        </tr>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        calendar = NewsCalendar()
        result = calendar._scrape_calendar()

        assert len(result) == 0


class TestSingleton:
    """Test singleton pattern."""

    def test_returns_same_instance(self):
        """Verify get_news_calendar returns singleton."""
        cal1 = get_news_calendar()
        cal2 = get_news_calendar()
        assert cal1 is cal2

    def test_is_news_calendar_instance(self):
        """Verify singleton is NewsCalendar instance."""
        cal = get_news_calendar()
        assert isinstance(cal, NewsCalendar)
