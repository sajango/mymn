# Phase 2: MT5 Data Export

## Context Links
- [Plan Overview](./plan.md)
- [Phase 1: Project Setup](./phase-01-project-setup.md)
- [MT5 Research](./research/researcher-02-mt5-python.md)

## Overview
- **Priority**: P1
- **Status**: Pending
- **Effort**: 3h
- **Description**: Connect to MT5, fetch OHLCV data, calculate indicators, export CSV

## Key Insights
- MT5 terminal must be running on Windows
- Use `copy_rates_from_pos()` for data fetching
- Calculate indicators in Python (no TA-Lib dependency)
- Export 4 timeframes: H4, H1, M30, M15 (200 candles each)
- Symbol name varies by broker (XAUUSD, XAUUSDm, GOLD)

## Requirements

### Functional
- Initialize MT5 connection with retry
- Fetch 200 candles for each timeframe
- Calculate RSI(14), EMA(34), EMA(89), MACD(12,26,9), ATR(14)
- Export to CSV with correct column format
- Health check for connection status

### Non-Functional
- Sync operations (will be wrapped in executor)
- Graceful handling of disconnection
- Validate symbol existence before fetch

## Architecture

### Data Flow
```
MT5 Terminal
    ↓
mt5.initialize()
    ↓
mt5.copy_rates_from_pos(symbol, tf, 0, 200)
    ↓
pd.DataFrame conversion
    ↓
calculate_indicators()
    ↓
df.to_csv()
```

### CSV Output Format
```
timestamp,open,high,low,close,tick_volume,rsi_14,ema_34,ema_89,macd,macd_signal,macd_histogram,atr_14
2026.01.04 12:00,3340.50,3345.20,3338.00,3342.80,1234,52.3,3341.5,3335.2,2.5,1.8,0.7,12.5
```

## Related Code Files

### Files to Create
- `src/mt5_client.py` - MT5 connection and operations

## Implementation Steps

1. **Create src/mt5_client.py**

```python
"""MT5 client for data export and trade execution"""
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd
import numpy as np

from src.config import config

logger = logging.getLogger(__name__)

TIMEFRAMES = {
    "H4": mt5.TIMEFRAME_H4,
    "H1": mt5.TIMEFRAME_H1,
    "M30": mt5.TIMEFRAME_M30,
    "M15": mt5.TIMEFRAME_M15,
}


class MT5Client:
    def __init__(self):
        self._initialized = False

    def initialize(self, retries: int = 3, delay: float = 2.0) -> bool:
        """Initialize MT5 connection with retry"""
        for attempt in range(retries):
            try:
                if config.mt5_path:
                    success = mt5.initialize(path=config.mt5_path)
                else:
                    success = mt5.initialize()

                if success:
                    self._initialized = True
                    logger.info(f"MT5 initialized: {mt5.terminal_info()}")
                    return True

                error = mt5.last_error()
                logger.warning(f"MT5 init attempt {attempt+1} failed: {error}")

            except Exception as e:
                logger.error(f"MT5 init exception: {e}")

            time.sleep(delay)

        logger.error("MT5 initialization failed after all retries")
        return False

    def shutdown(self):
        """Shutdown MT5 connection"""
        if self._initialized:
            mt5.shutdown()
            self._initialized = False
            logger.info("MT5 shutdown complete")

    def is_connected(self) -> bool:
        """Check if MT5 is connected"""
        if not self._initialized:
            return False
        try:
            info = mt5.terminal_info()
            return info is not None and info.connected
        except:
            return False

    def validate_symbol(self, symbol: str) -> bool:
        """Check if symbol exists and select it"""
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Symbol {symbol} not found")
            return False

        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                logger.error(f"Failed to select symbol {symbol}")
                return False

        return True

    def fetch_ohlcv(
        self, symbol: str, timeframe: str, bars: int = 200
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data for given symbol and timeframe"""
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
        df = df.rename(columns={"time": "timestamp", "tick_volume": "tick_volume"})

        return df[["timestamp", "open", "high", "low", "close", "tick_volume"]]

    @staticmethod
    def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def calculate_ema(close: pd.Series, period: int) -> pd.Series:
        """Calculate EMA"""
        return close.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_macd(
        close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate MACD, Signal, Histogram"""
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
        """Calculate ATR"""
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all indicators to dataframe"""
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

    def export_csv(self, symbol: str, output_dir: Optional[Path] = None) -> dict[str, Path]:
        """Export all timeframes to CSV with indicators"""
        output_dir = output_dir or config.csv_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        if not self.validate_symbol(symbol):
            raise ValueError(f"Invalid symbol: {symbol}")

        exported = {}

        for tf_name in TIMEFRAMES.keys():
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
```

2. **Add basic tests**

```python
# tests/test_mt5.py
import pytest
from src.mt5_client import mt5_client, MT5Client

def test_indicator_calculations():
    """Test indicator calculations without MT5"""
    import pandas as pd
    import numpy as np

    # Create sample data
    data = {
        "close": [100, 102, 101, 103, 104, 103, 105, 106, 104, 107],
        "high": [101, 103, 102, 104, 105, 104, 106, 107, 105, 108],
        "low": [99, 101, 100, 102, 103, 102, 104, 105, 103, 106],
    }
    df = pd.DataFrame(data)

    # Test RSI
    rsi = MT5Client.calculate_rsi(df["close"], period=5)
    assert len(rsi) == 10
    assert not rsi.iloc[5:].isna().any()

    # Test EMA
    ema = MT5Client.calculate_ema(df["close"], period=3)
    assert len(ema) == 10

    # Test MACD
    macd, signal, hist = MT5Client.calculate_macd(df["close"], 3, 5, 2)
    assert len(macd) == 10

    # Test ATR
    atr = MT5Client.calculate_atr(df["high"], df["low"], df["close"], period=3)
    assert len(atr) == 10
```

## Todo List

- [ ] Create src/mt5_client.py
- [ ] Implement initialize() with retry
- [ ] Implement fetch_ohlcv()
- [ ] Implement indicator calculations
- [ ] Implement export_csv()
- [ ] Write tests/test_mt5.py
- [ ] Test with live MT5 terminal
- [ ] Verify CSV format matches instructions.md

## Success Criteria

- [ ] MT5 connects successfully
- [ ] All 4 timeframes export correctly
- [ ] CSV columns match instructions.md format
- [ ] Indicators calculated correctly
- [ ] Graceful handling when MT5 not running

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Symbol name mismatch | Medium | High | Auto-detect from broker |
| MT5 not running | Medium | High | Clear error message |
| Data gaps | Low | Medium | Check for None values |

## Security Considerations

- No credentials in this phase
- CSV files may contain price data (not sensitive)

## Next Steps

→ [Phase 3: Claude AI Integration](./phase-03-claude-integration.md)
