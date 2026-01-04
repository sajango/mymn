"""MT5 client for data export and trade execution."""

import logging
import time
from pathlib import Path
from typing import Optional

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from src.config import get_settings

logger = logging.getLogger(__name__)

TIMEFRAMES = {
    "H4": mt5.TIMEFRAME_H4,
    "H1": mt5.TIMEFRAME_H1,
    "M30": mt5.TIMEFRAME_M30,
    "M15": mt5.TIMEFRAME_M15,
}


class MT5Client:
    """Client for MT5 terminal operations."""

    def __init__(self, config=None):
        self._initialized = False
        self._config = config

    @property
    def config(self):
        """Lazy load config on first access."""
        if self._config is None:
            self._config = get_settings()
        return self._config

    def initialize(self, retries: int = 3, delay: float = 2.0) -> bool:
        """Initialize MT5 connection with retry.

        Args:
            retries: Number of retry attempts
            delay: Delay between retries in seconds

        Returns:
            True if initialization successful
        """
        for attempt in range(retries):
            try:
                if self.config.mt5_path:
                    success = mt5.initialize(path=self.config.mt5_path)
                else:
                    success = mt5.initialize()

                if success:
                    self._initialized = True
                    info = mt5.terminal_info()
                    logger.info(f"MT5 initialized: {info}")
                    return True

                error = mt5.last_error()
                logger.warning(f"MT5 init attempt {attempt + 1} failed: {error}")

            except Exception as e:
                logger.error(f"MT5 init exception: {e}")

            time.sleep(delay)

        logger.error("MT5 initialization failed after all retries")
        return False

    def shutdown(self) -> None:
        """Shutdown MT5 connection."""
        if self._initialized:
            mt5.shutdown()
            self._initialized = False
            logger.info("MT5 shutdown complete")

    def is_connected(self) -> bool:
        """Check if MT5 is connected.

        Returns:
            True if connected and terminal is active
        """
        if not self._initialized:
            return False
        try:
            info = mt5.terminal_info()
            return info is not None and info.connected
        except Exception as e:
            logger.warning(f"Connection check failed: {e}")
            return False

    def validate_symbol(self, symbol: str) -> bool:
        """Check if symbol exists and select it.

        Args:
            symbol: Trading symbol to validate

        Returns:
            True if symbol is valid and selected
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Symbol {symbol} not found")
            return False

        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                logger.error(f"Failed to select symbol {symbol}")
                return False

        return True

    def get_current_spread(self, symbol: str) -> Optional[float]:
        """Get current spread in pips for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Spread in pips or None if unavailable
        """
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        info = mt5.symbol_info(symbol)
        if info is None:
            return None

        # Point is the smallest price change
        spread_points = tick.ask - tick.bid
        # For gold, 1 pip = 0.1, point = 0.01 (10 points = 1 pip)
        spread_pips = spread_points / info.point / 10
        return round(spread_pips, 2)

    def fetch_ohlcv(
        self, symbol: str, timeframe: str, bars: int = 200
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data for given symbol and timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe string (H4, H1, M30, M15)
            bars: Number of bars to fetch

        Returns:
            DataFrame with OHLCV data or None on error
        """
        if timeframe not in TIMEFRAMES:
            logger.error(f"Invalid timeframe: {timeframe}")
            return None

        tf = TIMEFRAMES[timeframe]
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)

        if rates is None:
            error = mt5.last_error()
            logger.error(f"Failed to fetch {symbol} {timeframe}: {error}")
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(columns={"time": "timestamp"})

        return df[["timestamp", "open", "high", "low", "close", "tick_volume"]]

    @staticmethod
    def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator.

        Args:
            close: Close price series
            period: RSI period

        Returns:
            RSI values series
        """
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        # Handle division by zero - when loss is 0, RSI is 100
        loss = loss.replace(0, np.nan)
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        # When loss is 0 (all gains), RSI = 100
        rsi = rsi.fillna(100)
        return rsi

    @staticmethod
    def calculate_ema(close: pd.Series, period: int) -> pd.Series:
        """Calculate EMA indicator.

        Args:
            close: Close price series
            period: EMA period

        Returns:
            EMA values series
        """
        return close.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_macd(
        close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate MACD indicator.

        Args:
            close: Close price series
            fast: Fast EMA period
            slow: Slow EMA period
            signal: Signal line period

        Returns:
            Tuple of (MACD line, Signal line, Histogram)
        """
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def calculate_atr(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> pd.Series:
        """Calculate ATR indicator.

        Args:
            high: High price series
            low: Low price series
            close: Close price series
            period: ATR period

        Returns:
            ATR values series
        """
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all technical indicators to dataframe.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with added indicator columns
        """
        df = df.copy()

        # RSI
        df["rsi_14"] = self.calculate_rsi(df["close"], 14)

        # EMAs
        df["ema_34"] = self.calculate_ema(df["close"], 34)
        df["ema_89"] = self.calculate_ema(df["close"], 89)

        # MACD
        macd, signal, hist = self.calculate_macd(df["close"])
        df["macd"] = macd
        df["macd_signal"] = signal
        df["macd_histogram"] = hist

        # ATR
        df["atr_14"] = self.calculate_atr(df["high"], df["low"], df["close"], 14)

        return df

    def export_csv(
        self, symbol: str, output_dir: Optional[Path] = None
    ) -> dict[str, Path]:
        """Export all timeframes to CSV with indicators.

        Args:
            symbol: Trading symbol
            output_dir: Output directory (defaults to config csv_dir)

        Returns:
            Dict mapping timeframe to file path

        Raises:
            ValueError: If symbol is invalid
        """
        output_dir = output_dir or self.config.csv_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        if not self.validate_symbol(symbol):
            raise ValueError(f"Invalid symbol: {symbol}")

        exported = {}

        for tf_name in TIMEFRAMES:
            df = self.fetch_ohlcv(symbol, tf_name, 200)
            if df is None:
                logger.warning(f"Skipping {tf_name}: no data")
                continue

            # Add indicators
            df = self.add_indicators(df)

            # Format timestamp for CSV
            df["timestamp"] = df["timestamp"].dt.strftime("%Y.%m.%d %H:%M")

            # Round numeric columns
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            df[numeric_cols] = df[numeric_cols].round(2)

            # Export
            filename = f"{symbol.lower()}_{tf_name.lower()}.csv"
            filepath = output_dir / filename
            df.to_csv(filepath, index=False)

            exported[tf_name] = filepath
            logger.info(f"Exported {tf_name}: {filepath}")

        return exported


# Singleton instance
mt5_client = MT5Client()
