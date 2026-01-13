"""Trailing stop manager with state machine logic.

State Machine:
- INACTIVE: Initial state, SL at original position
- ACTIVATED: TP1 hit OR profit > 1R, SL moved to breakeven + buffer
- TRAILING: SL trails price at ATR distance

Activation triggers:
1. TP1 price reached (partial close triggered)
2. Profit exceeds 1R (stop distance from entry)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.config import get_settings
from src.database import Database, TrailingState, get_database
from src.mt5_client import MT5Client, mt5_client

logger = logging.getLogger(__name__)


class TrailingStopManager:
    """Manages trailing stop logic for open positions.

    Monitors positions and updates stop losses based on state machine:
    - INACTIVE → ACTIVATED when TP1 hit or profit > 1R
    - ACTIVATED → TRAILING when price moves favorably
    - TRAILING: Continuously trail at ATR distance

    Uses configuration:
    - trail_atr_multiplier: ATR multiple for trail distance
    - breakeven_buffer_pips: Pips above entry for breakeven SL
    """

    def __init__(
        self,
        mt5: Optional[MT5Client] = None,
        db: Optional[Database] = None,
        settings=None,
    ):
        self._mt5 = mt5
        self._db = db
        self._settings = settings
        self._consecutive_failures = 0
        self._max_failures = 3

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

    def check_position(self, trade_id: int) -> dict:
        """Check single position and update trailing stop.

        Args:
            trade_id: Database trade ID

        Returns:
            Status dict with action taken
        """
        trade = self.db.get_trade_by_id(trade_id)
        if trade is None:
            return {"status": "error", "message": "Trade not found"}

        if trade["status"] not in ("open", "partial"):
            return {"status": "skipped", "message": "Trade not open"}

        # Get current position from MT5
        position = self.mt5.get_position_by_ticket(trade["ticket"])
        if position is None:
            # Position closed externally - sync DB state
            return self._sync_closed_position(trade)

        current_state = TrailingState(trade["trailing_state"])
        action_taken = "none"

        # State machine transitions
        if current_state == TrailingState.INACTIVE:
            action_taken = self._check_activation(trade, position)

        elif current_state == TrailingState.ACTIVATED:
            action_taken = self._check_trailing_start(trade, position)

        elif current_state == TrailingState.TRAILING:
            action_taken = self._update_trailing_stop(trade, position)

        return {
            "status": "ok",
            "trade_id": trade_id,
            "state": current_state.value,
            "action": action_taken,
        }

    def _check_activation(self, trade: dict, position: dict) -> str:
        """Check if trailing stop should activate.

        Activation triggers:
        1. TP1 reached (price crossed TP1 level)
        2. Profit > 1R (profit exceeds initial risk)

        Args:
            trade: Trade dict from database
            position: Position dict from MT5

        Returns:
            Action description
        """
        entry = trade["entry_price"]
        initial_sl = trade["initial_stop_loss"]
        current_price = position["current_price"]
        is_buy = trade["action"] == "BUY"

        # Calculate 1R in price terms
        one_r = abs(entry - initial_sl)

        # Check TP1 reached
        tp_levels = self.db.get_tp_levels(trade["id"])
        tp1 = next((tp for tp in tp_levels if tp["level"] == "TP1"), None)
        tp1_hit = False

        if tp1:
            if is_buy and current_price >= tp1["price"]:
                tp1_hit = True
            elif not is_buy and current_price <= tp1["price"]:
                tp1_hit = True

        # Check profit > 1R
        profit_distance = current_price - entry if is_buy else entry - current_price
        profit_over_1r = profit_distance >= one_r

        if tp1_hit or profit_over_1r:
            trigger = "TP1_HIT" if tp1_hit else "PROFIT_1R"
            return self._activate_trailing(trade, position, trigger)

        return "none"

    def _activate_trailing(
        self, trade: dict, position: dict, trigger: str
    ) -> str:
        """Activate trailing stop - move SL to breakeven + buffer.

        Args:
            trade: Trade dict
            position: Position dict
            trigger: Activation trigger reason

        Returns:
            Action description
        """
        entry = trade["entry_price"]
        is_buy = trade["action"] == "BUY"

        # Calculate breakeven with buffer
        buffer_pips = self.settings.breakeven_buffer_pips
        symbol_info = self.mt5.validate_symbol(trade["symbol"])

        # For XAUUSD: 1 pip = 0.1, so buffer in price = buffer_pips * 0.1
        # Simplified: use point * 10 for pip
        buffer_price = buffer_pips * 0.1  # For gold

        if is_buy:
            breakeven_sl = entry + buffer_price
        else:
            breakeven_sl = entry - buffer_price

        # Only move SL if it improves position
        current_sl = position["sl"]
        should_update = (
            (is_buy and breakeven_sl > current_sl)
            or (not is_buy and breakeven_sl < current_sl)
        )

        if should_update:
            success = self.mt5.modify_position(
                trade["ticket"], stop_loss=breakeven_sl
            )

            if success:
                self.db.update_trailing_state(
                    trade["id"],
                    TrailingState.ACTIVATED,
                    trailing_stop_price=breakeven_sl,
                    breakeven_price=breakeven_sl,
                )
                self.db.update_stop_loss(trade["id"], breakeven_sl)
                logger.info(
                    f"Trailing activated: trade={trade['id']}, "
                    f"trigger={trigger}, sl={breakeven_sl}"
                )
                return f"activated_{trigger}"

            logger.error(f"Failed to modify SL for trade {trade['id']}")
            return "activation_failed"

        # Already at better SL, just update state
        self.db.update_trailing_state(
            trade["id"],
            TrailingState.ACTIVATED,
            breakeven_price=breakeven_sl,
        )
        return f"activated_{trigger}_no_sl_change"

    def _check_trailing_start(self, trade: dict, position: dict) -> str:
        """Check if should start trailing (ACTIVATED → TRAILING).

        Transition to TRAILING when price moves beyond breakeven + 1 ATR.

        Args:
            trade: Trade dict
            position: Position dict

        Returns:
            Action description
        """
        breakeven = trade.get("breakeven_price") or trade["entry_price"]
        current_price = position["current_price"]
        is_buy = trade["action"] == "BUY"

        # Get current ATR
        atr = self.mt5.get_current_atr(trade["symbol"])
        if atr is None:
            logger.warning(f"Cannot get ATR for {trade['symbol']}")
            return "atr_unavailable"

        # Price needs to be ATR distance beyond breakeven to start trailing
        trail_trigger = atr * self.settings.trail_atr_multiplier

        if is_buy:
            if current_price >= breakeven + trail_trigger:
                return self._start_trailing(trade, position, atr)
        else:
            if current_price <= breakeven - trail_trigger:
                return self._start_trailing(trade, position, atr)

        return "none"

    def _start_trailing(
        self, trade: dict, position: dict, atr: float
    ) -> str:
        """Start trailing mode - set initial trailing stop.

        Args:
            trade: Trade dict
            position: Position dict
            atr: Current ATR value

        Returns:
            Action description
        """
        current_price = position["current_price"]
        is_buy = trade["action"] == "BUY"
        trail_distance = atr * self.settings.trail_atr_multiplier

        if is_buy:
            new_sl = current_price - trail_distance
        else:
            new_sl = current_price + trail_distance

        # Only if better than current
        current_sl = position["sl"]
        should_update = (
            (is_buy and new_sl > current_sl)
            or (not is_buy and new_sl < current_sl)
        )

        if should_update:
            success = self.mt5.modify_position(trade["ticket"], stop_loss=new_sl)

            if success:
                self.db.update_trailing_state(
                    trade["id"],
                    TrailingState.TRAILING,
                    trailing_stop_price=new_sl,
                )
                self.db.update_stop_loss(trade["id"], new_sl)
                logger.info(
                    f"Trailing started: trade={trade['id']}, sl={new_sl}"
                )
                return "trailing_started"

            return "trailing_start_failed"

        # State transition without SL change
        self.db.update_trailing_state(
            trade["id"],
            TrailingState.TRAILING,
        )
        return "trailing_started_no_sl_change"

    def _update_trailing_stop(self, trade: dict, position: dict) -> str:
        """Update trailing stop as price moves favorably.

        Only moves SL in direction of profit, never backward.

        Args:
            trade: Trade dict
            position: Position dict

        Returns:
            Action description
        """
        current_price = position["current_price"]
        current_sl = position["sl"]
        is_buy = trade["action"] == "BUY"

        # Get ATR for trail distance
        atr = self.mt5.get_current_atr(trade["symbol"])
        if atr is None:
            return "atr_unavailable"

        trail_distance = atr * self.settings.trail_atr_multiplier

        if is_buy:
            new_sl = current_price - trail_distance
            should_update = new_sl > current_sl
        else:
            new_sl = current_price + trail_distance
            should_update = new_sl < current_sl

        if should_update:
            success = self.mt5.modify_position(trade["ticket"], stop_loss=new_sl)

            if success:
                self.db.update_trailing_state(
                    trade["id"],
                    TrailingState.TRAILING,
                    trailing_stop_price=new_sl,
                )
                self.db.update_stop_loss(trade["id"], new_sl)
                logger.info(f"Trailing updated: trade={trade['id']}, sl={new_sl}")
                return "trailing_updated"

            return "trailing_update_failed"

        return "none"

    def _sync_closed_position(self, trade: dict) -> dict:
        """Sync DB when MT5 position was closed externally (TP/SL hit).

        Retrieves close info from MT5 deal history and updates DB.

        Args:
            trade: Trade dict from database

        Returns:
            Status dict with sync details
        """
        ticket = trade["ticket"]
        trade_id = trade["id"]

        # Get close info from MT5 deal history
        close_info = self.mt5.get_position_close_info(ticket)

        if close_info is None:
            # No deal history found - estimate close from SL (conservative)
            # Assume worst case: position hit stop loss
            estimated_close, estimated_profit = self._estimate_close_values(trade)

            logger.warning(
                f"Position {ticket} closed but no deal history. "
                f"Estimated close={estimated_close:.2f}, profit={estimated_profit:.2f}"
            )

            self.db.close_trade(
                trade_id=trade_id,
                close_price=estimated_close,
                profit=estimated_profit,
            )
            return {
                "status": "synced",
                "trade_id": trade_id,
                "ticket": ticket,
                "close_price": estimated_close,
                "profit": estimated_profit,
                "close_reason": "unknown",
                "message": "Closed with estimated values (no deal history)",
            }

        # Calculate total profit including swap and commission
        total_profit = (
            close_info["profit"]
            + close_info.get("swap", 0)
            + close_info.get("commission", 0)
        )

        # Update DB with actual close info
        self.db.close_trade(
            trade_id=trade_id,
            close_price=close_info["close_price"],
            profit=total_profit,
        )

        logger.info(
            f"Position synced: trade={trade_id}, ticket={ticket}, "
            f"reason={close_info['close_reason']}, profit={total_profit:.2f}"
        )

        return {
            "status": "synced",
            "trade_id": trade_id,
            "ticket": ticket,
            "close_price": close_info["close_price"],
            "profit": total_profit,
            "close_reason": close_info["close_reason"],
            "close_time": close_info["close_time"].isoformat(),
        }

    def _estimate_close_values(self, trade: dict) -> tuple[float, float]:
        """Estimate close price and profit when deal history unavailable.

        Smart estimation priority:
        1. If trailing active → use trailing_stop_price (locked-in profit)
        2. If breakeven activated → use breakeven_price (at least BE)
        3. If TP levels triggered → estimate near highest triggered TP
        4. Fallback → use midpoint between entry and SL (better than SL)

        Args:
            trade: Trade dict from database

        Returns:
            Tuple of (estimated_close_price, estimated_profit)
        """
        entry = trade["entry_price"]
        sl = trade["stop_loss"]
        volume = trade["volume"]
        is_buy = trade["action"] == "BUY"
        trailing_state = trade.get("trailing_state", "inactive")

        # Priority 1: If trailing was active, use trailing stop price
        # This represents locked-in profit level
        if trailing_state == "trailing":
            trailing_price = trade.get("trailing_stop_price")
            if trailing_price:
                estimated_close = trailing_price
                logger.info(
                    f"Estimation using trailing_stop_price={trailing_price}"
                )
                return self._calculate_profit(
                    estimated_close, entry, volume, is_buy
                )

        # Priority 2: If breakeven activated, use breakeven price
        # Position was at least at breakeven when closed
        if trailing_state in ("activated", "trailing"):
            breakeven = trade.get("breakeven_price")
            if breakeven:
                estimated_close = breakeven
                logger.info(f"Estimation using breakeven_price={breakeven}")
                return self._calculate_profit(
                    estimated_close, entry, volume, is_buy
                )

        # Priority 3: Check TP levels for context
        tp_levels = self.db.get_tp_levels(trade["id"])
        triggered_tps = [tp for tp in tp_levels if tp.get("triggered")]
        if triggered_tps:
            # Use highest triggered TP price as estimate
            if is_buy:
                best_tp = max(triggered_tps, key=lambda x: x["price"])
            else:
                best_tp = min(triggered_tps, key=lambda x: x["price"])
            estimated_close = best_tp["price"]
            logger.info(
                f"Estimation using triggered TP level={best_tp['level']}"
            )
            return self._calculate_profit(
                estimated_close, entry, volume, is_buy
            )

        # Priority 4: Fallback to midpoint (better than worst-case SL)
        # Midpoint assumes random exit, not definite loss
        tp = trade.get("take_profit")
        if tp:
            estimated_close = (entry + tp) / 2 if is_buy else (entry + tp) / 2
            logger.info(f"Estimation using midpoint entry-TP={estimated_close}")
        else:
            # Last resort: midpoint between entry and SL
            estimated_close = (entry + sl) / 2
            logger.info(f"Estimation using midpoint entry-SL={estimated_close}")

        return self._calculate_profit(estimated_close, entry, volume, is_buy)

    def _calculate_profit(
        self, close: float, entry: float, volume: float, is_buy: bool
    ) -> tuple[float, float]:
        """Calculate profit from close price.

        Args:
            close: Estimated close price
            entry: Entry price
            volume: Position volume in lots
            is_buy: True for BUY, False for SELL

        Returns:
            Tuple of (close_price, profit)
        """
        # XAUUSD contract: 1 lot = 100 oz (contract size = 100)
        contract_size = 100
        price_diff = close - entry if is_buy else entry - close
        profit = price_diff * volume * contract_size
        return close, round(profit, 2)

    def check_all_positions(self) -> list[dict]:
        """Check all open positions for trailing stop updates.

        Returns:
            List of status dicts for each position
        """
        results = []
        open_trades = self.db.get_open_trades()

        for trade in open_trades:
            try:
                result = self.check_position(trade["id"])
                results.append(result)

                # Track failures for alerting
                if result.get("status") == "error":
                    self._consecutive_failures += 1
                else:
                    self._consecutive_failures = 0

            except Exception as e:
                logger.error(f"Error checking trade {trade['id']}: {e}")
                self._consecutive_failures += 1
                results.append({
                    "status": "error",
                    "trade_id": trade["id"],
                    "message": str(e),
                })

        return results

    def should_alert(self) -> bool:
        """Check if consecutive failures warrant an alert.

        Returns:
            True if alert should be sent
        """
        return self._consecutive_failures >= self._max_failures

    def reset_failures(self):
        """Reset failure counter after alert sent."""
        self._consecutive_failures = 0

    def check_tp_levels(self, trade_id: int) -> dict:
        """Check and handle TP level triggers for partial closes.

        Args:
            trade_id: Database trade ID

        Returns:
            Status dict with actions taken
        """
        trade = self.db.get_trade_by_id(trade_id)
        if trade is None:
            return {"status": "error", "message": "Trade not found"}

        position = self.mt5.get_position_by_ticket(trade["ticket"])
        if position is None:
            return {"status": "closed", "message": "Position closed"}

        tp_levels = self.db.get_tp_levels(trade_id)
        current_price = position["current_price"]
        is_buy = trade["action"] == "BUY"
        actions = []

        for tp in tp_levels:
            if tp["triggered"]:
                continue

            tp_hit = (
                (is_buy and current_price >= tp["price"])
                or (not is_buy and current_price <= tp["price"])
            )

            if tp_hit:
                # Calculate volume to close
                close_pct = tp["close_percent"] / 100
                close_volume = round(trade["initial_volume"] * close_pct, 2)

                if close_volume > 0:
                    success = self.mt5.close_partial(
                        trade["ticket"], close_volume
                    )

                    if success:
                        self.db.mark_tp_triggered(trade_id, tp["level"])
                        new_volume = round(position["volume"] - close_volume, 2)
                        self.db.update_trade_volume(trade_id, new_volume)

                        actions.append({
                            "level": tp["level"],
                            "status": "triggered",
                            "volume_closed": close_volume,
                        })
                        logger.info(
                            f"TP {tp['level']} triggered: "
                            f"trade={trade_id}, closed={close_volume}"
                        )
                    else:
                        actions.append({
                            "level": tp["level"],
                            "status": "close_failed",
                        })

        return {
            "status": "ok",
            "trade_id": trade_id,
            "actions": actions,
        }

    def sync_historical_positions(self, lookback_days: int = 7) -> dict:
        """Scan MT5 history and sync positions closed while system offline.

        Runs on startup to backfill database for positions that closed
        when the system wasn't running (manual close, TP/SL hit offline).

        Args:
            lookback_days: Days to scan in MT5 history (default 7)

        Returns:
            Summary dict with synced_count and errors
        """
        import MetaTrader5 as mt5

        MAGIC_NUMBER = 123456  # Same as TradeExecutor/RiskGuard

        # Get open trades from database that might be stale
        open_trades = self.db.get_open_trades()
        if not open_trades:
            logger.info("No open trades in DB, skipping historical sync")
            return {"synced_count": 0, "errors": []}

        # Build ticket lookup
        ticket_to_trade = {t["ticket"]: t for t in open_trades}

        # Scan MT5 deal history
        from_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        to_date = datetime.now(timezone.utc) + timedelta(days=1)

        deals = mt5.history_deals_get(from_date, to_date)
        if deals is None:
            logger.warning("Could not retrieve MT5 deal history")
            return {"synced_count": 0, "errors": ["MT5 history unavailable"]}

        synced = 0
        errors = []

        # Find closing deals that match our tracked trades
        for deal in deals:
            # Only process OUT deals (position close) with our magic
            if deal.entry != mt5.DEAL_ENTRY_OUT:
                continue
            if deal.magic != MAGIC_NUMBER:
                continue

            # Check if this deal's position is in our DB as still open
            position_id = deal.position_id
            if position_id not in ticket_to_trade:
                continue

            trade = ticket_to_trade[position_id]
            trade_id = trade["id"]

            # Get full close info using existing method
            close_info = self.mt5.get_position_close_info(position_id)
            if close_info:
                total_profit = (
                    close_info["profit"]
                    + close_info.get("swap", 0)
                    + close_info.get("commission", 0)
                )
                self.db.close_trade(
                    trade_id=trade_id,
                    close_price=close_info["close_price"],
                    profit=total_profit,
                )
                logger.info(
                    f"Synced historical close: trade={trade_id}, "
                    f"ticket={position_id}, profit={total_profit:.2f}"
                )
            else:
                # Fallback to estimation
                est_close, est_profit = self._estimate_close_values(trade)
                self.db.close_trade(
                    trade_id=trade_id,
                    close_price=est_close,
                    profit=est_profit,
                )
                logger.warning(
                    f"Synced with estimation: trade={trade_id}, "
                    f"ticket={position_id}, est_profit={est_profit:.2f}"
                )

            synced += 1
            # Remove from lookup to avoid reprocessing
            del ticket_to_trade[position_id]

        logger.info(f"Historical sync complete: {synced} trades updated")
        return {"synced_count": synced, "errors": errors}


# Lazy singleton
_trailing_manager: Optional[TrailingStopManager] = None


def get_trailing_manager() -> TrailingStopManager:
    """Get or create trailing stop manager singleton."""
    global _trailing_manager
    if _trailing_manager is None:
        _trailing_manager = TrailingStopManager()
    return _trailing_manager
