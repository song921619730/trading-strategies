#!/usr/bin/env python3
"""信号触发后的 K 线走势"""
import os, sys, numpy as np
from datetime import datetime, timezone
import MetaTrader5 as mt5

mt5.initialize()

print('XAUUSD H1 K线 (信号前后)')
print(f'{"时间(UTC)":<22} {"开盘":<10} {"最高":<10} {"最低":<10} {"收盘":<10} {"涨跌%":<8} {"信号":<16}')
print('-' * 70)

bars = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_H1, 0, 30)
if bars is None:
    print("No data")
    mt5.shutdown()
    sys.exit(1)

# Find signal bar (13:00 UTC)
signal_idx = None
for i, b in enumerate(bars):
    t = datetime.fromtimestamp(b['time'], tz=timezone.utc)
    if t.hour == 13 and t.minute == 0:
        signal_idx = i
        break

if signal_idx is not None:
    start = max(0, signal_idx - 1)
    for i in range(start, len(bars)):
        b = bars[i]
        t = datetime.fromtimestamp(b['time'], tz=timezone.utc)
        o, h, l, c = b['open'], b['high'], b['low'], b['close']
        prev = bars[i-1]['close'] if i > 0 else o
        chg = (c - prev) / prev * 100
        
        if i == signal_idx:
            marker = '⏳信号触发'
        elif i > signal_idx:
            if c > o:
                marker = f'📈 阳线 +{chg:.2f}%'
            else:
                marker = f'📉 阴线 {chg:.2f}%'
        else:
            marker = ''
        
        print(f'{t.strftime("%Y-%m-%d %H:%M"):<22} {o:<10.3f} {h:<10.3f} {l:<10.3f} {c:<10.3f} {chg:<+8.3f} {marker:<16}')
    
    # Summary
    print(f'\n📊 信号后走势统计')
    after_bars = bars[signal_idx+1:]
    if len(after_bars) > 0:
        entry = bars[signal_idx]['close']
        latest = after_bars[-1]['close']
        highest = max(b['high'] for b in after_bars)
        lowest = min(b['low'] for b in after_bars)
        print(f'  入场价: {entry:.3f}')
        print(f'  当前价: {latest:.3f}')
        print(f'  最高到: {highest:.3f} (+{(highest-entry)/entry*100:.2f}%)')
        print(f'  最低到: {lowest:.3f} ({(lowest-entry)/entry*100:.2f}%)')
        print(f'  当前盈亏: {(latest-entry)/entry*100:+.2f}%')
        print(f'  已过K线: {len(after_bars)} 根 (持有所需: 7根)')

# Also check M30 signal (13:00 UTC for tier2)
print(f'\n{"="*70}')
print('XAUUSD M30 K线 (信号后)')
print(f'{"时间(UTC)":<22} {"开盘":<10} {"最高":<10} {"最低":<10} {"收盘":<10} {"涨跌%":<8} {"信号":<16}')
print('-' * 70)

bars = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M30, 0, 50)
if bars is None:
    print("No M30 data")
    mt5.shutdown()
    sys.exit(1)

signal_idx = None
for i, b in enumerate(bars):
    t = datetime.fromtimestamp(b['time'], tz=timezone.utc)
    if t.hour == 13 and t.minute == 0:
        signal_idx = i
        break

if signal_idx is not None:
    start = max(0, signal_idx - 2)
    for i in range(start, len(bars)):
        b = bars[i]
        t = datetime.fromtimestamp(b['time'], tz=timezone.utc)
        o, h, l, c = b['open'], b['high'], b['low'], b['close']
        prev = bars[i-1]['close'] if i > 0 else o
        chg = (c - prev) / prev * 100
        
        if i == signal_idx:
            marker = '⏳信号触发'
        elif i > signal_idx:
            if c > o and c > (bars[i-1]['close'] if i > 0 else o):
                marker = f'📈 阳 +{chg:.2f}%'
            elif c < o:
                marker = f'📉 阴 {chg:.2f}%'
            else:
                marker = f'→ {chg:.2f}%'
        else:
            marker = ''
        
        print(f'{t.strftime("%Y-%m-%d %H:%M"):<22} {o:<10.3f} {h:<10.3f} {l:<10.3f} {c:<10.3f} {chg:<+8.3f} {marker:<16}')
    
    after = bars[signal_idx+1:]
    if len(after) > 0:
        entry = bars[signal_idx]['close']
        latest = after[-1]['close']
        highest = max(b['high'] for b in after)
        lowest = min(b['low'] for b in after)
        print(f'\n📊 M30 信号后统计')
        print(f'  入场价: {entry:.3f}')
        print(f'  当前价: {latest:.3f}')
        print(f'  最高到: {highest:.3f} (+{(highest-entry)/entry*100:.2f}%)')
        print(f'  最低到: {lowest:.3f} ({(lowest-entry)/entry*100:.2f}%)')
        print(f'  当前盈亏: {(latest-entry)/entry*100:+.2f}%')
        print(f'  已过K线: {len(after)} 根')
        
        sl = entry - 19.707 * 2  # ATR * 2
        tp = entry + 19.707 * 4  # ATR * 4 for RR=2
        print(f'  SL: {sl:.3f} (需跌 {(entry-sl)/entry*100:.2f}%)')
        print(f'  TP: {tp:.3f} (需涨 {(tp-entry)/entry*100:.2f}%)')

mt5.shutdown()
