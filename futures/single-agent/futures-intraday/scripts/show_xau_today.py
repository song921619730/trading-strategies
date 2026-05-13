#!/usr/bin/env python3
"""正确显示今天(5月12日)信号后的K线"""
import os, numpy as np
from datetime import datetime, timezone
import MetaTrader5 as mt5

mt5.initialize()

print('XAUUSD M30 K线 — 仅今天信号触发后')
print(f'{"时间(UTC)":<22} {"开盘":<10} {"最高":<10} {"最低":<10} {"收盘":<10} {"涨跌%":<8} {"说明":<20}')
print('-'*70)

bars = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M30, 0, 100)
if bars is not None and len(bars) > 0:
    # Find today's 13:00 bar (May 12)
    signal_idx = None
    for i, b in enumerate(bars):
        t = datetime.fromtimestamp(b['time'], tz=timezone.utc)
        if t.hour == 13 and t.minute == 0 and t.day == 12:
            signal_idx = i
            break
    
    if signal_idx is not None:
        start = signal_idx - 2
        for i in range(start, len(bars)):
            b = bars[i]
            t = datetime.fromtimestamp(b['time'], tz=timezone.utc)
            o, h, l, c = b['open'], b['high'], b['low'], b['close']
            prev = bars[i-1]['close'] if i > 0 else o
            chg = (c - prev) / prev * 100
            
            if i == signal_idx:
                marker = '⏳ 信号触发 RSI=18'
            elif i == signal_idx + 1:
                marker = '📉 第一根后 续跌'
            elif i > signal_idx + 1:
                if c > o and c > bars[i-1]['close']:
                    marker = '📈 阳线反弹'
                elif c < o:
                    marker = '📉 继续下跌'
                else:
                    marker = '→ 平盘'
            else:
                marker = '信号前'
            
            candle = '📈' if c > o else '📉'
            print(f'{t.strftime("%m-%d %H:%M"):<22} {o:<10.3f} {h:<10.3f} {l:<10.3f} {c:<10.3f} {chg:<+8.3f} {marker:<20}')
        
        # Summary
        print(f'\n{"="*70}')
        signal_bar = bars[signal_idx]
        entry = signal_bar['close']  # 4690
        after = bars[signal_idx+1:]
        
        if len(after) > 0:
            peak = max(max(b['high'] for b in after), entry)
            trough = min(min(b['low'] for b in after), entry)
            latest = after[-1]['close']
            
            print(f'入场价(信号收盘): {entry:.3f}')
            print(f'信号后最高: {peak:.3f} (+{(peak-entry)/entry*100:.2f}%)')
            print(f'信号后最低: {trough:.3f} ({(trough-entry)/entry*100:.2f}%)')
            print(f'最后价格:   {latest:.3f} ({(latest-entry)/entry*100:+.2f}%)')
            print(f'已过M30:    {len(after)} 根 (hold=15, 还需 {15-len(after)} 根)')
            print()
            
            if latest < entry:
                print('📉 结论: 信号后价格继续下跌，DXY过滤成功避亏')
            else:
                print('📈 结论: 信号后价格反弹，DXY过滤可能挡了利润')
    
    else:
        print('找不到今天的信号K线')

print(f'\n📊 当前H1收盘价')
bars_h1 = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_H1, 0, 3)
if bars_h1 is not None and len(bars_h1) > 0:
    for b in bars_h1:
        t = datetime.fromtimestamp(b['time'], tz=timezone.utc)
        if t.day == 12:
            print(f'  {t.strftime("%H:%M")} UTC: O={b["open"]:.3f} H={b["high"]:.3f} L={b["low"]:.3f} C={b["close"]:.3f}')

mt5.shutdown()
