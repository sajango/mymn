"""Unit tests for backtest engine module.

Tests coverage:
1. BacktestConfig - configuration validation
2. RuleBasedSignalGenerator - signal generation logic
3. TradeSimulator - trade execution and management
4. BacktestEngine - core engine functionality
5. BacktestResult - metrics calculation
"""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import pandas as pd
import numpy as np

from src.backtest_engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    BacktestSignal,
    OHLCV,
    RuleBasedSignalGenerator,
    SimTrade,
    SimTradeStatus,
    TradeSimulator,
)


class TestBacktestConfig:
    """Test BacktestConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BacktestConfig()

        assert config.symbol == "XAUUSD"
        assert config.min_confidence == 50
        assert config.initial_balance == 10000.0
        assert config.risk_percent == 1.5
        assert config.slippage_pips == 1.0
        assert config.analysis_timeframe == "M15"
        assert "H4" in config.timeframes
        assert "M15" in config.timeframes

    def test_custom_config(self):
        """Test custom configuration values."""
        config = BacktestConfig(
            symbol="EURUSD",
            min_confidence=70,
            initial_balance=50000.0,
            risk_percent=2.0,
        )

        assert config.symbol == "EURUSD"
        assert config.min_confidence == 70
        assert config.initial_balance == 50000.0
        assert config.risk_percent == 2.0


class TestOHLCV:
    """Test OHLCV dataclass."""

    def test_ohlcv_creation(self):
        """Test OHLCV bar creation."""
        timestamp = datetime(2024, 1, 15, 10, 0, 0)
        bar = OHLCV(
            timestamp=timestamp,
            open=2050.5,
            high=2055.0,
            low=2048.0,
            close=2052.0,
            volume=1000,
        )

        assert bar.timestamp == timestamp
        assert bar.open == 2050.5
        assert bar.high == 2055.0
        assert bar.low == 2048.0
        assert bar.close == 2052.0
        assert bar.volume == 1000

    def test_ohlcv_ask_bid(self):
        """Test ask/bid properties."""
        bar = OHLCV(
            timestamp=datetime.now(),
            open=2050.0,
            high=2055.0,
            low=2048.0,
            close=2052.0,
            volume=100,
        )

        # Ask and bid default to close price
        assert bar.ask == 2052.0
        assert bar.bid == 2052.0


class TestBacktestSignal:
    """Test BacktestSignal dataclass."""

    def test_signal_creation(self):
        """Test signal creation with all fields."""
        signal = BacktestSignal(
            timestamp=datetime.now(),
            action="BUY",
            entry_price=2050.0,
            stop_loss=2040.0,
            take_profit=[2060.0, 2070.0, 2085.0],
            confidence=75,
            regime_type="trending-strong",
            wave_position="Wave 2",
            reasoning="Test signal",
        )

        assert signal.action == "BUY"
        assert signal.confidence == 75
        assert len(signal.take_profit) == 3
        assert signal.regime_type == "trending-strong"


class TestRuleBasedSignalGenerator:
    """Test RuleBasedSignalGenerator class."""

    @pytest.fixture
    def generator(self):
        """Create generator instance."""
        config = BacktestConfig()
        return RuleBasedSignalGenerator(config)

    @pytest.fixture
    def sample_market_data(self):
        """Create sample market data for testing."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='15min')
        data = {
            'timestamp': dates,
            'open': np.random.uniform(2040, 2060, 100),
            'high': np.random.uniform(2055, 2070, 100),
            'low': np.random.uniform(2030, 2045, 100),
            'close': np.random.uniform(2045, 2055, 100),
            'volume': np.random.randint(100, 1000, 100),
        }
        df = pd.DataFrame(data)
        df['high'] = df[['open', 'close']].max(axis=1) + np.random.uniform(1, 5, 100)
        df['low'] = df[['open', 'close']].min(axis=1) - np.random.uniform(1, 5, 100)
        return {'M15': df}

    def test_generate_no_trade_insufficient_data(self, generator):
        """Test NO_TRADE signal with insufficient data."""
        timestamp = datetime(2024, 1, 1, 10, 0, 0)
        market_data = {'M15': pd.DataFrame()}

        signal = generator.generate(market_data, timestamp)

        assert signal.action == "NO_TRADE"
        assert signal.confidence == 0

    def test_generate_signal_with_data(self, generator, sample_market_data):
        """Test signal generation with sufficient data."""
        timestamp = sample_market_data['M15']['timestamp'].iloc[-1]

        signal = generator.generate(sample_market_data, timestamp)

        # Signal should be generated (action could be BUY, SELL, or NO_TRADE)
        assert signal.action in ["BUY", "SELL", "NO_TRADE"]
        assert isinstance(signal.confidence, int)
        assert 0 <= signal.confidence <= 100

    def test_calculate_indicators(self, generator):
        """Test indicator calculation."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='15min')
        df = pd.DataFrame({
            'timestamp': dates,
            'open': np.linspace(2040, 2060, 50),
            'high': np.linspace(2045, 2065, 50),
            'low': np.linspace(2035, 2055, 50),
            'close': np.linspace(2042, 2062, 50),
        })

        result = generator._calculate_indicators(df)

        assert 'rsi' in result.columns
        assert 'ema_20' in result.columns
        assert 'atr' in result.columns
        assert 'adx' in result.columns

    def test_no_trade_signal(self, generator):
        """Test no trade signal creation."""
        timestamp = datetime.now()
        signal = generator._no_trade_signal(timestamp, "Test reason")

        assert signal.action == "NO_TRADE"
        assert signal.confidence == 0
        assert signal.entry_price == 0
        assert signal.reasoning == "Test reason"


class TestTradeSimulator:
    """Test TradeSimulator class."""

    @pytest.fixture
    def simulator(self):
        """Create simulator instance."""
        config = BacktestConfig()
        return TradeSimulator(config)

    @pytest.fixture
    def sample_buy_signal(self):
        """Create sample BUY signal."""
        return BacktestSignal(
            timestamp=datetime.now(),
            action="BUY",
            entry_price=2050.0,
            stop_loss=2040.0,
            take_profit=[2060.0, 2070.0, 2085.0],
            confidence=75,
            regime_type="trending-strong",
        )

    @pytest.fixture
    def sample_sell_signal(self):
        """Create sample SELL signal."""
        return BacktestSignal(
            timestamp=datetime.now(),
            action="SELL",
            entry_price=2050.0,
            stop_loss=2060.0,
            take_profit=[2040.0, 2030.0, 2015.0],
            confidence=75,
            regime_type="trending-strong",
        )

    def test_execute_buy_trade(self, simulator, sample_buy_signal):
        """Test executing a BUY trade."""
        candle = OHLCV(
            timestamp=datetime.now(),
            open=2050.0,
            high=2052.0,
            low=2048.0,
            close=2051.0,
            volume=100,
        )
        balance = 10000.0

        trade = simulator.execute(sample_buy_signal, balance)

        assert trade is not None
        assert trade.action == "BUY"
        assert trade.volume > 0
        assert trade.stop_loss == 2040.0
        assert len(trade.take_profit) == 3
        assert trade.status == SimTradeStatus.OPEN

    def test_execute_sell_trade(self, simulator, sample_sell_signal):
        """Test executing a SELL trade."""
        candle = OHLCV(
            timestamp=datetime.now(),
            open=2050.0,
            high=2052.0,
            low=2048.0,
            close=2049.0,
            volume=100,
        )
        balance = 10000.0

        trade = simulator.execute(sample_sell_signal, balance)

        assert trade is not None
        assert trade.action == "SELL"
        assert trade.volume > 0
        assert trade.stop_loss == 2060.0

    def test_execute_no_trade_signal(self, simulator):
        """Test executing NO_TRADE signal returns None."""
        signal = BacktestSignal(
            timestamp=datetime.now(),
            action="NO_TRADE",
            entry_price=0,
            stop_loss=0,
            take_profit=[0, 0, 0],
            confidence=0,
        )
        candle = OHLCV(
            timestamp=datetime.now(),
            open=2050.0,
            high=2052.0,
            low=2048.0,
            close=2051.0,
            volume=100,
        )

        trade = simulator.execute(signal, 10000.0)

        assert trade is None

    def test_update_trade_sl_hit_buy(self, simulator, sample_buy_signal):
        """Test stop loss hit for BUY trade."""
        config = BacktestConfig()
        candle = OHLCV(
            timestamp=datetime.now(),
            open=2050.0,
            high=2052.0,
            low=2048.0,
            close=2051.0,
            volume=100,
        )
        trade = simulator.execute(sample_buy_signal, 10000.0)

        # Price drops to SL
        sl_candle = OHLCV(
            timestamp=datetime.now(),
            open=2042.0,
            high=2043.0,
            low=2038.0,  # Below SL of 2040
            close=2039.0,
            volume=100,
        )

        result = simulator.update(trade, sl_candle, config)

        assert result is not None
        assert result['reason'] == 'stopped_out'
        assert trade.status == SimTradeStatus.CLOSED

    def test_update_trade_tp1_hit_buy(self, simulator, sample_buy_signal):
        """Test TP1 hit for BUY trade."""
        config = BacktestConfig()
        candle = OHLCV(
            timestamp=datetime.now(),
            open=2050.0,
            high=2052.0,
            low=2048.0,
            close=2051.0,
            volume=100,
        )
        trade = simulator.execute(sample_buy_signal, 10000.0)
        initial_volume = trade.volume

        # Price rises to TP1
        tp_candle = OHLCV(
            timestamp=datetime.now(),
            open=2058.0,
            high=2062.0,  # Above TP1 of 2060
            low=2057.0,
            close=2061.0,
            volume=100,
        )

        result = simulator.update(trade, tp_candle, config)

        assert trade.tp_triggered[0] is True
        assert trade.trailing_active is True
        assert trade.volume < initial_volume  # Partial close

    def test_check_sl_hit_buy(self, simulator):
        """Test SL hit detection for BUY."""
        trade = SimTrade(
            id=1,
            entry_price=2050.0,
            stop_loss=2040.0,
            initial_stop_loss=2040.0,
            take_profit=[2060.0, 2070.0, 2085.0],
            volume=0.1,
            initial_volume=0.1,
            action="BUY",
            open_time=datetime.now(),
        )

        hit_candle = OHLCV(
            timestamp=datetime.now(),
            open=2042.0,
            high=2043.0,
            low=2039.0,  # Below SL
            close=2041.0,
            volume=100,
        )

        assert simulator._check_sl_hit(trade, hit_candle) is True

        no_hit_candle = OHLCV(
            timestamp=datetime.now(),
            open=2050.0,
            high=2052.0,
            low=2041.0,  # Above SL
            close=2051.0,
            volume=100,
        )

        assert simulator._check_sl_hit(trade, no_hit_candle) is False

    def test_check_tp_hit_buy(self, simulator):
        """Test TP hit detection for BUY."""
        trade = SimTrade(
            id=1,
            entry_price=2050.0,
            stop_loss=2040.0,
            initial_stop_loss=2040.0,
            take_profit=[2060.0, 2070.0, 2085.0],
            volume=0.1,
            initial_volume=0.1,
            action="BUY",
            open_time=datetime.now(),
        )

        hit_candle = OHLCV(
            timestamp=datetime.now(),
            open=2058.0,
            high=2062.0,  # Above TP1
            low=2057.0,
            close=2060.0,
            volume=100,
        )

        assert simulator._check_tp_hit(trade, hit_candle, 2060.0) is True

        no_hit_candle = OHLCV(
            timestamp=datetime.now(),
            open=2055.0,
            high=2058.0,  # Below TP1
            low=2054.0,
            close=2057.0,
            volume=100,
        )

        assert simulator._check_tp_hit(trade, no_hit_candle, 2060.0) is False


class TestBacktestResult:
    """Test BacktestResult class."""

    @pytest.fixture
    def sample_trades(self):
        """Create sample trades for testing."""
        return [
            SimTrade(
                id=1, entry_price=2050.0, stop_loss=2040.0, initial_stop_loss=2040.0,
                take_profit=[2060.0], volume=0.1, initial_volume=0.1,
                action="BUY", open_time=datetime.now(), profit=150.0,
                status=SimTradeStatus.CLOSED, regime_type="trending-strong",
            ),
            SimTrade(
                id=2, entry_price=2055.0, stop_loss=2045.0, initial_stop_loss=2045.0,
                take_profit=[2065.0], volume=0.1, initial_volume=0.1,
                action="BUY", open_time=datetime.now(), profit=-100.0,
                status=SimTradeStatus.CLOSED, regime_type="trending-strong",
            ),
            SimTrade(
                id=3, entry_price=2060.0, stop_loss=2070.0, initial_stop_loss=2070.0,
                take_profit=[2050.0], volume=0.1, initial_volume=0.1,
                action="SELL", open_time=datetime.now(), profit=200.0,
                status=SimTradeStatus.CLOSED, regime_type="ranging",
            ),
        ]

    @pytest.fixture
    def sample_equity_curve(self):
        """Create sample equity curve."""
        start = datetime(2024, 1, 1)
        return [
            {"timestamp": start, "equity": 10000.0},
            {"timestamp": start + timedelta(hours=1), "equity": 10150.0},
            {"timestamp": start + timedelta(hours=2), "equity": 10050.0},
            {"timestamp": start + timedelta(hours=3), "equity": 10250.0},
        ]

    def test_total_trades(self, sample_trades, sample_equity_curve):
        """Test total trades calculation."""
        config = BacktestConfig()
        result = BacktestResult(
            config=config,
            trades=sample_trades,
            equity_curve=sample_equity_curve,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
        )

        assert result.total_trades == 3

    def test_winning_losing_trades(self, sample_trades, sample_equity_curve):
        """Test winning/losing trades count."""
        config = BacktestConfig()
        result = BacktestResult(
            config=config,
            trades=sample_trades,
            equity_curve=sample_equity_curve,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
        )

        assert result.winning_trades == 2
        assert result.losing_trades == 1

    def test_win_rate(self, sample_trades, sample_equity_curve):
        """Test win rate calculation."""
        config = BacktestConfig()
        result = BacktestResult(
            config=config,
            trades=sample_trades,
            equity_curve=sample_equity_curve,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
        )

        # 2 wins out of 3 = 66.67%
        assert abs(result.win_rate - 66.67) < 0.1

    def test_total_profit(self, sample_trades, sample_equity_curve):
        """Test total profit calculation."""
        config = BacktestConfig()
        result = BacktestResult(
            config=config,
            trades=sample_trades,
            equity_curve=sample_equity_curve,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
        )

        # 150 - 100 + 200 = 250
        assert result.total_profit == 250.0

    def test_profit_factor(self, sample_trades, sample_equity_curve):
        """Test profit factor calculation."""
        config = BacktestConfig()
        result = BacktestResult(
            config=config,
            trades=sample_trades,
            equity_curve=sample_equity_curve,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
        )

        # Gross profit = 350, gross loss = 100
        # Profit factor = 350 / 100 = 3.5
        assert result.profit_factor == 3.5

    def test_max_drawdown(self, sample_equity_curve):
        """Test max drawdown calculation."""
        config = BacktestConfig()
        # Modify equity curve to have clear drawdown
        equity_curve = [
            {"timestamp": datetime(2024, 1, 1), "equity": 10000.0},
            {"timestamp": datetime(2024, 1, 1, 1), "equity": 10500.0},  # Peak
            {"timestamp": datetime(2024, 1, 1, 2), "equity": 9800.0},   # Drawdown
            {"timestamp": datetime(2024, 1, 1, 3), "equity": 10200.0},
        ]

        result = BacktestResult(
            config=config,
            trades=[],
            equity_curve=equity_curve,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
        )

        # Drawdown from 10500 to 9800 = 6.67%
        assert abs(result.max_drawdown - 6.67) < 0.1

    def test_generate_report(self, sample_trades, sample_equity_curve):
        """Test report generation."""
        config = BacktestConfig()
        result = BacktestResult(
            config=config,
            trades=sample_trades,
            equity_curve=sample_equity_curve,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
        )

        report = result.generate_report()

        assert "# Backtest Report" in report
        assert "Total Trades" in report
        assert "Win Rate" in report
        assert "Profit Factor" in report
        assert "XAUUSD" in report

    def test_regime_stats(self, sample_trades, sample_equity_curve):
        """Test regime statistics calculation."""
        config = BacktestConfig()
        result = BacktestResult(
            config=config,
            trades=sample_trades,
            equity_curve=sample_equity_curve,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
        )

        stats = result._calculate_regime_stats()

        assert "trending-strong" in stats
        assert "ranging" in stats
        assert stats["trending-strong"]["trades"] == 2
        assert stats["ranging"]["trades"] == 1


class TestBacktestEngine:
    """Test BacktestEngine class."""

    @pytest.fixture
    def sample_data_dir(self):
        """Create temporary directory with sample data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = Path(tmpdir)

            # Create sample M15 data
            dates = pd.date_range(start='2024-01-01', periods=200, freq='15min')
            df = pd.DataFrame({
                'timestamp': dates,
                'open': np.linspace(2040, 2060, 200) + np.random.uniform(-2, 2, 200),
                'high': np.linspace(2045, 2065, 200) + np.random.uniform(0, 5, 200),
                'low': np.linspace(2035, 2055, 200) - np.random.uniform(0, 5, 200),
                'close': np.linspace(2042, 2062, 200) + np.random.uniform(-2, 2, 200),
                'volume': np.random.randint(100, 1000, 200),
            })
            df.to_csv(data_path / 'XAUUSD_M15.csv', index=False)

            yield data_path

    def test_engine_initialization(self):
        """Test engine initialization."""
        config = BacktestConfig()
        engine = BacktestEngine(config)

        assert engine.config == config
        assert isinstance(engine.generator, RuleBasedSignalGenerator)
        assert isinstance(engine.simulator, TradeSimulator)
        assert engine.balance == config.initial_balance

    def test_load_data_success(self, sample_data_dir):
        """Test successful data loading."""
        config = BacktestConfig(
            data_path=sample_data_dir,
            timeframes=["M15"],
        )
        engine = BacktestEngine(config)

        result = engine.load_data()

        assert result is True
        assert "M15" in engine._data
        assert len(engine._data["M15"]) == 200

    def test_load_data_missing_file(self):
        """Test data loading with missing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = BacktestConfig(
                data_path=Path(tmpdir),
                timeframes=["M15"],
            )
            engine = BacktestEngine(config)

            result = engine.load_data()

            assert result is False

    def test_run_backtest(self, sample_data_dir):
        """Test running backtest."""
        config = BacktestConfig(
            data_path=sample_data_dir,
            timeframes=["M15"],
            min_confidence=30,  # Lower threshold for more trades
        )
        engine = BacktestEngine(config)
        engine.load_data()

        result = engine.run()

        assert isinstance(result, BacktestResult)
        assert result.start_date is not None
        assert result.end_date is not None
        assert len(result.equity_curve) > 0

    def test_run_without_data(self):
        """Test running backtest without loading data."""
        config = BacktestConfig()
        engine = BacktestEngine(config)

        with pytest.raises(ValueError, match="No data loaded"):
            engine.run()

    def test_calculate_unrealized_pnl_buy(self):
        """Test unrealized P&L calculation for BUY."""
        config = BacktestConfig()
        engine = BacktestEngine(config)

        trade = SimTrade(
            id=1, entry_price=2050.0, stop_loss=2040.0, initial_stop_loss=2040.0,
            take_profit=[2060.0], volume=0.1, initial_volume=0.1,
            action="BUY", open_time=datetime.now(),
        )

        candle = OHLCV(
            timestamp=datetime.now(),
            open=2055.0,
            high=2058.0,
            low=2053.0,
            close=2055.0,  # +5 from entry
            volume=100,
        )

        pnl = engine._calculate_unrealized_pnl(trade, candle)

        # (2055 - 2050) * 0.1 * 100 = 50
        assert abs(pnl - 50.0) < 0.01

    def test_calculate_unrealized_pnl_sell(self):
        """Test unrealized P&L calculation for SELL."""
        config = BacktestConfig()
        engine = BacktestEngine(config)

        trade = SimTrade(
            id=1, entry_price=2050.0, stop_loss=2060.0, initial_stop_loss=2060.0,
            take_profit=[2040.0], volume=0.1, initial_volume=0.1,
            action="SELL", open_time=datetime.now(),
        )

        candle = OHLCV(
            timestamp=datetime.now(),
            open=2045.0,
            high=2048.0,
            low=2043.0,
            close=2045.0,  # -5 from entry (profit for sell)
            volume=100,
        )

        pnl = engine._calculate_unrealized_pnl(trade, candle)

        # (2050 - 2045) * 0.1 * 100 = 50
        assert abs(pnl - 50.0) < 0.01


class TestSimTrade:
    """Test SimTrade dataclass."""

    def test_sim_trade_defaults(self):
        """Test SimTrade default values."""
        trade = SimTrade(
            id=1,
            entry_price=2050.0,
            stop_loss=2040.0,
            initial_stop_loss=2040.0,
            take_profit=[2060.0, 2070.0, 2085.0],
            volume=0.1,
            initial_volume=0.1,
            action="BUY",
            open_time=datetime.now(),
        )

        assert trade.status == SimTradeStatus.OPEN
        assert trade.trailing_active is False
        assert trade.tp_triggered == [False, False, False]
        assert trade.profit == 0.0
        assert trade.close_time is None


class TestIntegration:
    """Integration tests for full backtest workflow."""

    def test_full_backtest_workflow(self):
        """Test complete backtest workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = Path(tmpdir)

            # Create trending data that should generate signals
            dates = pd.date_range(start='2024-01-01', periods=300, freq='15min')

            # Create uptrend with pullbacks
            base_prices = np.linspace(2000, 2100, 300)
            noise = np.random.uniform(-5, 5, 300)

            # Add RSI-favorable conditions
            df = pd.DataFrame({
                'timestamp': dates,
                'open': base_prices + noise,
                'close': base_prices + noise + np.random.uniform(-2, 2, 300),
            })
            df['high'] = df[['open', 'close']].max(axis=1) + np.random.uniform(1, 5, 300)
            df['low'] = df[['open', 'close']].min(axis=1) - np.random.uniform(1, 5, 300)
            df['volume'] = np.random.randint(100, 1000, 300)

            df.to_csv(data_path / 'XAUUSD_M15.csv', index=False)

            # Run backtest
            config = BacktestConfig(
                data_path=data_path,
                timeframes=["M15"],
                min_confidence=40,
                initial_balance=10000.0,
            )

            engine = BacktestEngine(config)
            engine.load_data()
            result = engine.run()

            # Verify results
            assert result.total_trades >= 0
            assert result.start_date < result.end_date
            assert len(result.equity_curve) > 0

            # Generate report
            report = result.generate_report()
            assert "Backtest Report" in report
