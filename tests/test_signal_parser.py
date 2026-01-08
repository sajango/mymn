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
    MarketRegime,
    PreTradeChecks,
    SessionContext,
    Signal,
    SignalAction,
    SpreadCheck,
    TakeProfit,
    TakeProfitConfluence,
    TimeframeWave,
    TrailingStopConfig,
    TradingSignal,
    WaveAnalysis,
    WaveStructure,
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


class TestNormalizeSignalData:
    """Test _normalize_signal_data function."""

    def test_normalize_risk_reward_dict_to_float(self) -> None:
        """Test risk_reward dict is normalized to float using rr_ratio_tp1."""
        response = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "confidence": 72,
                "entry_price": 4453.44,
                "stop_loss": 4427.70,
                "risk_reward": {
                    "risk_pips": 25.74,
                    "reward_pips_tp1": 32.56,
                    "reward_pips_tp2": 56.56,
                    "reward_pips_tp3": 86.56,
                    "rr_ratio_tp1": 1.27,
                    "rr_ratio_tp2": 2.2,
                    "rr_ratio_tp3": 3.36
                }
            }
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.signal.risk_reward == 1.27  # Extracted from rr_ratio_tp1

    def test_normalize_risk_reward_dict_fallback_calculation(self) -> None:
        """Test risk_reward calculated from pips when rr_ratio not available."""
        response = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "confidence": 72,
                "risk_reward": {
                    "risk_pips": 25.0,
                    "reward_pips_tp1": 50.0
                }
            }
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.signal.risk_reward == 2.0  # 50/25 = 2.0

    def test_normalize_confidence_string_to_int(self) -> None:
        """Test confidence string (HIGH/MEDIUM/LOW) is normalized to int."""
        response = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "confidence": "MEDIUM",
                "entry_price": 4464.17
            }
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.signal.confidence == 60  # MEDIUM -> 60

    def test_normalize_confidence_string_high(self) -> None:
        """Test HIGH confidence string maps to 80."""
        response = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {"action": "BUY", "confidence": "HIGH"}
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.signal.confidence == 80

    def test_normalize_confidence_string_low(self) -> None:
        """Test LOW confidence string maps to 40."""
        response = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {"action": "SELL", "confidence": "LOW"}
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.signal.confidence == 40

    def test_normalize_risk_reward_ratio_string(self) -> None:
        """Test risk_reward ratio string (1:3.5) is normalized to float."""
        response = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "SELL",
                "confidence": 60,
                "risk_reward": "1:3.5"
            }
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.signal.risk_reward == 3.5  # 3.5/1 = 3.5

    def test_normalize_risk_reward_ratio_string_with_decimals(self) -> None:
        """Test risk_reward ratio with decimals on both sides."""
        response = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "confidence": 70,
                "risk_reward": "1.5:4.5"
            }
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.signal.risk_reward == 3.0  # 4.5/1.5 = 3.0

    def test_normalize_wave_position_from_elliott_wave_analysis(self) -> None:
        """Test extraction of wave_position from signal.elliott_wave_analysis."""
        response = '''```json
        {
            "timestamp": "2026-01-07T00:00:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "confidence": 75,
                "elliott_wave_analysis": {
                    "current_wave": "Wave 3 impulse in progress",
                    "h4_structure": "Bullish trend continuation",
                    "primary_count": {
                        "current_wave": "3",
                        "wave_position": "Impulse wave in progress"
                    }
                }
            }
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.wave_analysis is not None
        assert signal.wave_analysis.wave_position is not None
        assert "Wave 3" in signal.wave_analysis.wave_position

    def test_normalize_wave_position_preserves_existing(self) -> None:
        """Test that existing wave_analysis.wave_position is preserved."""
        response = '''```json
        {
            "timestamp": "2026-01-07T00:00:00Z",
            "symbol": "XAUUSD",
            "signal": {"action": "SELL", "confidence": 70},
            "wave_analysis": {
                "wave_position": "wave_5_complete",
                "h4_trend": "bullish",
                "current_wave": "Wave 5 complete"
            }
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.wave_analysis is not None
        assert signal.wave_analysis.wave_position == "wave_5_complete"

    def test_normalize_wave_position_from_current_wave(self) -> None:
        """Test wave_position is created from current_wave if missing."""
        response = '''```json
        {
            "timestamp": "2026-01-07T00:00:00Z",
            "symbol": "XAUUSD",
            "signal": {"action": "BUY", "confidence": 65},
            "wave_analysis": {
                "current_wave": "Corrective Wave B",
                "h4_trend": "bearish"
            }
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.wave_analysis is not None
        assert signal.wave_analysis.wave_position == "Corrective Wave B"

    def test_normalize_wave_position_with_h4_trend(self) -> None:
        """Test h4_trend extraction from elliott_wave_analysis."""
        response = '''```json
        {
            "timestamp": "2026-01-07T00:00:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "confidence": 75,
                "elliott_wave_analysis": {
                    "current_wave": "Wave 4",
                    "h4_structure": "Bullish continuation expected"
                }
            }
        }
        ```'''
        signal = parse_trading_signal(response)
        assert signal is not None
        assert signal.wave_analysis is not None
        assert signal.wave_analysis.h4_trend == "bullish"


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


class TestV4Models:
    """Test v4 new models."""

    def test_market_regime(self) -> None:
        """Test MarketRegime model."""
        regime = MarketRegime(
            classification="trending_strong",
            adx_14=32.5,
            trend_direction="bullish",
            trend_strength="strong",
            elliott_wave_reliability="high",
            confidence_modifier=15,
        )
        assert regime.classification == "trending_strong"
        assert regime.adx_14 == 32.5
        assert regime.confidence_modifier == 15

    def test_market_regime_defaults(self) -> None:
        """Test MarketRegime defaults."""
        regime = MarketRegime(classification="ranging")
        assert regime.trend_direction == "neutral"
        assert regime.trend_strength == "moderate"
        assert regime.elliott_wave_reliability == "medium"
        assert regime.confidence_modifier == 0
        assert regime.warnings == []

    def test_timeframe_wave(self) -> None:
        """Test TimeframeWave model."""
        wave = TimeframeWave(
            degree="Primary",
            current_wave="(3)",
            wave_label="(3) of Primary impulse",
            position_in_sequence="impulse_wave_3_of_5",
            structure="impulse",
            subwaves_expected=5,
        )
        assert wave.degree == "Primary"
        assert wave.current_wave == "(3)"
        assert wave.subwaves_expected == 5

    def test_wave_structure(self) -> None:
        """Test WaveStructure model."""
        h4_wave = TimeframeWave(
            degree="Primary",
            current_wave="(3)",
            wave_label="(3) of Primary",
            position_in_sequence="impulse_wave_3_of_5",
        )
        h1_wave = TimeframeWave(
            degree="Intermediate",
            current_wave="4",
            wave_label="4 of (3)",
            position_in_sequence="correction_within_impulse",
            parent_wave="H4_(3)",
        )
        ws = WaveStructure(
            h4=h4_wave,
            h1=h1_wave,
            alignment_status="ALIGNED",
            alignment_confidence_modifier=10,
        )
        assert ws.h4.degree == "Primary"
        assert ws.h1.parent_wave == "H4_(3)"
        assert ws.alignment_status == "ALIGNED"

    def test_take_profit_confluence(self) -> None:
        """Test TakeProfitConfluence model."""
        confluence = TakeProfitConfluence(
            count=3, details=["EMA support", "Fib 61.8%", "Previous resistance"]
        )
        assert confluence.count == 3
        assert len(confluence.details) == 3

    def test_take_profit_v4_enhanced(self) -> None:
        """Test enhanced TakeProfit with v4 fields."""
        tp = TakeProfit(
            level="TP1",
            price=3380.00,
            close_percent=40,
            fib_basis="61.8% of Wave 1",
            confluence_count=2,
            probability=80,
            risk_reward=1.73,
        )
        assert tp.fib_basis == "61.8% of Wave 1"
        assert tp.confluence_count == 2
        assert tp.probability == 80
        assert tp.risk_reward == 1.73

    def test_pre_trade_checks(self) -> None:
        """Test PreTradeChecks model."""
        checks = PreTradeChecks(
            trading_allowed=True,
            regime_suitable=True,
            session_suitable=True,
            spread_ok=True,
            risk_budget_available=True,
            all_checks_passed=True,
        )
        assert checks.all_checks_passed is True

    def test_pre_trade_checks_defaults(self) -> None:
        """Test PreTradeChecks defaults."""
        checks = PreTradeChecks()
        assert checks.trading_allowed is True
        assert checks.all_checks_passed is True


class TestV4SignalParsing:
    """Test parsing v4 format signals."""

    def test_parse_v4_signal_with_market_regime(self) -> None:
        """Test parsing v4 signal with market_regime."""
        v4_json = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "market_regime": {
                "classification": "trending_strong",
                "adx_14": 32.5,
                "trend_direction": "bullish",
                "elliott_wave_reliability": "high",
                "confidence_modifier": 15
            },
            "signal": {"action": "BUY", "confidence": 78}
        }
        ```'''
        signal = parse_trading_signal(v4_json)
        assert signal is not None
        assert signal.market_regime is not None
        assert signal.market_regime.classification == "trending_strong"
        assert signal.market_regime.confidence_modifier == 15

    def test_parse_v4_signal_with_pre_trade_checks(self) -> None:
        """Test parsing v4 signal with pre_trade_checks."""
        v4_json = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "pre_trade_checks": {
                "trading_allowed": true,
                "regime_suitable": true,
                "session_suitable": true,
                "spread_ok": true,
                "all_checks_passed": true
            },
            "signal": {"action": "SELL", "confidence": 72}
        }
        ```'''
        signal = parse_trading_signal(v4_json)
        assert signal is not None
        assert signal.pre_trade_checks is not None
        assert signal.pre_trade_checks.all_checks_passed is True

    def test_parse_v4_signal_with_wave_structure(self) -> None:
        """Test parsing v4 signal with wave_structure."""
        v4_json = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "wave_structure": {
                "h4": {
                    "degree": "Primary",
                    "current_wave": "(3)",
                    "wave_label": "(3) of Primary impulse",
                    "position_in_sequence": "impulse_wave_3_of_5",
                    "structure": "impulse"
                },
                "h1": {
                    "degree": "Intermediate",
                    "current_wave": "4",
                    "wave_label": "4 of (3)",
                    "position_in_sequence": "correction_within_impulse",
                    "parent_wave": "H4_(3)"
                },
                "alignment_status": "ALIGNED",
                "alignment_confidence_modifier": 10
            },
            "signal": {"action": "BUY", "confidence": 85}
        }
        ```'''
        signal = parse_trading_signal(v4_json)
        assert signal is not None
        assert signal.wave_structure is not None
        assert signal.wave_structure.h4.degree == "Primary"
        assert signal.wave_structure.h1.parent_wave == "H4_(3)"
        assert signal.wave_structure.alignment_status == "ALIGNED"

    def test_parse_v4_enhanced_take_profit(self) -> None:
        """Test parsing v4 enhanced take_profit with confluence."""
        v4_json = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "confidence": 78,
                "entry_price": 3340.00,
                "stop_loss": 3310.00,
                "take_profit": [
                    {
                        "level": "TP1",
                        "price": 3380.00,
                        "close_percent": 40,
                        "fib_basis": "61.8% of Wave 1",
                        "confluence_count": 2,
                        "probability": 80,
                        "risk_reward": 1.73
                    }
                ]
            }
        }
        ```'''
        signal = parse_trading_signal(v4_json)
        assert signal is not None
        assert len(signal.signal.take_profit) == 1
        tp = signal.signal.take_profit[0]
        assert tp.fib_basis == "61.8% of Wave 1"
        assert tp.confluence_count == 2
        assert tp.probability == 80

    def test_parse_full_v4_signal(self) -> None:
        """Test parsing complete v4 signal structure."""
        v4_json = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "pre_trade_checks": {
                "trading_allowed": true,
                "all_checks_passed": true
            },
            "market_regime": {
                "classification": "trending_strong",
                "trend_direction": "bullish",
                "elliott_wave_reliability": "high"
            },
            "wave_structure": {
                "h4": {
                    "degree": "Primary",
                    "current_wave": "(3)",
                    "wave_label": "(3) of Primary",
                    "position_in_sequence": "impulse_wave_3_of_5"
                },
                "alignment_status": "ALIGNED"
            },
            "wave_analysis": {
                "h4_trend": "bullish",
                "current_wave": "wave_4_complete"
            },
            "signal": {
                "action": "BUY",
                "entry_price": 3340.00,
                "stop_loss": 3310.00,
                "confidence": 78,
                "take_profit": [
                    {"level": "TP1", "price": 3380.00, "close_percent": 40}
                ]
            },
            "metadata": {
                "model_version": "elliott_wave_v4.0",
                "features_used": ["market_regime_filter", "wave_degree_labeling"]
            }
        }
        ```'''
        signal = parse_trading_signal(v4_json)
        assert signal is not None
        assert signal.pre_trade_checks.all_checks_passed is True
        assert signal.market_regime.classification == "trending_strong"
        assert signal.wave_structure.h4.degree == "Primary"
        assert signal.wave_analysis.h4_trend == "bullish"
        assert signal.metadata.model_version == "elliott_wave_v4.0"
        assert "market_regime_filter" in signal.metadata.features_used

    def test_v4_backward_compat_with_v2_signal(self) -> None:
        """Test v4 models backward compatible with v2 format."""
        v2_json = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "confidence": 75,
                "take_profit": [
                    {"level": "TP1", "price": 3380.00, "close_percent": 50}
                ]
            },
            "wave_analysis": {
                "h4_trend": "bullish",
                "current_wave": "wave_4_complete"
            }
        }
        ```'''
        signal = parse_trading_signal(v2_json)
        assert signal is not None
        assert signal.signal.action.value == "BUY"
        # v4 fields should be None for v2 signals
        assert signal.pre_trade_checks is None
        assert signal.market_regime is None
        assert signal.wave_structure is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
