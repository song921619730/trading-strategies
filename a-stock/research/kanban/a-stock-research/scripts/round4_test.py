#!/usr/bin/env python3
"""
Scalping Round 4 — H1 PiercingLine + M30上升趋势 → 做多
Cross-timeframe confirmation test for pattern_004
品种: XAUUSD, XAGUSD, JP225, US500, US30
时间框架: H1 (entry), M30 (trend filter)
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

def fetch_mt5(timeframes=['H1', 'M30'], lookback=5000):
    """Fetch MT5 data for H1 + M30 across all symbols."""
    code = f'''import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import json
import numpy as np
from datetime import datetime as _dt

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
tf_map = {{'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15,
           'M30': mt5.TIMEFRAME_M30, 'H1': mt5.TIMEFRAME_H1}}
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
    win_path_wsl = os.path.join(TMP_DIR, "mt5_round4_fetch.py")
    with open(win_path_wsl, "w", encoding='utf-8') as f:
        f.write(code)
    
    r = subprocess.run(
        [WINDOWS_PYTHON, os.path.join("C:/Users/gj/tmp", "mt5_round4_fetch.py")],
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


# ─── 形态检测 ──────────────────────────────────────────────────

def detect_piercing_line(opens, highs, lows, closes):
    """Piercing Line (bullish): red candle, then green that opens lower but closes > 50% of prev body"""
    result = [False] * len(opens)
    for i in range(1, len(opens)):
        prev_body = closes[i-1] - opens[i-1]
        curr_body = closes[i] - opens[i]
        prev_abs = abs(prev_body)
        if prev_abs == 0:
            continue
        if prev_body < 0 and curr_body > 0:
            midpoint = opens[i-1] + prev_abs / 2
            if opens[i] < closes[i-1] and closes[i] > midpoint:
                result[i] = True
    return result


def detect_engulfing(opens, highs, lows, closes):
    """Bullish Engulfing"""
    bullish = [False] * len(opens)
    for i in range(1, len(opens)):
        prev_body = closes[i-1] - opens[i-1]
        curr_body = closes[i] - opens[i]
        prev_abs = abs(prev_body)
        curr_abs = abs(curr_body)
        if prev_abs == 0 or curr_abs == 0:
            continue
        if prev_body < 0 and curr_body > 0 and curr_abs > prev_abs:
            if opens[i] < closes[i-1] and closes[i] > opens[i-1]:
                bullish[i] = True
    return bullish


def detect_harami(opens, highs, lows, closes):
    """Bullish Harami"""
    bullish = [False] * len(opens)
    for i in range(1, len(opens)):
        prev_body = closes[i-1] - opens[i-1]
        curr_body = closes[i] - opens[i]
        prev_abs = abs(prev_body)
        curr_abs = abs(curr_body)
        if prev_abs == 0 or curr_abs == 0:
            continue
        prev_top = max(opens[i-1], closes[i-1])
        prev_bot = min(opens[i-1], closes[i-1])
        curr_top = max(opens[i], closes[i])
        curr_bot = min(opens[i], closes[i])
        if curr_top < prev_top and curr_bot > prev_bot and curr_abs < prev_abs:
            if prev_body < 0:
                bullish[i] = True
    return bullish


def detect_three_soldiers(opens, highs, lows, closes):
    """Three White Soldiers"""
    soldiers = [False] * len(opens)
    for i in range(2, len(opens)):
        if (closes[i] > opens[i] and closes[i-1] > opens[i-1] and closes[i-2] > opens[i-2] and
            closes[i] > closes[i-1] > closes[i-2] and
            opens[i] > opens[i-1] > opens[i-2]):
            soldiers[i] = True
    return soldiers


def detect_doji(opens, highs, lows, closes, threshold_pct=0.1):
    result = [False] * len(opens)
    for i in range(len(opens)):
        body = abs(closes[i] - opens[i])
        range_total = highs[i] - lows[i]
        if range_total > 0 and body / range_total <= threshold_pct:
            result[i] = True
    return result


# ─── 回测引擎 ──────────────────────────────────────────────────

def backtest_entry(closes, entry_condition, hold_bars=3, direction='long'):
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


# ─── 核心分析 ──────────────────────────────────────────────────

def run_round4(data):
    """Round 4 analysis: test pattern_004 + additional combo hypotheses"""
    
    results = {
        "round": 4,
        "hypotheses_tested": [],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "symbol_results": {},
        "cross_symbol_summary": {},
        "best_findings": [],
    }
    
    h1_data = data.get('H1', {})
    m30_data = data.get('M30', {})
    
    # ─── Hypothesis A (pattern_004): H1 PiercingLine + M30 uptrend ───
    # Entry: H1 PiercingLine detected
    # Filter: M30 SMA20 uptrend (close > SMA20) at signal time
    # Hold: 3 H1 bars, 5 H1 bars
    
    print("\n[Hypothesis A] H1 PiercingLine + M30上升趋势 → 做多")
    hypothesis_a = {
        "id": "pattern_004",
        "hypothesis": "H1 PiercingLine + M30上升趋势(M30 close>SMA20) → 做多",
        "direction": "long",
        "variants": {},
    }
    
    for sym in SYMBOLS:
        h1_klines = h1_data.get(sym, [])
        m30_klines = m30_data.get(sym, [])
        if not h1_klines or not m30_klines or len(h1_klines) < 100 or len(m30_klines) < 100:
            continue
        
        h1_closes = [k['close'] for k in h1_klines]
        h1_opens = [k['open'] for k in h1_klines]
        h1_highs = [k['high'] for k in h1_klines]
        h1_lows = [k['low'] for k in h1_klines]
        h1_ts = [k['ts'] for k in h1_klines]
        
        m30_closes = [k['close'] for k in m30_klines]
        m30_ts = [k['ts'] for k in m30_klines]
        m30_sma20 = compute_sma(m30_closes, 20)
        
        # Detect patterns on H1
        piercing = detect_piercing_line(h1_opens, h1_highs, h1_lows, h1_closes)
        engulf_bull = detect_engulfing(h1_opens, h1_highs, h1_lows, h1_closes)
        harami_bull = detect_harami(h1_opens, h1_highs, h1_lows, h1_closes)
        soldiers = detect_three_soldiers(h1_opens, h1_highs, h1_lows, h1_closes)
        doji = detect_doji(h1_opens, h1_highs, h1_lows, h1_closes)
        
        rsi = compute_rsi(h1_closes, 14)
        
        for test_name, (pattern_signal, base_direction, hold_list) in {
            "A1_PiercingLine_M30up_hold3": (piercing, 'long', [3]),
            "A2_PiercingLine_M30up_hold5": (piercing, 'long', [5]),
            "A3_PiercingLine_alone_hold3": (piercing, 'long', [3]),
            "A4_PiercingLine_alone_hold5": (piercing, 'long', [5]),
            "A5_Engulfing_M30up_hold3": (engulf_bull, 'long', [3]),
            "A6_Engulfing_M30up_hold5": (engulf_bull, 'long', [5]),
            "A7_Engulfing_RSI40_hold3": (engulf_bull, 'long', [3]),
            "A8_Harami_volSurge_hold3": (harami_bull, 'long', [3]),
            "A9_XAGUSD_Doji_hold3": (doji, 'long', [3]),
            "A10_XAUUSD_Soldiers_hold5": (soldiers, 'long', [5]),
        }.items():
            # Build entry condition with filters
            def make_cond(pat=pattern_signal, use_m30=False, use_rsi=False, 
                          rsi_thr=40, sym_name=sym, ts_list=h1_ts,
                          m30_ts_list=m30_ts, m30_close_list=m30_closes,
                          m30_sma=m30_sma20, rsi_list=rsi):
                def entry(i):
                    if not pat[i]:
                        return False
                    if use_m30:
                        # Find corresponding M30 bar
                        h1_ts_val = ts_list[i]
                        m30_idx = -1
                        for j in range(len(m30_ts_list)):
                            if m30_ts_list[j] <= h1_ts_val:
                                m30_idx = j
                            else:
                                break
                        if m30_idx < 20 or m30_sma[m30_idx] is None:
                            return False
                        # M30 uptrend: close > SMA20
                        if m30_close_list[m30_idx] <= m30_sma[m30_idx]:
                            return False
                    if use_rsi:
                        if rsi_list[i] is None or rsi_list[i] >= rsi_thr:
                            return False
                    return True
                return entry
            
            # Determine filters
            use_m30 = 'M30up' in test_name
            use_rsi = 'RSI' in test_name
            hold = hold_list[0]
            
            # Special: A8_Harami_volSurge — check volume surge
            if test_name == 'A8_Harami_volSurge_hold3':
                def make_vol_cond(pat=pattern_signal, sym_name=sym, ts_list=h1_ts,
                                  m30_ts_list=m30_ts, m30_close_list=m30_closes,
                                  m30_sma=m30_sma20, h1_klines=h1_klines):
                    # compute volume MA for H1
                    h1_volumes = [k.get('volume', 0) for k in h1_klines]
                    h1_vol_ma20 = compute_sma(h1_volumes, 20)
                    def entry(i):
                        if not pat[i]:
                            return False
                        # Volume surge > 2x MA
                        if h1_vol_ma20[i] is not None and h1_vol_ma20[i] > 0:
                            if h1_volumes[i] / h1_vol_ma20[i] > 2.0:
                                return True
                        return False
                    return entry
                cond = make_vol_cond()
            elif test_name == 'A9_XAGUSD_Doji_hold3':
                # Only for XAGUSD
                if sym != 'XAGUSD':
                    continue
                cond = make_cond(use_m30=False)
            elif test_name == 'A10_XAUUSD_Soldiers_hold5':
                # Only for XAUUSD
                if sym != 'XAUUSD':
                    continue
                cond = make_cond(use_m30=False)
            else:
                cond = make_cond(use_m30=use_m30, use_rsi=use_rsi)
            
            bt = backtest_entry(h1_closes, cond, hold_bars=hold, direction=base_direction)
            
            if test_name not in hypothesis_a["variants"]:
                hypothesis_a["variants"][test_name] = {}
            hypothesis_a["variants"][test_name][sym] = bt
            
            if sym not in results["symbol_results"]:
                results["symbol_results"][sym] = {}
            if test_name not in results["symbol_results"][sym]:
                results["symbol_results"][sym][test_name] = {}
            results["symbol_results"][sym][test_name] = bt
    
    results["hypotheses_tested"].append(hypothesis_a)
    
    # ─── 跨品种汇总 ──────────────────────────────────────────────
    print("\n[Summary] Computing cross-symbol aggregations...")
    
    all_variants = set()
    for sym in SYMBOLS:
        sr = results.get("symbol_results", {}).get(sym, {})
        for vname in sr:
            all_variants.add(vname)
    
    for vname in sorted(all_variants):
        all_rets = []
        for sym in SYMBOLS:
            sr = results.get("symbol_results", {}).get(sym, {})
            bt = sr.get(vname, {})
            if bt and "returns" in bt and bt["returns"]:
                all_rets.extend(bt["returns"])
        
        if all_rets:
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
            
            results["cross_symbol_summary"][vname] = {
                "total_signals": n,
                "total_wins": wins,
                "win_rate": round(wr, 2),
                "ci_lower": round(ci_lower, 2),
                "avg_return": round(avg_ret, 4),
                "median_return": round(median_ret, 4),
                "profit_factor": round(pf, 2),
                "is_significant": ci_lower > 50,
            }
    
    # ─── 最佳发现 ──────────────────────────────────────────────
    for vname, vdata in sorted(results["cross_symbol_summary"].items(), 
                                key=lambda x: x[1]["ci_lower"], reverse=True):
        if vdata.get("is_significant") and vdata.get("total_signals", 0) >= 10:
            results["best_findings"].append({
                "variant": vname,
                "hypothesis": vname,
                "win_rate": vdata["win_rate"],
                "ci_lower": vdata["ci_lower"],
                "signal_count": vdata["total_signals"],
                "avg_return": vdata["avg_return"],
                "profit_factor": vdata["profit_factor"],
            })
    
    return results


# ─── 报告生成 ──────────────────────────────────────────────────

def generate_report(results):
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    report = f"""# 📊 Scalping Round 4 — H1 形态 + 过滤条件验证

> **生成时间**: {timestamp} BJT
> **研究轮次**: Round 4
> **品种**: XAUUSD, XAGUSD, JP225, US500, US30（5个）
> **时间框架**: H1（入场）+ M30（趋势过滤）
> **数据量**: 每品种 5000 根 H1 K线 + 5000 根 M30 K线

---

## 一、执行概览

测试假设集（继承自 Round 3 待验证队列）：
- **pattern_004**: H1 PiercingLine + M30上升趋势 → 做多（高优先级 ✅）
- **pattern_007**: H1 BullishEngulfing + RSI<40 → 做多（中优先级）
- **pattern_006**: H1 BullishHarami + 成交量放大 → 3根H1做多（中优先级）
- **pattern_008**: XAGUSD H1 Doji → 持有3根H1做多（品种特异）
- **pattern_009**: XAUUSD H1 ThreeWhiteSoldiers → 持有5根H1做多（品种特异）

同时测试了基础变体（无过滤 vs 有过滤）用于对比分析。

---

## 二、核心发现

"""
    
    # 显著发现
    cs = results.get("cross_symbol_summary", {})
    significant = {k: v for k, v in cs.items() if v.get("is_significant") and v.get("total_signals", 0) >= 10}
    sorted_sig = sorted(significant.items(), key=lambda x: x[1]["ci_lower"], reverse=True)
    
    if sorted_sig:
        report += "### 🔥 统计显著模式 (CI下限 > 50%)\n\n"
        report += "| 测试变体 | 胜率 | CI下限 | 信号数 | 平均收益 | 中位收益 | 盈亏比 |\n"
        report += "|:--------:|:----:|:------:|:-----:|:--------:|:--------:|:-----:|\n"
        for vname, vdata in sorted_sig:
            report += f"| {vname} | {vdata['win_rate']}% | {vdata['ci_lower']}% | {vdata['total_signals']} | {vdata['avg_return']:+.4f}% | {vdata['median_return']:+.4f}% | {vdata['profit_factor']} |\n"
        report += "\n"
    else:
        report += "### ⚠️ 未发现统计显著模式\n\n"
    
    # 全排名
    all_tests = {k: v for k, v in cs.items() if v.get("total_signals", 0) >= 5}
    sorted_all = sorted(all_tests.items(), key=lambda x: x[1]["win_rate"], reverse=True)
    
    report += "### 全测试排名（按胜率，信号数≥5）\n\n"
    report += "| 测试变体 | 胜率 | CI下限 | 信号数 | 平均收益 | 显著? |\n"
    report += "|:--------:|:----:|:------:|:-----:|:--------:|:----:|\n"
    for vname, vdata in sorted_all:
        sig = "✅" if vdata.get("is_significant") and vdata.get("ci_lower", 0) > 50 else "⚠️"
        report += f"| {vname} | {vdata['win_rate']}% | {vdata['ci_lower']}% | {vdata['total_signals']} | {vdata['avg_return']:+.4f}% | {sig} |\n"
    report += "\n"
    
    # 品种特异性分析
    report += "### 各品种最佳测试\n\n"
    report += "| 品种 | 最佳测试 | 胜率 | CI下限 | 信号数 | 平均收益 |\n"
    report += "|:---:|:--------:|:----:|:------:|:-----:|:--------:|\n"
    for sym in SYMBOLS:
        sr = results.get("symbol_results", {}).get(sym, {})
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
    
    # 对比分析
    report += "### 关键对比：过滤条件效果\n\n"
    report += "| 对比组 | 无过滤胜率 | 有过滤胜率 | 信号变化 | 结论 |\n"
    report += "|:-----:|:----------:|:----------:|:--------:|:----:|\n"
    
    a3 = cs.get("A3_PiercingLine_alone_hold3", {})
    a1 = cs.get("A1_PiercingLine_M30up_hold3", {})
    a4 = cs.get("A4_PiercingLine_alone_hold5", {})
    a2 = cs.get("A2_PiercingLine_M30up_hold5", {})
    a7 = cs.get("A7_Engulfing_RSI40_hold3", {})
    a5 = cs.get("A5_Engulfing_M30up_hold3", {})
    
    # PiercingLine alone vs +M30 trend
    if a3 and a1:
        change = a1.get("win_rate", 0) - a3.get("win_rate", 0)
        sig_change = a1.get("total_signals", 0) - a3.get("total_signals", 0)
        report += f"| PiercingLine hold3 | {a3.get('win_rate', 'N/A')}% (n={a3.get('total_signals', 0)}) | {a1.get('win_rate', 'N/A')}% (n={a1.get('total_signals', 0)}) | {sig_change:+d} | {'✅ 过滤提升' if change > 0 else '❌ 过滤无效'} (ΔWR={change:+.2f}%) |\n"
    
    if a4 and a2:
        change = a2.get("win_rate", 0) - a4.get("win_rate", 0)
        sig_change = a2.get("total_signals", 0) - a4.get("total_signals", 0)
        report += f"| PiercingLine hold5 | {a4.get('win_rate', 'N/A')}% (n={a4.get('total_signals', 0)}) | {a2.get('win_rate', 'N/A')}% (n={a2.get('total_signals', 0)}) | {sig_change:+d} | {'✅ 过滤提升' if change > 0 else '❌ 过滤无效'} (ΔWR={change:+.2f}%) |\n"
    
    if a3 and a7:
        change = a7.get("win_rate", 0) - a3.get("win_rate", 0)
        report += f"| Engulfing+RSI<40 vs Piercing(基线) | {a3.get('win_rate', 'N/A')}% | {a7.get('win_rate', 'N/A')}% (n={a7.get('total_signals', 0)}) | — | RSI过滤{'有效' if change > 0 else '无效'} |\n"
    
    report += "\n"
    
    # 结论
    report += "---\n\n## 三、结论与下一步\n\n"
    
    sig_count = len(sorted_sig)
    if sig_count > 0:
        report += f"### ✅ 发现 {sig_count} 个统计显著模式\n\n"
        for vname, vdata in sorted_sig:
            report += f"- **{vname}**: WR={vdata['win_rate']}%, CI={vdata['ci_lower']}%, n={vdata['total_signals']}, avg={vdata['avg_return']:+.4f}%\n"
    else:
        report += "### ❌ 本轮无统计显著发现\n\n"
        report += "H1级别形态的过滤条件（M30趋势、RSI、成交量）未能显著提升胜率至统计显著水平。可能原因：\n"
        report += "1. 过滤条件过于严格 → 信号量不足\n"
        report += "2. H1形态已含趋势信息 → 再叠加趋势过滤收益递减\n"
        report += "3. 需要更大的数据量（MT5免费版仅5000根限制）\n\n"
    
    report += "### Round 5 建议\n\n"
    report += "1. **M30 Hammer+BB下轨 品种特异回测**（pattern_005）— GBPUSD/USOIL 深度验证\n"
    report += "2. **M1/M5 scalping 回归** — 重新聚焦超短线（M1 RSI<30, M5 BB下轨）\n"
    report += "3. **组合信号权重系统** — 多形态同时出现时加权评分\n"
    report += "4. **止损嵌入** — 加入 ATR 跟踪止损后的风险收益比\n\n"
    
    report += "---\n\n*Round 4 完成 — H1 形态 + 过滤条件验证*\n"
    
    return report


# ─── 主函数 ──────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("📊 Scalping Round 4 — H1 形态 + 过滤条件验证")
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Step 1: Fetch data
    print("\n[1/3] 获取 H1 + M30 数据...")
    data = fetch_mt5(timeframes=['H1', 'M30'], lookback=5000)
    
    if "error" in data:
        print(f"ERROR: {data['error']}")
        sys.exit(1)
    
    h1_total = sum(len(v) for v in data.get('H1', {}).values())
    m30_total = sum(len(v) for v in data.get('M30', {}).values())
    print(f"  ✅ H1: {h1_total} K线, M30: {m30_total} K线")
    
    # Step 2: Run analysis
    print("\n[2/3] 执行假设测试...")
    results = run_round4(data)
    
    # Step 3: Generate reports
    print("\n[3/3] 生成报告...")
    report_md = generate_report(results)
    
    # Save reports
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reports_dir = os.path.join(base_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    report_path = os.path.join(reports_dir, "round_004.md")
    with open(report_path, "w", encoding='utf-8') as f:
        f.write(report_md)
    print(f"  ✅ 报告保存: {report_path}")
    
    json_path = os.path.join(reports_dir, "round_004.json")
    # Save results without returns (too large)
    json_output = {
        "round": 4,
        "timestamp": results["timestamp"],
        "hypotheses_tested": [h["id"] for h in results["hypotheses_tested"]],
        "cross_symbol_summary": results["cross_symbol_summary"],
        "best_findings": results["best_findings"],
    }
    with open(json_path, "w", encoding='utf-8') as f:
        json.dump(json_output, f, ensure_ascii=False, indent=2)
    print(f"  ✅ JSON摘要保存: {json_path}")
    
    # Print summary
    print(f"\n{'=' * 70}")
    print("📊 ROUND 4 — 结果摘要")
    print(f"{'=' * 70}")
    
    cs = results.get("cross_symbol_summary", {})
    significant = {k: v for k, v in cs.items() if v.get("is_significant") and v.get("total_signals", 0) >= 10}
    
    if significant:
        print(f"\n🔥 统计显著模式: {len(significant)}个")
        for vname, vdata in sorted(significant.items(), key=lambda x: x[1]["ci_lower"], reverse=True):
            print(f"  ✅ {vname}: WR={vdata['win_rate']}% CI={vdata['ci_lower']}% n={vdata['total_signals']}")
    else:
        print(f"\n⚠️ 无统计显著模式")
        # Show best few
        all_tests = {k: v for k, v in cs.items() if v.get("total_signals", 0) >= 5}
        sorted_all = sorted(all_tests.items(), key=lambda x: x[1]["win_rate"], reverse=True)
        print(f"\n  最佳结果（前5）:")
        for vname, vdata in sorted_all[:5]:
            print(f"  {vname}: WR={vdata['win_rate']}% CI={vdata['ci_lower']}% n={vdata['total_signals']}")
    
    print(f"\n{'=' * 70}")
    print("完成 ✅")
    print(f"{'=' * 70}")
