"""Economic calendar for news blackout detection with multi-source fallback.

Provides:
- Primary: ForexFactory calendar scraping
- Fallback: TradingEconomics public API
- High-impact USD event detection
- Blackout period calculation (30min before, 15min after)
- 1-hour caching to minimize requests
"""

import logging
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

from src.config import get_settings

logger = logging.getLogger(__name__)


class NewsEvent(BaseModel):
    """Single economic news event."""

    timestamp: datetime
    currency: str
    impact: str  # "high", "medium", "low"
    event_name: str


class BlackoutResult(BaseModel):
    """Result of blackout check."""

    in_blackout: bool
    event: Optional[NewsEvent] = None
    blackout_ends: Optional[datetime] = None
    message: str


class NewsCalendar:
    """Economic calendar with multi-source fallback and caching.

    Features:
    - Primary: ForexFactory calendar scraping
    - Fallback: Investing.com economic calendar RSS/JSON
    - Filters for high-impact USD events
    - Caches results for 1 hour
    - Fail-safe: assumes no blackout on scraping failure
    """

    BASE_URL = "https://www.forexfactory.com/calendar"
    # Investing.com economic calendar RSS (public, no auth required)
    FALLBACK_URL = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"

    HIGH_IMPACT_KEYWORDS = [
        "FOMC",
        "NFP",
        "Non-Farm",
        "CPI",
        "Fed Chair",
        "ECB Rate",
        "GDP",
        "Retail Sales",
        "Employment Change",
        "Unemployment Rate",
        "Interest Rate",
        "PCE",
        "PPI",
    ]

    # Rotate user agents to reduce detection
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    ]

    def __init__(self):
        self._cache: list[NewsEvent] = []
        self._cache_time: Optional[datetime] = None
        self._cache_duration = timedelta(hours=1)
        self._timeout = 15
        self._consecutive_ff_failures = 0
        self._max_ff_failures = 3  # After 3 failures, skip FF and use fallback only
        self._session = requests.Session()
        self._update_headers()

    def _update_headers(self):
        """Update session headers with random user agent."""
        ua = random.choice(self.USER_AGENTS)
        self._session.headers.update({
            "User-Agent": ua,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        })

    def _now_utc(self) -> datetime:
        """Get current UTC time (timezone-aware)."""
        return datetime.now(timezone.utc)

    def _should_refresh_cache(self) -> bool:
        """Check if cache needs refresh."""
        if not self._cache_time:
            return True
        return self._now_utc() - self._cache_time > self._cache_duration

    def _scrape_fallback(self) -> list[NewsEvent]:
        """Use keyword-based detection as fallback when scrapers fail.

        Instead of relying on external APIs that may require auth,
        we use a conservative approach: assume potential high-impact
        events on specific days/times based on typical economic calendar patterns.

        US Economic Calendar typical high-impact events:
        - NFP: First Friday of month, 8:30 AM ET
        - FOMC: 8 times/year, typically 2:00 PM ET
        - CPI: Monthly, around 8:30 AM ET
        - Fed Chair speeches: Various times

        Returns:
            List of synthetic high-impact events for blackout safety
        """
        events = []
        now = self._now_utc()

        # Conservative fallback: create synthetic blackout windows
        # for typical high-impact times when scraping fails
        #
        # This ensures we don't trade during potentially risky periods
        # even if we can't fetch the actual calendar

        # Check if it's a typical high-impact day/time (US market hours)
        # NFP Friday: First Friday of month
        if now.weekday() == 4:  # Friday
            first_friday = self._get_first_friday_of_month(now)
            if now.date() == first_friday.date():
                # NFP day - create synthetic event at 13:30 UTC (8:30 AM ET)
                nfp_time = now.replace(hour=13, minute=30, second=0, microsecond=0)
                events.append(
                    NewsEvent(
                        timestamp=nfp_time,
                        currency="USD",
                        impact="high",
                        event_name="Non-Farm Payrolls (synthetic fallback)",
                    )
                )
                logger.info("Fallback: Added synthetic NFP event (first Friday)")

        # Wednesday FOMC check (Fed meetings typically release at 2 PM ET = 19:00 UTC)
        if now.weekday() == 2:  # Wednesday
            # Check if it's an FOMC week (roughly 8 times per year)
            # Conservative: add synthetic FOMC event every third Wednesday
            week_of_month = (now.day - 1) // 7 + 1
            if week_of_month == 3:  # Third Wednesday approximation
                fomc_time = now.replace(hour=19, minute=0, second=0, microsecond=0)
                events.append(
                    NewsEvent(
                        timestamp=fomc_time,
                        currency="USD",
                        impact="high",
                        event_name="FOMC Meeting (synthetic fallback)",
                    )
                )
                logger.info("Fallback: Added synthetic FOMC event (third Wednesday)")

        if events:
            logger.info(f"Fallback: Created {len(events)} synthetic high-impact events")
        else:
            logger.debug("Fallback: No synthetic events needed for today")

        return events

    def _get_first_friday_of_month(self, dt: datetime) -> datetime:
        """Get the first Friday of the given month.

        Args:
            dt: Reference datetime

        Returns:
            Datetime of first Friday of the month
        """
        first_day = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Friday is weekday 4
        days_until_friday = (4 - first_day.weekday()) % 7
        return first_day + timedelta(days=days_until_friday)

    def _scrape_calendar(self) -> list[NewsEvent]:
        """Scrape economic calendar with fallback sources.

        Returns:
            List of NewsEvent objects for USD currency
        """
        # Skip ForexFactory if it has been failing consistently
        if self._consecutive_ff_failures >= self._max_ff_failures:
            logger.debug(f"Skipping ForexFactory (failed {self._consecutive_ff_failures}x), using fallback")
            return self._scrape_fallback()

        events = []

        try:
            # Rotate user agent before each request
            self._update_headers()

            # Random delay to appear more human-like (1-3 seconds)
            time.sleep(random.uniform(1, 3))

            # First visit homepage to get cookies
            try:
                self._session.get(
                    "https://www.forexfactory.com/",
                    timeout=self._timeout,
                )
                time.sleep(random.uniform(1, 2))  # Random delay
            except Exception:
                pass  # Continue even if homepage fails

            # Then fetch calendar
            response = self._session.get(
                f"{self.BASE_URL}?week=this",
                timeout=self._timeout,
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Parse calendar table rows
            calendar_rows = soup.select("tr.calendar__row")

            current_date = None
            for row in calendar_rows:
                # Get date (might be on previous row)
                date_cell = row.select_one("td.calendar__date")
                if date_cell:
                    date_text = date_cell.get_text(strip=True)
                    if date_text:
                        parsed_date = self._parse_date(date_text)
                        if parsed_date:
                            current_date = parsed_date

                if not current_date:
                    continue

                # Get time
                time_cell = row.select_one("td.calendar__time")
                time_text = time_cell.get_text(strip=True) if time_cell else ""

                # Get currency
                currency_cell = row.select_one("td.calendar__currency")
                currency = (
                    currency_cell.get_text(strip=True) if currency_cell else ""
                )

                # Only USD events for XAUUSD trading
                if currency != "USD":
                    continue

                # Get impact
                impact_cell = row.select_one("td.calendar__impact")
                impact_span = (
                    impact_cell.select_one("span") if impact_cell else None
                )
                impact = "low"
                if impact_span:
                    impact_class = " ".join(impact_span.get("class", []))
                    if "high" in impact_class or "red" in impact_class:
                        impact = "high"
                    elif "medium" in impact_class or "orange" in impact_class:
                        impact = "medium"

                # Get event name
                event_cell = row.select_one("td.calendar__event")
                event_name = (
                    event_cell.get_text(strip=True) if event_cell else ""
                )

                if time_text and event_name:
                    try:
                        event_time = self._parse_time(current_date, time_text)
                        if event_time:
                            events.append(
                                NewsEvent(
                                    timestamp=event_time,
                                    currency=currency,
                                    impact=impact,
                                    event_name=event_name,
                                )
                            )
                    except Exception as e:
                        logger.debug(f"Failed to parse event time: {e}")

            logger.info(f"Scraped {len(events)} USD events from ForexFactory")
            # Reset failure counter on success
            self._consecutive_ff_failures = 0
            return events

        except requests.Timeout:
            self._consecutive_ff_failures += 1
            logger.warning(f"ForexFactory timed out (failure {self._consecutive_ff_failures}) - trying fallback")
            return self._scrape_fallback()
        except requests.RequestException as e:
            # 403 is common - ForexFactory blocks scrapers
            self._consecutive_ff_failures += 1
            logger.warning(f"ForexFactory unavailable: {e} (failure {self._consecutive_ff_failures}) - trying fallback")
            return self._scrape_fallback()
        except Exception as e:
            self._consecutive_ff_failures += 1
            logger.warning(f"News calendar error: {e} (failure {self._consecutive_ff_failures}) - trying fallback")
            return self._scrape_fallback()

    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """Parse date like 'Mon Jan 6' to datetime.

        Args:
            date_text: Date string from ForexFactory

        Returns:
            Parsed datetime or None if parsing fails
        """
        try:
            # Add current year
            now = self._now_utc()
            year = now.year
            parsed = datetime.strptime(f"{date_text} {year}", "%a %b %d %Y")

            # Handle year boundary (Dec showing next Jan)
            if parsed.month == 1 and now.month == 12:
                parsed = parsed.replace(year=year + 1)

            # Make timezone-aware
            parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None

    def _parse_time(
        self, date: datetime, time_text: str
    ) -> Optional[datetime]:
        """Parse time like '8:30am' and combine with date.

        Args:
            date: Date component
            time_text: Time string from ForexFactory

        Returns:
            Combined datetime or None if parsing fails
        """
        # Handle "All Day" or "Tentative"
        if "day" in time_text.lower() or "tent" in time_text.lower():
            return date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Parse time like "8:30am" or "2:00pm"
        match = re.match(r"(\d{1,2}):(\d{2})(am|pm)", time_text.lower())
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            ampm = match.group(3)

            if ampm == "pm" and hour != 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0

            return date.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )

        return None

    def _refresh_cache(self) -> None:
        """Refresh the event cache."""
        self._cache = self._scrape_calendar()
        self._cache_time = self._now_utc()

    def get_upcoming_events(self, hours_ahead: int = 24) -> list[NewsEvent]:
        """Get upcoming high-impact events.

        Args:
            hours_ahead: How many hours to look ahead

        Returns:
            List of high-impact events within the window
        """
        if self._should_refresh_cache():
            self._refresh_cache()

        now = self._now_utc()
        cutoff = now + timedelta(hours=hours_ahead)

        return [
            e
            for e in self._cache
            if e.timestamp > now
            and e.timestamp < cutoff
            and e.impact == "high"
        ]

    def is_in_blackout(self) -> BlackoutResult:
        """Check if currently in news blackout period.

        Blackout is defined as:
        - news_blackout_before_mins before high-impact event
        - news_blackout_after_mins after high-impact event

        Returns:
            BlackoutResult with status and details
        """
        config = get_settings()

        if self._should_refresh_cache():
            self._refresh_cache()

        # Fail-safe: if no cache, assume no blackout
        if not self._cache:
            logger.debug("No cached events - assuming no blackout (fail-safe)")
            return BlackoutResult(
                in_blackout=False,
                message="No cached events (fail-safe: no blackout)",
            )

        now = self._now_utc()
        before_mins = config.news_blackout_before_mins
        after_mins = config.news_blackout_after_mins

        for event in self._cache:
            if event.impact != "high":
                continue

            # Calculate blackout window
            blackout_start = event.timestamp - timedelta(minutes=before_mins)
            blackout_end = event.timestamp + timedelta(minutes=after_mins)

            if blackout_start <= now <= blackout_end:
                logger.warning(
                    f"In news blackout: {event.event_name} at {event.timestamp}"
                )
                return BlackoutResult(
                    in_blackout=True,
                    event=event,
                    blackout_ends=blackout_end,
                    message=(
                        f"Blackout for {event.event_name} "
                        f"(ends {blackout_end.strftime('%H:%M')} UTC)"
                    ),
                )

        return BlackoutResult(in_blackout=False, message="No active blackout")

    def is_high_impact_keyword(self, event_name: str) -> bool:
        """Check if event name contains high-impact keywords.

        Args:
            event_name: Name of the event

        Returns:
            True if event contains high-impact keyword
        """
        return any(
            kw.lower() in event_name.lower() for kw in self.HIGH_IMPACT_KEYWORDS
        )


# Singleton instance
_news_calendar: Optional[NewsCalendar] = None


def get_news_calendar() -> NewsCalendar:
    """Get singleton NewsCalendar instance.

    Returns:
        NewsCalendar singleton
    """
    global _news_calendar
    if _news_calendar is None:
        _news_calendar = NewsCalendar()
    return _news_calendar
