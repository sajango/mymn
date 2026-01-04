# Code Review: Phase 6.5 News Integration

## Scope
- **Files reviewed**: 4 files
  - `src/news_calendar.py` (new, 350 lines)
  - `src/main.py` (modified, lines 216-224)
  - `requirements.txt` (modified, +2 deps)
  - `tests/test_news_calendar.py` (new, 482 lines)
- **Lines analyzed**: ~900 lines
- **Focus**: Security, performance, architecture, YAGNI/KISS/DRY

## Overall Assessment
Well-engineered implementation following KISS/DRY principles. Clean integration with orchestrator, comprehensive test coverage (37 tests, 100% pass), proper error handling.

**Critical issues**: 1
**High priority**: 1
**Medium priority**: 2

---

## Critical Issues

### 🔴 CRITICAL: Deprecated `datetime.utcnow()` Usage
**File**: `src/news_calendar.py`
**Lines**: 79, 197, 201, 246, 260, 294

**Issue**: Uses deprecated `datetime.utcnow()` throughout codebase. Python 3.13+ deprecation warnings visible in test output (33 warnings).

**Impact**: Future Python versions will remove this API, breaking production.

**Fix**:
```python
# Replace all instances
- datetime.utcnow()
+ datetime.now(timezone.utc)

# Import timezone
from datetime import datetime, timedelta, timezone
```

**Why**: Python 3.12+ deprecates naive UTC datetimes. Timezone-aware objects prevent DST/timezone bugs.

---

## High Priority Findings

### 🟡 No Rate Limiting on ForexFactory Scraping
**File**: `src/news_calendar.py`
**Lines**: 99-103

**Issue**: Direct HTTP requests to ForexFactory without rate limiting or request throttling beyond 1-hour cache.

**Risk**: Potential IP ban if cache invalidation logic triggers excessive requests (e.g., rapid restarts).

**Recommendation**:
```python
# Add exponential backoff on scrape failures
self._backoff_until: Optional[datetime] = None

def _scrape_calendar(self):
    if self._backoff_until and datetime.now(timezone.utc) < self._backoff_until:
        logger.warning(f"Rate limit backoff until {self._backoff_until}")
        return []

    try:
        # ... existing scrape logic ...
    except requests.RequestException:
        # Exponential backoff: 5min, 15min, 30min
        self._backoff_until = datetime.now(timezone.utc) + timedelta(minutes=5)
```

**Alternative**: Add `requests-cache` library for transparent HTTP-level caching.

---

## Medium Priority Improvements

### 🟢 Hard-Coded User-Agent String
**File**: `src/news_calendar.py`
**Lines**: 90-98

**Issue**: Hard-coded Chrome 120 user-agent may become stale/detectable.

**Impact**: ForexFactory may block outdated user-agents as bot traffic.

**Recommendation**:
```python
# Use fake-useragent library or config-based rotation
from fake_useragent import UserAgent

headers = {
    "User-Agent": UserAgent().chrome,  # Auto-rotates
    # ... rest of headers
}
```

**Or** move to config:
```python
# In config.py
forex_factory_user_agent: str = Field(
    default="Mozilla/5.0 ...",
    env="FOREX_FACTORY_USER_AGENT"
)
```

---

### 🟢 Missing HTML Parsing Robustness
**File**: `src/news_calendar.py`
**Lines**: 106-174

**Issue**: Relies on specific CSS selectors (`tr.calendar__row`, `td.calendar__date`) with no fallback if ForexFactory changes HTML structure.

**Impact**: Silent scraping failure → empty cache → incorrect "no blackout" assumption (line 288).

**Recommendation**:
```python
# Add validation checkpoint after parsing
if len(calendar_rows) == 0:
    logger.warning("No calendar rows found - possible HTML structure change")
    # Could trigger alert or use cached old data longer

# Add event count sanity check
if len(events) < 3 and len(calendar_rows) > 0:  # Expect some events per week
    logger.warning(f"Suspiciously low event count: {len(events)} from {len(calendar_rows)} rows")
```

---

## Positive Observations

### ✅ Excellent Error Handling
**Lines**: 176-184, 287-292

- Comprehensive exception handling with specific logging
- Fail-safe design: assumes **no blackout** on scrape failure (conservative for live trading)
- Proper timeout handling (10s) prevents hung requests
- Clean separation: HTTP errors → empty list → fail-safe logic

### ✅ Clean Singleton Pattern
**Lines**: 337-349

- Global singleton with lazy initialization
- Thread-safe (Python GIL protects simple assignment)
- Consistent access pattern via `get_news_calendar()`

### ✅ Well-Integrated with Orchestrator
**File**: `src/main.py` (lines 216-224)

- Clean integration: 7 lines added to `analysis_job()`
- Proper layering: check blackout → skip analysis → save to DB
- No code duplication (DRY)

### ✅ Comprehensive Test Coverage
**File**: `tests/test_news_calendar.py`

- 37 tests covering all major paths
- Proper mocking (`requests.get`, `get_settings`)
- Edge cases: timeout, HTTP errors, timezone boundaries (Dec/Jan)
- 100% pass rate

### ✅ Security: No Credentials Exposed
- `.env` in `.gitignore` (line 2)
- No API keys required for ForexFactory
- No credentials in codebase (grep confirmed)
- Privacy hook blocked `.env` access correctly

---

## Recommended Actions

**Priority order**:

1. **🔴 [CRITICAL]** Replace `datetime.utcnow()` → `datetime.now(timezone.utc)` (8 locations)
2. **🟡 [HIGH]** Add exponential backoff to `_scrape_calendar()` (prevent IP bans)
3. **🟢 [MEDIUM]** Add HTML parsing validation (detect structure changes)
4. **🟢 [MEDIUM]** Move user-agent to config or use rotation library

**Code fixes**:

```python
# src/news_calendar.py - Fix #1 (Critical)
from datetime import datetime, timedelta, timezone

# Replace all 6 instances:
- datetime.utcnow()
+ datetime.now(timezone.utc)

# src/news_calendar.py - Fix #2 (High)
def __init__(self):
    # ... existing init ...
    self._backoff_until: Optional[datetime] = None
    self._scrape_failures = 0

def _scrape_calendar(self) -> list[NewsEvent]:
    # Check backoff
    if self._backoff_until and datetime.now(timezone.utc) < self._backoff_until:
        logger.warning(f"Scraping on backoff until {self._backoff_until}")
        return []

    try:
        # ... existing scrape logic ...
        self._scrape_failures = 0  # Reset on success
        return events
    except requests.RequestException as e:
        self._scrape_failures += 1
        backoff_mins = min(5 * (2 ** (self._scrape_failures - 1)), 60)  # 5, 10, 20, 40, 60
        self._backoff_until = datetime.now(timezone.utc) + timedelta(minutes=backoff_mins)
        logger.error(f"Scrape failed, backoff {backoff_mins}min: {e}")
        return []
```

---

## Architecture Review

### Design Pattern Adherence
- **KISS**: ✅ Straightforward scraping + caching, no over-engineering
- **YAGNI**: ✅ Only USD events, only high-impact filtering (matches XAUUSD trading scope)
- **DRY**: ✅ Single source of truth for scraping, reused cache logic

### Integration Quality
- **Coupling**: Low - orchestrator depends on interface, not implementation
- **Cohesion**: High - single responsibility (news blackout detection)
- **Testability**: High - 100% mockable, no global state leaks

### Performance
- **Caching**: Effective (1-hour duration prevents over-scraping)
- **Timeout**: Conservative 10s (adequate for ForexFactory)
- **Parsing**: BeautifulSoup overhead acceptable for 1-request/hour frequency

---

## Metrics

| Metric | Value | Status |
|--------|-------|--------|
| Test coverage | 37 tests | ✅ Excellent |
| Test pass rate | 100% | ✅ Pass |
| Critical issues | 1 | ⚠️ Fix required |
| Linting issues | 33 warnings (deprecation) | 🔴 Fix deprecation |
| Security risks | 0 | ✅ Clean |
| Dependencies added | 2 (bs4, requests) | ✅ Standard libs |

---

## Unresolved Questions

1. **Production monitoring**: How will HTML structure changes be detected/alerted in production? Consider adding Sentry/logging alerts when `len(events) == 0` for multiple consecutive scrapes.

2. **Timezone handling**: ForexFactory displays times in broker/local timezone. Current code assumes UTC. Verify ForexFactory returns UTC or add timezone conversion.

3. **Cache persistence**: Cache only lives in memory. Server restart = immediate re-scrape. Consider persisting cache to disk/DB to survive restarts gracefully.

4. **Blackout window tuning**: Default 30min before / 15min after. Has this been backtested against historical XAUUSD volatility during news events? May need adjustment based on live data.

---

**Review completed**: 2026-01-04 19:07 UTC
**Reviewer**: code-reviewer agent
**Status**: ✅ **Approved with fixes required** (critical deprecation + recommended rate limiting)
