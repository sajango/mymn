"""Test volatility manager functionality."""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from src.volatility_manager import VolatilityManager, VolatilityState


def create_test_data(volatility_type='normal', trend='stable', periods=100):
    """Create test OHLCV data with specified volatility characteristics."""
    
    timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=periods, freq='h')
    base_price = 2650
    
    # Base volatility by type
    if volatility_type == 'compression':
        base_atr = 5
        price_range = 10
    elif volatility_type == 'low':
        base_atr = 8
        price_range = 20
    elif volatility_type == 'normal':
        base_atr = 12
        price_range = 40
    elif volatility_type == 'high':
        base_atr = 20
        price_range = 80
    elif volatility_type == 'extreme':
        base_atr = 35
        price_range = 150
    else:
        base_atr = 12
        price_range = 40
    
    # Generate prices with specified volatility
    prices = []
    current_price = base_price
    
    for i in range(periods):
        # Add trend component
        if trend == 'increasing' and i > periods * 0.7:
            volatility_multiplier = 1 + (i - periods * 0.7) / (periods * 0.3) * 0.5
        elif trend == 'decreasing' and i > periods * 0.7:
            volatility_multiplier = 1 - (i - periods * 0.7) / (periods * 0.3) * 0.3
        else:
            volatility_multiplier = 1.0
            
        # Random walk with volatility
        change = np.random.randn() * base_atr * volatility_multiplier * 0.1
        current_price += change
        prices.append(current_price)
    
    prices = pd.Series(prices)
    
    # Create OHLC data
    data = pd.DataFrame({
        'timestamp': timestamps,
        'open': prices - np.abs(np.random.randn(periods)) * base_atr * 0.2,
        'high': prices + np.abs(np.random.randn(periods)) * base_atr * 0.3,
        'low': prices - np.abs(np.random.randn(periods)) * base_atr * 0.3,
        'close': prices,
        'tick_volume': np.random.randint(1000, 5000, periods)
    })
    
    # Add indicators
    data['rsi_14'] = 50 + np.random.randn(periods) * 15
    data['rsi_14'] = data['rsi_14'].clip(20, 80)
    
    # EMAs
    data['ema_34'] = data['close'].ewm(span=34).mean()
    data['ema_89'] = data['close'].ewm(span=89).mean()
    
    # MACD
    ema_12 = data['close'].ewm(span=12).mean()
    ema_26 = data['close'].ewm(span=26).mean()
    data['macd'] = ema_12 - ema_26
    data['macd_signal'] = data['macd'].ewm(span=9).mean()
    data['macd_histogram'] = data['macd'] - data['macd_signal']
    
    # ATR with specified volatility
    if trend == 'increasing':
        # Gradually increase ATR
        atr_series = []
        for i in range(periods):
            if i < periods * 0.7:
                atr_val = base_atr + np.random.randn() * 2
            else:
                # Increase in last 30%
                progress = (i - periods * 0.7) / (periods * 0.3)
                atr_val = base_atr * (1 + progress * 0.8) + np.random.randn() * 2
            atr_series.append(max(3, atr_val))
        data['atr_14'] = atr_series
    elif trend == 'decreasing':
        # Gradually decrease ATR
        atr_series = []
        for i in range(periods):
            if i < periods * 0.7:
                atr_val = base_atr + np.random.randn() * 2
            else:
                # Decrease in last 30%
                progress = (i - periods * 0.7) / (periods * 0.3)
                atr_val = base_atr * (1 - progress * 0.5) + np.random.randn() * 2
            atr_series.append(max(3, atr_val))
        data['atr_14'] = atr_series
    else:
        # Stable ATR
        data['atr_14'] = base_atr + np.random.randn(periods) * 2
        data['atr_14'] = data['atr_14'].clip(3, 50)
    
    # ADX (not used by volatility manager but included for completeness)
    data['adx_14'] = 25 + np.random.randn(periods) * 10
    data['adx_14'] = data['adx_14'].clip(10, 50)
    
    return data


# Test the volatility manager
manager = VolatilityManager()

print("=== Testing Volatility Manager ===\n")

# Test 1: Compression state
print("Test 1: Volatility Compression")
h4_data = create_test_data('compression', 'stable')
h1_data = create_test_data('compression', 'stable')
m30_data = create_test_data('compression', 'stable')
profile = manager.analyze_volatility(h4_data, h1_data, m30_data)
print(f"State: {profile.state.value}")
print(f"ATR Percentile: {profile.atr_percentile}%")
print(f"Position Size Factor: {profile.position_size_factor}")
print(f"SL Adjustment: {profile.sl_adjustment_factor}")
print(f"Entry Filter: {profile.entry_filter}")
print(f"Description: {profile.description}")
print()

# Test 2: Normal volatility with increasing trend
print("Test 2: Normal Volatility + Increasing Trend")
h4_data = create_test_data('normal', 'increasing')
h1_data = create_test_data('normal', 'increasing')
m30_data = create_test_data('normal', 'increasing')
profile = manager.analyze_volatility(h4_data, h1_data, m30_data)
print(f"State: {profile.state.value}")
print(f"Volatility Trend: {profile.volatility_trend}")
print(f"Position Size Factor: {profile.position_size_factor}")
print(f"Confidence Impact: {profile.confidence_impact:+d}")
print(f"Description: {profile.description}")
print()

# Test 3: High volatility
print("Test 3: High Volatility")
h4_data = create_test_data('high', 'stable')
h1_data = create_test_data('high', 'stable')
m30_data = create_test_data('high', 'stable')
profile = manager.analyze_volatility(h4_data, h1_data, m30_data)
print(f"State: {profile.state.value}")
print(f"Position Size Factor: {profile.position_size_factor}")
print(f"SL Adjustment: {profile.sl_adjustment_factor}")
print(f"Entry Filter: {profile.entry_filter}")
print(f"Confidence Impact: {profile.confidence_impact:+d}")
print(f"Description: {profile.description}")
print()

# Test 4: Extreme volatility
print("Test 4: Extreme Volatility")
h4_data = create_test_data('extreme', 'stable')
h1_data = create_test_data('extreme', 'stable')
m30_data = create_test_data('extreme', 'stable')
profile = manager.analyze_volatility(h4_data, h1_data, m30_data)
print(f"State: {profile.state.value}")
print(f"Entry Filter: {profile.entry_filter}")
print(f"Should filter entry (conf=65)?: {manager.should_filter_entry(profile.entry_filter, 65)}")
print(f"Description: {profile.description}")
print()

# Test 5: Dynamic stop loss calculation
print("Test 5: Dynamic Stop Loss Calculation")
entry_price = 2650.00
atr = 15.0
for state, sl_factor in [(VolatilityState.COMPRESSION, 0.8),
                        (VolatilityState.NORMAL, 1.0), 
                        (VolatilityState.HIGH, 1.3),
                        (VolatilityState.EXTREME, 1.5)]:
    
    buy_sl = manager.calculate_dynamic_stop_loss(entry_price, 'BUY', atr, sl_factor)
    sell_sl = manager.calculate_dynamic_stop_loss(entry_price, 'SELL', atr, sl_factor)
    print(f"{state.value}: BUY SL={buy_sl} | SELL SL={sell_sl} (factor={sl_factor})")
print()

# Test 6: Position sizing adjustment
print("Test 6: Position Size Adjustments")
base_lots = 0.10
for conf in [60, 70, 80]:
    for pos_factor in [0.5, 0.7, 1.0, 1.1]:
        adjusted = manager.calculate_position_size(base_lots, pos_factor, conf)
        print(f"Base={base_lots}, Factor={pos_factor}, Conf={conf}% -> {adjusted} lots")
print()

# Test 7: Volatility dashboard
print("Test 7: Volatility Dashboard")
h4_data = create_test_data('high', 'increasing')
h1_data = create_test_data('high', 'increasing')
m30_data = create_test_data('high', 'increasing')
profile = manager.analyze_volatility(h4_data, h1_data, m30_data)
dashboard = manager.get_volatility_dashboard(profile)
print(dashboard)
print()

print("All tests completed successfully!")