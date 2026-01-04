"""Test MT5 client module."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mt5_client import MT5Client


class TestIndicatorCalculations:
    """Test indicator calculations without MT5 connection."""

    @pytest.fixture
    def sample_data(self) -> pd.DataFrame:
        """Create sample OHLCV data for testing."""
        # Generate 50 bars of price data with realistic movement
        np.random.seed(42)
        base_price = 2000.0
        returns = np.random.normal(0, 0.002, 50)
        prices = base_price * (1 + returns).cumprod()

        data = {
            "close": prices,
            "high": prices * (1 + np.abs(np.random.normal(0, 0.001, 50))),
            "low": prices * (1 - np.abs(np.random.normal(0, 0.001, 50))),
        }
        return pd.DataFrame(data)

    def test_calculate_rsi_returns_series(self, sample_data: pd.DataFrame) -> None:
        """Test RSI calculation returns proper series."""
        rsi = MT5Client.calculate_rsi(sample_data["close"], period=14)

        assert isinstance(rsi, pd.Series)
        assert len(rsi) == len(sample_data)

    def test_calculate_rsi_values_in_range(self, sample_data: pd.DataFrame) -> None:
        """Test RSI values are between 0 and 100."""
        rsi = MT5Client.calculate_rsi(sample_data["close"], period=14)

        # Skip NaN values from warmup period
        valid_rsi = rsi.dropna()
        assert all(valid_rsi >= 0)
        assert all(valid_rsi <= 100)

    def test_calculate_rsi_warmup_period(self, sample_data: pd.DataFrame) -> None:
        """Test RSI warmup period produces valid values (not NaN)."""
        period = 14
        rsi = MT5Client.calculate_rsi(sample_data["close"], period=period)

        # RSI should never have NaN - division by zero handled by returning 100
        assert not rsi.isna().any()
        # First value is NaN from diff(), but RSI handles it
        assert len(rsi) == len(sample_data)

    def test_calculate_ema_returns_series(self, sample_data: pd.DataFrame) -> None:
        """Test EMA calculation returns proper series."""
        ema = MT5Client.calculate_ema(sample_data["close"], period=34)

        assert isinstance(ema, pd.Series)
        assert len(ema) == len(sample_data)
        assert not ema.isna().all()

    def test_calculate_ema_different_periods(self, sample_data: pd.DataFrame) -> None:
        """Test EMA with different periods produces different results."""
        ema_34 = MT5Client.calculate_ema(sample_data["close"], period=34)
        ema_89 = MT5Client.calculate_ema(sample_data["close"], period=89)

        # EMAs with different periods should differ
        assert not ema_34.equals(ema_89)
        # Shorter period EMA should be more responsive (different values)
        assert (ema_34 != ema_89).any()

    def test_calculate_macd_returns_tuple(self, sample_data: pd.DataFrame) -> None:
        """Test MACD calculation returns three series."""
        result = MT5Client.calculate_macd(sample_data["close"])

        assert isinstance(result, tuple)
        assert len(result) == 3

        macd, signal, histogram = result
        assert isinstance(macd, pd.Series)
        assert isinstance(signal, pd.Series)
        assert isinstance(histogram, pd.Series)

    def test_calculate_macd_histogram_relationship(
        self, sample_data: pd.DataFrame
    ) -> None:
        """Test MACD histogram equals MACD minus signal."""
        macd, signal, histogram = MT5Client.calculate_macd(sample_data["close"])

        # Histogram should be MACD - Signal
        expected = macd - signal
        np.testing.assert_array_almost_equal(histogram.values, expected.values)

    def test_calculate_atr_returns_series(self, sample_data: pd.DataFrame) -> None:
        """Test ATR calculation returns proper series."""
        atr = MT5Client.calculate_atr(
            sample_data["high"], sample_data["low"], sample_data["close"], period=14
        )

        assert isinstance(atr, pd.Series)
        assert len(atr) == len(sample_data)

    def test_calculate_atr_positive_values(self, sample_data: pd.DataFrame) -> None:
        """Test ATR values are positive."""
        atr = MT5Client.calculate_atr(
            sample_data["high"], sample_data["low"], sample_data["close"], period=14
        )

        valid_atr = atr.dropna()
        assert all(valid_atr >= 0)

    def test_calculate_atr_has_warmup_nans(self, sample_data: pd.DataFrame) -> None:
        """Test ATR has NaN values during warmup period."""
        period = 14
        atr = MT5Client.calculate_atr(
            sample_data["high"], sample_data["low"], sample_data["close"], period=period
        )

        # First 'period' values should have NaN
        assert atr.iloc[: period - 1].isna().any()


class TestMT5ClientMethods:
    """Test MT5Client class methods."""

    def test_add_indicators_adds_all_columns(self) -> None:
        """Test add_indicators adds all required indicator columns."""
        # Create sample OHLCV dataframe
        np.random.seed(42)
        base = 2000.0
        n = 100
        prices = base + np.cumsum(np.random.randn(n) * 5)

        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=n, freq="h"),
                "open": prices,
                "high": prices + np.abs(np.random.randn(n)),
                "low": prices - np.abs(np.random.randn(n)),
                "close": prices + np.random.randn(n) * 0.5,
                "tick_volume": np.random.randint(100, 1000, n),
            }
        )

        client = MT5Client()
        result = client.add_indicators(df)

        # Check all expected columns exist
        expected_cols = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "rsi_14",
            "ema_34",
            "ema_89",
            "macd",
            "macd_signal",
            "macd_histogram",
            "atr_14",
        ]

        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_add_indicators_preserves_original(self) -> None:
        """Test add_indicators doesn't modify original dataframe."""
        np.random.seed(42)
        n = 50
        prices = 2000 + np.cumsum(np.random.randn(n))

        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=n, freq="h"),
                "open": prices,
                "high": prices + 1,
                "low": prices - 1,
                "close": prices,
                "tick_volume": [100] * n,
            }
        )

        original_cols = list(df.columns)
        client = MT5Client()
        _ = client.add_indicators(df)

        # Original should be unchanged
        assert list(df.columns) == original_cols

    def test_timeframes_constant(self) -> None:
        """Test TIMEFRAMES constant has expected entries."""
        from src.mt5_client import TIMEFRAMES

        expected_keys = ["H4", "H1", "M30", "M15"]
        assert list(TIMEFRAMES.keys()) == expected_keys


class TestMT5ClientInitialization:
    """Test MT5Client initialization (mocked, no MT5 required)."""

    def test_client_initializes_not_connected(self) -> None:
        """Test client starts in not-connected state."""
        client = MT5Client()
        assert client._initialized is False

    def test_is_connected_returns_false_when_not_initialized(self) -> None:
        """Test is_connected returns False when not initialized."""
        client = MT5Client()
        assert client.is_connected() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
