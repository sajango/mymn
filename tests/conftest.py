"""Pytest configuration and shared fixtures for MT5 Elliott Wave Trading tests.

Provides centralized fixtures for:
- Database setup with temp directories
- Mock MT5 client with configurable responses
- Mock settings with test defaults
- Common signal and trade fixtures
- Async test configuration
"""

import gc
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

# Ensure src is in path before any imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set required env vars before importing config-dependent modules
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")


# Configure pytest-asyncio
def pytest_configure(config):
    """Configure pytest with asyncio_default_fixture_loop_scope."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )


# Fixture loop scope configuration
pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def temp_db(tmp_path: Path) -> Generator:
    """Create temporary database for testing.

    Uses a fresh database for each test to avoid state pollution.
    """
    from src.database import Database

    db_path = tmp_path / "test.db"
    db = Database(db_path)
    yield db
    # Database uses context manager for connections, no explicit close needed
    gc.collect()


@pytest.fixture
def mock_mt5() -> MagicMock:
    """Create mock MT5 client with common method stubs.

    Returns:
        Configured MagicMock with paper trading defaults.
    """
    mock = MagicMock()
    mock.config = MagicMock()
    mock.config.paper_trading = True
    mock.config.risk_percent = 1.5
    mock.config.max_position_size = 0.1
    mock.config.confidence_full_position = 75
    mock.config.confidence_half_position = 60
    mock.config.trail_atr_multiplier = 1.5
    mock.config.breakeven_buffer_pips = 5

    # Common method returns
    mock._initialized = False
    mock.is_connected.return_value = False
    mock.calculate_position_size.return_value = 0.05
    mock.place_market_order.return_value = -1  # Paper trade ticket
    mock.get_current_atr.return_value = 10.0
    mock.modify_position.return_value = True
    mock.validate_symbol.return_value = True
    mock.close_partial.return_value = True
    mock.get_current_spread.return_value = 2.0

    return mock


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings with test defaults."""
    from src.config import Settings

    settings = Settings(
        _env_file=None,
        mt5_symbol="XAUUSD",
        paper_trading=True,
        risk_percent=1.5,
        max_spread_pips=4.0,
        confidence_threshold=60,
    )
    return settings


@pytest.fixture
def buy_signal():
    """Create sample BUY signal for testing."""
    from src.signal_parser import (
        Signal,
        SignalAction,
        TakeProfit,
        TradingSignal,
        WaveAnalysis,
    )

    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.BUY,
            entry_price=3340.0,
            stop_loss=3310.0,
            stop_loss_atr=3312.5,
            take_profit=[
                TakeProfit(level="TP1", price=3380.0, close_percent=50),
                TakeProfit(level="TP2", price=3420.0, close_percent=30),
                TakeProfit(level="TP3", price=3460.0, close_percent=20),
            ],
            risk_reward=2.67,
            confidence=78,
        ),
        wave_analysis=WaveAnalysis(
            h4_trend="Bullish",
            current_wave="Wave 3 impulse",
            invalidation_price=3290.0,
        ),
    )


@pytest.fixture
def sell_signal():
    """Create sample SELL signal for testing."""
    from src.signal_parser import (
        Signal,
        SignalAction,
        TakeProfit,
        TradingSignal,
    )

    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.SELL,
            entry_price=3340.0,
            stop_loss=3370.0,
            take_profit=[
                TakeProfit(level="TP1", price=3300.0, close_percent=50),
            ],
            risk_reward=1.33,
            confidence=65,
        ),
    )


@pytest.fixture
def no_trade_signal():
    """Create NO_TRADE signal for testing."""
    from src.signal_parser import (
        Signal,
        SignalAction,
        TradingSignal,
    )

    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.NO_TRADE,
            confidence=30,
            reason="Unclear wave structure",
        ),
    )


@pytest.fixture
def wait_signal():
    """Create WAIT signal for testing."""
    from src.signal_parser import (
        Signal,
        SignalAction,
        TradingSignal,
    )

    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.WAIT,
            confidence=55,
            details="Waiting for wave completion",
        ),
    )


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV DataFrame for testing indicators."""
    import numpy as np
    import pandas as pd

    np.random.seed(42)
    n = 100
    base_price = 2000.0
    returns = np.random.normal(0, 0.002, n)
    prices = base_price * (1 + returns).cumprod()

    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="h"),
        "open": prices,
        "high": prices * (1 + np.abs(np.random.normal(0, 0.001, n))),
        "low": prices * (1 - np.abs(np.random.normal(0, 0.001, n))),
        "close": prices + np.random.randn(n) * 0.5,
        "tick_volume": np.random.randint(100, 1000, n),
    })


@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run for Claude CLI tests."""
    with patch("src.claude_client.subprocess.run") as mock:
        yield mock


@pytest.fixture
def mock_telegram_bot():
    """Create mock Telegram bot for testing."""
    with patch("src.telegram_bot.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            telegram_bot_token="test_token",
            telegram_chat_id="123456",
            mt5_symbol="XAUUSD",
            paper_trading=True,
            signal_timeout=300,
        )
        from src.telegram_bot import TradingBot
        yield TradingBot()


@pytest.fixture
def valid_json_response():
    """Sample valid Claude JSON response for testing."""
    return '''```json
    {
        "timestamp": "2024-08-21T14:30:00Z",
        "symbol": "XAUUSD",
        "signal": {
            "action": "BUY",
            "entry_price": 3340.00,
            "stop_loss": 3310.00,
            "take_profit": [
                {"level": "TP1", "price": 3380.00, "close_percent": 50}
            ],
            "confidence": 78
        }
    }
    ```'''


@pytest.fixture
def v4_signal_json():
    """Load v4 signal fixture from file."""
    fixture_path = Path(__file__).parent / "fixtures" / "v4_signal_sample.json"
    return json.loads(fixture_path.read_text())


@pytest.fixture
def v4_signal(v4_signal_json):
    """Create TradingSignal from v4 fixture."""
    from src.signal_parser import TradingSignal
    return TradingSignal.model_validate(v4_signal_json)
