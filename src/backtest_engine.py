"""Backtesting engine for historical strategy validation.

Features:
- Historical data loading from CSV with validation
- Signal generation (rule-based or cached)
- Trade simulation with realistic slippage and spreads
- Trailing stop and partial TP support
- Performance metrics calculation
- Report generation
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Security: Input validation patterns
VALID_SYMBOL_PATTERN = re.compile(r'^[A-Z0-9]{3,10}$')
VALID_TIMEFRAME_PATTERN = re.compile(r'^(M\d+|H\d+|D\d+|W\d+|MN\d+)$')
MAX_CSV_FILE_SIZE = 100_000_000  # 100MB
MAX_CSV_ROWS = 100_000
MAX_BARS_EXPORT = 100_000


class SimTradeStatus(str, Enum):
    """Simulated trade status."""
    OPEN = "open"
    PARTIAL = "partial"
    CLOSED = "closed"


def _validate_symbol(symbol: str) -> None:
    """Validate symbol format to prevent path traversal."""
    if not VALID_SYMBOL_PATTERN.match(symbol):
        raise ValueError(f"Invalid symbol format: {symbol}")


def _validate_timeframe(timeframe: str) -> None:
    """Validate timeframe format."""
    if not VALID_TIMEFRAME_PATTERN.match(timeframe):
        raise ValueError(f"Invalid timeframe format: {timeframe}")


def _validate_path_within_directory(file_path: Path, base_path: Path) -> None:
    """Validate file path is within expected directory (prevent traversal)."""
    resolved_file = file_path.resolve()
    resolved_base = base_path.resolve()
    if not str(resolved_file).startswith(str(resolved_base)):
        raise ValueError("Path traversal detected - file outside allowed directory")


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""

    # Data settings
    data_path: Path = field(default_factory=lambda: Path("data/backtest"))
    symbol: str = "XAUUSD"
    timeframes: List[str] = field(
        default_factory=lambda: ["H4", "H1", "M30", "M15"]
    )

    # Trading settings
    min_confidence: int = 50
    initial_balance: float = 10000.0
    risk_percent: float = 1.5
    max_position_size: float = 0.1

    # Simulation settings
    slippage_pips: float = 1.0
    spread_pips: float = 2.5
    random_seed: Optional[int] = None  # For reproducible backtests

    # Trailing stop settings
    trail_atr_multiplier: float = 1.5
    breakeven_buffer_pips: float = 5.0

    # Analysis settings
    analysis_timeframe: str = "M15"
    analysis_interval_bars: int = 1

    # Configurable multipliers (previously hardcoded)
    point_value: float = 100.0  # $100 per pip for 1 lot XAUUSD
    sl_atr_multiplier: float = 2.0
    tp_atr_multipliers: List[float] = field(
        default_factory=lambda: [1.5, 2.5, 4.0]
    )
    default_atr_for_trailing: float = 2.0

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate numeric ranges
        if self.risk_percent <= 0 or self.risk_percent > 100:
            raise ValueError(f"risk_percent must be 0-100: {self.risk_percent}")
        if self.initial_balance <= 0:
            raise ValueError(f"initial_balance must be positive: {self.initial_balance}")
        if self.slippage_pips < 0:
            raise ValueError(f"slippage_pips must be non-negative: {self.slippage_pips}")
        if self.spread_pips < 0:
            raise ValueError(f"spread_pips must be non-negative: {self.spread_pips}")
        if self.min_confidence < 0 or self.min_confidence > 100:
            raise ValueError(f"min_confidence must be 0-100: {self.min_confidence}")
        if self.max_position_size <= 0:
            raise ValueError(f"max_position_size must be positive: {self.max_position_size}")

        # Validate symbol and timeframes
        _validate_symbol(self.symbol)
        for tf in self.timeframes:
            _validate_timeframe(tf)
        _validate_timeframe(self.analysis_timeframe)


@dataclass
class OHLCV:
    """Single OHLCV bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def ask(self) -> float:
        """Simulated ask price."""
        return self.close

    @property
    def bid(self) -> float:
        """Simulated bid price."""
        return self.close


@dataclass
class SimTrade:
    """Simulated trade for backtesting."""

    id: int
    entry_price: float
    stop_loss: float
    initial_stop_loss: float
    take_profit: List[float]
    volume: float
    initial_volume: float
    action: str  # BUY or SELL
    open_time: datetime
    close_time: Optional[datetime] = None
    close_price: Optional[float] = None
    profit: float = 0.0
    status: SimTradeStatus = SimTradeStatus.OPEN

    # Trailing stop state
    trailing_active: bool = False
    trailing_stop_price: Optional[float] = None
    breakeven_price: Optional[float] = None

    # TP tracking
    tp_triggered: List[bool] = field(
        default_factory=lambda: [False, False, False]
    )
    partial_closes: List[float] = field(default_factory=list)

    # Metadata
    confidence: int = 0
    regime_type: str = ""
    wave_position: str = ""


@dataclass
class BacktestSignal:
    """Signal generated during backtesting."""

    timestamp: datetime
    action: str  # BUY, SELL, NO_TRADE
    entry_price: float
    stop_loss: float
    take_profit: List[float]  # [TP1, TP2, TP3]
    confidence: int
    regime_type: str = ""
    wave_position: str = ""
    reasoning: str = ""


class SignalGenerator(Protocol):
    """Protocol for signal generators."""

    def generate(
        self,
        market_data: Dict[str, pd.DataFrame],
        timestamp: datetime,
    ) -> BacktestSignal:
        """Generate trading signal from market data."""


class RuleBasedSignalGenerator:
    """Simple rule-based signal generator for backtesting.

    Uses technical indicators to detect potential Elliott Wave patterns:
    - Wave 2: Deep retracement (50-61.8%) with RSI oversold
    - Wave 4: Shallow retracement (38.2-50%) with momentum divergence
    """

    def __init__(self, config: BacktestConfig):
        self.config = config
        self._trade_counter = 0

    def generate(
        self,
        market_data: Dict[str, pd.DataFrame],
        timestamp: datetime,
    ) -> BacktestSignal:
        """Generate signal based on technical rules."""
        # Get M15 data up to timestamp
        df = market_data.get("M15", pd.DataFrame())
        if df.empty:
            return self._no_trade_signal(timestamp, "No M15 data")

        # Slice to current timestamp
        df_slice = df[df['timestamp'] <= timestamp].copy()
        if len(df_slice) < 50:  # Need enough history
            return self._no_trade_signal(timestamp, "Insufficient history")

        # Calculate indicators if not present
        if 'rsi' not in df_slice.columns:
            df_slice = self._calculate_indicators(df_slice)

        # Get latest values
        latest = df_slice.iloc[-1]
        prev = df_slice.iloc[-2]
        current_price = latest['close']
        atr = latest.get('atr', self._calculate_atr(df_slice))
        rsi = latest.get('rsi', 50)
        ema_20 = latest.get('ema_20', current_price)

        # Determine market regime from ADX
        adx = latest.get('adx', 20)
        regime = self._determine_regime(adx)

        # Detect signal pattern
        signal_result = self._detect_pattern(
            latest, prev, current_price, rsi, adx, ema_20, regime
        )

        if signal_result is None:
            return self._no_trade_signal(timestamp, "No pattern detected")

        signal_action, confidence, wave_position, reasoning = signal_result

        # Calculate levels using configurable multipliers
        stop_loss, tp_levels = self._calculate_levels(
            signal_action, current_price, atr
        )

        return BacktestSignal(
            timestamp=timestamp,
            action=signal_action,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=tp_levels,
            confidence=confidence,
            regime_type=regime,
            wave_position=wave_position,
            reasoning=reasoning,
        )

    def _determine_regime(self, adx: float) -> str:
        """Determine market regime from ADX."""
        if adx >= 25:
            return "trending-strong"
        if adx >= 15:
            return "trending-weak"
        return "ranging"

    def _detect_pattern(
        self,
        latest: pd.Series,
        prev: pd.Series,
        current_price: float,
        rsi: float,
        adx: float,
        ema_20: float,
        regime: str,
    ) -> Optional[tuple]:
        """Detect trading pattern and return signal details."""
        # Wave 2 entry (bullish) - RSI oversold, price near support
        if rsi < 35 and current_price > ema_20 * 0.995:
            if latest['close'] > latest['open'] and prev['close'] < prev['open']:
                return (
                    "BUY",
                    self._calculate_confidence(rsi, adx, regime, "wave_2"),
                    "Wave 2 - Bullish reversal",
                    f"RSI oversold ({rsi:.1f}), bullish engulfing",
                )

        # Wave 2 entry (bearish) - RSI overbought
        if rsi > 65 and current_price < ema_20 * 1.005:
            if latest['close'] < latest['open'] and prev['close'] > prev['open']:
                return (
                    "SELL",
                    self._calculate_confidence(100 - rsi, adx, regime, "wave_2"),
                    "Wave 2 - Bearish reversal",
                    f"RSI overbought ({rsi:.1f}), bearish engulfing",
                )

        # Wave 4 entry (trend continuation)
        if 40 <= rsi <= 60 and adx >= 20:
            # Pullback in uptrend
            if (current_price > ema_20 and
                latest['low'] < prev['low'] and
                latest['close'] > prev['close']):
                return (
                    "BUY",
                    self._calculate_confidence(50, adx, regime, "wave_4"),
                    "Wave 4 - Trend continuation",
                    f"Pullback in uptrend, ADX strong ({adx:.1f})",
                )
            # Pullback in downtrend
            if (current_price < ema_20 and
                latest['high'] > prev['high'] and
                latest['close'] < prev['close']):
                return (
                    "SELL",
                    self._calculate_confidence(50, adx, regime, "wave_4"),
                    "Wave 4 - Trend continuation",
                    f"Pullback in downtrend, ADX strong ({adx:.1f})",
                )

        return None

    def _calculate_levels(
        self,
        action: str,
        current_price: float,
        atr: float,
    ) -> tuple:
        """Calculate SL and TP levels using config multipliers."""
        sl_mult = self.config.sl_atr_multiplier
        tp_mults = self.config.tp_atr_multipliers

        if action == "BUY":
            stop_loss = current_price - (atr * sl_mult)
            tp_levels = [current_price + (atr * m) for m in tp_mults]
        else:
            stop_loss = current_price + (atr * sl_mult)
            tp_levels = [current_price - (atr * m) for m in tp_mults]

        return stop_loss, tp_levels

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators."""
        df = df.copy()

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))

        # EMA 20
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()

        # ATR
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low'] - df['close'].shift()).abs()
        ], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()

        # ADX (simplified)
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        atr_14 = df['atr'].bfill()
        plus_di = 100 * (plus_dm.ewm(span=14).mean() / atr_14)
        minus_di = 100 * (minus_dm.ewm(span=14).mean() / atr_14)
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
        df['adx'] = dx.ewm(span=14).mean()

        return df

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR for position sizing."""
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low'] - df['close'].shift()).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    def _calculate_confidence(
        self,
        rsi_factor: float,
        adx: float,
        regime: str,
        wave_type: str,
    ) -> int:
        """Calculate confidence score based on factors."""
        base = 50

        # RSI contribution
        if rsi_factor < 30:
            base += 15
        elif rsi_factor < 40:
            base += 10

        # ADX contribution
        if adx >= 30:
            base += 15
        elif adx >= 25:
            base += 10
        elif adx >= 20:
            base += 5

        # Regime bonus
        if regime == "trending-strong":
            base += 5
        elif regime == "ranging":
            base -= 10

        # Wave type bonus
        if wave_type == "wave_2":
            base += 5

        return min(max(base, 0), 100)

    def _no_trade_signal(self, timestamp: datetime, reason: str) -> BacktestSignal:
        """Create NO_TRADE signal."""
        return BacktestSignal(
            timestamp=timestamp,
            action="NO_TRADE",
            entry_price=0,
            stop_loss=0,
            take_profit=[0, 0, 0],
            confidence=0,
            reasoning=reason,
        )


class TradeSimulator:
    """Simulates trade execution and management."""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self._trade_id = 0
        # Use numpy RNG for reproducible and secure randomness
        self._rng = np.random.default_rng(seed=config.random_seed)

    def execute(
        self,
        signal: BacktestSignal,
        balance: float,
    ) -> Optional[SimTrade]:
        """Execute a simulated trade."""
        if signal.action == "NO_TRADE":
            return None

        # Calculate entry with slippage
        slippage = self._random_slippage()
        if signal.action == "BUY":
            entry_price = signal.entry_price + slippage
        else:
            entry_price = signal.entry_price - slippage

        # Calculate position size
        risk_amount = balance * (self.config.risk_percent / 100)
        sl_distance = abs(entry_price - signal.stop_loss)

        if sl_distance <= 0:
            logger.warning("Invalid SL distance, skipping trade")
            return None

        # Position size using configurable point value
        volume = risk_amount / (sl_distance * self.config.point_value)
        volume = min(volume, self.config.max_position_size)
        volume = round(volume, 2)

        if volume < 0.01:
            logger.debug("Position size too small, skipping")
            return None

        self._trade_id += 1

        return SimTrade(
            id=self._trade_id,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            initial_stop_loss=signal.stop_loss,
            take_profit=signal.take_profit.copy(),
            volume=volume,
            initial_volume=volume,
            action=signal.action,
            open_time=signal.timestamp,
            confidence=signal.confidence,
            regime_type=signal.regime_type,
            wave_position=signal.wave_position,
        )

    def update(
        self,
        trade: SimTrade,
        candle: OHLCV,
        config: BacktestConfig,
    ) -> Optional[Dict[str, Any]]:
        """Update trade state based on price action."""
        if trade.status == SimTradeStatus.CLOSED:
            return None

        # Check stop loss hit
        if self._check_sl_hit(trade, candle):
            return self._close_trade(trade, candle, trade.stop_loss, "stopped_out")

        # Check TP levels
        for i, tp in enumerate(trade.take_profit):
            if not trade.tp_triggered[i] and tp > 0:
                if self._check_tp_hit(trade, candle, tp):
                    trade.tp_triggered[i] = True

                    # Partial close percentages: 40%, 30%, 30%
                    close_pct = [0.4, 0.3, 0.3][i]
                    partial_volume = trade.initial_volume * close_pct

                    if i == 0:  # TP1 hit - activate trailing
                        trade.trailing_active = True
                        buffer = config.breakeven_buffer_pips * 0.01
                        trade.breakeven_price = (
                            trade.entry_price + buffer
                            if trade.action == "BUY"
                            else trade.entry_price - buffer
                        )
                        trade.stop_loss = trade.breakeven_price

                    trade.volume -= partial_volume
                    trade.partial_closes.append(partial_volume)

                    # Calculate partial profit
                    if trade.action == "BUY":
                        partial_profit = (tp - trade.entry_price) * partial_volume
                    else:
                        partial_profit = (trade.entry_price - tp) * partial_volume
                    partial_profit *= config.point_value
                    trade.profit += partial_profit

                    if i == 2 or trade.volume < 0.01:
                        trade.status = SimTradeStatus.CLOSED
                        trade.close_time = candle.timestamp
                        trade.close_price = tp
                        return {"reason": "all_tp_hit", "price": tp}

                    trade.status = SimTradeStatus.PARTIAL

        # Update trailing stop
        if trade.trailing_active:
            self._update_trailing_stop(trade, candle, config)

        return None

    def _check_sl_hit(self, trade: SimTrade, candle: OHLCV) -> bool:
        """Check if stop loss was hit."""
        if trade.action == "BUY":
            return candle.low <= trade.stop_loss
        return candle.high >= trade.stop_loss

    def _check_tp_hit(self, trade: SimTrade, candle: OHLCV, tp: float) -> bool:
        """Check if take profit was hit."""
        if trade.action == "BUY":
            return candle.high >= tp
        return candle.low <= tp

    def _update_trailing_stop(
        self,
        trade: SimTrade,
        candle: OHLCV,
        config: BacktestConfig,
    ) -> None:
        """Update trailing stop based on price action."""
        trail_distance = config.default_atr_for_trailing * config.trail_atr_multiplier

        if trade.action == "BUY":
            new_sl = candle.high - trail_distance
            if new_sl > trade.stop_loss:
                trade.stop_loss = new_sl
                trade.trailing_stop_price = new_sl
        else:
            new_sl = candle.low + trail_distance
            if new_sl < trade.stop_loss:
                trade.stop_loss = new_sl
                trade.trailing_stop_price = new_sl

    def close_trade(
        self,
        trade: SimTrade,
        candle: OHLCV,
        close_price: float,
        reason: str,
    ) -> Dict[str, Any]:
        """Close a trade and calculate final profit (public method)."""
        return self._close_trade(trade, candle, close_price, reason)

    def _close_trade(
        self,
        trade: SimTrade,
        candle: OHLCV,
        close_price: float,
        reason: str,
    ) -> Dict[str, Any]:
        """Close a trade and calculate final profit."""
        if trade.action == "BUY":
            remaining_profit = (close_price - trade.entry_price) * trade.volume
        else:
            remaining_profit = (trade.entry_price - close_price) * trade.volume
        remaining_profit *= self.config.point_value

        trade.profit += remaining_profit
        trade.status = SimTradeStatus.CLOSED
        trade.close_time = candle.timestamp
        trade.close_price = close_price

        return {"reason": reason, "price": close_price}

    def _random_slippage(self) -> float:
        """Generate random slippage using numpy RNG."""
        max_slip = self.config.slippage_pips * 0.01
        return float(self._rng.uniform(-max_slip * 0.5, max_slip))


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    config: BacktestConfig
    trades: List[SimTrade]
    equity_curve: List[Dict[str, Any]]
    start_date: datetime
    end_date: datetime

    @property
    def total_trades(self) -> int:
        """Total number of trades."""
        return len(self.trades)

    @property
    def winning_trades(self) -> int:
        """Number of winning trades."""
        return sum(1 for t in self.trades if t.profit > 0)

    @property
    def losing_trades(self) -> int:
        """Number of losing trades."""
        return sum(1 for t in self.trades if t.profit < 0)

    @property
    def win_rate(self) -> float:
        """Win rate percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    @property
    def total_profit(self) -> float:
        """Total profit/loss."""
        return sum(t.profit for t in self.trades)

    @property
    def gross_profit(self) -> float:
        """Total of all winning trades."""
        return sum(t.profit for t in self.trades if t.profit > 0)

    @property
    def gross_loss(self) -> float:
        """Total of all losing trades (absolute value)."""
        return abs(sum(t.profit for t in self.trades if t.profit < 0))

    @property
    def profit_factor(self) -> float:
        """Ratio of gross profit to gross loss."""
        if self.gross_loss == 0:
            return float('inf') if self.gross_profit > 0 else 0.0
        return self.gross_profit / self.gross_loss

    @property
    def average_win(self) -> float:
        """Average profit of winning trades."""
        wins = [t.profit for t in self.trades if t.profit > 0]
        return float(np.mean(wins)) if wins else 0.0

    @property
    def average_loss(self) -> float:
        """Average loss of losing trades."""
        losses = [abs(t.profit) for t in self.trades if t.profit < 0]
        return float(np.mean(losses)) if losses else 0.0

    @property
    def max_drawdown(self) -> float:
        """Calculate maximum drawdown from equity curve."""
        if not self.equity_curve:
            return 0.0

        equities = [e['equity'] for e in self.equity_curve]
        peak = equities[0]
        max_dd = 0.0

        for equity in equities:
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

        return max_dd

    @property
    def sharpe_ratio(self) -> float:
        """Calculate Sharpe ratio (assuming 0 risk-free rate)."""
        if not self.trades:
            return 0.0

        returns = [t.profit / self.config.initial_balance for t in self.trades]
        if len(returns) < 2 or np.std(returns) == 0:
            return 0.0

        daily_factor = np.sqrt(252 / max(len(returns), 1))
        return float((np.mean(returns) / np.std(returns)) * daily_factor)

    def generate_report(self) -> str:
        """Generate markdown report."""
        lines = [
            "# Backtest Report",
            "",
            "## Configuration",
            f"- Symbol: {self.config.symbol}",
            f"- Period: {self.start_date.strftime('%Y-%m-%d')} to "
            f"{self.end_date.strftime('%Y-%m-%d')}",
            f"- Initial Balance: ${self.config.initial_balance:,.2f}",
            f"- Risk per Trade: {self.config.risk_percent}%",
            f"- Min Confidence: {self.config.min_confidence}%",
            "",
            "## Performance Summary",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Trades | {self.total_trades} |",
            f"| Winning Trades | {self.winning_trades} |",
            f"| Losing Trades | {self.losing_trades} |",
            f"| Win Rate | {self.win_rate:.1f}% |",
            f"| Total Profit | ${self.total_profit:,.2f} |",
            f"| Profit Factor | {self.profit_factor:.2f} |",
            f"| Max Drawdown | {self.max_drawdown:.1f}% |",
            f"| Sharpe Ratio | {self.sharpe_ratio:.2f} |",
            "",
            "## Trade Statistics",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Average Win | ${self.average_win:,.2f} |",
            f"| Average Loss | ${self.average_loss:,.2f} |",
            f"| Gross Profit | ${self.gross_profit:,.2f} |",
            f"| Gross Loss | ${self.gross_loss:,.2f} |",
            "",
            "## Final Balance",
            f"${self.config.initial_balance + self.total_profit:,.2f}",
        ]

        # Add regime breakdown if available
        regime_stats = self._calculate_regime_stats()
        if regime_stats:
            lines.extend([
                "",
                "## Performance by Regime",
                "| Regime | Trades | Win Rate | Profit |",
                "|--------|--------|----------|--------|",
            ])
            for regime, stats in regime_stats.items():
                lines.append(
                    f"| {regime} | {stats['trades']} | "
                    f"{stats['win_rate']:.1f}% | ${stats['profit']:,.2f} |"
                )

        return "\n".join(lines)

    def _calculate_regime_stats(self) -> Dict[str, Dict[str, Any]]:
        """Calculate performance by regime."""
        regime_trades: Dict[str, List[SimTrade]] = {}

        for trade in self.trades:
            regime = trade.regime_type or "unknown"
            if regime not in regime_trades:
                regime_trades[regime] = []
            regime_trades[regime].append(trade)

        stats = {}
        for regime, trades in regime_trades.items():
            wins = sum(1 for t in trades if t.profit > 0)
            stats[regime] = {
                "trades": len(trades),
                "win_rate": (wins / len(trades) * 100) if trades else 0,
                "profit": sum(t.profit for t in trades),
            }

        return stats


class BacktestEngine:
    """Core backtesting engine."""

    def __init__(
        self,
        config: BacktestConfig,
        signal_generator: Optional[SignalGenerator] = None,
    ):
        self.config = config
        self.generator = signal_generator or RuleBasedSignalGenerator(config)
        self.simulator = TradeSimulator(config)
        self.trades: List[SimTrade] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.balance = config.initial_balance
        self.open_trades: List[SimTrade] = []
        self._data: Dict[str, pd.DataFrame] = {}

    def load_data(self, data_path: Optional[Path] = None) -> bool:
        """Load historical data from CSV files with validation."""
        path = data_path or self.config.data_path
        path = path.resolve()

        for tf in self.config.timeframes:
            file_path = path / f"{self.config.symbol}_{tf}.csv"

            # Security: Validate path
            _validate_path_within_directory(file_path, path)

            if not file_path.exists():
                logger.warning("Data file not found: %s", file_path)
                continue

            # Security: Check file size
            if file_path.stat().st_size > MAX_CSV_FILE_SIZE:
                logger.error("File too large (>100MB): %s", file_path)
                continue

            # Load with row limit
            df = pd.read_csv(file_path, nrows=MAX_CSV_ROWS)

            # Validate required columns
            required_cols = {'open', 'high', 'low', 'close'}
            if not required_cols.issubset(df.columns):
                logger.error("Missing required columns in %s", file_path)
                continue

            # Ensure timestamp column
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            elif 'time' in df.columns:
                df['timestamp'] = pd.to_datetime(df['time'])
            else:
                logger.warning("No timestamp column in %s", file_path)
                continue

            # Data quality checks
            df = self._validate_and_clean_data(df, file_path)
            if df is None or df.empty:
                continue

            # Sort by timestamp
            df = df.sort_values('timestamp').reset_index(drop=True)

            # Pre-calculate indicators for performance
            df = self._precalculate_indicators(df)

            self._data[tf] = df
            logger.info("Loaded %d bars for %s", len(df), tf)

        return len(self._data) > 0

    def _validate_and_clean_data(
        self,
        df: pd.DataFrame,
        file_path: Path,
    ) -> Optional[pd.DataFrame]:
        """Validate and clean OHLCV data."""
        # Validate numeric data types
        numeric_cols = ['open', 'high', 'low', 'close']
        for col in numeric_cols:
            if not pd.api.types.is_numeric_dtype(df[col]):
                logger.error("Non-numeric %s column in %s", col, file_path)
                return None

        # Check for NaN
        if df[numeric_cols].isnull().any().any():
            nan_count = df[numeric_cols].isnull().sum().sum()
            logger.warning("Dropping %d rows with NaN in %s", nan_count, file_path)
            df = df.dropna(subset=numeric_cols)

        # Check for duplicates
        if df['timestamp'].duplicated().any():
            dup_count = df['timestamp'].duplicated().sum()
            logger.warning(
                "Dropping %d duplicate timestamps in %s", dup_count, file_path
            )
            df = df.drop_duplicates(subset=['timestamp'], keep='first')

        # Validate OHLC relationship
        invalid_bars = (
            (df['high'] < df['low']) |
            (df['high'] < df['open']) |
            (df['high'] < df['close']) |
            (df['low'] > df['open']) |
            (df['low'] > df['close'])
        )
        if invalid_bars.any():
            invalid_count = invalid_bars.sum()
            logger.warning(
                "Dropping %d invalid OHLC bars in %s", invalid_count, file_path
            )
            df = df[~invalid_bars]

        return df

    def _precalculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Pre-calculate indicators once for performance."""
        df = df.copy()

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))

        # EMA 20
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()

        # ATR
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low'] - df['close'].shift()).abs()
        ], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()

        # ADX
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        atr_14 = df['atr'].bfill()
        plus_di = 100 * (plus_dm.ewm(span=14).mean() / atr_14)
        minus_di = 100 * (minus_dm.ewm(span=14).mean() / atr_14)
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
        df['adx'] = dx.ewm(span=14).mean()

        return df

    def run(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> BacktestResult:
        """Run backtest simulation."""
        if not self._data:
            raise ValueError("No data loaded. Call load_data() first.")

        analysis_tf = self.config.analysis_timeframe
        if analysis_tf not in self._data:
            raise ValueError(
                f"Analysis timeframe {analysis_tf} not in loaded data"
            )

        df = self._data[analysis_tf]

        # Filter by date range
        if start_date:
            df = df[df['timestamp'] >= start_date]
        if end_date:
            df = df[df['timestamp'] <= end_date]

        if df.empty:
            raise ValueError("No data in specified date range")

        actual_start = df['timestamp'].iloc[0]
        actual_end = df['timestamp'].iloc[-1]

        logger.info("Running backtest from %s to %s", actual_start, actual_end)
        logger.info("Total bars: %d", len(df))

        # Initialize
        self.equity_curve = [{"timestamp": actual_start, "equity": self.balance}]
        self.trades = []
        self.open_trades = []

        # Build timestamp index for efficient slicing
        tf_indices = {tf: 0 for tf in self._data.keys()}

        bar_count = 0
        for idx in range(50, len(df), self.config.analysis_interval_bars):
            row = df.iloc[idx]
            timestamp = row['timestamp']

            candle = OHLCV(
                timestamp=timestamp,
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row.get('volume', 0),
            )

            # Update open trades
            self._update_open_trades(candle)

            # Generate new signal if no open trades
            if not self.open_trades:
                # Efficient data slicing using index tracking
                market_data = self._slice_market_data(timestamp, tf_indices)
                signal = self.generator.generate(market_data, timestamp)

                if (signal.action != "NO_TRADE" and
                    signal.confidence >= self.config.min_confidence):
                    trade = self.simulator.execute(signal, self.balance)
                    if trade:
                        self.open_trades.append(trade)
                        logger.debug(
                            "Opened trade: %s at %s",
                            trade.action,
                            trade.entry_price,
                        )

            # Track equity
            unrealized = sum(
                self._calculate_unrealized_pnl(t, candle)
                for t in self.open_trades
            )
            self.equity_curve.append({
                "timestamp": timestamp,
                "equity": self.balance + unrealized,
            })

            bar_count += 1
            if bar_count % 1000 == 0:
                logger.info("Processed %d bars...", bar_count)

        # Close remaining open trades
        self._close_remaining_trades(df)

        logger.info("Backtest complete. %d trades executed.", len(self.trades))

        return BacktestResult(
            config=self.config,
            trades=self.trades,
            equity_curve=self.equity_curve,
            start_date=actual_start,
            end_date=actual_end,
        )

    def _update_open_trades(self, candle: OHLCV) -> None:
        """Update all open trades and move closed ones to trades list."""
        closed_trades = []
        for trade in self.open_trades:
            result = self.simulator.update(trade, candle, self.config)
            if result:
                self.balance += trade.profit
                closed_trades.append(trade)

        for trade in closed_trades:
            self.open_trades.remove(trade)
            self.trades.append(trade)

    def _slice_market_data(
        self,
        timestamp: datetime,
        tf_indices: Dict[str, int],
    ) -> Dict[str, pd.DataFrame]:
        """Efficiently slice market data up to timestamp."""
        market_data = {}
        for tf, tf_df in self._data.items():
            # Advance index to current timestamp
            while (tf_indices[tf] < len(tf_df) and
                   tf_df.iloc[tf_indices[tf]]['timestamp'] <= timestamp):
                tf_indices[tf] += 1
            market_data[tf] = tf_df.iloc[:tf_indices[tf]]
        return market_data

    def _close_remaining_trades(self, df: pd.DataFrame) -> None:
        """Close any remaining open trades at last price."""
        if not self.open_trades:
            return

        last_row = df.iloc[-1]
        last_candle = OHLCV(
            timestamp=last_row['timestamp'],
            open=last_row['open'],
            high=last_row['high'],
            low=last_row['low'],
            close=last_row['close'],
            volume=last_row.get('volume', 0),
        )

        for trade in self.open_trades:
            self.simulator.close_trade(
                trade, last_candle, last_row['close'], "end_of_test"
            )
            self.balance += trade.profit
            self.trades.append(trade)

        self.open_trades = []

    def _calculate_unrealized_pnl(self, trade: SimTrade, candle: OHLCV) -> float:
        """Calculate unrealized P&L for open trade."""
        if trade.action == "BUY":
            pnl = (candle.close - trade.entry_price) * trade.volume
        else:
            pnl = (trade.entry_price - candle.close) * trade.volume
        return pnl * self.config.point_value


def export_historical_data(
    symbol: str = "XAUUSD",
    timeframes: Optional[List[str]] = None,
    bars: int = 10000,
    output_path: Optional[Path] = None,
) -> Dict[str, Path]:
    """Export historical data from MT5 to CSV files.

    Args:
        symbol: Trading symbol (validated for security)
        timeframes: List of timeframes to export
        bars: Number of bars per timeframe (max 100000)
        output_path: Output directory

    Returns:
        Dict mapping timeframe to output file path

    Raises:
        ValueError: If inputs fail validation
        RuntimeError: If MT5 initialization fails
    """
    # pylint: disable=import-outside-toplevel
    from src.mt5_client import MT5Client

    # Security validations
    _validate_symbol(symbol)

    if bars > MAX_BARS_EXPORT:
        raise ValueError(f"bars exceeds max ({MAX_BARS_EXPORT}): {bars}")
    if bars <= 0:
        raise ValueError(f"bars must be positive: {bars}")

    if timeframes is None:
        timeframes = ["H4", "H1", "M30", "M15"]

    for tf in timeframes:
        _validate_timeframe(tf)

    if output_path is None:
        output_path = Path("data/backtest")

    output_path = output_path.resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    client = MT5Client()
    if not client.initialize():
        raise RuntimeError("Failed to initialize MT5")

    try:
        exported = {}
        for tf in timeframes:
            df = client.fetch_ohlcv(symbol=symbol, timeframe=tf, bars=bars)
            if df is not None and not df.empty:
                file_path = output_path / f"{symbol}_{tf}.csv"
                _validate_path_within_directory(file_path, output_path)
                df.to_csv(file_path, index=False)
                exported[tf] = file_path
                logger.info("Exported %d bars to %s", len(df), file_path)
            else:
                logger.warning("No data for %s", tf)

        return exported
    finally:
        client.shutdown()
