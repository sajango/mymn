"""Analytics calculation service for dashboard.

Provides statistical calculations for trading performance metrics.
"""

from datetime import datetime, timedelta
from typing import Any

from dashboard.backend.services.database import get_db


def get_overall_stats() -> dict[str, Any]:
    """Get overall trading statistics."""
    with get_db() as conn:
        # Total closed trades
        total = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE status = 'closed'"
        ).fetchone()[0]

        if total == 0:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_profit": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0,
                "profit_factor": 0.0,
            }

        # Win/loss counts
        wins = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE profit > 0 AND status = 'closed'"
        ).fetchone()[0]

        losses = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE profit < 0 AND status = 'closed'"
        ).fetchone()[0]

        # P&L stats
        pnl_row = conn.execute("""
            SELECT
                COALESCE(SUM(profit), 0) as total_pnl,
                COALESCE(AVG(profit), 0) as avg_profit,
                COALESCE(MAX(profit), 0) as max_profit,
                COALESCE(MIN(profit), 0) as max_loss
            FROM trades WHERE status = 'closed'
        """).fetchone()

        # Profit factor (gross profit / gross loss)
        gross_profit = conn.execute(
            "SELECT COALESCE(SUM(profit), 0) FROM trades WHERE profit > 0 AND status = 'closed'"
        ).fetchone()[0]

        gross_loss = abs(conn.execute(
            "SELECT COALESCE(SUM(profit), 0) FROM trades WHERE profit < 0 AND status = 'closed'"
        ).fetchone()[0])

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round((wins / total * 100) if total > 0 else 0, 1),
            "total_pnl": round(pnl_row["total_pnl"], 2),
            "avg_profit": round(pnl_row["avg_profit"], 2),
            "max_profit": round(pnl_row["max_profit"], 2),
            "max_loss": round(pnl_row["max_loss"], 2),
            "profit_factor": round(profit_factor, 2),
        }


def get_equity_curve() -> list[dict]:
    """Get equity curve data (cumulative P&L over time)."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                close_time,
                profit,
                SUM(profit) OVER (ORDER BY close_time) as cumulative
            FROM trades
            WHERE status = 'closed' AND close_time IS NOT NULL
            ORDER BY close_time
        """).fetchall()

        return [
            {
                "time": row["close_time"],
                "profit": round(row["profit"], 2),
                "equity": round(row["cumulative"], 2),
            }
            for row in rows
        ]


def get_daily_pnl(days: int = 30) -> list[dict]:
    """Get daily P&L for the last N days."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                date(close_time) as date,
                SUM(profit) as daily_pnl,
                COUNT(*) as trade_count
            FROM trades
            WHERE status = 'closed'
                AND close_time >= date('now', ? || ' days')
            GROUP BY date(close_time)
            ORDER BY date
        """, (f"-{days}",)).fetchall()

        return [
            {
                "date": row["date"],
                "pnl": round(row["daily_pnl"], 2),
                "trades": row["trade_count"],
            }
            for row in rows
        ]


def get_confidence_analysis() -> list[dict]:
    """Analyze signal confidence vs actual outcome."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                CASE
                    WHEN s.confidence >= 75 THEN 'High (75-100)'
                    WHEN s.confidence >= 60 THEN 'Medium (60-74)'
                    ELSE 'Low (<60)'
                END as confidence_band,
                COUNT(*) as total,
                SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END) as wins,
                ROUND(AVG(t.profit), 2) as avg_profit,
                ROUND(SUM(t.profit), 2) as total_profit
            FROM trades t
            JOIN signals s ON t.signal_id = s.id
            WHERE t.status = 'closed'
            GROUP BY confidence_band
            ORDER BY
                CASE confidence_band
                    WHEN 'High (75-100)' THEN 1
                    WHEN 'Medium (60-74)' THEN 2
                    ELSE 3
                END
        """).fetchall()

        return [
            {
                "band": row["confidence_band"],
                "total": row["total"],
                "wins": row["wins"],
                "win_rate": round((row["wins"] / row["total"] * 100) if row["total"] > 0 else 0, 1),
                "avg_profit": row["avg_profit"],
                "total_profit": row["total_profit"],
            }
            for row in rows
        ]


def get_time_analysis() -> dict:
    """Analyze performance by hour and day of week."""
    with get_db() as conn:
        # By hour
        hour_rows = conn.execute("""
            SELECT
                strftime('%H', open_time) as hour,
                COUNT(*) as trades,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                ROUND(SUM(profit), 2) as total_pnl
            FROM trades
            WHERE status = 'closed'
            GROUP BY hour
            ORDER BY hour
        """).fetchall()

        # By day of week (0=Sunday, 6=Saturday)
        day_rows = conn.execute("""
            SELECT
                strftime('%w', open_time) as dow,
                COUNT(*) as trades,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                ROUND(SUM(profit), 2) as total_pnl
            FROM trades
            WHERE status = 'closed'
            GROUP BY dow
            ORDER BY dow
        """).fetchall()

        day_names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

        return {
            "by_hour": [
                {
                    "hour": int(row["hour"]),
                    "trades": row["trades"],
                    "win_rate": round((row["wins"] / row["trades"] * 100) if row["trades"] > 0 else 0, 1),
                    "pnl": row["total_pnl"],
                }
                for row in hour_rows
            ],
            "by_day": [
                {
                    "day": day_names[int(row["dow"])],
                    "trades": row["trades"],
                    "win_rate": round((row["wins"] / row["trades"] * 100) if row["trades"] > 0 else 0, 1),
                    "pnl": row["total_pnl"],
                }
                for row in day_rows
            ],
        }


def get_open_positions() -> list[dict]:
    """Get currently open positions."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                t.*,
                s.confidence,
                s.wave_position
            FROM trades t
            LEFT JOIN signals s ON t.signal_id = s.id
            WHERE t.status IN ('open', 'partial')
            ORDER BY t.open_time DESC
        """).fetchall()

        return [dict(row) for row in rows]
