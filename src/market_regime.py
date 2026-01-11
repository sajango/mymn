"""Market regime detection for adaptive trading strategies.

Identifies market conditions:
- Trending (up/down, strong/weak)
- Ranging (tight/wide)
- Volatile (high/extreme)

Uses multiple indicators:
- ADX for trend strength
- ATR percentiles for volatility
- Price vs EMAs for direction
- Range detection algorithms
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class RegimeType(str, Enum):
    """Market regime classifications."""
    
    STRONG_TREND_UP = "strong_trend_up"
    TREND_UP = "trend_up"
    RANGING_TIGHT = "ranging_tight"
    RANGING_WIDE = "ranging_wide"
    TREND_DOWN = "trend_down"
    STRONG_TREND_DOWN = "strong_trend_down"
    HIGH_VOLATILITY = "high_volatility"
    EXTREME_VOLATILITY = "extreme_volatility"


@dataclass
class MarketRegime:
    """Market regime analysis result."""
    
    regime_type: RegimeType
    confidence: int  # 0-100
    trend_strength: float  # ADX value
    volatility_percentile: int  # 0-100
    volatility_state: str  # low/normal/high/extreme
    direction_bias: str  # bullish/bearish/neutral
    confidence_modifier: int  # -20 to +20
    risk_multiplier: float  # 0.5 to 1.5
    description: str


class MarketRegimeDetector:
    """Detects current market regime from price and indicator data."""
    
    def __init__(self):
        from src.config import get_settings
        settings = get_settings()
        
        self.trend_threshold_weak = settings.regime_trend_threshold_weak
        self.trend_threshold_strong = settings.regime_trend_threshold_strong
        self.volatility_thresholds = {
            'low': settings.regime_volatility_low,
            'normal': 50,  # Midpoint
            'high': settings.regime_volatility_high,
            'extreme': settings.regime_volatility_extreme
        }
        
    def detect_regime(self, h4_data: pd.DataFrame, h1_data: pd.DataFrame) -> MarketRegime:
        """Detect current market regime from H4 and H1 data.
        
        Args:
            h4_data: H4 timeframe data with OHLCV and indicators
            h1_data: H1 timeframe data with OHLCV and indicators
            
        Returns:
            MarketRegime with analysis results
        """
        try:
            # Get latest values
            h4_latest = h4_data.iloc[-1]
            h1_latest = h1_data.iloc[-1]
            
            # Calculate trend strength (use ADX if available, else calculate)
            trend_strength = self._calculate_trend_strength(h4_data)
            
            # Calculate volatility state
            volatility_percentile = self._calculate_volatility_percentile(h4_data)
            volatility_state = self._get_volatility_state(volatility_percentile)
            
            # Determine direction bias
            direction_bias = self._calculate_direction_bias(h4_data, h1_data)
            
            # Determine regime type
            regime_type = self._determine_regime_type(
                trend_strength, volatility_state, direction_bias
            )
            
            # Calculate modifiers
            confidence_modifier = self._calculate_confidence_modifier(
                regime_type, volatility_state
            )
            risk_multiplier = self._calculate_risk_multiplier(
                volatility_state, regime_type
            )
            
            # Build description
            description = self._build_regime_description(
                regime_type, trend_strength, volatility_state
            )
            
            return MarketRegime(
                regime_type=regime_type,
                confidence=self._calculate_regime_confidence(trend_strength, volatility_state),
                trend_strength=trend_strength,
                volatility_percentile=volatility_percentile,
                volatility_state=volatility_state,
                direction_bias=direction_bias,
                confidence_modifier=confidence_modifier,
                risk_multiplier=risk_multiplier,
                description=description
            )
            
        except Exception as e:
            logger.error(f"Regime detection failed: {e}")
            # Return neutral regime on error
            return MarketRegime(
                regime_type=RegimeType.RANGING_WIDE,
                confidence=50,
                trend_strength=0,
                volatility_percentile=50,
                volatility_state="normal",
                direction_bias="neutral",
                confidence_modifier=0,
                risk_multiplier=1.0,
                description="Unable to determine regime"
            )
    
    def _calculate_trend_strength(self, data: pd.DataFrame) -> float:
        """Calculate trend strength using ADX or price/EMA relationship."""
        # Check if ADX is available
        if 'adx_14' in data.columns:
            return data['adx_14'].iloc[-1]
        
        # Fallback: Calculate trend strength from price vs EMAs
        latest = data.iloc[-1]
        close = latest['close']
        ema_34 = latest['ema_34']
        ema_89 = latest['ema_89']
        
        # Calculate percentage distances
        dist_34 = abs(close - ema_34) / ema_34 * 100
        dist_89 = abs(close - ema_89) / ema_89 * 100
        
        # Estimate trend strength (0-100 scale like ADX)
        if close > ema_34 > ema_89 or close < ema_34 < ema_89:
            # Trending condition
            trend_strength = min(dist_34 + dist_89, 50)  # Cap at 50 for estimation
        else:
            # Non-trending
            trend_strength = max(10 - dist_34, 0)
            
        return trend_strength
    
    def _calculate_volatility_percentile(self, data: pd.DataFrame) -> int:
        """Calculate current ATR percentile over lookback period."""
        if 'atr_14' not in data.columns:
            return 50  # Default to normal if no ATR
            
        # Get last 100 periods of ATR
        atr_series = data['atr_14'].tail(100)
        current_atr = atr_series.iloc[-1]
        
        # Calculate percentile
        percentile = (atr_series < current_atr).sum() / len(atr_series) * 100
        return int(percentile)
    
    def _get_volatility_state(self, percentile: int) -> str:
        """Convert volatility percentile to state."""
        if percentile < self.volatility_thresholds['low']:
            return 'low'
        elif percentile < self.volatility_thresholds['normal']:
            return 'normal'
        elif percentile < self.volatility_thresholds['high']:
            return 'high'
        elif percentile < self.volatility_thresholds['extreme']:
            return 'high'
        else:
            return 'extreme'
    
    def _calculate_direction_bias(self, h4_data: pd.DataFrame, h1_data: pd.DataFrame) -> str:
        """Determine market direction bias."""
        h4_latest = h4_data.iloc[-1]
        h1_latest = h1_data.iloc[-1]
        
        # Price vs EMAs on H4
        h4_bullish = h4_latest['close'] > h4_latest['ema_34'] > h4_latest['ema_89']
        h4_bearish = h4_latest['close'] < h4_latest['ema_34'] < h4_latest['ema_89']
        
        # Price vs EMAs on H1  
        h1_bullish = h1_latest['close'] > h1_latest['ema_34']
        h1_bearish = h1_latest['close'] < h1_latest['ema_34']
        
        # MACD momentum
        h4_macd_bullish = h4_latest['macd'] > h4_latest['macd_signal']
        h1_macd_bullish = h1_latest['macd'] > h1_latest['macd_signal']
        
        # Combine signals
        bullish_score = sum([h4_bullish, h1_bullish, h4_macd_bullish, h1_macd_bullish])
        bearish_score = sum([h4_bearish, h1_bearish, not h4_macd_bullish, not h1_macd_bullish])
        
        if bullish_score >= 3:
            return 'bullish'
        elif bearish_score >= 3:
            return 'bearish'
        else:
            return 'neutral'
    
    def _determine_regime_type(self, trend_strength: float, volatility: str, direction: str) -> RegimeType:
        """Determine regime type from components."""
        # Check for extreme volatility first
        if volatility == 'extreme':
            return RegimeType.EXTREME_VOLATILITY
        elif volatility == 'high':
            # High volatility can override trend
            if trend_strength < self.trend_threshold_weak:
                return RegimeType.HIGH_VOLATILITY
        
        # Trend-based regimes
        if trend_strength >= self.trend_threshold_strong:
            if direction == 'bullish':
                return RegimeType.STRONG_TREND_UP
            elif direction == 'bearish':
                return RegimeType.STRONG_TREND_DOWN
            else:
                return RegimeType.RANGING_WIDE  # Strong ADX but no clear direction
                
        elif trend_strength >= self.trend_threshold_weak:
            if direction == 'bullish':
                return RegimeType.TREND_UP
            elif direction == 'bearish':
                return RegimeType.TREND_DOWN
            else:
                return RegimeType.RANGING_WIDE
        
        # Range-bound regimes
        else:
            if volatility == 'low':
                return RegimeType.RANGING_TIGHT
            else:
                return RegimeType.RANGING_WIDE
    
    def _calculate_confidence_modifier(self, regime: RegimeType, volatility: str) -> int:
        """Calculate confidence adjustment based on regime."""
        modifiers = {
            RegimeType.STRONG_TREND_UP: 10,
            RegimeType.STRONG_TREND_DOWN: 10,
            RegimeType.TREND_UP: 5,
            RegimeType.TREND_DOWN: 5,
            RegimeType.RANGING_TIGHT: -5,
            RegimeType.RANGING_WIDE: -10,
            RegimeType.HIGH_VOLATILITY: -15,
            RegimeType.EXTREME_VOLATILITY: -20
        }
        
        base_modifier = modifiers.get(regime, 0)
        
        # Additional penalty for extreme volatility
        if volatility == 'extreme':
            base_modifier -= 5
            
        return base_modifier
    
    def _calculate_risk_multiplier(self, volatility: str, regime: RegimeType) -> float:
        """Calculate position size multiplier based on conditions."""
        # Base multipliers by volatility
        volatility_multipliers = {
            'low': 1.2,
            'normal': 1.0,
            'high': 0.7,
            'extreme': 0.5
        }
        
        base = volatility_multipliers.get(volatility, 1.0)
        
        # Adjust for regime
        if regime in [RegimeType.STRONG_TREND_UP, RegimeType.STRONG_TREND_DOWN]:
            base *= 1.1  # Slightly larger in strong trends
        elif regime in [RegimeType.HIGH_VOLATILITY, RegimeType.EXTREME_VOLATILITY]:
            base *= 0.8  # More conservative in volatile markets
            
        return round(base, 2)
    
    def _calculate_regime_confidence(self, trend_strength: float, volatility: str) -> int:
        """Calculate confidence in regime detection."""
        # Base confidence on trend strength clarity
        if trend_strength > 40:
            confidence = 90
        elif trend_strength > 25:
            confidence = 75
        elif trend_strength > 15:
            confidence = 60
        else:
            confidence = 50
            
        # Adjust for volatility
        if volatility == 'extreme':
            confidence -= 10
        elif volatility == 'low':
            confidence += 5
            
        return max(min(confidence, 100), 30)
    
    def _build_regime_description(self, regime: RegimeType, trend_strength: float, volatility: str) -> str:
        """Build human-readable regime description."""
        descriptions = {
            RegimeType.STRONG_TREND_UP: f"Strong uptrend (ADX: {trend_strength:.1f})",
            RegimeType.STRONG_TREND_DOWN: f"Strong downtrend (ADX: {trend_strength:.1f})",
            RegimeType.TREND_UP: f"Moderate uptrend (ADX: {trend_strength:.1f})",
            RegimeType.TREND_DOWN: f"Moderate downtrend (ADX: {trend_strength:.1f})",
            RegimeType.RANGING_TIGHT: f"Tight range, low volatility",
            RegimeType.RANGING_WIDE: f"Wide range, choppy market",
            RegimeType.HIGH_VOLATILITY: f"High volatility conditions ({volatility})",
            RegimeType.EXTREME_VOLATILITY: f"Extreme volatility - caution advised"
        }
        
        return descriptions.get(regime, "Unknown regime")
    
    def apply_regime_adjustments(self, signal, regime: MarketRegime):
        """Apply regime-based adjustments to trading signal.
        
        Args:
            signal: Trading signal to adjust
            regime: Current market regime
            
        Returns:
            Modified signal
        """
        # Adjust confidence
        original_confidence = signal.signal.confidence
        adjusted_confidence = original_confidence + regime.confidence_modifier
        adjusted_confidence = max(min(adjusted_confidence, 100), 0)
        signal.signal.confidence = adjusted_confidence
        
        logger.info(
            f"Regime adjustment: {original_confidence}% "
            f"{regime.confidence_modifier:+d} = {adjusted_confidence}% "
            f"({regime.description})"
        )
        
        return signal


# Singleton instance
_regime_detector: Optional[MarketRegimeDetector] = None


def get_regime_detector() -> MarketRegimeDetector:
    """Get or create regime detector singleton."""
    global _regime_detector
    if _regime_detector is None:
        _regime_detector = MarketRegimeDetector()
    return _regime_detector