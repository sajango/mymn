"""Risk Guard - Pre-execution validation for trading signals.

Validates signals before execution to prevent:
- Duplicate orders within cooldown period
- Direction conflicts (hedged positions)
- Position accumulation beyond limits
- Account risk over-exposure

All checks must pass before signal proceeds to TradeExecutor.
"""

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.config import get_settings
from src.database import Database, get_database
from src.mt5_client import MT5Client, mt5_client
from src.signal_parser import TradingSignal

logger = logging.getLogger(__name__)


class RiskCheckReason(str, Enum):
    """Risk check rejection reasons."""

    DUPLICATE_SIGNAL = "duplicate_signal"
    MAX_POSITIONS_REACHED = "max_positions_reached"
    MAX_LOTS_EXCEEDED = "max_lots_exceeded"
    ACCOUNT_RISK_EXCEEDED = "account_risk_exceeded"
    OPPOSITE_POSITION_EXISTS = "opposite_position_exists"
    CLOSE_FAILED = "close_failed"
    MT5_DISCONNECTED = "mt5_disconnected"


@dataclass
class RiskCheckResult:
    """Result of a risk validation check."""

    passed: bool
    reason: Optional[RiskCheckReason] = None
    message: str = ""
    action_taken: str = ""  # e.g., "closed_position_1234"


class RiskGuard:
    """Pre-execution risk validation for trading signals.

    Validates:
    - Duplicate signal detection via content hashing
    - Concurrent position limits
    - Total lot exposure limits
    - Direction conflict handling (close-first policy)
    - Account risk percentage limits

    Usage:
        guard = get_risk_guard()
        result = await guard.validate(signal)
        if not result.passed:
            logger.warning(f"Rejected: {result.reason}")
    """

    MAGIC_NUMBER = 123456  # Same as TradeExecutor

    def __init__(
        self,
        mt5: Optional[MT5Client] = None,
        db: Optional[Database] = None,
        settings=None,
    ):
        self._mt5 = mt5
        self._db = db
        self._settings = settings
        # In-memory hash cache as fallback
        self._hash_cache: set[str] = set()

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
    def config(self):
        """Lazy load settings."""
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def validate(self, signal: TradingSignal) -> RiskCheckResult:
        """Run all risk checks on signal.

        Args:
            signal: Trading signal to validate

        Returns:
            RiskCheckResult with pass/fail and reason
        """
        logger.info(f"[RiskGuard] Validating signal: {signal.signal.action.value}")

        # Check MT5 connection first
        if not self.mt5.is_connected():
            logger.error("[RiskGuard] MT5 not connected")
            return RiskCheckResult(
                passed=False,
                reason=RiskCheckReason.MT5_DISCONNECTED,
                message="MT5 not connected, cannot validate positions",
            )

        # Run checks in order of importance
        checks = [
            ("duplicate", self._check_duplicate),
            ("direction_conflict", self._check_direction_conflict),
            ("exposure_limits", self._check_exposure_limits),
            ("account_risk", self._check_account_risk),
        ]

        for check_name, check_fn in checks:
            result = check_fn(signal)
            if not result.passed:
                logger.warning(
                    f"[RiskGuard] FAILED: {check_name} - {result.reason.value}"
                )
                return result
            logger.info(f"[RiskGuard] PASSED: {check_name}")

        logger.info("[RiskGuard] All checks passed")
        return RiskCheckResult(passed=True)

    def _generate_signal_hash(self, signal: TradingSignal) -> str:
        """Generate hash from signal content for deduplication.

        Args:
            signal: Trading signal

        Returns:
            16-character hash string
        """
        s = signal.signal
        content = f"{signal.symbol}:{s.action.value}:{s.entry_price}:{s.stop_loss}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _check_duplicate(self, signal: TradingSignal) -> RiskCheckResult:
        """Check if signal is duplicate within cooldown period.

        Args:
            signal: Trading signal

        Returns:
            RiskCheckResult
        """
        signal_hash = self._generate_signal_hash(signal)

        # Check database
        try:
            recent_hashes = self.db.get_recent_signal_hashes(
                minutes=self.config.duplicate_cooldown_minutes
            )
        except Exception as e:
            logger.warning(f"DB lookup failed, using memory cache: {e}")
            recent_hashes = self._hash_cache

        if signal_hash in recent_hashes:
            return RiskCheckResult(
                passed=False,
                reason=RiskCheckReason.DUPLICATE_SIGNAL,
                message=f"Duplicate signal within {self.config.duplicate_cooldown_minutes}min cooldown",
            )

        # Save hash for future checks
        try:
            self.db.save_signal_hash(
                signal_hash, signal.symbol, signal.signal.action.value
            )
        except Exception as e:
            logger.warning(f"Failed to save hash to DB: {e}")

        # Always update memory cache
        self._hash_cache.add(signal_hash)

        return RiskCheckResult(passed=True)

    def _check_direction_conflict(self, signal: TradingSignal) -> RiskCheckResult:
        """Check for and handle opposite direction positions.

        Applies configured policy:
        - reject: Block new signal if opposite exists
        - close_first: Close existing, then allow new
        - hedge: Allow both if within exposure limits

        Args:
            signal: Trading signal

        Returns:
            RiskCheckResult
        """
        positions = self.mt5.get_positions(magic=self.MAGIC_NUMBER)
        symbol = signal.symbol
        is_buy = signal.is_buy

        # Find opposite direction positions for same symbol
        opposite_positions = [
            p for p in positions
            if p["symbol"] == symbol
            and self._is_opposite_direction(p, is_buy)
        ]

        if not opposite_positions:
            return RiskCheckResult(passed=True)

        # Apply policy
        policy = self.config.opposite_position_policy

        if policy == "reject":
            return RiskCheckResult(
                passed=False,
                reason=RiskCheckReason.OPPOSITE_POSITION_EXISTS,
                message=f"Opposite position exists (policy=reject), "
                        f"tickets: {[p['ticket'] for p in opposite_positions]}",
            )

        elif policy == "close_first":
            return self._handle_close_first(opposite_positions, signal)

        elif policy == "hedge":
            # Hedge allowed - will be checked by exposure limits
            logger.info(
                f"[RiskGuard] Hedging allowed, opposite positions: "
                f"{[p['ticket'] for p in opposite_positions]}"
            )
            return RiskCheckResult(passed=True)

        # Unknown policy - safe default
        return RiskCheckResult(
            passed=False,
            reason=RiskCheckReason.OPPOSITE_POSITION_EXISTS,
            message=f"Unknown policy: {policy}",
        )

    def _is_opposite_direction(self, position: dict, is_buy: bool) -> bool:
        """Check if position is opposite direction to signal.

        Args:
            position: Position dict from MT5
            is_buy: True if signal is BUY direction

        Returns:
            True if opposite direction
        """
        # MT5 position type: 0 = BUY, 1 = SELL
        pos_is_buy = position["type"] == 0
        return pos_is_buy != is_buy

    def _handle_close_first(
        self, opposite_positions: list[dict], signal: TradingSignal
    ) -> RiskCheckResult:
        """Close opposite positions before allowing new signal.

        Args:
            opposite_positions: List of positions to close
            signal: New trading signal

        Returns:
            RiskCheckResult
        """
        closed_tickets = []

        for pos in opposite_positions:
            ticket = pos["ticket"]
            logger.info(f"[RiskGuard] Closing opposite position: {ticket}")

            success = self.mt5.close_position(ticket)

            if not success:
                logger.error(f"[RiskGuard] Failed to close position: {ticket}")
                return RiskCheckResult(
                    passed=False,
                    reason=RiskCheckReason.CLOSE_FAILED,
                    message=f"Failed to close position {ticket} for reversal",
                )

            closed_tickets.append(ticket)
            logger.info(f"[RiskGuard] Closed position: {ticket}")

        return RiskCheckResult(
            passed=True,
            action_taken=f"closed_positions:{closed_tickets}",
        )

    def _check_exposure_limits(self, signal: TradingSignal) -> RiskCheckResult:
        """Check concurrent positions and total lot exposure.

        Args:
            signal: Trading signal

        Returns:
            RiskCheckResult
        """
        positions = self.mt5.get_positions(magic=self.MAGIC_NUMBER)

        # Check position count
        if len(positions) >= self.config.max_concurrent_positions:
            return RiskCheckResult(
                passed=False,
                reason=RiskCheckReason.MAX_POSITIONS_REACHED,
                message=f"Max {self.config.max_concurrent_positions} positions reached "
                        f"(current: {len(positions)})",
            )

        # Check total lots
        total_lots = sum(p["volume"] for p in positions)
        # Estimate new position volume (use max as conservative estimate)
        proposed_volume = min(
            self.config.max_position_size,
            self.config.fixed_lot_size if self.config.use_fixed_lots else 0.1,
        )
        proposed_total = total_lots + proposed_volume

        if proposed_total > self.config.max_total_lots:
            return RiskCheckResult(
                passed=False,
                reason=RiskCheckReason.MAX_LOTS_EXCEEDED,
                message=f"Total lots {proposed_total:.2f} would exceed max "
                        f"{self.config.max_total_lots}",
            )

        return RiskCheckResult(passed=True)

    def _check_account_risk(self, signal: TradingSignal) -> RiskCheckResult:
        """Check total account risk exposure.

        Args:
            signal: Trading signal

        Returns:
            RiskCheckResult
        """
        positions = self.mt5.get_positions(magic=self.MAGIC_NUMBER)
        account = self.mt5.get_account_info()

        if account is None:
            logger.warning("[RiskGuard] Could not get account info, skipping risk check")
            return RiskCheckResult(passed=True)

        balance = account.get("balance", 0)
        if balance <= 0:
            return RiskCheckResult(passed=True)

        # Calculate current risk from open positions
        current_risk_pct = 0.0
        for pos in positions:
            pos_risk = self._calculate_position_risk(pos, balance)
            current_risk_pct += pos_risk

        # Add proposed trade risk
        proposed_risk = self.config.risk_percent
        total_risk = current_risk_pct + proposed_risk

        if total_risk > self.config.max_account_risk_percent:
            return RiskCheckResult(
                passed=False,
                reason=RiskCheckReason.ACCOUNT_RISK_EXCEEDED,
                message=f"Total risk {total_risk:.1f}% would exceed max "
                        f"{self.config.max_account_risk_percent}%",
            )

        return RiskCheckResult(passed=True)

    def _calculate_position_risk(self, position: dict, balance: float) -> float:
        """Calculate risk percentage for a single position.

        Approximates risk based on SL distance and position size.

        Args:
            position: Position dict from MT5
            balance: Account balance

        Returns:
            Risk percentage for this position
        """
        if balance <= 0:
            return 0.0

        volume = position.get("volume", 0)
        sl = position.get("sl", 0)
        entry = position.get("open_price", 0)

        if sl == 0 or entry == 0:
            # No SL set, assume max risk
            return self.config.risk_percent

        # SL distance in price
        sl_distance = abs(entry - sl)

        # Approximate pip value for XAUUSD: $1 per pip per 0.01 lots
        # 0.1 lots = $10/pip
        pip_value = volume * 100  # Rough estimate

        # Risk in dollars
        risk_dollars = sl_distance * pip_value

        # Risk as percentage
        risk_pct = (risk_dollars / balance) * 100

        return min(risk_pct, self.config.risk_percent)  # Cap at configured risk


# Lazy singleton
_risk_guard: Optional[RiskGuard] = None


def get_risk_guard() -> RiskGuard:
    """Get or create RiskGuard singleton."""
    global _risk_guard
    if _risk_guard is None:
        _risk_guard = RiskGuard()
    return _risk_guard
