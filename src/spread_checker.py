"""Spread validation for trade entry decisions.

Checks current spread against MAX_SPREAD_PIPS threshold.
Provides spread-adjusted entry/TP prices when requested.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from src.config import get_settings
from src.mt5_client import MT5Client, mt5_client

logger = logging.getLogger(__name__)


@dataclass
class SpreadCheckResult:
    """Spread validation result."""

    current_spread_pips: float
    max_allowed_pips: float
    spread_ok: bool
    adjusted_entry: Optional[float] = None
    adjusted_tp1: Optional[float] = None
    message: str = ""


class SpreadChecker:
    """Validates spread before trade entry.

    Uses MT5 to get current spread and compares against
    MAX_SPREAD_PIPS threshold from config.
    """

    def __init__(
        self,
        mt5: Optional[MT5Client] = None,
        settings=None,
    ):
        self._mt5 = mt5
        self._settings = settings

    @property
    def mt5(self) -> MT5Client:
        """Lazy load MT5 client."""
        if self._mt5 is None:
            self._mt5 = mt5_client
        return self._mt5

    @property
    def settings(self):
        """Lazy load settings."""
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    def check_spread(
        self,
        symbol: Optional[str] = None,
        entry_price: Optional[float] = None,
        is_buy: bool = True,
    ) -> SpreadCheckResult:
        """Check if current spread is acceptable for trading.

        Args:
            symbol: Trading symbol (defaults to config)
            entry_price: Proposed entry price for adjustment
            is_buy: True for buy, False for sell

        Returns:
            SpreadCheckResult with validation details
        """
        symbol = symbol or self.settings.mt5_symbol
        max_spread = self.settings.max_spread_pips

        # Get current spread
        current_spread = self.mt5.get_current_spread(symbol)

        if current_spread is None:
            logger.warning(f"Could not get spread for {symbol}")
            return SpreadCheckResult(
                current_spread_pips=0,
                max_allowed_pips=max_spread,
                spread_ok=False,
                message="Unable to get spread from MT5",
            )

        spread_ok = current_spread <= max_spread

        # Calculate adjusted prices if entry provided
        adjusted_entry = None
        adjusted_tp1 = None

        if entry_price and not spread_ok:
            # Adjust for spread impact
            # XAUUSD: 1 pip = 0.1 price units (e.g., 2 pips = 0.2 price change)
            pip_size = 0.1  # XAUUSD pip size
            spread_adjustment = current_spread * pip_size

            if is_buy:
                adjusted_entry = entry_price + spread_adjustment
            else:
                adjusted_entry = entry_price - spread_adjustment

        message = ""
        if not spread_ok:
            message = f"Spread {current_spread:.1f} > max {max_spread:.1f} pips"
            logger.info(f"Spread check failed: {message}")
        else:
            logger.debug(f"Spread OK: {current_spread:.1f} <= {max_spread:.1f} pips")

        return SpreadCheckResult(
            current_spread_pips=current_spread,
            max_allowed_pips=max_spread,
            spread_ok=spread_ok,
            adjusted_entry=adjusted_entry,
            adjusted_tp1=adjusted_tp1,
            message=message,
        )

    def is_spread_ok(self, symbol: Optional[str] = None) -> bool:
        """Simple spread check - just returns True/False.

        Args:
            symbol: Trading symbol (defaults to config)

        Returns:
            True if spread is acceptable
        """
        result = self.check_spread(symbol)
        return result.spread_ok


# Lazy singleton
_spread_checker: Optional[SpreadChecker] = None


def get_spread_checker() -> SpreadChecker:
    """Get or create spread checker singleton."""
    global _spread_checker
    if _spread_checker is None:
        _spread_checker = SpreadChecker()
    return _spread_checker
