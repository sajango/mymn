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
    """Take profit level configuration - v4 compatible."""

    level: str = Field(description="TP level (TP1, TP2, TP3)")
    price: float = Field(gt=0, description="Target price")
    close_percent: int = Field(ge=0, le=100, description="Position % to close")
    # NEW v4 fields (optional for backward compat)
    fib_basis: Optional[str] = Field(default=None, description="Fibonacci basis")
    confluence_count: Optional[int] = Field(
        default=None, description="Number of confluence factors"
    )
    probability: Optional[int] = Field(default=None, ge=0, le=100)
    risk_reward: Optional[float] = Field(default=None, ge=0)
    rr_adjusted: bool = Field(
        default=False, description="Was R:R adjusted for min threshold"
    )
    note: Optional[str] = Field(default=None)


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


class MarketRegime(BaseModel):
    """Market regime detection from instruction_v4."""

    classification: str = Field(
        description="trending_strong, trending_weak, ranging, choppy"
    )
    adx_14: Optional[float] = Field(default=None, description="ADX 14 value")
    trend_direction: str = Field(
        default="neutral", description="bullish/bearish/neutral"
    )
    trend_strength: str = Field(
        default="moderate", description="very_strong/strong/moderate/weak/absent"
    )
    ema_spread_percent: Optional[float] = Field(
        default=None, description="EMA 34-89 spread %"
    )
    volatility_regime: str = Field(default="normal", description="Volatility regime")
    elliott_wave_reliability: str = Field(
        default="medium", description="high/medium/low/not_recommended"
    )
    confidence_modifier: int = Field(default=0, description="Confidence adjustment")
    recommended_action: str = Field(
        default="full_analysis",
        description="full_analysis/cautious_analysis/skip_ew/wait",
    )
    warnings: list[str] = Field(default_factory=list, description="Regime warnings")


class TimeframeWave(BaseModel):
    """Wave analysis for single timeframe."""

    degree: str = Field(description="Primary/Intermediate/Minor/Minute")
    current_wave: str = Field(description="Wave label e.g. (3), 4, [c]")
    wave_label: str = Field(description="Full label e.g. '(3) of Primary'")
    position_in_sequence: str = Field(description="impulse_wave_3_of_5")
    structure: str = Field(default="impulse", description="impulse/corrective")
    subwaves_expected: Optional[int] = Field(default=None)
    parent_wave: Optional[str] = Field(default=None, description="Parent wave reference")


class WaveStructure(BaseModel):
    """Multi-timeframe wave structure from v4."""

    h4: Optional[TimeframeWave] = Field(default=None)
    h1: Optional[TimeframeWave] = Field(default=None)
    m30: Optional[TimeframeWave] = Field(default=None)
    m15: Optional[TimeframeWave] = Field(default=None)
    alignment_status: str = Field(
        default="UNKNOWN", description="ALIGNED/CONFLICT/WARNING"
    )
    alignment_confidence_modifier: int = Field(default=0)


class TakeProfitConfluence(BaseModel):
    """Confluence details for TP level."""

    count: int = Field(default=0, description="Number of confluence factors")
    details: list[str] = Field(
        default_factory=list, description="Confluence descriptions"
    )


class PreTradeChecks(BaseModel):
    """Pre-trade validation summary from v4."""

    trading_allowed: bool = Field(default=True)
    regime_suitable: bool = Field(default=True)
    session_suitable: bool = Field(default=True)
    spread_ok: bool = Field(default=True)
    risk_budget_available: bool = Field(default=True)
    all_checks_passed: bool = Field(default=True)


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
        default="elliott_wave_v4.0", description="Model version"
    )
    features_used: list[str] = Field(default_factory=list, description="Features used")


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
    """Complete trading signal from Claude analysis - v4 compatible."""

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
    # NEW v4 fields
    pre_trade_checks: Optional[PreTradeChecks] = Field(
        default=None, description="Pre-trade validation summary"
    )
    market_regime: Optional[MarketRegime] = Field(
        default=None, description="Market regime detection"
    )
    wave_structure: Optional[WaveStructure] = Field(
        default=None, description="Multi-timeframe wave structure"
    )

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


def _extract_signal_from_markdown(response: str) -> Optional[dict]:
    """Strategy 5: Extract trading signal data from markdown response.

    When Claude ignores JSON instructions and outputs markdown analysis,
    extract key data and build a valid signal structure.

    Args:
        response: Markdown-formatted analysis response

    Returns:
        Dict with signal data or None if extraction fails
    """
    # Detect if this is a markdown response (has headers/tables but no JSON)
    has_markdown_headers = bool(re.search(r"^#{1,3}\s+", response, re.MULTILINE))
    has_tables = "|" in response and "---" in response
    has_json_markers = "{" in response and "}" in response

    if not (has_markdown_headers or has_tables) or has_json_markers:
        return None  # Not a markdown-only response

    logger.info("Attempting Strategy 5: Markdown fallback extraction")

    # Extract signal action
    action = "NO_TRADE"
    action_patterns = [
        r"SIGNAL[:\s]*\**\s*(BUY|SELL|HOLD|WAIT|NEUTRAL|NO[_\s]?TRADE)",
        r"Signal[:\s]*\**\s*(BUY|SELL|HOLD|WAIT|NEUTRAL|NO[_\s]?TRADE)",
        r"Bias[:\s]*\**\s*(BULLISH|BEARISH|NEUTRAL)",
        r"\*\*(BUY|SELL|HOLD|WAIT|NO[_\s]?TRADE)\*\*",
    ]
    for pattern in action_patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            raw_action = match.group(1).upper().replace(" ", "_")
            if raw_action in ("HOLD", "WAIT", "NEUTRAL"):
                action = "NO_TRADE"
            elif raw_action == "BULLISH":
                action = "NO_TRADE"  # Bias, not action - need to wait for entry
            elif raw_action == "BEARISH":
                action = "NO_TRADE"
            elif raw_action in ("BUY", "SELL", "NO_TRADE"):
                action = raw_action
            break

    # Extract confidence score
    confidence = 0
    confidence_patterns = [
        r"[Cc]onfidence[:\s]*\**\s*(\d{1,3})\s*%",  # Confidence: 65%
        r"(\d{1,3})\s*%\s*[Cc]onfidence",  # 65% confidence
        r"[Cc]onfidence\s*\|\s*(\d{1,3})\s*%",  # Confidence | 65%
        r"\*\*[Cc]onfidence\*\*\s*\|\s*(\d{1,3})\s*%",  # **Confidence** | 65%
        r"[Cc]onfidence[^\d]*(\d{1,3})\s*%",  # Confidence ... 65%
        r"(\d{1,3})\s*%.*(?:trend|strong|weak|extended)",  # 65% | Strong trend
    ]
    for pattern in confidence_patterns:
        match = re.search(pattern, response)
        if match:
            confidence = min(int(match.group(1)), 100)
            break

    # Extract current price
    current_price = None
    price_patterns = [
        r"[Cc]urrent\s*[Pp]rice[:\s]*\**\s*([\d,]+\.?\d*)",
        r"[Cc]lose[:\s]*\**\s*([\d,]+\.?\d*)",
    ]
    for pattern in price_patterns:
        match = re.search(pattern, response)
        if match:
            try:
                current_price = float(match.group(1).replace(",", ""))
                break
            except ValueError:
                continue

    # Extract reason/details from markdown
    reason = "Markdown analysis - no JSON output"
    details_patterns = [
        r"(?:Key\s+)?Observations?[:\s]*(.*?)(?=\n\n|\n---|\n#|\Z)",
        r"Rationale[:\s]*(.*?)(?=\n\n|\n---|\n#|\Z)",
        r"Summary[:\s]*(.*?)(?=\n\n|\n---|\n#|\Z)",
    ]
    for pattern in details_patterns:
        match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
        if match:
            details_text = match.group(1).strip()[:500]  # Limit length
            # Clean up markdown formatting
            details_text = re.sub(r"\*\*|\n\d+\.\s*", " ", details_text)
            details_text = re.sub(r"\s+", " ", details_text).strip()
            if details_text:
                reason = details_text[:200]
                break

    # Build signal structure
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    signal_data = {
        "timestamp": timestamp,
        "symbol": "XAUUSD",
        "signal": {
            "action": action,
            "confidence": confidence,
            "reason": "markdown_fallback",
            "details": reason,
        },
    }

    # Add entry price if we have it and action is tradeable
    if current_price and action in ("BUY", "SELL"):
        signal_data["signal"]["entry_price"] = current_price

    logger.info(
        f"Strategy 5 extracted: action={action}, confidence={confidence}, "
        f"price={current_price}"
    )
    return signal_data


def _normalize_signal_data(data: dict) -> dict:
    """Normalize LLM output to match Pydantic schema.

    Handles field name variations and format differences between
    what the LLM produces and what the schema expects.

    Args:
        data: Raw JSON dict from LLM

    Returns:
        Normalized dict matching TradingSignal schema
    """
    if not isinstance(data, dict):
        return data

    # Normalize signal sub-object
    signal = data.get("signal", {})
    if isinstance(signal, dict):
        # Map direction -> action (field name)
        if "direction" in signal and "action" not in signal:
            signal["action"] = signal.pop("direction")
            logger.debug("Normalized: direction -> action")

        # Map direction values to action values (BULLISH -> BUY, etc.)
        if "action" in signal:
            action_val = str(signal["action"]).upper()
            direction_to_action = {
                "BULLISH": "BUY",
                "BEARISH": "SELL",
                "LONG": "BUY",
                "SHORT": "SELL",
                "NEUTRAL": "NO_TRADE",
                "HOLD": "NO_TRADE",
                "WAIT": "WAIT",
            }
            if action_val in direction_to_action:
                original = signal["action"]
                signal["action"] = direction_to_action[action_val]
                logger.debug(f"Normalized: action value {original} -> {signal['action']}")

        # Convert confidence from 0-1 float to 0-100 int, or string to int
        if "confidence" in signal:
            conf = signal["confidence"]
            if isinstance(conf, float) and 0 <= conf <= 1:
                signal["confidence"] = int(conf * 100)
                logger.debug(f"Normalized: confidence {conf} -> {signal['confidence']}")
            elif isinstance(conf, str):
                # Map string confidence levels to int values
                confidence_map = {
                    "HIGH": 80,
                    "MEDIUM": 60,
                    "LOW": 40,
                    "VERY_HIGH": 90,
                    "VERY_LOW": 20,
                }
                conf_upper = conf.upper().replace(" ", "_")
                if conf_upper in confidence_map:
                    signal["confidence"] = confidence_map[conf_upper]
                    logger.debug(f"Normalized: confidence '{conf}' -> {signal['confidence']}")

        # Map risk_reward_ratio -> risk_reward
        if "risk_reward_ratio" in signal and "risk_reward" not in signal:
            signal["risk_reward"] = signal.pop("risk_reward_ratio")
            logger.debug("Normalized: risk_reward_ratio -> risk_reward")

        # Handle risk_reward as ratio string -> extract float (e.g., "1:3.5" -> 3.5)
        if "risk_reward" in signal and isinstance(signal["risk_reward"], str):
            rr_str = signal["risk_reward"]
            if ":" in rr_str:
                try:
                    parts = rr_str.split(":")
                    if len(parts) == 2:
                        risk_part = float(parts[0].strip())
                        reward_part = float(parts[1].strip())
                        if risk_part > 0:
                            signal["risk_reward"] = round(reward_part / risk_part, 2)
                            logger.debug(f"Normalized: risk_reward '{rr_str}' -> {signal['risk_reward']}")
                except (ValueError, IndexError) as e:
                    logger.warning(f"Could not parse risk_reward ratio string '{rr_str}': {e}")
                    signal["risk_reward"] = None

        # Handle risk_reward as dict -> extract float
        # Claude may return: {'risk_pips': 25.74, 'rr_ratio_tp1': 1.27, 'rr_ratio_tp2': 2.2, ...}
        if "risk_reward" in signal and isinstance(signal["risk_reward"], dict):
            rr_dict = signal["risk_reward"]
            # Priority: rr_ratio_tp1 (first target), then calculate from pips
            if "rr_ratio_tp1" in rr_dict:
                signal["risk_reward"] = float(rr_dict["rr_ratio_tp1"])
                logger.debug(f"Normalized: risk_reward dict -> {signal['risk_reward']} (from rr_ratio_tp1)")
            elif "rr_ratio" in rr_dict:
                signal["risk_reward"] = float(rr_dict["rr_ratio"])
                logger.debug(f"Normalized: risk_reward dict -> {signal['risk_reward']} (from rr_ratio)")
            elif "risk_pips" in rr_dict and "reward_pips_tp1" in rr_dict:
                risk = rr_dict["risk_pips"]
                reward = rr_dict["reward_pips_tp1"]
                if risk > 0:
                    signal["risk_reward"] = round(reward / risk, 2)
                    logger.debug(f"Normalized: risk_reward dict -> {signal['risk_reward']} (calculated)")
                else:
                    signal["risk_reward"] = None
            else:
                # Can't extract a valid R:R, set to None
                signal["risk_reward"] = None
                logger.warning(f"Could not extract risk_reward from dict: {rr_dict.keys()}")

        # Extract wave_position from elliott_wave_analysis
        # Claude may output wave data in signal.elliott_wave_analysis instead of wave_analysis
        elliott_wave = signal.get("elliott_wave_analysis", {})
        if isinstance(elliott_wave, dict) and elliott_wave and "wave_analysis" not in data:
            wave_analysis = {}

            # Try multiple locations for wave position
            wave_position = (
                elliott_wave.get("wave_position") or
                elliott_wave.get("current_wave") or
                elliott_wave.get("primary_count", {}).get("current_wave") or
                elliott_wave.get("primary_count", {}).get("wave_position")
            )

            if wave_position:
                wave_analysis["wave_position"] = str(wave_position)
                logger.debug(f"Normalized: extracted wave_position: {wave_position}")

            # Extract h4_trend from multiple possible locations
            h4_trend = None
            # 1. Try timeframe_analysis.h4.trend (Claude's preferred location)
            timeframe_analysis = signal.get("timeframe_analysis", {})
            h4_data = timeframe_analysis.get("h4", {})
            if isinstance(h4_data, dict) and h4_data.get("trend"):
                h4_trend_raw = str(h4_data["trend"]).lower()
                if "bullish" in h4_trend_raw:
                    h4_trend = "bullish"
                elif "bearish" in h4_trend_raw:
                    h4_trend = "bearish"
                else:
                    h4_trend = h4_trend_raw  # Use as-is if not bullish/bearish
            # 2. Try elliott_wave.h4_structure keyword match
            if not h4_trend:
                h4_structure = elliott_wave.get("h4_structure", "")
                if h4_structure and "bullish" in str(h4_structure).lower():
                    h4_trend = "bullish"
                elif h4_structure and "bearish" in str(h4_structure).lower():
                    h4_trend = "bearish"
            # 3. Try technical_context.h4_trend
            if not h4_trend:
                tech_context = data.get("technical_context", {})
                if isinstance(tech_context, dict):
                    h4_trend = tech_context.get("h4_trend")
            # 4. Default fallback
            if h4_trend:
                wave_analysis["h4_trend"] = h4_trend
            else:
                wave_analysis["h4_trend"] = "unknown"
                logger.debug("Normalized: h4_trend not found, defaulting to 'unknown'")

            # Extract current_wave from multiple locations
            current_wave = (
                elliott_wave.get("current_wave") or
                elliott_wave.get("primary_count") or  # Claude often uses this
                elliott_wave.get("wave_description") or
                wave_position  # Fallback to wave_position if nothing else
            )
            if current_wave:
                wave_analysis["current_wave"] = str(current_wave)

            if wave_analysis:
                data["wave_analysis"] = wave_analysis
                logger.debug("Normalized: created wave_analysis from elliott_wave_analysis")

        # Handle take_profit as single float -> convert to list
        # Claude may return: "take_profit": 4430.0 instead of a list
        if "take_profit" in signal and isinstance(signal["take_profit"], (int, float)):
            tp_price = float(signal["take_profit"])
            signal["take_profit"] = [{
                "level": "TP1",
                "price": tp_price,
                "close_percent": 100  # Single TP = close 100%
            }]
            logger.debug(f"Normalized: take_profit float {tp_price} -> take_profit array")

        # Convert take_profit_1/2/3 to take_profit array
        if "take_profit" not in signal or not signal.get("take_profit"):
            tp_levels = []
            # Default close percentages: TP1=40%, TP2=35%, TP3=25%
            close_percents = [40, 35, 25]
            for i in range(1, 4):
                tp_key = f"take_profit_{i}"
                if tp_key in signal:
                    tp_price = signal.pop(tp_key)
                    if tp_price is not None:
                        tp_levels.append({
                            "level": f"TP{i}",
                            "price": float(tp_price),
                            "close_percent": close_percents[i - 1]
                        })
            if tp_levels:
                signal["take_profit"] = tp_levels
                logger.debug(f"Normalized: take_profit_1/2/3 -> take_profit array ({len(tp_levels)} levels)")

        # Normalize existing take_profit array items
        if "take_profit" in signal and isinstance(signal["take_profit"], list):
            normalized_tps = []
            # Default close percentages for multi-TP
            close_percents = [40, 35, 25]
            for i, tp in enumerate(signal["take_profit"]):
                # Handle list of floats: [4430.0, 4400.0, 4380.0]
                if isinstance(tp, (int, float)):
                    normalized_tps.append({
                        "level": f"TP{i + 1}",
                        "price": float(tp),
                        "close_percent": close_percents[i] if i < len(close_percents) else 100
                    })
                    logger.debug(f"Normalized: take_profit[{i}] float {tp} -> TP{i + 1}")
                    continue
                if isinstance(tp, dict):
                    normalized_tp = dict(tp)

                    # Convert level: int -> str (e.g., 1 -> "TP1")
                    if "level" in normalized_tp:
                        level_val = normalized_tp["level"]
                        if isinstance(level_val, int):
                            normalized_tp["level"] = f"TP{level_val}"
                            logger.debug(f"Normalized: take_profit[{i}].level {level_val} -> TP{level_val}")

                    # Convert ratio -> close_percent (0.5 -> 50)
                    if "ratio" in normalized_tp and "close_percent" not in normalized_tp:
                        ratio = normalized_tp.pop("ratio")
                        if isinstance(ratio, (int, float)):
                            normalized_tp["close_percent"] = int(ratio * 100)
                            logger.debug(f"Normalized: take_profit[{i}].ratio {ratio} -> close_percent {normalized_tp['close_percent']}")

                    normalized_tps.append(normalized_tp)
                else:
                    normalized_tps.append(tp)
            signal["take_profit"] = normalized_tps

        data["signal"] = signal

    # Normalize wave_analysis if present but missing wave_position
    wave_analysis = data.get("wave_analysis", {})
    if isinstance(wave_analysis, dict) and wave_analysis:
        if "wave_position" not in wave_analysis or wave_analysis.get("wave_position") is None:
            current_wave = wave_analysis.get("current_wave", "")
            if current_wave:
                wave_analysis["wave_position"] = str(current_wave)
                logger.debug(f"Normalized: wave_position from current_wave: {current_wave}")
        data["wave_analysis"] = wave_analysis

    return data


def extract_json_from_response(response: str) -> Optional[dict]:
    """Extract JSON from Claude CLI response.

    Tries multiple extraction strategies:
    1. JSON code block (```json ... ```)
    2. Generic code block (``` ... ```)
    3. Raw JSON object at start ({ ... })
    4. JSON object anywhere in response (handles prose before JSON)
    5. Markdown fallback - parse structured data from markdown tables/text

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

    # Strategy 5: Markdown fallback - extract data from markdown analysis
    result = _extract_signal_from_markdown(response)
    if result:
        logger.info("Extracted signal via Strategy 5 (markdown fallback)")
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

    # Normalize LLM output to match expected schema
    json_data = _normalize_signal_data(json_data)

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
