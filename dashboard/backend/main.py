"""FastAPI Dashboard API for MT5 Trading System.

Provides read-only access to trading data for visualization.
Run separately from the trading bot to avoid interference.
"""

import os
from enum import Enum

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from routes import analytics, stats, trades
from services.database import check_db_exists


# Rate limiter (60 requests per minute per IP)
limiter = Limiter(key_func=get_remote_address)


# Trade status enum for validation
class TradeStatusEnum(str, Enum):
    OPEN = "open"
    PARTIAL = "partial"
    CLOSED = "closed"


app = FastAPI(
    title="MT5 Trading Dashboard API",
    description="Read-only API for trading performance analytics",
    version="1.0.0",
)

# Add rate limiter to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Environment-based CORS origins
cors_origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
cors_origins = [o.strip() for o in cors_origins if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# Global exception handler for database errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors gracefully."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# Register routes
app.include_router(stats.router)
app.include_router(trades.router)
app.include_router(analytics.router)


@app.get("/")
@limiter.limit("60/minute")
def root(request: Request):
    """API root - health check."""
    return {
        "status": "ok",
        "api": "MT5 Trading Dashboard",
        "version": "1.0.0",
    }


@app.get("/api/health")
@limiter.limit("60/minute")
def health(request: Request):
    """Health check endpoint."""
    db_exists = check_db_exists()
    return {
        "status": "healthy" if db_exists else "degraded",
        "database": "connected" if db_exists else "not found",
    }
