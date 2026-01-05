"""Trading signal models and JSON parsing for Claude CLI output."""

import json
import logging
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class SignalAction(str, Enum):
    """Trading signal action types."""

    BUY = "BUY"
    BUY_LIMIT = "BUY_LIMIT"
    SELL = "SELL"
    SELL_LIMIT = "SELL_LIMIT"
    NO_TRADE = "NO_TRADE"
    WAIT = "WAIT"


class TakeProfit(BaseModel):
    """Take profit level configuration."""

    level: str = Field(description="TP level (TP1, TP2, TP3)")
    price: float = Field(gt=0, description="Target price")
    close_percent: int = Field(ge=0, le=100, description="Position % to close")


class TrailingStopConfig(BaseModel):
    """Trailing stop configuration."""

    activation_trigger: str = Field(
        default="TP1_HIT", description="When to activate trailing"
    )
    trail_distance_atr: float = Field(
        default=1.5, ge=0.5, le=5.0, description="Trail distance as ATR multiple"
    )
    breakeven_buffer_pips: int = Field(
        default=5, ge=0, le=50, description="Pips above entry for breakeven"
    )


class PositionSize(BaseModel):
    """Position sizing recommendation."""

    recommended_lots: float = Field(ge=0, description="Recommended lot size")
    risk_percent: float = Field(ge=0, le=10, description="Risk as % of account")
    risk_amount_usd: float = Field(ge=0, description="Risk amount in USD")
    atr_based: bool = Field(default=True, description="Whether ATR-based sizing used")


class UpcomingNews(BaseModel):
    """Upcoming news event information."""

    event: Optional[str] = Field(default=None, description="Event name")
    time_utc: Optional[str] = Field(default=None, description="Event time UTC")
    impact: Optional[str] = Field(default=None, description="Impact level")
    minutes_until: Optional[int] = Field(default=None, description="Minutes until event")
    in_blackout: bool = Field(default=False, description="Whether in blackout period")


class SessionContext(BaseModel):
    """Trading session context information."""

    current_session: str = Field(description="Current trading session name")
    session_quality: str = Field(description="Session quality assessment")
    session_modifier: int = Field(description="Confidence modifier for session")
    time_to_session_end_minutes: Optional[int] = Field(
        default=None, description="Minutes until session ends"
    )
    upcoming_news: Optional[UpcomingNews] = Field(
        default=None, description="Upcoming news event"
    )


class SpreadCheck(BaseModel):
    """Spread validation results."""

    current_spread_pips: float = Field(ge=0, description="Current spread in pips")
    max_allowed_pips: float = Field(ge=0, description="Maximum allowed spread")
    spread_ok: bool = Field(description="Whether spread is acceptable")
    adjusted_entry: Optional[float] = Field(
        default=None, description="Spread-adjusted entry price"
    )
    adjusted_tp1: Optional[float] = Field(
        default=None, description="Spread-adjusted TP1 price"
    )


class RulesCheck(BaseModel):
    """Elliott Wave rules validation."""

    rule_1_wave2_valid: bool = Field(
        default=True, description="Wave 2 retracement < 100%"
    )
    rule_2_wave3_not_shortest: bool = Field(
        default=True, description="Wave 3 not shortest"
    )
    rule_3_wave4_no_overlap: bool = Field(
        default=True, description="Wave 4 no overlap with Wave 1"
    )


class WaveScenario(BaseModel):
    """Wave count scenario."""

    description: str = Field(description="Scenario description")
    probability: int = Field(ge=0, le=100, description="Scenario probability %")


class WaveAnalysis(BaseModel):
    """Elliott Wave analysis results."""

    h4_trend: str = Field(description="H4 timeframe trend direction")
    current_wave: str = Field(description="Current wave position")
    wave_position: Optional[str] = Field(
        default=None, description="Detailed wave position for tracking"
    )
    wave_count_valid: bool = Field(default=True, description="Whether wave count valid")
    rules_check: Optional[RulesCheck] = Field(
        default=None, description="Rules validation"
    )
    primary_scenario: Optional[WaveScenario] = Field(
        default=None, description="Primary wave scenario"
    )
    alternative_scenario: Optional[WaveScenario] = Field(
        default=None, description="Alternative wave scenario"
    )
    invalidation_price: Optional[float] = Field(
        default=None, description="Price that invalidates count"
    )


class RSIIndicator(BaseModel):
    """RSI indicator analysis."""

    value: float = Field(description="RSI value")
    zone: str = Field(description="RSI zone (oversold/neutral/overbought)")
    divergence: bool = Field(default=False, description="Divergence detected")
    confirmation: Optional[str] = Field(
        default=None, description="Confirmation status"
    )


class EMAIndicator(BaseModel):
    """EMA indicator analysis."""

    ema_34: float = Field(description="EMA 34 value")
    ema_89: float = Field(description="EMA 89 value")
    price_position: str = Field(description="Price position relative to EMAs")
    trend_alignment: str = Field(description="Trend alignment status")


class MACDIndicator(BaseModel):
    """MACD indicator analysis."""

    macd_line: float = Field(description="MACD line value")
    signal_line: float = Field(description="Signal line value")
    histogram: float = Field(description="Histogram value")
    divergence: bool = Field(default=False, description="Divergence detected")
    momentum: Optional[str] = Field(default=None, description="Momentum status")


class ATRIndicator(BaseModel):
    """ATR indicator analysis."""

    value: float = Field(description="ATR value")
    regime: str = Field(description="Volatility regime")
    stop_distance: Optional[float] = Field(
        default=None, description="Calculated stop distance"
    )


class Indicators(BaseModel):
    """All technical indicators."""

    rsi: Optional[RSIIndicator] = Field(default=None, description="RSI analysis")
    ema: Optional[EMAIndicator] = Field(default=None, description="EMA analysis")
    macd: Optional[MACDIndicator] = Field(default=None, description="MACD analysis")
    atr: Optional[ATRIndicator] = Field(default=None, description="ATR analysis")


class ConfidenceBreakdown(BaseModel):
    """Confidence score breakdown."""

    base_score: int = Field(default=50, description="Base confidence score")
    timeframe_alignment: int = Field(default=0, description="Timeframe alignment bonus")
    fibonacci_confluence: int = Field(default=0, description="Fibonacci confluence bonus")
    rsi_confirmation: int = Field(default=0, description="RSI confirmation bonus")
    ema_alignment: int = Field(default=0, description="EMA alignment bonus")
    macd_confirmation: int = Field(default=0, description="MACD confirmation bonus")
    session_bonus: int = Field(default=0, description="Session bonus/penalty")
    penalties: int = Field(default=0, description="Total penalties")
    penalty_reasons: list[str] = Field(
        default_factory=list, description="Penalty reason list"
    )
    total: int = Field(description="Total confidence score")


class ExecutionInstructions(BaseModel):
    """Order execution instructions."""

    order_type: str = Field(description="Order type (MARKET, LIMIT)")
    valid_until: Optional[str] = Field(
        default=None, description="Order validity timestamp"
    )
    cancel_if: list[str] = Field(
        default_factory=list, description="Conditions to cancel order"
    )
    post_fill_actions: list[str] = Field(
        default_factory=list, description="Actions after order fills"
    )


class PivotQuality(BaseModel):
    """Pivot point detection quality metrics."""

    total_pivots: int = Field(default=0, description="Total pivots detected")
    major_pivots: int = Field(default=0, description="Major pivots count")
    intermediate_pivots: int = Field(default=0, description="Intermediate pivots count")
    minor_pivots: int = Field(default=0, description="Minor pivots count")
    filtered_noise: int = Field(default=0, description="Noise pivots filtered")


class Metadata(BaseModel):
    """Analysis metadata."""

    h4_candles_analyzed: int = Field(default=200, description="H4 candles analyzed")
    h1_candles_analyzed: int = Field(default=200, description="H1 candles analyzed")
    m30_candles_analyzed: int = Field(default=200, description="M30 candles analyzed")
    m15_candles_analyzed: int = Field(default=200, description="M15 candles analyzed")
    pivots_detected: Optional[dict[str, int]] = Field(
        default=None, description="Pivots by type"
    )
    analysis_timestamp: Optional[str] = Field(
        default=None, description="Analysis timestamp"
    )
    model_version: str = Field(
        default="elliott_wave_v2.0", description="Model version"
    )


class Signal(BaseModel):
    """Trading signal details."""

    action: SignalAction = Field(description="Signal action type")
    entry_price: Optional[float] = Field(default=None, description="Entry price")
    stop_loss: Optional[float] = Field(default=None, description="Stop loss price")
    stop_loss_atr: Optional[float] = Field(
        default=None, description="ATR-based stop loss"
    )
    take_profit: list[TakeProfit] = Field(
        default_factory=list, description="Take profit levels"
    )
    trailing_stop: Optional[TrailingStopConfig] = Field(
        default=None, description="Trailing stop config"
    )
    risk_reward: Optional[float] = Field(default=None, description="Risk:Reward ratio")
    confidence: int = Field(ge=0, le=100, description="Signal confidence 0-100")
    position_size: Optional[PositionSize] = Field(
        default=None, description="Position sizing"
    )
    reason: Optional[str] = Field(default=None, description="No-trade reason")
    details: Optional[str] = Field(default=None, description="Additional details")


class TradingSignal(BaseModel):
    """Complete trading signal from Claude analysis."""

    timestamp: str = Field(description="Signal generation timestamp")
    symbol: str = Field(default="XAUUSD", description="Trading symbol")
    signal: Signal = Field(description="Signal details")
    session_context: Optional[SessionContext] = Field(
        default=None, description="Session context"
    )
    spread_check: Optional[SpreadCheck] = Field(
        default=None, description="Spread validation"
    )
    wave_analysis: Optional[WaveAnalysis] = Field(
        default=None, description="Wave analysis"
    )
    indicators: Optional[Indicators] = Field(
        default=None, description="Indicator analysis"
    )
    confidence_breakdown: Optional[ConfidenceBreakdown] = Field(
        default=None, description="Confidence breakdown"
    )
    execution_instructions: Optional[ExecutionInstructions] = Field(
        default=None, description="Execution instructions"
    )
    metadata: Optional[Metadata] = Field(default=None, description="Analysis metadata")

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> str:
        """Accept various timestamp formats."""
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)

    @property
    def is_tradeable(self) -> bool:
        """Check if signal is actionable."""
        return self.signal.action not in (SignalAction.NO_TRADE, SignalAction.WAIT)

    @property
    def is_buy(self) -> bool:
        """Check if signal is a buy."""
        return self.signal.action in (SignalAction.BUY, SignalAction.BUY_LIMIT)

    @property
    def is_sell(self) -> bool:
        """Check if signal is a sell."""
        return self.signal.action in (SignalAction.SELL, SignalAction.SELL_LIMIT)


def _extract_json_at_position(text: str, start: int) -> Optional[dict]:
    """Try to extract valid JSON object starting at given position.

    Uses brace-matching with proper string/escape handling.

    Args:
        text: Full text to search in
        start: Position of opening brace

    Returns:
        Parsed JSON dict or None if invalid
    """
    depth = 0
    in_string = False
    escape_next = False

    for i, char in enumerate(text[start:]):
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if not in_string:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    json_str = text[start : start + i + 1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        return None
    return None


def extract_json_from_response(response: str) -> Optional[dict]:
    """Extract JSON from Claude CLI response.

    Tries multiple extraction strategies:
    1. JSON code block (```json ... ```)
    2. Generic code block (``` ... ```)
    3. Raw JSON object at start ({ ... })
    4. JSON object anywhere in response (handles prose before JSON)

    Args:
        response: Raw CLI output string

    Returns:
        Parsed JSON dict or None if extraction fails
    """
    if not response or not response.strip():
        logger.warning("Empty response received")
        return None

    # Strategy 1: JSON code block
    json_block_pattern = r"```json\s*([\s\S]*?)\s*```"
    matches = re.findall(json_block_pattern, response)
    if matches:
        for match in matches:
            try:
                result = json.loads(match)
                logger.debug("Extracted JSON via Strategy 1 (```json block)")
                return result
            except json.JSONDecodeError:
                continue

    # Strategy 2: Generic code block
    code_block_pattern = r"```\s*([\s\S]*?)\s*```"
    matches = re.findall(code_block_pattern, response)
    if matches:
        for match in matches:
            # Skip non-JSON code blocks
            if match.strip().startswith(("{", "[")):
                try:
                    result = json.loads(match)
                    logger.debug("Extracted JSON via Strategy 2 (generic ``` block)")
                    return result
                except json.JSONDecodeError:
                    continue

    # Strategy 3: Raw JSON object at start
    brace_start = response.find("{")
    if brace_start != -1 and brace_start < 50:  # JSON starts near beginning
        result = _extract_json_at_position(response, brace_start)
        if result:
            logger.debug("Extracted JSON via Strategy 3 (raw JSON at start)")
            return result

    # Strategy 4: Find JSON object ANYWHERE in response (handles prose before JSON)
    # Search for { positions and try to parse valid JSON from each (limit attempts for performance)
    MAX_BRACE_ATTEMPTS = 20
    brace_positions = [i for i, c in enumerate(response) if c == '{'][:MAX_BRACE_ATTEMPTS]
    for pos in brace_positions:
        # Skip if we already tried this position
        if pos == brace_start and brace_start < 50:
            continue
        result = _extract_json_at_position(response, pos)
        if result:
            # Validate it looks like a trading signal (requires BOTH keys)
            if isinstance(result, dict) and ("signal" in result and "timestamp" in result):
                logger.debug(f"Extracted JSON via Strategy 4 (found at position {pos})")
                return result

    logger.warning("Failed to extract JSON from response")
    return None


def parse_trading_signal(response: str) -> Optional[TradingSignal]:
    """Parse Claude CLI response into TradingSignal.

    Args:
        response: Raw CLI output string

    Returns:
        TradingSignal or None if parsing fails
    """
    json_data = extract_json_from_response(response)
    if json_data is None:
        logger.error("Could not extract JSON from response")
        return None

    try:
        signal = TradingSignal.model_validate(json_data)
        logger.info(f"Parsed signal: {signal.signal.action} confidence={signal.signal.confidence}")
        return signal
    except Exception as e:
        logger.error(f"Signal validation failed: {e}")
        return None


def create_no_trade_signal(reason: str, details: str = "") -> TradingSignal:
    """Create a NO_TRADE signal for error cases.

    Args:
        reason: Short reason code
        details: Detailed explanation

    Returns:
        TradingSignal with NO_TRADE action
    """
    return TradingSignal(
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        symbol="XAUUSD",
        signal=Signal(
            action=SignalAction.NO_TRADE,
            confidence=0,
            reason=reason,
            details=details,
        ),
    )
