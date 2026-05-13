#!/usr/bin/env python3
"""诊断扫描器为什么不出信号 — 打印每个策略的当前市场值与条件对比"""
import json, os, sys, math, numpy as np
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))
from signal_scanner import *

# Load strategies
with open(os.path.join(BASE, "config", "strategies.json")) as f:
    cfg = json.load(f)

# Connect MT5
mt5, account = connect_mt5()
if mt5 is None:
    print(f"❌ MT5 connect failed: {account}")
    sys.exit(1)

# Get DXY
dxy_bars = None
try:
    dxy_raw = mt5.copy_rates_from_pos("DXY", mt5.TIMEFRAME_H1, 0, 20)
    if dxy_raw is not None and len(dxy_raw) >= 6:
        dxy_bars = [{"time": b.time, "open": b.open, "high": b.high, "low": b.low, "close": b.close} for b in dxy_raw]
except Exception as e:
    print(f"⚠️ DXY data unavailable: {e}")

utc_now = datetime.now(timezone.utc)
print(f"🕐 Current UTC: {utc_now.hour}:{utc_now.minute:02d}")
print(f"🕐 Session: {get_session(utc_now.hour)}")
print(f"💰 Balance: {account['balance']}  Equity: {account['equity']}")
print()

for strategy in cfg.get("signals", []):
    sid = strategy["id"]
    symbol = strategy.get("symbols", ["?"])[0]
    sym_mt5 = symbol  # 不带 "m" 后缀
    tf_name = strategy["timeframe"]
    cond = strategy["entry_conditions"]
    direction = strategy["direction"]
    
    try:
        tf = getattr(mt5, f"TIMEFRAME_{tf_name}", None)
        if not tf:
            continue
        
        needed = 40 if "consecutive_bear" in cond else 30
        bars = mt5.copy_rates_from_pos(sym_mt5, tf, 0, needed)
        if bars is None or len(bars) < 20:
            print(f"❌ {sid:40s} | {sym_mt5:12s} | NO DATA ({len(bars) if isinstance(bars, (list, np.ndarray)) else 0} bars)")
            continue
        
        bars_list = []
        for b in bars:
            if isinstance(b, (dict, np.void)):
                bars_list.append({"time": b["time"], "open": b["open"], "high": b["high"],
                                   "low": b["low"], "close": b["close"], "tick_volume": b["tick_volume"]})
            else:
                bars_list.append({"time": b.time, "open": b.open, "high": b.high,
                                   "low": b.low, "close": b.close, "tick_volume": b.tick_volume})
        latest = bars_list[-1]
        closes = [b["close"] for b in bars_list]
        current_close = latest["close"]
        current_utc_hour = utc_now.hour
        
        rsi = calc_rsi(closes)
        atr = calc_atr(bars_list)
        session = get_session(current_utc_hour)
        bears = detected_consecutive_bears(bars_list)
        atr_pct = (atr / current_close * 100) if atr and current_close > 0 else 0
        
        # Check each condition
        fails = []
        
        if "session" in cond and cond["session"]:
            required = SESSION_ALIAS.get(cond["session"], cond["session"])
            if required != session:
                fails.append(f"session: required={cond['session']}(→{required}) got={session}")
        
        if "rsi14_max" in cond:
            if rsi is None or rsi > cond["rsi14_max"]:
                fails.append(f"RSI<{cond['rsi14_max']}: got RSI={rsi:.1f}")
        
        if "rsi14_min" in cond:
            if rsi is None or rsi < cond["rsi14_min"]:
                fails.append(f"RSI>{cond['rsi14_min']}: got RSI={rsi:.1f}")
        
        if "atr_min_pct" in cond:
            if atr_pct < cond["atr_min_pct"] * 100:
                fails.append(f"ATR%>{cond['atr_min_pct']*100:.2f}%: got {atr_pct:.3f}%")
        
        if "consecutive_bear" in cond:
            if bears < cond["consecutive_bear"]:
                fails.append(f"Bears>={cond['consecutive_bear']}: got {bears}")
        
        status = "✅ MATCH" if not fails else f"❌ FAIL ({'; '.join(fails)})"
        print(f"{status:20s} | {sid:40s} | {sym_mt5:12s} {tf_name} {direction:5s} | "
              f"RSI={rsi:5.1f} ATR%={atr_pct:.3f}% Session={session} Bears={bears}")
    
    except Exception as e:
        print(f"⚠️  ERROR {sid:40s} | {sym_mt5:12s} | {e}")

mt5.shutdown()
