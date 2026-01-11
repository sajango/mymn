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
    TOO_CLOSE_TO_KEY_LEVEL = "too_close_to_key_level"
    DRAWDOWN_LIMIT_EXCEEDED = "drawdown_limit_exceeded"
    PORTFOLIO_HEAT_EXCEEDED = "portfolio_heat_exceeded"
    CORRELATION_RISK_HIGH = "correlation_risk_high"


@dataclass
class RiskCheckResult:
    """Result of a risk validation check."""

    passed: bool
    reason: Optional[RiskCheckReason] = None
    message: str = ""
    action_taken: str = ""  # e.g., "closed_position_1234"
    position_size_modifier: float = 1.0  # Multiplier from drawdown manager


class RiskGuard:
    """Pre-execution risk validation for trading signals.

    Validates:
    - Duplicate signal detection via content hashing
    - Concurrent position limits
    - Total lot exposure limits
    - Direction conflict handling (close-first policy)
    - Account risk percentage limits
    - Drawdown limits (daily/weekly/monthly)

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
        drawdown_manager=None,
    ):
        self._mt5 = mt5
        self._db = db
        self._settings = settings
        self._drawdown_manager = drawdown_manager
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

    @property
    def drawdown_manager(self):
        """Lazy load drawdown manager."""
        if self._drawdown_manager is None:
            from src.drawdown_manager import get_drawdown_manager
            self._drawdown_manager = get_drawdown_manager()
        return self._drawdown_manager

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

        # Check drawdown limits first (highest priority risk check)
        account = self.mt5.get_account_info()
        account_balance = account.get("balance", 0) if account else 0
        position_modifier = 1.0

        if self.config.enable_drawdown_check and account_balance > 0:
            dd_result = self.drawdown_manager.validate(account_balance)
            if not dd_result.trading_allowed:
                logger.warning(
                    f"[RiskGuard] FAILED: drawdown_check - {dd_result.pause_reason}"
                )
                return RiskCheckResult(
                    passed=False,
                    reason=RiskCheckReason.DRAWDOWN_LIMIT_EXCEEDED,
                    message=dd_result.pause_reason or "Drawdown limit exceeded",
                )
            position_modifier = dd_result.position_size_modifier
            logger.info(
                f"[RiskGuard] PASSED: drawdown_check (modifier={position_modifier})"
            )
        elif not self.config.enable_drawdown_check:
            logger.warning("[RiskGuard] SKIPPED: drawdown_check (disabled in config)")

        # Run checks in order of importance
        checks = [
            ("duplicate", self._check_duplicate),
            ("direction_conflict", self._check_direction_conflict),
            ("key_level_proximity", self._check_key_level_proximity),
            ("portfolio_risk", self._check_portfolio_risk),
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
        return RiskCheckResult(passed=True, position_size_modifier=position_modifier)

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

    def _extract_key_levels(
        self, signal: TradingSignal
    ) -> tuple[list[float], list[float]]:
        """Extract key levels from signal for proximity validation.

        Args:
            signal: Trading signal with wave analysis and TPs

        Returns:
            Tuple of (resistance_levels, support_levels)
        """
        resistance_levels: list[float] = []
        support_levels: list[float] = []

        s = signal.signal
        entry = s.entry_price
        is_buy = signal.is_buy

        if entry is None:
            return resistance_levels, support_levels

        # Take profit levels based on position relative to entry
        if s.take_profit:
            for tp in s.take_profit:
                if tp.price > entry:
                    resistance_levels.append(tp.price)
                else:
                    support_levels.append(tp.price)

        # Wave invalidation price
        if signal.wave_analysis and signal.wave_analysis.invalidation_price:
            inv_price = signal.wave_analysis.invalidation_price
            if inv_price < entry:
                support_levels.append(inv_price)
            else:
                resistance_levels.append(inv_price)

        # Stop loss is a key level (support for BUY, resistance for SELL)
        if s.stop_loss:
            if is_buy:
                support_levels.append(s.stop_loss)
            else:
                resistance_levels.append(s.stop_loss)

        # Deduplicate and sort
        resistance_levels = sorted(set(resistance_levels))
        support_levels = sorted(set(support_levels), reverse=True)  # Descending

        return resistance_levels, support_levels

    def _check_key_level_proximity(self, signal: TradingSignal) -> RiskCheckResult:
        """Check if entry is too close to conflicting key level.

        Validates that:
        - BUY orders have sufficient distance to nearest resistance
        - SELL orders have sufficient distance to nearest support

        Distance threshold = max(min_pips, ATR × multiplier)

        Args:
            signal: Trading signal

        Returns:
            RiskCheckResult
        """
        # Check if feature enabled
        if not self.config.key_level_proximity_enabled:
            return RiskCheckResult(passed=True)

        s = signal.signal
        entry = s.entry_price

        # Skip if no entry price
        if entry is None:
            return RiskCheckResult(passed=True)

        # Extract key levels
        resistance_levels, support_levels = self._extract_key_levels(signal)

        # Calculate safe distance
        min_safe_distance = self._calculate_safe_distance(signal)

        # Validate based on direction
        if signal.is_buy:
            # Check distance to nearest resistance
            nearest_resistance = self._find_nearest_level_above(entry, resistance_levels)
            if nearest_resistance is not None:
                distance = nearest_resistance - entry
                if distance < min_safe_distance:
                    return RiskCheckResult(
                        passed=False,
                        reason=RiskCheckReason.TOO_CLOSE_TO_KEY_LEVEL,
                        message=(
                            f"BUY too close to resistance: "
                            f"entry={entry:.2f}, resistance={nearest_resistance:.2f}, "
                            f"distance={distance:.2f}, required={min_safe_distance:.2f}"
                        ),
                    )
        else:  # SELL
            # Check distance to nearest support
            nearest_support = self._find_nearest_level_below(entry, support_levels)
            if nearest_support is not None:
                distance = entry - nearest_support
                if distance < min_safe_distance:
                    return RiskCheckResult(
                        passed=False,
                        reason=RiskCheckReason.TOO_CLOSE_TO_KEY_LEVEL,
                        message=(
                            f"SELL too close to support: "
                            f"entry={entry:.2f}, support={nearest_support:.2f}, "
                            f"distance={distance:.2f}, required={min_safe_distance:.2f}"
                        ),
                    )

        return RiskCheckResult(passed=True)

    def _calculate_safe_distance(self, signal: TradingSignal) -> float:
        """Calculate minimum safe distance from key levels.

        Returns max of:
        - Fixed minimum pips converted to price
        - ATR × multiplier (if ATR available)

        Args:
            signal: Trading signal with indicators

        Returns:
            Minimum safe distance in price units
        """
        # Fixed minimum (pips to price for XAUUSD: 1 pip = 0.1)
        pip_size = 0.1  # XAUUSD pip size
        min_distance = self.config.key_level_proximity_min_pips * pip_size

        # ATR-based distance (if available)
        if signal.indicators and signal.indicators.atr:
            atr_value = signal.indicators.atr.value
            atr_distance = atr_value * self.config.key_level_proximity_atr_multiplier
            min_distance = max(min_distance, atr_distance)

        return min_distance

    def _find_nearest_level_above(
        self, price: float, levels: list[float]
    ) -> Optional[float]:
        """Find nearest level above given price.

        Args:
            price: Reference price
            levels: Sorted list of levels (ascending)

        Returns:
            Nearest level above price, or None if none exist
        """
        for level in levels:
            if level > price:
                return level
        return None

    def _find_nearest_level_below(
        self, price: float, levels: list[float]
    ) -> Optional[float]:
        """Find nearest level below given price.

        Args:
            price: Reference price
            levels: Sorted list of levels (descending)

        Returns:
            Nearest level below price, or None if none exist
        """
        for level in levels:
            if level < price:
                return level
        return None

    def _check_portfolio_risk(self, signal: TradingSignal) -> RiskCheckResult:
        """Check portfolio-level risk constraints.
        
        Uses PortfolioRiskManager to validate:
        - Total portfolio heat
        - Correlation risk
        - Position concentration
        - Dynamic risk adjustments
        
        Args:
            signal: Trading signal
            
        Returns:
            RiskCheckResult
        """
        from src.portfolio_risk_manager import get_portfolio_risk_manager
        
        portfolio_manager = get_portfolio_risk_manager()
        
        # Calculate proposed position risk
        account = self.mt5.get_account_info()
        if not account:
            logger.warning("Cannot get account info for portfolio risk check")
            return RiskCheckResult(passed=True)
        
        balance = account.get("balance", 0)
        if balance <= 0:
            return RiskCheckResult(passed=True)
        
        # Estimate risk for proposed position
        s = signal.signal
        if s.entry_price and s.stop_loss:
            # Simplified risk calculation
            sl_distance = abs(s.entry_price - s.stop_loss)
            estimated_volume = 0.05  # Default estimate
            proposed_risk = sl_distance * estimated_volume * 100  # For gold
            
            # Check if position allowed
            allowed, reason = portfolio_manager.check_position_allowed(
                signal.symbol, proposed_risk
            )
            
            if not allowed:
                # Determine specific rejection reason
                if "heat" in reason.lower():
                    return RiskCheckResult(
                        passed=False,
                        reason=RiskCheckReason.PORTFOLIO_HEAT_EXCEEDED,
                        message=reason
                    )
                elif "correlation" in reason.lower():
                    return RiskCheckResult(
                        passed=False,
                        reason=RiskCheckReason.CORRELATION_RISK_HIGH,
                        message=reason
                    )
                else:
                    return RiskCheckResult(
                        passed=False,
                        reason=RiskCheckReason.MAX_POSITIONS_REACHED,
                        message=reason
                    )
        
        # Check if trading should be paused
        should_pause, pause_reason = portfolio_manager.should_pause_trading()
        if should_pause:
            return RiskCheckResult(
                passed=False,
                reason=RiskCheckReason.PORTFOLIO_HEAT_EXCEEDED,
                message=f"Trading paused: {pause_reason}"
            )
        
        # Get dynamic risk adjustment
        risk_adj = portfolio_manager.calculate_dynamic_risk()
        
        # Store adjustment factor for later use
        self._portfolio_risk_adjustment = risk_adj.adjustment_factor
        
        logger.info(
            f"[RiskGuard] Portfolio risk check passed. "
            f"Risk adjustment: {risk_adj.adjustment_factor:.2f}x"
        )
        
        return RiskCheckResult(passed=True)


# Lazy singleton
_risk_guard: Optional[RiskGuard] = None


def get_risk_guard() -> RiskGuard:
    """Get or create RiskGuard singleton."""
    global _risk_guard
    if _risk_guard is None:
        _risk_guard = RiskGuard()
    return _risk_guard
