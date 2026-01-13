"""Volatility-based adaptive system for dynamic risk management.

Features:
- Multi-timeframe volatility analysis
- Volatility regime classification
- Dynamic stop loss adjustment
- Adaptive position sizing
- Volatility-based entry filtering
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List, Tuple

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class VolatilityState(str, Enum):
    """Volatility state classifications."""
    
    COMPRESSION = "compression"  # Very low volatility, potential breakout
    LOW = "low"                  # Below average volatility
    NORMAL = "normal"            # Average volatility
    ELEVATED = "elevated"        # Above average volatility
    HIGH = "high"               # High volatility
    EXTREME = "extreme"         # Extreme volatility, caution


@dataclass
class VolatilityProfile:
    """Comprehensive volatility analysis result."""
    
    state: VolatilityState
    current_atr: float              # Current ATR value
    atr_percentile: int            # 0-100 percentile
    volatility_ratio: float        # Current vs average
    volatility_trend: str          # increasing/decreasing/stable
    expansion_signal: bool         # Volatility expansion detected
    compression_zones: List[Tuple[float, float]]  # Price ranges of compression
    sl_adjustment_factor: float    # Multiplier for stop loss
    position_size_factor: float    # Multiplier for position size
    entry_filter: str             # allow/caution/avoid
    confidence_impact: int        # -20 to +10 adjustment
    description: str


class VolatilityManager:
    """Manages volatility analysis and adaptive adjustments."""
    
    def __init__(self):
        from src.config import get_settings
        self.settings = get_settings()
        
        # Volatility thresholds (ATR ratio to baseline average)
        # Values < 1.0 = below average, values > 1.0 = above average
        self.compression_ratio = 0.7   # ATR < 70% of average = compression
        self.low_ratio = 0.85          # ATR < 85% of average = low volatility
        self.high_ratio = 1.3          # ATR > 130% of average = high volatility
        self.extreme_ratio = 1.8       # ATR > 180% of average = extreme volatility
        
        # ATR lookback periods
        self.atr_fast = 10
        self.atr_slow = 50
        self.percentile_lookback = 100
        
    def analyze_volatility(self, h4_data: pd.DataFrame, h1_data: pd.DataFrame, 
                          m30_data: pd.DataFrame) -> VolatilityProfile:
        """Perform comprehensive volatility analysis.
        
        Args:
            h4_data: H4 timeframe data with ATR
            h1_data: H1 timeframe data with ATR
            m30_data: M30 timeframe data with ATR
            
        Returns:
            VolatilityProfile with analysis results
        """
        try:
            # Get current and historical ATR values
            h4_atr = self._get_atr_analysis(h4_data, 'H4')
            h1_atr = self._get_atr_analysis(h1_data, 'H1')
            m30_atr = self._get_atr_analysis(m30_data, 'M30')
            
            # Weight timeframes (H4 most important for position sizing)
            weighted_atr = (h4_atr['current'] * 0.5 + 
                          h1_atr['current'] * 0.3 + 
                          m30_atr['current'] * 0.2)
            
            weighted_percentile = int(
                h4_atr['percentile'] * 0.5 + 
                h1_atr['percentile'] * 0.3 + 
                m30_atr['percentile'] * 0.2
            )
            
            # Calculate volatility ratio (current vs average)
            volatility_ratio = h4_atr['ratio']
            
            # Determine volatility trend
            volatility_trend = self._calculate_volatility_trend(h4_data)
            
            # Check for volatility expansion
            expansion_signal = self._detect_volatility_expansion(
                h4_data, h1_data
            )
            
            # Find compression zones
            compression_zones = self._find_compression_zones(h4_data)
            
            # Determine volatility state
            state = self._determine_volatility_state(
                volatility_ratio, weighted_percentile
            )
            
            # Calculate adjustments
            sl_factor = self._calculate_sl_adjustment(state, volatility_ratio)
            position_factor = self._calculate_position_adjustment(
                state, volatility_trend, expansion_signal
            )
            entry_filter = self._determine_entry_filter(
                state, volatility_trend, expansion_signal
            )
            confidence_impact = self._calculate_confidence_impact(
                state, volatility_trend
            )
            
            # Build description
            description = self._build_volatility_description(
                state, volatility_ratio, volatility_trend, expansion_signal
            )
            
            return VolatilityProfile(
                state=state,
                current_atr=weighted_atr,
                atr_percentile=weighted_percentile,
                volatility_ratio=volatility_ratio,
                volatility_trend=volatility_trend,
                expansion_signal=expansion_signal,
                compression_zones=compression_zones,
                sl_adjustment_factor=sl_factor,
                position_size_factor=position_factor,
                entry_filter=entry_filter,
                confidence_impact=confidence_impact,
                description=description
            )
            
        except Exception as e:
            logger.error(f"Volatility analysis failed: {e}")
            # Return conservative profile on error
            return VolatilityProfile(
                state=VolatilityState.NORMAL,
                current_atr=10,
                atr_percentile=50,
                volatility_ratio=1.0,
                volatility_trend="stable",
                expansion_signal=False,
                compression_zones=[],
                sl_adjustment_factor=1.0,
                position_size_factor=1.0,
                entry_filter="caution",
                confidence_impact=0,
                description="Unable to analyze volatility"
            )
    
    def _get_atr_analysis(self, data: pd.DataFrame, timeframe: str) -> dict:
        """Analyze ATR for a specific timeframe."""
        if 'atr_14' not in data.columns:
            logger.warning(f"No ATR data for {timeframe}")
            return {'current': 10, 'average': 10, 'ratio': 1.0, 'percentile': 50}
        
        # Get ATR values
        atr_series = data['atr_14'].tail(self.percentile_lookback)
        current_atr = atr_series.iloc[-1]
        
        # Calculate statistics
        avg_atr = atr_series.mean()
        percentile = (atr_series < current_atr).sum() / len(atr_series) * 100
        ratio = current_atr / avg_atr if avg_atr > 0 else 1.0
        
        logger.debug(
            f"{timeframe} ATR: current={current_atr:.2f}, "
            f"avg={avg_atr:.2f}, ratio={ratio:.2f}"
        )
        
        return {
            'current': current_atr,
            'average': avg_atr,
            'ratio': ratio,
            'percentile': int(percentile)
        }
    
    def _calculate_volatility_trend(self, data: pd.DataFrame) -> str:
        """Determine if volatility is expanding, contracting, or stable."""
        if 'atr_14' not in data.columns:
            return "stable"
        
        # Compare recent ATR to longer-term ATR
        atr = data['atr_14'].tail(20)
        if len(atr) < 20:
            return "stable"
        
        # Fast vs slow ATR
        fast_atr = atr.tail(5).mean()
        slow_atr = atr.mean()
        
        ratio = fast_atr / slow_atr
        
        if ratio > 1.15:
            return "increasing"
        elif ratio < 0.85:
            return "decreasing"
        else:
            return "stable"
    
    def _detect_volatility_expansion(self, h4_data: pd.DataFrame, 
                                   h1_data: pd.DataFrame) -> bool:
        """Detect sudden volatility expansion (potential breakout)."""
        try:
            # Check H4 for expansion
            h4_atr = h4_data['atr_14'].tail(10)
            if len(h4_atr) >= 3:
                recent = h4_atr.iloc[-1]
                previous = h4_atr.iloc[-3:-1].mean()
                if recent > previous * 1.5:  # 50% increase
                    return True
            
            # Check H1 for faster expansion
            h1_atr = h1_data['atr_14'].tail(20)
            if len(h1_atr) >= 5:
                recent = h1_atr.iloc[-2:].mean()
                previous = h1_atr.iloc[-10:-2].mean()
                if recent > previous * 1.3:  # 30% increase
                    return True
                    
            return False
            
        except Exception as e:
            logger.debug(f"Expansion detection error: {e}")
            return False
    
    def _find_compression_zones(self, data: pd.DataFrame) -> List[Tuple[float, float]]:
        """Identify price ranges with compressed volatility."""
        zones = []
        
        try:
            # Look for periods of low ATR
            atr = data['atr_14'].tail(50)
            highs = data['high'].tail(50)
            lows = data['low'].tail(50)
            
            if len(atr) < 20:
                return zones
            
            # Find compression periods (ATR < 80% of average)
            avg_atr = atr.mean()
            compression_mask = atr < (avg_atr * 0.8)
            
            # Extract price ranges during compression
            i = 0
            while i < len(compression_mask):
                if compression_mask.iloc[i]:
                    start = i
                    while i < len(compression_mask) and compression_mask.iloc[i]:
                        i += 1
                    end = i - 1
                    
                    # Get price range for this compression period
                    zone_high = highs.iloc[start:end+1].max()
                    zone_low = lows.iloc[start:end+1].min()
                    zones.append((zone_low, zone_high))
                else:
                    i += 1
            
            # Merge overlapping zones
            zones = self._merge_overlapping_zones(zones)
            
            # Keep only recent zones (last 3)
            return zones[-3:] if zones else []
            
        except Exception as e:
            logger.debug(f"Compression zone detection error: {e}")
            return []
    
    def _merge_overlapping_zones(self, zones: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Merge overlapping compression zones."""
        if not zones:
            return zones
        
        zones.sort(key=lambda x: x[0])  # Sort by lower bound
        merged = [zones[0]]
        
        for current in zones[1:]:
            last = merged[-1]
            # Check if zones overlap
            if current[0] <= last[1]:
                # Merge zones
                merged[-1] = (min(last[0], current[0]), max(last[1], current[1]))
            else:
                merged.append(current)
        
        return merged
    
    def _determine_volatility_state(self, ratio: float, percentile: int) -> VolatilityState:
        """Determine current volatility state."""
        # Check for compression first
        if ratio < self.compression_ratio and percentile < 20:
            return VolatilityState.COMPRESSION
        
        # Then check extremes
        if ratio > self.extreme_ratio or percentile > 95:
            return VolatilityState.EXTREME
        elif ratio > self.high_ratio or percentile > 85:
            return VolatilityState.HIGH
        elif percentile > 70:
            return VolatilityState.ELEVATED
        elif ratio < self.low_ratio or percentile < 30:
            return VolatilityState.LOW
        else:
            return VolatilityState.NORMAL
    
    def _calculate_sl_adjustment(self, state: VolatilityState, ratio: float) -> float:
        """Calculate stop loss adjustment factor based on volatility."""
        adjustments = {
            VolatilityState.COMPRESSION: 0.8,   # Tighter stops in compression
            VolatilityState.LOW: 0.9,
            VolatilityState.NORMAL: 1.0,
            VolatilityState.ELEVATED: 1.1,
            VolatilityState.HIGH: 1.3,
            VolatilityState.EXTREME: 1.5        # Wider stops in extreme volatility
        }
        
        base = adjustments.get(state, 1.0)
        
        # Fine-tune based on exact ratio
        if ratio > 2.0:
            base *= 1.1
        elif ratio < 0.5:
            base *= 0.9
            
        return round(base, 2)
    
    def _calculate_position_adjustment(self, state: VolatilityState, 
                                     trend: str, expansion: bool) -> float:
        """Calculate position size adjustment based on volatility."""
        # Base adjustments by state
        adjustments = {
            VolatilityState.COMPRESSION: 0.8,   # Smaller before breakout
            VolatilityState.LOW: 1.1,          # Can be larger in low vol
            VolatilityState.NORMAL: 1.0,
            VolatilityState.ELEVATED: 0.9,
            VolatilityState.HIGH: 0.7,
            VolatilityState.EXTREME: 0.5       # Much smaller in extreme vol
        }
        
        factor = adjustments.get(state, 1.0)
        
        # Adjust for volatility trend
        if trend == "increasing" and state != VolatilityState.LOW:
            factor *= 0.9  # More conservative when vol expanding
        elif trend == "decreasing" and state != VolatilityState.EXTREME:
            factor *= 1.05  # Slightly larger when vol contracting
        
        # Caution during expansion breakouts
        if expansion and state == VolatilityState.COMPRESSION:
            factor *= 0.7  # Extra caution during breakout
            
        return round(factor, 2)
    
    def _determine_entry_filter(self, state: VolatilityState, 
                               trend: str, expansion: bool) -> str:
        """Determine if entries should be filtered based on volatility."""
        if state == VolatilityState.EXTREME:
            return "avoid"  # No new entries in extreme volatility
        
        if state == VolatilityState.HIGH and trend == "increasing":
            return "avoid"  # Avoid entries when volatility expanding to highs
        
        if expansion and state == VolatilityState.COMPRESSION:
            return "caution"  # Be careful during potential breakouts
        
        if state in [VolatilityState.HIGH, VolatilityState.ELEVATED]:
            return "caution"  # Need higher confidence
            
        return "allow"  # Normal entry conditions
    
    def _calculate_confidence_impact(self, state: VolatilityState, trend: str) -> int:
        """Calculate confidence score impact from volatility."""
        impacts = {
            VolatilityState.COMPRESSION: 5,     # Potential breakout opportunity
            VolatilityState.LOW: 0,
            VolatilityState.NORMAL: 0,
            VolatilityState.ELEVATED: -5,
            VolatilityState.HIGH: -10,
            VolatilityState.EXTREME: -20
        }
        
        impact = impacts.get(state, 0)
        
        # Additional penalty for expanding volatility
        if trend == "increasing" and state in [VolatilityState.HIGH, VolatilityState.EXTREME]:
            impact -= 5
            
        return impact
    
    def _build_volatility_description(self, state: VolatilityState, ratio: float,
                                    trend: str, expansion: bool) -> str:
        """Build human-readable volatility description."""
        desc_parts = []
        
        # State description
        state_desc = {
            VolatilityState.COMPRESSION: "Volatility compression detected",
            VolatilityState.LOW: "Low volatility environment",
            VolatilityState.NORMAL: "Normal volatility levels",
            VolatilityState.ELEVATED: "Elevated volatility",
            VolatilityState.HIGH: "High volatility conditions",
            VolatilityState.EXTREME: "Extreme volatility - exercise caution"
        }
        desc_parts.append(state_desc.get(state, "Unknown volatility"))
        
        # Ratio info
        desc_parts.append(f"(current/avg: {ratio:.2f})")
        
        # Trend info
        if trend != "stable":
            desc_parts.append(f"- volatility {trend}")
            
        # Expansion warning
        if expansion:
            desc_parts.append("- EXPANSION BREAKOUT detected")
            
        return " ".join(desc_parts)
    
    def calculate_dynamic_stop_loss(self, entry_price: float, direction: str,
                                   atr: float, sl_factor: float) -> float:
        """Calculate dynamic stop loss based on current volatility.
        
        Args:
            entry_price: Entry price for the trade
            direction: 'BUY' or 'SELL'
            atr: Current ATR value
            sl_factor: Adjustment factor from volatility profile
            
        Returns:
            Adjusted stop loss price
        """
        # Base ATR multiplier from settings
        base_multiplier = self.settings.trail_atr_multiplier
        
        # Apply volatility adjustment
        adjusted_multiplier = base_multiplier * sl_factor
        
        # Calculate stop distance
        stop_distance = atr * adjusted_multiplier
        
        # Apply to price based on direction
        if direction == 'BUY':
            stop_loss = entry_price - stop_distance
        else:
            stop_loss = entry_price + stop_distance
            
        # Round to appropriate decimal places (assuming 2 for gold)
        return round(stop_loss, 2)
    
    def calculate_position_size(self, base_lots: float, 
                              position_factor: float,
                              confidence: int) -> float:
        """Calculate adjusted position size based on volatility.
        
        Args:
            base_lots: Base position size from risk calculation
            position_factor: Adjustment factor from volatility profile
            confidence: Signal confidence (0-100)
            
        Returns:
            Adjusted position size in lots
        """
        # Apply volatility adjustment
        adjusted_lots = base_lots * position_factor
        
        # Further adjust based on confidence in volatile markets
        if position_factor < 0.8 and confidence < 70:
            # Extra conservative in high volatility with lower confidence
            adjusted_lots *= 0.8
            
        # Ensure minimum lot size
        min_lots = 0.01
        adjusted_lots = max(adjusted_lots, min_lots)
        
        # Round to lot step (typically 0.01)
        return round(adjusted_lots, 2)
    
    def should_filter_entry(self, entry_filter: str, confidence: int) -> bool:
        """Determine if trade entry should be filtered.
        
        Args:
            entry_filter: Filter level from volatility profile
            confidence: Signal confidence
            
        Returns:
            True if entry should be blocked
        """
        if entry_filter == "avoid":
            return True
            
        if entry_filter == "caution" and confidence < 70:
            return True
            
        return False
    
    def get_volatility_dashboard(self, profile: VolatilityProfile) -> str:
        """Generate volatility dashboard for logging/display.
        
        Args:
            profile: Current volatility profile
            
        Returns:
            Formatted dashboard string
        """
        dashboard = [
            "=== Volatility Dashboard ===",
            f"State: {profile.state.value}",
            f"ATR Percentile: {profile.atr_percentile}%",
            f"Volatility Ratio: {profile.volatility_ratio:.2f}",
            f"Trend: {profile.volatility_trend}",
            f"Entry Filter: {profile.entry_filter}",
            f"SL Adjustment: {profile.sl_adjustment_factor:.2f}x",
            f"Position Size: {profile.position_size_factor:.2f}x",
            f"Confidence Impact: {profile.confidence_impact:+d}",
        ]
        
        if profile.expansion_signal:
            dashboard.append("⚠️ VOLATILITY EXPANSION DETECTED")
            
        if profile.compression_zones:
            dashboard.append(f"Compression Zones: {len(profile.compression_zones)}")
            
        return "\n".join(dashboard)


# Singleton instance
_volatility_manager: Optional[VolatilityManager] = None


def get_volatility_manager() -> VolatilityManager:
    """Get or create volatility manager singleton."""
    global _volatility_manager
    if _volatility_manager is None:
        _volatility_manager = VolatilityManager()
    return _volatility_manager