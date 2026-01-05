"""Test signal parser module."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.signal_parser import (
    ConfidenceBreakdown,
    ExecutionInstructions,
    Indicators,
    SessionContext,
    Signal,
    SignalAction,
    SpreadCheck,
    TakeProfit,
    TrailingStopConfig,
    TradingSignal,
    WaveAnalysis,
    create_no_trade_signal,
    extract_json_from_response,
    parse_trading_signal,
)


class TestSignalAction:
    """Test SignalAction enum."""

    def test_buy_actions(self) -> None:
        """Test BUY action types exist."""
        assert SignalAction.BUY.value == "BUY"
        assert SignalAction.BUY_LIMIT.value == "BUY_LIMIT"

    def test_sell_actions(self) -> None:
        """Test SELL action types exist."""
        assert SignalAction.SELL.value == "SELL"
        assert SignalAction.SELL_LIMIT.value == "SELL_LIMIT"

    def test_no_trade_actions(self) -> None:
        """Test NO_TRADE and WAIT actions exist."""
        assert SignalAction.NO_TRADE.value == "NO_TRADE"
        assert SignalAction.WAIT.value == "WAIT"


class TestExtractJsonFromResponse:
    """Test JSON extraction from CLI output."""

    def test_extract_from_json_code_block(self) -> None:
        """Test extraction from ```json block."""
        response = '''
        Some text before
        ```json
        {"signal": {"action": "BUY", "confidence": 75}}
        ```
        Some text after
        '''
        result = extract_json_from_response(response)
        assert result is not None
        assert result["signal"]["action"] == "BUY"

    def test_extract_from_generic_code_block(self) -> None:
        """Test extraction from generic ``` block."""
        response = '''
        Analysis complete
        ```
        {"signal": {"action": "SELL", "confidence": 80}}
        ```
        '''
        result = extract_json_from_response(response)
        assert result is not None
        assert result["signal"]["action"] == "SELL"

    def test_extract_raw_json(self) -> None:
        """Test extraction of raw JSON without code blocks."""
        response = '''
        Here is the signal:
        {"signal": {"action": "NO_TRADE", "confidence": 0}}
        End of analysis
        '''
        result = extract_json_from_response(response)
        assert result is not None
        assert result["signal"]["action"] == "NO_TRADE"

    def test_extract_nested_json(self) -> None:
        """Test extraction handles nested objects."""
        response = '''```json
        {
            "signal": {
                "action": "BUY",
                "confidence": 78,
                "take_profit": [
                    {"level": "TP1", "price": 3380.0, "close_percent": 50}
                ]
            },
            "wave_analysis": {
                "h4_trend": "bullish",
                "current_wave": "wave_4_complete"
            }
        }
        ```'''
        result = extract_json_from_response(response)
        assert result is not None
        assert result["signal"]["action"] == "BUY"
        assert len(result["signal"]["take_profit"]) == 1
        assert result["wave_analysis"]["h4_trend"] == "bullish"

    def test_extract_handles_empty_response(self) -> None:
        """Test extraction returns None for empty response."""
        assert extract_json_from_response("") is None
        assert extract_json_from_response("   ") is None

    def test_extract_handles_no_json(self) -> None:
        """Test extraction returns None when no JSON present."""
        response = "This is just plain text with no JSON at all."
        assert extract_json_from_response(response) is None

    def test_extract_handles_invalid_json(self) -> None:
        """Test extraction returns None for malformed JSON."""
        response = '''```json
        {"signal": {"action": "BUY" missing_comma "confidence": 75}}
        ```'''
        result = extract_json_from_response(response)
        assert result is None

    def test_extract_handles_json_with_escaped_chars(self) -> None:
        """Test extraction handles escaped characters."""
        response = '''```json
        {"signal": {"action": "NO_TRADE", "confidence": 0, "reason": "Wave \\"unclear\\""}}
        ```'''
        result = extract_json_from_response(response)
        assert result is not None
        assert 'unclear' in result["signal"]["reason"]

    def test_extract_prefers_first_valid_json(self) -> None:
        """Test extraction returns first valid JSON block."""
        response = '''
        ```json
        {"first": true}
        ```
        Some text
        ```json
        {"second": true}
        ```
        '''
        result = extract_json_from_response(response)
        assert result is not None
        assert result.get("first") is True

    def test_extract_json_after_prose(self) -> None:
        """Test Strategy 4: extraction finds JSON anywhere after prose."""
        response = '''Based on the Elliott Wave analysis of the XAUUSD data:

**H4 Analysis**: Bullish impulse wave structure with Wave 4 completing near the 38.2% retracement.

**H1 Analysis**: Corrective pattern forming, but the overall trend remains bullish.

**Trading Signal:**

{"timestamp": "2024-08-21T14:30:00Z", "symbol": "XAUUSD", "signal": {"action": "BUY", "entry_price": 3340.00, "stop_loss": 3310.00, "confidence": 78}}

This completes the analysis.'''
        result = extract_json_from_response(response)
        assert result is not None
        assert result["signal"]["action"] == "BUY"
        assert result["signal"]["confidence"] == 78

    def test_extract_json_with_prose_and_nested_braces(self) -> None:
        """Test extraction ignores invalid JSON snippets in prose."""
        response = '''Analysis shows {wave pattern} in progress.

The function returns {error: true} on failure.

Final signal:
{"timestamp": "2024-08-21T14:30:00Z", "signal": {"action": "SELL", "confidence": 65}}'''
        result = extract_json_from_response(response)
        assert result is not None
        assert result["signal"]["action"] == "SELL"


class TestTradingSignalModel:
    """Test TradingSignal Pydantic model."""

    @pytest.fixture
    def minimal_signal_data(self) -> dict:
        """Minimal valid signal data."""
        return {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "confidence": 78,
            },
        }

    @pytest.fixture
    def full_signal_data(self) -> dict:
        """Complete signal data with all fields."""
        return {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "entry_price": 3340.00,
                "stop_loss": 3310.00,
                "stop_loss_atr": 3312.50,
                "take_profit": [
                    {"level": "TP1", "price": 3380.00, "close_percent": 50},
                    {"level": "TP2", "price": 3420.00, "close_percent": 30},
                    {"level": "TP3", "price": 3450.00, "close_percent": 20},
                ],
                "trailing_stop": {
                    "activation_trigger": "TP1_HIT",
                    "trail_distance_atr": 1.5,
                    "breakeven_buffer_pips": 5,
                },
                "risk_reward": 2.67,
                "confidence": 78,
                "position_size": {
                    "recommended_lots": 0.02,
                    "risk_percent": 1.5,
                    "risk_amount_usd": 30.00,
                    "atr_based": True,
                },
            },
            "session_context": {
                "current_session": "london_ny_overlap",
                "session_quality": "optimal",
                "session_modifier": 10,
                "time_to_session_end_minutes": 120,
            },
            "spread_check": {
                "current_spread_pips": 2.5,
                "max_allowed_pips": 4.0,
                "spread_ok": True,
                "adjusted_entry": 3340.125,
                "adjusted_tp1": 3379.75,
            },
            "wave_analysis": {
                "h4_trend": "bullish",
                "current_wave": "wave_4_complete",
                "wave_count_valid": True,
            },
            "confidence_breakdown": {
                "base_score": 50,
                "timeframe_alignment": 15,
                "fibonacci_confluence": 10,
                "rsi_confirmation": 10,
                "ema_alignment": 10,
                "macd_confirmation": 5,
                "session_bonus": 10,
                "penalties": -12,
                "penalty_reasons": ["alternative_30%"],
                "total": 78,
            },
        }

    def test_parse_minimal_signal(self, minimal_signal_data: dict) -> None:
        """Test parsing minimal valid signal."""
        signal = TradingSignal.model_validate(minimal_signal_data)
        assert signal.signal.action == SignalAction.BUY
        assert signal.signal.confidence == 78
        assert signal.symbol == "XAUUSD"

    def test_parse_full_signal(self, full_signal_data: dict) -> None:
        """Test parsing complete signal with all fields."""
        signal = TradingSignal.model_validate(full_signal_data)

        assert signal.signal.action == SignalAction.BUY
        assert signal.signal.entry_price == 3340.00
        assert len(signal.signal.take_profit) == 3
        assert signal.session_context.current_session == "london_ny_overlap"
        assert signal.spread_check.spread_ok is True
        assert signal.wave_analysis.h4_trend == "bullish"
        assert signal.confidence_breakdown.total == 78

    def test_is_tradeable_property(self, minimal_signal_data: dict) -> None:
        """Test is_tradeable property."""
        signal = TradingSignal.model_validate(minimal_signal_data)
        assert signal.is_tradeable is True

        minimal_signal_data["signal"]["action"] = "NO_TRADE"
        signal = TradingSignal.model_validate(minimal_signal_data)
        assert signal.is_tradeable is False

        minimal_signal_data["signal"]["action"] = "WAIT"
        signal = TradingSignal.model_validate(minimal_signal_data)
        assert signal.is_tradeable is False

    def test_is_buy_property(self, minimal_signal_data: dict) -> None:
        """Test is_buy property."""
        signal = TradingSignal.model_validate(minimal_signal_data)
        assert signal.is_buy is True
        assert signal.is_sell is False

        minimal_signal_data["signal"]["action"] = "BUY_LIMIT"
        signal = TradingSignal.model_validate(minimal_signal_data)
        assert signal.is_buy is True

    def test_is_sell_property(self, minimal_signal_data: dict) -> None:
        """Test is_sell property."""
        minimal_signal_data["signal"]["action"] = "SELL"
        signal = TradingSignal.model_validate(minimal_signal_data)
        assert signal.is_sell is True
        assert signal.is_buy is False

        minimal_signal_data["signal"]["action"] = "SELL_LIMIT"
        signal = TradingSignal.model_validate(minimal_signal_data)
        assert signal.is_sell is True

    def test_confidence_validation(self, minimal_signal_data: dict) -> None:
        """Test confidence score validation range."""
        # Valid: 0-100
        minimal_signal_data["signal"]["confidence"] = 0
        signal = TradingSignal.model_validate(minimal_signal_data)
        assert signal.signal.confidence == 0

        minimal_signal_data["signal"]["confidence"] = 100
        signal = TradingSignal.model_validate(minimal_signal_data)
        assert signal.signal.confidence == 100

        # Invalid: negative
        with pytest.raises(Exception):
            minimal_signal_data["signal"]["confidence"] = -1
            TradingSignal.model_validate(minimal_signal_data)

        # Invalid: > 100
        with pytest.raises(Exception):
            minimal_signal_data["signal"]["confidence"] = 101
            TradingSignal.model_validate(minimal_signal_data)


class TestParseTradingSignal:
    """Test parse_trading_signal function."""

    def test_parse_valid_json_response(self) -> None:
        """Test parsing valid JSON response."""
        response = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {"action": "BUY", "confidence": 75}
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.signal.action == SignalAction.BUY

    def test_parse_returns_none_for_invalid(self) -> None:
        """Test parsing returns None for invalid response."""
        assert parse_trading_signal("no json here") is None
        assert parse_trading_signal("") is None

    def test_parse_returns_none_for_missing_required(self) -> None:
        """Test parsing returns None when required fields missing."""
        response = '''```json
        {"symbol": "XAUUSD"}
        ```'''
        signal = parse_trading_signal(response)
        assert signal is None


class TestCreateNoTradeSignal:
    """Test create_no_trade_signal function."""

    def test_creates_valid_no_trade_signal(self) -> None:
        """Test creates valid NO_TRADE signal."""
        signal = create_no_trade_signal("test_reason", "Test details")

        assert signal.signal.action == SignalAction.NO_TRADE
        assert signal.signal.confidence == 0
        assert signal.signal.reason == "test_reason"
        assert signal.signal.details == "Test details"
        assert signal.symbol == "XAUUSD"
        assert signal.timestamp is not None

    def test_no_trade_signal_not_tradeable(self) -> None:
        """Test NO_TRADE signal is not tradeable."""
        signal = create_no_trade_signal("reason", "")
        assert signal.is_tradeable is False


class TestSubModels:
    """Test individual sub-models."""

    def test_take_profit_validation(self) -> None:
        """Test TakeProfit model validation."""
        tp = TakeProfit(level="TP1", price=3380.00, close_percent=50)
        assert tp.level == "TP1"
        assert tp.price == 3380.00
        assert tp.close_percent == 50

        # Price must be positive
        with pytest.raises(Exception):
            TakeProfit(level="TP1", price=-100, close_percent=50)

    def test_trailing_stop_defaults(self) -> None:
        """Test TrailingStopConfig defaults."""
        ts = TrailingStopConfig()
        assert ts.activation_trigger == "TP1_HIT"
        assert ts.trail_distance_atr == 1.5
        assert ts.breakeven_buffer_pips == 5

    def test_session_context(self) -> None:
        """Test SessionContext model."""
        ctx = SessionContext(
            current_session="london",
            session_quality="good",
            session_modifier=5,
        )
        assert ctx.current_session == "london"
        assert ctx.session_modifier == 5

    def test_spread_check(self) -> None:
        """Test SpreadCheck model."""
        sc = SpreadCheck(
            current_spread_pips=2.5,
            max_allowed_pips=4.0,
            spread_ok=True,
        )
        assert sc.spread_ok is True
        assert sc.current_spread_pips == 2.5

    def test_wave_analysis(self) -> None:
        """Test WaveAnalysis model."""
        wa = WaveAnalysis(
            h4_trend="bullish",
            current_wave="wave_4_complete",
        )
        assert wa.h4_trend == "bullish"
        assert wa.wave_count_valid is True  # default

    def test_confidence_breakdown(self) -> None:
        """Test ConfidenceBreakdown model."""
        cb = ConfidenceBreakdown(
            base_score=50,
            timeframe_alignment=15,
            total=65,
        )
        assert cb.base_score == 50
        assert cb.total == 65

    def test_execution_instructions(self) -> None:
        """Test ExecutionInstructions model."""
        ei = ExecutionInstructions(
            order_type="LIMIT",
            cancel_if=["price_exceeds_3355"],
        )
        assert ei.order_type == "LIMIT"
        assert "price_exceeds_3355" in ei.cancel_if


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
