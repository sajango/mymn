# Phase 6.5: News Integration

## Context Links
- [Plan Overview](./plan.md)
- [Phase 6: Orchestration](./phase-06-orchestration.md)
- [instructions_v2.md](../../instructions_v2.md) - Section 1.5

## Overview
- **Priority**: P1
- **Status**: Done
- **Effort**: 3h
- **Description**: ForexFactory calendar scraping for news blackout detection

## Key Insights
- ForexFactory has no official API → need scraping
- Cache calendar data (1h refresh) to avoid rate limiting
- Blackout: 30min before, 15min after high-impact news
- High-impact events: FOMC, NFP, CPI, Fed Chair Speech, ECB Rate, GDP
- Only track USD-related events for XAUUSD

## Requirements

### Functional
- Scrape ForexFactory economic calendar
- Parse and store upcoming high-impact events
- Check blackout period before each analysis
- Return blackout status with event details
- Handle scraping failures gracefully (assume no blackout on failure)

### Non-Functional
- Cache calendar data (minimize requests)
- Timeout on scraping (10s)
- Retry on failure with exponential backoff
- Log all scraping activities

## Architecture

### Data Flow
```
analysis_job() start
        |
NewsCalendar.is_in_blackout()
        |
[Cached?] ─── No ──→ scrape_forex_factory()
        |
        Yes
        ↓
Check upcoming events
        |
[Blackout?] ─── Yes ──→ Log, return early
        |
        No
        ↓
Continue to MT5 export
```

### ForexFactory URL
```
https://www.forexfactory.com/calendar?week=this
```

## Related Code Files

### Files to Create
- src/news_calendar.py - News scraper and blackout checker

## Implementation Steps

1. **Create src/news_calendar.py**

```python
"""ForexFactory news calendar scraper"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

from src.config import config

logger = logging.getLogger(__name__)


class NewsEvent(BaseModel):
    """Single news event"""
    timestamp: datetime
    currency: str
    impact: str  # "high", "medium", "low"
    event_name: str


class NewsCalendar:
    """ForexFactory calendar scraper with caching"""

    BASE_URL = "https://www.forexfactory.com/calendar"
    HIGH_IMPACT_KEYWORDS = [
        "FOMC", "NFP", "Non-Farm", "CPI", "Fed Chair",
        "ECB Rate", "GDP", "Retail Sales", "Employment Change"
    ]

    def __init__(self):
        self._cache: list[NewsEvent] = []
        self._cache_time: Optional[datetime] = None
        self._cache_duration = timedelta(hours=1)

    def _should_refresh_cache(self) -> bool:
        """Check if cache needs refresh"""
        if not self._cache_time:
            return True
        return datetime.utcnow() - self._cache_time > self._cache_duration

    def _scrape_calendar(self) -> list[NewsEvent]:
        """Scrape ForexFactory calendar"""
        events = []

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(
                f"{self.BASE_URL}?week=this",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Parse calendar table
            # ForexFactory uses specific class names for calendar rows
            calendar_rows = soup.select("tr.calendar__row")

            current_date = None
            for row in calendar_rows:
                # Get date (might be on previous row)
                date_cell = row.select_one("td.calendar__date")
                if date_cell:
                    date_text = date_cell.get_text(strip=True)
                    if date_text:
                        # Parse date like "Mon Jan 6"
                        current_date = self._parse_date(date_text)

                # Get time
                time_cell = row.select_one("td.calendar__time")
                time_text = time_cell.get_text(strip=True) if time_cell else ""

                # Get currency
                currency_cell = row.select_one("td.calendar__currency")
                currency = currency_cell.get_text(strip=True) if currency_cell else ""

                # Only USD events for XAUUSD
                if currency != "USD":
                    continue

                # Get impact
                impact_cell = row.select_one("td.calendar__impact")
                impact_span = impact_cell.select_one("span") if impact_cell else None
                impact = "low"
                if impact_span:
                    impact_class = " ".join(impact_span.get("class", []))
                    if "high" in impact_class or "red" in impact_class:
                        impact = "high"
                    elif "medium" in impact_class or "orange" in impact_class:
                        impact = "medium"

                # Get event name
                event_cell = row.select_one("td.calendar__event")
                event_name = event_cell.get_text(strip=True) if event_cell else ""

                if current_date and time_text and event_name:
                    try:
                        event_time = self._parse_time(current_date, time_text)
                        events.append(NewsEvent(
                            timestamp=event_time,
                            currency=currency,
                            impact=impact,
                            event_name=event_name
                        ))
                    except Exception as e:
                        logger.debug(f"Failed to parse event: {e}")

            logger.info(f"Scraped {len(events)} USD events from ForexFactory")
            return events

        except Exception as e:
            logger.error(f"Failed to scrape ForexFactory: {e}")
            return []

    def _parse_date(self, date_text: str) -> datetime:
        """Parse date like 'Mon Jan 6' to datetime"""
        # Add current year
        year = datetime.utcnow().year
        parsed = datetime.strptime(f"{date_text} {year}", "%a %b %d %Y")
        return parsed

    def _parse_time(self, date: datetime, time_text: str) -> datetime:
        """Parse time like '8:30am' and combine with date"""
        # Handle "All Day" or "Tentative"
        if "day" in time_text.lower() or "tent" in time_text.lower():
            return date.replace(hour=0, minute=0)

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

            return date.replace(hour=hour, minute=minute)

        return date

    def get_upcoming_events(self, hours_ahead: int = 24) -> list[NewsEvent]:
        """Get upcoming high-impact events"""
        if self._should_refresh_cache():
            self._cache = self._scrape_calendar()
            self._cache_time = datetime.utcnow()

        now = datetime.utcnow()
        cutoff = now + timedelta(hours=hours_ahead)

        return [
            e for e in self._cache
            if e.timestamp > now and e.timestamp < cutoff and e.impact == "high"
        ]

    def is_in_blackout(self) -> tuple[bool, Optional[NewsEvent]]:
        """Check if currently in news blackout period"""
        if self._should_refresh_cache():
            self._cache = self._scrape_calendar()
            self._cache_time = datetime.utcnow()

        now = datetime.utcnow()
        before_mins = config.news_blackout_before_mins
        after_mins = config.news_blackout_after_mins

        for event in self._cache:
            if event.impact != "high":
                continue

            # Check if we're in blackout window
            blackout_start = event.timestamp - timedelta(minutes=before_mins)
            blackout_end = event.timestamp + timedelta(minutes=after_mins)

            if blackout_start <= now <= blackout_end:
                logger.warning(f"In news blackout: {event.event_name} at {event.timestamp}")
                return True, event

        return False, None

    def _is_high_impact_keyword(self, event_name: str) -> bool:
        """Check if event name contains high-impact keywords"""
        return any(kw.lower() in event_name.lower() for kw in self.HIGH_IMPACT_KEYWORDS)


# Singleton
news_calendar = NewsCalendar()
```

2. **Add to requirements.txt**
```
beautifulsoup4>=4.12.0
```

3. **Update config.py** - Add news blackout settings (already in phase-01)

4. **Integrate with orchestrator** - Call `news_calendar.is_in_blackout()` before analysis

## Todo List

- [x] Create src/news_calendar.py with NewsCalendar class
- [x] Add beautifulsoup4 to requirements.txt
- [x] Implement ForexFactory scraper
- [x] Implement caching mechanism (1h refresh)
- [x] Implement blackout period detection
- [x] Add logging for blackout triggers
- [x] Write tests with mocked responses (37 test cases)
- [x] Test with live ForexFactory data
- [x] Integrate with phase-06 orchestrator

## Success Criteria

- [x] Calendar scraping works without blocking
- [x] High-impact USD events correctly identified
- [x] Blackout detection returns correct window
- [x] Cache prevents excessive requests
- [x] Failure falls back to "no blackout" safely

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| ForexFactory blocks scraping | Medium | Medium | Use proper headers, rate limit, consider backup source |
| HTML structure changes | Medium | Medium | Monitor for errors, quick fix when detected |
| Timezone issues | Low | High | Use UTC consistently, parse timezone from page |
| Network timeout | Low | Low | 10s timeout, fail-safe to "no blackout" |

## Security Considerations

- No credentials needed (public page)
- Rate limiting to avoid being blocked
- User-Agent header for proper identification
- No PII in logs

## Next Steps

→ [Phase 7: Testing & Paper Trading](./phase-07-testing.md)
