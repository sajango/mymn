"""MT5 client for data export and trade execution."""

import logging
import time
from datetime import datetime, timedelta, timezone
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

    def get_tick(self, symbol: str) -> Optional[dict]:
        """Get current tick data for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Dict with bid, ask, time or None if unavailable
        """
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "time": tick.time,
            "volume": tick.volume,
        }

    def get_last_candles(
        self, symbol: str, timeframe: str = "M15", count: int = 2
    ) -> Optional[list[dict]]:
        """Get last N candles for compression observer.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe string (M15, M30, H1, H4)
            count: Number of candles to fetch

        Returns:
            List of candle dicts with open, high, low, close or None
        """
        if timeframe not in TIMEFRAMES:
            logger.error(f"Invalid timeframe: {timeframe}")
            return None

        tf = TIMEFRAMES[timeframe]
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

        if rates is None or len(rates) == 0:
            error = mt5.last_error()
            logger.debug(f"Failed to fetch candles: {error}")
            return None

        candles = []
        for rate in rates:
            candles.append({
                "time": rate[0],
                "open": rate[1],
                "high": rate[2],
                "low": rate[3],
                "close": rate[4],
                "volume": rate[5],
            })

        return candles

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


    def get_account_info(self) -> Optional[dict]:
        """Get account balance and margin info.

        Returns:
            Account info dict or None if unavailable
        """
        info = mt5.account_info()
        if info is None:
            logger.error(f"Failed to get account info: {mt5.last_error()}")
            return None
        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "currency": info.currency,
            "leverage": info.leverage,
        }

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        risk_percent: Optional[float] = None,
        confidence: int = 100,
    ) -> float:
        """Calculate lot size based on risk percentage and confidence.

        Position sizing modes:
        1. Fixed lots mode (use_fixed_lots=true): Uses config.fixed_lot_size
        2. Risk-based mode (default): Calculates based on account balance and SL distance
           - confidence >= 75: full position (100% of risk_percent)
           - confidence 60-74: half position (50% of risk_percent)
           - confidence < 60: minimum position

        Args:
            symbol: Trading symbol
            entry_price: Entry price
            stop_loss: Stop loss price
            risk_percent: Risk percentage (default from config)
            confidence: Signal confidence 0-100

        Returns:
            Calculated lot size
        """
        # Fixed lots mode - bypass risk calculation
        if self.config.use_fixed_lots:
            lot_size = self.config.fixed_lot_size
            logger.info(f"Position size: {lot_size} lots (FIXED MODE)")
            return lot_size

        # Risk-based calculation
        risk_percent = risk_percent or self.config.risk_percent

        # Confidence-based position sizing
        if confidence >= self.config.confidence_full_position:
            size_multiplier = 1.0
        elif confidence >= self.config.confidence_half_position:
            size_multiplier = 0.5
        else:
            size_multiplier = 0.25  # Minimum for low confidence

        account = self.get_account_info()
        if account is None:
            logger.error("Cannot get account info for position sizing")
            return 0.01  # Minimum fallback

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"Symbol info unavailable: {symbol}")
            return 0.01

        # Calculate risk amount with confidence adjustment
        risk_amount = account["balance"] * (risk_percent / 100) * size_multiplier
        stop_distance = abs(entry_price - stop_loss)

        if stop_distance == 0:
            logger.error("Stop distance is zero")
            return 0.01

        # XAUUSD: 1 lot = 100 oz, pip value varies by price
        # For gold, trade_contract_size is typically 100
        pip_value = symbol_info.trade_contract_size * symbol_info.point
        lot_size = risk_amount / (stop_distance / symbol_info.point * pip_value)

        # Apply limits
        lot_size = max(symbol_info.volume_min, lot_size)
        lot_size = min(symbol_info.volume_max, lot_size)
        lot_size = min(self.config.max_position_size, lot_size)

        # Round to step
        lot_size = round(lot_size / symbol_info.volume_step) * symbol_info.volume_step
        lot_size = round(lot_size, 2)

        logger.info(
            f"Position size: {lot_size} lots "
            f"(risk: {risk_percent}%, confidence: {confidence}%, "
            f"multiplier: {size_multiplier}, amount: ${risk_amount:.2f})"
        )
        return lot_size

    def _get_filling_mode(self, symbol: str) -> int:
        """Get supported filling mode for symbol.

        MT5 brokers support different filling modes. Query symbol info
        to determine which mode to use.

        Args:
            symbol: Trading symbol

        Returns:
            Appropriate ORDER_FILLING_* constant
        """
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.warning(f"Cannot get symbol info for {symbol}, defaulting to FOK")
            return mt5.ORDER_FILLING_FOK

        filling_mode = symbol_info.filling_mode

        # Check supported modes (filling_mode is a bitmask)
        # SYMBOL_FILLING_FOK = 1, SYMBOL_FILLING_IOC = 2
        if filling_mode & 1:  # FOK supported
            return mt5.ORDER_FILLING_FOK
        elif filling_mode & 2:  # IOC supported
            return mt5.ORDER_FILLING_IOC
        else:
            # Fallback to RETURN for brokers that don't specify
            return mt5.ORDER_FILLING_RETURN

    def place_market_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        stop_loss: float,
        take_profit: float,
        comment: str = "EW Auto",
        magic: int = 123456,
    ) -> Optional[int]:
        """Place market order with SL/TP.

        Args:
            symbol: Trading symbol
            order_type: "BUY" or "SELL"
            volume: Lot size
            stop_loss: Stop loss price
            take_profit: Take profit price (TP1)
            comment: Order comment
            magic: Magic number for identification

        Returns:
            Order ticket or None on failure, -1 for paper trading
        """
        if self.config.paper_trading:
            logger.info(
                f"PAPER TRADE: {order_type} {volume} {symbol} "
                f"SL:{stop_loss:.2f} TP:{take_profit:.2f}"
            )
            return -1  # Fake ticket for paper trading

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Failed to get tick: {mt5.last_error()}")
            return None

        mt5_type = mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL
        price = tick.ask if order_type == "BUY" else tick.bid
        filling_mode = self._get_filling_mode(symbol)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": self.config.max_slippage,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        # Retry on requote
        for attempt in range(3):
            result = mt5.order_send(request)

            if result is None:
                logger.error(f"Order send returned None: {mt5.last_error()}")
                return None

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"Order placed: ticket={result.order}, price={result.price}")
                return result.order

            if result.retcode == mt5.TRADE_RETCODE_REQUOTE:
                logger.warning(f"Requote attempt {attempt + 1}")
                tick = mt5.symbol_info_tick(symbol)
                if tick:
                    request["price"] = tick.ask if order_type == "BUY" else tick.bid
                continue

            logger.error(f"Order failed: {result.retcode} - {result.comment}")
            break

        return None

    def get_positions(self, magic: int = 123456) -> list[dict]:
        """Get open positions by magic number.

        Args:
            magic: Magic number filter

        Returns:
            List of position dicts
        """
        positions = mt5.positions_get()
        if positions is None:
            return []

        return [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "open_price": p.price_open,
                "current_price": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "magic": p.magic,
                "time": p.time,
            }
            for p in positions
            if p.magic == magic
        ]

    def get_position_by_ticket(self, ticket: int) -> Optional[dict]:
        """Get single position by ticket.

        Args:
            ticket: Position ticket

        Returns:
            Position dict or None if not found
        """
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return None

        p = positions[0]
        return {
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": "BUY" if p.type == 0 else "SELL",
            "volume": p.volume,
            "open_price": p.price_open,
            "current_price": p.price_current,
            "sl": p.sl,
            "tp": p.tp,
            "profit": p.profit,
            "magic": p.magic,
            "time": p.time,
        }

    def modify_position(
        self,
        ticket: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """Modify position SL/TP.

        Args:
            ticket: Position ticket
            stop_loss: New stop loss (None keeps existing)
            take_profit: New take profit (None keeps existing)

        Returns:
            True if successful
        """
        if self.config.paper_trading:
            logger.info(f"PAPER: Modify position {ticket} SL:{stop_loss} TP:{take_profit}")
            return True

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            logger.error(f"Position not found: {ticket}")
            return False

        pos = positions[0]

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": pos.symbol,
            "sl": stop_loss if stop_loss else pos.sl,
            "tp": take_profit if take_profit else pos.tp,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error(f"Modify returned None: {mt5.last_error()}")
            return False

        success = result.retcode == mt5.TRADE_RETCODE_DONE

        if success:
            logger.info(f"Position modified: {ticket} SL:{request['sl']} TP:{request['tp']}")
        else:
            logger.error(f"Modify failed: {result.retcode} - {result.comment}")

        return success

    def close_partial(self, ticket: int, volume: float) -> bool:
        """Close partial position volume.

        Args:
            ticket: Position ticket
            volume: Volume to close

        Returns:
            True if successful
        """
        if self.config.paper_trading:
            logger.info(f"PAPER: Partial close {ticket} volume={volume}")
            return True

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            logger.error(f"Position not found for partial close: {ticket}")
            return False

        pos = positions[0]
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            logger.error(f"Failed to get tick for partial close: {mt5.last_error()}")
            return False

        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == 0 else tick.ask

        filling_mode = self._get_filling_mode(pos.symbol)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": pos.symbol,
            "volume": volume,
            "type": close_type,
            "price": price,
            "deviation": self.config.max_slippage,
            "magic": pos.magic,
            "type_filling": filling_mode,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error(f"Partial close returned None: {mt5.last_error()}")
            return False

        success = result.retcode == mt5.TRADE_RETCODE_DONE

        if success:
            logger.info(f"Partial close: {ticket} volume={volume} price={result.price}")
        else:
            logger.error(f"Partial close failed: {result.retcode} - {result.comment}")

        return success

    def close_position(self, ticket: int) -> bool:
        """Close entire position.

        Args:
            ticket: Position ticket

        Returns:
            True if successful
        """
        pos = self.get_position_by_ticket(ticket)
        if pos is None:
            logger.error(f"Position not found for close: {ticket}")
            return False

        return self.close_partial(ticket, pos["volume"])

    def get_current_atr(self, symbol: str, period: int = 14) -> Optional[float]:
        """Get current ATR value for symbol.

        Args:
            symbol: Trading symbol
            period: ATR period

        Returns:
            ATR value or None
        """
        df = self.fetch_ohlcv(symbol, "H1", period * 2)
        if df is None or len(df) < period:
            return None

        atr = self.calculate_atr(df["high"], df["low"], df["close"], period)
        return atr.iloc[-1] if not atr.empty else None

    def get_position_close_info(
        self, ticket: int, lookback_days: int = 7, max_retries: int = 3
    ) -> Optional[dict]:
        """Get close info for a position from deal history.

        When MT5 auto-closes a position (TP/SL hit), this retrieves
        the close price and profit from deal history.

        Uses retry logic with exponential backoff to handle MT5 sync delays.

        Args:
            ticket: Original position ticket
            lookback_days: Days to search in history
            max_retries: Number of retry attempts for deal history lookup

        Returns:
            Dict with close_price, profit, close_reason or None if not found
        """
        from_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        to_date = datetime.now(timezone.utc) + timedelta(days=1)

        # Retry with exponential backoff for MT5 sync delays
        deals = None
        for attempt in range(max_retries):
            deals = mt5.history_deals_get(from_date, to_date, position=ticket)
            if deals is not None and len(deals) > 0:
                break
            if attempt < max_retries - 1:
                delay = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s
                logger.debug(f"No deals yet for {ticket}, retry {attempt + 1}/{max_retries} in {delay}s")
                time.sleep(delay)

        if deals is None or len(deals) == 0:
            logger.info(f"No deal history for position {ticket} after {max_retries} attempts")
            return None

        # Find the closing deal
        close_deal = None
        for deal in deals:
            if deal.entry == mt5.DEAL_ENTRY_OUT:
                close_deal = deal
                break

        if close_deal is None:
            logger.debug(f"No closing deal found for position {ticket}")
            return None

        # Determine close reason from deal comment/reason
        close_reason = self._parse_close_reason(close_deal)

        return {
            "ticket": ticket,
            "close_price": close_deal.price,
            "profit": close_deal.profit,
            "commission": close_deal.commission,
            "swap": close_deal.swap,
            "close_time": datetime.fromtimestamp(close_deal.time, tz=timezone.utc),
            "close_reason": close_reason,
            "deal_ticket": close_deal.ticket,
        }

    def _parse_close_reason(self, deal) -> str:
        """Parse close reason from deal.

        Args:
            deal: MT5 deal object

        Returns:
            Close reason string: 'tp', 'sl', 'manual', or 'unknown'
        """
        # Map MT5 deal reason constants to readable strings
        reason_map = {
            mt5.DEAL_REASON_SL: "sl",
            mt5.DEAL_REASON_TP: "tp",
            mt5.DEAL_REASON_SO: "stop_out",
        }

        # Manual close reasons
        manual_reasons = {
            mt5.DEAL_REASON_CLIENT,
            mt5.DEAL_REASON_MOBILE,
            mt5.DEAL_REASON_WEB,
            mt5.DEAL_REASON_EXPERT,
        }

        if hasattr(deal, "reason") and deal.reason in reason_map:
            return reason_map[deal.reason]

        # Fallback: check comment for keywords
        comment = deal.comment.lower() if deal.comment else ""
        if "tp" in comment or "take profit" in comment:
            return "tp"
        if "sl" in comment or "stop loss" in comment:
            return "sl"
        if "so" in comment or "stop out" in comment:
            return "stop_out"

        return "manual" if deal.reason in manual_reasons else "unknown"


# Singleton instance
mt5_client = MT5Client()
