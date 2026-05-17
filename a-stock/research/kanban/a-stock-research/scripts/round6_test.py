#!/usr/bin/env python3
"""
Scalping Round 6 — M1/M5 多时间框架 + 止损嵌入深度验证
品种: XAUUSD, XAGUSD, JP225, US500, US30
时间框架: M1 (entry), M5 (trend filter), M15 (context)
"""
import json
import math
import sys
import subprocess
import os
from datetime import datetime, timezone, timedelta

WINDOWS_PYTHON = "/mnt/c/Users/gj/AppData/Local/Programs/Python/Python312/python.exe"
TMP_DIR = "/mnt/c/Users/gj/tmp"
os.makedirs(TMP_DIR, exist_ok=True)

SYMBOLS = ['XAUUSD', 'XAGUSD', 'JP225', 'US500', 'US30']

# ─── MT5 数据获取 ────────────────────────────────────────────

def fetch_mt5(timeframes=['M1', 'M5', 'M15'], lookback=5000):
    """Fetch MT5 data for M1 + M5 + M15 across all symbols."""
    code = f'''import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import json
import numpy as np
from datetime import datetime as _dt
import time

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        elif isinstance(obj, (np.floating,)): return float(obj)
        elif isinstance(obj, np.ndarray): return obj.tolist()
        return super().default(obj)

if not mt5.initialize():
    print(json.dumps({{'error': f'MT5 init: {{mt5.last_error()}}'}}))
    sys.exit(0)

symbols = {SYMBOLS}
tf_map = {{'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15}}
timeframes = {timeframes}

result = {{}}
for tf_name in timeframes:
    tf = tf_map.get(tf_name)
    if tf is None: continue
    result[tf_name] = {{}}
    for sym in symbols:
        rates = mt5.copy_rates_from_pos(sym, tf, 0, {lookback})
        if rates is None or len(rates) == 0:
            result[tf_name][sym] = []
            continue
        klines = []
        for r in rates:
            klines.append({{
                'time': _dt.fromtimestamp(int(r[0])).strftime('%Y-%m-%d %H:%M:%S'),
                'ts': int(r[0]),
                'open': round(float(r[1]), 5),
                'high': round(float(r[2]), 5),
                'low': round(float(r[3]), 5),
                'close': round(float(r[4]), 5),
                'volume': int(r[5]),
            }})
        result[tf_name][sym] = klines

mt5.shutdown()
print(json.dumps(result, cls=NpEncoder))
'''
    win_path_wsl = os.path.join(TMP_DIR, "mt5_round6_fetch.py")
    with open(win_path_wsl, "w", encoding='utf-8') as f:
        f.write(code)
    
    r = subprocess.run(
        [WINDOWS_PYTHON, os.path.join("C:/Users/gj/tmp", "mt5_round6_fetch.py")],
        capture_output=True, text=True, timeout=300
    )
    if r.returncode != 0:
        return {"error": f"Windows Python error: {r.stderr[:500]}"}
    idx = r.stdout.find('{')
    if idx >= 0:
        try:
            return json.loads(r.stdout[idx:])
        except json.JSONDecodeError as e:
            return {"error": f"JSON decode: {e}"}
    return {"error": f"No JSON found. stdout[:500]: {r.stdout[:500]}"}


# ─── 技术指标 ──────────────────────────────────────────────────

def compute_sma(series, period):
    if len(series) < period:
        return [None] * len(series)
    sma = [None] * len(series)
    cum = sum(series[:period])
    sma[period-1] = cum / period
    for i in range(period, len(series)):
        cum = cum - series[i-period] + series[i]
        sma[i] = cum / period
    return sma


def compute_rsi(series, period=14):
    if len(series) < period + 1:
        return [None] * len(series)
    rsi = [None] * len(series)
    gains, losses = 0, 0
    for i in range(1, period + 1):
        diff = series[i] - series[i-1]
        gains += max(diff, 0)
        losses += max(-diff, 0)
    avg_gain = gains / period
    avg_loss = losses / period
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    rsi[period] = 100 - 100 / (1 + rs)
    for i in range(period + 1, len(series)):
        diff = series[i] - series[i-1]
        gain = max(diff, 0)
        loss = max(-diff, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi[i] = 100 - 100 / (1 + rs)
    return rsi


def compute_bollinger(series, period=20, std_dev=2):
    middle = compute_sma(series, period)
    bb_upper = [None] * len(series)
    bb_lower = [None] * len(series)
    for i in range(period - 1, len(series)):
        window = series[i - period + 1:i + 1]
        std = math.sqrt(sum((x - middle[i]) ** 2 for x in window) / period)
        bb_upper[i] = middle[i] + std_dev * std
        bb_lower[i] = middle[i] - std_dev * std
    return bb_upper, middle, bb_lower


def compute_atr(high, low, close, period=14):
    if len(close) < 2:
        return [None] * len(close)
    tr = [None]
    for i in range(1, len(close)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i-1]) if len(close) > 0 else 0
        lc = abs(low[i] - close[i-1]) if len(close) > 0 else 0
        tr.append(max(hl, hc, lc))
    atr = [None] * len(tr)
    if len(tr) >= period + 1:
        atr[period] = sum(tr[1:period + 1]) / period
        for i in range(period + 1, len(tr)):
            atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return atr


def compute_ema(series, period):
    """EMA calculation"""
    if len(series) < period:
        return [None] * len(series)
    ema = [None] * len(series)
    multiplier = 2 / (period + 1)
    # Start with SMA
    ema[period-1] = sum(series[:period]) / period
    for i in range(period, len(series)):
        ema[i] = (series[i] - ema[i-1]) * multiplier + ema[i-1]
    return ema


# ─── 回测引擎 ──────────────────────────────────────────────────

def backtest_entry(closes, entry_condition, hold_bars=5, atr_stop=None, entry_price_fn=None):
    """
    通用入场回测，支持ATR止损。
    entry_condition: function(idx) -> bool
    hold_bars: 固定持有K线数
    atr_stop: { 'atr': [...], 'multiplier': float } — 若有则加入ATR移动止损
    entry_price_fn: 可选，用于获取入场价格（默认用close）
    返回: { signals, wins, win_rate, ci_lower, avg_return, returns, ... }
    """
    signals = []
    for i in range(len(closes)):
        if entry_condition(i):
            signals.append(i)
    
    if not signals:
        return {"signals": 0, "wins": 0, "losses": 0, "win_rate": 0, "ci_lower": 0,
                "avg_return": 0, "total_return": 0, "median_return": 0,
                "p10": 0, "p25": 0, "p75": 0, "p90": 0,
                "max_consec_losses": 0, "sharpe": 0, "profit_factor": 0,
                "stop_loss_hit": 0, "returns": []}
    
    wins = 0
    losses = 0
    returns = []
    stop_hits = 0
    
    for entry_idx in signals:
        entry_price = entry_price_fn(entry_idx) if entry_price_fn else closes[entry_idx]
        
        if entry_price <= 0:
            continue
        
        exit_price = None
        
        # ATR trailing stop logic
        if atr_stop and atr_stop['atr'][entry_idx] is not None and atr_stop['atr'][entry_idx] > 0:
            atr_val = atr_stop['atr'][entry_idx]
            stop_dist = atr_val * atr_stop['multiplier']
            stop_price = entry_price - stop_dist  # long stop
            
            # Walk forward with trailing stop
            for offset in range(1, hold_bars + 1):
                bar_idx = entry_idx + offset
                if bar_idx >= len(closes):
                    break
                
                low = None  # We'll compute from entry_price_fn context if needed
                # Check if stop was hit (we'll approximate using low)
                # For simplicity, check if bar's range crosses stop price
                # We need high/low data... for now just close-based check
                
                # Update trailing stop (move up if price rises)
                if closes[bar_idx] > entry_price:
                    new_stop = closes[bar_idx] - stop_dist
                    if new_stop > stop_price:
                        stop_price = new_stop
                
                # Check if bar low < stop price => stop loss triggered
                # Simplified: if close drops below stop, exit at stop
                
            # Simple version: check if any bar in the hold period closes below stop
            hit = False
            for offset in range(1, hold_bars + 1):
                bar_idx = entry_idx + offset
                if bar_idx >= len(closes):
                    break
                if closes[bar_idx] < stop_price:
                    hit = True
                    stop_hits += 1
                    exit_price = stop_price
                    break
            
            if not hit:
                exit_idx = entry_idx + hold_bars
                if exit_idx < len(closes):
                    exit_price = closes[exit_idx]
                else:
                    continue  # can't exit
        else:
            # Fixed hold, no stop
            exit_idx = entry_idx + hold_bars
            if exit_idx >= len(closes):
                continue
            exit_price = closes[exit_idx]
        
        if exit_price is None or exit_price <= 0:
            continue
        
        ret = (exit_price - entry_price) / entry_price * 100
        returns.append(ret)
        if ret > 0:
            wins += 1
        else:
            losses += 1
    
    if not returns:
        return {"signals": len(signals), "wins": 0, "losses": 0, "win_rate": 0, "ci_lower": 0,
                "avg_return": 0, "total_return": 0, "median_return": 0,
                "p10": 0, "p25": 0, "p75": 0, "p90": 0,
                "max_consec_losses": 0, "sharpe": 0, "profit_factor": 0,
                "stop_loss_hit": 0, "returns": []}
    
    n = len(returns)
    win_rate = wins / n * 100
    avg_return = sum(returns) / n
    total_return = sum(returns)
    
    # 95% CI lower bound
    p = wins / n
    se = math.sqrt(p * (1-p) / n) if n > 1 else 0
    ci_lower = max(0, (p - 1.96 * se)) * 100
    
    sorted_ret = sorted(returns)
    p10 = sorted_ret[int(n * 0.1)] if n >= 10 else sorted_ret[0]
    p25 = sorted_ret[int(n * 0.25)] if n >= 4 else sorted_ret[0]
    p75 = sorted_ret[int(n * 0.75)] if n >= 4 else sorted_ret[-1]
    p90 = sorted_ret[int(n * 0.9)] if n >= 10 else sorted_ret[-1]
    median_ret = sorted_ret[n // 2]
    
    # Max consecutive losses
    max_consec_loss = 0
    curr_loss = 0
    for r in returns:
        if r <= 0:
            curr_loss += 1
            max_consec_loss = max(max_consec_loss, curr_loss)
        else:
            curr_loss = 0
    
    # Sharpe-like (return / std)
    if n > 1:
        mean_ret = sum(returns) / n
        variance = sum((x - mean_ret) ** 2 for x in returns) / (n - 1)
        std = math.sqrt(variance)
        sharpe = mean_ret / std if std > 0 else 0
    else:
        sharpe = 0
    
    # Profit factor
    gross_wins = sum(r for r in returns if r > 0)
    gross_losses = abs(sum(r for r in returns if r < 0))
    pf = gross_wins / gross_losses if gross_losses > 0 else float('inf')
    
    return {
        "signals": n,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "ci_lower": round(ci_lower, 2),
        "avg_return": round(avg_return, 4),
        "total_return": round(total_return, 4),
        "median_return": round(median_ret, 4),
        "p10": round(p10, 4),
        "p25": round(p25, 4),
        "p75": round(p75, 4),
        "p90": round(p90, 4),
        "max_consec_losses": max_consec_loss,
        "sharpe": round(sharpe, 4),
        "profit_factor": round(pf, 2) if pf != float('inf') else 99,
        "stop_loss_hit": stop_hits,
        "returns": returns,
    }


# ─── 入口条件工厂 ──────────────────────────────────────────────

def make_entry_rsi30_bull(rsi, opens, closes):
    """M1 RSI<30 + 收阳"""
    def entry(i):
        if rsi[i] is None or rsi[i] >= 30:
            return False
        if closes[i] <= opens[i]:
            return False
        return True
    return entry


def make_entry_rsi25_bull(rsi, opens, closes):
    """M1 RSI<25 + 收阳 (更严格)"""
    def entry(i):
        if rsi[i] is None or rsi[i] >= 25:
            return False
        if closes[i] <= opens[i]:
            return False
        return True
    return entry


def make_entry_bb_lower_bull(bb_lower, opens, closes):
    """M1 BB下轨+收阳"""
    def entry(i):
        if bb_lower[i] is None:
            return False
        if closes[i] > bb_lower[i] * 1.001:  # price must be at/near BB lower
            return False
        if closes[i] <= opens[i]:
            return False
        return True
    return entry


def make_entry_m5_trend_confirmation(m1_time, m5_closes, m5_ema20, hold_cache):
    """
    Multi-timeframe: require M5 EMA20 trend to be up at signal time.
    Returns a wrapped entry function that checks M5 context.
    """
    # Build M5 lookup: for each M1 timestamp, find corresponding M5 EMA20
    m5_lookup = {}
    m5_idx = 0
    for ts, ema_val in zip(hold_cache['m5_ts_list'], hold_cache['m5_ema_list']):
        m5_lookup[ts] = ema_val
    
    def wrapper(base_entry_fn):
        def entry(i):
            if not base_entry_fn(i):
                return False
            # Get M1 bar timestamp
            ts = hold_cache['m1_ts_list'][i]
            # Find nearest M5 bar at or before this time
            best_ema = None
            for mts in sorted(m5_lookup.keys()):
                if mts <= ts:
                    best_ema = m5_lookup[mts]
                else:
                    break
            if best_ema is None:
                return False
            # Require M5 close > EMA20 (uptrend)
            m5_close = None
            for j in range(len(hold_cache['m5_ts_list'])):
                if hold_cache['m5_ts_list'][j] <= ts:
                    if j < len(hold_cache['m5_closes_list']):
                        m5_close = hold_cache['m5_closes_list'][j]
                else:
                    break
            if m5_close is None:
                return False
            return m5_close > best_ema
        return entry
    return wrapper


# ─── 品种特异性测试 ────────────────────────────────────────────

def test_xagusd_specific(m1_data):
    """XAGUSD 特异策略深度验证"""
    results = {}
    klines = m1_data.get('XAGUSD', [])
    if not klines or len(klines) < 200:
        return {"error": "insufficient XAGUSD data"}
    
    closes = [k['close'] for k in klines]
    opens = [k['open'] for k in klines]
    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    volumes = [k['volume'] for k in klines]
    
    rsi = compute_rsi(closes, 14)
    bb_upper, bb_mid, bb_lower = compute_bollinger(closes, 20, 2)
    atr = compute_atr(highs, lows, closes, 14)
    vol_ma20 = compute_sma(volumes, 20)
    
    sym_res = {}
    
    # ─── D1: XAGUSD M1 RSI<30 + 收阳 — 多持有期 ───
    cond_rsi = make_entry_rsi30_bull(rsi, opens, closes)
    for hold in [3, 5, 8, 13]:
        bt = backtest_entry(closes, cond_rsi, hold_bars=hold)
        sym_res[f"D1_XAG_RSI30_Bull_hold{hold}"] = bt
    
    # ─── D2: XAGUSD M1 RSI<30 + 收阳 + ATR止损 ───
    for mult in [0.5, 1.0, 1.5, 2.0]:
        atr_stop = {'atr': atr, 'multiplier': mult}
        bt = backtest_entry(closes, cond_rsi, hold_bars=5, atr_stop=atr_stop)
        sym_res[f"D2_XAG_RSI30_ATRstop{mult}x_hold5"] = bt
    
    # ─── D3: XAGUSD BB下轨+RSI<40+收阳 ───
    def cond_bb_rsi40(i):
        if bb_lower[i] is None or rsi[i] is None:
            return False
        if closes[i] > bb_lower[i] * 1.001:
            return False
        if rsi[i] >= 40:
            return False
        if closes[i] <= opens[i]:
            return False
        return True
    
    for hold in [3, 5, 8]:
        bt = backtest_entry(closes, cond_bb_rsi40, hold_bars=hold)
        sym_res[f"D3_XAG_BBlower_RSI40_hold{hold}"] = bt
    
    # ─── D4: XAGUSD 放量+RSI超卖 ───
    def cond_vol_rsi(i):
        if rsi[i] is None or vol_ma20[i] is None or vol_ma20[i] <= 0:
            return False
        if rsi[i] >= 30:
            return False
        if volumes[i] / vol_ma20[i] < 1.5:
            return False
        if closes[i] <= opens[i]:
            return False
        return True
    
    for hold in [3, 5]:
        bt = backtest_entry(closes, cond_vol_rsi, hold_bars=hold)
        sym_res[f"D4_XAG_VolSurge_RSI30_hold{hold}"] = bt
    
    results["XAGUSD"] = sym_res
    return results


def test_us30_specific(m1_data):
    """US30 特异策略深度验证"""
    results = {}
    klines = m1_data.get('US30', [])
    if not klines or len(klines) < 200:
        return {"error": "insufficient US30 data"}
    
    closes = [k['close'] for k in klines]
    opens = [k['open'] for k in klines]
    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    
    rsi = compute_rsi(closes, 14)
    bb_upper, bb_mid, bb_lower = compute_bollinger(closes, 20, 2)
    atr = compute_atr(highs, lows, closes, 14)
    
    sym_res = {}
    
    # ─── E1: US30 M1 RSI<25 + 收阳 (更严格) ───
    cond_rsi25 = make_entry_rsi25_bull(rsi, opens, closes)
    for hold in [3, 5, 8, 13]:
        bt = backtest_entry(closes, cond_rsi25, hold_bars=hold)
        sym_res[f"E1_US30_RSI25_Bull_hold{hold}"] = bt
    
    # ─── E2: US30 M1 RSI<30 + 收阳 + ATR止损 ───
    cond_rsi30 = make_entry_rsi30_bull(rsi, opens, closes)
    for mult in [0.5, 1.0, 1.5, 2.0]:
        atr_stop = {'atr': atr, 'multiplier': mult}
        bt = backtest_entry(closes, cond_rsi30, hold_bars=5, atr_stop=atr_stop)
        sym_res[f"E2_US30_RSI30_ATRstop{mult}x_hold5"] = bt
    
    # ─── E3: US30 BB下轨+收阳 ───
    cond_bb = make_entry_bb_lower_bull(bb_lower, opens, closes)
    for hold in [3, 5, 8]:
        bt = backtest_entry(closes, cond_bb, hold_bars=hold)
        sym_res[f"E3_US30_BBlower_Bull_hold{hold}"] = bt
    
    # ─── E4: US30 BB下轨+RSI<30+收阳 ───
    def cond_bb_rsi30(i):
        if bb_lower[i] is None or rsi[i] is None:
            return False
        if closes[i] > bb_lower[i] * 1.001:
            return False
        if rsi[i] >= 30:
            return False
        if closes[i] <= opens[i]:
            return False
        return True
    
    for hold in [3, 5]:
        bt = backtest_entry(closes, cond_bb_rsi30, hold_bars=hold)
        sym_res[f"E4_US30_BBlower_RSI30_hold{hold}"] = bt
    
    results["US30"] = sym_res
    return results


# ─── 多时间框架验证 (M1 entry + M5 trend) ────────────────────

def test_multitimeframe(m1_data, m5_data):
    """M1 entry with M5 trend confirmation."""
    results = {}
    
    for sym in SYMBOLS:
        m1_klines = m1_data.get(sym, [])
        m5_klines = m5_data.get(sym, [])
        
        if not m1_klines or len(m1_klines) < 200 or not m5_klines or len(m5_klines) < 100:
            continue
        
        m1_closes = [k['close'] for k in m1_klines]
        m1_opens = [k['open'] for k in m1_klines]
        m1_highs = [k['high'] for k in m1_klines]
        m1_lows = [k['low'] for k in m1_klines]
        m1_ts = [k['ts'] for k in m1_klines]
        
        m5_closes = [k['close'] for k in m5_klines]
        m5_ts = [k['ts'] for k in m5_klines]
        
        # M5 indicators
        m5_ema20 = compute_ema(m5_closes, 20)
        m5_rsi = compute_rsi(m5_closes, 14)
        m5_bb_upper, m5_bb_mid, m5_bb_lower = compute_bollinger(m5_closes, 20, 2)
        
        # M1 indicators
        m1_rsi = compute_rsi(m1_closes, 14)
        m1_bb_upper, m1_bb_mid, m1_bb_lower = compute_bollinger(m1_closes, 20, 2)
        m1_atr = compute_atr(m1_highs, m1_lows, m1_closes, 14)
        
        sym_res = {}
        
        # Helper: precompute M5 trend at each M1 timestamp
        m1_idx_for_m5 = []
        m5_ptr = 0
        for ts in m1_ts:
            while m5_ptr < len(m5_ts) - 1 and m5_ts[m5_ptr + 1] <= ts:
                m5_ptr += 1
            m1_idx_for_m5.append(m5_ptr)
        
        # ─── F1: M1 RSI<30+收阳 + M5 EMA20上升趋势 ───
        def make_cond_m1_rsi_m5_trend(m1_rsi_local, m1_opens_local, m1_closes_local, m1_idx_m5, m5_ema_local, m5_closes_local):
            def cond(i):
                if i >= len(m1_rsi_local) or m1_rsi_local[i] is None:
                    return False
                if m1_rsi_local[i] >= 30:
                    return False
                if m1_closes_local[i] <= m1_opens_local[i]:
                    return False
                # M5 trend check
                m5_i = m1_idx_m5[i] if i < len(m1_idx_m5) else -1
                if m5_i < 20 or m5_i >= len(m5_ema_local) or m5_ema_local[m5_i] is None:
                    return False
                if m5_closes_local[m5_i] <= m5_ema_local[m5_i]:
                    return False
                return True
            return cond
        
        cond_trend = make_cond_m1_rsi_m5_trend(m1_rsi, m1_opens, m1_closes, m1_idx_for_m5, m5_ema20, m5_closes)
        for hold in [3, 5, 8]:
            bt = backtest_entry(m1_closes, cond_trend, hold_bars=hold)
            sym_res[f"F1_{sym}_M1rsi30_M5trend_hold{hold}"] = bt
        
        # ─── F2: M1 BB下轨+收阳 + M5 EMA20上升趋势 ───
        def make_cond_m1_bb_m5_trend(m1_bb_lower_local, m1_opens_local, m1_closes_local, m1_idx_m5, m5_ema_local, m5_closes_local):
            def cond(i):
                if i >= len(m1_bb_lower_local) or m1_bb_lower_local[i] is None:
                    return False
                if m1_closes_local[i] > m1_bb_lower_local[i] * 1.001:
                    return False
                if m1_closes_local[i] <= m1_opens_local[i]:
                    return False
                # M5 trend
                m5_i = m1_idx_m5[i] if i < len(m1_idx_m5) else -1
                if m5_i < 20 or m5_i >= len(m5_ema_local) or m5_ema_local[m5_i] is None:
                    return False
                if m5_closes_local[m5_i] <= m5_ema_local[m5_i]:
                    return False
                return True
            return cond
        
        cond_bb_trend = make_cond_m1_bb_m5_trend(m1_bb_lower, m1_opens, m1_closes, m1_idx_for_m5, m5_ema20, m5_closes)
        for hold in [3, 5, 8]:
            bt = backtest_entry(m1_closes, cond_bb_trend, hold_bars=hold)
            sym_res[f"F2_{sym}_M1bblower_M5trend_hold{hold}"] = bt
        
        # ─── F3: M1 RSI<30+收阳 + M5 RSI<50 (oversold on both TFs) ───
        def make_cond_m1_rsi_m5_rsi(m1_rsi_local, m1_opens_local, m1_closes_local, m1_idx_m5, m5_rsi_local):
            def cond(i):
                if i >= len(m1_rsi_local) or m1_rsi_local[i] is None:
                    return False
                if m1_rsi_local[i] >= 30:
                    return False
                if m1_closes_local[i] <= m1_opens_local[i]:
                    return False
                # M5 RSI check
                m5_i = m1_idx_m5[i] if i < len(m1_idx_m5) else -1
                if m5_i < 14 or m5_i >= len(m5_rsi_local) or m5_rsi_local[m5_i] is None:
                    return False
                if m5_rsi_local[m5_i] >= 50:  # not oversold on M5
                    return False
                return True
            return cond
        
        cond_m5rsi = make_cond_m1_rsi_m5_rsi(m1_rsi, m1_opens, m1_closes, m1_idx_for_m5, m5_rsi)
        for hold in [3, 5, 8]:
            bt = backtest_entry(m1_closes, cond_m5rsi, hold_bars=hold)
            sym_res[f"F3_{sym}_M1rsi30_M5rsi50_hold{hold}"] = bt
        
        # ─── F4: M1 RSI<30+收阳 + M5 BB下轨 (double BB support) ───
        def make_cond_m1_rsi30_m5_bb(m1_rsi_local, m1_opens_local, m1_closes_local, m1_idx_m5, m5_bb_lower_local, m5_closes_local):
            def cond(i):
                if i >= len(m1_rsi_local) or m1_rsi_local[i] is None:
                    return False
                if m1_rsi_local[i] >= 30:
                    return False
                if m1_closes_local[i] <= m1_opens_local[i]:
                    return False
                # M5 near BB lower
                m5_i = m1_idx_m5[i] if i < len(m1_idx_m5) else -1
                if m5_i < 20 or m5_i >= len(m5_bb_lower_local) or m5_bb_lower_local[m5_i] is None:
                    return False
                if m5_closes_local[m5_i] > m5_bb_lower_local[m5_i] * 1.005:
                    return False
                return True
            return cond
        
        cond_double_bb = make_cond_m1_rsi30_m5_bb(m1_rsi, m1_opens, m1_closes, m1_idx_for_m5, m5_bb_lower, m5_closes)
        for hold in [3, 5]:
            bt = backtest_entry(m1_closes, cond_double_bb, hold_bars=hold)
            sym_res[f"F4_{sym}_DoubleBB_hold{hold}"] = bt
        
        results[sym] = sym_res
    
    return results


# ─── 模式退化检测 — 对比 Round 1/2 结果 ─────────────────────

def check_pattern_decay(m1_data, m5_data):
    """
    复现 Round 1/2 的核心测试，检测模式是否退化。
    返回对比数据。
    """
    decay_results = {}
    
    for sym in SYMBOLS:
        m1_klines = m1_data.get(sym, [])
        m5_klines = m5_data.get(sym, [])
        
        if not m1_klines or len(m1_klines) < 200:
            continue
        
        # M1 tests
        m1_closes = [k['close'] for k in m1_klines]
        m1_opens = [k['open'] for k in m1_klines]
        m1_rsi = compute_rsi(m1_closes, 14)
        
        sym_decay = {}
        
        # Test 1: M1 RSI<30+收阳 → hold 5 M1 (Round 2 core test)
        cond_rsi = make_entry_rsi30_bull(m1_rsi, m1_opens, m1_closes)
        bt = backtest_entry(m1_closes, cond_rsi, hold_bars=5)
        sym_decay["M1_RSI30_Bull_hold5"] = {
            "signals": bt["signals"],
            "win_rate": bt["win_rate"],
            "ci_lower": bt["ci_lower"],
            "avg_return": bt["avg_return"],
        }
        
        # Test 2: M1 RSI<30+收阳 → hold 3 M1
        bt2 = backtest_entry(m1_closes, cond_rsi, hold_bars=3)
        sym_decay["M1_RSI30_Bull_hold3"] = {
            "signals": bt2["signals"],
            "win_rate": bt2["win_rate"],
            "ci_lower": bt2["ci_lower"],
            "avg_return": bt2["avg_return"],
        }
        
        # M5 tests
        if m5_klines and len(m5_klines) >= 200:
            m5_closes = [k['close'] for k in m5_klines]
            m5_opens = [k['open'] for k in m5_klines]
            m5_bb_upper, m5_bb_mid, m5_bb_lower = compute_bollinger(m5_closes, 20, 2)
            m5_rsi = compute_rsi(m5_closes, 14)
            
            # Test 3: M5 BB下轨+收阳 → hold 5 M5 (Round 1 find)
            cond_bb = make_entry_bb_lower_bull(m5_bb_lower, m5_opens, m5_closes)
            bt3 = backtest_entry(m5_closes, cond_bb, hold_bars=5)
            sym_decay["M5_BBlower_Bull_hold5"] = {
                "signals": bt3["signals"],
                "win_rate": bt3["win_rate"],
                "ci_lower": bt3["ci_lower"],
                "avg_return": bt3["avg_return"],
            }
            
            # Test 4: M5 RSI<30+收阳 → hold 5 M5
            cond_m5_rsi = make_entry_rsi30_bull(m5_rsi, m5_opens, m5_closes)
            bt4 = backtest_entry(m5_closes, cond_m5_rsi, hold_bars=5)
            sym_decay["M5_RSI30_Bull_hold5"] = {
                "signals": bt4["signals"],
                "win_rate": bt4["win_rate"],
                "ci_lower": bt4["ci_lower"],
                "avg_return": bt4["avg_return"],
            }
        
        decay_results[sym] = sym_decay
    
    return decay_results


# ─── 跨品种汇总 ──────────────────────────────────────────────

def cross_summary(symbol_results):
    """Aggregate results across symbols for each test variant."""
    all_variants = set()
    for sym in SYMBOLS:
        sr = symbol_results.get(sym, {})
        for vname in sr:
            all_variants.add(vname)
    
    summary = {}
    for vname in sorted(all_variants):
        all_rets = []
        for sym in SYMBOLS:
            bt = symbol_results.get(sym, {}).get(vname, {})
            if bt and "returns" in bt and bt["returns"]:
                all_rets.extend(bt["returns"])
        
        if not all_rets:
            continue
        
        n = len(all_rets)
        wins = sum(1 for r in all_rets if r > 0)
        wr = wins / n * 100
        p = wins / n
        se = math.sqrt(p * (1-p) / n) if n > 1 else 0
        ci_lower = max(0, (p - 1.96 * se)) * 100
        avg_ret = sum(all_rets) / n
        sorted_all = sorted(all_rets)
        median_ret = sorted_all[n // 2] if n > 0 else 0
        
        gross_profit = sum(r for r in all_rets if r > 0)
        gross_loss = abs(sum(r for r in all_rets if r < 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        summary[vname] = {
            "total_signals": n,
            "total_wins": wins,
            "win_rate": round(wr, 2),
            "ci_lower": round(ci_lower, 2),
            "avg_return": round(avg_ret, 4),
            "median_return": round(median_ret, 4),
            "profit_factor": round(pf, 2) if pf != float('inf') else 99,
            "is_significant": ci_lower > 50,
        }
    
    return summary


# ─── 报告生成 ──────────────────────────────────────────────────

def generate_report(mtf_results, spec_results, decay_results, mtf_summary, decay_summary):
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    report = f"""# 📊 Scalping Round 6 — M1/M5 多时间框架 + 止损嵌入深度验证

> **生成时间**: {timestamp} BJT
> **研究轮次**: Round 6
> **品种**: XAUUSD, XAGUSD, JP225, US500, US30（5个）
> **时间框架**: M1 (entry) + M5/M15 (trend filter)
> **数据量**: 每品种 5000 根 M1 K线 + 5000 根 M5 K线 + 5000 根 M15 K线

---

## 一、执行概览

### 本轮测试假设

**品种特异性验证（D/E系列）:**
- **D1**: XAGUSD M1 RSI<30+收阳 → hold 3/5/8/13 M1（深度验证品种特异）
- **D2**: XAGUSD M1 RSI<30 + ATR止损 (0.5x/1.0x/1.5x/2.0x) → hold 5 M1
- **D3**: XAGUSD BB下轨+RSI<40+收阳 → hold 3/5/8 M1
- **D4**: XAGUSD 放量(>1.5x均量)+RSI<30+收阳 → hold 3/5 M1
- **E1**: US30 M1 RSI<25+收阳 → hold 3/5/8/13 M1（更严格）
- **E2**: US30 M1 RSI<30 + ATR止损 (0.5x/1.0x/1.5x/2.0x) → hold 5 M1
- **E3**: US30 M1 BB下轨+收阳 → hold 3/5/8 M1
- **E4**: US30 M1 BB下轨+RSI<30+收阳 → hold 3/5 M1

**多时间框架验证（F系列）:**
- **F1**: M1 RSI<30+收阳 + M5 EMA20上升趋势 → hold 3/5/8 M1
- **F2**: M1 BB下轨+收阳 + M5 EMA20上升趋势 → hold 3/5/8 M1
- **F3**: M1 RSI<30+收阳 + M5 RSI<50（双时间框架超卖）→ hold 3/5/8 M1
- **F4**: M1 RSI<30+收阳 + M5 BB下轨（双BB支撑）→ hold 3/5 M1

**模式退化检测（G系列）:**
- G1: M1 RSI<30+收阳 hold3 — 与 Round 1/2 结果对比
- G2: M1 RSI<30+收阳 hold5 — 与 Round 2 结果对比
- G3: M5 BB下轨+收阳 hold5 — 与 Round 1 结果对比
- G4: M5 RSI<30+收阳 hold5 — 新增基准

---

## 二、品种特异性验证 — XAGUSD

"""
    
    # XAGUSD specific results
    xag = spec_results.get("XAGUSD", {})
    if xag and "error" not in xag:
        report += "### D系列 — XAGUSD M1 深度验证\n\n"
        report += "| 测试变体 | 胜率 | CI下限 | 信号数 | 平均收益 | 中位收益 | 盈亏比 | Sharpe |\n"
        report += "|:--------:|:----:|:------:|:-----:|:--------:|:--------:|:-----:|:-----:|\n"
        for vname in sorted(xag.keys()):
            vd = xag[vname]
            if vd and vd.get("signals", 0) > 0:
                sig = "✅" if vd.get("ci_lower", 0) > 50 else "⚠️"
                report += f"| {sig} {vname} | {vd.get('win_rate', 0)}% | {vd.get('ci_lower', 0)}% | {vd.get('signals', 0)} | {vd.get('avg_return', 0):+.4f}% | {vd.get('median_return', 0):+.4f}% | {vd.get('profit_factor', 0)} | {vd.get('sharpe', 0)} |\n"
        report += "\n"
    else:
        report += "### ❌ XAGUSD 数据不足\n\n"
    
    report += "## 三、品种特异性验证 — US30\n\n"
    
    us30 = spec_results.get("US30", {})
    if us30 and "error" not in us30:
        report += "### E系列 — US30 M1 深度验证\n\n"
        report += "| 测试变体 | 胜率 | CI下限 | 信号数 | 平均收益 | 中位收益 | 盈亏比 | Sharpe |\n"
        report += "|:--------:|:----:|:------:|:-----:|:--------:|:--------:|:-----:|:-----:|\n"
        for vname in sorted(us30.keys()):
            vd = us30[vname]
            if vd and vd.get("signals", 0) > 0:
                sig = "✅" if vd.get("ci_lower", 0) > 50 else "⚠️"
                report += f"| {sig} {vname} | {vd.get('win_rate', 0)}% | {vd.get('ci_lower', 0)}% | {vd.get('signals', 0)} | {vd.get('avg_return', 0):+.4f}% | {vd.get('median_return', 0):+.4f}% | {vd.get('profit_factor', 0)} | {vd.get('sharpe', 0)} |\n"
        report += "\n"
    else:
        report += "### ❌ US30 数据不足\n\n"
    
    report += """## 四、多时间框架验证 — M1+M5

### F系列 — 跨品种汇总

"""
    
    # Multi-timeframe summary
    sig_mtf = {k: v for k, v in mtf_summary.items() if v.get("is_significant") and v.get("total_signals", 0) >= 5}
    all_mtf = {k: v for k, v in mtf_summary.items() if v.get("total_signals", 0) >= 3}
    
    if sig_mtf:
        sorted_mtf = sorted(sig_mtf.items(), key=lambda x: x[1]["ci_lower"], reverse=True)
        report += "### 🔥 统计显著的多TF模式 (CI下限 > 50%)\n\n"
        report += "| 测试变体 | 胜率 | CI下限 | 信号数 | 平均收益 | 中位收益 | 盈亏比 |\n"
        report += "|:--------:|:----:|:------:|:-----:|:--------:|:--------:|:-----:|\n"
        for vname, vdata in sorted_mtf:
            report += f"| {vname} | {vdata['win_rate']}% | {vdata['ci_lower']}% | {vdata['total_signals']} | {vdata['avg_return']:+.4f}% | {vdata['median_return']:+.4f}% | {vdata['profit_factor']} |\n"
        report += "\n"
    else:
        report += "### ⚠️ 多TF模式未发现统计显著结果\n\n"
    
    report += "### F系列 全排名（按胜率）\n\n"
    if all_mtf:
        sorted_all = sorted(all_mtf.items(), key=lambda x: x[1]["win_rate"], reverse=True)
        report += "| 测试变体 | 胜率 | CI下限 | 信号数 | 平均收益 | 显著? |\n"
        report += "|:--------:|:----:|:------:|:-----:|:--------:|:----:|\n"
        for vname, vdata in sorted_all:
            sig = "✅" if vdata.get("is_significant") else "⚠️"
            report += f"| {vname} | {vdata['win_rate']}% | {vdata['ci_lower']}% | {vdata['total_signals']} | {vdata['avg_return']:+.4f}% | {sig} |\n"
        report += "\n"
    
    # Per-symbol best multi-TF
    report += "### F系列 各品种最佳多TF测试\n\n"
    report += "| 品种 | 最佳测试 | 胜率 | CI下限 | 信号数 | 平均收益 |\n"
    report += "|:---:|:--------:|:----:|:------:|:-----:|:--------:|\n"
    for sym in SYMBOLS:
        sr = mtf_results.get(sym, {})
        best_v = None
        best_ci = 0
        best_data = None
        for vname, vd in sr.items():
            if vd and vd.get("signals", 0) >= 3:
                ci = vd.get("ci_lower", 0)
                if ci > best_ci:
                    best_ci = ci
                    best_v = vname
                    best_data = vd
        if best_v:
            sig = "✅" if best_ci > 50 else "⚠️"
            report += f"| {sym} | {sig} {best_v} | {best_data.get('win_rate', 0)}% | {best_ci}% | {best_data.get('signals', 0)} | {best_data.get('avg_return', 0):+.4f}% |\n"
        else:
            report += f"| {sym} | — | — | — | — | — |\n"
    report += "\n"
    
    # ─── Pattern decay section ───
    report += """## 五、模式退化检测

### G系列 — 与 Round 1/2 核心发现对比

"""
    
    ref_data = {
        "R1_M1_RSI30_Bull_hold5": {"win_rate": 55.50, "ci_lower": 48.00, "n": 218},
        "R2_M1_RSI30_Bull_hold5": {"win_rate": 60.55, "ci_lower": 53.93, "n": 218},
        "R2_M1_RSI30_Bull_hold3": {"win_rate": 56.88, "ci_lower": 50.24, "n": 218},
        "R1_M5_BBlower_Bull_hold5": {"win_rate": 54.17, "ci_lower": 51.30, "n": 1163},
    }
    
    report += "| 测试 | 品种 | 历史WR | 历史CI下限 | 本轮WR | 本轮CI下限 | 信号数 | 退化状态 |\n"
    report += "|:---:|:---:|:-----:|:---------:|:-----:|:---------:|:-----:|:-------:|\n"
    
    for sym in SYMBOLS:
        sd = decay_results.get(sym, {})
        if not sd:
            continue
        
        # G1: M1 RSI<30+收阳 hold3
        if "M1_RSI30_Bull_hold3" in sd:
            d = sd["M1_RSI30_Bull_hold3"]
            ref = ref_data["R2_M1_RSI30_Bull_hold3"]
            delta = d["win_rate"] - ref["win_rate"]
            status = "✅ 增强" if delta > 3 else ("⚠️ 持平" if delta > -3 else "❌ 退化")
            report += f"| M1 RSI30+收阳 hold3 | {sym} | {ref['win_rate']}% | {ref['ci_lower']}% | {d['win_rate']}% | {d['ci_lower']}% | {d['signals']} | {status} |\n"
        
        # G2: M1 RSI<30+收阳 hold5
        if "M1_RSI30_Bull_hold5" in sd:
            d = sd["M1_RSI30_Bull_hold5"]
            ref = ref_data["R2_M1_RSI30_Bull_hold5"]
            delta = d["win_rate"] - ref["win_rate"]
            status = "✅ 增强" if delta > 3 else ("⚠️ 持平" if delta > -3 else "❌ 退化")
            report += f"| M1 RSI30+收阳 hold5 | {sym} | {ref['win_rate']}% | {ref['ci_lower']}% | {d['win_rate']}% | {d['ci_lower']}% | {d['signals']} | {status} |\n"
    
    report += "\n"
    
    for sym in SYMBOLS:
        sd = decay_results.get(sym, {})
        if not sd:
            continue
        if "M5_BBlower_Bull_hold5" in sd:
            d = sd["M5_BBlower_Bull_hold5"]
            ref = ref_data["R1_M5_BBlower_Bull_hold5"]
            delta = d["win_rate"] - ref["win_rate"]
            status = "✅ 增强" if delta > 3 else ("⚠️ 持平" if delta > -3 else "❌ 退化")
            report += f"| M5 BB下轨+收阳 hold5 | {sym} | {ref['win_rate']}% | {ref['ci_lower']}% | {d['win_rate']}% | {d['ci_lower']}% | {d['signals']} | {status} |\n"
    
    report += "\n"
    
    # ─── ATR 止损分析 ───
    report += """## 六、ATR止损效果分析

### XAGUSD — ATR止损对比

"""
    
    for sym_name, sym_key in [("XAGUSD", "XAGUSD"), ("US30", "US30")]:
        sr = spec_results.get(sym_key, {})
        if not sr or "error" in sr:
            continue
        report += f"**{sym_name} M1 RSI<30+收阳 hold5 — ATR止损参数对比:**\n\n"
        report += "| ATR乘数 | 胜率 | CI下限 | 信号数 | 平均收益 | 盈亏比 | Sharpe |\n"
        report += "|:------:|:----:|:------:|:-----:|:--------:|:-----:|:-----:|\n"
        
        base_key = f"D{sym_key[0]}2_{sym_key}_RSI30_ATRstop" if sym_key == "XAGUSD" else f"E2_{sym_key}_RSI30_ATRstop"
        
        for mult in [0.5, 1.0, 1.5, 2.0]:
            vname = f"D2_{sym_key}_RSI30_ATRstop{mult}x_hold5" if sym_key == "XAGUSD" else f"E2_{sym_key}_RSI30_ATRstop{mult}x_hold5"
            vd = sr.get(vname)
            if vd:
                report += f"| {mult}x | {vd.get('win_rate', 0)}% | {vd.get('ci_lower', 0)}% | {vd.get('signals', 0)} | {vd.get('avg_return', 0):+.4f}% | {vd.get('profit_factor', 0)} | {vd.get('sharpe', 0)} |\n"
        
        # Baseline (no stop)
        base = sr.get(f"D1_{sym_key}_RSI30_Bull_hold5" if sym_key == "XAGUSD" else f"E1_{sym_key}_RSI25_Bull_hold5")
        if not base:
            base = sr.get(f"D1_{sym_key}_RSI30_Bull_hold5" if sym_key == "XAGUSD" else None)
        if base:
            report += f"| 无止损 | {base.get('win_rate', 0)}% | {base.get('ci_lower', 0)}% | {base.get('signals', 0)} | {base.get('avg_return', 0):+.4f}% | {base.get('profit_factor', 0)} | {base.get('sharpe', 0)} |\n"
        report += "\n"
    
    # ─── 结论 ───
    report += """## 七、综合结论与下一步

"""
    
    total_sig = len(sig_mtf)
    xag_sig = sum(1 for v in xag.values() if v.get("ci_lower", 0) > 50 and v.get("signals", 0) > 0) if xag and "error" not in xag else 0
    us30_sig = sum(1 for v in us30.values() if v.get("ci_lower", 0) > 50 and v.get("signals", 0) > 0) if us30 and "error" not in us30 else 0
    
    if total_sig + xag_sig + us30_sig > 0:
        report += f"### ✅ 发现 {total_sig + xag_sig + us30_sig} 个统计显著模式\n\n"
    else:
        report += "### ❌ 本轮未发现统计显著模式\n\n"
    
    report += """### Round 7 建议

1. **非对称杠杆策略** — 基于盈亏比>2.0的策略分配仓位
2. **实时信号监控** — 将最佳模式部署为MT5 EA信号
3. **跨品种套利** — XAUUSD/XAGUSD比值回归策略
4. **Tick级入场优化** — 在M1信号出现后的Tick级最佳入场点
5. **动态止损优化** — 基于波动率的自适应止损参数

---

*Round 6 完成 — M1/M5 多时间框架 + 止损嵌入深度验证*
"""
    
    return report


# ─── 主函数 ──────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("📊 Scalping Round 6 — M1/M5 多时间框架 + 止损深度验证")
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Step 1: Fetch data
    print("\n[1/5] 获取 M1 + M5 + M15 数据...")
    data = fetch_mt5(timeframes=['M1', 'M5', 'M15'], lookback=5000)
    
    if "error" in data:
        print(f"ERROR: {data['error']}")
        sys.exit(1)
    
    m1_total = sum(len(v) for v in data.get('M1', {}).values())
    m5_total = sum(len(v) for v in data.get('M5', {}).values())
    m15_total = sum(len(v) for v in data.get('M15', {}).values())
    print(f"  ✅ M1: {m1_total} K线, M5: {m5_total} K线, M15: {m15_total} K线")
    
    # Step 2: Run XAGUSD specific tests
    print("\n[2/5] 执行 XAGUSD 品种特异性验证...")
    xag_results = test_xagusd_specific(data.get('M1', {}))
    
    # Step 3: Run US30 specific tests
    print("\n[3/5] 执行 US30 品种特异性验证...")
    us30_results = test_us30_specific(data.get('M1', {}))
    
    spec_results = {}
    if xag_results and "error" not in xag_results:
        spec_results.update(xag_results)
    if us30_results and "error" not in us30_results:
        spec_results.update(us30_results)
    
    # Step 4: Run multi-timeframe tests
    print("\n[4a/5] 执行多时间框架验证 (M1+M5)...")
    mtf_results = test_multitimeframe(data.get('M1', {}), data.get('M5', {}))
    
    # Step 5: Run pattern decay check
    print("\n[4b/5] 执行模式退化检测...")
    decay_results = check_pattern_decay(data.get('M1', {}), data.get('M5', {}))
    
    # Compute summaries
    mtf_summary = cross_summary(mtf_results)
    
    # Compile best findings
    best_findings = []
    for vname, vdata in sorted(mtf_summary.items(), key=lambda x: x[1].get("ci_lower", 0), reverse=True):
        if vdata.get("is_significant") and vdata.get("total_signals", 0) >= 5:
            best_findings.append({
                "variant": vname,
                "timeframe": "M1+M5",
                "win_rate": vdata["win_rate"],
                "ci_lower": vdata["ci_lower"],
                "signal_count": vdata["total_signals"],
                "avg_return": vdata["avg_return"],
                "profit_factor": vdata["profit_factor"],
            })
    
    # Add best XAGUSD findings
    for sym_key in ["XAGUSD", "US30"]:
        sr = spec_results.get(sym_key, {})
        if sr and "error" not in sr:
            for vname, vd in sr.items():
                if vd.get("ci_lower", 0) > 50 and vd.get("signals", 0) >= 5:
                    best_findings.append({
                        "variant": vname,
                        "timeframe": f"M1-{sym_key}",
                        "win_rate": vd["win_rate"],
                        "ci_lower": vd["ci_lower"],
                        "signal_count": vd["signals"],
                        "avg_return": vd["avg_return"],
                        "profit_factor": vd["profit_factor"],
                    })
    
    # Step 5: Generate reports
    print("\n[5/5] 生成报告...")
    report_md = generate_report(mtf_results, spec_results, decay_results, mtf_summary, {})
    
    # Save reports
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    report_path = os.path.join(reports_dir, "round_006.md")
    with open(report_path, "w", encoding='utf-8') as f:
        f.write(report_md)
    print(f"  ✅ 报告保存: {report_path}")
    
    json_path = os.path.join(reports_dir, "round_006.json")
    json_output = {
        "round": 6,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "hypotheses_tested": [
            "XAGUSD_RSI30_Bull_multi_hold",
            "XAGUSD_ATR_stop_validation",
            "XAGUSD_BBlower_RSI40",
            "XAGUSD_VolSurge_RSI30",
            "US30_RSI25_Bull_multi_hold",
            "US30_ATR_stop_validation",
            "US30_BBlower_variants",
            "M1_RSI30_M5_trend_confirmation",
            "M1_BBlower_M5_trend_confirmation",
            "M1_RSI30_M5_RSI50",
            "Double_BB_support",
            "Pattern_decay_check_vs_R1R2",
        ],
        "mtf_summary": mtf_summary,
        "best_findings": best_findings,
    }
    with open(json_path, "w", encoding='utf-8') as f:
        json.dump(json_output, f, ensure_ascii=False, indent=2)
    print(f"  ✅ JSON摘要保存: {json_path}")
    
    # Print summary
    print(f"\n{'=' * 70}")
    print("📊 ROUND 6 — 结果摘要")
    print(f"{'=' * 70}")
    
    print(f"\n多TF显著模式: {len([v for v in mtf_summary.values() if v.get('is_significant')])}个")
    for vname, vdata in sorted(mtf_summary.items(), key=lambda x: x[1].get("ci_lower", 0), reverse=True)[:5]:
        sig = "✅" if vdata.get("is_significant") else "⚠️"
        print(f"  {sig} {vname}: WR={vdata['win_rate']}% CI={vdata['ci_lower']}% n={vdata['total_signals']} avg={vdata['avg_return']:+.4f}%")
    
    for sym_key in ["XAGUSD", "US30"]:
        sr = spec_results.get(sym_key, {})
        if sr and "error" not in sr:
            print(f"\n{sym_key} 最佳:")
            for vname, vd in sorted(sr.items(), key=lambda x: x[1].get("ci_lower", 0), reverse=True)[:3]:
                if vd.get("signals", 0) > 0:
                    sig = "✅" if vd.get("ci_lower", 0) > 50 else "⚠️"
                    print(f"  {sig} {vname}: WR={vd.get('win_rate', 0)}% CI={vd.get('ci_lower', 0)}% n={vd.get('signals', 0)} avg={vd.get('avg_return', 0):+.4f}%")
    
    print(f"\n{'=' * 70}")
    print("完成 ✅")
