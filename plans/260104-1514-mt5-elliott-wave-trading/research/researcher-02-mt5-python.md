# MetaTrader5 Python Trading Automation Research

**Date**: 2026-01-04 | **Status**: Complete

---

## 1. Installation & Setup

**Requirements**: Windows, MT5 terminal running, Python 3.8+

```bash
pip install MetaTrader5 pandas numpy
```

**Initialization**:
```python
import MetaTrader5 as mt5

if not mt5.initialize():
    print(f"initialize() failed: {mt5.last_error()}")

# Verify connection
print(mt5.terminal_info())
print(mt5.account_info())
```

---

## 2. Data Export: Multi-Timeframe OHLCV

```python
import pandas as pd

TIMEFRAMES = {
    "H4": mt5.TIMEFRAME_H4,
    "H1": mt5.TIMEFRAME_H1,
    "M30": mt5.TIMEFRAME_M30,
    "M15": mt5.TIMEFRAME_M15
}

def fetch_ohlcv(symbol, timeframe_name, bars=200):
    tf = TIMEFRAMES[timeframe_name]
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)

    if rates is None:
        print(f"Failed: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df[['time', 'open', 'high', 'low', 'close', 'tick_volume']]
```

---

## 3. Indicators Calculation

**Using pandas (no TA-Lib dependency)**:

```python
def calculate_rsi(data, period=14):
    delta = data['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(data, period):
    return data['close'].ewm(span=period, adjust=False).mean()

def calculate_macd(data, fast=12, slow=26, signal=9):
    ema_fast = data['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = data['close'].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_atr(data, period=14):
    high = data['high']
    low = data['low']
    close = data['close']

    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()
```

---

## 4. Order Execution

```python
def place_market_order(symbol, order_type, volume, sl, tp):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None, f"Failed: {mt5.last_error()}"

    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": 123456,
        "comment": "EW Auto Trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return None, f"Order failed: {result.comment}"

    return result.order, "Success"
```

---

## 5. Position Management

```python
def get_positions(magic=123456):
    positions = mt5.positions_get()
    if positions is None:
        return []
    return [p for p in positions if p.magic == magic]

def modify_sl_tp(ticket, new_sl, new_tp):
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "sl": new_sl,
        "tp": new_tp,
    }
    result = mt5.order_send(request)
    return result.retcode == mt5.TRADE_RETCODE_DONE

def close_partial(ticket, volume):
    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        return False

    pos = pos[0]
    tick = mt5.symbol_info_tick(pos.symbol)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": ticket,
        "symbol": pos.symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
        "price": tick.bid if pos.type == 0 else tick.ask,
        "deviation": 20,
        "magic": 123456,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    return result.retcode == mt5.TRADE_RETCODE_DONE
```

---

## 6. Error Handling

**Common errors**:
| Error Code | Meaning | Solution |
|------------|---------|----------|
| 10004 | Requote | Retry with new price |
| 10006 | Request rejected | Check parameters |
| 10014 | Invalid volume | Adjust lot size |
| 10015 | Invalid price | Refresh tick data |
| 10019 | No money | Reduce position size |

```python
def safe_initialize(retries=3):
    for i in range(retries):
        if mt5.initialize():
            return True
        time.sleep(2)
    return False

def safe_order_send(request, retries=2):
    for _ in range(retries):
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return result
        if result.retcode in [10004, 10015]:  # Requote, invalid price
            time.sleep(0.5)
            continue
        break
    return result
```

---

## 7. CSV Export Function

```python
def export_to_csv(symbol, output_dir="data/csv"):
    os.makedirs(output_dir, exist_ok=True)

    for tf_name, tf_code in TIMEFRAMES.items():
        df = fetch_ohlcv(symbol, tf_name, 200)
        if df is None:
            continue

        # Add indicators
        df['rsi_14'] = calculate_rsi(df)
        df['ema_34'] = calculate_ema(df, 34)
        df['ema_89'] = calculate_ema(df, 89)
        df['macd'], df['macd_signal'], df['macd_histogram'] = calculate_macd(df)
        df['atr_14'] = calculate_atr(df)

        filename = f"{symbol.lower()}_{tf_name.lower()}.csv"
        df.to_csv(os.path.join(output_dir, filename), index=False)
```

---

## Key Findings

| Aspect | Status | Notes |
|--------|--------|-------|
| **Installation** | ✅ | `pip install MetaTrader5` |
| **Data Fetch** | ✅ | `copy_rates_from_pos()` |
| **Indicators** | ✅ | Pure pandas implementation |
| **Order Execution** | ✅ | `order_send()` |
| **Position Management** | ✅ | Modify SL/TP, partial close |
| **Error Handling** | ✅ | Retry patterns |

---

## Unresolved Questions

1. XAUUSD symbol name varies by broker (XAUUSD, XAUUSDm, GOLD)
2. Filling mode varies by broker (IOC, FOK, RETURN)
3. Minimum volume/step size needs runtime check
