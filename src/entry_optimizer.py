"""Entry optimization system for improved trade timing.

Features:
- Multi-timeframe entry confirmation
- Momentum-based entry filtering
- Spread-aware entry timing
- Limit order optimization
- Entry zone identification
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class EntryType(str, Enum):
    """Entry order types."""
    
    MARKET = "market"              # Immediate market order
    LIMIT_AGGRESSIVE = "limit_aggressive"  # Close to market
    LIMIT_PATIENT = "limit_patient"        # Wait for better price
    SCALE_IN = "scale_in"          # Multiple entries
    MOMENTUM = "momentum"          # Wait for momentum confirmation


@dataclass
class EntryZone:
    """Optimal entry price zone."""
    
    best_entry: float             # Ideal entry price
    acceptable_entry: float       # Acceptable entry price
    max_entry: float             # Maximum acceptable entry
    zone_width_pips: float
    confidence: int              # Confidence in zone


@dataclass
class EntryPlan:
    """Complete entry execution plan."""
    
    entry_type: EntryType
    entry_zones: List[EntryZone]
    recommended_price: float
    market_price: float
    limit_offset_pips: float
    scale_in_levels: Optional[List[float]] = None
    momentum_threshold: Optional[float] = None
    max_wait_minutes: int = 5
    spread_threshold_pips: float = 2.0


@dataclass
class MomentumProfile:
    """Current momentum analysis."""
    
    direction: str               # bullish/bearish/neutral
    strength: float             # 0-100
    acceleration: float         # Rate of change
    alignment: Dict[str, bool]  # Timeframe alignment
    volume_confirmation: bool


class EntryOptimizer:
    """Optimizes trade entries for better fills and timing."""
    
    def __init__(self):
        from src.config import get_settings
        self.settings = get_settings()
        
        # Entry configuration
        self.max_spread_multiplier = 1.5  # Max spread vs normal
        self.momentum_threshold = 60       # Minimum momentum strength
        self.alignment_requirement = 0.7   # 70% timeframe alignment
        
        # Historical entry performance
        self.entry_performance = {
            entry_type: {'trades': 0, 'avg_slippage': 0, 'success_rate': 0}
            for entry_type in EntryType
        }
    
    def optimize_entry(self,
                      signal_price: float,
                      market_price: float,
                      direction: str,
                      confidence: int,
                      volatility_state: str,
                      spread_pips: float,
                      market_data: Dict[str, pd.DataFrame]) -> EntryPlan:
        """Create optimized entry plan.
        
        Args:
            signal_price: Price where signal was generated
            market_price: Current market price
            direction: 'BUY' or 'SELL'
            confidence: Signal confidence
            volatility_state: Current volatility state
            spread_pips: Current spread in pips
            market_data: Dict of dataframes by timeframe
            
        Returns:
            EntryPlan with execution instructions
        """
        # Analyze momentum across timeframes
        momentum = self._analyze_momentum(market_data, direction)
        
        # Identify entry zones
        zones = self._identify_entry_zones(
            signal_price, market_price, direction,
            volatility_state, market_data
        )
        
        # Select entry type based on conditions
        entry_type = self._select_entry_type(
            confidence, momentum, volatility_state,
            spread_pips, zones
        )
        
        # Calculate entry parameters
        if entry_type == EntryType.MARKET:
            plan = self._create_market_entry_plan(
                market_price, spread_pips, zones
            )
        elif entry_type == EntryType.LIMIT_AGGRESSIVE:
            plan = self._create_aggressive_limit_plan(
                market_price, direction, spread_pips, zones
            )
        elif entry_type == EntryType.LIMIT_PATIENT:
            plan = self._create_patient_limit_plan(
                market_price, direction, zones, volatility_state
            )
        elif entry_type == EntryType.SCALE_IN:
            plan = self._create_scale_in_plan(
                market_price, direction, zones, confidence
            )
        else:  # MOMENTUM
            plan = self._create_momentum_plan(
                market_price, direction, momentum, zones
            )
        
        # Add spread threshold based on volatility
        plan.spread_threshold_pips = self._calculate_spread_threshold(
            volatility_state, confidence
        )
        
        return plan
    
    def _analyze_momentum(self, market_data: Dict[str, pd.DataFrame], 
                         direction: str) -> MomentumProfile:
        """Analyze momentum across timeframes."""
        alignments = {}
        total_strength = 0
        
        timeframes = ['M15', 'M30', 'H1', 'H4']
        weights = {'M15': 0.15, 'M30': 0.25, 'H1': 0.35, 'H4': 0.25}
        
        for tf in timeframes:
            if tf in market_data:
                data = market_data[tf]
                
                # Check price vs EMA
                latest = data.iloc[-1]
                ema_aligned = (
                    (direction == 'BUY' and latest['close'] > latest['ema_34']) or
                    (direction == 'SELL' and latest['close'] < latest['ema_34'])
                )
                alignments[tf] = ema_aligned
                
                # Calculate momentum strength
                if 'rsi_14' in data.columns:
                    rsi = latest['rsi_14']
                    if direction == 'BUY':
                        strength = max(0, (rsi - 50) * 2)  # 0-100
                    else:
                        strength = max(0, (50 - rsi) * 2)  # 0-100
                    
                    total_strength += strength * weights.get(tf, 0.25)
        
        # Calculate acceleration (momentum change)
        acceleration = 0
        if 'H1' in market_data:
            h1_data = market_data['H1']
            if len(h1_data) >= 3 and 'rsi_14' in h1_data.columns:
                recent_rsi = h1_data['rsi_14'].tail(3).values
                acceleration = recent_rsi[-1] - recent_rsi[0]
        
        # Volume confirmation (simplified)
        volume_confirmation = True  # Would check volume patterns
        
        # Overall direction
        aligned_count = sum(1 for a in alignments.values() if a)
        if aligned_count >= len(alignments) * 0.7:
            momentum_dir = 'bullish' if direction == 'BUY' else 'bearish'
        else:
            momentum_dir = 'neutral'
        
        return MomentumProfile(
            direction=momentum_dir,
            strength=total_strength,
            acceleration=acceleration,
            alignment=alignments,
            volume_confirmation=volume_confirmation
        )
    
    def _identify_entry_zones(self, signal_price: float, market_price: float,
                            direction: str, volatility_state: str,
                            market_data: Dict[str, pd.DataFrame]) -> List[EntryZone]:
        """Identify optimal entry zones."""
        zones = []
        
        # Get ATR for zone width
        atr = 10  # Default
        if 'H1' in market_data:
            h1_data = market_data['H1']
            if 'atr_14' in h1_data.columns:
                atr = h1_data['atr_14'].iloc[-1]
        
        # Zone 1: Immediate zone around current price
        zone_width = atr * 0.2  # 20% of ATR
        if direction == 'BUY':
            best = market_price - zone_width * 0.3
            acceptable = market_price
            max_entry = market_price + zone_width * 0.5
        else:
            best = market_price + zone_width * 0.3
            acceptable = market_price
            max_entry = market_price - zone_width * 0.5
        
        zones.append(EntryZone(
            best_entry=round(best, 2),
            acceptable_entry=round(acceptable, 2),
            max_entry=round(max_entry, 2),
            zone_width_pips=zone_width / 0.1,  # Convert to pips
            confidence=80
        ))
        
        # Zone 2: Support/Resistance based
        sr_levels = self._find_sr_levels(market_data, direction)
        for level in sr_levels[:2]:  # Top 2 levels
            if direction == 'BUY':
                # Buy at support
                if level < market_price:
                    zones.append(EntryZone(
                        best_entry=level,
                        acceptable_entry=level + atr * 0.1,
                        max_entry=level + atr * 0.2,
                        zone_width_pips=atr * 0.2 / 0.1,
                        confidence=70
                    ))
            else:
                # Sell at resistance
                if level > market_price:
                    zones.append(EntryZone(
                        best_entry=level,
                        acceptable_entry=level - atr * 0.1,
                        max_entry=level - atr * 0.2,
                        zone_width_pips=atr * 0.2 / 0.1,
                        confidence=70
                    ))
        
        return zones
    
    def _find_sr_levels(self, market_data: Dict[str, pd.DataFrame], 
                       direction: str) -> List[float]:
        """Find nearby support/resistance levels."""
        levels = []
        
        if 'H1' in market_data:
            h1_data = market_data['H1']
            
            # Recent highs/lows
            recent_highs = h1_data['high'].tail(20)
            recent_lows = h1_data['low'].tail(20)
            
            if direction == 'BUY':
                # Find support levels (recent lows)
                levels = sorted(recent_lows.unique())[-3:]
            else:
                # Find resistance levels (recent highs)
                levels = sorted(recent_highs.unique(), reverse=True)[:3]
        
        return levels
    
    def _select_entry_type(self, confidence: int, momentum: MomentumProfile,
                          volatility_state: str, spread_pips: float,
                          zones: List[EntryZone]) -> EntryType:
        """Select optimal entry type."""
        
        # High urgency conditions = market order
        if (confidence >= 80 and momentum.strength >= 70 and 
            momentum.direction != 'neutral'):
            return EntryType.MARKET
        
        # High spread or low volatility = patient limit
        if spread_pips > self.settings.max_spread_pips * 0.8:
            return EntryType.LIMIT_PATIENT
        
        # Low confidence or conflicting momentum = scale in
        if confidence < 65 or momentum.direction == 'neutral':
            return EntryType.SCALE_IN
        
        # Waiting for momentum confirmation
        if momentum.strength < self.momentum_threshold:
            return EntryType.MOMENTUM
        
        # Default to aggressive limit
        return EntryType.LIMIT_AGGRESSIVE
    
    def _create_market_entry_plan(self, market_price: float, 
                                 spread_pips: float,
                                 zones: List[EntryZone]) -> EntryPlan:
        """Create market order entry plan."""
        return EntryPlan(
            entry_type=EntryType.MARKET,
            entry_zones=zones,
            recommended_price=market_price,
            market_price=market_price,
            limit_offset_pips=0,
            max_wait_minutes=0,
            spread_threshold_pips=spread_pips * 1.2  # Allow 20% higher
        )
    
    def _create_aggressive_limit_plan(self, market_price: float, direction: str,
                                    spread_pips: float, 
                                    zones: List[EntryZone]) -> EntryPlan:
        """Create aggressive limit order plan."""
        # Place limit just inside the spread
        offset_pips = spread_pips * 0.3
        
        if direction == 'BUY':
            limit_price = market_price - (offset_pips * 0.1)
        else:
            limit_price = market_price + (offset_pips * 0.1)
        
        return EntryPlan(
            entry_type=EntryType.LIMIT_AGGRESSIVE,
            entry_zones=zones,
            recommended_price=round(limit_price, 2),
            market_price=market_price,
            limit_offset_pips=offset_pips,
            max_wait_minutes=3
        )
    
    def _create_patient_limit_plan(self, market_price: float, direction: str,
                                  zones: List[EntryZone], 
                                  volatility_state: str) -> EntryPlan:
        """Create patient limit order plan."""
        # Use best entry from zones
        if zones:
            target_price = zones[0].best_entry
        else:
            # Fallback to fixed offset
            offset = 5 if volatility_state in ['low', 'compression'] else 10
            if direction == 'BUY':
                target_price = market_price - (offset * 0.1)
            else:
                target_price = market_price + (offset * 0.1)
        
        offset_pips = abs(market_price - target_price) / 0.1
        
        return EntryPlan(
            entry_type=EntryType.LIMIT_PATIENT,
            entry_zones=zones,
            recommended_price=round(target_price, 2),
            market_price=market_price,
            limit_offset_pips=offset_pips,
            max_wait_minutes=10
        )
    
    def _create_scale_in_plan(self, market_price: float, direction: str,
                             zones: List[EntryZone], confidence: int) -> EntryPlan:
        """Create scale-in entry plan."""
        # Create 3 entry levels
        scale_levels = []
        
        if zones:
            # Use zones for scale levels
            for i, zone in enumerate(zones[:3]):
                scale_levels.append(zone.acceptable_entry)
        else:
            # Create evenly spaced levels
            spacing = 3 if confidence >= 70 else 5  # Pips
            for i in range(3):
                if direction == 'BUY':
                    level = market_price - (i * spacing * 0.1)
                else:
                    level = market_price + (i * spacing * 0.1)
                scale_levels.append(round(level, 2))
        
        return EntryPlan(
            entry_type=EntryType.SCALE_IN,
            entry_zones=zones,
            recommended_price=scale_levels[0],
            market_price=market_price,
            limit_offset_pips=abs(market_price - scale_levels[0]) / 0.1,
            scale_in_levels=scale_levels,
            max_wait_minutes=15
        )
    
    def _create_momentum_plan(self, market_price: float, direction: str,
                            momentum: MomentumProfile,
                            zones: List[EntryZone]) -> EntryPlan:
        """Create momentum-based entry plan."""
        # Set momentum threshold for entry
        if momentum.strength < 40:
            threshold = 60  # Need strong momentum
        else:
            threshold = momentum.strength * 1.2  # Need acceleration
        
        return EntryPlan(
            entry_type=EntryType.MOMENTUM,
            entry_zones=zones,
            recommended_price=market_price,
            market_price=market_price,
            limit_offset_pips=0,
            momentum_threshold=threshold,
            max_wait_minutes=5
        )
    
    def _calculate_spread_threshold(self, volatility_state: str,
                                  confidence: int) -> float:
        """Calculate maximum acceptable spread."""
        base_spread = self.settings.max_spread_pips
        
        # Volatility adjustments
        vol_multipliers = {
            'compression': 0.8,
            'low': 0.9,
            'normal': 1.0,
            'elevated': 1.1,
            'high': 1.3,
            'extreme': 1.5
        }
        
        multiplier = vol_multipliers.get(volatility_state, 1.0)
        
        # Confidence adjustment (higher confidence = accept higher spread)
        if confidence >= 75:
            multiplier *= 1.1
        elif confidence < 60:
            multiplier *= 0.9
        
        return base_spread * multiplier
    
    def should_enter_now(self, plan: EntryPlan, current_momentum: float,
                        current_spread: float, elapsed_minutes: float) -> bool:
        """Determine if entry conditions are met.
        
        Args:
            plan: Entry plan
            current_momentum: Current momentum reading
            current_spread: Current spread in pips
            elapsed_minutes: Minutes since signal
            
        Returns:
            Whether to enter now
        """
        # Check spread threshold
        if current_spread > plan.spread_threshold_pips:
            return False
        
        # Check time limit
        if elapsed_minutes > plan.max_wait_minutes:
            return False
        
        # Check momentum threshold if applicable
        if (plan.entry_type == EntryType.MOMENTUM and 
            plan.momentum_threshold and
            current_momentum < plan.momentum_threshold):
            return False
        
        return True
    
    def calculate_entry_score(self, price: float, plan: EntryPlan,
                            direction: str) -> float:
        """Calculate entry quality score (0-100).
        
        Args:
            price: Actual entry price
            plan: Original entry plan
            direction: Trade direction
            
        Returns:
            Entry quality score
        """
        score = 100
        
        # Penalize for distance from recommended price
        price_diff = abs(price - plan.recommended_price)
        price_penalty = min(price_diff / 0.1 * 2, 30)  # Max 30 point penalty
        score -= price_penalty
        
        # Penalize for bad direction vs recommended
        if direction == 'BUY' and price > plan.recommended_price:
            score -= 10  # Buying higher than recommended
        elif direction == 'SELL' and price < plan.recommended_price:
            score -= 10  # Selling lower than recommended
        
        # Bonus for entering in best zone
        if plan.entry_zones:
            best_zone = plan.entry_zones[0]
            if (best_zone.best_entry <= price <= best_zone.acceptable_entry or
                best_zone.acceptable_entry <= price <= best_zone.best_entry):
                score += 10
        
        return max(0, min(100, score))


# Singleton instance
_entry_optimizer: Optional[EntryOptimizer] = None


def get_entry_optimizer() -> EntryOptimizer:
    """Get or create entry optimizer singleton."""
    global _entry_optimizer
    if _entry_optimizer is None:
        _entry_optimizer = EntryOptimizer()
    return _entry_optimizer