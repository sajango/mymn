"""Real-time drawdown tracking per instruction_v4 Section 8.7.

Tracks:
- Daily P&L and trade count (3% max loss, 5 trades max)
- Weekly P&L (6% max loss)
- Monthly drawdown from peak (10% max)
- Consecutive losses (3 → pause 4 hours)
- Recovery mode (5% drawdown → 0.5x position)
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from src.config import get_settings
from src.database import Database, get_database

logger = logging.getLogger(__name__)


class DrawdownStatus(str, Enum):
    """Drawdown tracking status."""

    NORMAL = "normal"
    RECOVERY = "recovery"
    HIGH_ALERT = "high_alert"
    PAUSED = "paused"


@dataclass
class DrawdownCheckResult:
    """Result of drawdown validation."""

    trading_allowed: bool
    status: DrawdownStatus
    position_size_modifier: float
    pause_reason: Optional[str] = None
    limits_remaining: dict = field(default_factory=dict)


class DrawdownManager:
    """Real-time drawdown tracking and enforcement.

    Limits (from instruction_v4 Section 8.7):
    - Daily: 3% max loss, 5 trades, 3 consecutive losses
    - Weekly: 6% max loss
    - Monthly: 10% max drawdown from peak
    - Recovery mode: 5% drawdown → 0.5x position
    """

    def __init__(self, db: Optional[Database] = None, settings=None):
        self._db = db
        self._settings = settings

    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = get_database()
        return self._db

    @property
    def config(self):
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    @property
    def recovery_threshold(self) -> float:
        """Recovery mode threshold as percentage (default 5%)."""
        return getattr(self.config, "recovery_mode_threshold", 5.0)

    def validate(self, account_balance: float) -> DrawdownCheckResult:
        """Check if trading is allowed based on drawdown limits.

        Args:
            account_balance: Current account balance

        Returns:
            DrawdownCheckResult with trading status and position modifier
        """
        if account_balance <= 0:
            return DrawdownCheckResult(
                trading_allowed=False,
                status=DrawdownStatus.PAUSED,
                position_size_modifier=0,
                pause_reason="INVALID_BALANCE: Account balance is zero or negative",
            )

        state = self._get_or_create_state(account_balance)

        # Run limit checks in priority order
        checks = [
            self._check_consecutive_losses,
            self._check_daily_limit,
            self._check_daily_trades,
            self._check_weekly_limit,
            self._check_monthly_drawdown,
        ]

        for check in checks:
            result = check(state, account_balance)
            if not result.trading_allowed:
                self._update_pause_state(state, result)
                return result

        # All checks passed - calculate position modifier
        modifier = self._get_position_modifier(state, account_balance)
        status = self._get_status(state, account_balance)

        return DrawdownCheckResult(
            trading_allowed=True,
            status=status,
            position_size_modifier=modifier,
            limits_remaining=self._get_limits_remaining(state, account_balance),
        )

    def record_trade_result(self, pnl: float, is_win: bool, balance: float):
        """Record trade result and update state.

        Args:
            pnl: Profit/loss amount in account currency
            is_win: Whether trade was profitable
            balance: Current account balance after trade
        """
        state = self._get_or_create_state(balance)

        # Update P&L
        state["daily_pnl"] = state.get("daily_pnl", 0) + pnl
        state["weekly_pnl"] = state.get("weekly_pnl", 0) + pnl

        # Update trade count
        state["daily_trades"] = state.get("daily_trades", 0) + 1
        state["weekly_trades"] = state.get("weekly_trades", 0) + 1

        # Update consecutive losses
        if is_win:
            state["consecutive_losses"] = 0
        else:
            state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1

        # Update peak balance
        if balance > state.get("peak_balance", 0):
            state["peak_balance"] = balance

        # Clear pause if conditions improve
        if state.get("trading_paused"):
            # Re-validate to check if pause should be lifted
            result = self.validate(balance)
            if result.trading_allowed:
                state["trading_paused"] = 0
                state["pause_reason"] = None

        self._save_state(state)
        logger.info(
            f"Trade recorded: pnl={pnl:.2f}, win={is_win}, "
            f"daily_pnl={state['daily_pnl']:.2f}, "
            f"consecutive_losses={state['consecutive_losses']}"
        )

    def reset_daily(self, current_balance: float):
        """Reset daily counters. Call at start of trading day.

        Args:
            current_balance: Current account balance
        """
        state = self._get_or_create_state(current_balance)
        state["daily_start_balance"] = current_balance
        state["daily_pnl"] = 0
        state["daily_trades"] = 0
        state["consecutive_losses"] = 0
        state["trading_paused"] = 0
        state["pause_reason"] = None
        state["date"] = date.today().isoformat()
        self._save_state(state)
        logger.info(f"Daily reset: balance={current_balance:.2f}")

    def reset_weekly(self, current_balance: float):
        """Reset weekly counters. Call at start of trading week.

        Args:
            current_balance: Current account balance
        """
        state = self._get_or_create_state(current_balance)
        state["weekly_start_balance"] = current_balance
        state["weekly_pnl"] = 0
        state["weekly_trades"] = 0
        self._save_state(state)
        logger.info(f"Weekly reset: balance={current_balance:.2f}")

    def get_status_summary(self) -> dict:
        """Get current drawdown status summary.

        Returns:
            Dict with current limits and status
        """
        state = self.db.get_latest_drawdown_state()
        if not state:
            return {"status": "no_data"}

        return {
            "date": state["date"],
            "daily_pnl": state["daily_pnl"],
            "daily_trades": state["daily_trades"],
            "weekly_pnl": state["weekly_pnl"],
            "consecutive_losses": state["consecutive_losses"],
            "trading_paused": bool(state["trading_paused"]),
            "pause_reason": state["pause_reason"],
            "peak_balance": state["peak_balance"],
        }

    # Private helper methods

    def _get_or_create_state(self, balance: float) -> dict:
        """Get existing state for today or create new one."""
        today = date.today().isoformat()
        state = self.db.get_drawdown_state(today)

        if state:
            return dict(state)

        # Check for previous state to carry over peak balance
        prev_state = self.db.get_latest_drawdown_state()
        peak = prev_state["peak_balance"] if prev_state else balance
        weekly_start = prev_state["weekly_start_balance"] if prev_state else balance
        weekly_pnl = prev_state["weekly_pnl"] if prev_state else 0
        weekly_trades = prev_state["weekly_trades"] if prev_state else 0

        # Check if new week (Monday)
        if datetime.now(timezone.utc).weekday() == 0:
            weekly_start = balance
            weekly_pnl = 0
            weekly_trades = 0

        new_state = {
            "date": today,
            "daily_start_balance": balance,
            "daily_pnl": 0,
            "daily_trades": 0,
            "weekly_start_balance": weekly_start,
            "weekly_pnl": weekly_pnl,
            "weekly_trades": weekly_trades,
            "peak_balance": max(peak, balance),
            "consecutive_losses": 0,
            "recovery_mode": 0,
            "trading_paused": 0,
            "pause_reason": None,
        }

        self._save_state(new_state)
        logger.info(f"Created new drawdown state for {today}")
        return new_state

    def _save_state(self, state: dict):
        """Save state to database."""
        self.db.save_drawdown_state(state)

    def _update_pause_state(self, state: dict, result: DrawdownCheckResult):
        """Update state when trading is paused."""
        state["trading_paused"] = 1
        state["pause_reason"] = result.pause_reason
        self._save_state(state)
        logger.warning(f"Trading paused: {result.pause_reason}")

    def _check_consecutive_losses(
        self, state: dict, balance: float
    ) -> DrawdownCheckResult:
        """Check consecutive losses limit (3 → pause)."""
        limit = getattr(self.config, "consecutive_loss_limit", 3)
        if state.get("consecutive_losses", 0) >= limit:
            return DrawdownCheckResult(
                trading_allowed=False,
                status=DrawdownStatus.PAUSED,
                position_size_modifier=0,
                pause_reason=(
                    f"CONSECUTIVE_LOSSES: {state['consecutive_losses']} "
                    f"losses in a row (limit {limit})"
                ),
            )
        return DrawdownCheckResult(
            trading_allowed=True,
            status=DrawdownStatus.NORMAL,
            position_size_modifier=1.0,
        )

    def _check_daily_limit(self, state: dict, balance: float) -> DrawdownCheckResult:
        """Check daily loss limit (3% max)."""
        limit = getattr(self.config, "daily_max_loss_percent", 3.0)
        start_balance = state.get("daily_start_balance", balance)
        if start_balance <= 0:
            return DrawdownCheckResult(
                trading_allowed=True,
                status=DrawdownStatus.NORMAL,
                position_size_modifier=1.0,
            )

        daily_loss_pct = (state.get("daily_pnl", 0) / start_balance) * 100

        if daily_loss_pct <= -limit:
            return DrawdownCheckResult(
                trading_allowed=False,
                status=DrawdownStatus.PAUSED,
                position_size_modifier=0,
                pause_reason=(
                    f"DAILY_LIMIT: {daily_loss_pct:.2f}% loss today "
                    f"(limit -{limit}%)"
                ),
            )
        return DrawdownCheckResult(
            trading_allowed=True,
            status=DrawdownStatus.NORMAL,
            position_size_modifier=1.0,
        )

    def _check_daily_trades(self, state: dict, balance: float) -> DrawdownCheckResult:
        """Check daily trade count limit (5 max)."""
        limit = getattr(self.config, "daily_max_trades", 5)
        trades = state.get("daily_trades", 0)

        if trades >= limit:
            return DrawdownCheckResult(
                trading_allowed=False,
                status=DrawdownStatus.PAUSED,
                position_size_modifier=0,
                pause_reason=f"DAILY_TRADES: {trades} trades today (limit {limit})",
            )
        return DrawdownCheckResult(
            trading_allowed=True,
            status=DrawdownStatus.NORMAL,
            position_size_modifier=1.0,
        )

    def _check_weekly_limit(self, state: dict, balance: float) -> DrawdownCheckResult:
        """Check weekly loss limit (6% max)."""
        limit = getattr(self.config, "weekly_max_loss_percent", 6.0)
        start_balance = state.get("weekly_start_balance", balance)
        if start_balance <= 0:
            return DrawdownCheckResult(
                trading_allowed=True,
                status=DrawdownStatus.NORMAL,
                position_size_modifier=1.0,
            )

        weekly_loss_pct = (state.get("weekly_pnl", 0) / start_balance) * 100

        if weekly_loss_pct <= -limit:
            return DrawdownCheckResult(
                trading_allowed=False,
                status=DrawdownStatus.PAUSED,
                position_size_modifier=0,
                pause_reason=(
                    f"WEEKLY_LIMIT: {weekly_loss_pct:.2f}% loss this week "
                    f"(limit -{limit}%)"
                ),
            )
        return DrawdownCheckResult(
            trading_allowed=True,
            status=DrawdownStatus.NORMAL,
            position_size_modifier=1.0,
        )

    def _check_monthly_drawdown(
        self, state: dict, balance: float
    ) -> DrawdownCheckResult:
        """Check monthly drawdown from peak (10% max)."""
        limit = getattr(self.config, "monthly_max_drawdown_percent", 10.0)
        peak = state.get("peak_balance", balance)
        if peak <= 0:
            return DrawdownCheckResult(
                trading_allowed=True,
                status=DrawdownStatus.NORMAL,
                position_size_modifier=1.0,
            )

        drawdown_pct = ((peak - balance) / peak) * 100

        if drawdown_pct >= limit:
            return DrawdownCheckResult(
                trading_allowed=False,
                status=DrawdownStatus.PAUSED,
                position_size_modifier=0,
                pause_reason=(
                    f"MAX_DRAWDOWN: {drawdown_pct:.2f}% from peak "
                    f"(limit {limit}%)"
                ),
            )
        return DrawdownCheckResult(
            trading_allowed=True,
            status=DrawdownStatus.NORMAL,
            position_size_modifier=1.0,
        )

    def _get_position_modifier(self, state: dict, balance: float) -> float:
        """Calculate position size modifier based on risk state."""
        peak = state.get("peak_balance", balance)
        recovery_threshold = self.recovery_threshold

        # Drawdown from peak
        if peak > 0:
            drawdown_pct = ((peak - balance) / peak) * 100
            if drawdown_pct >= recovery_threshold:
                return 0.5  # Recovery mode

        # After 2 consecutive losses
        losses = state.get("consecutive_losses", 0)
        if losses == 2:
            return 0.5
        if losses == 1:
            return 0.75

        # Approaching daily limit (>70% of 3% = 2.1%)
        start_balance = state.get("daily_start_balance", balance)
        if start_balance > 0:
            daily_loss_pct = abs(state.get("daily_pnl", 0) / start_balance) * 100
            daily_limit = getattr(self.config, "daily_max_loss_percent", 3.0)
            if daily_loss_pct > daily_limit * 0.7:
                return 0.5

        return 1.0

    def _get_status(self, state: dict, balance: float) -> DrawdownStatus:
        """Determine current drawdown status."""
        peak = state.get("peak_balance", balance)
        recovery_threshold = self.recovery_threshold

        if peak > 0:
            drawdown_pct = ((peak - balance) / peak) * 100
            if drawdown_pct >= recovery_threshold:
                return DrawdownStatus.RECOVERY

        losses = state.get("consecutive_losses", 0)
        if losses >= 2:
            return DrawdownStatus.HIGH_ALERT

        start_balance = state.get("daily_start_balance", balance)
        if start_balance > 0:
            daily_loss_pct = abs(state.get("daily_pnl", 0) / start_balance) * 100
            daily_limit = getattr(self.config, "daily_max_loss_percent", 3.0)
            if daily_loss_pct > daily_limit * 0.5:
                return DrawdownStatus.HIGH_ALERT

        return DrawdownStatus.NORMAL

    def _get_limits_remaining(self, state: dict, balance: float) -> dict:
        """Calculate remaining limits before pause."""
        daily_limit = getattr(self.config, "daily_max_loss_percent", 3.0)
        weekly_limit = getattr(self.config, "weekly_max_loss_percent", 6.0)
        daily_trades_limit = getattr(self.config, "daily_max_trades", 5)
        loss_limit = getattr(self.config, "consecutive_loss_limit", 3)

        start_daily = state.get("daily_start_balance", balance)
        start_weekly = state.get("weekly_start_balance", balance)

        daily_remaining = daily_limit + (
            (state.get("daily_pnl", 0) / start_daily) * 100 if start_daily > 0 else 0
        )
        weekly_remaining = weekly_limit + (
            (state.get("weekly_pnl", 0) / start_weekly) * 100
            if start_weekly > 0
            else 0
        )

        return {
            "daily_loss_remaining_pct": max(0, daily_remaining),
            "weekly_loss_remaining_pct": max(0, weekly_remaining),
            "daily_trades_remaining": max(
                0, daily_trades_limit - state.get("daily_trades", 0)
            ),
            "consecutive_losses_remaining": max(
                0, loss_limit - state.get("consecutive_losses", 0)
            ),
        }


# Lazy singleton
_drawdown_manager: Optional[DrawdownManager] = None


def get_drawdown_manager() -> DrawdownManager:
    """Get or create DrawdownManager singleton."""
    global _drawdown_manager
    if _drawdown_manager is None:
        _drawdown_manager = DrawdownManager()
    return _drawdown_manager
