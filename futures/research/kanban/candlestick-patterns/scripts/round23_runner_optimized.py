#!/usr/bin/env python3
""""
Round 23 — 优化版：预计算各品种指标缓存后运行6个假设测试
"""
import sys, os, json, warnings, time
warnings.filterwarnings('ignore')
from datetime import datetime
from typing import Any, Dict, List
import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
INTRADAY_SCRIPTS = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "futures-intraday", "scripts"))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, INTRADAY_SCRIPTS)

from data_loader import load_data, compute_indicators, list_available_symbols
from candlestick_features import add_candlestick_features, list_available_patterns

NOW_STR = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
OUT_DIR = os.path.join(PROJECT_DIR, "data")
STATE_PATH = os.path.join(PROJECT_DIR, "state", "research_state.json")
REPORT_DIR = os.path.join(PROJECT_DIR, "reports")

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# ─── Data Cache ───
_cache: Dict[str, pd.DataFrame] = {}

def load_with_cache(timeframe: str, symbols: list) -> Dict[str, pd.DataFrame]:
    """Load data with in-memory caching (compute indicators once per symbol per timeframe)."""
    key_prefix = f"{timeframe}:"
    result = {}
    need_load = []
    for sym in symbols:
        key = key_prefix + sym
        if key in _cache:
            result[sym] = _cache[key]
        else:
            need_load.append(sym)
    if need_load:
        raw = load_data(timeframe=timeframe, symbols=need_load)
        for sym in need_load:
            if sym in raw:
                t0 = time.time()
                df = compute_indicators(raw[sym])
                df = add_candlestick_features(df)
                elapsed = time.time() - t0
                print(f"  ⏳ [{timeframe}] {sym} 指标计算完成: {elapsed:.1f}s", flush=True)
                key = key_prefix + sym
                _cache[key] = df
                result[sym] = df
            else:
                print(f"  ⚠️ {sym} 无数据", flush=True)
    return result


# ─── Stats computation (same as grid_engine) ───
_PERIODS_PER_YEAR = {"H1": 5000, "M30": 10000}

def _compute_stats(returns: np.ndarray, hold_period: int, periods_per_year: int) -> dict:
    if len(returns) == 0:
        return {"signal_count": 0, "win_rate": 0, "avg_return": 0,
                "std_return": 0, "sharpe_ratio": 0, "max_drawdown": 0}
    wr = (returns > 0).mean()
    avg = returns.mean()
    std = returns.std() if returns.std() > 0 else 1e-10
    sharpe = (avg / std) * np.sqrt(periods_per_year / hold_period) if hold_period > 0 else 0
    dd = np.minimum(0, returns.min()) if len(returns) > 0 else 0
    return {"signal_count": len(returns), "win_rate": round(wr, 4),
            "avg_return": round(avg, 6), "std_return": round(std, 6),
            "sharpe_ratio": round(sharpe, 4), "max_drawdown": round(dd, 6)}


def run_hypothesis(entry_condition: str, direction: str, timeframe: str,
                   symbols: list = None, label: str = "",
                   hold_periods: list = None) -> list:
    if symbols is None:
        symbols = list_available_symbols(timeframe)
    if hold_periods is None:
        hold_periods = [1, 2, 3, 5, 7, 10, 12, 15, 20]

    periods_per_year = _PERIODS_PER_YEAR[timeframe]
    dir_sign = 1.0 if direction == "long" else -1.0

    print(f"\n{'='*70}")
    print(f"  🔬 {label}")
    print(f"  Condition: {entry_condition} | Dir: {direction} | TF: {timeframe}")
    print(f"{'='*70}", flush=True)

    data = load_with_cache(timeframe=timeframe, symbols=symbols)
    findings = []
    for sym, df in data.items():
        n_rows = len(df)
        if n_rows == 0:
            continue
        close_arr = df["close"].values
        open_arr = df["open"].values
        try:
            mask = df.eval(entry_condition).values.astype(bool)
        except Exception as e:
            print(f"  ⚠️ {sym} eval失败: {e}", flush=True)
            continue
        signal_indices = np.where(mask)[0]
        if len(signal_indices) == 0:
            continue
        for hp in hold_periods:
            rets = []
            for i in signal_indices:
                exit_idx = i + hp
                if exit_idx >= n_rows:
                    continue
                ret = (close_arr[exit_idx] - close_arr[i]) / close_arr[i] * dir_sign
                rets.append(ret)
            ret_arr = np.array(rets, dtype=np.float64)
            stats = _compute_stats(ret_arr, hp, periods_per_year)
            stats["signal_count"] = len(rets)
            cnt = stats["signal_count"]
            if cnt < 30:
                continue
            wr = stats["win_rate"]
            findings.append({
                "symbol": sym, "timeframe": timeframe,
                "entry_condition": entry_condition, "direction": direction,
                "hold_period": hp, "win_rate": round(wr * 100, 2),
                "signal_count": cnt, "avg_return": stats["avg_return"],
                "sharpe_ratio": stats["sharpe_ratio"],
                "max_drawdown": stats["max_drawdown"],
            })

    strong = [f for f in findings if f["win_rate"] >= 60.0]
    promising = [f for f in findings if 55.0 <= f["win_rate"] < 60.0]

    print(f"\n  RESULTS: {label}")
    print(f"  {'品种':<10} {'持有':>4} {'胜率':>7} {'n':>6} {'Sharpe':>8}")
    print(f"  {'-'*40}")
    for f in sorted(findings, key=lambda x: -x["win_rate"]):
        wr = f["win_rate"]
        if wr >= 55.0:
            star = "⭐" if wr >= 60 else "💡"
            print(f"  {star} {f['symbol']:<8} {f['hold_period']:>4} {wr:>6.1f}% {f['signal_count']:>6} {f['sharpe_ratio']:>8.2f}", flush=True)

    return findings, strong, promising


def run_yearly_validation(entry_condition: str, direction: str, timeframe: str,
                          symbol: str, hold_period: int, label: str = ""):
    print(f"\n{'='*60}")
    print(f"  📅 分年验证: {label}")
    print(f"  {symbol} {timeframe} hold={hold_period}", flush=True)

    data = load_with_cache(timeframe=timeframe, symbols=[symbol])
    if symbol not in data:
        return {}
    df = data[symbol]
    dir_sign = 1.0 if direction == "long" else -1.0

    mask = df.eval(entry_condition).values.astype(bool)
    signal_indices = np.where(mask)[0]
    signal_years = [df.index[i].year for i in signal_indices]

    results = {}
    for year in sorted(set(signal_years)):
        year_indices = [i for i, y in zip(signal_indices, signal_years) if y == year]
        rets = []
        for i in year_indices:
            exit_idx = i + hold_period
            if exit_idx >= len(df):
                continue
            ret = (df.iloc[exit_idx]["close"] - df.iloc[i]["close"]) / df.iloc[i]["close"] * dir_sign
            rets.append(ret)
        if len(rets) < 10:
            continue
        ret_arr = np.array(rets)
        wr = (ret_arr > 0).mean() * 100
        avg = ret_arr.mean()
        std = ret_arr.std() if ret_arr.std() > 0 else 1e-10
        sharpe = (avg / std) * np.sqrt(5000 / hold_period) if hold_period > 0 else 0
        results[int(year)] = {"n": len(rets), "win_rate": round(wr, 2),
                              "avg_return": round(avg, 6), "sharpe": round(sharpe, 2)}
        sig = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
        print(f"  {sig} {year}: WR={wr:.1f}% n={len(rets)} Sharpe={sharpe:.2f}", flush=True)

    if results:
        ok = sum(1 for y in results.values() if y["win_rate"] >= 60)
        total = len(results)
        print(f"  📊 {ok}/{total} 年 WR≥60%", flush=True)
    return results


def run_atr_optimization(entry_condition: str, direction: str, timeframe: str,
                          symbol: str, hold_period: int = 5, label: str = "",
                          atr_multipliers: list = None):
    if atr_multipliers is None:
        atr_multipliers = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
    print(f"\n{'='*60}")
    print(f"  📐 ATR Trailing Stop: {label}")
    print(f"  {symbol} {timeframe} hold={hold_period}", flush=True)

    data = load_with_cache(timeframe=timeframe, symbols=[symbol])
    if symbol not in data:
        return {}
    df = data[symbol]
    dir_sign = 1.0 if direction == "long" else -1.0

    mask = df.eval(entry_condition).values.astype(bool)
    signal_indices = np.where(mask)[0]

    results = {}
    for atr_mult in atr_multipliers:
        rets = []
        for i in signal_indices:
            if i + hold_period >= len(df):
                continue
            entry_price = df.iloc[i]["close"]
            atr = df.iloc[i]["atr14"]
            atr_stop = atr * atr_mult
            best_price = entry_price
            exit_price = None
            for j in range(i, i + hold_period + 1):
                if direction == "long":
                    best_price = max(best_price, df.iloc[j]["high"])
                    if df.iloc[j]["low"] <= (best_price - atr_stop):
                        exit_price = best_price - atr_stop
                        break
                else:
                    best_price = min(best_price, df.iloc[j]["low"])
                    if df.iloc[j]["high"] >= (best_price + atr_stop):
                        exit_price = best_price + atr_stop
                        break
            if exit_price is None:
                exit_price = df.iloc[i + hold_period]["close"]
            ret = (exit_price - entry_price) / entry_price * dir_sign
            rets.append(ret)
        if len(rets) < 10:
            continue
        ret_arr = np.array(rets)
        wr = (ret_arr > 0).mean() * 100
        avg = ret_arr.mean()
        std = ret_arr.std() if ret_arr.std() > 0 else 1e-10
        sharpe = (avg / std) * np.sqrt(5000 / hold_period) if hold_period > 0 else 0
        results[atr_mult] = {"n": len(rets), "win_rate": round(wr, 2),
                             "avg_return": round(avg, 6), "sharpe": round(sharpe, 2)}
        sig = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
        print(f"  {sig} ATR x{atr_mult:.1f}: WR={wr:.1f}% n={len(rets)} Sharpe={sharpe:.2f}", flush=True)
    return results


def main():
    total_t0 = time.time()
    print("=" * 70)
    print("  🕯️  第23轮 K线形态研究 (优化版) — 6个假设深度验证")
    print(f"  日期: {NOW_STR}")
    print("=" * 70, flush=True)

    all_strong = []
    all_promising = []
    all_findings = []
    yearly_results = {}
    atr_results = {}
    cache_stats = {"h1_symbols": 0, "m30_symbols": 0}

    # ═══════════════════════════════════════════════════════════════════
    # H1: EURUSD Doji+RSI>75 — 分年验证+Session过滤+ATR优化
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "█" * 70)
    print("  █ H1：EURUSD Doji+RSI>75 — 分年验证+Session过滤+ATR优化")
    print("█" * 70, flush=True)

    # RSI阈值对比
    for rsi_thresh in [70, 72, 75, 78]:
        cond = f"doji and rsi14 > {rsi_thresh}"
        f, s, p = run_hypothesis(cond, "short", "H1", symbols=["EURUSD"],
            label=f"H1a: Doji+RSI>{rsi_thresh} → 做空", hold_periods=[1, 2, 3, 5, 7, 10, 12])
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # Session分离
    for ses_filter, ses_label in [("", "全部"), ("session == 'asia'", "亚盘"),
                                    ("session == 'europe'", "欧盘"), ("session == 'us'", "美盘")]:
        cond = "doji and rsi14 > 75"
        if ses_filter:
            cond = f"({cond}) and {ses_filter}"
        f, s, p = run_hypothesis(cond, "short", "H1", symbols=["EURUSD"],
            label=f"H1b: Doji+RSI>75 {ses_label} → 做空", hold_periods=[1, 2, 3, 5, 7, 10, 12])
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # 分年验证
    for hp in [1, 2, 3, 5]:
        yr = run_yearly_validation("doji and rsi14 > 75", "short", "H1",
                                    "EURUSD", hp, f"EURUSD Doji75 hold={hp}")
        yearly_results[f"EURUSD_Doji75_h{hp}"] = yr

    # ATR优化
    for hp in [1, 2, 3]:
        ar = run_atr_optimization("doji and rsi14 > 75", "short", "H1",
                                   "EURUSD", hp, f"EURUSD Doji75 hold={hp}")
        atr_results[f"EURUSD_Doji75_h{hp}_atr"] = ar

    # ═══════════════════════════════════════════════════════════════════
    # H2: UKOIL Evening Star+RSI>60 M30 short hold=18 — 分年验证
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "█" * 70)
    print("  █ H2：UKOIL Evening Star+RSI>60 M30 — 分年验证+Session对比")
    print("█" * 70, flush=True)

    for ses_filter, ses_label in [("", "全部"), ("session == 'europe'", "欧盘"),
                                    ("session == 'us'", "美盘"), ("session == 'asia'", "亚盘")]:
        cond = "evening_star and rsi14 > 60"
        if ses_filter:
            cond = f"({cond}) and {ses_filter}"
        f, s, p = run_hypothesis(cond, "short", "M30", symbols=["UKOIL"],
            label=f"H2a: UKOIL ES+RSI>60 M30 {ses_label} → 做空",
            hold_periods=[12, 15, 18, 20, 24, 30, 36])
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # 分年验证 (hold=18, 全/欧/美)
    for ses_cond, ses_key in [("", "全部"), ("and session == 'europe'", "欧盘"),
                               ("and session == 'us'", "美盘")]:
        cond = "evening_star and rsi14 > 60"
        if ses_cond:
            cond = f"({cond}) {ses_cond}"
        yr = run_yearly_validation(cond, "short", "M30", "UKOIL", 18,
                                    f"UKOIL ES+R60 {ses_key} hold=18")
        yearly_results[f"UKOIL_ES_R60_{ses_key}_h18"] = yr

    # ═══════════════════════════════════════════════════════════════════
    # H3: XCUUSD Inside Bar+RSI>70 H1 short — 深度测试
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "█" * 70)
    print("  █ H3：XCUUSD Inside Bar+RSI>70 H1 — 深度测试")
    print("█" * 70, flush=True)

    for rsi_thresh in [65, 70, 75]:
        f, s, p = run_hypothesis(f"inside_bar and rsi14 > {rsi_thresh}", "short", "H1",
            symbols=["XCUUSD"], label=f"H3a: Inside Bar+RSI>{rsi_thresh} → 做空",
            hold_periods=[1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 48])
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    for ses_filter, ses_label in [("session == 'asia'", "亚盘"),
                                    ("session == 'europe'", "欧盘"), ("session == 'us'", "美盘")]:
        cond = f"(inside_bar and rsi14 > 70) and {ses_filter}"
        f, s, p = run_hypothesis(cond, "short", "H1", symbols=["XCUUSD"],
            label=f"H3b: Inside Bar+RSI>70 {ses_label} → 做空",
            hold_periods=[1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 48])
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # 分年验证
    for hp in [7, 10, 24]:
        yr = run_yearly_validation("inside_bar and rsi14 > 70", "short", "H1",
                                    "XCUUSD", hp, f"XCUUSD IB+RSI70 hold={hp}")
        yearly_results[f"XCUUSD_IB_R70_h{hp}"] = yr

    # ═══════════════════════════════════════════════════════════════════
    # H4: HK50 Three Black Crows+RSI>65+趋势过滤 H1 short
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "█" * 70)
    print("  █ H4：HK50 Three Black Crows+RSI>65 H1 — 趋势过滤")
    print("█" * 70, flush=True)

    for cond, cond_label in [
        ("three_black_crows and rsi14 > 65", "基准"),
        ("three_black_crows and rsi14 > 65 and close > ma200", "价格>MA200"),
        ("three_black_crows and rsi14 > 65 and close < ma200", "价格<MA200"),
        ("three_black_crows and rsi14 > 65 and rsi14 < 70", "RSI 65-70"),
        ("three_black_crows and rsi14 > 70", "RSI>70"),
    ]:
        f, s, p = run_hypothesis(cond, "short", "H1", symbols=["HK50"],
            label=f"H4: HK50 TBC {cond_label} → 做空",
            hold_periods=[1, 2, 3, 5, 7, 10, 12, 15, 20, 24])
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # 分年验证
    for cond, cond_key in [
        ("three_black_crows and rsi14 > 65", "基准"),
        ("three_black_crows and rsi14 > 65 and close > ma200", "价格>MA200"),
    ]:
        for hp in [5, 10, 15]:
            yr = run_yearly_validation(cond, "short", "H1", "HK50", hp,
                                        f"HK50 TBC+R65 {cond_key} hold={hp}")
            yearly_results[f"HK50_TBC_{cond_key}_h{hp}"] = yr

    # ═══════════════════════════════════════════════════════════════════
    # H5: AUDUSD Doji+RSI>75 H1 short ATR x2.5 — 扩展至其他品种
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "█" * 70)
    print("  █ H5：AUDUSD Doji+RSI>75 ATR优化 — 扩展至NZDUSD/GBPUSD")
    print("█" * 70, flush=True)

    for sym in ["AUDUSD", "NZDUSD", "GBPUSD", "EURUSD"]:
        # RSI阈值
        for rsi_thresh in [72, 75, 78]:
            f, s, p = run_hypothesis(f"doji and rsi14 > {rsi_thresh}", "short", "H1",
                symbols=[sym], label=f"H5a: {sym} Doji+RSI>{rsi_thresh} → 做空",
                hold_periods=[1, 2, 3, 5, 7, 10, 12])
            all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

        # Session分离
        for ses_filter, ses_label in [("session == 'europe'", "欧盘"), ("session == 'us'", "美盘")]:
            cond = f"(doji and rsi14 > 75) and {ses_filter}"
            f, s, p = run_hypothesis(cond, "short", "H1", symbols=[sym],
                label=f"H5b: {sym} Doji+RSI>75 {ses_label} → 做空",
                hold_periods=[1, 2, 3, 5, 7, 10, 12])
            all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

        # ATR优化
        for hp in [1, 2, 3]:
            ar = run_atr_optimization("doji and rsi14 > 75", "short", "H1",
                                       sym, hp, f"{sym} Doji75 hold={hp}")
            atr_results[f"{sym}_Doji75_h{hp}_atr"] = ar

        # 分年验证
        for hp in [1, 2, 3]:
            yr = run_yearly_validation("doji and rsi14 > 75", "short", "H1",
                                        sym, hp, f"{sym} Doji75 hold={hp}")
            yearly_results[f"{sym}_Doji75_h{hp}"] = yr

    # ═══════════════════════════════════════════════════════════════════
    # H6: 全品种 Doji+RSI极端值做空扫描 H1
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "█" * 70)
    print("  █ H6：全品种 Doji+RSI极端值做空扫描 H1")
    print("█" * 70, flush=True)

    ALL_H1 = list_available_symbols("H1")
    for rsi_thresh in [75, 78]:
        f, s, p = run_hypothesis(f"doji and rsi14 > {rsi_thresh}", "short", "H1",
            symbols=ALL_H1, label=f"H6: 全品种 Doji+RSI>{rsi_thresh} → 做空",
            hold_periods=[1, 2, 3, 5, 7, 10, 12, 15, 20])
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # ═══════════════════════════════════════════════════════════════════
    # Summary & Save
    # ═══════════════════════════════════════════════════════════════════
    elapsed = time.time() - total_t0
    print(f"\n\n{'='*70}")
    print(f"  📊 ROUND 23 SUMMARY (耗时: {elapsed/60:.1f}分)")
    print(f"{'='*70}")
    print(f"\n| {'品种':<10} | {'TF':<4} | {'方向':<4} | {'持有':<5} | {'胜率':<7} | {'n':<6} | {'Sharpe':<8}")
    print(f"|{'':->10}|{'':->4}|{'':->4}|{'':->5}|{'':->7}|{'':->6}|{'':->8}")

    for f in sorted(all_findings, key=lambda x: -x["win_rate"]):
        wr = f["win_rate"]
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        star = "⭐" if wr >= 60 else ("💡" if wr >= 55 else "")
        if wr >= 55:
            print(f"| {star} {f['symbol']:<7} | {f['timeframe']:<4} | {dir_cn:<4} | {f['hold_period']:<5} | {wr:>5.1f}% | {f['signal_count']:<6} | {f['sharpe_ratio']:<8.2f}")

    print(f"\n  强信号 (WR>=60%, n>=30): {len(all_strong)}")
    for f in sorted(all_strong, key=lambda x: -x["win_rate"]):
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        print(f"    ⭐ {f['symbol']:10s} {f['timeframe']:4s} {dir_cn:4s} hold={f['hold_period']:3d}  WR={f['win_rate']:5.1f}%  n={f['signal_count']:5d}  Sharpe={f['sharpe_ratio']:7.2f}")

    print(f"\n  潜力信号 (55%<=WR<60%, n>=30): {len(all_promising)}")
    for f in sorted(all_promising, key=lambda x: -x["win_rate"]):
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        print(f"    💡 {f['symbol']:10s} {f['timeframe']:4s} {dir_cn:4s} hold={f['hold_period']:3d}  WR={f['win_rate']:5.1f}%  n={f['signal_count']:5d}  Sharpe={f['sharpe_ratio']:7.2f}")

    # Save results
    output = {
        "round": 23,
        "date": NOW_STR,
        "timeframes": ["H1", "M30"],
        "symbols": list_available_symbols("H1"),
        "all_findings": all_findings,
        "strong_findings": all_strong,
        "promising_findings": all_promising,
        "yearly_validations": yearly_results,
        "atr_optimizations": atr_results,
        "elapsed_minutes": round(elapsed / 60, 1),
    }
    results_path = os.path.join(OUT_DIR, "round23_results.json")
    with open(results_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 结果已保存: {results_path}")
    print(f"⏱ 总耗时: {elapsed/60:.1f} 分钟")

    return all_findings, all_strong, all_promising


if __name__ == "__main__":
    findings, strong, promising = main()
