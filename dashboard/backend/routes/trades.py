"""Trade history API endpoints."""

from enum import Enum
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from services.analytics import get_open_positions
from services.database import get_db

router = APIRouter(prefix="/api", tags=["trades"])


class TradeStatusFilter(str, Enum):
    """Valid trade status filter values."""

    OPEN = "open"
    PARTIAL = "partial"
    CLOSED = "closed"


@router.get("/trades")
def trades(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[TradeStatusFilter] = Query(None, description="Filter by status"),
):
    """Get trade history with pagination."""
    with get_db() as conn:
        query = """
            SELECT
                t.*,
                s.confidence,
                s.action as signal_action,
                s.wave_position
            FROM trades t
            LEFT JOIN signals s ON t.signal_id = s.id
        """
        params: list = []

        if status:
            query += " WHERE t.status = ?"
            params.append(status.value)

        query += " ORDER BY t.open_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()

        # Get total count for pagination
        count_query = "SELECT COUNT(*) FROM trades"
        if status:
            count_query += " WHERE status = ?"
            total = conn.execute(count_query, (status.value,)).fetchone()[0]
        else:
            total = conn.execute(count_query).fetchone()[0]

        return {
            "trades": [dict(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/trades/{trade_id}")
def trade_detail(trade_id: int):
    """Get single trade with events."""
    with get_db() as conn:
        # Trade details
        trade = conn.execute("""
            SELECT
                t.*,
                s.confidence,
                s.action as signal_action,
                s.wave_position
            FROM trades t
            LEFT JOIN signals s ON t.signal_id = s.id
            WHERE t.id = ?
        """, (trade_id,)).fetchone()

        if not trade:
            return {"error": "Trade not found"}

        # TP levels
        tp_levels = conn.execute(
            "SELECT * FROM tp_levels WHERE trade_id = ? ORDER BY price",
            (trade_id,)
        ).fetchall()

        # Trade events
        events = conn.execute(
            "SELECT * FROM trade_events WHERE trade_id = ? ORDER BY created_at",
            (trade_id,)
        ).fetchall()

        return {
            "trade": dict(trade),
            "tp_levels": [dict(tp) for tp in tp_levels],
            "events": [dict(e) for e in events],
        }


@router.get("/positions")
def positions():
    """Get current open positions."""
    return get_open_positions()


@router.get("/signals")
def signals(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get signal history."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM signals
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()

        total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]

        return {
            "signals": [dict(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
