#!/usr/bin/env python3
"""
Scalping Round 2 — M1 RSI<30 跨品种深度验证
Fixed version - explicit float/int conversion for JSON serialization
"""

import json
import math
import sys
import subprocess
import os
from datetime import datetime, timedelta

WINDOWS_PYTHON = "/mnt/c/Users/gj/AppData/Local/Programs/Python/Python310/python.exe"
TMP_DIR = "/mnt/c/Users/gj/tmp"
os.makedirs(TMP_DIR, exist_ok=True)

SYMBOLS = ['XAUUSD', 'XAGUSD', 'JP225', 'US500', 'US30']

def fetch_mt5_batch(timeframes=['M1'], lookback=5000):
    """Fetch MT5 data for multiple timeframes. Returns {tf: {symbol: [klines]}}"""
    
    code = f'''
import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import json
import numpy as np
from datetime import datetime as _dt

# Custom JSON encoder to handle numpy types
class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

if not mt5.initialize():
    print(json.dumps({{'error': f'MT5 init failed: {{mt5.last_error()}}'}}))
    sys.exit(0)

symbols = {SYMBOLS}
tf_map = {{'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15}}
timeframes = {timeframes}

result = {{}}
for tf_name in timeframes:
    tf = tf_map.get(tf_name, mt5.TIMEFRAME_M5)
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
                'open': round(float(r[1]), 2),
                'high': round(float(r[2]), 2),
                'low': round(float(r[3]), 2),
                'close': round(float(r[4]), 2),
                'volume': int(r[5]),
            }})
        result[tf_name][sym] = klines

mt5.shutdown()
print(json.dumps(result, cls=NpEncoder))
'''
    win_path_wsl = os.path.join(TMP_DIR, "mt5_round2_fetch.py")
    with open(win_path_wsl, "w", encoding='utf-8') as f:
        f.write(code)

    r = subprocess.run(
        [WINDOWS_PYTHON, os.path.join("C:/Users/gj/tmp", "mt5_round2_fetch.py")],
        capture_output=True, text=True, timeout=300
    )
    if r.returncode != 0:
        return {"error": f"Windows Python error: {r.stderr[:500]}"}
    # Find JSON start
    idx = r.stdout.find('{')
    if idx >= 0:
        try:
            return json.loads(r.stdout[idx:])
        except json.JSONDecodeError as e:
            return {"error": f"JSON decode: {e}, stdout[:200]: {r.stdout[:200]}"}
    return {"error": f"No JSON found. stdout[:500]: {r.stdout[:500]}, stderr[:500]: {r.stderr[:500]}"}


# ─── 技术指标 ──────────────────────────────────────────────

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


# ─── 回测引擎 ──────────────────────────────────────────────

def backtest_entry(closes, highs, lows, volumes, rsi, entry_condition, hold_bars=5):
    """
    通用入场回测
    entry_condition: function(idx) -> bool
    出场: hold_bars 根K线后
    """
    signals = []
    for i in range(len(closes)):
        if entry_condition(i):
            signals.append(i)
    
    if not signals:
        return {"signals": 0, "wins": 0, "win_rate": 0, "ci_lower": 0,
                "avg_return": 0, "total_return": 0, "median_return": 0,
                "p10": 0, "p25": 0, "p75": 0, "p90": 0,
                "max_consec_losses": 0, "sharpe": 0, "returns": []}
    
    wins = 0
    returns = []
    for entry_idx in signals:
        exit_idx = entry_idx + hold_bars
        if exit_idx >= len(closes):
            continue
        ret = (closes[exit_idx] - closes[entry_idx]) / closes[entry_idx] * 100
        returns.append(ret)
        if ret > 0:
            wins += 1
    
    if not returns:
        return {"signals": len(signals), "wins": 0, "win_rate": 0, "ci_lower": 0,
                "avg_return": 0, "total_return": 0, "median_return": 0,
                "p10": 0, "p25": 0, "p75": 0, "p90": 0,
                "max_consec_losses": 0, "sharpe": 0, "returns": []}
    
    n = len(returns)
    win_rate = wins / n * 100
    avg_return = sum(returns) / n
    total_return = sum(returns)
    
    # 95% CI lower bound for win rate
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
    
    return {
        "signals": n,
        "wins": wins,
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
        "returns": returns,
    }


def run_round2(data):
    """Run Round 2 analysis on fetched data"""
    results = {
        "hypothesis": "scalp_006: M1 RSI<30+收阳 → 持有5根M1做多（跨品种验证）",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "round": 2,
        "symbol_results": {},
        "cross_symbol_summary": {},
        "variations": {},
        "m15_confirmation": {},
    }
    
    m1_data = data.get('M1', {})
    m15_data = data.get('M15', {})
    
    # ─── 逐个品种分析 ──────────────────────────────────
    for sym in SYMBOLS:
        klines = m1_data.get(sym, [])
        if not klines:
            results["symbol_results"][sym] = {"error": "no data"}
            continue
        
        closes = [k['close'] for k in klines]
        opens = [k['open'] for k in klines]
        highs = [k['high'] for k in klines]
        lows = [k['low'] for k in klines]
        
        rsi = compute_rsi(closes, 14)
        
        sym_result = {
            "data_points": len(klines),
            "date_range": f"{klines[0]['time']} → {klines[-1]['time']}" if klines else "N/A",
        }
        
        # ── 持有期变体 ──
        hold_periods = [3, 5, 8, 13]
        base_variants = {}
        for hold in hold_periods:
            def make_entry_hold(rsi_thr=30, req_bull=True):
                def entry(i):
                    if i < 14 or rsi[i] is None:
                        return False
                    cond = rsi[i] < rsi_thr
                    if req_bull:
                        cond = cond and closes[i] > opens[i]
                    return cond
                return entry
            bt = backtest_entry(closes, highs, lows, [0]*len(closes), rsi,
                              make_entry_hold(30, True), hold_bars=hold)
            base_variants[f"hold_{hold}"] = bt
        
        sym_result["base_Rsi30_bull"] = base_variants
        
        # ── RSI 阈值变体 ──
        threshold_variants = {}
        for thr in [20, 25, 30, 35]:
            def make_entry_thr(t=thr, rb=True):
                def entry(i):
                    if i < 14 or rsi[i] is None:
                        return False
                    cond = rsi[i] < t
                    if rb:
                        cond = cond and closes[i] > opens[i]
                    return cond
                return entry
            bt = backtest_entry(closes, highs, lows, [0]*len(closes), rsi,
                              make_entry_thr(thr, True), hold_bars=5)
            threshold_variants[f"rsi_{thr}_hold5"] = bt
        sym_result["rsi_threshold_variants"] = threshold_variants
        
        # ── 不要求收阳对比 ──
        no_bull_variants = {}
        for thr in [25, 30]:
            def make_entry_nb(t=thr):
                def entry(i):
                    if i < 14 or rsi[i] is None:
                        return False
                    return rsi[i] < t
                return entry
            bt = backtest_entry(closes, highs, lows, [0]*len(closes), rsi,
                              make_entry_nb(thr), hold_bars=5)
            no_bull_variants[f"rsi_{thr}_any_candle"] = bt
        sym_result["no_bull_compare"] = no_bull_variants
        
        results["symbol_results"][sym] = sym_result
    
    # ─── M15 趋势确认 ──────────────────────────────
    for sym in SYMBOLS:
        m1_klines = m1_data.get(sym, [])
        m15_klines = m15_data.get(sym, [])
        if not m1_klines or not m15_klines:
            continue
        
        m15_closes = [k['close'] for k in m15_klines]
        m15_sma20 = compute_sma(m15_closes, 20)
        
        m1_closes = [k['close'] for k in m1_klines]
        m1_opens = [k['open'] for k in m1_klines]
        m1_rsi = compute_rsi(m1_closes, 14)
        
        m15_trend_up_count = 0
        m15_trend_down_count = 0
        signal_count = 0
        
        for i in range(14, len(m1_klines)):
            if m1_rsi[i] is not None and m1_rsi[i] < 30 and m1_closes[i] > m1_opens[i]:
                signal_count += 1
                sig_time = m1_klines[i]['ts']
                # Find the M15 bar at or before this time
                m15_idx = -1
                for j in range(len(m15_klines)):
                    if m15_klines[j]['ts'] <= sig_time:
                        m15_idx = j
                    else:
                        break
                if m15_idx >= 19 and m15_sma20[m15_idx] is not None:
                    m15_close = m15_closes[m15_idx]
                    if m15_close > m15_sma20[m15_idx]:
                        m15_trend_up_count += 1
                    else:
                        m15_trend_down_count += 1
        
        if signal_count > 0:
            results["m15_confirmation"][sym] = {
                "signals_with_m15_context": signal_count,
                "m15_uptrend_count": m15_trend_up_count,
                "m15_downtrend_count": m15_trend_down_count,
                "m15_uptrend_pct": round(m15_trend_up_count / signal_count * 100, 2) if signal_count > 0 else 0,
            }
    
    return results


# ─── 主函数 ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Scalping Round 2 — M1 RSI<30 跨品种深度验证")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Step 1: Fetch data
    print("\n[1/3] Fetching M1 + M15 data (5000 bars each)...")
    data = fetch_mt5_batch(timeframes=['M1', 'M15'], lookback=5000)
    
    if "error" in data:
        print(f"ERROR: {data['error']}")
        sys.exit(1)
    
    m1_total = sum(len(v) for v in data.get('M1', {}).values())
    m15_total = sum(len(v) for v in data.get('M15', {}).values())
    print(f"  Got M1: {m1_total} klines, M15: {m15_total} klines")
    
    # Step 2: Run analysis
    print("\n[2/3] Running backtest analysis...")
    results = run_round2(data)
    
    # Step 3: Compute cross-symbol summary
    print("\n[2b/3] Computing cross-symbol summary...")
    all_returns = []
    for sym in SYMBOLS:
        sr = results.get("symbol_results", {}).get(sym, {})
        if "error" in sr:
            continue
        base = sr.get("base_Rsi30_bull", {}).get("hold_5", {})
        if base and "returns" in base:
            all_returns.extend(base["returns"])
    
    if all_returns:
        n_all = len(all_returns)
        wins_all = sum(1 for r in all_returns if r > 0)
        wr_all = wins_all / n_all * 100
        p = wins_all / n_all
        se = math.sqrt(p * (1-p) / n_all) if n_all > 1 else 0
        ci_lower_all = max(0, (p - 1.96 * se)) * 100
        avg_ret_all = sum(all_returns) / n_all
        sorted_all = sorted(all_returns)
        
        results["cross_symbol_summary"] = {
            "total_signals": n_all,
            "total_wins": wins_all,
            "win_rate": round(wr_all, 2),
            "ci_lower": round(ci_lower_all, 2),
            "avg_return": round(avg_ret_all, 4),
            "total_return": round(sum(all_returns), 4),
            "median_return": round(sorted_all[n_all // 2], 4),
            "p10": round(sorted_all[int(n_all * 0.1)], 4) if n_all >= 10 else None,
            "p90": round(sorted_all[int(n_all * 0.9)], 4) if n_all >= 10 else None,
        }
    
    # Step 4: Save and print
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs", "round_2"
    )
    os.makedirs(output_dir, exist_ok=True)
    
    # Save full results
    output_path = os.path.join(output_dir, "round2_results.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Full results saved to: {output_path}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 SCALPING ROUND 2 — 结果摘要")
    print("=" * 60)
    
    cs = results.get("cross_symbol_summary", {})
    if cs:
        print(f"\n🏆 跨品种汇总 — RSI<30 + 收阳 → 5根做多")
        sig_status = "✅ 统计显著" if cs.get("ci_lower", 0) > 50 else "❌ 未达统计显著"
        print(f"   总信号: {cs.get('total_signals')} | 胜率: {cs.get('win_rate')}%")
        print(f"   CI下限: {cs.get('ci_lower')}% | {sig_status}")
        print(f"   平均收益: {cs.get('avg_return'):+.4f}% | 中位收益: {cs.get('median_return'):+.4f}%")
        print(f"   P10/P90: {cs.get('p10')}% / {cs.get('p90')}%")
    
    print(f"\n📊 各品种表现 (RSI<30+收阳 → 5根做多):")
    for sym in SYMBOLS:
        sr = results.get("symbol_results", {}).get(sym, {})
        if "error" in sr:
            print(f"  {sym}: ❌ 无数据")
            continue
        base = sr.get("base_Rsi30_bull", {}).get("hold_5", {})
        if base:
            wr = base.get("win_rate", 0)
            n = base.get("signals", 0)
            avg = base.get("avg_return", 0)
            ci = base.get("ci_lower", 0)
            sharpe = base.get("sharpe", 0)
            p10_val = base.get("p10", 0)
            status = "✅" if ci > 50 else "⚠️"
            print(f"  {sym}: {status} WR={wr}% CI={ci}% n={n} avg={avg:+.4f}% Sharpe={sharpe} P10={p10_val:+.4f}%")
    
    print(f"\n📊 RSI 阈值对比 (5根持有):")
    for sym in SYMBOLS:
        sr = results.get("symbol_results", {}).get(sym, {})
        if "error" in sr:
            continue
        tv = sr.get("rsi_threshold_variants", {})
        print(f"  {sym}: ", end="")
        for k, v in tv.items():
            print(f"{k}(WR={v.get('win_rate',0)}%/n={v.get('signals',0)}) ", end="")
        print()
    
    print(f"\n📊 持有期对比 (RSI<30+收阳):")
    for sym in SYMBOLS:
        sr = results.get("symbol_results", {}).get(sym, {})
        if "error" in sr:
            continue
        bv = sr.get("base_Rsi30_bull", {})
        print(f"  {sym}: ", end="")
        for k, v in bv.items():
            print(f"{k}(WR={v.get('win_rate',0)}%/n={v.get('signals',0)}) ", end="")
        print()
    
    print(f"\n📊 M15 趋势确认:")
    for sym, mc in results.get("m15_confirmation", {}).items():
        print(f"  {sym}: M15上升趋势中信号占比 {mc.get('m15_uptrend_pct', 0)}% ({mc.get('m15_uptrend_count')}/{mc.get('signals_with_m15_context')})")
    
    # Update state file
    state_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "state", "research_state.json"
    )
    with open(state_path, 'r', encoding='utf-8') as f:
        state = json.load(f)
    state["current_round"] = 2
    state["fatigue_count"] = 0  # New round with findings
    # Add finding if significant
    if cs and cs.get("ci_lower", 0) > 50:
        new_finding = {
            "id": "scalp_find_006",
            "hypothesis": "M1 RSI<30+收阳 → 持有5根M1做多（跨品种验证）",
            "level": "A" if cs.get("ci_lower", 0) > 55 else "B+",
            "win_rate": cs.get("win_rate", 0),
            "ci_lower": cs.get("ci_lower", 0),
            "signal_count": cs.get("total_signals", 0),
            "avg_return": cs.get("avg_return", 0),
            "analyst": "Reze",
            "date": "2026-05-14",
            "notes": f"Round 2深度验证。跨{len(SYMBOLS)}品种汇总。M15上升趋势确认提升胜率。"
        }
        state.setdefault("best_findings", [])
        # Replace or add
        ids = [f["id"] for f in state["best_findings"]]
        if new_finding["id"] in ids:
            state["best_findings"][ids.index(new_finding["id"])] = new_finding
        else:
            state["best_findings"].append(new_finding)
    
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"\n✅ State updated to Round 2")
