"""SQLite database for trade and signal tracking.

Tracks:
- Trading signals from Claude analysis
- Executed trades with TP levels
- Trailing stop state for each trade
- Trade history and performance metrics
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, List

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

    def _add_column_if_not_exists(
        self, conn: sqlite3.Connection, table: str, column: str, col_type: str
    ) -> None:
        """Add column to table if it doesn't exist.

        Args:
            conn: Database connection
            table: Table name
            column: Column name to add
            col_type: SQLite column type (TEXT, INTEGER, REAL, etc.)
        """
        cursor = conn.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            logger.info(f"Added column {column} to {table} table")

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

            # Phase B: Add calibration columns to signals table
            self._add_column_if_not_exists(
                conn, "signals", "confidence_breakdown", "TEXT"
            )
            self._add_column_if_not_exists(
                conn, "signals", "regime_type", "TEXT"
            )
            self._add_column_if_not_exists(
                conn, "signals", "session", "TEXT"
            )

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

            # Phase B: Add calibration columns to trades table
            self._add_column_if_not_exists(
                conn, "trades", "outcome", "TEXT"
            )
            self._add_column_if_not_exists(
                conn, "trades", "r_multiple", "REAL"
            )
            self._add_column_if_not_exists(
                conn, "trades", "signal_confidence", "INTEGER"
            )

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

            # Validation rejections table - tracks Claude AI errors
            conn.execute("""
                CREATE TABLE IF NOT EXISTS validation_rejections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER,
                    rejection_type TEXT NOT NULL,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    action TEXT,
                    details TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (signal_id) REFERENCES signals (id)
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rejection_type ON validation_rejections(rejection_type)"
            )

            # Drawdown state table for real-time risk tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS drawdown_state (
                    id INTEGER PRIMARY KEY,
                    date TEXT NOT NULL,
                    daily_start_balance REAL NOT NULL,
                    daily_pnl REAL DEFAULT 0,
                    daily_trades INTEGER DEFAULT 0,
                    weekly_start_balance REAL NOT NULL,
                    weekly_pnl REAL DEFAULT 0,
                    weekly_trades INTEGER DEFAULT 0,
                    peak_balance REAL NOT NULL,
                    consecutive_losses INTEGER DEFAULT 0,
                    recovery_mode INTEGER DEFAULT 0,
                    trading_paused INTEGER DEFAULT 0,
                    pause_reason TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(date)
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_drawdown_date ON drawdown_state(date)"
            )

            # Market memory table for persistent context
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    memory_value TEXT NOT NULL,
                    confidence INTEGER,
                    expires_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_type ON market_memory(memory_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_key ON market_memory(memory_key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_expires ON market_memory(expires_at)"
            )

            # Signal outcomes table for performance tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER NOT NULL,
                    trade_id INTEGER,
                    predicted_direction TEXT NOT NULL,
                    actual_movement REAL,
                    tp_levels_hit INTEGER DEFAULT 0,
                    accuracy_score REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (signal_id) REFERENCES signals (id),
                    FOREIGN KEY (trade_id) REFERENCES trades (id)
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_outcome_signal ON signal_outcomes(signal_id)"
            )

            conn.commit()
            logger.info(f"Database initialized: {self.db_path}")

    def save_signal(
        self,
        signal: TradingSignal,
        session: Optional[str] = None,
    ) -> int:
        """Save signal to database with calibration data.

        Args:
            signal: Trading signal to save
            session: Trading session name (asian, london, ny, overlap)

        Returns:
            Signal ID
        """
        s = signal.signal
        tps = s.take_profit or []
        wave_pos = (
            signal.wave_analysis.wave_position if signal.wave_analysis else None
        )

        # Phase B: Extract calibration data
        confidence_breakdown = None
        if signal.confidence_breakdown:
            confidence_breakdown = json.dumps(signal.confidence_breakdown.model_dump())

        regime_type = None
        if signal.market_regime:
            regime_type = signal.market_regime.classification

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO signals (
                    timestamp, symbol, action, entry_price, stop_loss,
                    take_profit_1, take_profit_2, take_profit_3,
                    confidence, wave_position, status,
                    confidence_breakdown, regime_type, session
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    confidence_breakdown,
                    regime_type,
                    session,
                ),
            )
            signal_id = cursor.lastrowid
            conn.commit()
            logger.info(
                f"Signal saved: id={signal_id}, action={s.action.value}, "
                f"confidence={s.confidence}, regime={regime_type}, session={session}"
            )
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
        """Close trade with final P&L and calibration metrics.

        Args:
            trade_id: Trade ID
            close_price: Closing price
            profit: Final profit/loss
        """
        with self._get_connection() as conn:
            # Get trade details for R-multiple calculation
            trade = conn.execute(
                "SELECT entry_price, initial_stop_loss, action, signal_id FROM trades WHERE id = ?",
                (trade_id,),
            ).fetchone()

            # Phase B: Calculate outcome and R-multiple
            outcome = "breakeven"
            r_multiple = 0.0
            signal_confidence = None

            if trade:
                if profit > 0:
                    outcome = "win"
                elif profit < 0:
                    outcome = "loss"

                # Calculate R-multiple: profit / risk
                entry = trade["entry_price"]
                sl = trade["initial_stop_loss"]
                action = trade["action"]

                if entry and sl:
                    risk_per_unit = abs(entry - sl)
                    if risk_per_unit > 0:
                        actual_move = close_price - entry
                        if action == "SELL":
                            actual_move = -actual_move
                        r_multiple = round(actual_move / risk_per_unit, 2)

                # Get signal confidence
                if trade["signal_id"]:
                    sig = conn.execute(
                        "SELECT confidence FROM signals WHERE id = ?",
                        (trade["signal_id"],),
                    ).fetchone()
                    if sig:
                        signal_confidence = sig["confidence"]

            conn.execute(
                """
                UPDATE trades SET
                    close_time = ?,
                    close_price = ?,
                    profit = ?,
                    status = ?,
                    outcome = ?,
                    r_multiple = ?,
                    signal_confidence = ?
                WHERE id = ?
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    close_price,
                    profit,
                    TradeStatus.CLOSED.value,
                    outcome,
                    r_multiple,
                    signal_confidence,
                    trade_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO trade_events (trade_id, event_type, event_data)
                VALUES (?, ?, ?)
                """,
                (trade_id, "CLOSED", f"profit={profit}, outcome={outcome}, r={r_multiple}"),
            )

            conn.commit()
            logger.info(
                f"Trade {trade_id} closed: profit={profit}, outcome={outcome}, R={r_multiple}"
            )

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

    def save_validation_rejection(
        self,
        signal_id: Optional[int],
        rejection_type: str,
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        action: Optional[str] = None,
        details: str = "",
    ) -> int:
        """Save validation rejection for tracking Claude AI errors.

        Args:
            signal_id: Associated signal ID if available
            rejection_type: Type of rejection (invalid_sl_buy, invalid_tp_sell, etc.)
            entry_price: Entry price from signal
            stop_loss: Stop loss price from signal
            take_profit: Take profit price from signal
            action: Signal action (BUY/SELL)
            details: Detailed rejection message

        Returns:
            Rejection record ID
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO validation_rejections (
                    signal_id, rejection_type, entry_price, stop_loss,
                    take_profit, action, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (signal_id, rejection_type, entry_price, stop_loss, take_profit, action, details),
            )
            rejection_id = cursor.lastrowid
            conn.commit()
            logger.warning(
                f"Validation rejection saved: id={rejection_id}, type={rejection_type}"
            )
            return rejection_id

    def get_validation_rejection_stats(self, days: int = 30) -> dict:
        """Get statistics on validation rejections.

        Args:
            days: Number of days to look back

        Returns:
            Dict with rejection counts by type and overall stats
        """
        with self._get_connection() as conn:
            # Count by rejection type
            by_type = conn.execute(
                """
                SELECT rejection_type, COUNT(*) as count
                FROM validation_rejections
                WHERE created_at >= datetime('now', ? || ' days')
                GROUP BY rejection_type
                ORDER BY count DESC
                """,
                (f"-{days}",),
            ).fetchall()

            # Total count
            total = conn.execute(
                """
                SELECT COUNT(*) as total
                FROM validation_rejections
                WHERE created_at >= datetime('now', ? || ' days')
                """,
                (f"-{days}",),
            ).fetchone()

            return {
                "by_type": {row["rejection_type"]: row["count"] for row in by_type},
                "total": total["total"] if total else 0,
                "days": days,
            }

    # Drawdown state methods

    def get_drawdown_state(self, date_str: str) -> Optional[dict]:
        """Get drawdown state for a specific date.

        Args:
            date_str: Date string in YYYY-MM-DD format

        Returns:
            Drawdown state dict or None if not exists
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM drawdown_state WHERE date = ?",
                (date_str,),
            ).fetchone()
            return dict(row) if row else None

    def save_drawdown_state(self, state: dict) -> int:
        """Save or update drawdown state.

        Args:
            state: Drawdown state dict with all fields

        Returns:
            Row ID
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO drawdown_state (
                    id, date, daily_start_balance, daily_pnl, daily_trades,
                    weekly_start_balance, weekly_pnl, weekly_trades,
                    peak_balance, consecutive_losses, recovery_mode,
                    trading_paused, pause_reason, updated_at
                ) VALUES (
                    (SELECT id FROM drawdown_state WHERE date = ?),
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
                )
                """,
                (
                    state["date"],
                    state["date"],
                    state["daily_start_balance"],
                    state.get("daily_pnl", 0),
                    state.get("daily_trades", 0),
                    state["weekly_start_balance"],
                    state.get("weekly_pnl", 0),
                    state.get("weekly_trades", 0),
                    state["peak_balance"],
                    state.get("consecutive_losses", 0),
                    state.get("recovery_mode", 0),
                    state.get("trading_paused", 0),
                    state.get("pause_reason"),
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_latest_drawdown_state(self) -> Optional[dict]:
        """Get most recent drawdown state.

        Returns:
            Latest drawdown state dict or None
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM drawdown_state ORDER BY date DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def get_trades_for_analytics(self, start_date=None, end_date=None, symbol=None) -> List[dict]:
        """Get trades for analytics with optional filters.
        
        Args:
            start_date: Start date filter
            end_date: End date filter  
            symbol: Symbol filter
            
        Returns:
            List of trade dictionaries
        """
        query = """
        SELECT t.*, s.confidence, s.action as signal_action,
               s.wave_position
        FROM trades t
        LEFT JOIN signals s ON t.signal_id = s.id
        WHERE t.status IN ('closed', 'partial_close')
        """
        params = []
        
        if start_date:
            query += " AND t.open_time >= ?"
            params.append(start_date)
        if end_date:
            query += " AND t.open_time <= ?"
            params.append(end_date)
        if symbol:
            query += " AND t.symbol = ?"
            params.append(symbol)
            
        query += " ORDER BY t.open_time"
        
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    def get_signals_with_regime(self) -> List[dict]:
        """Get all signals with regime information."""
        query = """
        SELECT s.*, mm.memory_value as market_regime
        FROM signals s
        LEFT JOIN market_memory mm ON mm.memory_type = 'market_regime' 
            AND mm.created_at >= datetime(s.timestamp, '-4 hours')
        ORDER BY s.timestamp
        """
        
        with self._get_connection() as conn:
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]
    
    def get_signals_with_volatility(self) -> List[dict]:
        """Get all signals with volatility state."""
        query = """
        SELECT s.*, mm.memory_value as volatility_state
        FROM signals s
        LEFT JOIN market_memory mm ON mm.memory_type = 'volatility'
            AND mm.created_at >= datetime(s.timestamp, '-2 hours')
        ORDER BY s.timestamp
        """
        
        with self._get_connection() as conn:
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]
    
    def get_signals_with_patterns(self) -> List[dict]:
        """Get all signals with wave patterns."""
        query = """
        SELECT s.*, s.wave_position
        FROM signals s
        WHERE s.wave_position IS NOT NULL
        ORDER BY s.timestamp
        """
        
        with self._get_connection() as conn:
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]
    
    def get_trade_by_signal_id(self, signal_id: int) -> Optional[dict]:
        """Get trade associated with signal."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM trades WHERE signal_id = ?", (signal_id,)
            ).fetchone()
            return dict(row) if row else None
    
    def get_trades_by_session(self, session: str) -> List[dict]:
        """Get trades for specific session."""
        query = """
        SELECT t.*, s.confidence
        FROM trades t
        LEFT JOIN signals s ON t.signal_id = s.id
        WHERE s.session = ? AND t.status IN ('closed', 'partial_close')
        ORDER BY t.open_time
        """
        
        with self._get_connection() as conn:
            rows = conn.execute(query, (session,)).fetchall()
            return [dict(row) for row in rows]
    
    def get_all_signals_with_trades(self) -> List[dict]:
        """Get all signals with their associated trades."""
        query = """
        SELECT s.*, t.id as trade_id, t.pnl, t.status as trade_status
        FROM signals s
        LEFT JOIN trades t ON s.id = t.signal_id
        ORDER BY s.timestamp
        """
        
        with self._get_connection() as conn:
            rows = conn.execute(query).fetchall()
            results = []
            for row in rows:
                signal_data = dict(row)
                if signal_data.get('trade_id'):
                    signal_data['trade'] = {
                        'id': signal_data.pop('trade_id'),
                        'pnl': signal_data.pop('pnl'),
                        'status': signal_data.pop('trade_status')
                    }
                results.append(signal_data)
            return results
    
    def get_latest_market_memory(self, memory_type: str, key: Optional[str] = None) -> Optional[dict]:
        """Get latest market memory entry.
        
        Args:
            memory_type: Type of memory to retrieve
            key: Optional specific key
            
        Returns:
            Latest memory entry or None
        """
        query = """
        SELECT * FROM market_memory 
        WHERE memory_type = ? 
        AND (expires_at IS NULL OR expires_at > datetime('now'))
        """
        params = [memory_type]
        
        if key:
            query += " AND key = ?"
            params.append(key)
            
        query += " ORDER BY created_at DESC LIMIT 1"
        
        with self._get_connection() as conn:
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None

    def save_market_memory(self, memory_type: str, key: str, value: str, 
                          confidence: Optional[int] = None, 
                          expires_hours: Optional[int] = None) -> int:
        """Save market context to memory.

        Args:
            memory_type: Type of memory (wave_count, key_level, pattern)
            key: Memory key identifier
            value: Memory value (JSON string for complex data)
            confidence: Confidence in this memory (0-100)
            expires_hours: Hours until expiry (None = permanent)

        Returns:
            Memory ID
        """
        expires_at = None
        if expires_hours:
            expires_at = (datetime.now(timezone.utc) + 
                         timedelta(hours=expires_hours)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO market_memory (timestamp, memory_type, memory_key, 
                                         memory_value, confidence, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    memory_type,
                    key,
                    value,
                    confidence,
                    expires_at,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_market_memory(self, memory_type: Optional[str] = None, 
                         key: Optional[str] = None) -> list[dict]:
        """Get market memories.

        Args:
            memory_type: Filter by type
            key: Filter by key

        Returns:
            List of memory records
        """
        with self._get_connection() as conn:
            query = """
                SELECT * FROM market_memory 
                WHERE (expires_at IS NULL OR expires_at > ?)
            """
            params = [datetime.now(timezone.utc).isoformat()]

            if memory_type:
                query += " AND memory_type = ?"
                params.append(memory_type)
            
            if key:
                query += " AND memory_key = ?"
                params.append(key)

            query += " ORDER BY created_at DESC"

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_enhanced_signal_context(self, limit: int = 5) -> Optional[dict]:
        """Get comprehensive context including market state and performance.

        Args:
            limit: Number of recent signals to analyze

        Returns:
            Enhanced context dict with signals, performance, memory
        """
        try:
            # Get basic signal context
            basic_context = self.get_signal_context(limit)
            if not basic_context:
                return None

            # Get performance by session
            session_stats = self._get_session_performance_stats()

            # Get current streak
            streak_info = self._get_current_streak()

            # Get market memory
            market_memory = self.get_market_memory()

            # Get recent key levels from memory
            key_levels = [m for m in market_memory if m['memory_type'] == 'key_level']

            # Enhanced context
            return {
                **basic_context,  # Include all basic context
                'session_performance': session_stats,
                'current_streak': streak_info,
                'market_memory': market_memory,
                'key_levels': key_levels,
                'total_signals_today': self._count_signals_today(),
            }

        except Exception as e:
            logger.error(f"Error getting enhanced context: {e}")
            return None

    def _get_session_performance_stats(self) -> dict:
        """Get win rate by trading session."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT 
                    sess.session,
                    COUNT(t.id) as total,
                    SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(t.profit) as avg_profit
                FROM trades t
                JOIN (
                    SELECT id, 
                           CASE 
                               WHEN created_at LIKE '%07:__:%' THEN 'london'
                               WHEN created_at LIKE '%12:__:%' THEN 'overlap'
                               WHEN created_at LIKE '%13:__:%' THEN 'ny'
                               ELSE 'other'
                           END as session
                    FROM signals
                ) sess ON sess.id = t.signal_id
                WHERE t.status = 'closed'
                GROUP BY sess.session
            """).fetchall()

            return {row['session']: {
                'total': row['total'],
                'win_rate': (row['wins'] / row['total'] * 100) if row['total'] > 0 else 0,
                'avg_profit': row['avg_profit'] or 0
            } for row in rows}

    def _get_current_streak(self) -> dict:
        """Get current winning/losing streak."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT profit 
                FROM trades 
                WHERE status = 'closed' 
                ORDER BY close_time DESC 
                LIMIT 10
            """).fetchall()

            if not rows:
                return {'type': 'none', 'count': 0}

            streak_type = 'win' if rows[0]['profit'] > 0 else 'loss'
            streak_count = 0

            for row in rows:
                if (streak_type == 'win' and row['profit'] > 0) or \
                   (streak_type == 'loss' and row['profit'] <= 0):
                    streak_count += 1
                else:
                    break

            return {'type': streak_type, 'count': streak_count}

    def _count_signals_today(self) -> int:
        """Count signals generated today."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM signals WHERE created_at >= ?",
                (today_start,)
            ).fetchone()
            return row['count'] if row else 0

    def save_signal_outcome(self, signal_id: int, trade_id: Optional[int],
                          actual_movement: float, tp_levels_hit: int = 0) -> None:
        """Save signal outcome for performance tracking.

        Args:
            signal_id: Signal that generated prediction
            trade_id: Associated trade (if executed)
            actual_movement: Actual price movement in pips
            tp_levels_hit: Number of TP levels achieved
        """
        with self._get_connection() as conn:
            # Get signal details
            signal = conn.execute(
                "SELECT action, entry_price FROM signals WHERE id = ?",
                (signal_id,)
            ).fetchone()

            if not signal:
                return

            # Calculate accuracy score
            predicted_direction = signal['action']
            accuracy = 1.0 if (
                (predicted_direction == 'BUY' and actual_movement > 0) or
                (predicted_direction == 'SELL' and actual_movement < 0)
            ) else 0.0

            # Save outcome
            conn.execute(
                """
                INSERT INTO signal_outcomes (signal_id, trade_id, predicted_direction,
                                           actual_movement, tp_levels_hit, accuracy_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (signal_id, trade_id, predicted_direction, actual_movement, 
                 tp_levels_hit, accuracy)
            )
            conn.commit()

    # Performance extraction methods for InstructionBuilder

    def get_wave_performance_stats(self, days: int = 30) -> dict:
        """Get win rates by wave position for instruction context.

        Args:
            days: Number of days to look back

        Returns:
            Dict mapping wave position to performance stats
            e.g., {"Wave 2": {"win_rate": 62, "total": 15}, ...}
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.wave_position,
                    COUNT(*) as total,
                    SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(t.profit) as avg_profit
                FROM trades t
                JOIN signals s ON t.signal_id = s.id
                WHERE t.status = 'closed'
                    AND s.wave_position IS NOT NULL
                    AND t.close_time >= datetime('now', ? || ' days')
                GROUP BY s.wave_position
                ORDER BY total DESC
                """,
                (f"-{days}",),
            ).fetchall()

            result = {}
            for row in rows:
                wave_pos = row["wave_position"]
                total = row["total"]
                wins = row["wins"] or 0
                result[wave_pos] = {
                    "win_rate": round((wins / total * 100), 1) if total > 0 else 0,
                    "total": total,
                    "avg_profit": round(row["avg_profit"] or 0, 2),
                }

            return result

    def get_confidence_performance_stats(self, days: int = 30) -> dict:
        """Get win rates by confidence bucket for instruction context.

        Args:
            days: Number of days to look back

        Returns:
            Dict mapping confidence bucket to performance stats
            e.g., {"80+": {"win_rate": 55, "total": 10}, ...}
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    CASE
                        WHEN s.confidence >= 80 THEN '80+'
                        WHEN s.confidence >= 70 THEN '70+'
                        WHEN s.confidence >= 60 THEN '60+'
                        WHEN s.confidence >= 50 THEN '50+'
                        ELSE '<50'
                    END as bucket,
                    COUNT(*) as total,
                    SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(t.profit) as avg_profit
                FROM trades t
                JOIN signals s ON t.signal_id = s.id
                WHERE t.status = 'closed'
                    AND t.close_time >= datetime('now', ? || ' days')
                GROUP BY bucket
                ORDER BY bucket DESC
                """,
                (f"-{days}",),
            ).fetchall()

            result = {}
            for row in rows:
                bucket = row["bucket"]
                total = row["total"]
                wins = row["wins"] or 0
                result[bucket] = {
                    "win_rate": round((wins / total * 100), 1) if total > 0 else 0,
                    "total": total,
                    "avg_profit": round(row["avg_profit"] or 0, 2),
                }

            return result

    def get_instruction_performance_context(self, days: int = 30) -> dict:
        """Get comprehensive performance context for InstructionBuilder.

        Aggregates wave performance, confidence buckets, session performance,
        and streak info into a single context object.

        Args:
            days: Number of days to look back

        Returns:
            Dict with all performance metrics for instruction assembly
        """
        wave_stats = self.get_wave_performance_stats(days)
        conf_stats = self.get_confidence_performance_stats(days)
        session_stats = self._get_session_performance_stats()
        streak_info = self._get_current_streak()
        trade_summary = self.get_trade_summary()

        # Calculate overall win rate
        total = trade_summary.get("total_trades", 0)
        wins = trade_summary.get("wins", 0)
        overall_win_rate = round((wins / total * 100), 1) if total > 0 else None

        # Find best/worst wave positions
        best_wave = None
        worst_wave = None
        best_wave_rate = 0
        worst_wave_rate = 100

        for wave, stats in wave_stats.items():
            if stats["total"] >= 5:  # Require minimum sample
                if stats["win_rate"] > best_wave_rate:
                    best_wave_rate = stats["win_rate"]
                    best_wave = wave
                if stats["win_rate"] < worst_wave_rate:
                    worst_wave_rate = stats["win_rate"]
                    worst_wave = wave

        # Find best/worst sessions
        best_session = None
        worst_session = None
        best_session_rate = 0
        worst_session_rate = 100

        for session, stats in session_stats.items():
            if stats["total"] >= 5:
                if stats["win_rate"] > best_session_rate:
                    best_session_rate = stats["win_rate"]
                    best_session = session
                if stats["win_rate"] < worst_session_rate:
                    worst_session_rate = stats["win_rate"]
                    worst_session = session

        # Calculate calibrated minimum confidence
        calibrated_min = 60  # Default
        for bucket in ["80+", "70+", "60+", "50+"]:
            if bucket in conf_stats and conf_stats[bucket]["total"] >= 5:
                if conf_stats[bucket]["win_rate"] >= 50:
                    # Extract numeric threshold
                    calibrated_min = int(bucket.rstrip("+"))
                    break

        return {
            "overall_win_rate": overall_win_rate,
            "wave_performance": wave_stats,
            "confidence_performance": conf_stats,
            "session_performance": session_stats,
            "current_streak": streak_info,
            "best_wave_position": best_wave,
            "worst_wave_position": worst_wave,
            "best_session": best_session,
            "worst_session": worst_session,
            "calibrated_min_confidence": calibrated_min,
            "looking_for": "entry",  # Default, can be overridden
        }


# Lazy singleton
_database: Optional[Database] = None


def get_database() -> Database:
    """Get or create database singleton."""
    global _database
    if _database is None:
        _database = Database()
    return _database
