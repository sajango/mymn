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
from src.risk_guard import RiskGuard, get_risk_guard
from src.signal_filter import SignalConsistencyFilter, get_signal_filter
from src.signal_parser import SignalAction, TradingSignal
from src.multi_tp_manager import get_multi_tp_manager
import pandas as pd

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
        risk_guard: Optional[RiskGuard] = None,
        signal_filter: Optional[SignalConsistencyFilter] = None,
    ):
        self._mt5 = mt5
        self._db = db
        self._settings = settings
        self._risk_guard = risk_guard
        self._signal_filter = signal_filter

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

    @property
    def risk_guard(self) -> RiskGuard:
        """Lazy load risk guard."""
        if self._risk_guard is None:
            self._risk_guard = get_risk_guard()
        return self._risk_guard

    @property
    def signal_filter(self) -> SignalConsistencyFilter:
        """Lazy load signal filter."""
        if self._signal_filter is None:
            self._signal_filter = get_signal_filter()
        return self._signal_filter

    def _validate_sl_tp_direction(
        self,
        action: SignalAction,
        entry_price: float,
        stop_loss: float,
        tp1_price: float,
    ) -> str | None:
        """Validate SL/TP prices are directionally correct.

        Prevents Claude hallucination errors where SL/TP are reversed.

        Args:
            action: BUY or SELL signal action
            entry_price: Entry price
            stop_loss: Stop loss price
            tp1_price: First take profit price

        Returns:
            Error message if invalid, None if valid
        """
        is_buy = action in (SignalAction.BUY, SignalAction.BUY_LIMIT)
        is_sell = action in (SignalAction.SELL, SignalAction.SELL_LIMIT)

        if is_buy:
            # BUY: SL must be below entry, TP must be above entry
            if stop_loss >= entry_price:
                return f"invalid_sl_buy: SL({stop_loss}) >= Entry({entry_price})"
            if tp1_price <= entry_price:
                return f"invalid_tp_buy: TP1({tp1_price}) <= Entry({entry_price})"
        elif is_sell:
            # SELL: SL must be above entry, TP must be below entry
            if stop_loss <= entry_price:
                return f"invalid_sl_sell: SL({stop_loss}) <= Entry({entry_price})"
            if tp1_price >= entry_price:
                return f"invalid_tp_sell: TP1({tp1_price}) >= Entry({entry_price})"

        return None

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

        # Signal consistency check (before risk validation)
        filter_result = self.signal_filter.check(signal)

        if not filter_result.passed:
            logger.warning(
                f"Signal filtered: {filter_result.reason.value} - "
                f"{filter_result.message}"
            )

            # Save signal as skipped
            signal_id = self.db.save_signal(signal)
            self.db.update_signal_status(signal_id, SignalStatus.SKIPPED)

            # Log to skipped_signals for analytics
            self.db.save_skipped_signal(
                reason=f"filter:{filter_result.reason.value}",
                details=filter_result.message,
                confidence=signal.signal.confidence,
            )

            return {
                "status": "filtered",
                "signal_id": signal_id,
                "reason": filter_result.reason.value,
                "message": filter_result.message,
                "previous_action": filter_result.previous_action,
                "minutes_since_last": filter_result.minutes_since_last,
            }

        # Risk validation before execution
        risk_result = await self.risk_guard.validate(signal)

        if not risk_result.passed:
            logger.warning(
                f"Trade rejected by RiskGuard: {risk_result.reason.value} - "
                f"{risk_result.message}"
            )

            # Save signal as rejected
            signal_id = self.db.save_signal(signal)
            self.db.update_signal_status(signal_id, SignalStatus.REJECTED)

            # Log to skipped_signals for analytics
            self.db.save_skipped_signal(
                reason=f"risk_guard:{risk_result.reason.value}",
                details=risk_result.message,
                confidence=signal.signal.confidence,
            )

            return {
                "status": "rejected",
                "reason": risk_result.reason.value,
                "message": risk_result.message,
                "action_taken": risk_result.action_taken,
            }

        # Save signal to database
        signal_id = self.db.save_signal(signal)

        try:
            result = await self._execute_order(
                signal, signal_id, risk_result.position_size_modifier
            )

            # Add risk guard info to result
            if risk_result.action_taken:
                result["risk_guard_action"] = risk_result.action_taken
            result["position_modifier"] = risk_result.position_size_modifier

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
        self, signal: TradingSignal, signal_id: int, position_modifier: float = 1.0
    ) -> dict:
        """Execute order through MT5.

        Args:
            signal: Trading signal
            signal_id: Database signal ID
            position_modifier: Position size multiplier from drawdown manager

        Returns:
            Execution result dict
        """
        s = signal.signal
        symbol = signal.symbol
        
        # Get volatility profile if available
        volatility_factor = 1.0
        sl_adjustment_factor = 1.0
        
        try:
            # Load recent data for volatility analysis (if available)
            csv_dir = self.settings.csv_dir
            h4_path = csv_dir / f"{symbol}_H4.csv"
            h1_path = csv_dir / f"{symbol}_H1.csv"
            m30_path = csv_dir / f"{symbol}_M30.csv"
            
            if h4_path.exists() and h1_path.exists() and m30_path.exists():
                h4_data = pd.read_csv(h4_path)
                h1_data = pd.read_csv(h1_path)
                m30_data = pd.read_csv(m30_path)
                
                # Get volatility manager
                from src.volatility_manager import get_volatility_manager
                vol_manager = get_volatility_manager()
                
                # Analyze current volatility
                vol_profile = vol_manager.analyze_volatility(h4_data, h1_data, m30_data)
                
                # Check if we should filter this entry
                if vol_manager.should_filter_entry(vol_profile.entry_filter, s.confidence):
                    logger.warning(f"Entry filtered by volatility manager: {vol_profile.description}")
                    self.db.update_signal_status(signal_id, SignalStatus.REJECTED)
                    return {
                        "status": "rejected",
                        "signal_id": signal_id,
                        "reason": "volatility_filter",
                        "details": vol_profile.description
                    }
                
                # Get adjustment factors
                volatility_factor = vol_profile.position_size_factor
                sl_adjustment_factor = vol_profile.sl_adjustment_factor
                
                logger.info(
                    f"Volatility adjustments: position={volatility_factor:.2f}x, "
                    f"sl={sl_adjustment_factor:.2f}x ({vol_profile.state.value})"
                )
                
        except Exception as e:
            logger.warning(f"Volatility analysis failed: {e}")
            # Continue with default factors

        # Validate we have required fields
        if s.entry_price is None or s.stop_loss is None:
            self.db.update_signal_status(signal_id, SignalStatus.REJECTED)
            return {
                "status": "rejected",
                "signal_id": signal_id,
                "reason": "missing_entry_or_sl",
            }

        # Create multi-TP exit plan
        tp_manager = get_multi_tp_manager()
        
        # Get market conditions for exit planning
        market_regime = None
        volatility_state = 'normal'
        
        # Try to get latest market memory
        try:
            regime_memory = self.db.get_latest_market_memory('market_regime')
            if regime_memory:
                market_regime = regime_memory.get('memory_value')
                
            vol_memory = self.db.get_latest_market_memory('volatility')
            if vol_memory:
                vol_state_str = vol_memory.get('memory_value', '')
                volatility_state = vol_state_str.split(' ')[0] if vol_state_str else 'normal'
        except Exception as e:
            logger.debug(f"Could not get market memory: {e}")
        
        # Create exit plan
        exit_plan = tp_manager.create_exit_plan(
            entry_price=s.entry_price,
            stop_loss=s.stop_loss,
            direction=s.action.value,
            confidence=s.confidence,
            market_regime=market_regime,
            volatility_state=volatility_state,
            atr=15,  # Default ATR, would get from data
            wave_pattern=signal.wave_analysis.wave_position if signal.wave_analysis else None
        )
        
        logger.info(
            f"Exit plan: {exit_plan.strategy.value} strategy, "
            f"{len(exit_plan.tp_levels)} TP levels, "
            f"Expected R:R: {exit_plan.expected_value:.2f}"
        )
        
        # Use TP1 for initial order (MT5 doesn't support multiple TPs natively)
        tp1_price = exit_plan.tp_levels[0].price if exit_plan.tp_levels else s.entry_price
        
        # Note: We could adjust stop loss here based on volatility if desired
        # For now, we trust the signal's stop loss but log the suggested adjustment
        if sl_adjustment_factor != 1.0:
            logger.info(
                f"Volatility suggests SL adjustment factor: {sl_adjustment_factor:.2f}x "
                f"(not applied - using signal SL: {s.stop_loss})"
            )

        # Validate SL/TP direction consistency
        validation_error = self._validate_sl_tp_direction(
            action=s.action,
            entry_price=s.entry_price,
            stop_loss=s.stop_loss,
            tp1_price=tp1_price,
        )
        if validation_error:
            logger.error(f"SL/TP validation failed: {validation_error}")
            self.db.update_signal_status(signal_id, SignalStatus.REJECTED)
            # Log rejection for Claude AI error tracking
            self.db.save_validation_rejection(
                signal_id=signal_id,
                rejection_type=validation_error.split(":")[0],  # e.g., "invalid_sl_buy"
                entry_price=s.entry_price,
                stop_loss=s.stop_loss,
                take_profit=tp1_price,
                action=s.action.value,
                details=validation_error,
            )
            return {
                "status": "rejected",
                "signal_id": signal_id,
                "reason": validation_error,
            }

        # Calculate position size with confidence
        volume = self.mt5.calculate_position_size(
            symbol=symbol,
            entry_price=s.entry_price,
            stop_loss=s.stop_loss,
            confidence=s.confidence,
        )
        
        # Apply volatility adjustment first
        if volatility_factor != 1.0:
            original_volume = volume
            volume = round(volume * volatility_factor, 2)
            logger.info(
                f"Position adjusted by volatility: "
                f"{original_volume} -> {volume} (factor={volatility_factor})"
            )

        # Apply drawdown manager position modifier
        if position_modifier < 1.0:
            original_volume = volume
            volume = round(volume * position_modifier, 2)
            volume = max(volume, 0.01)  # Minimum lot size
            logger.info(
                f"Position reduced by drawdown manager: "
                f"{original_volume} -> {volume} (modifier={position_modifier})"
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
        
        # Save exit plan details as market memory
        try:
            exit_plan_data = {
                'strategy': exit_plan.strategy.value,
                'tp_levels': [
                    {
                        'name': tp.level_name,
                        'price': tp.price,
                        'percentage': tp.percentage,
                        'rr': tp.risk_reward
                    }
                    for tp in exit_plan.tp_levels
                ],
                'breakeven_trigger': exit_plan.breakeven_trigger,
                'time_stop_hours': exit_plan.time_stop_hours,
                'expected_value': exit_plan.expected_value
            }
            
            import json
            self.db.save_market_memory(
                memory_type='exit_plan',
                key=f'trade_{trade_id}',
                value=json.dumps(exit_plan_data),
                confidence=100,
                expires_hours=72  # Keep for 3 days
            )
        except Exception as e:
            logger.warning(f"Could not save exit plan: {e}")

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

    def record_trade_closed(self, pnl: float, balance: float):
        """Record trade closure for drawdown tracking.

        Should be called when a trade is closed (via SL, TP, or manual).

        Args:
            pnl: Profit/loss amount in account currency
            balance: Current account balance after trade
        """
        from src.drawdown_manager import get_drawdown_manager

        is_win = pnl > 0
        dd_manager = get_drawdown_manager()
        dd_manager.record_trade_result(pnl, is_win, balance)
        logger.info(f"Trade result recorded: pnl={pnl:.2f}, is_win={is_win}")


# Lazy singleton
_trade_executor: Optional[TradeExecutor] = None


def get_trade_executor() -> TradeExecutor:
    """Get or create trade executor singleton."""
    global _trade_executor
    if _trade_executor is None:
        _trade_executor = TradeExecutor()
    return _trade_executor
