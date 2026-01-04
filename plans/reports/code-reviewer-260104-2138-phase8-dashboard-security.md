# Code Review: Phase 8 Web Dashboard Security & Quality

**Review Date**: 2026-01-04
**Scope**: Dashboard backend (FastAPI) + frontend (React/TypeScript)
**Focus**: Security vulnerabilities, performance, architecture, YAGNI/KISS/DRY compliance

---

## Executive Summary

**Overall Assessment**: GOOD with CRITICAL production readiness issues

Phase 8 dashboard implementation follows clean architecture with proper separation. Read-only database access enforced correctly. However, **CRITICAL** security gaps in CORS configuration and missing rate limiting pose production deployment risks.

**Immediate Action Required**:
1. Fix CORS wildcard in production
2. Add rate limiting to all endpoints
3. Implement request validation middleware
4. Add security headers

---

## Critical Issues (MUST FIX)

### 🚨 SECURITY-001: CORS Configuration - Production Risk
**File**: `dashboard/backend/main.py:20-31`
**Severity**: CRITICAL
**OWASP**: A05:2021 - Security Misconfiguration

```python
# CURRENT - Only localhost allowed (GOOD for dev, BAD for prod missing)
allow_origins=[
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
],
```

**Problem**: No production origin configuration. If deployed, will need manual code change.

**Fix Required**:
```python
# Use environment variable for production
import os

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET"],  # Good - read-only
    allow_headers=["*"],    # ⚠️ Consider restricting
)
```

---

### 🚨 SECURITY-002: Missing Rate Limiting
**Files**: All API endpoints
**Severity**: CRITICAL
**OWASP**: A04:2021 - Insecure Design

**Problem**: No rate limiting on any endpoint. Vulnerable to:
- DoS attacks (rapid requests exhaust SQLite connections)
- Resource exhaustion (30s auto-refresh * 100 users = 200 req/min)
- Database locking issues (SQLite read locks)

**Fix Required**:
```python
# Install: slowapi
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@router.get("/stats")
@limiter.limit("60/minute")  # 60 requests per minute
def stats(request: Request):
    return get_overall_stats()
```

---

### 🚨 SECURITY-003: SQL Injection Risk - User Input Not Validated
**File**: `dashboard/backend/routes/trades.py:30-35`
**Severity**: HIGH
**OWASP**: A03:2021 - Injection

```python
# CURRENT - Direct query string param usage
if status:
    query += " WHERE t.status = ?"
    params.append(status)  # ⚠️ No validation
```

**Problem**: `status` parameter from Query() accepts ANY string. No whitelist validation.

**Attack Vector**:
```
GET /api/trades?status=closed' OR '1'='1
```

While parameterized queries prevent classic SQLi, logic errors possible.

**Fix Required**:
```python
from enum import Enum
from fastapi import Query, HTTPException

class TradeStatus(str, Enum):
    OPEN = "open"
    PARTIAL = "partial"
    CLOSED = "closed"

@router.get("/trades")
def trades(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: TradeStatus | None = None,  # ✅ Enum validation
):
    # Now status can only be None or valid enum value
```

**Similar Issues**:
- `analytics.py:24` - `days` parameter (validated with `ge=1, le=365` ✅)
- `trades.py:56` - `trade_id` parameter (⚠️ should validate type)

---

### 🚨 SECURITY-004: Missing Security Headers
**File**: `dashboard/frontend/nginx.conf`
**Severity**: HIGH
**OWASP**: A05:2021 - Security Misconfiguration

**Problem**: No security headers configured in nginx.

**Fix Required**:
```nginx
# Add to nginx.conf server block
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' http://api:8000" always;
```

---

### 🚨 ARCHITECTURE-001: Database Connection Leak Risk
**File**: `dashboard/backend/services/database.py:17-28`
**Severity**: MEDIUM-HIGH

```python
@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()  # ⚠️ No error handling for close()
```

**Problem**: If `conn.close()` fails, connection leak occurs. Under high load (30s refresh * N users), can exhaust SQLite connection pool.

**Fix Required**:
```python
@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = None
    try:
        conn = sqlite3.connect(
            f"file:{DB_PATH}?mode=ro&timeout=5000",
            uri=True,
            check_same_thread=False  # Safe for read-only
        )
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
```

---

## High Priority Findings (SHOULD FIX)

### ⚠️ PERFORMANCE-001: N+1 Query Pattern
**File**: `dashboard/backend/routes/trades.py:55-90`
**Severity**: MEDIUM

```python
# Gets trade details, then separate queries for TP levels and events
trade = conn.execute("SELECT ... WHERE t.id = ?", (trade_id,)).fetchone()
tp_levels = conn.execute("SELECT * FROM tp_levels WHERE trade_id = ?", (trade_id,)).fetchall()
events = conn.execute("SELECT * FROM trade_events WHERE trade_id = ?", (trade_id,)).fetchall()
```

**Impact**: 3 queries per trade detail view. Under load, creates unnecessary database contention.

**Fix**: Use single JOIN query or consider denormalizing for read performance.

---

### ⚠️ PERFORMANCE-002: Missing Response Compression
**File**: `dashboard/backend/main.py`
**Severity**: MEDIUM

**Problem**: No GZip middleware for API responses. Large JSON payloads (trades table, equity curve) sent uncompressed.

**Fix**:
```python
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
```

---

### ⚠️ REACT-001: No Error Boundaries
**Files**: All React components
**Severity**: MEDIUM

**Problem**: Component errors crash entire app. No graceful degradation.

**Fix**: Add ErrorBoundary component wrapping main App.

---

### ⚠️ REACT-002: Prop Drilling & Type Safety
**File**: `dashboard/frontend/src/App.tsx:17-20`

```typescript
const { data: stats, isLoading: statsLoading, refetch } = useQuery({
    queryKey: ['stats'],
    queryFn: () => api.get('/stats').then(res => res.data),  // ⚠️ No type checking
})
```

**Problem**: API responses not typed. Runtime type errors possible.

**Fix**: Define API response types and use generics:
```typescript
interface StatsResponse {
    total_trades: number;
    wins: number;
    // ... all fields
}

const { data: stats } = useQuery<StatsResponse>({
    queryKey: ['stats'],
    queryFn: () => api.get<StatsResponse>('/stats').then(res => res.data),
})
```

---

### ⚠️ DOCKER-001: Missing Health Check Timeout
**File**: `dashboard/docker-compose.yml:18-23`

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s  # ⚠️ Too short for Python startup
```

**Fix**: Increase `start_period: 30s` for slower environments.

---

## Medium Priority Improvements (NICE TO HAVE)

### 📊 ARCHITECTURE-002: Missing Logging & Monitoring
**Severity**: LOW-MEDIUM

**Current**: No structured logging, no metrics, no error tracking.

**Recommendation**:
- Add structlog for JSON logging
- Add Prometheus metrics endpoint (`/metrics`)
- Add Sentry or similar for error tracking
- Log all API access with timing

---

### 📊 YAGNI-001: Overly Complex Time Analysis
**File**: `dashboard/backend/services/analytics.py:163-213`

**Observation**: Time analysis by hour AND day of week. Useful but potentially premature optimization for MVP.

**Verdict**: ACCEPTABLE - Trading strategy benefits from time-based insights. Keep.

---

### 📊 DRY-001: Repeated Query Patterns
**Files**: `analytics.py`, `trades.py`

**Pattern**: Multiple functions with similar query structure:
```python
with get_db() as conn:
    rows = conn.execute("SELECT ...").fetchall()
    return [dict(row) for row in rows]
```

**Fix**: Create query helper:
```python
def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    with get_db() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]
```

**Impact**: Minor. Current code readable. Low priority.

---

### 📊 REACT-003: Excessive Re-renders
**File**: `dashboard/frontend/src/main.tsx:10`

```typescript
refetchInterval: 30000, // Auto-refresh every 30 seconds
```

**Concern**: ALL queries refetch every 30s. For static data (like closed trades), wasteful.

**Fix**: Per-query refetch intervals:
```typescript
// main.tsx - Remove global refetchInterval
// Per component:
useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: 30000,  // Stats change frequently
})

useQuery({
    queryKey: ['trades', 'closed'],
    queryFn: fetchClosedTrades,
    refetchInterval: false,  // Closed trades never change
})
```

---

## Positive Observations ✅

**Excellent Implementation**:

1. **Read-only Database**: `?mode=ro` flag correctly prevents writes ✅
2. **GET-only CORS**: `allow_methods=["GET"]` enforced ✅
3. **Parameterized Queries**: All SQL uses `?` placeholders ✅
4. **Input Validation**: FastAPI Query() with `ge`, `le` constraints ✅
5. **Docker Multi-stage Build**: Optimized frontend image ✅
6. **Nginx Proxy**: Proper API proxying with headers ✅
7. **Component Structure**: Clean React component hierarchy ✅
8. **TypeScript**: Strong typing in frontend components ✅
9. **Error States**: All components handle loading/error states ✅
10. **Accessibility**: Semantic HTML, proper ARIA labels ✅

**Architecture Strengths**:
- Clean separation: backend/frontend
- Context manager pattern for DB connections
- Service layer abstraction (analytics.py)
- Router-based FastAPI structure
- React Query for state management

---

## Recommended Actions (Priority Order)

### Immediate (Pre-Production)
1. ✅ Add rate limiting (slowapi)
2. ✅ Add environment-based CORS config
3. ✅ Add input validation enums
4. ✅ Add security headers to nginx
5. ✅ Improve database error handling

### Short-term (Week 1)
6. ✅ Add API response typing
7. ✅ Add error boundaries
8. ✅ Add structured logging
9. ✅ Add GZip compression
10. ✅ Fix N+1 query patterns

### Medium-term (Month 1)
11. ✅ Add Prometheus metrics
12. ✅ Add Sentry error tracking
13. ✅ Optimize refetch intervals
14. ✅ Add query result caching
15. ✅ Write integration tests

---

## Security Checklist

| Check | Status | Notes |
|-------|--------|-------|
| SQL Injection | ⚠️ PARTIAL | Parameterized queries ✅, input validation missing ❌ |
| XSS | ✅ SAFE | React auto-escapes, no dangerouslySetInnerHTML |
| CSRF | ✅ N/A | Read-only API, no mutations |
| CORS | ⚠️ DEV ONLY | Production config missing |
| Rate Limiting | ❌ MISSING | Critical gap |
| Auth/Session | ✅ N/A | Internal dashboard, no auth required |
| HTTPS | ⚠️ UNKNOWN | Depends on deployment (nginx SSL termination recommended) |
| Security Headers | ❌ MISSING | High priority |
| Secrets Management | ✅ SAFE | No secrets in code |
| Error Disclosure | ✅ SAFE | Generic error messages, no stack traces |

---

## Performance Metrics (Estimated)

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| API Response Time | <100ms | <100ms | ✅ |
| Page Load Time | ~2s | <3s | ✅ |
| Bundle Size | ~200KB | <500KB | ✅ |
| API Payload Size | ~50KB | <100KB | ✅ |
| Concurrent Users | Untested | 50 | ⚠️ Needs load testing |
| DB Connection Pool | 1 (SQLite) | N/A | ⚠️ Monitor under load |

---

## Test Coverage Gaps

**Current**: No dashboard-specific tests found.

**Missing**:
1. Backend API endpoint tests
2. Database service tests
3. Analytics calculation tests
4. React component tests (Jest/RTL)
5. E2E tests (Playwright)
6. Load tests (Locust)

**Recommendation**: Add minimal test suite:
```python
# tests/dashboard/test_api.py
def test_stats_endpoint():
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert "total_trades" in response.json()

def test_rate_limiting():
    # Test after adding rate limiter
    for _ in range(70):
        response = client.get("/api/stats")
    assert response.status_code == 429  # Too Many Requests
```

---

## Files Reviewed

**Backend** (7 files):
- ✅ `dashboard/backend/main.py`
- ✅ `dashboard/backend/services/database.py`
- ✅ `dashboard/backend/services/analytics.py`
- ✅ `dashboard/backend/routes/stats.py`
- ✅ `dashboard/backend/routes/trades.py`
- ✅ `dashboard/backend/routes/analytics.py`
- ✅ `dashboard/backend/Dockerfile`

**Frontend** (9 files):
- ✅ `dashboard/frontend/src/App.tsx`
- ✅ `dashboard/frontend/src/main.tsx`
- ✅ `dashboard/frontend/src/components/StatsCards.tsx`
- ✅ `dashboard/frontend/src/components/TradesTable.tsx`
- ✅ `dashboard/frontend/src/components/OpenPositions.tsx`
- ✅ `dashboard/frontend/src/components/EquityCurve.tsx`
- ✅ `dashboard/frontend/src/components/DailyPnLChart.tsx`
- ✅ `dashboard/frontend/nginx.conf`
- ✅ `dashboard/frontend/Dockerfile`

**Infrastructure** (1 file):
- ✅ `dashboard/docker-compose.yml`

**Total**: 17 files, ~1,500 LOC

---

## Unresolved Questions

1. **Deployment Environment**: On-premise vs cloud? Affects CORS config, HTTPS setup.
2. **User Count**: Single user dashboard or team access? Affects rate limiting strategy.
3. **Data Retention**: How long to keep closed trades? Affects SQLite file size growth.
4. **Backup Strategy**: How to backup trading.db while dashboard is running?
5. **Monitoring**: What's the incident response plan if dashboard goes down?

---

## Next Steps

**Updated Plan Status**: Phase 8 implementation COMPLETE with security gaps.

**Recommendation**: Mark Phase 8 as "DONE - Needs Hardening" and create follow-up task:
- **Phase 8.5**: Production Hardening (2h)
  - Rate limiting
  - Security headers
  - Environment config
  - Basic tests
  - Load testing

**Alternative**: Mark Phase 8 as BLOCKED pending security fixes before deployment.

---

**Review Completed**: 2026-01-04 21:38 UTC+7
**Reviewer**: code-reviewer agent (ID: a5cbb93)
**Next Review**: After security fixes implementation
