"""Multi-TP exit management system with adaptive strategies.

Features:
- Dynamic TP level calculation based on market conditions
- Partial exit management with position scaling
- Time-based exit optimization
- Volatility-adjusted TP distances
- Performance-based TP adaptation
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class ExitStrategy(str, Enum):
    """Exit strategy types."""
    
    FIXED_RATIO = "fixed_ratio"      # Fixed R:R ratios
    ATR_BASED = "atr_based"          # ATR multiples
    FIBONACCI = "fibonacci"          # Fibonacci extensions
    ADAPTIVE = "adaptive"            # Market-adaptive
    TIME_DECAY = "time_decay"        # Time-based urgency
    MOMENTUM = "momentum"            # Momentum-based


@dataclass
class TPLevel:
    """Take profit level configuration."""
    
    level_name: str              # TP1, TP2, TP3, etc.
    price: float
    percentage: float            # % of position to close
    risk_reward: float          # R:R ratio
    atr_multiple: Optional[float] = None
    fib_level: Optional[float] = None
    hit: bool = False
    hit_time: Optional[datetime] = None


@dataclass
class ExitPlan:
    """Complete exit plan for a position."""
    
    strategy: ExitStrategy
    tp_levels: List[TPLevel]
    stop_loss: float
    breakeven_trigger: float     # Price to move SL to BE
    time_stop_hours: Optional[int] = None
    trailing_config: Optional[dict] = None
    total_risk_reward: float = 0.0
    expected_value: float = 0.0


@dataclass
class ExitPerformance:
    """Track exit strategy performance."""
    
    strategy: ExitStrategy
    trades: int = 0
    tp1_hits: int = 0
    tp2_hits: int = 0
    tp3_hits: int = 0
    full_hits: int = 0
    stopped_out: int = 0
    timed_out: int = 0
    avg_rr_achieved: float = 0.0
    total_rr: float = 0.0


class MultiTPManager:
    """Manages multi-level take profit strategies."""
    
    def __init__(self):
        from src.config import get_settings
        self.settings = get_settings()
        
        # Default TP percentages
        self.default_tp_percentages = {
            'TP1': 0.5,   # 50% at TP1
            'TP2': 0.3,   # 30% at TP2
            'TP3': 0.2    # 20% at TP3
        }
        
        # Strategy performance tracking
        self.strategy_performance: Dict[ExitStrategy, ExitPerformance] = {
            strategy: ExitPerformance(strategy=strategy) 
            for strategy in ExitStrategy
        }
        
        # Load historical performance if available
        self._load_performance_history()
    
    def create_exit_plan(self, 
                        entry_price: float,
                        stop_loss: float,
                        direction: str,
                        confidence: int,
                        market_regime: Optional[str] = None,
                        volatility_state: Optional[str] = None,
                        atr: Optional[float] = None,
                        wave_pattern: Optional[str] = None) -> ExitPlan:
        """Create comprehensive exit plan based on conditions.
        
        Args:
            entry_price: Entry price for the trade
            stop_loss: Initial stop loss price
            direction: 'BUY' or 'SELL'
            confidence: Signal confidence (0-100)
            market_regime: Current market regime
            volatility_state: Current volatility state
            atr: Current ATR value
            wave_pattern: Elliott wave pattern
            
        Returns:
            ExitPlan with all TP levels and exit rules
        """
        # Select strategy based on conditions
        strategy = self._select_exit_strategy(
            confidence, market_regime, volatility_state, wave_pattern
        )
        
        # Calculate base risk
        risk = abs(entry_price - stop_loss)
        
        # Generate TP levels based on strategy
        if strategy == ExitStrategy.FIXED_RATIO:
            tp_levels = self._create_fixed_ratio_tps(
                entry_price, risk, direction, confidence
            )
        elif strategy == ExitStrategy.ATR_BASED and atr:
            tp_levels = self._create_atr_based_tps(
                entry_price, atr, direction, volatility_state
            )
        elif strategy == ExitStrategy.FIBONACCI:
            tp_levels = self._create_fibonacci_tps(
                entry_price, risk, direction, wave_pattern
            )
        elif strategy == ExitStrategy.ADAPTIVE:
            tp_levels = self._create_adaptive_tps(
                entry_price, risk, direction, confidence,
                market_regime, volatility_state
            )
        elif strategy == ExitStrategy.MOMENTUM:
            tp_levels = self._create_momentum_tps(
                entry_price, risk, direction, market_regime
            )
        else:
            # Default to fixed ratio
            tp_levels = self._create_fixed_ratio_tps(
                entry_price, risk, direction, confidence
            )
        
        # Calculate breakeven trigger (after TP1 typically)
        breakeven_trigger = self._calculate_breakeven_trigger(
            entry_price, tp_levels[0].price, direction
        )
        
        # Determine time stop based on volatility
        time_stop_hours = self._calculate_time_stop(
            volatility_state, market_regime, confidence
        )
        
        # Create trailing stop config
        trailing_config = self._create_trailing_config(
            volatility_state, strategy
        )
        
        # Calculate expected value
        expected_value = self._calculate_expected_value(
            tp_levels, confidence, strategy
        )
        
        # Calculate total risk:reward
        total_rr = self._calculate_total_rr(tp_levels)
        
        return ExitPlan(
            strategy=strategy,
            tp_levels=tp_levels,
            stop_loss=stop_loss,
            breakeven_trigger=breakeven_trigger,
            time_stop_hours=time_stop_hours,
            trailing_config=trailing_config,
            total_risk_reward=total_rr,
            expected_value=expected_value
        )
    
    def _select_exit_strategy(self, confidence: int, 
                            market_regime: Optional[str],
                            volatility_state: Optional[str],
                            wave_pattern: Optional[str]) -> ExitStrategy:
        """Select optimal exit strategy based on conditions."""
        
        # High confidence + strong trend = let it run with adaptive
        if confidence >= 75 and market_regime in ['strong_trend_up', 'strong_trend_down']:
            return ExitStrategy.ADAPTIVE
        
        # Wave 3 patterns = Fibonacci extensions
        if wave_pattern and 'wave 3' in wave_pattern.lower():
            return ExitStrategy.FIBONACCI
        
        # High volatility = ATR-based for dynamic targets
        if volatility_state in ['high', 'extreme']:
            return ExitStrategy.ATR_BASED
        
        # Ranging markets = fixed ratio with tighter targets
        if market_regime in ['ranging_tight', 'ranging_wide']:
            return ExitStrategy.FIXED_RATIO
        
        # Momentum-based for normal trending
        if market_regime in ['trend_up', 'trend_down']:
            return ExitStrategy.MOMENTUM
        
        # Default to adaptive
        return ExitStrategy.ADAPTIVE
    
    def _create_fixed_ratio_tps(self, entry: float, risk: float, 
                               direction: str, confidence: int) -> List[TPLevel]:
        """Create fixed risk:reward ratio TPs."""
        tp_levels = []
        
        # Adjust ratios based on confidence
        if confidence >= 75:
            ratios = [1.5, 2.5, 4.0]
        elif confidence >= 65:
            ratios = [1.2, 2.0, 3.0]
        else:
            ratios = [1.0, 1.5, 2.0]
        
        for i, ratio in enumerate(ratios):
            tp_name = f"TP{i+1}"
            if direction == 'BUY':
                tp_price = entry + (risk * ratio)
            else:
                tp_price = entry - (risk * ratio)
                
            tp_levels.append(TPLevel(
                level_name=tp_name,
                price=round(tp_price, 2),
                percentage=self.default_tp_percentages.get(tp_name, 0.33),
                risk_reward=ratio
            ))
        
        return tp_levels
    
    def _create_atr_based_tps(self, entry: float, atr: float,
                             direction: str, volatility_state: str) -> List[TPLevel]:
        """Create ATR-multiple based TPs."""
        tp_levels = []
        
        # Adjust multiples based on volatility
        if volatility_state == 'extreme':
            multiples = [2.0, 3.5, 5.0]
        elif volatility_state == 'high':
            multiples = [1.5, 2.5, 3.5]
        elif volatility_state == 'low':
            multiples = [0.8, 1.2, 1.8]
        else:
            multiples = [1.0, 1.8, 2.5]
        
        for i, multiple in enumerate(multiples):
            tp_name = f"TP{i+1}"
            if direction == 'BUY':
                tp_price = entry + (atr * multiple)
            else:
                tp_price = entry - (atr * multiple)
            
            tp_levels.append(TPLevel(
                level_name=tp_name,
                price=round(tp_price, 2),
                percentage=self.default_tp_percentages.get(tp_name, 0.33),
                risk_reward=0,  # Calculate separately
                atr_multiple=multiple
            ))
        
        return tp_levels
    
    def _create_fibonacci_tps(self, entry: float, risk: float,
                             direction: str, wave_pattern: str) -> List[TPLevel]:
        """Create Fibonacci extension based TPs."""
        tp_levels = []
        
        # Fibonacci levels based on wave pattern
        if 'wave 3' in wave_pattern.lower():
            fib_levels = [1.618, 2.618, 4.236]  # Extended targets for wave 3
        elif 'wave 5' in wave_pattern.lower():
            fib_levels = [1.0, 1.618, 2.0]      # Conservative for wave 5
        else:
            fib_levels = [1.272, 1.618, 2.0]    # Standard levels
        
        for i, fib in enumerate(fib_levels):
            tp_name = f"TP{i+1}"
            if direction == 'BUY':
                tp_price = entry + (risk * fib)
            else:
                tp_price = entry - (risk * fib)
                
            tp_levels.append(TPLevel(
                level_name=tp_name,
                price=round(tp_price, 2),
                percentage=self.default_tp_percentages.get(tp_name, 0.33),
                risk_reward=fib,
                fib_level=fib
            ))
        
        return tp_levels
    
    def _create_adaptive_tps(self, entry: float, risk: float, direction: str,
                            confidence: int, market_regime: str,
                            volatility_state: str) -> List[TPLevel]:
        """Create adaptive TPs based on multiple factors."""
        tp_levels = []
        
        # Base ratios
        base_ratios = [1.2, 2.0, 3.0]
        
        # Regime adjustments
        regime_multipliers = {
            'strong_trend_up': 1.3,
            'strong_trend_down': 1.3,
            'trend_up': 1.1,
            'trend_down': 1.1,
            'ranging_tight': 0.8,
            'ranging_wide': 0.9,
            'high_volatility': 1.0,
            'extreme_volatility': 0.7
        }
        
        # Confidence adjustments
        conf_multiplier = 0.8 + (confidence / 100) * 0.4  # 0.8 to 1.2
        
        # Volatility adjustments
        vol_multipliers = {
            'compression': 1.2,
            'low': 1.1,
            'normal': 1.0,
            'elevated': 0.95,
            'high': 0.9,
            'extreme': 0.8
        }
        
        regime_mult = regime_multipliers.get(market_regime, 1.0)
        vol_mult = vol_multipliers.get(volatility_state, 1.0)
        
        for i, base_ratio in enumerate(base_ratios):
            tp_name = f"TP{i+1}"
            # Apply all adjustments
            adjusted_ratio = base_ratio * regime_mult * conf_multiplier * vol_mult
            
            if direction == 'BUY':
                tp_price = entry + (risk * adjusted_ratio)
            else:
                tp_price = entry - (risk * adjusted_ratio)
                
            tp_levels.append(TPLevel(
                level_name=tp_name,
                price=round(tp_price, 2),
                percentage=self.default_tp_percentages.get(tp_name, 0.33),
                risk_reward=adjusted_ratio
            ))
        
        return tp_levels
    
    def _create_momentum_tps(self, entry: float, risk: float,
                            direction: str, market_regime: str) -> List[TPLevel]:
        """Create momentum-based TPs that expand with trend strength."""
        tp_levels = []
        
        # Base on expected momentum continuation
        if 'strong' in market_regime:
            # Strong momentum - wider targets
            ratios = [1.0, 2.5, 4.5]
            percentages = {'TP1': 0.3, 'TP2': 0.3, 'TP3': 0.4}  # Keep more for TP3
        else:
            # Normal momentum
            ratios = [1.0, 1.8, 2.8]
            percentages = {'TP1': 0.5, 'TP2': 0.3, 'TP3': 0.2}
        
        for i, ratio in enumerate(ratios):
            tp_name = f"TP{i+1}"
            if direction == 'BUY':
                tp_price = entry + (risk * ratio)
            else:
                tp_price = entry - (risk * ratio)
                
            tp_levels.append(TPLevel(
                level_name=tp_name,
                price=round(tp_price, 2),
                percentage=percentages.get(tp_name, 0.33),
                risk_reward=ratio
            ))
        
        return tp_levels
    
    def _calculate_breakeven_trigger(self, entry: float, tp1: float, 
                                   direction: str) -> float:
        """Calculate price level to move stop loss to breakeven."""
        # Typically trigger BE when 70% to TP1
        if direction == 'BUY':
            trigger = entry + (tp1 - entry) * 0.7
        else:
            trigger = entry - (entry - tp1) * 0.7
            
        return round(trigger, 2)
    
    def _calculate_time_stop(self, volatility_state: str,
                           market_regime: str, confidence: int) -> Optional[int]:
        """Calculate time-based stop in hours."""
        # Base hours by volatility
        base_hours = {
            'compression': 48,
            'low': 36,
            'normal': 24,
            'elevated': 18,
            'high': 12,
            'extreme': 8
        }
        
        hours = base_hours.get(volatility_state, 24)
        
        # Adjust for ranging markets (trades take longer)
        if 'ranging' in market_regime:
            hours = int(hours * 1.5)
        
        # High confidence trades get more time
        if confidence >= 75:
            hours = int(hours * 1.2)
        
        return hours
    
    def _create_trailing_config(self, volatility_state: str,
                              strategy: ExitStrategy) -> dict:
        """Create trailing stop configuration."""
        # ATR multiplier for trailing distance
        trail_multipliers = {
            'compression': 1.0,
            'low': 1.2,
            'normal': 1.5,
            'elevated': 1.8,
            'high': 2.0,
            'extreme': 2.5
        }
        
        config = {
            'enabled': True,
            'atr_multiplier': trail_multipliers.get(volatility_state, 1.5),
            'start_after_tp': 'TP1',  # Start trailing after TP1 hit
            'min_profit_atr': 1.0     # Minimum profit in ATR before trailing
        }
        
        # Momentum strategy uses tighter trailing
        if strategy == ExitStrategy.MOMENTUM:
            config['atr_multiplier'] *= 0.8
            
        return config
    
    def _calculate_expected_value(self, tp_levels: List[TPLevel],
                                confidence: int, strategy: ExitStrategy) -> float:
        """Calculate expected value of the exit plan."""
        # Get historical hit rates for this strategy
        perf = self.strategy_performance.get(strategy)
        
        if perf and perf.trades >= 10:
            # Use historical data
            tp1_prob = perf.tp1_hits / perf.trades if perf.trades > 0 else 0.5
            tp2_prob = perf.tp2_hits / perf.trades if perf.trades > 0 else 0.3
            tp3_prob = perf.tp3_hits / perf.trades if perf.trades > 0 else 0.15
        else:
            # Use confidence-based estimates
            base_prob = confidence / 100
            tp1_prob = base_prob * 0.9
            tp2_prob = base_prob * 0.6
            tp3_prob = base_prob * 0.3
        
        # Calculate expected R:R
        expected_rr = 0
        for i, tp in enumerate(tp_levels):
            if i == 0:
                prob = tp1_prob
            elif i == 1:
                prob = tp2_prob
            elif i == 2:
                prob = tp3_prob
            else:
                prob = 0.1
                
            expected_rr += tp.risk_reward * tp.percentage * prob
        
        # Account for stop loss probability
        stop_prob = 1 - (confidence / 100)
        expected_rr -= stop_prob * 1.0  # -1R on stop
        
        return expected_rr
    
    def _calculate_total_rr(self, tp_levels: List[TPLevel]) -> float:
        """Calculate total potential R:R if all targets hit."""
        total = 0
        for tp in tp_levels:
            total += tp.risk_reward * tp.percentage
        return total
    
    def update_performance(self, trade_result: dict, strategy: ExitStrategy):
        """Update strategy performance metrics.
        
        Args:
            trade_result: Trade result with exit details
            strategy: Strategy used for the trade
        """
        perf = self.strategy_performance[strategy]
        perf.trades += 1
        
        # Update hit statistics
        if trade_result.get('tp1_hit'):
            perf.tp1_hits += 1
        if trade_result.get('tp2_hit'):
            perf.tp2_hits += 1
        if trade_result.get('tp3_hit'):
            perf.tp3_hits += 1
        if trade_result.get('all_targets_hit'):
            perf.full_hits += 1
        if trade_result.get('stopped_out'):
            perf.stopped_out += 1
        if trade_result.get('timed_out'):
            perf.timed_out += 1
            
        # Update R:R tracking
        rr_achieved = trade_result.get('rr_achieved', 0)
        perf.total_rr += rr_achieved
        perf.avg_rr_achieved = perf.total_rr / perf.trades if perf.trades > 0 else 0
        
        # Save updated performance
        self._save_performance_history()
    
    def get_optimal_strategy(self, conditions: dict) -> ExitStrategy:
        """Get optimal strategy based on historical performance.
        
        Args:
            conditions: Current market conditions
            
        Returns:
            Optimal exit strategy
        """
        # Filter strategies with enough data
        valid_strategies = [
            (strategy, perf) for strategy, perf in self.strategy_performance.items()
            if perf.trades >= 20
        ]
        
        if not valid_strategies:
            # Not enough data, use default selection
            return self._select_exit_strategy(
                conditions.get('confidence', 60),
                conditions.get('market_regime'),
                conditions.get('volatility_state'),
                conditions.get('wave_pattern')
            )
        
        # Find strategy with best average R:R
        best_strategy = max(valid_strategies, key=lambda x: x[1].avg_rr_achieved)
        
        return best_strategy[0]
    
    def calculate_partial_close_size(self, current_lots: float, 
                                   tp_percentage: float) -> float:
        """Calculate lots to close at TP level.
        
        Args:
            current_lots: Current position size
            tp_percentage: Percentage to close
            
        Returns:
            Lots to close
        """
        lots_to_close = current_lots * tp_percentage
        
        # Round to valid lot step (typically 0.01)
        lot_step = 0.01
        lots_to_close = round(lots_to_close / lot_step) * lot_step
        
        # Ensure minimum lot size
        return max(lots_to_close, lot_step)
    
    def should_exit_on_time(self, entry_time: datetime, 
                          time_stop_hours: int,
                          current_pnl: float) -> tuple[bool, str]:
        """Check if position should exit based on time.
        
        Args:
            entry_time: When trade was entered
            time_stop_hours: Hours until time stop
            current_pnl: Current P&L
            
        Returns:
            Tuple of (should_exit, reason)
        """
        if not time_stop_hours:
            return False, ""
            
        current_time = datetime.now(timezone.utc)
        elapsed_hours = (current_time - entry_time).total_seconds() / 3600
        
        if elapsed_hours >= time_stop_hours:
            if current_pnl > 0:
                return True, f"Time stop - in profit after {time_stop_hours}h"
            else:
                # Give losing trades more time if close to breakeven
                if current_pnl > -50:  # Within $50 of breakeven
                    extra_hours = time_stop_hours * 0.25
                    if elapsed_hours >= time_stop_hours + extra_hours:
                        return True, f"Extended time stop after {elapsed_hours:.1f}h"
                else:
                    return True, f"Time stop - cutting loss after {time_stop_hours}h"
                    
        return False, ""
    
    def _load_performance_history(self):
        """Load historical performance data."""
        try:
            import json
            from pathlib import Path
            
            perf_file = Path("data/exit_performance.json")
            if perf_file.exists():
                with open(perf_file, 'r') as f:
                    data = json.load(f)
                    
                for strategy_str, perf_data in data.items():
                    strategy = ExitStrategy(strategy_str)
                    perf = ExitPerformance(strategy=strategy, **perf_data)
                    self.strategy_performance[strategy] = perf
                    
                logger.info("Loaded exit strategy performance history")
        except Exception as e:
            logger.warning(f"Could not load performance history: {e}")
    
    def _save_performance_history(self):
        """Save performance data for persistence."""
        try:
            import json
            from pathlib import Path
            
            data = {}
            for strategy, perf in self.strategy_performance.items():
                data[strategy.value] = {
                    'trades': perf.trades,
                    'tp1_hits': perf.tp1_hits,
                    'tp2_hits': perf.tp2_hits,
                    'tp3_hits': perf.tp3_hits,
                    'full_hits': perf.full_hits,
                    'stopped_out': perf.stopped_out,
                    'timed_out': perf.timed_out,
                    'avg_rr_achieved': perf.avg_rr_achieved,
                    'total_rr': perf.total_rr
                }
            
            perf_file = Path("data/exit_performance.json")
            perf_file.parent.mkdir(exist_ok=True)
            
            with open(perf_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Could not save performance history: {e}")


# Singleton instance
_multi_tp_manager: Optional[MultiTPManager] = None


def get_multi_tp_manager() -> MultiTPManager:
    """Get or create multi-TP manager singleton."""
    global _multi_tp_manager
    if _multi_tp_manager is None:
        _multi_tp_manager = MultiTPManager()
    return _multi_tp_manager