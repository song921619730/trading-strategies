#!/usr/bin/env python3
"""
Round 23 — H1/M30 K线形态研究: 深度验证与扩展

本轮聚焦 (6个待办假设):
1. EURUSD Doji+RSI>75 H1 short hold=1-2 — 分年验证+Session过滤+ATR优化
2. UKOIL Evening Star+RSI>60 M30 short hold=18 — 分年验证+美盘对比
3. XCUUSD Inside Bar+RSI>70 H1 short hold=24 + 亚盘Session深度测试
4. HK50 Three Black Crows+RSI>65+趋势过滤(price>ma200) H1 short
5. AUDUSD Doji+RSI>75 H1 short ATR x2.5 hold=3 — 分年验证+扩展至NZDUSD
6. 全品种 Doji+RSI极端值做空扫描 H1
"""

import sys, os, json
from datetime import datetime
from typing import Any, Dict, List

# ── Paths ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
INTRADAY_SCRIPTS = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "futures-intraday", "scripts"))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, INTRADAY_SCRIPTS)

import numpy as np
import pandas as pd
from data_loader import load_data, compute_indicators, list_available_symbols
from candlestick_engine import run_candlestick_grid
from candlestick_features import add_candlestick_features, list_available_patterns

# ─── Config ───
ALL_SYMBOLS = list_available_symbols("H1")
HOLD_SHORT = [1, 2, 3, 5, 7, 10, 12, 15, 20]
HOLD_MEDIUM = [1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30]
HOLD_LONG = [1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 48]
NOW_STR = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def run_hypothesis(entry_condition: str, direction: str, timeframe: str,
                   symbols: List[str] = None, label: str = "",
                   hold_periods: List[int] = None) -> List[Dict[str, Any]]:
    """Run a hypothesis and return structured findings."""
    if symbols is None:
        symbols = ALL_SYMBOLS
    if hold_periods is None:
        hold_periods = HOLD_MEDIUM

    print(f"\n{'='*80}")
    print(f"  🔬 {label}")
    print(f"  Condition: {entry_condition}")
    print(f"  Direction: {direction} | TF: {timeframe}")
    print(f"  Symbols: {len(symbols)}")
    print(f"{'='*80}")

    config = {
        "timeframe": timeframe,
        "symbols": symbols,
        "entry_condition": entry_condition,
        "direction": direction,
        "hold_periods": hold_periods,
        "exit_at_close": True,
    }
    results = run_candlestick_grid(config)
    meta = results.pop("_meta", {})

    findings = []
    for sym in sorted(results.keys()):
        sym_res = results[sym]
        for hp in sorted(sym_res.keys(), key=int):
            s = sym_res[hp]
            cnt = s.get("signal_count", 0)
            if cnt < 30:
                continue
            wr = s.get("win_rate", 0) or 0
            avg = s.get("avg_return", 0) or 0
            sharpe = s.get("sharpe_ratio", 0) or 0
            dd = s.get("max_drawdown", 0) or 0
            findings.append({
                "symbol": sym,
                "timeframe": timeframe,
                "entry_condition": entry_condition,
                "direction": direction,
                "hold_period": hp,
                "win_rate": round(wr * 100, 2),
                "signal_count": cnt,
                "avg_return": round(avg, 6),
                "sharpe_ratio": round(sharpe, 2),
                "max_drawdown": round(dd, 4),
            })

    # Print results
    print(f"\n  {'='*60}")
    print(f"  RESULTS: {label}")
    print(f"  {'='*60}")
    print(f"  {'品种':<10} {'持有':>4} {'胜率':>7} {'n':>6} {'Sharpe':>8} {'等级':>6}")
    print(f"  {'-'*45}")

    strong = [f for f in findings if f["win_rate"] >= 60.0]
    promising = [f for f in findings if 55.0 <= f["win_rate"] < 60.0]

    for f in sorted(findings, key=lambda x: -x["win_rate"]):
        wr = f["win_rate"]
        cnt = f["signal_count"]
        sharpe = f["sharpe_ratio"]
        label_star = "⭐" if wr >= 60.0 else ("💡" if wr >= 55.0 else "")
        if wr >= 55.0:
            print(f"  {label_star} {f['symbol']:<8} {f['hold_period']:>4} {wr:>6.1f}% {cnt:>6} {sharpe:>8.2f} {'A-' if wr>=60 else 'B+':>6}")

    return findings, strong, promising


def run_yearly_validation(entry_condition: str, direction: str, timeframe: str,
                          symbol: str, hold_period: int, label: str = "") -> Dict:
    """Run yearly split validation for a specific pattern."""
    print(f"\n{'='*60}")
    print(f"  📅 分年验证: {label}")
    print(f"  {symbol} {timeframe} {entry_condition} hold={hold_period}")
    print(f"{'='*60}")

    raw = load_data(timeframe=timeframe, symbols=[symbol])
    if not raw or symbol not in raw:
        return {"error": "No data"}
    df = raw[symbol]
    df = compute_indicators(df)
    df = add_candlestick_features(df)

    mask = df.eval(entry_condition)
    df["signal"] = mask.astype(int)
    signal_df = df[df["signal"] == 1].copy()
    signal_df["year"] = signal_df.index.year

    results = {}
    for year, grp in signal_df.groupby("year"):
        returns = []
        for idx in grp.index:
            pos = df.index.get_loc(idx)
            exit_pos = pos + hold_period
            if exit_pos >= len(df):
                continue
            entry_price = df.loc[idx, "close"]
            exit_price = df.iloc[exit_pos]["close"]
            if direction == "long":
                ret = (exit_price - entry_price) / entry_price
            else:
                ret = (entry_price - exit_price) / entry_price
            returns.append(ret)

        if len(returns) < 10:
            continue
        ret_arr = np.array(returns)
        wr = (ret_arr > 0).mean() * 100
        avg_ret = ret_arr.mean()
        std = ret_arr.std() if ret_arr.std() > 0 else 1e-10
        sharpe = (avg_ret / std) * np.sqrt(5000 / hold_period) if hold_period > 0 else 0
        results[int(year)] = {
            "n": len(returns),
            "win_rate": round(wr, 2),
            "avg_return": round(avg_ret, 6),
            "sharpe": round(sharpe, 2),
        }
        sig = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
        print(f"  {sig} {year}: WR={wr:.1f}% n={len(returns)} Sharpe={sharpe:.2f}")

    if results:
        years_ok = sum(1 for y in results.values() if y["win_rate"] >= 60)
        total_years = len(results)
        print(f"\n  📊 总览: {years_ok}/{total_years} 年 WR≥60%")
        if total_years > 0 and years_ok / total_years >= 0.7:
            print(f"  ✅ 结论: 策略鲁棒性通过! (>70%年份达标)")
        else:
            print(f"  ⚠️ 结论: 策略鲁棒性一般 (<70%年份达标)")

    return results


def run_atr_optimization(entry_condition: str, direction: str, timeframe: str,
                          symbol: str, label: str = "",
                          hold_period: int = 5,
                          atr_multipliers: List[float] = None) -> Dict:
    """Run ATR trailing stop optimization for a pattern."""
    if atr_multipliers is None:
        atr_multipliers = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]

    print(f"\n{'='*60}")
    print(f"  📐 ATR Trailing Stop优化: {label}")
    print(f"  {symbol} {timeframe} {entry_condition} hold={hold_period}")
    print(f"{'='*60}")

    raw = load_data(timeframe=timeframe, symbols=[symbol])
    if not raw or symbol not in raw:
        return {"error": "No data"}
    df = raw[symbol]
    df = compute_indicators(df)
    df = add_candlestick_features(df)

    mask = df.eval(entry_condition)
    df["signal"] = mask.astype(int)
    signal_indices = np.where(df["signal"].values)[0]

    results = {}
    for atr_mult in atr_multipliers:
        returns = []
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
                    stop_level = best_price - atr_stop
                    if df.iloc[j]["low"] <= stop_level:
                        exit_price = stop_level
                        break
                else:
                    best_price = min(best_price, df.iloc[j]["low"])
                    stop_level = best_price + atr_stop
                    if df.iloc[j]["high"] >= stop_level:
                        exit_price = stop_level
                        break

            if exit_price is None:
                exit_price = df.iloc[i + hold_period]["close"]

            if direction == "long":
                ret = (exit_price - entry_price) / entry_price
            else:
                ret = (entry_price - exit_price) / entry_price
            returns.append(ret)

        if len(returns) < 10:
            continue
        ret_arr = np.array(returns)
        wr = (ret_arr > 0).mean() * 100
        avg_ret = ret_arr.mean()
        std = ret_arr.std() if ret_arr.std() > 0 else 1e-10
        sharpe = (avg_ret / std) * np.sqrt(5000 / hold_period) if hold_period > 0 else 0

        results[atr_mult] = {
            "n": len(returns),
            "win_rate": round(wr, 2),
            "avg_return": round(avg_ret, 6),
            "sharpe": round(sharpe, 2),
        }
        sig = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
        print(f"  {sig} ATR x{atr_mult:.1f}: WR={wr:.1f}% n={len(returns)} Sharpe={sharpe:.2f}")

    return results


def run_market_regime_split(entry_condition: str, direction: str, timeframe: str,
                             symbol: str, hold_period: int, label: str = "") -> Dict:
    """Split validation by market regime (trend/choppy)."""
    print(f"\n{'='*60}")
    print(f"  🌊 市场状态分离: {label}")
    print(f"  {symbol} {timeframe} {entry_condition} hold={hold_period}")
    print(f"{'='*60}")

    raw = load_data(timeframe=timeframe, symbols=[symbol])
    if not raw or symbol not in raw:
        return {"error": "No data"}
    df = raw[symbol]
    df = compute_indicators(df)
    df = add_candlestick_features(df)

    mask = df.eval(entry_condition)
    df["signal"] = mask.astype(int)
    signal_df = df[df["signal"] == 1].copy()

    results = {}
    for regime, regime_label in [("trending", "趋势市"), ("choppy", "震荡市")]:
        if regime not in df.columns:
            print(f"  ⚠️ {regime} 列不存在，跳过")
            continue
        regime_signals = signal_df[signal_df[regime] == True]
        if len(regime_signals) < 10:
            print(f"  ⚠️ {regime_label} 信号不足: {len(regime_signals)}个")
            continue

        returns = []
        for idx in regime_signals.index:
            pos = df.index.get_loc(idx)
            exit_pos = pos + hold_period
            if exit_pos >= len(df):
                continue
            entry_price = df.loc[idx, "close"]
            exit_price = df.iloc[exit_pos]["close"]
            if direction == "long":
                ret = (exit_price - entry_price) / entry_price
            else:
                ret = (entry_price - exit_price) / entry_price
            returns.append(ret)

        ret_arr = np.array(returns)
        wr = (ret_arr > 0).mean() * 100
        avg_ret = ret_arr.mean()
        std = ret_arr.std() if ret_arr.std() > 0 else 1e-10
        sharpe = (avg_ret / std) * np.sqrt(5000 / hold_period) if hold_period > 0 else 0

        results[regime] = {
            "label": regime_label,
            "n": len(returns),
            "win_rate": round(wr, 2),
            "avg_return": round(avg_ret, 6),
            "sharpe": round(sharpe, 2),
        }
        sig = "✅" if wr >= 60 else ("⚠️" if wr >= 50 else "❌")
        print(f"  {sig} {regime_label}: WR={wr:.1f}% n={len(returns)} Sharpe={sharpe:.2f}")

    return results


def main():
    print("=" * 80)
    print("  🕯️  第23轮 K线形态研究 — 6个待办假设深度验证与扩展")
    print(f"  日期: {NOW_STR}")
    print(f"  品种池: {len(ALL_SYMBOLS)}个")
    print("=" * 80)

    all_strong = []
    all_promising = []
    yearly_results = {}
    atr_results = {}
    regime_results = {}

    # ═══════════════════════════════════════════════════════════════════════
    # H1: EURUSD Doji+RSI>75 H1 short hold=1-2 — 分年验证+Session过滤+ATR优化
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "█" * 80)
    print("  █ H1: EURUSD Doji+RSI>75 H1 short — 分年验证+Session过滤+ATR优化")
    print("█" * 80)

    # 基准测试 (各种RSI阈值对比)
    for rsi_thresh in [70, 72, 75, 78]:
        cond = f"doji and rsi14 > {rsi_thresh}"
        f, s, p = run_hypothesis(
            entry_condition=cond,
            direction="short",
            timeframe="H1",
            symbols=["EURUSD"],
            label=f"H1a: EURUSD Doji+RSI>{rsi_thresh} H1 → 做空",
            hold_periods=[1, 2, 3, 5, 7, 10, 12],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # Session分离 (Doji+RSI>75)
    for session_filter, label_suffix in [("", "全部"), ("session == 'asia'", "亚盘"),
                                          ("session == 'europe'", "欧盘"), ("session == 'us'", "美盘")]:
        cond = "doji and rsi14 > 75"
        if session_filter:
            cond = f"({cond}) and {session_filter}"
        f, s, p = run_hypothesis(
            entry_condition=cond,
            direction="short",
            timeframe="H1",
            symbols=["EURUSD"],
            label=f"H1b: EURUSD Doji+RSI>75 H1 {label_suffix} → 做空",
            hold_periods=[1, 2, 3, 5, 7, 10, 12],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # 分年验证 (hold=1,2,3)
    for hp in [1, 2, 3, 5]:
        yr = run_yearly_validation(
            entry_condition="doji and rsi14 > 75",
            direction="short",
            timeframe="H1",
            symbol="EURUSD",
            hold_period=hp,
            label=f"EURUSD Doji+RSI>75 hold={hp} 分年验证",
        )
        yearly_results[f"EURUSD_Doji75_h{hp}"] = yr

    # ATR优化 (hold=2 — Round22最佳)
    for hp in [1, 2, 3]:
        ar = run_atr_optimization(
            entry_condition="doji and rsi14 > 75",
            direction="short",
            timeframe="H1",
            symbol="EURUSD",
            hold_period=hp,
            label=f"EURUSD Doji+RSI>75 hold={hp} ATR优化",
            atr_multipliers=[0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
        )
        atr_results[f"EURUSD_Doji75_h{hp}_atr"] = ar

    # 市场状态分离
    rr = run_market_regime_split(
        entry_condition="doji and rsi14 > 75",
        direction="short",
        timeframe="H1",
        symbol="EURUSD",
        hold_period=2,
        label="EURUSD Doji+RSI>75 趋势/震荡分离 hold=2",
    )
    regime_results["EURUSD_Doji75_h2"] = rr

    # ═══════════════════════════════════════════════════════════════════════
    # H2: UKOIL Evening Star+RSI>60 M30 short hold=18 — 分年验证+美盘对比
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "█" * 80)
    print("  █ H2: UKOIL Evening Star+RSI>60 M30 short — 分年验证+美盘对比")
    print("█" * 80)

    # 所有Session的hold=18验证
    for session_filter, label_suffix in [("", "全部"), ("session == 'europe'", "欧盘"),
                                          ("session == 'us'", "美盘"), ("session == 'asia'", "亚盘")]:
        cond = "evening_star and rsi14 > 60"
        if session_filter:
            cond = f"({cond}) and {session_filter}"
        f, s, p = run_hypothesis(
            entry_condition=cond,
            direction="short",
            timeframe="M30",
            symbols=["UKOIL"],
            label=f"H2a: UKOIL Evening Star+RSI>60 M30 {label_suffix} → 做空 (hold=18焦点)",
            hold_periods=[12, 15, 18, 20, 24, 30, 36],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # 分年验证 (hold=18)
    yr = run_yearly_validation(
        entry_condition="evening_star and rsi14 > 60",
        direction="short",
        timeframe="M30",
        symbol="UKOIL",
        hold_period=18,
        label="UKOIL Evening Star+RSI>60 hold=18 分年验证",
    )
    yearly_results["UKOIL_ES_R60_h18"] = yr

    # 欧盘hold=18 分年验证
    yr = run_yearly_validation(
        entry_condition="(evening_star and rsi14 > 60) and session == 'europe'",
        direction="short",
        timeframe="M30",
        symbol="UKOIL",
        hold_period=18,
        label="UKOIL Evening Star+RSI>60 欧盘 hold=18 分年验证",
    )
    yearly_results["UKOIL_ES_R60_EU_h18"] = yr

    # 美盘对比 (分年验证)
    yr = run_yearly_validation(
        entry_condition="(evening_star and rsi14 > 60) and session == 'us'",
        direction="short",
        timeframe="M30",
        symbol="UKOIL",
        hold_period=18,
        label="UKOIL Evening Star+RSI>60 美盘 hold=18 分年验证",
    )
    yearly_results["UKOIL_ES_R60_US_h18"] = yr

    # ═══════════════════════════════════════════════════════════════════════
    # H3: XCUUSD Inside Bar+RSI>70 H1 short — 亚盘Session深度测试
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "█" * 80)
    print("  █ H3: XCUUSD Inside Bar+RSI>70 H1 short — 亚盘Session深度测试")
    print("█" * 80)

    # RSI阈值对比 (65, 70, 75)
    for rsi_thresh in [65, 70, 75]:
        cond = f"inside_bar and rsi14 > {rsi_thresh}"
        f, s, p = run_hypothesis(
            entry_condition=cond,
            direction="short",
            timeframe="H1",
            symbols=["XCUUSD"],
            label=f"H3a: XCUUSD Inside Bar+RSI>{rsi_thresh} H1 → 做空 (深度hold)",
            hold_periods=[1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 48],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # 亚盘Session深度测试 (RSI>70)
    for session_filter, label_suffix in [("session == 'asia'", "亚盘"),
                                          ("session == 'europe'", "欧盘"),
                                          ("session == 'us'", "美盘")]:
        cond = f"(inside_bar and rsi14 > 70) and {session_filter}"
        f, s, p = run_hypothesis(
            entry_condition=cond,
            direction="short",
            timeframe="H1",
            symbols=["XCUUSD"],
            label=f"H3b: XCUUSD Inside Bar+RSI>70 H1 {label_suffix} → 做空",
            hold_periods=[1, 2, 3, 5, 7, 10, 12, 15, 20, 24, 30, 48],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # 分年验证 (RSI>70, hold=24)
    yr = run_yearly_validation(
        entry_condition="inside_bar and rsi14 > 70",
        direction="short",
        timeframe="H1",
        symbol="XCUUSD",
        hold_period=24,
        label="XCUUSD Inside Bar+RSI>70 hold=24 分年验证",
    )
    yearly_results["XCUUSD_IB_R70_h24"] = yr

    # 亚盘分年验证
    yr = run_yearly_validation(
        entry_condition="(inside_bar and rsi14 > 70) and session == 'asia'",
        direction="short",
        timeframe="H1",
        symbol="XCUUSD",
        hold_period=7,
        label="XCUUSD Inside Bar+RSI>70 亚盘 hold=7 分年验证",
    )
    yearly_results["XCUUSD_IB_R70_ASIA_h7"] = yr

    # ═══════════════════════════════════════════════════════════════════════
    # H4: HK50 Three Black Crows+RSI>65+趋势过滤 H1 short
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "█" * 80)
    print("  █ H4: HK50 Three Black Crows+RSI>65+趋势过滤 H1 short — 解决退化")
    print("█" * 80)

    # 基准 (无过滤)
    f, s, p = run_hypothesis(
        entry_condition="three_black_crows and rsi14 > 65",
        direction="short",
        timeframe="H1",
        symbols=["HK50"],
        label="H4a: HK50 Three Black Crows+RSI>65 H1 → 做空 (基准)",
        hold_periods=[1, 2, 3, 5, 7, 10, 12, 15, 20],
    )
    all_strong.extend(s)
    all_promising.extend(p)

    # 趋势过滤: price < ma200 (下跌趋势确认)
    for trend_filter, trend_label in [
        ("close < ma200", "价格<MA200(下跌趋势)"),
        ("close < ma100", "价格<MA100(中短期下跌)"),
        ("close < ma50", "价格<MA50(短期下跌)"),
        ("close < ma200 and ma50 < ma200", "MA50<MA200(熊市排列)"),
        ("close < ma50 and rsi14 > 65", "价格<MA50+RSI>65(短期下跌过度)"),
    ]:
        cond = f"(three_black_crows and rsi14 > 65) and ({trend_filter})"
        f, s, p = run_hypothesis(
            entry_condition=cond,
            direction="short",
            timeframe="H1",
            symbols=["HK50"],
            label=f"H4b: HK50 3BC+RSI>65+{trend_label} H1 → 做空",
            hold_periods=[1, 2, 3, 5, 7, 10, 12],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # 分年验证 (best trend filter: close < ma200, hold=5)
    for tf_label, trend_filter in [("close<ma200", "close < ma200"),
                                    ("close<ma100", "close < ma100")]:
        cond = f"(three_black_crows and rsi14 > 65) and ({trend_filter})"
        yr = run_yearly_validation(
            entry_condition=cond,
            direction="short",
            timeframe="H1",
            symbol="HK50",
            hold_period=5,
            label=f"HK50 3BC+RSI>65+{tf_label} hold=5 分年验证",
        )
        yearly_results[f"HK50_3BC_{tf_label}_h5"] = yr

    # 市场状态分离 (原始策略 vs 趋势过滤后)
    rr = run_market_regime_split(
        entry_condition="three_black_crows and rsi14 > 65",
        direction="short",
        timeframe="H1",
        symbol="HK50",
        hold_period=5,
        label="HK50 3BC+RSI>65 趋势/震荡分离 hold=5",
    )
    regime_results["HK50_3BC_h5"] = rr

    # ═══════════════════════════════════════════════════════════════════════
    # H5: AUDUSD Doji+RSI>75 H1 short ATR x2.5 hold=3 — 分年验证+扩展
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "█" * 80)
    print("  █ H5: AUDUSD Doji+RSI>75 H1 short ATR x2.5 — 分年验证+扩展")
    print("█" * 80)

    # AUDUSD基准
    f, s, p = run_hypothesis(
        entry_condition="doji and rsi14 > 75",
        direction="short",
        timeframe="H1",
        symbols=["AUDUSD"],
        label="H5a: AUDUSD Doji+RSI>75 H1 → 做空 (基准hold=1-12)",
        hold_periods=[1, 2, 3, 5, 7, 10, 12],
    )
    all_strong.extend(s)
    all_promising.extend(p)

    # 分年验证 (hold=3 最佳ATR参数)
    for hp in [3, 5, 7]:
        yr = run_yearly_validation(
            entry_condition="doji and rsi14 > 75",
            direction="short",
            timeframe="H1",
            symbol="AUDUSD",
            hold_period=hp,
            label=f"AUDUSD Doji+RSI>75 hold={hp} 分年验证",
        )
        yearly_results[f"AUDUSD_Doji75_h{hp}"] = yr

    # ATR优化hold=3深度测试 (扩展ATR范围)
    ar = run_atr_optimization(
        entry_condition="doji and rsi14 > 75",
        direction="short",
        timeframe="H1",
        symbol="AUDUSD",
        hold_period=3,
        label="AUDUSD Doji+RSI>75 hold=3 ATR深度优化",
        atr_multipliers=[1.5, 2.0, 2.2, 2.5, 2.8, 3.0, 3.5, 4.0, 5.0],
    )
    atr_results["AUDUSD_Doji75_h3_atr"] = ar

    # 扩展至NZDUSD (同类型商品货币)
    for session_filter, label_suffix in [("", "全部"), ("session == 'asia'", "亚盘"),
                                          ("session == 'europe'", "欧盘")]:
        cond = "doji and rsi14 > 75"
        if session_filter:
            cond = f"({cond}) and {session_filter}"
        f, s, p = run_hypothesis(
            entry_condition=cond,
            direction="short",
            timeframe="H1",
            symbols=["NZDUSD"],
            label=f"H5b: NZDUSD Doji+RSI>75 H1 {label_suffix} → 做空 (扩展验证)",
            hold_periods=[1, 2, 3, 5, 7, 10, 12],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # ═══════════════════════════════════════════════════════════════════════
    # H6: 全品种 Doji+RSI极端值做空扫描 H1
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "█" * 80)
    print("  █ H6: 全品种 Doji+RSI极端值做空扫描 H1")
    print("█" * 80)

    # 全品种扫描: Doji+RSI>75做空
    for rsi_thresh in [72, 75, 78]:
        cond = f"doji and rsi14 > {rsi_thresh}"
        f, s, p = run_hypothesis(
            entry_condition=cond,
            direction="short",
            timeframe="H1",
            symbols=ALL_SYMBOLS,
            label=f"H6a: 全品种 Doji+RSI>{rsi_thresh} H1 → 做空 (全品种扫描)",
            hold_periods=[1, 2, 3, 5, 7, 10, 12],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # Doji+RSI>78 各Session全品种扫描
    for session_filter, label_suffix in [("", "全部"), ("session == 'us'", "美盘"),
                                          ("session == 'europe'", "欧盘")]:
        cond = "doji and rsi14 > 78"
        if session_filter:
            cond = f"({cond}) and {session_filter}"
        f, s, p = run_hypothesis(
            entry_condition=cond,
            direction="short",
            timeframe="H1",
            symbols=ALL_SYMBOLS,
            label=f"H6b: 全品种 Doji+RSI>78 H1 {label_suffix} → 做空",
            hold_periods=[1, 2, 3, 5, 7, 10, 12],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # ═══════════════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n\n{'='*80}")
    print(f"  📊 ROUND 23 SUMMARY — ALL FINDINGS (n>=30)")
    print(f"{'='*80}")

    # Deduplicate
    seen = set()
    all_findings_dedup = []
    for f in all_strong + all_promising:
        key = (f["symbol"], f["timeframe"], f["entry_condition"], f["hold_period"])
        if key not in seen:
            seen.add(key)
            all_findings_dedup.append(f)

    print(f"\n| {'品种':<10} | {'TF':<4} | {'方向':<4} | {'持有':<5} | {'胜率':<7} | {'n':<6} | {'Sharpe':<8} | {'条件'}")
    print(f"|{'' :->10}|{'' :->4}|{'' :->4}|{'' :->5}|{'' :->7}|{'' :->6}|{'' :->8}|{'' :->50}")

    for f in sorted(all_findings_dedup, key=lambda x: -x["win_rate"]):
        wr = f["win_rate"]
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        label = "⭐" if wr >= 60.0 else ("💡" if wr >= 55.0 else "")
        if wr >= 55.0:
            cond_short = f["entry_condition"][:50]
            print(f"| {label} {f['symbol']:<7} | {f['timeframe']:<4} | {dir_cn:<4} | {f['hold_period']:<5} | {wr:>5.1f}% | {f['signal_count']:<6} | {f['sharpe_ratio']:<8.2f} | {cond_short}")

    print(f"\n{'='*80}")
    strong_unique = [f for f in all_findings_dedup if f["win_rate"] >= 60.0]
    promising_unique = [f for f in all_findings_dedup if 55.0 <= f["win_rate"] < 60.0]
    print(f"  强信号 (WR>=60%, n>=30): {len(strong_unique)}")
    for f in sorted(strong_unique, key=lambda x: -x["win_rate"]):
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        print(f"    ⭐ {f['symbol']:10s} {f['timeframe']:4s} {dir_cn:4s} "
              f"hold={f['hold_period']:3d}  WR={f['win_rate']:5.1f}%  "
              f"n={f['signal_count']:5d}  Sharpe={f['sharpe_ratio']:7.2f}")

    print(f"\n  潜力信号 (55%<=WR<60%, n>=30): {len(promising_unique)}")
    for f in sorted(promising_unique, key=lambda x: -x["win_rate"]):
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        print(f"    💡 {f['symbol']:10s} {f['timeframe']:4s} {dir_cn:4s} "
              f"hold={f['hold_period']:3d}  WR={f['win_rate']:5.1f}%  "
              f"n={f['signal_count']:5d}  Sharpe={f['sharpe_ratio']:7.2f}")

    # ─── Save results ───
    output = {
        "round": 23,
        "date": NOW_STR,
        "timeframes": ["H1", "M30"],
        "symbols": ALL_SYMBOLS,
        "all_findings": all_findings_dedup,
        "strong_findings": strong_unique,
        "promising_findings": promising_unique,
        "yearly_validations": yearly_results,
        "atr_optimizations": atr_results,
        "regime_validations": regime_results,
    }

    results_path = os.path.join(PROJECT_DIR, "data", "round23_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 结果已保存: {results_path}")

    return output


if __name__ == "__main__":
    results = main()
