"""Test multi-TP exit management system."""

from src.multi_tp_manager import MultiTPManager, ExitStrategy, get_multi_tp_manager
from src.entry_optimizer import EntryOptimizer, get_entry_optimizer
import pandas as pd
import numpy as np
from datetime import datetime, timezone


def test_multi_tp_strategies():
    """Test different TP strategies."""
    print("=== Testing Multi-TP Exit Strategies ===\n")
    
    manager = get_multi_tp_manager()
    
    # Test parameters
    entry_price = 2650.00
    stop_loss = 2640.00  # 10 points risk
    direction = 'BUY'
    
    print(f"Entry: {entry_price}, SL: {stop_loss}, Risk: {entry_price - stop_loss}")
    print("-" * 50)
    
    # Test 1: Fixed Ratio Strategy
    print("\nTest 1: Fixed Ratio Strategy (High Confidence)")
    plan = manager.create_exit_plan(
        entry_price=entry_price,
        stop_loss=stop_loss,
        direction=direction,
        confidence=80,
        market_regime='trend_up',
        volatility_state='normal',
        atr=12,
        wave_pattern='Wave 3 of 5'
    )
    
    print(f"Strategy: {plan.strategy.value}")
    print("TP Levels:")
    for tp in plan.tp_levels:
        print(f"  {tp.level_name}: {tp.price} ({tp.percentage*100:.0f}% exit) - R:R {tp.risk_reward:.1f}")
    print(f"Expected Value: {plan.expected_value:.2f}R")
    print(f"Breakeven Trigger: {plan.breakeven_trigger}")
    
    # Test 2: ATR-Based Strategy
    print("\n\nTest 2: ATR-Based Strategy (High Volatility)")
    plan = manager.create_exit_plan(
        entry_price=entry_price,
        stop_loss=stop_loss,
        direction=direction,
        confidence=70,
        market_regime='trend_up',
        volatility_state='high',
        atr=20,  # Higher ATR
        wave_pattern=None
    )
    
    print(f"Strategy: {plan.strategy.value}")
    print("TP Levels:")
    for tp in plan.tp_levels:
        atr_info = f" (ATR x{tp.atr_multiple})" if tp.atr_multiple else ""
        print(f"  {tp.level_name}: {tp.price}{atr_info}")
    
    # Test 3: Fibonacci Strategy
    print("\n\nTest 3: Fibonacci Strategy (Wave 3)")
    plan = manager.create_exit_plan(
        entry_price=entry_price,
        stop_loss=stop_loss,
        direction=direction,
        confidence=75,
        market_regime='strong_trend_up',
        volatility_state='normal',
        atr=12,
        wave_pattern='Wave 3 Extension'
    )
    
    print(f"Strategy: {plan.strategy.value}")
    print("TP Levels (Fibonacci):")
    for tp in plan.tp_levels:
        fib_info = f" (Fib {tp.fib_level})" if tp.fib_level else ""
        print(f"  {tp.level_name}: {tp.price}{fib_info}")
    
    # Test 4: Adaptive Strategy
    print("\n\nTest 4: Adaptive Strategy (Mixed Conditions)")
    plan = manager.create_exit_plan(
        entry_price=entry_price,
        stop_loss=stop_loss,
        direction=direction,
        confidence=65,
        market_regime='ranging_wide',
        volatility_state='elevated',
        atr=15,
        wave_pattern='ABC Correction'
    )
    
    print(f"Strategy: {plan.strategy.value}")
    print(f"Time Stop: {plan.time_stop_hours} hours")
    print(f"Trailing Config: ATR x{plan.trailing_config['atr_multiplier']}")
    
    # Test 5: Sell Direction
    print("\n\nTest 5: SELL Direction")
    sell_entry = 2700.00
    sell_sl = 2710.00
    
    plan = manager.create_exit_plan(
        entry_price=sell_entry,
        stop_loss=sell_sl,
        direction='SELL',
        confidence=75,
        market_regime='trend_down',
        volatility_state='normal',
        atr=12,
        wave_pattern=None
    )
    
    print(f"Entry: {sell_entry}, SL: {sell_sl}")
    print("TP Levels:")
    for tp in plan.tp_levels:
        print(f"  {tp.level_name}: {tp.price} - R:R {tp.risk_reward:.1f}")


def test_entry_optimization():
    """Test entry optimization."""
    print("\n\n=== Testing Entry Optimization ===\n")
    
    optimizer = get_entry_optimizer()
    
    # Create mock market data
    def create_mock_data(trend='up'):
        timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=50, freq='15T')
        
        if trend == 'up':
            prices = 2650 + np.cumsum(np.random.randn(50) * 2)
        else:
            prices = 2650 - np.cumsum(np.random.randn(50) * 2)
            
        data = pd.DataFrame({
            'timestamp': timestamps,
            'open': prices - np.random.rand(50) * 1,
            'high': prices + np.random.rand(50) * 2,
            'low': prices - np.random.rand(50) * 2,
            'close': prices,
            'ema_34': prices.ewm(span=34).mean(),
            'rsi_14': 50 + np.random.randn(50) * 10,
            'atr_14': 12 + np.random.randn(50) * 2
        })
        data['rsi_14'] = data['rsi_14'].clip(20, 80)
        data['atr_14'] = data['atr_14'].clip(8, 20)
        
        return data
    
    # Test 1: Market Entry
    print("Test 1: High Confidence Market Entry")
    market_data = {
        'H4': create_mock_data('up'),
        'H1': create_mock_data('up'),
        'M30': create_mock_data('up'),
        'M15': create_mock_data('up')
    }
    
    plan = optimizer.optimize_entry(
        signal_price=2650.00,
        market_price=2650.50,
        direction='BUY',
        confidence=85,
        volatility_state='normal',
        spread_pips=2.0,
        market_data=market_data
    )
    
    print(f"Entry Type: {plan.entry_type.value}")
    print(f"Recommended Price: {plan.recommended_price}")
    print(f"Market Price: {plan.market_price}")
    print(f"Max Wait: {plan.max_wait_minutes} minutes")
    print(f"Spread Threshold: {plan.spread_threshold_pips} pips")
    
    # Test 2: Patient Limit Entry
    print("\n\nTest 2: High Spread - Patient Limit")
    plan = optimizer.optimize_entry(
        signal_price=2650.00,
        market_price=2651.00,
        direction='BUY',
        confidence=70,
        volatility_state='normal',
        spread_pips=5.0,  # High spread
        market_data=market_data
    )
    
    print(f"Entry Type: {plan.entry_type.value}")
    print(f"Limit Offset: {plan.limit_offset_pips} pips from market")
    print("Entry Zones:")
    for zone in plan.entry_zones[:2]:
        print(f"  Best: {zone.best_entry}, Acceptable: {zone.acceptable_entry}")
    
    # Test 3: Scale-In Entry
    print("\n\nTest 3: Low Confidence - Scale In")
    plan = optimizer.optimize_entry(
        signal_price=2650.00,
        market_price=2650.00,
        direction='BUY',
        confidence=55,  # Low confidence
        volatility_state='elevated',
        spread_pips=3.0,
        market_data=market_data
    )
    
    print(f"Entry Type: {plan.entry_type.value}")
    if plan.scale_in_levels:
        print("Scale-In Levels:")
        for i, level in enumerate(plan.scale_in_levels):
            print(f"  Level {i+1}: {level}")
    
    # Test 4: Momentum Entry
    print("\n\nTest 4: Waiting for Momentum")
    # Create weak momentum data
    weak_data = market_data.copy()
    weak_data['M15']['rsi_14'] = 52  # Weak momentum
    
    plan = optimizer.optimize_entry(
        signal_price=2650.00,
        market_price=2650.00,
        direction='BUY',
        confidence=70,
        volatility_state='normal',
        spread_pips=2.0,
        market_data=weak_data
    )
    
    print(f"Entry Type: {plan.entry_type.value}")
    if plan.momentum_threshold:
        print(f"Momentum Threshold: {plan.momentum_threshold}")
    
    # Test 5: Entry Scoring
    print("\n\nTest 5: Entry Quality Scoring")
    entries = [
        (2650.00, "Perfect entry at recommended"),
        (2650.50, "Slightly worse but acceptable"),
        (2651.00, "Bad - chasing price"),
        (2649.50, "Better than recommended")
    ]
    
    for price, desc in entries:
        score = optimizer.calculate_entry_score(price, plan, 'BUY')
        print(f"{desc}: {price} = {score}/100")


def test_exit_performance_tracking():
    """Test exit strategy performance tracking."""
    print("\n\n=== Testing Performance Tracking ===\n")
    
    manager = get_multi_tp_manager()
    
    # Simulate trade results
    trade_results = [
        {'tp1_hit': True, 'tp2_hit': True, 'tp3_hit': False, 'stopped_out': False, 'rr_achieved': 1.8},
        {'tp1_hit': True, 'tp2_hit': False, 'tp3_hit': False, 'stopped_out': False, 'rr_achieved': 0.5},
        {'tp1_hit': False, 'tp2_hit': False, 'tp3_hit': False, 'stopped_out': True, 'rr_achieved': -1.0},
        {'tp1_hit': True, 'tp2_hit': True, 'tp3_hit': True, 'all_targets_hit': True, 'rr_achieved': 3.2},
    ]
    
    # Update performance for each strategy
    strategies = [ExitStrategy.FIXED_RATIO, ExitStrategy.ADAPTIVE, 
                 ExitStrategy.FIXED_RATIO, ExitStrategy.FIBONACCI]
    
    for result, strategy in zip(trade_results, strategies):
        manager.update_performance(result, strategy)
    
    # Display performance
    print("Strategy Performance Summary:")
    print("-" * 60)
    for strategy, perf in manager.strategy_performance.items():
        if perf.trades > 0:
            tp1_rate = perf.tp1_hits / perf.trades * 100 if perf.trades > 0 else 0
            print(f"\n{strategy.value}:")
            print(f"  Trades: {perf.trades}")
            print(f"  TP1 Hit Rate: {tp1_rate:.0f}%")
            print(f"  Avg R:R: {perf.avg_rr_achieved:.2f}")
    
    # Test optimal strategy selection
    print("\n\nOptimal Strategy Selection:")
    conditions = {
        'confidence': 75,
        'market_regime': 'trend_up',
        'volatility_state': 'normal',
        'wave_pattern': 'Wave 3'
    }
    
    optimal = manager.get_optimal_strategy(conditions)
    print(f"Recommended strategy: {optimal.value}")


def test_partial_exits():
    """Test partial exit calculations."""
    print("\n\n=== Testing Partial Exit Calculations ===\n")
    
    manager = get_multi_tp_manager()
    
    # Test position sizing for partial exits
    position_sizes = [0.10, 0.05, 0.03, 0.01]
    tp_percentages = [0.5, 0.3, 0.2]  # TP1, TP2, TP3
    
    print("Partial Exit Calculations:")
    print("-" * 40)
    
    for size in position_sizes:
        print(f"\nPosition Size: {size} lots")
        remaining = size
        
        for i, pct in enumerate(tp_percentages):
            close_lots = manager.calculate_partial_close_size(remaining, pct)
            print(f"  TP{i+1} ({pct*100:.0f}%): Close {close_lots} lots")
            remaining = remaining - close_lots
            
        print(f"  Remaining: {remaining:.2f} lots")


def test_time_based_exits():
    """Test time-based exit logic."""
    print("\n\n=== Testing Time-Based Exits ===\n")
    
    manager = get_multi_tp_manager()
    
    from datetime import timedelta
    
    # Test scenarios
    scenarios = [
        (24, 10, 50, "In profit, within time"),
        (24, 25, 50, "In profit, exceeded time"),
        (24, 25, -30, "Small loss, exceeded time + buffer"),
        (24, 25, -100, "Large loss, exceeded time"),
        (12, 13, -20, "Small loss in volatile market")
    ]
    
    print("Time Stop Scenarios:")
    print("-" * 50)
    
    for time_limit, elapsed, pnl, desc in scenarios:
        entry_time = datetime.now(timezone.utc) - timedelta(hours=elapsed)
        should_exit, reason = manager.should_exit_on_time(entry_time, time_limit, pnl)
        
        print(f"\n{desc}:")
        print(f"  Time limit: {time_limit}h, Elapsed: {elapsed}h, P&L: ${pnl}")
        print(f"  Exit? {should_exit}, Reason: {reason}")


if __name__ == "__main__":
    test_multi_tp_strategies()
    test_entry_optimization()
    test_exit_performance_tracking()
    test_partial_exits()
    test_time_based_exits()
    
    print("\n\nAll tests completed successfully!")