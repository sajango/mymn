"""Analytics API endpoints for charts."""

from fastapi import APIRouter, Query

from dashboard.backend.services.analytics import get_daily_pnl, get_equity_curve
from dashboard.backend.services.database import get_db

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/equity")
def equity_curve():
    """Get equity curve data for line chart."""
    return get_equity_curve()


@router.get("/daily-pnl")
def daily_pnl(days: int = Query(30, ge=1, le=365)):
    """Get daily P&L for bar chart."""
    return get_daily_pnl(days)


@router.get("/skipped-signals")
def skipped_signals(days: int = Query(7, ge=1, le=90)):
    """Get summary of skipped signals by reason."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                reason,
                COUNT(*) as count,
                AVG(spread_pips) as avg_spread,
                AVG(confidence) as avg_confidence
            FROM skipped_signals
            WHERE created_at >= datetime('now', ? || ' days')
            GROUP BY reason
            ORDER BY count DESC
        """, (f"-{days}",)).fetchall()

        return [
            {
                "reason": row["reason"],
                "count": row["count"],
                "avg_spread": round(row["avg_spread"], 2) if row["avg_spread"] else None,
                "avg_confidence": round(row["avg_confidence"], 1) if row["avg_confidence"] else None,
            }
            for row in rows
        ]


@router.get("/weekly-summary")
def weekly_summary():
    """Get week-over-week performance summary."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                strftime('%Y-W%W', close_time) as week,
                COUNT(*) as trades,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                ROUND(SUM(profit), 2) as pnl
            FROM trades
            WHERE status = 'closed'
            GROUP BY week
            ORDER BY week DESC
            LIMIT 12
        """).fetchall()

        return [
            {
                "week": row["week"],
                "trades": row["trades"],
                "wins": row["wins"],
                "win_rate": round((row["wins"] / row["trades"] * 100) if row["trades"] > 0 else 0, 1),
                "pnl": row["pnl"],
            }
            for row in rows
        ]
