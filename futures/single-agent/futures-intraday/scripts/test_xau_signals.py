#!/usr/bin/env python3
"""验证 XAU 信号：如果当时买入，现在是赚是亏"""
import os, sys, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import MetaTrader5 as mt5

path = os.getenv("MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
mt5.initialize(path=path)

# 策略配置
strategies = {
    "tier1_xau_h1_us_oversold": {
        "hold": 3,  # best_hold from strategies.json
        "sl_atr_mult": 2.0,
        "tp_rr_mult": 2.0,
        "direction": "long",
        "entry_price": 4692.761,
    },
    "tier2_xau_m30_relaxed": {
        "hold": 3,
        "sl_atr_mult": 2.0,
        "tp_rr_mult": 2.0,
        "direction": "long",
        "entry_price": 4692.761,
    },
}

# 获取当前价
tick = mt5.symbol_info_tick("XAUUSD")
current_bid = tick.bid if tick else 0
current_ask = tick.ask if tick else 0
current_mid = (current_bid + current_ask) / 2

print(f"=== XAUUSD 信号验证 ===")
print(f"信号触发时间: 2026-05-12 13:31 UTC")
print(f"信号触发价格: 4692.761")
print(f"当前时间:     ...")
print(f"当前买价:     {current_bid:.3f}")
print(f"当前卖价:     {current_ask:.3f}")
print(f"当前中间价:   {current_mid:.3f}")

# 按策略的 SL/TP 规则计算盈亏
for name, cfg in strategies.items():
    entry = cfg["entry_price"]
    direction = cfg["direction"]
    
    # 获取真实 ATR 用于 SL/TP
    bars = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_H1, 0, 30)
    if bars is not None and len(bars) >= 14:
        trs = []
        for i in range(1, len(bars)):
            h = bars[-i]["high"] if isinstance(bars[-i], (dict, np.void)) else bars[-i].high
            l = bars[-i]["low"] if isinstance(bars[-i], (dict, np.void)) else bars[-i].low
            pc = bars[-i-1]["close"] if isinstance(bars[-i-1], (dict, np.void)) else bars[-i-1].close
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        atr = sum(trs[:14]) / 14
    else:
        atr = 19.7  # fallback to signal-time ATR
    
    sl_dist = atr * cfg["sl_atr_mult"]
    tp_dist = sl_dist * cfg["tp_rr_mult"]
    sl = entry - sl_dist if direction == "long" else entry + sl_dist
    tp = entry + tp_dist if direction == "long" else entry - tp_dist
    
    # 当前盈亏
    if direction == "long":
        pnl_points = current_bid - entry
        pnl_pct = (current_bid - entry) / entry * 100
        status = "止盈" if current_bid >= tp else ("止损" if current_bid <= sl else "持仓中")
    else:
        pnl_points = entry - current_ask
        pnl_pct = (entry - current_ask) / entry * 100
        status = "止盈" if current_ask <= tp else ("止损" if current_ask >= sl else "持仓中")
    
    print(f"\n{'='*50}")
    print(f"📊 {name}")
    print(f"{'='*50}")
    print(f"  方向:    {direction}")
    print(f"  入场:    {entry:.3f}")
    print(f"  ATR:     {atr:.3f}")
    print(f"  SL:      {sl:.3f} ({sl_dist:.3f} 距离)")
    print(f"  TP:      {tp:.3f} ({tp_dist:.3f} 距离)")
    print(f"  当前价:  {current_bid:.3f}")
    print(f"  盈亏:    {pnl_points:.3f} 点 ({pnl_pct:+.2f}%)")
    print(f"  状态:    {status}")
    
    # SL 或 TP 已触及？
    if status == "止盈":
        print(f"  ✅ 信号正确！按策略已止盈")
    elif status == "止损":
        print(f"  ❌ 信号错误，被 DXY 过滤救了")
    elif pnl_points > 0:
        print(f"  ⚠️ 当前浮盈，但 DXY 过滤时无法入场")
    else:
        print(f"  ✅ DXY 过滤正确，避开了亏损")

mt5.shutdown()
