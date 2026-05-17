#!/usr/bin/env python3
"""
Scalping Round 5 — M1/M5 超短线回归深度挖掘
品种: XAUUSD, XAGUSD, JP225, US500, US30
时间框架: M1, M5
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

def fetch_mt5(timeframes=['M1', 'M5'], lookback=5000):
    """Fetch MT5 data for M1 + M5 across all symbols."""
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
tf_map = {{'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5}}
timeframes = {timeframes}
lookback = {lookback}

result = {{}}
for tf_name in timeframes:
    tf = tf_map.get(tf_name)
    if tf is None: continue
    result[tf_name] = {{}}
    for sym in symbols:
        rates = mt5.copy_rates_from_pos(sym, tf, 0, lookback)
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
    win_path_wsl = os.path.join(TMP_DIR, "mt5_round5_fetch.py")
    with open(win_path_wsl, "w", encoding='utf-8') as f:
        f.write(code)
    
    r = subprocess.run(
        [WINDOWS_PYTHON, os.path.join("C:/Users/gj/tmp", "mt5_round5_fetch.py")],
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
    avg_gain = gains / period if gains > 0 else 0
    avg_loss = losses / period if losses > 0 else 0
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
    sma = compute_sma(series, period)
    upper = [None] * len(series)
    lower = [None] * len(series)
    for i in range(period - 1, len(series)):
        subset = series[i - period + 1:i + 1]
        std = (sum((x - sma[i]) ** 2 for x in subset) / period) ** 0.5
        upper[i] = sma[i] + std_dev * std
        lower[i] = sma[i] - std_dev * std
    return upper, sma, lower


def compute_volume_ma(volumes, period=20):
    return compute_sma(volumes, period)


# ─── 回测引擎 ──────────────────────────────────────────────────

def backtest_entry(closes, entry_condition, hold_bars=5, direction='long'):
    signals = []
    for i in range(len(closes)):
        if entry_condition(i):
            signals.append(i)
    
    if not signals:
        return {"signals": 0, "wins": 0, "win_rate": 0, "ci_lower": 0,
                "avg_return": 0, "returns": []}
    
    wins = 0
    returns = []
    for entry_idx in signals:
        exit_idx = entry_idx + hold_bars
        if exit_idx >= len(closes):
            continue
        if direction == 'long':
            ret = (closes[exit_idx] - closes[entry_idx]) / closes[entry_idx] * 100
        else:
            ret = (closes[entry_idx] - closes[exit_idx]) / closes[entry_idx] * 100
        returns.append(ret)
        if ret > 0:
            wins += 1
    
    if not returns:
        return {"signals": len(signals), "wins": 0, "win_rate": 0, "ci_lower": 0,
                "avg_return": 0, "returns": []}
    
    n = len(returns)
    win_rate = wins / n * 100
    avg_return = sum(returns) / n
    
    p = wins / n
    se = math.sqrt(p * (1-p) / n) if n > 1 else 0
    ci_lower = max(0, (p - 1.96 * se)) * 100
    
    sorted_ret = sorted(returns)
    median_ret = sorted_ret[n // 2] if n > 0 else 0
    
    gross_profit = sum(r for r in returns if r > 0)
    gross_loss = abs(sum(r for r in returns if r < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    return {
        "signals": n,
        "wins": wins,
        "win_rate": round(win_rate, 2),
        "ci_lower": round(ci_lower, 2),
        "avg_return": round(avg_return, 4),
        "median_return": round(median_ret, 4),
        "profit_factor": round(pf, 2),
        "returns": returns,
    }


# ─── M1 scalping 测试 ──────────────────────────────────────────

def test_m1_scalp(m1_data):
    """Test M1 scalping hypotheses."""
    results = {}
    
    for sym in SYMBOLS:
        klines = m1_data.get(sym, [])
        if not klines or len(klines) < 200:
            continue
        
        opens = [k['open'] for k in klines]
        highs = [k['high'] for k in klines]
        lows = [k['low'] for k in klines]
        closes = [k['close'] for k in klines]
        volumes = [k['volume'] for k in klines]
        
        rsi = compute_rsi(closes, 14)
        
        sym_res = {}
        
        # ─── Test B1: M1 RSI<30+收阳 → hold 5 M1 (re-validate scalp_find_006) ───
        def make_cond_rsi30(sym_closes=sym):
            rsi_local = rsi
            opens_local = opens
            closes_local = closes
            def cond(i):
                if rsi_local[i] is None or rsi_local[i] >= 30:
                    return False
                # 收阳: close > open
                if closes_local[i] <= opens_local[i]:
                    return False
                return True
            return cond
        
        for hold in [3, 5, 8]:
            bt = backtest_entry(closes, make_cond_rsi30(), hold_bars=hold)
            sym_res[f"B1_RSI30_Bull_hold{hold}"] = bt
        
        # ─── Test B2: XAGUSD M1 RSI<30 → hold 5 M1 (scalp_008) ───
        # Only for XAGUSD
        if sym == 'XAGUSD':
            bt = backtest_entry(closes, make_cond_rsi30(), hold_bars=5)
            sym_res[f"B2_XAGUSD_RSI30_hold5"] = bt
            for hold in [3, 8]:
                bt = backtest_entry(closes, make_cond_rsi30(), hold_bars=hold)
                sym_res[f"B2_XAGUSD_RSI30_hold{hold}"] = bt
        
        # ─── Test B3: M1 RSI<25+收阳 → US30 specific ───
        def make_cond_rsi25():
            rsi_local = rsi
            opens_local = opens
            closes_local = closes
            def cond(i):
                if rsi_local[i] is None or rsi_local[i] >= 25:
                    return False
                if closes_local[i] <= opens_local[i]:
                    return False
                return True
            return cond
        
        for hold in [3, 5]:
            bt = backtest_entry(closes, make_cond_rsi25(), hold_bars=hold)
            sym_res[f"B3_RSI25_Bull_hold{hold}"] = bt
        
        # ─── Test B4: M1 连续3阴线 → 反弹做多 ───
        def make_cond_3red():
            closes_local = closes
            opens_local = opens
            def cond(i):
                if i < 3:
                    return False
                # 3 consecutive red candles
                for j in range(i-2, i+1):
                    if closes_local[j] >= opens_local[j]:
                        return False
                return True
            return cond
        
        for hold in [3, 5]:
            bt = backtest_entry(closes, make_cond_3red(), hold_bars=hold)
            sym_res[f"B4_3Red_hold{hold}"] = bt
        
        # ─── Test B5: M1 RSI<30 + Vol surge (>2x MA20) ───
        vol_ma20 = compute_volume_ma(volumes, 20)
        def make_cond_rsi30_vol():
            rsi_local = rsi
            opens_local = opens
            closes_local = closes
            volumes_local = volumes
            vol_ma = vol_ma20
            def cond(i):
                if rsi_local[i] is None or rsi_local[i] >= 30:
                    return False
                if closes_local[i] <= opens_local[i]:
                    return False
                if vol_ma[i] is None or vol_ma[i] <= 0:
                    return False
                if volumes_local[i] / vol_ma[i] < 2.0:
                    return False
                return True
            return cond
        
        for hold in [3, 5]:
            bt = backtest_entry(closes, make_cond_rsi30_vol(), hold_bars=hold)
            sym_res[f"B5_RSI30_VolSurge_hold{hold}"] = bt
        
        results[sym] = sym_res
    
    return results


# ─── M5 scalping 测试 ──────────────────────────────────────────

def test_m5_scalp(m5_data):
    """Test M5 scalping hypotheses."""
    results = {}
    
    for sym in SYMBOLS:
        klines = m5_data.get(sym, [])
        if not klines or len(klines) < 200:
            continue
        
        opens = [k['open'] for k in klines]
        highs = [k['high'] for k in klines]
        lows = [k['low'] for k in klines]
        closes = [k['close'] for k in klines]
        volumes = [k['volume'] for k in klines]
        
        rsi = compute_rsi(closes, 14)
        bb_upper, bb_mid, bb_lower = compute_bollinger(closes, 20, 2)
        vol_ma20 = compute_volume_ma(volumes, 20)
        
        sym_res = {}
        
        # ─── Test C1: M5 BB下轨+收阳 → hold 5 M5 (re-validate scalp_find_002) ───
        def make_cond_bb_lower():
            bb_l = bb_lower
            opens_local = opens
            closes_local = closes
            def cond(i):
                if bb_l[i] is None:
                    return False
                # touch lower BB: low <= BB lower, or close <= BB lower + 0.1%
                if closes_local[i] > bb_l[i] * 1.001:
                    return False
                # bullish candle
                if closes_local[i] <= opens_local[i]:
                    return False
                return True
            return cond
        
        for hold in [3, 5, 8]:
            bt = backtest_entry(closes, make_cond_bb_lower(), hold_bars=hold)
            sym_res[f"C1_BBlower_Bull_hold{hold}"] = bt
        
        # ─── Test C2: M5 BB下轨+RSI<40+收阳 → hold 5 M5 (scalp_010) ───
        def make_cond_bb_lower_rsi40():
            bb_l = bb_lower
            opens_local = opens
            closes_local = closes
            rsi_local = rsi
            def cond(i):
                if bb_l[i] is None or rsi_local[i] is None:
                    return False
                if closes_local[i] > bb_l[i] * 1.001:
                    return False
                if closes_local[i] <= opens_local[i]:
                    return False
                if rsi_local[i] >= 40:
                    return False
                return True
            return cond
        
        for hold in [3, 5, 8]:
            bt = backtest_entry(closes, make_cond_bb_lower_rsi40(), hold_bars=hold)
            sym_res[f"C2_BBlower_RSI40_Bull_hold{hold}"] = bt
        
        # ─── Test C3: M5 放量反转(vol>2xMA + 前阴后阳) → hold 1 M5 (re-validate) ───
        def make_cond_vol_reversal():
            opens_local = opens
            closes_local = closes
            volumes_local = volumes
            vol_ma = vol_ma20
            def cond(i):
                if i < 1:
                    return False
                if vol_ma[i] is None or vol_ma[i] <= 0:
                    return False
                if volumes_local[i] / vol_ma[i] < 2.0:
                    return False
                # prev bearish, current bullish
                if closes_local[i-1] >= opens_local[i-1]:
                    return False
                if closes_local[i] <= opens_local[i]:
                    return False
                return True
            return cond
        
        for hold in [1, 3, 5]:
            bt = backtest_entry(closes, make_cond_vol_reversal(), hold_bars=hold)
            sym_res[f"C3_VolReversal_hold{hold}"] = bt
        
        # ─── Test C4: M5 RSI<30+收阳 → hold 5 M5 ───
        def make_cond_m5_rsi30():
            rsi_local = rsi
            opens_local = opens
            closes_local = closes
            def cond(i):
                if rsi_local[i] is None or rsi_local[i] >= 30:
                    return False
                if closes_local[i] <= opens_local[i]:
                    return False
                return True
            return cond
        
        for hold in [5]:
            bt = backtest_entry(closes, make_cond_m5_rsi30(), hold_bars=hold)
            sym_res[f"C4_M5_RSI30_Bull_hold{hold}"] = bt
        
        # ─── Test C5: M5 BB下轨+RSI<30+收阳 → hold 5 M5 (stricter combo) ───
        def make_cond_bb_lower_rsi30():
            bb_l = bb_lower
            opens_local = opens
            closes_local = closes
            rsi_local = rsi
            def cond(i):
                if bb_l[i] is None or rsi_local[i] is None:
                    return False
                if closes_local[i] > bb_l[i] * 1.001:
                    return False
                if closes_local[i] <= opens_local[i]:
                    return False
                if rsi_local[i] >= 30:
                    return False
                return True
            return cond
        
        for hold in [5]:
            bt = backtest_entry(closes, make_cond_bb_lower_rsi30(), hold_bars=hold)
            sym_res[f"C5_BBlower_RSI30_Bull_hold{hold}"] = bt
        
        results[sym] = sym_res
    
    return results


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
            "profit_factor": round(pf, 2),
            "is_significant": ci_lower > 50,
        }
    
    return summary


# ─── 报告生成 ──────────────────────────────────────────────────

def generate_report(m1_results, m5_results, m1_summary, m5_summary, best_findings):
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    report = f"""# 📊 Scalping Round 5 — M1/M5 超短线回归深度挖掘

> **生成时间**: {timestamp} BJT
> **研究轮次**: Round 5
> **品种**: XAUUSD, XAGUSD, JP225, US500, US30（5个）
> **时间框架**: M1 + M5
> **数据量**: 每品种 5000 根 M1 K线 + 5000 根 M5 K线

---

## 一、执行概览

### 本轮测试假设

**M1 scalping（B系列）:**
- **B1**: M1 RSI<30+收阳 → hold 3/5/8 M1（重新验证 scalp_find_006）
- **B2**: XAGUSD M1 RSI<30 → hold 3/5/8 M1（scalp_008，品种特异）
- **B3**: M1 RSI<25+收阳 → hold 3/5 M1（US30最佳参数验证）
- **B4**: M1 连续3阴线 → hold 3/5 M1（反弹做多）
- **B5**: M1 RSI<30+成交量突增(>2xMA) → hold 3/5 M1（组合过滤）

**M5 scalping（C系列）:**
- **C1**: M5 BB下轨+收阳 → hold 3/5/8 M5（重新验证 scalp_find_002）
- **C2**: M5 BB下轨+RSI<40+收阳 → hold 3/5/8 M5（scalp_010，组合过滤）
- **C3**: M5 放量反转(vol>2xMA+前阴后阳) → hold 1/3/5 M5（重新验证 scalp_find_003）
- **C4**: M5 RSI<30+收阳 → hold 5 M5（M5级别RSI超卖）
- **C5**: M5 BB下轨+RSI<30+收阳 → hold 5 M5（严格组合过滤）

---

## 二、M1 时间框架 — 核心发现

"""
    
    # M1 significant findings
    sig_m1 = {k: v for k, v in m1_summary.items() if v.get("is_significant") and v.get("total_signals", 0) >= 10}
    sorted_m1 = sorted(sig_m1.items(), key=lambda x: x[1]["ci_lower"], reverse=True)
    
    if sorted_m1:
        report += "### 🔥 统计显著模式 (CI下限 > 50%)\n\n"
        report += "| 测试变体 | 胜率 | CI下限 | 信号数 | 平均收益 | 中位收益 | 盈亏比 |\n"
        report += "|:--------:|:----:|:------:|:-----:|:--------:|:--------:|:-----:|\n"
        for vname, vdata in sorted_m1:
            report += f"| {vname} | {vdata['win_rate']}% | {vdata['ci_lower']}% | {vdata['total_signals']} | {vdata['avg_return']:+.4f}% | {vdata['median_return']:+.4f}% | {vdata['profit_factor']} |\n"
        report += "\n"
    else:
        report += "### ⚠️ M1 未发现统计显著模式\n\n"
    
    # M1 full ranking
    all_m1 = {k: v for k, v in m1_summary.items() if v.get("total_signals", 0) >= 5}
    sorted_all_m1 = sorted(all_m1.items(), key=lambda x: x[1]["win_rate"], reverse=True)
    
    report += "### M1 全测试排名（按胜率，信号数≥5）\n\n"
    report += "| 测试变体 | 胜率 | CI下限 | 信号数 | 平均收益 | 显著? |\n"
    report += "|:--------:|:----:|:------:|:-----:|:--------:|:----:|\n"
    for vname, vdata in sorted_all_m1:
        sig = "✅" if vdata.get("is_significant") and vdata.get("ci_lower", 0) > 50 else "⚠️"
        report += f"| {vname} | {vdata['win_rate']}% | {vdata['ci_lower']}% | {vdata['total_signals']} | {vdata['avg_return']:+.4f}% | {sig} |\n"
    report += "\n"
    
    # M1 best per symbol
    report += "### M1 各品种最佳测试\n\n"
    report += "| 品种 | 最佳测试 | 胜率 | CI下限 | 信号数 | 平均收益 |\n"
    report += "|:---:|:--------:|:----:|:------:|:-----:|:--------:|\n"
    for sym in SYMBOLS:
        sr = m1_results.get(sym, {})
        best_v = None
        best_ci = 0
        best_data = None
        for vname, vdata in sr.items():
            if vdata and vdata.get("signals", 0) >= 5:
                ci = vdata.get("ci_lower", 0)
                if ci > best_ci:
                    best_ci = ci
                    best_v = vname
                    best_data = vdata
        if best_v:
            report += f"| {sym} | {best_v} | {best_data.get('win_rate', 0)}% | {best_ci}% | {best_data.get('signals', 0)} | {best_data.get('avg_return', 0):+.4f}% |\n"
        else:
            report += f"| {sym} | — | — | — | — | — |\n"
    report += "\n"
    
    # ─── M5 section ───
    report += "---\n\n## 三、M5 时间框架 — 核心发现\n\n"
    
    sig_m5 = {k: v for k, v in m5_summary.items() if v.get("is_significant") and v.get("total_signals", 0) >= 10}
    sorted_m5 = sorted(sig_m5.items(), key=lambda x: x[1]["ci_lower"], reverse=True)
    
    if sorted_m5:
        report += "### 🔥 统计显著模式 (CI下限 > 50%)\n\n"
        report += "| 测试变体 | 胜率 | CI下限 | 信号数 | 平均收益 | 中位收益 | 盈亏比 |\n"
        report += "|:--------:|:----:|:------:|:-----:|:--------:|:--------:|:-----:|\n"
        for vname, vdata in sorted_m5:
            report += f"| {vname} | {vdata['win_rate']}% | {vdata['ci_lower']}% | {vdata['total_signals']} | {vdata['avg_return']:+.4f}% | {vdata['median_return']:+.4f}% | {vdata['profit_factor']} |\n"
        report += "\n"
    else:
        report += "### ⚠️ M5 未发现统计显著模式\n\n"
    
    all_m5 = {k: v for k, v in m5_summary.items() if v.get("total_signals", 0) >= 5}
    sorted_all_m5 = sorted(all_m5.items(), key=lambda x: x[1]["win_rate"], reverse=True)
    
    report += "### M5 全测试排名（按胜率，信号数≥5）\n\n"
    report += "| 测试变体 | 胜率 | CI下限 | 信号数 | 平均收益 | 显著? |\n"
    report += "|:--------:|:----:|:------:|:-----:|:--------:|:----:|\n"
    for vname, vdata in sorted_all_m5:
        sig = "✅" if vdata.get("is_significant") and vdata.get("ci_lower", 0) > 50 else "⚠️"
        report += f"| {vname} | {vdata['win_rate']}% | {vdata['ci_lower']}% | {vdata['total_signals']} | {vdata['avg_return']:+.4f}% | {sig} |\n"
    report += "\n"
    
    report += "### M5 各品种最佳测试\n\n"
    report += "| 品种 | 最佳测试 | 胜率 | CI下限 | 信号数 | 平均收益 |\n"
    report += "|:---:|:--------:|:----:|:------:|:-----:|:--------:|\n"
    for sym in SYMBOLS:
        sr = m5_results.get(sym, {})
        best_v = None
        best_ci = 0
        best_data = None
        for vname, vdata in sr.items():
            if vdata and vdata.get("signals", 0) >= 5:
                ci = vdata.get("ci_lower", 0)
                if ci > best_ci:
                    best_ci = ci
                    best_v = vname
                    best_data = vdata
        if best_v:
            report += f"| {sym} | {best_v} | {best_data.get('win_rate', 0)}% | {best_ci}% | {best_data.get('signals', 0)} | {best_data.get('avg_return', 0):+.4f}% |\n"
        else:
            report += f"| {sym} | — | — | — | — | — |\n"
    report += "\n"
    
    # ─── 综合分析 ───
    report += "---\n\n## 四、综合分析：M1 vs M5\n\n"
    
    # Compare best M1 vs best M5
    best_m1 = max([(k, v) for k, v in all_m1.items()], key=lambda x: x[1]["win_rate"]) if all_m1 else (None, None)
    best_m5 = max([(k, v) for k, v in all_m5.items()], key=lambda x: x[1]["win_rate"]) if all_m5 else (None, None)
    
    if best_m1[1]:
        report += f"**M1 最佳**: {best_m1[0]} — WR={best_m1[1]['win_rate']}%, CI={best_m1[1]['ci_lower']}%, n={best_m1[1]['total_signals']}, avg={best_m1[1]['avg_return']:+.4f}%\n\n"
    if best_m5[1]:
        report += f"**M5 最佳**: {best_m5[0]} — WR={best_m5[1]['win_rate']}%, CI={best_m5[1]['ci_lower']}%, n={best_m5[1]['total_signals']}, avg={best_m5[1]['avg_return']:+.4f}%\n\n"
    
    # Round 4 comparison
    report += "### 与 Round 4 最佳发现的对比\n\n"
    report += "| 来源 | 策略 | 类型 | 胜率 | CI下限 | 信号数 | 平均收益 |\n"
    report += "|:---:|:----:|:---:|:----:|:------:|:-----:|:--------:|\n"
    report += "| R4 | XAGUSD H1 Doji hold3 | H1 | 58.63% | 54.43% | 527 | +0.1421% |\n"
    report += "| R4 | Harami+VolSurge hold3 | H1 | 60.13% | 52.49% | 158 | +0.1083% |\n"
    report += "| R4 | PiercingLine+M30up hold5 | H1 | 56.16% | 50.31% | 276 | +0.1157% |\n"
    report += "| R2 | M1 RSI<30+收阳 hold5 (US30) | M1 | 68.85% | — | 61 | — |\n"
    report += "| R2 | M5 BB下轨+收阳 hold5 | M5 | 54.17% | 51.30% | 1163 | +0.0176% |\n"
    if best_m1[1]:
        report += f"| R5 | {best_m1[0]} | M1 | {best_m1[1]['win_rate']}% | {best_m1[1]['ci_lower']}% | {best_m1[1]['total_signals']} | {best_m1[1]['avg_return']:+.4f}% |\n"
    if best_m5[1]:
        report += f"| R5 | {best_m5[0]} | M5 | {best_m5[1]['win_rate']}% | {best_m5[1]['ci_lower']}% | {best_m5[1]['total_signals']} | {best_m5[1]['avg_return']:+.4f}% |\n"
    report += "\n"
    
    # ─── 结论 ───
    report += "---\n\n## 五、结论与下一步\n\n"
    
    m1_sig_count = len(sorted_m1)
    m5_sig_count = len(sorted_m5)
    total_sig = m1_sig_count + m5_sig_count
    
    if total_sig > 0:
        report += f"### ✅ 发现 {total_sig} 个统计显著模式（M1: {m1_sig_count}, M5: {m5_sig_count}）\n\n"
        for vname, vdata in sorted_m1 + sorted_m5:
            report += f"- **{vname}**: WR={vdata['win_rate']}%, CI={vdata['ci_lower']}%, n={vdata['total_signals']}, avg={vdata['avg_return']:+.4f}%\n"
    else:
        report += "### ❌ 本轮 M1/M5 未发现统计显著模式\n\n"
        report += "可能原因：\n"
        report += "1. 超短线(5000根)数据量不足以在M1/M5达到统计显著\n"
        report += "2. M1/M5级别噪声大，简单技术指标难以产生稳定edge\n"
        report += "3. 组合过滤条件过于严格，信号量不足\n\n"
    
    report += "### Round 6 建议\n\n"
    report += "1. **M1/M5 品种特异策略深化** — XAGUSD/US30 最佳策略深度验证\n"
    report += "2. **止损/止盈嵌入** — 加入 ATR 动态止损后的风险收益比\n"
    report += "3. **多时间框架验证** — M1入场 + M5趋势确认的组合\n"
    report += "4. **模式退化检测** — 比较今日结果与 Round 1/2 结果是否一致\n"
    report += "5. **非对称杠杆策略** — 基于盈亏比的仓位分配\n\n"
    
    report += "---\n\n*Round 5 完成 — M1/M5 超短线回归深度挖掘*\n"
    
    return report


# ─── 主函数 ──────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("📊 Scalping Round 5 — M1/M5 超短线回归深度挖掘")
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Step 1: Fetch data
    print("\n[1/4] 获取 M1 + M5 数据...")
    data = fetch_mt5(timeframes=['M1', 'M5'], lookback=5000)
    
    if "error" in data:
        print(f"ERROR: {data['error']}")
        sys.exit(1)
    
    m1_total = sum(len(v) for v in data.get('M1', {}).values())
    m5_total = sum(len(v) for v in data.get('M5', {}).values())
    print(f"  ✅ M1: {m1_total} K线, M5: {m5_total} K线")
    
    # Step 2: Run M1 analysis
    print("\n[2/4] 执行 M1 scalping 测试...")
    m1_results = test_m1_scalp(data.get('M1', {}))
    
    # Step 3: Run M5 analysis
    print("\n[3/4] 执行 M5 scalping 测试...")
    m5_results = test_m5_scalp(data.get('M5', {}))
    
    # Compute summaries
    m1_summary = cross_summary(m1_results)
    m5_summary = cross_summary(m5_results)
    
    # Compile best findings
    best_findings = []
    for vname, vdata in sorted(m1_summary.items(), key=lambda x: x[1]["ci_lower"], reverse=True):
        if vdata.get("is_significant") and vdata.get("total_signals", 0) >= 10:
            best_findings.append({
                "variant": vname,
                "timeframe": "M1",
                "win_rate": vdata["win_rate"],
                "ci_lower": vdata["ci_lower"],
                "signal_count": vdata["total_signals"],
                "avg_return": vdata["avg_return"],
                "profit_factor": vdata["profit_factor"],
            })
    for vname, vdata in sorted(m5_summary.items(), key=lambda x: x[1]["ci_lower"], reverse=True):
        if vdata.get("is_significant") and vdata.get("total_signals", 0) >= 10:
            best_findings.append({
                "variant": vname,
                "timeframe": "M5",
                "win_rate": vdata["win_rate"],
                "ci_lower": vdata["ci_lower"],
                "signal_count": vdata["total_signals"],
                "avg_return": vdata["avg_return"],
                "profit_factor": vdata["profit_factor"],
            })
    
    # Step 4: Generate reports
    print("\n[4/4] 生成报告...")
    report_md = generate_report(m1_results, m5_results, m1_summary, m5_summary, best_findings)
    
    # Save reports
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reports_dir = os.path.join(base_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    report_path = os.path.join(reports_dir, "round_005.md")
    with open(report_path, "w", encoding='utf-8') as f:
        f.write(report_md)
    print(f"  ✅ 报告保存: {report_path}")
    
    json_path = os.path.join(reports_dir, "round_005.json")
    json_output = {
        "round": 5,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "hypotheses_tested": ["scalp_007", "scalp_008", "scalp_009", "scalp_010"],
        "m1_summary": m1_summary,
        "m5_summary": m5_summary,
        "best_findings": best_findings,
    }
    with open(json_path, "w", encoding='utf-8') as f:
        json.dump(json_output, f, ensure_ascii=False, indent=2)
    print(f"  ✅ JSON摘要保存: {json_path}")
    
    # Print summary
    print(f"\n{'=' * 70}")
    print("📊 ROUND 5 — 结果摘要")
    print(f"{'=' * 70}")
    
    print(f"\nM1 显著模式: {len([v for v in m1_summary.values() if v.get('is_significant')])}个")
    for vname, vdata in sorted(m1_summary.items(), key=lambda x: x[1].get("ci_lower", 0), reverse=True)[:5]:
        sig = "✅" if vdata.get("is_significant") else "⚠️"
        print(f"  {sig} {vname}: WR={vdata['win_rate']}% CI={vdata['ci_lower']}% n={vdata['total_signals']}")
    
    print(f"\nM5 显著模式: {len([v for v in m5_summary.values() if v.get('is_significant')])}个")
    for vname, vdata in sorted(m5_summary.items(), key=lambda x: x[1].get("ci_lower", 0), reverse=True)[:5]:
        sig = "✅" if vdata.get("is_significant") else "⚠️"
        print(f"  {sig} {vname}: WR={vdata['win_rate']}% CI={vdata['ci_lower']}% n={vdata['total_signals']}")
    
    print(f"\n{'=' * 70}")
    print("完成 ✅")
    print(f"{'=' * 70}")
