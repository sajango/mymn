"""Tests for Dashboard API endpoints.

Tests the FastAPI dashboard backend with mock database data.
"""

import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Import test-required modules
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient


@pytest.fixture
def temp_db():
    """Create temporary database with test data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create tables
    conn.execute("""
        CREATE TABLE signals (
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

    conn.execute("""
        CREATE TABLE trades (
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

    conn.execute("""
        CREATE TABLE tp_levels (
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

    conn.execute("""
        CREATE TABLE trade_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trade_id) REFERENCES trades (id)
        )
    """)

    conn.execute("""
        CREATE TABLE skipped_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reason TEXT NOT NULL,
            details TEXT,
            session TEXT,
            spread_pips REAL,
            confidence INTEGER,
            signal_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert test data
    now = datetime.now(timezone.utc)

    # Signals
    for i in range(5):
        conn.execute("""
            INSERT INTO signals (timestamp, symbol, action, entry_price, stop_loss,
                take_profit_1, confidence, wave_position, status)
            VALUES (?, 'XAUUSD', ?, ?, ?, ?, ?, 'Wave 3', 'executed')
        """, (
            (now - timedelta(days=i)).isoformat(),
            'BUY' if i % 2 == 0 else 'SELL',
            2000 + i * 10,
            1990 + i * 10,
            2020 + i * 10,
            70 + i * 5,
        ))

    # Trades (3 winning, 2 losing)
    profits = [50, 30, -20, 25, -15]
    for i, profit in enumerate(profits):
        signal_id = i + 1
        conn.execute("""
            INSERT INTO trades (signal_id, ticket, symbol, action, volume, initial_volume,
                entry_price, stop_loss, initial_stop_loss, take_profit,
                open_time, close_time, close_price, profit, status)
            VALUES (?, ?, 'XAUUSD', ?, 0.1, 0.1, ?, ?, ?, ?, ?, ?, ?, ?, 'closed')
        """, (
            signal_id,
            100000 + i,
            'BUY' if i % 2 == 0 else 'SELL',
            2000 + i * 10,
            1990 + i * 10,
            1990 + i * 10,
            2020 + i * 10,
            (now - timedelta(days=5-i, hours=10+i)).isoformat(),
            (now - timedelta(days=5-i, hours=5+i)).isoformat(),
            2010 + i * 10,
            profit,
        ))

    # One open trade
    conn.execute("""
        INSERT INTO trades (signal_id, ticket, symbol, action, volume, initial_volume,
            entry_price, stop_loss, initial_stop_loss, take_profit,
            open_time, trailing_state, status)
        VALUES (?, ?, 'XAUUSD', 'BUY', 0.05, 0.1, 2050, 2040, 2040, 2070, ?, 'activated', 'partial')
    """, (5, 100005, now.isoformat()))

    # Skipped signals
    conn.execute("""
        INSERT INTO skipped_signals (reason, details, spread_pips, confidence)
        VALUES ('spread_high', 'Spread 5.5 pips', 5.5, 75)
    """)
    conn.execute("""
        INSERT INTO skipped_signals (reason, details, confidence)
        VALUES ('low_confidence', 'Confidence 55%', 55)
    """)

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    db_path.unlink(missing_ok=True)


@pytest.fixture
def client(temp_db):
    """Create test client with patched database path."""
    with patch("dashboard.backend.services.database.DB_PATH", temp_db):
        from dashboard.backend.main import app
        with TestClient(app) as client:
            yield client


class TestHealthEndpoints:
    """Test health and root endpoints."""

    def test_root(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "api" in data

    def test_health(self, client):
        """Test health endpoint with database."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"


class TestStatsEndpoints:
    """Test statistics endpoints."""

    def test_stats(self, client):
        """Test overall stats endpoint."""
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()

        assert data["total_trades"] == 5
        assert data["wins"] == 3
        assert data["losses"] == 2
        assert data["win_rate"] == 60.0
        assert data["total_pnl"] == 70.0  # 50+30-20+25-15
        assert "profit_factor" in data

    def test_confidence_analysis(self, client):
        """Test confidence analysis endpoint."""
        response = client.get("/api/confidence-analysis")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        # Should have data grouped by confidence bands
        for band in data:
            assert "band" in band
            assert "total" in band
            assert "win_rate" in band

    def test_time_analysis(self, client):
        """Test time analysis endpoint."""
        response = client.get("/api/time-analysis")
        assert response.status_code == 200
        data = response.json()

        assert "by_hour" in data
        assert "by_day" in data


class TestTradesEndpoints:
    """Test trade-related endpoints."""

    def test_trades_list(self, client):
        """Test trades list with pagination."""
        response = client.get("/api/trades?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()

        assert "trades" in data
        assert "total" in data
        assert data["total"] == 6  # 5 closed + 1 partial

    def test_trades_filter_status(self, client):
        """Test trades filter by status."""
        response = client.get("/api/trades?status=closed")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        for trade in data["trades"]:
            assert trade["status"] == "closed"

    def test_trade_detail(self, client):
        """Test single trade detail."""
        response = client.get("/api/trades/1")
        assert response.status_code == 200
        data = response.json()

        assert "trade" in data
        assert "tp_levels" in data
        assert "events" in data

    def test_positions(self, client):
        """Test open positions endpoint."""
        response = client.get("/api/positions")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) == 1  # One partial position
        assert data[0]["status"] == "partial"

    def test_signals(self, client):
        """Test signals endpoint."""
        response = client.get("/api/signals")
        assert response.status_code == 200
        data = response.json()

        assert "signals" in data
        assert data["total"] == 5


class TestAnalyticsEndpoints:
    """Test analytics endpoints."""

    def test_equity_curve(self, client):
        """Test equity curve endpoint."""
        response = client.get("/api/equity")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        if len(data) > 0:
            assert "time" in data[0]
            assert "equity" in data[0]

    def test_daily_pnl(self, client):
        """Test daily P&L endpoint."""
        response = client.get("/api/daily-pnl?days=30")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        if len(data) > 0:
            assert "date" in data[0]
            assert "pnl" in data[0]

    def test_skipped_signals(self, client):
        """Test skipped signals summary."""
        response = client.get("/api/skipped-signals?days=7")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        # Should have 2 different reasons
        assert len(data) == 2

    def test_weekly_summary(self, client):
        """Test weekly summary endpoint."""
        response = client.get("/api/weekly-summary")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        if len(data) > 0:
            assert "week" in data[0]
            assert "pnl" in data[0]
