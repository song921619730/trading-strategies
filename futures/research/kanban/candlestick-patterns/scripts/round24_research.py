#!/usr/bin/env python3
"""
Round 24 — H1/M30 K线形态研究: UKOIL美盘ES验证 + AUDUSD Doji + 全品种补全

本轮基于 Round 23 发现，聚焦 5 个待办假设:
1. UKOIL Evening Star 美盘单独验证 M30 hold=15 (P0)
2. AUDUSD Doji+RSI>78 美盘做空 H1 hold=5 (P0)
3. 全品种 Doji+RSI>75/78 H1 全品种扫描补全 (P1)
4. UKOIL Evening Star 美盘 + trend filter M30 (P1)
5. UKOIL ES扩展至USOIL M30 (P2)
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
                # Normalize column names to lowercase (parquet files use uppercase)
                df = raw[sym].copy()
                df.columns = [c.lower() for c in df.columns]
                df = compute_indicators(df)
                df = add_candlestick_features(df)
                elapsed = time.time() - t0
                print(f"  ⏳ [{timeframe}] {sym} 计算完成: {elapsed:.1f}s", flush=True)
                key = key_prefix + sym
                _cache[key] = df
                result[sym] = df
            else:
                print(f"  ⚠️ {sym} 无数据", flush=True)
    return result

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
                   hold_periods: list = None, min_signals: int = 20) -> list:
    if symbols is None:
        symbols = list_available_symbols(timeframe)
    if hold_periods is None:
        hold_periods = [1, 2, 3, 5, 7, 10, 12, 15, 20]
    periods_per_year = _PERIODS_PER_YEAR[timeframe]
    dir_sign = 1.0 if direction == "long" else -1.0

    print(f"\n{'='*65}")
    print(f"  🔬 {label}")
    print(f"  cond={entry_condition} | dir={direction} | tf={timeframe}")
    print(f"  sym={symbols} | holds={hold_periods}", flush=True)

    data = load_with_cache(timeframe=timeframe, symbols=symbols)
    findings = []
    for sym, df in data.items():
        n_rows = len(df)
        if n_rows == 0:
            continue
        close_arr = df["close"].values
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
            cnt = len(rets)
            if cnt < min_signals:
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
    print(f"\n{'='*55}")
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


def run_regime_validation(entry_condition: str, direction: str, timeframe: str,
                           symbol: str, hold_period: int, label: str = "") -> dict:
    """Check if the signal is stronger in trending vs choppy conditions using MA slope."""
    print(f"\n{'='*55}")
    print(f"  🌊 市场状态分离: {label}")
    print(f"  {symbol} {timeframe} hold={hold_period}", flush=True)
    data = load_with_cache(timeframe=timeframe, symbols=[symbol])
    if symbol not in data:
        return {}
    df = data[symbol]
    dir_sign = 1.0 if direction == "long" else -1.0

    # Define regimes based on MA slope
    df["ma50_slope"] = df["ma50"].pct_change(20)  # 20-period slope
    df["trending"] = df["ma50_slope"].abs() > 0.002  # steep enough
    df["choppy"] = df["ma50_slope"].abs() <= 0.002

    mask = df.eval(entry_condition).values.astype(bool)
    signal_indices = np.where(mask)[0]

    results = {}
    for regime, regime_label in [("trending", "趋势市"), ("choppy", "震荡市")]:
        regime_mask = df[regime].values.astype(bool)
        valid = mask & regime_mask
        valid_indices = np.where(valid)[0]
        if len(valid_indices) < 10:
            print(f"  ⚠️ {regime_label} 信号不足: {len(valid_indices)}个", flush=True)
            continue
        rets = []
        for i in valid_indices:
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
        results[regime] = {"label": regime_label, "n": len(rets),
                           "win_rate": round(wr, 2), "sharpe": round(sharpe, 2)}
        sig = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
        print(f"  {sig} {regime_label}: WR={wr:.1f}% n={len(rets)} Sharpe={sharpe:.2f}", flush=True)
    return results


def run_multiday_validation(entry_condition: str, direction: str, timeframe: str,
                             symbol: str, label: str = "") -> dict:
    """Test if signal works across both H1 and M30 timeframes."""
    print(f"\n{'='*55}")
    print(f"  🔄 跨时间框架验证: {label}", flush=True)
    results = {}
    for tf in ["H1", "M30"]:
        data = load_with_cache(timeframe=tf, symbols=[symbol])
        if symbol not in data:
            continue
        df = data[symbol]
        dir_sign = 1.0 if direction == "long" else -1.0
        periods_per_year = _PERIODS_PER_YEAR[tf]
        try:
            mask = df.eval(entry_condition).values.astype(bool)
        except:
            continue
        signal_indices = np.where(mask)[0]
        for hp in [5, 10, 15, 20]:
            rets = []
            for i in signal_indices:
                exit_idx = i + hp
                if exit_idx >= len(df):
                    continue
                ret = (df.iloc[exit_idx]["close"] - df.iloc[i]["close"]) / df.iloc[i]["close"] * dir_sign
                rets.append(ret)
            if len(rets) < 20:
                continue
            ret_arr = np.array(rets)
            wr = (ret_arr > 0).mean() * 100
            avg = ret_arr.mean()
            std = ret_arr.std() if ret_arr.std() > 0 else 1e-10
            sharpe = (avg / std) * np.sqrt(periods_per_year / hp) if hp > 0 else 0
            results[f"{tf}_h{hp}"] = {"n": len(rets), "win_rate": round(wr, 2), "sharpe": round(sharpe, 2)}
            sig = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
            print(f"  {sig} {tf} hold={hp}: WR={wr:.1f}% n={len(rets)} Sharpe={sharpe:.2f}", flush=True)
    return results


def main():
    total_t0 = time.time()
    print("=" * 70)
    print("  🕯️  第24轮 K线形态研究 (Round 24)")
    print(f"  日期: {NOW_STR}")
    print("  P0: UKOIL美盘ES验证 + AUDUSD Doji + 全品种补全")
    print("=" * 70, flush=True)

    all_findings = []
    all_strong = []
    all_promising = []
    yearly_results = {}
    regime_results = {}
    cross_tf_results = {}

    # ═══════════════════════════════════════════════════════════════════
    # H1: UKOIL Evening Star 美盘单独验证 M30 hold=15 (P0 - round24_001)
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "█" * 70)
    print("  █ H1: UKOIL Evening Star 美盘验证 M30 — 大样本+分年 (P0)")
    print("█" * 70, flush=True)

    # 1a. 美盘ES+RSI>60 不同hold对比
    for ses_filter, ses_label in [("", "全部"), ("session == 'us'", "美盘"),
                                    ("session == 'europe'", "欧盘")]:
        cond = "evening_star and rsi14 > 60"
        if ses_filter:
            cond = f"({cond}) and {ses_filter}"
        f, s, p = run_hypothesis(cond, "short", "M30", symbols=["UKOIL"],
            label=f"H1a: UKOIL ES+R60 {ses_label} → 做空 (扩展hold)",
            hold_periods=[10, 12, 15, 18, 20, 24, 30, 36],
            min_signals=15)
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # 1b. 美盘+RSI>65 (更高RSI过滤)
    cond = "(evening_star and rsi14 > 65) and session == 'us'"
    f, s, p = run_hypothesis(cond, "short", "M30", symbols=["UKOIL"],
        label="H1b: UKOIL ES+R65 美盘 → 做空",
        hold_periods=[10, 12, 15, 18, 20, 24],
        min_signals=10)
    all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # 1c. 分年验证 - 美盘
    for hp in [12, 15, 18]:
        yr = run_yearly_validation(
            "(evening_star and rsi14 > 60) and session == 'us'",
            "short", "M30", "UKOIL", hp,
            f"UKOIL ES+R60 美盘 hold={hp} 分年验证")
        yearly_results[f"UKOIL_ES_R60_US_h{hp}"] = yr

    # 1d. 分年验证 - 全部
    for hp in [15, 18]:
        yr = run_yearly_validation(
            "evening_star and rsi14 > 60",
            "short", "M30", "UKOIL", hp,
            f"UKOIL ES+R60 全部 hold={hp} 分年验证")
        yearly_results[f"UKOIL_ES_R60_ALL_h{hp}"] = yr

    # 1e. 市场状态分离 (美盘ES+RSI>60)
    rr = run_regime_validation(
        "(evening_star and rsi14 > 60) and session == 'us'",
        "short", "M30", "UKOIL", 15,
        "UKOIL ES+R60 美盘 市场状态分离 hold=15")
    regime_results["UKOIL_ES_US_h15_regime"] = rr

    # 1f. 跨时间框架验证
    ct = run_multiday_validation(
        "evening_star and rsi14 > 60",
        "short", "M30", "UKOIL",
        "UKOIL ES+R60 跨TF验证")
    cross_tf_results["UKOIL_ES_R60_crossTF"] = ct

    # ═══════════════════════════════════════════════════════════════════
    # H2: AUDUSD Doji+RSI>78 美盘做空 H1 hold=5 (P0 - round24_002)
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "█" * 70)
    print("  █ H2: AUDUSD Doji+RSI>78 美盘做空 H1 — 分年验证+扩展 (P0)")
    print("█" * 70, flush=True)

    # 2a. AUDUSD RSI各阈值+Session分离
    for rsi_thresh in [72, 75, 78]:
        cond = f"doji and rsi14 > {rsi_thresh}"
        f, s, p = run_hypothesis(cond, "short", "H1", symbols=["AUDUSD"],
            label=f"H2a: AUDUSD Doji+RSI>{rsi_thresh} → 做空 (扩展hold)",
            hold_periods=[1, 2, 3, 5, 7, 10, 12, 15, 20])
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    for ses_filter, ses_label in [("session == 'asia'", "亚盘"), ("session == 'us'", "美盘"),
                                    ("session == 'europe'", "欧盘")]:
        cond = f"(doji and rsi14 > 78) and {ses_filter}"
        f, s, p = run_hypothesis(cond, "short", "H1", symbols=["AUDUSD"],
            label=f"H2b: AUDUSD Doji+RSI>78 {ses_label} → 做空",
            hold_periods=[1, 2, 3, 5, 7, 10, 12])
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # 2c. 分年验证 AUDUSD Doji+RSI>78
    for hp in [3, 5, 7]:
        yr = run_yearly_validation("doji and rsi14 > 78", "short", "H1",
                                    "AUDUSD", hp, f"AUDUSD Doji+R78 hold={hp}")
        yearly_results[f"AUDUSD_DojiR78_h{hp}"] = yr

    # 2d. 分年验证 美盘
    for hp in [3, 5]:
        yr = run_yearly_validation(
            "(doji and rsi14 > 75) and session == 'us'",
            "short", "H1", "AUDUSD", hp,
            f"AUDUSD Doji+R75 美盘 hold={hp}")
        yearly_results[f"AUDUSD_DojiR75_US_h{hp}"] = yr

    # 2e. 市场状态分离
    rr = run_regime_validation(
        "(doji and rsi14 > 75) and session == 'us'",
        "short", "H1", "AUDUSD", 5,
        "AUDUSD Doji+R75 美盘 市场状态分离 hold=5")
    regime_results["AUDUSD_Doji_US_h5_regime"] = rr

    # 2f. 品种扩展: GBPUSD, NZDUSD, EURUSD Doji+RSI>75/78
    for sym in ["GBPUSD", "NZDUSD", "EURUSD", "USDCHF", "USDJPY"]:
        for rsi_thresh in [75, 78]:
            f, s, p = run_hypothesis(f"doji and rsi14 > {rsi_thresh}", "short", "H1",
                symbols=[sym], label=f"H2f: {sym} Doji+RSI>{rsi_thresh} → 做空 (扩展)",
                hold_periods=[1, 2, 3, 5, 7, 10, 12])
            all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

        # Session分离
        for ses_filter, ses_label in [("session == 'us'", "美盘"), ("session == 'asia'", "亚盘")]:
            cond = f"(doji and rsi14 > 75) and {ses_filter}"
            f, s, p = run_hypothesis(cond, "short", "H1", symbols=[sym],
                label=f"H2g: {sym} Doji+R75 {ses_label} → 做空",
                hold_periods=[1, 2, 3, 5, 7, 10, 12])
            all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # ═══════════════════════════════════════════════════════════════════
    # H3: 全品种 Doji+RSI>75/78 H1 全品种扫描补全 (P1 - round24_003)
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "█" * 70)
    print("  █ H3: 全品种 Doji+RSI>75/78 H1 扫描补全 (P1)")
    print("█" * 70, flush=True)

    # 全品种 Doji+RSI>75 做空扫描
    f, s, p = run_hypothesis("doji and rsi14 > 75", "short", "H1",
        symbols=list_available_symbols("H1"),
        label="H3a: 全品种 Doji+RSI>75 → 做空 (全部19品种)",
        hold_periods=[1, 2, 3, 5, 7, 10, 12, 15, 20])
    all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # 全品种 Doji+RSI>78 做空扫描
    f, s, p = run_hypothesis("doji and rsi14 > 78", "short", "H1",
        symbols=list_available_symbols("H1"),
        label="H3b: 全品种 Doji+RSI>78 → 做空 (全部19品种)",
        hold_periods=[1, 2, 3, 5, 7, 10, 12, 15, 20])
    all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # 全品种 Doji+RSI>78 + 美盘
    f, s, p = run_hypothesis("(doji and rsi14 > 78) and session == 'us'", "short", "H1",
        symbols=list_available_symbols("H1"),
        label="H3c: 全品种 Doji+RSI>78 美盘 → 做空",
        hold_periods=[1, 2, 3, 5, 7, 10, 12])
    all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # ═══════════════════════════════════════════════════════════════════
    # H4: UKOIL Evening Star 美盘 + trend filter (P1 - round24_004)
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "█" * 70)
    print("  █ H4: UKOIL Evening Star 美盘 + Trend Filter M30 (P1)")
    print("█" * 70, flush=True)

    # 趋势过滤组合
    for trend_cond, trend_label in [
        ("atr14 > atr14_median", "ATR>中位(高波动)"),
        ("close > ma200", "价格>MA200(上升趋势)"),
        ("close < ma200", "价格<MA200(下降趋势)"),
        ("rsi14 > 60", "RSI>60(已有)"),
        ("rsi14 > 65", "RSI>65(更严格)"),
        ("rsi14 > 60 and vol > ma50", "RSI>60+VOL>MA50"),
        ("rsi14 > 60 and close > ma200", "RSI>60+价格>MA200"),
        ("rsi14 > 60 and close < ma200", "RSI>60+价格<MA200"),
    ]:
        cond = f"(evening_star and {trend_cond}) and session == 'us'"
        f, s, p = run_hypothesis(cond, "short", "M30", symbols=["UKOIL"],
            label=f"H4: UKOIL ES 美盘+{trend_label}",
            hold_periods=[10, 12, 15, 18, 20, 24],
            min_signals=8)
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # ═══════════════════════════════════════════════════════════════════
    # H5: UKOIL ES扩展至USOIL + 其他品种的Evening Star验证 (P2 - round24_005)
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "█" * 70)
    print("  █ H5: UKOIL ES扩展至USOIL + 其他品种ES验证 (P2)")
    print("█" * 70, flush=True)

    # USOIL Evening Star+RSI>60 M30
    for ses_filter, ses_label in [("", "全部"), ("session == 'us'", "美盘")]:
        cond = "evening_star and rsi14 > 60"
        if ses_filter:
            cond = f"({cond}) and {ses_filter}"
        f, s, p = run_hypothesis(cond, "short", "M30", symbols=["USOIL"],
            label=f"H5a: USOIL ES+R60 {ses_label} → 做空",
            hold_periods=[10, 12, 15, 18, 20, 24, 30],
            min_signals=10)
        all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # 全品种 Evening Star+RSI>60 M30 做空扫描
    f, s, p = run_hypothesis("evening_star and rsi14 > 60", "short", "M30",
        symbols=["USOIL", "XAUUSD", "XAGUSD", "USTEC", "US30", "US500",
                 "JP225", "HK50", "EURUSD", "GBPUSD"],
        label="H5b: 多品种 ES+R60 M30 → 做空",
        hold_periods=[10, 15, 18, 20, 24],
        min_signals=10)
    all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # 全品种 Evening Star+RSI>60 + 美盘 M30
    f, s, p = run_hypothesis("(evening_star and rsi14 > 60) and session == 'us'", "short", "M30",
        symbols=["USOIL", "XAUUSD", "XAGUSD", "USTEC", "US30", "US500",
                 "JP225", "HK50", "EURUSD", "GBPUSD"],
        label="H5c: 多品种 ES+R60 美盘 M30 → 做空",
        hold_periods=[10, 15, 18, 20, 24],
        min_signals=8)
    all_findings.extend(f); all_strong.extend(s); all_promising.extend(p)

    # ═══════════════════════════════════════════════════════════════════
    # Summary & Save
    # ═══════════════════════════════════════════════════════════════════
    elapsed = time.time() - total_t0
    print(f"\n\n{'='*70}")
    print(f"  📊 ROUND 24 SUMMARY (耗时: {elapsed/60:.1f}分)")
    print(f"{'='*70}")

    # 去重
    seen = set()
    findings_dedup = []
    for f in all_findings:
        key = (f["symbol"], f["timeframe"], f["entry_condition"], f["hold_period"])
        if key not in seen:
            seen.add(key)
            findings_dedup.append(f)

    strong_dedup = [f for f in findings_dedup if f["win_rate"] >= 60.0]
    promising_dedup = [f for f in findings_dedup if 55.0 <= f["win_rate"] < 60.0]

    print(f"\n| {'品种':<10} | {'TF':<4} | {'方向':<4} | {'持有':<5} | {'胜率':<7} | {'n':<6} | {'Sharpe':<8}")
    print(f"|{'' :->10}|{'' :->4}|{'' :->4}|{'' :->5}|{'' :->7}|{'' :->6}|{'' :->8}")

    for f in sorted(findings_dedup, key=lambda x: -x["win_rate"]):
        wr = f["win_rate"]
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        star = "⭐" if wr >= 60 else ("💡" if wr >= 55 else "")
        if wr >= 55:
            print(f"| {star} {f['symbol']:<7} | {f['timeframe']:<4} | {dir_cn:<4} | {f['hold_period']:<5} | {wr:>5.1f}% | {f['signal_count']:<6} | {f['sharpe_ratio']:<8.2f}")

    print(f"\n  强信号 (WR>=60%, n>=30): {len(strong_dedup)}")
    for f in sorted(strong_dedup, key=lambda x: -x["win_rate"]):
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        print(f"    ⭐ {f['symbol']:10s} {f['timeframe']:4s} {dir_cn:4s} hold={f['hold_period']:3d}  WR={f['win_rate']:5.1f}%  n={f['signal_count']:5d}  Sharpe={f['sharpe_ratio']:7.2f}  cond={f['entry_condition'][:40]}")

    print(f"\n  潜力信号 (55%<=WR<60%, n>=30): {len(promising_dedup)}")
    for f in sorted(promising_dedup, key=lambda x: -x["win_rate"]):
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        print(f"    💡 {f['symbol']:10s} {f['timeframe']:4s} {dir_cn:4s} hold={f['hold_period']:3d}  WR={f['win_rate']:5.1f}%  n={f['signal_count']:5d}  Sharpe={f['sharpe_ratio']:7.2f}")

    # Save results
    output = {
        "round": 24,
        "date": NOW_STR,
        "timeframes": ["H1", "M30"],
        "all_findings": findings_dedup,
        "strong_findings": strong_dedup,
        "promising_findings": promising_dedup,
        "yearly_validations": yearly_results,
        "regime_validations": regime_results,
        "cross_tf_validations": cross_tf_results,
        "elapsed_minutes": round(elapsed / 60, 1),
    }
    results_path = os.path.join(OUT_DIR, "round24_results.json")
    with open(results_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 结果已保存: {results_path}")
    print(f"⏱ 总耗时: {elapsed/60:.1f} 分钟")

    return findings_dedup, strong_dedup, promising_dedup


if __name__ == "__main__":
    findings, strong, promising = main()
