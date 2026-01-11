"""Test market regime detection."""

import pandas as pd
from datetime import datetime, timezone
import numpy as np

from src.market_regime import MarketRegimeDetector, RegimeType

# Create test data
def create_test_data(trend_type='strong_up', volatility='normal', periods=100):
    """Create test OHLCV data with indicators."""
    
    timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=periods, freq='h')
    
    if trend_type == 'strong_up':
        # Strong uptrend
        base_price = 2600
        prices = base_price + np.arange(periods) * 0.5 + np.random.randn(periods) * 2
        trend_bias = 5
    elif trend_type == 'strong_down':
        # Strong downtrend  
        base_price = 2700
        prices = base_price - np.arange(periods) * 0.5 + np.random.randn(periods) * 2
        trend_bias = -5
    elif trend_type == 'ranging':
        # Ranging market
        base_price = 2650
        prices = base_price + np.sin(np.arange(periods) * 0.1) * 10 + np.random.randn(periods) * 2
        trend_bias = 0
    else:
        base_price = 2650
        prices = base_price + np.random.randn(periods) * 5
        trend_bias = 0
    
    # Volatility adjustments
    if volatility == 'high':
        atr_base = 15
        price_noise = 10
    elif volatility == 'extreme':
        atr_base = 25
        price_noise = 20
    elif volatility == 'low':
        atr_base = 5
        price_noise = 2
    else:  # normal
        atr_base = 10
        price_noise = 5
    
    prices = prices + np.random.randn(periods) * price_noise
    
    # Create OHLC
    data = pd.DataFrame({
        'timestamp': timestamps,
        'open': prices - np.abs(np.random.randn(periods)) * 1,
        'high': prices + np.abs(np.random.randn(periods)) * 2,
        'low': prices - np.abs(np.random.randn(periods)) * 2,
        'close': prices,
        'tick_volume': np.random.randint(1000, 5000, periods)
    })
    
    # Add indicators
    data['rsi_14'] = 50 + trend_bias + np.random.randn(periods) * 10
    data['rsi_14'] = data['rsi_14'].clip(20, 80)
    
    # EMAs follow trend
    data['ema_34'] = data['close'].ewm(span=34).mean()
    data['ema_89'] = data['close'].ewm(span=89).mean()
    
    # MACD
    ema_12 = data['close'].ewm(span=12).mean()
    ema_26 = data['close'].ewm(span=26).mean()
    data['macd'] = ema_12 - ema_26
    data['macd_signal'] = data['macd'].ewm(span=9).mean()
    data['macd_histogram'] = data['macd'] - data['macd_signal']
    
    # ATR with volatility
    data['atr_14'] = atr_base + np.random.randn(periods) * 2
    data['atr_14'] = data['atr_14'].clip(3, 30)
    
    # ADX for trend strength
    if 'strong' in trend_type:
        data['adx_14'] = 40 + np.random.randn(periods) * 5
    elif trend_type == 'ranging':
        data['adx_14'] = 15 + np.random.randn(periods) * 5
    else:
        data['adx_14'] = 25 + np.random.randn(periods) * 5
    
    return data


# Test regime detector
detector = MarketRegimeDetector()

print("=== Testing Market Regime Detection ===\n")

# Test 1: Strong uptrend with normal volatility
print("Test 1: Strong Uptrend + Normal Volatility")
h4_data = create_test_data('strong_up', 'normal')
h1_data = create_test_data('strong_up', 'normal')
regime = detector.detect_regime(h4_data, h1_data)
print(f"Result: {regime.regime_type.value}")
print(f"Confidence: {regime.confidence}%")
print(f"Description: {regime.description}")
print(f"Confidence Modifier: {regime.confidence_modifier:+d}")
print(f"Risk Multiplier: {regime.risk_multiplier}\n")

# Test 2: Strong downtrend with high volatility
print("Test 2: Strong Downtrend + High Volatility")
h4_data = create_test_data('strong_down', 'high')
h1_data = create_test_data('strong_down', 'high')
regime = detector.detect_regime(h4_data, h1_data)
print(f"Result: {regime.regime_type.value}")
print(f"Confidence: {regime.confidence}%")
print(f"Description: {regime.description}")
print(f"Confidence Modifier: {regime.confidence_modifier:+d}")
print(f"Risk Multiplier: {regime.risk_multiplier}\n")

# Test 3: Ranging market with low volatility
print("Test 3: Ranging Market + Low Volatility")
h4_data = create_test_data('ranging', 'low')
h1_data = create_test_data('ranging', 'low')
regime = detector.detect_regime(h4_data, h1_data)
print(f"Result: {regime.regime_type.value}")
print(f"Confidence: {regime.confidence}%")
print(f"Description: {regime.description}")
print(f"Confidence Modifier: {regime.confidence_modifier:+d}")
print(f"Risk Multiplier: {regime.risk_multiplier}\n")

# Test 4: Extreme volatility
print("Test 4: Extreme Volatility")
h4_data = create_test_data('neutral', 'extreme')
h1_data = create_test_data('neutral', 'extreme')
regime = detector.detect_regime(h4_data, h1_data)
print(f"Result: {regime.regime_type.value}")
print(f"Confidence: {regime.confidence}%")
print(f"Description: {regime.description}")
print(f"Confidence Modifier: {regime.confidence_modifier:+d}")
print(f"Risk Multiplier: {regime.risk_multiplier}\n")

print("Test completed successfully!")