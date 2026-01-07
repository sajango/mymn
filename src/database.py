"""SQLite database for trade and signal tracking.

Tracks:
- Trading signals from Claude analysis
- Executed trades with TP levels
- Trailing stop state for each trade
- Trade history and performance metrics
"""

import logging
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from src.config import get_settings
from src.signal_parser import TradingSignal

logger = logging.getLogger(__name__)


class TrailingState(str, Enum):
    """Trailing stop state machine states."""

    INACTIVE = "inactive"  # Initial state, not yet activated
    ACTIVATED = "activated"  # TP1 hit or profit > 1R, SL moved to breakeven
    TRAILING = "trailing"  # Actively trailing price


class TradeStatus(str, Enum):
    """Trade lifecycle status."""

    OPEN = "open"
    PARTIAL = "partial"  # Partially closed
    CLOSED = "closed"
    CANCELLED = "cancelled"


class SignalStatus(str, Enum):
    """Signal lifecycle status."""

    PENDING = "pending"
    EXECUTED = "executed"
    SKIPPED = "skipped"
    EXPIRED = "expired"
    REJECTED = "rejected"


class Database:
    """SQLite database for trading system data.

    Tables:
    - signals: Trading signals from Claude analysis
    - trades: Executed trades with current state
    - tp_levels: Take profit levels for each trade
    - trade_events: Audit trail of trade modifications
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is not None:
            self.db_path = db_path
        else:
            settings = get_settings()
            self.db_path = settings.db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize database tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            # Signals table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit_1 REAL,
                    take_profit_2 REAL,
                    take_profit_3 REAL,
                    confidence INTEGER NOT NULL,
                    wave_position TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Trades table with trailing stop state
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER,
                    ticket INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    volume REAL NOT NULL,
                    initial_volume REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    initial_stop_loss REAL NOT NULL,
                    take_profit REAL,
                    open_time TEXT NOT NULL,
                    close_time TEXT,
                    close_price REAL,
                    profit REAL,
                    trailing_state TEXT DEFAULT 'inactive',
                    trailing_stop_price REAL,
                    breakeven_price REAL,
                    status TEXT DEFAULT 'open',
                    FOREIGN KEY (signal_id) REFERENCES signals (id)
                )
            """)

            # TP levels table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tp_levels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    price REAL NOT NULL,
                    close_percent INTEGER NOT NULL,
                    triggered INTEGER DEFAULT 0,
                    triggered_at TEXT,
                    FOREIGN KEY (trade_id) REFERENCES trades (id)
                )
            """)

            # Trade events audit trail
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (trade_id) REFERENCES trades (id)
                )
            """)

            # Create indexes for common queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_ticket ON trades(ticket)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status)"
            )

            # Skipped signals table for tracking silent skips
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skipped_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reason TEXT NOT NULL,
                    details TEXT,
                    session TEXT,
                    spread_pips REAL,
                    confidence INTEGER,
                    signal_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (signal_id) REFERENCES signals (id)
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_skipped_reason ON skipped_signals(reason)"
            )

            # Signal hashes for duplicate detection
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_hashes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hash TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_signal_hash ON signal_hashes(hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_signal_hash_created ON signal_hashes(created_at)"
            )

            conn.commit()
            logger.info(f"Database initialized: {self.db_path}")

    def save_signal(self, signal: TradingSignal) -> int:
        """Save signal to database.

        Args:
            signal: Trading signal to save

        Returns:
            Signal ID
        """
        s = signal.signal
        tps = s.take_profit or []
        wave_pos = (
            signal.wave_analysis.wave_position if signal.wave_analysis else None
        )

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO signals (
                    timestamp, symbol, action, entry_price, stop_loss,
                    take_profit_1, take_profit_2, take_profit_3,
                    confidence, wave_position, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.timestamp,
                    signal.symbol,
                    s.action.value,
                    s.entry_price,
                    s.stop_loss,
                    tps[0].price if len(tps) > 0 else None,
                    tps[1].price if len(tps) > 1 else None,
                    tps[2].price if len(tps) > 2 else None,
                    s.confidence,
                    wave_pos,
                    SignalStatus.PENDING.value,
                ),
            )
            signal_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Signal saved: id={signal_id}, action={s.action.value}")
            return signal_id

    def save_trade(
        self,
        signal_id: int,
        ticket: int,
        volume: float,
        signal: TradingSignal,
    ) -> int:
        """Save executed trade.

        Args:
            signal_id: Associated signal ID
            ticket: MT5 order ticket
            volume: Trade volume
            signal: Trading signal

        Returns:
            Trade ID
        """
        s = signal.signal
        tp1_price = s.take_profit[0].price if s.take_profit else None

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trades (
                    signal_id, ticket, symbol, action, volume, initial_volume,
                    entry_price, stop_loss, initial_stop_loss, take_profit,
                    open_time, trailing_state, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    ticket,
                    signal.symbol,
                    s.action.value,
                    volume,
                    volume,
                    s.entry_price,
                    s.stop_loss,
                    s.stop_loss,
                    tp1_price,
                    datetime.now(timezone.utc).isoformat(),
                    TrailingState.INACTIVE.value,
                    TradeStatus.OPEN.value,
                ),
            )
            trade_id = cursor.lastrowid

            # Save TP levels
            if s.take_profit:
                for tp in s.take_profit:
                    conn.execute(
                        """
                        INSERT INTO tp_levels (trade_id, level, price, close_percent)
                        VALUES (?, ?, ?, ?)
                        """,
                        (trade_id, tp.level, tp.price, tp.close_percent),
                    )

            # Log trade open event
            conn.execute(
                """
                INSERT INTO trade_events (trade_id, event_type, event_data)
                VALUES (?, ?, ?)
                """,
                (trade_id, "OPENED", f"ticket={ticket}, volume={volume}"),
            )

            conn.commit()
            logger.info(f"Trade saved: id={trade_id}, ticket={ticket}")
            return trade_id

    def update_signal_status(self, signal_id: int, status: SignalStatus):
        """Update signal status.

        Args:
            signal_id: Signal ID
            status: New status
        """
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE signals SET status = ? WHERE id = ?",
                (status.value, signal_id),
            )
            conn.commit()

    def get_open_trades(self) -> list[dict]:
        """Get all open trades.

        Returns:
            List of open trade dicts
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status IN ('open', 'partial')"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_trade_by_id(self, trade_id: int) -> Optional[dict]:
        """Get trade by ID.

        Args:
            trade_id: Trade ID

        Returns:
            Trade dict or None
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM trades WHERE id = ?", (trade_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_trade_by_ticket(self, ticket: int) -> Optional[dict]:
        """Get trade by MT5 ticket.

        Args:
            ticket: MT5 order ticket

        Returns:
            Trade dict or None
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM trades WHERE ticket = ? AND status IN ('open', 'partial')",
                (ticket,),
            ).fetchone()
            return dict(row) if row else None

    def get_tp_levels(self, trade_id: int) -> list[dict]:
        """Get TP levels for trade.

        Args:
            trade_id: Trade ID

        Returns:
            List of TP level dicts
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tp_levels WHERE trade_id = ? ORDER BY price",
                (trade_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_trailing_state(
        self,
        trade_id: int,
        state: TrailingState,
        trailing_stop_price: Optional[float] = None,
        breakeven_price: Optional[float] = None,
    ):
        """Update trailing stop state.

        Args:
            trade_id: Trade ID
            state: New trailing state
            trailing_stop_price: Current trailing stop price
            breakeven_price: Breakeven price
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE trades SET
                    trailing_state = ?,
                    trailing_stop_price = COALESCE(?, trailing_stop_price),
                    breakeven_price = COALESCE(?, breakeven_price)
                WHERE id = ?
                """,
                (state.value, trailing_stop_price, breakeven_price, trade_id),
            )

            # Log event
            conn.execute(
                """
                INSERT INTO trade_events (trade_id, event_type, event_data)
                VALUES (?, ?, ?)
                """,
                (
                    trade_id,
                    f"TRAILING_{state.value.upper()}",
                    f"sl={trailing_stop_price}",
                ),
            )

            conn.commit()
            logger.info(f"Trade {trade_id} trailing state: {state.value}")

    def update_stop_loss(self, trade_id: int, new_sl: float):
        """Update trade stop loss.

        Args:
            trade_id: Trade ID
            new_sl: New stop loss price
        """
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE trades SET stop_loss = ? WHERE id = ?",
                (new_sl, trade_id),
            )

            conn.execute(
                """
                INSERT INTO trade_events (trade_id, event_type, event_data)
                VALUES (?, ?, ?)
                """,
                (trade_id, "SL_MODIFIED", f"new_sl={new_sl}"),
            )

            conn.commit()

    def mark_tp_triggered(self, trade_id: int, level: str):
        """Mark TP level as triggered.

        Args:
            trade_id: Trade ID
            level: TP level (TP1, TP2, TP3)
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE tp_levels SET
                    triggered = 1,
                    triggered_at = ?
                WHERE trade_id = ? AND level = ?
                """,
                (datetime.now(timezone.utc).isoformat(), trade_id, level),
            )

            conn.execute(
                """
                INSERT INTO trade_events (trade_id, event_type, event_data)
                VALUES (?, ?, ?)
                """,
                (trade_id, f"TP_TRIGGERED", f"level={level}"),
            )

            conn.commit()
            logger.info(f"Trade {trade_id} {level} triggered")

    def update_trade_volume(self, trade_id: int, new_volume: float):
        """Update trade remaining volume after partial close.

        Args:
            trade_id: Trade ID
            new_volume: Remaining volume
        """
        status = TradeStatus.PARTIAL.value if new_volume > 0 else TradeStatus.CLOSED.value

        with self._get_connection() as conn:
            conn.execute(
                "UPDATE trades SET volume = ?, status = ? WHERE id = ?",
                (new_volume, status, trade_id),
            )

            conn.execute(
                """
                INSERT INTO trade_events (trade_id, event_type, event_data)
                VALUES (?, ?, ?)
                """,
                (trade_id, "PARTIAL_CLOSE", f"remaining={new_volume}"),
            )

            conn.commit()

    def close_trade(
        self,
        trade_id: int,
        close_price: float,
        profit: float,
    ):
        """Close trade with final P&L.

        Args:
            trade_id: Trade ID
            close_price: Closing price
            profit: Final profit/loss
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE trades SET
                    close_time = ?,
                    close_price = ?,
                    profit = ?,
                    status = ?
                WHERE id = ?
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    close_price,
                    profit,
                    TradeStatus.CLOSED.value,
                    trade_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO trade_events (trade_id, event_type, event_data)
                VALUES (?, ?, ?)
                """,
                (trade_id, "CLOSED", f"profit={profit}"),
            )

            conn.commit()
            logger.info(f"Trade {trade_id} closed: profit={profit}")

    def get_trade_events(self, trade_id: int) -> list[dict]:
        """Get trade events audit trail.

        Args:
            trade_id: Trade ID

        Returns:
            List of event dicts
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM trade_events
                WHERE trade_id = ?
                ORDER BY created_at
                """,
                (trade_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_recent_signals(self, limit: int = 10) -> list[dict]:
        """Get recent signals.

        Args:
            limit: Number of signals to return

        Returns:
            List of signal dicts
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_signal_context(self, limit: int = 3) -> Optional[dict]:
        """Get context from recent signals for Claude prompt.

        Args:
            limit: Number of recent signals to analyze

        Returns:
            dict with signal context or None if no signals exist
        """
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        action,
                        confidence,
                        wave_position,
                        created_at
                    FROM signals
                    WHERE action IN ('BUY', 'SELL')
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

                if not rows:
                    return None

                # Most recent signal
                last = rows[0]
                last_time_str = last["created_at"]

                # Parse timestamp (handle both with and without timezone)
                try:
                    if "+" in last_time_str or last_time_str.endswith("Z"):
                        last_time = datetime.fromisoformat(
                            last_time_str.replace("Z", "+00:00")
                        )
                    else:
                        last_time = datetime.fromisoformat(last_time_str).replace(
                            tzinfo=timezone.utc
                        )
                except ValueError:
                    last_time = datetime.now(timezone.utc)

                minutes_since = int(
                    (datetime.now(timezone.utc) - last_time).total_seconds() / 60
                )

                # Build sequence string (oldest to newest)
                sequence = " → ".join(row["action"] for row in reversed(rows))

                return {
                    "last_action": last["action"],
                    "last_time": last_time_str,
                    "last_confidence": last["confidence"] or 0,
                    "wave_position": last["wave_position"],
                    "recent_sequence": sequence,
                    "minutes_since_last": minutes_since,
                }

        except sqlite3.Error as e:
            logger.error(f"Error getting signal context: {e}")
            return None

    def get_trade_summary(self) -> dict:
        """Get trading summary statistics.

        Returns:
            Summary dict with win/loss/profit stats
        """
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN profit = 0 THEN 1 ELSE 0 END) as breakeven,
                    SUM(profit) as total_profit,
                    AVG(profit) as avg_profit
                FROM trades
                WHERE status = 'closed'
                """
            ).fetchone()

            return dict(row) if row else {}

    def save_skipped_signal(
        self,
        reason: str,
        details: str = "",
        session: Optional[str] = None,
        spread_pips: Optional[float] = None,
        confidence: Optional[int] = None,
        signal_id: Optional[int] = None,
    ) -> int:
        """Save skipped signal for analytics.

        Args:
            reason: Skip reason (spread_high, low_confidence, etc.)
            details: Detailed explanation
            session: Trading session name
            spread_pips: Current spread if relevant
            confidence: Signal confidence if relevant
            signal_id: Associated signal ID if available

        Returns:
            Skipped signal ID
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO skipped_signals (
                    reason, details, session, spread_pips, confidence, signal_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (reason, details, session, spread_pips, confidence, signal_id),
            )
            skip_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Skipped signal saved: id={skip_id}, reason={reason}")
            return skip_id

    def get_skipped_summary(self, days: int = 7) -> dict:
        """Get summary of skipped signals.

        Args:
            days: Number of days to look back

        Returns:
            Summary dict with skip counts by reason
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT reason, COUNT(*) as count
                FROM skipped_signals
                WHERE created_at >= datetime('now', ? || ' days')
                GROUP BY reason
                ORDER BY count DESC
                """,
                (f"-{days}",),
            ).fetchall()

            return {row["reason"]: row["count"] for row in rows}

    def save_signal_hash(
        self, hash_value: str, symbol: str, action: str
    ) -> int:
        """Save signal hash for duplicate detection.

        Args:
            hash_value: MD5 hash of signal content
            symbol: Trading symbol
            action: Signal action (BUY/SELL)

        Returns:
            Hash record ID
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO signal_hashes (hash, symbol, action)
                VALUES (?, ?, ?)
                """,
                (hash_value, symbol, action),
            )
            hash_id = cursor.lastrowid
            conn.commit()
            logger.debug(f"Signal hash saved: {hash_value[:8]}...")
            return hash_id

    def get_recent_signal_hashes(self, minutes: int = 15) -> set[str]:
        """Get signal hashes from last N minutes.

        Args:
            minutes: Lookback window in minutes

        Returns:
            Set of hash strings
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT hash FROM signal_hashes
                WHERE created_at >= datetime('now', ? || ' minutes')
                """,
                (f"-{minutes}",),
            ).fetchall()
            return {row["hash"] for row in rows}

    def cleanup_old_hashes(self, hours: int = 24) -> int:
        """Remove signal hashes older than N hours.

        Args:
            hours: Age threshold for cleanup

        Returns:
            Number of deleted records
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM signal_hashes
                WHERE created_at < datetime('now', ? || ' hours')
                """,
                (f"-{hours}",),
            )
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old signal hashes")
            return deleted

    # Analytics queries for Phase 9

    def get_closed_trades(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> list[dict]:
        """Get all closed trades for analytics.

        Args:
            start_date: Optional start date filter (ISO format)
            end_date: Optional end date filter (ISO format)

        Returns:
            List of closed trade dicts
        """
        query = "SELECT * FROM trades WHERE status = 'closed'"
        params = []

        if start_date:
            query += " AND close_time >= ?"
            params.append(start_date)
        if end_date:
            query += " AND close_time <= ?"
            params.append(end_date)

        query += " ORDER BY close_time"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_signals_with_trades(self) -> list[dict]:
        """Get signals with associated trade data for analytics.

        Returns:
            List of signals with trade profit and status
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.*,
                    t.profit,
                    t.close_price,
                    t.entry_price as trade_entry,
                    t.stop_loss as trade_sl,
                    t.status as trade_status
                FROM signals s
                LEFT JOIN trades t ON s.id = t.signal_id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_analytics_snapshot(self) -> dict:
        """Get aggregated analytics snapshot for reports.

        Returns:
            Dict with aggregated stats for reporting
        """
        with self._get_connection() as conn:
            # Overall stats
            overall = conn.execute(
                """
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(profit), 0) as total_profit,
                    COALESCE(SUM(CASE WHEN profit > 0 THEN profit ELSE 0 END), 0) as gross_profit,
                    COALESCE(ABS(SUM(CASE WHEN profit < 0 THEN profit ELSE 0 END)), 0) as gross_loss
                FROM trades WHERE status = 'closed'
                """
            ).fetchone()

            # Signal counts by session
            by_session = conn.execute(
                """
                SELECT
                    CASE
                        WHEN CAST(strftime('%H', timestamp) AS INTEGER) BETWEEN 12 AND 14 THEN 'overlap'
                        WHEN CAST(strftime('%H', timestamp) AS INTEGER) BETWEEN 7 AND 15 THEN 'london'
                        WHEN CAST(strftime('%H', timestamp) AS INTEGER) BETWEEN 12 AND 20 THEN 'new_york'
                        WHEN CAST(strftime('%H', timestamp) AS INTEGER) < 7 THEN 'asian'
                        ELSE 'offhours'
                    END as session,
                    COUNT(*) as count
                FROM signals
                GROUP BY session
                """
            ).fetchall()

            return {
                "overall": dict(overall) if overall else {},
                "by_session": {row["session"]: row["count"] for row in by_session},
            }


# Lazy singleton
_database: Optional[Database] = None


def get_database() -> Database:
    """Get or create database singleton."""
    global _database
    if _database is None:
        _database = Database()
    return _database
