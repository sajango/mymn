"""Analytics API endpoints for charts."""

import logging
from fastapi import APIRouter, Query

from services.analytics import get_daily_pnl, get_equity_curve
from services.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/equity")
def equity_curve():
    """Get equity curve data for line chart."""
    logger.info("[API] GET /api/equity - Fetching equity curve")
    result = get_equity_curve()
    logger.info(f"[API] GET /api/equity - Returned {len(result)} data points")
    return result


@router.get("/daily-pnl")
def daily_pnl(days: int = Query(30, ge=1, le=365)):
    """Get daily P&L for bar chart."""
    logger.info(f"[API] GET /api/daily-pnl?days={days} - Fetching daily P&L")
    result = get_daily_pnl(days)
    logger.info(f"[API] GET /api/daily-pnl - Returned {len(result)} days")
    return result


@router.get("/skipped-signals")
def skipped_signals(days: int = Query(7, ge=1, le=90)):
    """Get summary of skipped signals by reason."""
    logger.info(f"[API] GET /api/skipped-signals?days={days} - Fetching skipped signals")
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

        result = [
            {
                "reason": row["reason"],
                "count": row["count"],
                "avg_spread": round(row["avg_spread"], 2) if row["avg_spread"] else None,
                "avg_confidence": round(row["avg_confidence"], 1) if row["avg_confidence"] else None,
            }
            for row in rows
        ]

        total_skipped = sum(r["count"] for r in result)
        logger.info(f"[API] GET /api/skipped-signals - Found {total_skipped} skipped signals across {len(result)} reasons")
        for r in result:
            logger.debug(f"[SKIPPED] {r['reason']}: {r['count']} signals")

        return result


@router.get("/weekly-summary")
def weekly_summary():
    """Get week-over-week performance summary."""
    logger.info("[API] GET /api/weekly-summary - Fetching weekly performance")
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

        result = [
            {
                "week": row["week"],
                "trades": row["trades"],
                "wins": row["wins"],
                "win_rate": round((row["wins"] / row["trades"] * 100) if row["trades"] > 0 else 0, 1),
                "pnl": row["pnl"],
            }
            for row in rows
        ]

        logger.info(f"[API] GET /api/weekly-summary - Returned {len(result)} weeks")
        for r in result:
            logger.debug(
                f"[WEEKLY] {r['week']}: {r['trades']} trades, "
                f"win_rate={r['win_rate']}%, pnl=${r['pnl']:.2f}"
            )

        return result
