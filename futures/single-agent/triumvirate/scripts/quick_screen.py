"""Quick D1 trend screening to narrow candidates"""
import json, os
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIUMVIRATE_DIR = os.path.dirname(SCRIPT_DIR)

with open(os.path.join(TRIUMVIRATE_DIR, "logs", "scans", "20260513_063633_pre_analyze.json")) as f:
    data = json.load(f)

symbols = data['symbols']

print(f"{'Symbol':<10} {'Price':<12} {'ATR':<10} {'D1 Trend':<15} {'H1 Last 3':<25} {'Score':<8} {'Phase'}")
print("="*90)

for sym, info in symbols.items():
    d1_candles = info['d1_candles']
    h1_candles = info['h1_candles']
    price = info['trade_params']['current_price']
    atr = info['indicators']['atr_14']
    
    # D1 trend analysis (last 5 candles)
    d1_last5 = d1_candles[-5:] if len(d1_candles) >= 5 else d1_candles
    
    # Check for HH/HL or LH/LL
    highs = [c['high'] for c in d1_last5]
    lows = [c['low'] for c in d1_last5]
    closes = [c['close'] for c in d1_last5]
    
    # Simple trend detection
    higher_highs = all(highs[i] <= highs[i+1] for i in range(len(highs)-1))
    lower_highs = all(highs[i] >= highs[i+1] for i in range(len(highs)-1))
    higher_lows = all(lows[i] <= lows[i+1] for i in range(len(lows)-1))
    lower_lows = all(lows[i] >= lows[i+1] for i in range(len(lows)-1))
    
    # Check consecutive candles
    up_candles = sum(1 for c in d1_last5 if c['close'] > c['open'])
    down_candles = sum(1 for c in d1_last5 if c['close'] < c['open'])
    
    # D1 trend signal
    d1_bullish = (higher_highs and higher_lows) or (up_candles >= 3 and closes[-1] > closes[-3])
    d1_bearish = (lower_highs and lower_lows) or (down_candles >= 3 and closes[-1] < closes[-3])
    
    if d1_bullish and not d1_bearish:
        d1_trend = "BULLISH"
        d1_score = 6
    elif d1_bearish and not d1_bullish:
        d1_trend = "BEARISH"
        d1_score = 6
    elif up_candles > down_candles:
        d1_trend = "WEAK_BULL"
        d1_score = 3
    elif down_candles > up_candles:
        d1_trend = "WEAK_BEAR"
        d1_score = 3
    else:
        d1_trend = "CHOP"
        d1_score = 1
    
    # H1 last 3 candles for recent momentum
    h1_last3 = h1_candles[-3:] if len(h1_candles) >= 3 else h1_candles
    h1_direction = ""
    for c in h1_last3:
        if c['close'] > c['open']:
            h1_direction += "↑"
        elif c['close'] < c['open']:
            h1_direction += "↓"
        else:
            h1_direction += "→"
    
    h1_volatility = sum(abs(c['high'] - c['low']) for c in h1_last3) / (atr * len(h1_last3)) if atr > 0 else 0
    
    # Overall phase assessment
    if d1_score >= 6:
        phase = "鱼身 BODY" if d1_bullish or d1_bearish else "鱼头 HEAD"
        total_score = d1_score
    elif d1_score >= 3:
        phase = "震荡 CHOP"
        total_score = d1_score
    else:
        phase = "混乱 NOISE"
        total_score = 0
    
    print(f"{sym:<10} {price:<12.4f} {atr:<10.4f} {d1_trend:<15} {h1_direction:<25} {total_score:<8} {phase}")

print("\n=== RECOMMENDED FOR ROUND 1 (D1 trend clear) ===")
for sym, info in symbols.items():
    d1_candles = info['d1_candles']
    d1_last5 = d1_candles[-5:] if len(d1_candles) >= 5 else d1_candles
    highs = [c['high'] for c in d1_last5]
    lows = [c['low'] for c in d1_last5]
    closes = [c['close'] for c in d1_last5]
    
    higher_highs = all(highs[i] <= highs[i+1] for i in range(len(highs)-1))
    lower_highs = all(highs[i] >= highs[i+1] for i in range(len(highs)-1))
    higher_lows = all(lows[i] <= lows[i+1] for i in range(len(lows)-1))
    lower_lows = all(lows[i] >= lows[i+1] for i in range(len(lows)-1))
    up_candles = sum(1 for c in d1_last5 if c['close'] > c['open'])
    down_candles = sum(1 for c in d1_last5 if c['close'] < c['open'])
    
    d1_bullish = (higher_highs and higher_lows) or (up_candles >= 3 and closes[-1] > closes[-3])
    d1_bearish = (lower_highs and lower_lows) or (down_candles >= 3 and closes[-1] < closes[-3])
    
    if d1_bullish or d1_bearish:
        price = info['trade_params']['current_price']
        atr = info['indicators']['atr_14']
        print(f"{sym:<10} Direction={'BUY' if d1_bullish else 'SELL'}  Price={price:<12.4f}  ATR={atr:<10.4f}")
