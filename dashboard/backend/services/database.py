"""Read-only database service for dashboard API.

Connects to trading.db in read-only mode to prevent any
interference with the trading bot's database operations.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

# Database path from env or default
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).parent.parent.parent.parent / "data" / "trading.db"))


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Get read-only database connection.

    Uses SQLite URI mode with read-only flag to prevent writes.
    """
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def check_db_exists() -> bool:
    """Check if database file exists."""
    return DB_PATH.exists()
