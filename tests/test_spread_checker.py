"""Tests for spread_checker module (Phase 6).

Tests spread validation for trade entry decisions.
"""

from unittest.mock import MagicMock

import pytest

from src.config import Settings
from src.spread_checker import (
    SpreadCheckResult,
    SpreadChecker,
    get_spread_checker,
)


class TestSpreadCheckResult:
    """Test SpreadCheckResult dataclass."""

    def test_creates_result_spread_ok(self):
        """Verify result creation when spread is acceptable."""
        result = SpreadCheckResult(
            current_spread_pips=2.5,
            max_allowed_pips=4.0,
            spread_ok=True,
            message="Spread OK",
        )
        assert result.current_spread_pips == 2.5
        assert result.max_allowed_pips == 4.0
        assert result.spread_ok is True
        assert result.message == "Spread OK"

    def test_creates_result_spread_not_ok(self):
        """Verify result creation when spread is too high."""
        result = SpreadCheckResult(
            current_spread_pips=5.0,
            max_allowed_pips=4.0,
            spread_ok=False,
            adjusted_entry=1950.5,
            message="Spread 5.0 > max 4.0 pips",
        )
        assert result.current_spread_pips == 5.0
        assert result.max_allowed_pips == 4.0
        assert result.spread_ok is False
        assert result.adjusted_entry == 1950.5
        assert "Spread" in result.message

    def test_result_optional_adjusted_prices(self):
        """Verify adjusted_entry and adjusted_tp1 are optional."""
        result = SpreadCheckResult(
            current_spread_pips=2.0,
            max_allowed_pips=4.0,
            spread_ok=True,
        )
        assert result.adjusted_entry is None
        assert result.adjusted_tp1 is None
        assert result.message == ""


class TestSpreadCheckerInitialization:
    """Test SpreadChecker initialization."""

    def test_initializes_without_dependencies(self):
        """Verify checker initializes with lazy loading."""
        checker = SpreadChecker()
        assert checker._mt5 is None
        assert checker._settings is None

    def test_initializes_with_custom_mt5(self):
        """Verify checker accepts custom MT5 client."""
        mt5_mock = MagicMock()
        checker = SpreadChecker(mt5=mt5_mock)
        assert checker._mt5 == mt5_mock

    def test_initializes_with_custom_settings(self):
        """Verify checker accepts custom settings."""
        settings = Settings()
        checker = SpreadChecker(settings=settings)
        assert checker._settings == settings

    def test_lazy_loads_mt5(self):
        """Verify MT5 client is lazy-loaded on access."""
        checker = SpreadChecker()
        assert checker._mt5 is None
        mt5 = checker.mt5
        # Should return either the mock or the actual client
        assert mt5 is not None

    def test_lazy_loads_settings(self):
        """Verify settings are lazy-loaded on access."""
        checker = SpreadChecker()
        assert checker._settings is None
        settings = checker.settings
        assert settings is not None
        assert isinstance(settings, Settings)


class TestCheckSpread:
    """Test spread validation."""

    def test_spread_ok_when_below_max(self):
        """Verify spread_ok=True when current < max."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 2.0
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(symbol="XAUUSD")

        assert result.spread_ok is True
        assert result.current_spread_pips == 2.0
        assert result.max_allowed_pips == 4.0

    def test_spread_not_ok_when_exceeds_max(self):
        """Verify spread_ok=False when current > max."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 5.0
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(symbol="XAUUSD")

        assert result.spread_ok is False
        assert result.current_spread_pips == 5.0
        assert "Spread" in result.message

    def test_spread_equal_to_max(self):
        """Verify spread_ok=True when current == max."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 4.0
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(symbol="XAUUSD")

        assert result.spread_ok is True

    def test_handles_none_spread(self):
        """Verify graceful handling when spread cannot be obtained."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = None
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(symbol="XAUUSD")

        assert result.spread_ok is False
        assert result.current_spread_pips == 0
        assert "Unable" in result.message

    def test_uses_default_symbol(self):
        """Verify default symbol from settings is used."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 2.0
        settings = Settings(mt5_symbol="XAUUSD", max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread()

        mt5_mock.get_current_spread.assert_called_with("XAUUSD")
        assert result.spread_ok is True

    def test_uses_provided_symbol(self):
        """Verify provided symbol overrides default."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 2.0
        settings = Settings(mt5_symbol="XAUUSD", max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(symbol="EURUSD")

        mt5_mock.get_current_spread.assert_called_with("EURUSD")


class TestAdjustedPrices:
    """Test spread-adjusted entry price calculation."""

    def test_adjusted_entry_for_buy_when_spread_high(self):
        """Verify entry is adjusted upward for buy when spread exceeds max."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 5.0
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(
            symbol="XAUUSD",
            entry_price=1950.0,
            is_buy=True,
        )

        assert result.spread_ok is False
        assert result.adjusted_entry is not None
        # For buy: entry + spread_adjustment
        assert result.adjusted_entry > 1950.0

    def test_adjusted_entry_for_sell_when_spread_high(self):
        """Verify entry is adjusted downward for sell when spread exceeds max."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 5.0
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(
            symbol="XAUUSD",
            entry_price=1950.0,
            is_buy=False,
        )

        assert result.spread_ok is False
        assert result.adjusted_entry is not None
        # For sell: entry - spread_adjustment
        assert result.adjusted_entry < 1950.0

    def test_no_adjustment_when_spread_ok(self):
        """Verify no adjustment when spread is acceptable."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 2.0
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(
            symbol="XAUUSD",
            entry_price=1950.0,
            is_buy=True,
        )

        assert result.spread_ok is True
        assert result.adjusted_entry is None

    def test_no_adjustment_without_entry_price(self):
        """Verify adjustment only occurs with entry_price provided."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 5.0
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(symbol="XAUUSD", entry_price=None)

        assert result.spread_ok is False
        assert result.adjusted_entry is None


class TestIsSpreadOk:
    """Test simple spread check."""

    def test_returns_true_when_spread_acceptable(self):
        """Verify returns True for acceptable spread."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 2.0
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        assert checker.is_spread_ok(symbol="XAUUSD") is True

    def test_returns_false_when_spread_high(self):
        """Verify returns False for high spread."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 5.0
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        assert checker.is_spread_ok(symbol="XAUUSD") is False

    def test_uses_default_symbol(self):
        """Verify default symbol is used."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 2.0
        settings = Settings(mt5_symbol="XAUUSD", max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        assert checker.is_spread_ok() is True

        mt5_mock.get_current_spread.assert_called_with("XAUUSD")


class TestSpreadCheckerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_spread(self):
        """Verify handling of zero spread (ideal case)."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 0.0
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(symbol="XAUUSD")

        assert result.spread_ok is True
        assert result.current_spread_pips == 0.0

    def test_very_high_spread(self):
        """Verify handling of very high spread."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 100.0
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(symbol="XAUUSD")

        assert result.spread_ok is False
        assert result.current_spread_pips == 100.0

    def test_fractional_spreads(self):
        """Verify handling of fractional spreads."""
        mt5_mock = MagicMock()
        mt5_mock.get_current_spread.return_value = 2.7
        settings = Settings(max_spread_pips=4.0)

        checker = SpreadChecker(mt5=mt5_mock, settings=settings)
        result = checker.check_spread(symbol="XAUUSD")

        assert result.spread_ok is True
        assert result.current_spread_pips == 2.7


class TestSpreadCheckerSingleton:
    """Test singleton getter function."""

    def test_returns_singleton_instance(self):
        """Verify get_spread_checker returns singleton."""
        checker1 = get_spread_checker()
        checker2 = get_spread_checker()
        assert checker1 is checker2

    def test_singleton_is_checker_instance(self):
        """Verify singleton is SpreadChecker instance."""
        checker = get_spread_checker()
        assert isinstance(checker, SpreadChecker)
