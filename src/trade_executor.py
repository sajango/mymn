"""Trade executor - coordinates signal execution with MT5.

Main entry point for executing trades based on TradingSignal objects.
Handles:
- Position sizing with confidence adjustment
- Order placement via MT5
- Database persistence
- Paper trading mode
"""

import logging
from typing import Optional

from src.config import get_settings
from src.database import Database, SignalStatus, get_database
from src.mt5_client import MT5Client, mt5_client
from src.signal_parser import SignalAction, TradingSignal

logger = logging.getLogger(__name__)


class TradeExecutor:
    """Executes trading signals via MT5.

    Coordinates between:
    - Signal parsing/validation
    - Position sizing (confidence-adjusted)
    - MT5 order placement
    - Database persistence

    Paper trading mode logs actions without live execution.
    """

    MAGIC_NUMBER = 123456  # Identifies our trades in MT5

    def __init__(
        self,
        mt5: Optional[MT5Client] = None,
        db: Optional[Database] = None,
        settings=None,
    ):
        self._mt5 = mt5
        self._db = db
        self._settings = settings

    @property
    def mt5(self) -> MT5Client:
        """Lazy load MT5 client."""
        if self._mt5 is None:
            self._mt5 = mt5_client
        return self._mt5

    @property
    def db(self) -> Database:
        """Lazy load database."""
        if self._db is None:
            self._db = get_database()
        return self._db

    @property
    def settings(self):
        """Lazy load settings."""
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def execute_signal(self, signal: TradingSignal) -> dict:
        """Execute trading signal.

        Args:
            signal: Trading signal to execute

        Returns:
            Execution result dict with status, ticket, etc.
        """
        # Validate signal is tradeable
        if not signal.is_tradeable:
            logger.info(f"Signal not tradeable: {signal.signal.action}")
            return {
                "status": "skipped",
                "reason": "not_tradeable",
                "action": signal.signal.action.value,
            }

        # Save signal to database
        signal_id = self.db.save_signal(signal)

        try:
            result = await self._execute_order(signal, signal_id)
            return result
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            self.db.update_signal_status(signal_id, SignalStatus.REJECTED)
            return {
                "status": "error",
                "signal_id": signal_id,
                "error": str(e),
            }

    async def _execute_order(
        self, signal: TradingSignal, signal_id: int
    ) -> dict:
        """Execute order through MT5.

        Args:
            signal: Trading signal
            signal_id: Database signal ID

        Returns:
            Execution result dict
        """
        s = signal.signal
        symbol = signal.symbol

        # Validate we have required fields
        if s.entry_price is None or s.stop_loss is None:
            self.db.update_signal_status(signal_id, SignalStatus.REJECTED)
            return {
                "status": "rejected",
                "signal_id": signal_id,
                "reason": "missing_entry_or_sl",
            }

        # Get TP1 for initial order (if available)
        tp1_price = s.take_profit[0].price if s.take_profit else s.entry_price

        # Calculate position size with confidence
        volume = self.mt5.calculate_position_size(
            symbol=symbol,
            entry_price=s.entry_price,
            stop_loss=s.stop_loss,
            confidence=s.confidence,
        )

        # Determine order type
        order_type = "BUY" if signal.is_buy else "SELL"

        # Place order
        ticket = self.mt5.place_market_order(
            symbol=symbol,
            order_type=order_type,
            volume=volume,
            stop_loss=s.stop_loss,
            take_profit=tp1_price,
            comment=f"EW {s.confidence}%",
            magic=self.MAGIC_NUMBER,
        )

        if ticket is None:
            self.db.update_signal_status(signal_id, SignalStatus.REJECTED)
            return {
                "status": "rejected",
                "signal_id": signal_id,
                "reason": "order_failed",
            }

        # Save trade to database
        trade_id = self.db.save_trade(
            signal_id=signal_id,
            ticket=ticket,
            volume=volume,
            signal=signal,
        )

        # Update signal status
        self.db.update_signal_status(signal_id, SignalStatus.EXECUTED)

        logger.info(
            f"Trade executed: signal={signal_id}, trade={trade_id}, "
            f"ticket={ticket}, volume={volume}"
        )

        return {
            "status": "executed",
            "signal_id": signal_id,
            "trade_id": trade_id,
            "ticket": ticket,
            "volume": volume,
            "order_type": order_type,
            "entry": s.entry_price,
            "sl": s.stop_loss,
            "tp1": tp1_price,
            "paper_mode": self.settings.paper_trading if self._settings else True,
        }

    def skip_signal(self, signal: TradingSignal, reason: str = "user_skipped") -> int:
        """Mark signal as skipped.

        Args:
            signal: Trading signal
            reason: Skip reason

        Returns:
            Signal ID
        """
        signal_id = self.db.save_signal(signal)
        self.db.update_signal_status(signal_id, SignalStatus.SKIPPED)
        logger.info(f"Signal skipped: {signal_id}, reason={reason}")
        return signal_id

    def get_open_positions_summary(self) -> str:
        """Get formatted summary of open positions.

        Returns:
            Formatted string for display
        """
        trades = self.db.get_open_trades()

        if not trades:
            return "No open positions"

        lines = []
        for t in trades:
            direction = "↑" if t["action"] == "BUY" else "↓"
            trail = t.get("trailing_state", "inactive")
            lines.append(
                f"{t['symbol']} {direction} {t['volume']} @ {t['entry_price']:.2f} "
                f"[SL:{t['stop_loss']:.2f}] [{trail}]"
            )

        return "\n".join(lines)


# Lazy singleton
_trade_executor: Optional[TradeExecutor] = None


def get_trade_executor() -> TradeExecutor:
    """Get or create trade executor singleton."""
    global _trade_executor
    if _trade_executor is None:
        _trade_executor = TradeExecutor()
    return _trade_executor
