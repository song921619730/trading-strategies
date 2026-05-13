"""Quick Round 1 analysis for all remaining candidates"""
import json, os, sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRIUMVIRATE_DIR = os.path.dirname(SCRIPT_DIR)

with open(os.path.join(TRIUMVIRATE_DIR, "logs", "scans", "20260513_063633_pre_analyze.json")) as f:
    data = json.load(f)

symbols = data['symbols']
# Candidates to analyze (those with clear D1 trend from screening)
candidates = ['US30', 'JP225', 'USOIL', 'USDJPY', 'AUDUSD', 'USDCHF']

results = {}

for sym in candidates:
    info = symbols[sym]
    d1 = info['d1_candles']
    h1 = info['h1_candles']
    price = info['trade_params']['current_price']
    atr = info['indicators']['atr_14']
    support = info['indicators']['support_14']
    resistance = info['indicators']['resistance_14']
    
    # D1 last 5 analysis
    d1_5 = d1[-5:]
    highs = [c['high'] for c in d1_5]
    lows = [c['low'] for c in d1_5]
    closes = [c['close'] for c in d1_5]
    opens = [c['open'] for c in d1_5]
    
    # Trend detection
    hh = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i-1])
    hl = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i-1])
    lh = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i-1])
    ll = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i-1])
    
    up_candles = sum(1 for c in d1_5 if c['close'] > c['open'])
    down_candles = sum(1 for c in d1_5 if c['close'] < c['open'])
    
    # Bullish if HH + HL >= 3 and up_candles >= 3
    # Bearish if LH + LL >= 3 and down_candles >= 3
    bullish_score = (1 if highs[-1] > highs[-3] else 0) + (1 if closes[-1] > opens[-3] else 0) + (1 if up_candles >= 3 else 0)
    bearish_score = (1 if highs[-1] < highs[-3] else 0) + (1 if closes[-1] < opens[-3] else 0) + (1 if down_candles >= 3 else 0)
    
    if bullish_score >= 2 and bearish_score < 2:
        d1_trend = "BULLISH"
    elif bearish_score >= 2 and bullish_score < 2:
        d1_trend = "BEARISH"
    else:
        d1_trend = "CONSOLIDATION"
    
    # H1 last 12 candles analysis
    h1_12 = h1[-12:] if len(h1) >= 12 else h1
    h1_up = sum(1 for c in h1_12 if c['close'] > c['open'])
    h1_down = sum(1 for c in h1_12 if c['close'] < c['open'])
    h1_net = h1_12[-1]['close'] - h1_12[0]['open'] if len(h1_12) >= 2 else 0
    
    # Price proximity to resistance/support
    dist_to_resist = ((resistance - price) / atr * 100) if atr > 0 else 999
    dist_to_support = ((price - support) / atr * 100) if atr > 0 else 999
    
    quality_score = 0
    quality_reasons = []
    
    # Score based on structure
    if d1_trend != "CONSOLIDATION":
        quality_score += 3
        quality_reasons.append(f"D1趋势清晰({d1_trend})")
    else:
        quality_score += 1
        quality_reasons.append("D1震荡")
    
    if abs(h1_net) > atr * 0.5:
        quality_score += 2
        quality_reasons.append(f"H1方向明确({'+' if h1_net>0 else ''}{h1_net:.1f})")
    else:
        quality_score += 0
        quality_reasons.append("H1方向模糊")
    
    if dist_to_resist > 50 and dist_to_support > 50:
        quality_score += 2
        quality_reasons.append("价格在中位有空间")
    elif dist_to_resist < 20:
        quality_score -= 1
        quality_reasons.append(f"距阻力仅{dist_to_resist:.0f}%ATR")
    elif dist_to_support < 20:
        quality_score -= 1
        quality_reasons.append(f"距支撑仅{dist_to_support:.0f}%ATR")
    
    if h1_up > h1_down * 1.5 or h1_down > h1_up * 1.5:
        quality_score += 1
        quality_reasons.append("H1量价配合好")
    
    results[sym] = {
        "price": price,
        "atr": atr,
        "d1_trend": d1_trend,
        "h1_recent": f"{h1_up}↑/{h1_down}↓",
        "h1_net_change": round(h1_net, 2),
        "quality_score": quality_score,
        "quality_reasons": quality_reasons,
        "dist_to_resistance%": round(dist_to_resist, 1),
        "dist_to_support%": round(dist_to_support, 1),
        "support": support,
        "resistance": resistance,
        "recommended_action": ""
    }
    
    # Recommended action
    if d1_trend == "BULLISH" and quality_score >= 4 and dist_to_resist > 30:
        results[sym]["recommended_action"] = "CONSIDER_BUY"
    elif d1_trend == "BEARISH" and quality_score >= 4 and dist_to_support > 30:
        results[sym]["recommended_action"] = "CONSIDER_SELL"
    else:
        results[sym]["recommended_action"] = "SKIP"

print(f"{'Symbol':<10} {'Price':<10} {'ATR':<8} {'D1 Trend':<15} {'H1':<10} {'Score':<7} {'DistR%':<8} {'DistS%':<8} {'Action':<15}")
print("="*95)
for sym in candidates:
    r = results[sym]
    print(f"{sym:<10} {r['price']:<10.4f} {r['atr']:<8.4f} {r['d1_trend']:<15} {r['h1_recent']:<10} {r['quality_score']:<7} {r['dist_to_resistance%']:<8} {r['dist_to_support%']:<8} {r['recommended_action']:<15}")
    for reason in r['quality_reasons']:
        print(f"  {'':<10} → {reason}")

# Also log this
ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
output = {"timestamp": ts, "analysis": results}
log_path = os.path.join(TRIUMVIRATE_DIR, "logs", "scans", f"{ts}_quick_scan_remaining.json")
os.makedirs(os.path.join(TRIUMVIRATE_DIR, "logs", "scans"), exist_ok=True)
with open(log_path, 'w') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\nLogged to {log_path}")
