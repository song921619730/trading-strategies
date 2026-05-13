#!/usr/bin/env python3
"""XAUUSD K线走势 — 信号触发前后"""
import os, sys, json, numpy as np
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import MetaTrader5 as mt5

mt5.initialize(path=os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe"))

print("XAUUSD K线走势 — 信号触发前后")
print("=" * 90)

# H1 K线
print("\n📊 H1 K线 (信号: tier1_xau_h1_us_oversold, hold=7)")
print(f"{'时间(UTC)':<22} {'开盘':<10} {'最高':<10} {'最低':<10} {'收盘':<10} {'涨跌%':<8} {'RSI':<8} {'方向':<6}")
print("-" * 90)

bars = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_H1, 0, 20)
if bars is not None:
    # Calculate RSI
    closes = [b["close"] for b in bars]
    gains, losses = [], []
    for i in range(1, 15):
        diff = closes[-i] - closes[-i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-14:]) / 14
    avg_loss = sum(losses[-14:]) / 14 if sum(losses[-14:]) > 0 else 0.001
    rs = avg_gain / avg_loss
    current_rsi = 100 - (100 / (1 + rs))
    
    signal_bar_idx = None
    for i, b in enumerate(bars):
        t = datetime.fromtimestamp(b["time"], tz=timezone.utc)
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        
        # Previous close for change
        prev_close = bars[i-1]["close"] if i > 0 else o
        change = (c - prev_close) / prev_close * 100
        
        # Mark signal time (13:00 UTC bar)
        is_signal = t.hour == 13 and t.minute < 30
        if is_signal:
            signal_bar_idx = i
        
        # Calc RSI at this bar
        sub_closes = [b2["close"] for b2 in bars[:i+1]]
        if len(sub_closes) >= 15:
            sg, sl = [], []
            for j in range(1, 15):
                d = sub_closes[-(j)] - sub_closes[-(j+1)]
                sg.append(max(d, 0))
                sl.append(max(-d, 0))
            ag = sum(sg) / 14
            al = sum(sl) / 14 if sum(sl) > 0 else 0.001
            rsi_val = 100 - (100 / (1 + ag/al))
        else:
            rsi_val = 0
        
        marker = "⬆️ SIGNAL" if is_signal else ("⬆️ ENTRY" if signal_bar_idx is not None and i == signal_bar_idx + 1 else "")
        if is_signal:
            dir_str = "⏳触发"
        elif c > o:
            dir_str = "📈阳"
        else:
            dir_str = "📉阴"
        
        print(f"{t.strftime('%Y-%m-%d %H:%M'):<22} {o:<10.3f} {h:<10.3f} {l:<10.3f} {c:<10.3f} {change:<+8.3f} {rsi_val:<8.1f} {dir_str:<6}")

print()
print("=" * 90)

# M30 K线 (最近20根)
print("\n📊 M30 K线 (信号: tier2_xau_m30_relaxed, hold=15)")
print(f"{'时间(UTC)':<22} {'开盘':<10} {'最高':<10} {'最低':<10} {'收盘':<10} {'涨跌%':<8} {'ATR%':<8} {'方向':<6}")
print("-" * 90)

bars_m30 = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M30, 0, 30)
if bars_m30 is not None:
    for i, b in enumerate(bars_m30):
        t = datetime.fromtimestamp(b["time"], tz=timezone.utc)
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        
        prev_close = bars_m30[i-1]["close"] if i > 0 else o
        change = (c - prev_close) / prev_close * 100
        
        # Calculate ATR% for this bar
        if i >= 14:
            trs = []
            for j in range(i-13, i+1):
                if j > 0:
                    hh = max(bars_m30[j]["high"], bars_m30[j-1]["close"])
                    ll = min(bars_m30[j]["low"], bars_m30[j-1]["close"])
                    trs.append(hh - ll)
            atr_val = sum(trs) / len(trs) if trs else 0
            atr_pct = atr_val / c * 100
        else:
            atr_pct = 0
        
        is_signal = t.hour == 13 and 0 <= t.minute <= 30
        if is_signal:
            dir_str = "⏳触发"
        elif c > o:
            dir_str = "📈阳"
        else:
            dir_str = "📉阴"
        
        print(f"{t.strftime('%Y-%m-%d %H:%M'):<22} {o:<10.3f} {h:<10.3f} {l:<10.3f} {c:<10.3f} {change:<+8.3f} {atr_pct:<8.3f} {dir_str:<6}")

print()
print("=" * 90)

# 统计总结
print("\n📈 走势总结")
tick = mt5.symbol_info_tick("XAUUSD")
print(f"当前价格: {tick.bid:.3f}")
bars_h1 = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_H1, 0, 3)
if bars_h1 is not None and len(bars_h1) >= 2:
    print(f"最近3根H1:")
    for b in bars_h1:
        tt = datetime.fromtimestamp(b["time"], tz=timezone.utc)
        print(f"  {tt.strftime('%H:%M')} O={b['open']:.3f} H={b['high']:.3f} L={b['low']:.3f} C={b['close']:.3f}")

bars_m30_last = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M30, 0, 6)
if bars_m30_last is not None and len(bars_m30_last) >= 2:
    print(f"最近6根M30:")
    for b in bars_m30_last:
        tt = datetime.fromtimestamp(b["time"], tz=timezone.utc)
        print(f"  {tt.strftime('%H:%M')} O={b['open']:.3f} H={b['high']:.3f} L={b['low']:.3f} C={b['close']:.3f}")

mt5.shutdown()
