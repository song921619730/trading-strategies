#!/usr/bin/env python3
"""Quick D1 trend analysis for trade gate candidates"""
import json, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIUMVIRATE_DIR = os.path.dirname(SCRIPT_DIR)

data_path = os.path.join(TRIUMVIRATE_DIR, "data", "pre_analyze_latest.json")
with open(data_path, 'r') as f:
    pre = json.load(f)

# Our held symbols (Magic 234004)
HELD = {"USOIL", "USDJPY"}

symbols_data = pre.get("symbols", {})

print("=" * 70)
print("D1 TREND QUICK CHECK — US Session 2026-05-13 16:17 BJT")
print("=" * 70)

for sym, data in sorted(symbols_data.items()):
    if sym in HELD:
        continue
    
    d1 = data.get("d1_candles", [])
    h1 = data.get("h1_candles", [])
    price = data.get("trade_params", {}).get("current_price", 0)
    atr = data.get("indicators", {}).get("atr_14", 0)
    
    if len(d1) < 5:
        print(f"\n{sym}: ❌ Insufficient D1 data")
        continue
    
    # Get last 5 D1 candles
    last_5 = d1[-5:]
    last_3 = d1[-3:]
    
    # Check HH/HL for bull, LH/LL for bear
    highs = [c['high'] for c in last_3]
    lows = [c['low'] for c in last_3]
    closes = [c['close'] for c in last_3]
    
    # Bullish: HH + HL
    bull_hh = highs[2] > highs[1] and highs[1] > highs[0]
    bull_hl = lows[2] > lows[1] and lows[1] > lows[0]
    bull_closes = closes[2] > closes[1] and closes[1] > closes[0]
    
    # Bearish: LH + LL
    bear_lh = highs[2] < highs[1] and highs[1] < highs[0]
    bear_ll = lows[2] < lows[1] and lows[1] < lows[0]
    bear_closes = closes[2] < closes[1] and closes[1] < closes[0]
    
    # H1 last 3 candles for short-term momentum
    h1_last_3 = h1[-3:] if len(h1) >= 3 else h1
    h1_bull = sum(1 for c in h1_last_3 if c['close'] > c['open'])
    h1_bear = sum(1 for c in h1_last_3 if c['close'] < c['open'])
    
    # Determine trend
    trend_score = 0
    if bull_hh: trend_score += 1
    if bull_hl: trend_score += 1
    if bull_closes: trend_score += 1
    
    bear_score = 0
    if bear_lh: bear_score += 1
    if bear_ll: bear_score += 1
    if bear_closes: bear_score += 1
    
    if trend_score >= 2 and trend_score > bear_score:
        trend = "BULLISH"
        confidence = "HIGH" if trend_score >= 3 else "MEDIUM"
    elif bear_score >= 2 and bear_score > trend_score:
        trend = "BEARISH"
        confidence = "HIGH" if bear_score >= 3 else "MEDIUM"
    else:
        trend = "NEUTRAL/SIDEWAYS"
        confidence = "LOW"
    
    # Price relative to last 5 D1 range
    d1_range_5 = max(c['high'] for c in last_5) - min(c['low'] for c in last_5)
    d1_range_pct = (d1_range_5 / price * 100) if price > 0 else 0
    
    h1_latest = h1[-1] if h1 else {}
    h1_latest_dir = "UP" if h1_latest.get('close', 0) > h1_latest.get('open', 0) else "DOWN"
    
    print(f"\n{'─' * 60}")
    print(f"{sym} @ ${price:.2f} | ATR: {atr:.2f}")
    print(f"{'─' * 60}")
    print(f"  D1 Trend: {trend} (conf: {confidence})")
    print(f"  D1 (last 3): HH={bull_hh}, HL={bull_hl}, LH={bear_lh}, LL={bear_ll}")
    print(f"  D1 Closes: {[round(c,1) for c in closes]}")
    print(f"  D1 5-bar Range: {d1_range_5:.2f} ({d1_range_pct:.2f}%)")
    print(f"  H1 Last Candle: {h1_latest_dir} (Close: {h1_latest.get('close', 0):.2f})")
    print(f"  H1 Momentum (3-candle): {h1_bull}UP/{h1_bear}DOWN")
