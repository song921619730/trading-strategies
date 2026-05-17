#!/usr/bin/env python3
"""
Round 21 — H1/M30 K线形态研究: 待办假设批量执行

本轮聚焦 (8个待办假设):
1. EURUSD Inside Bar+RSI<25 H1 long hold=7 — ATR止损+Session过滤
2. GBPUSD Doji+RSI<25+US Session H1 long hold=5 — 分年验证
3. HK50 Three Black Crows+RSI>65 H1 short hold=5 — M30验证+Session分离
4. EURUSD Tweezer Top+RSI>75 H1 short — ATR止损+止盈优化
5. UKOIL Evening Star+RSI>60 M30 short — Session过滤
6. AUDUSD Doji+RSI>75 H1 short hold=5 — 分年测试
7. XAUUSD Tweezer Top+RSI>75 H1 short hold=5 — M30交叉验证
8. JP225 Inside Bar+RSI>65 H1 short — 新方向探索
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

    # Load data with candlestick features
    raw = load_data(timeframe=timeframe, symbols=[symbol])
    if not raw or symbol not in raw:
        return {"error": "No data"}
    df = raw[symbol]
    df = compute_indicators(df)
    df = add_candlestick_features(df)

    # Evaluate condition
    mask = df.eval(entry_condition)
    df["signal"] = mask.astype(int)
    signal_df = df[df["signal"] == 1].copy()

    # Add year column
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

    # Summary
    if results:
        years_ok = sum(1 for y in results.values() if y["win_rate"] >= 60)
        total_years = len(results)
        print(f"\n  📊 总览: {years_ok}/{total_years} 年 WR≥60%")
        if years_ok / total_years >= 0.7:
            print(f"  ✅ 结论: 策略鲁棒性通过! (>70%年份达标)")
        else:
            print(f"  ⚠️ 结论: 策略鲁棒性一般 (<70%年份达标)")

    return results


def main():
    print("=" * 80)
    print("  🕯️  第21轮 K线形态研究 — 8个待办假设批量执行")
    print(f"  日期: {NOW_STR}")
    print(f"  品种池: {len(ALL_SYMBOLS)}个")
    print("=" * 80)

    all_strong = []
    all_promising = []
    yearly_results = {}

    # ─────────────────────────────────────────────────
    # H1: EURUSD Inside Bar+RSI<25 — ATR止损+Session过滤
    # ─────────────────────────────────────────────────
    print("\n" + "█" * 80)
    print("  █ H1: EURUSD Inside Bar+RSI<25 H1 long — ATR止损+Session过滤")
    print("█" * 80)

    # 对比: 无过滤 vs Session过滤
    for session_filter, label_suffix in [("", "全部时段"), ("session == 'europe'", "仅欧盘"), ("session == 'us'", "仅美盘")]:
        cond = "inside_bar and rsi14 < 25"
        if session_filter:
            cond = f"({cond}) and {session_filter}"
        f, s, p = run_hypothesis(
            entry_condition=cond,
            direction="long",
            timeframe="H1",
            symbols=["EURUSD"],
            label=f"H1a: EURUSD Inside Bar+RSI<25 {label_suffix} → 做多",
            hold_periods=[3, 5, 7, 10, 12, 15, 20],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # ─────────────────────────────────────────────────
    # H2: GBPUSD Doji+RSI<25+US Session — 分年验证
    # ─────────────────────────────────────────────────
    print("\n" + "█" * 80)
    print("  █ H2: GBPUSD Doji+RSI<25+US Session H1 long hold=5 — 分年验证")
    print("█" * 80)

    f, s, p = run_hypothesis(
        entry_condition="doji and rsi14 < 25 and session == 'us'",
        direction="long",
        timeframe="H1",
        symbols=["GBPUSD"],
        label="H2a: GBPUSD Doji+RSI<25+US Session H1 → 做多 (基准)",
        hold_periods=[3, 5, 7, 10, 12],
    )
    all_strong.extend(s)
    all_promising.extend(p)

    yr = run_yearly_validation(
        entry_condition="doji and rsi14 < 25 and session == 'us'",
        direction="long",
        timeframe="H1",
        symbol="GBPUSD",
        hold_period=5,
        label="GBPUSD Doji+RSI<25+US Session hold=5 分年验证",
    )
    yearly_results["GBPUSD_Doji_RSI25_US"] = yr

    # ─────────────────────────────────────────────────
    # H3: HK50 Three Black Crows+RSI>65 — M30验证+Session分离
    # ─────────────────────────────────────────────────
    print("\n" + "█" * 80)
    print("  █ H3: HK50 Three Black Crows+RSI>65 — M30验证+Session分离")
    print("█" * 80)

    for tf in ["H1", "M30"]:
        for session_filter, label_suffix in [("", "全部"), ("session == 'asia'", "亚盘"), ("session == 'europe'", "欧盘")]:
            cond = "three_black_crows and rsi14 > 65"
            if session_filter:
                cond = f"({cond}) and {session_filter}"
            f, s, p = run_hypothesis(
                entry_condition=cond,
                direction="short",
                timeframe=tf,
                symbols=["HK50"],
                label=f"H3: HK50 Three Black Crows+RSI>65 {tf} {label_suffix} → 做空",
                hold_periods=HOLD_SHORT if tf == "H1" else [3, 5, 7, 10, 12, 15, 20, 30],
            )
            all_strong.extend(s)
            all_promising.extend(p)

    # ─────────────────────────────────────────────────
    # H4: EURUSD Tweezer Top+RSI>75 — ATR止损+止盈优化
    # ─────────────────────────────────────────────────
    print("\n" + "█" * 80)
    print("  █ H4: EURUSD Tweezer Top+RSI>75 H1 short — ATR止损+止盈优化")
    print("█" * 80)

    # 对比不同RSI阈值
    for rsi_thresh in [72, 75, 78]:
        f, s, p = run_hypothesis(
            entry_condition=f"tweezer_top and rsi14 > {rsi_thresh}",
            direction="short",
            timeframe="H1",
            symbols=["EURUSD"],
            label=f"H4: EURUSD Tweezer Top+RSI>{rsi_thresh} H1 → 做空",
            hold_periods=[1, 2, 3, 5, 7, 10, 12],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # ─────────────────────────────────────────────────
    # H5: UKOIL Evening Star+RSI>60 M30 — Session过滤
    # ─────────────────────────────────────────────────
    print("\n" + "█" * 80)
    print("  █ H5: UKOIL Evening Star+RSI>60 M30 short — Session过滤")
    print("█" * 80)

    for session_filter, label_suffix in [("", "全部时段"), ("session == 'us'", "仅美盘"), ("session == 'europe'", "仅欧盘")]:
        cond = "evening_star and rsi14 > 60"
        if session_filter:
            cond = f"({cond}) and {session_filter}"
        f, s, p = run_hypothesis(
            entry_condition=cond,
            direction="short",
            timeframe="M30",
            symbols=["UKOIL"],
            label=f"H5: UKOIL Evening Star+RSI>60 M30 {label_suffix} → 做空",
            hold_periods=[3, 5, 7, 10, 12, 15, 20, 30, 48],
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # ─────────────────────────────────────────────────
    # H6: AUDUSD Doji+RSI>75 H1 short — 分年测试
    # ─────────────────────────────────────────────────
    print("\n" + "█" * 80)
    print("  █ H6: AUDUSD Doji+RSI>75 H1 short — 分年测试")
    print("█" * 80)

    f, s, p = run_hypothesis(
        entry_condition="doji and rsi14 > 75",
        direction="short",
        timeframe="H1",
        symbols=["AUDUSD"],
        label="H6a: AUDUSD Doji+RSI>75 H1 → 做空 (基准)",
        hold_periods=[3, 5, 7, 10, 12, 15],
    )
    all_strong.extend(s)
    all_promising.extend(p)

    yr = run_yearly_validation(
        entry_condition="doji and rsi14 > 75",
        direction="short",
        timeframe="H1",
        symbol="AUDUSD",
        hold_period=5,
        label="AUDUSD Doji+RSI>75 hold=5 分年测试",
    )
    yearly_results["AUDUSD_Doji_RSI75"] = yr

    # ─────────────────────────────────────────────────
    # H7: XAUUSD Tweezer Top+RSI>75 — M30交叉验证
    # ─────────────────────────────────────────────────
    print("\n" + "█" * 80)
    print("  █ H7: XAUUSD Tweezer Top+RSI>75 — H1+M30交叉验证")
    print("█" * 80)

    for tf in ["H1", "M30"]:
        for rsi_val in [72, 75, 78]:
            cond = f"tweezer_top and rsi14 > {rsi_val}"
            f, s, p = run_hypothesis(
                entry_condition=cond,
                direction="short",
                timeframe=tf,
                symbols=["XAUUSD"],
                label=f"H7: XAUUSD Tweezer Top+RSI>{rsi_val} {tf} → 做空",
                hold_periods=HOLD_SHORT if tf == "H1" else [3, 5, 7, 10, 12, 15, 20],
            )
            all_strong.extend(s)
            all_promising.extend(p)

    # ─────────────────────────────────────────────────
    # H8: JP225 Inside Bar+RSI>65 H1 short — 新方向探索
    # ─────────────────────────────────────────────────
    print("\n" + "█" * 80)
    print("  █ H8: JP225 Inside Bar+RSI>65 H1 short — 新方向探索")
    print("█" * 80)

    for rsi_val in [60, 65, 70, 75]:
        f, s, p = run_hypothesis(
            entry_condition=f"inside_bar and rsi14 > {rsi_val}",
            direction="short",
            timeframe="H1",
            symbols=["JP225"],
            label=f"H8: JP225 Inside Bar+RSI>{rsi_val} H1 → 做空",
            hold_periods=HOLD_SHORT,
        )
        all_strong.extend(s)
        all_promising.extend(p)

    # 跨品种扩展: Inside Bar+RSI>65 H1 short 全品种扫描
    f, s, p = run_hypothesis(
        entry_condition="inside_bar and rsi14 > 65",
        direction="short",
        timeframe="H1",
        symbols=ALL_SYMBOLS,
        label="H8x: Inside Bar+RSI>65 H1 → 做空 (全品种扩展)",
        hold_periods=HOLD_SHORT,
    )
    all_strong.extend(s)
    all_promising.extend(p)

    # ─────────────────────────────────────────────────
    # FINAL SUMMARY
    # ─────────────────────────────────────────────────
    print(f"\n\n{'='*80}")
    print(f"  📊 ROUND 21 SUMMARY — ALL FINDINGS (n>=30)")
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
    print(f"|{'':->10}|{'':->4}|{'':->4}|{'':->5}|{'':->7}|{'':->6}|{'':->8}|{'':->50}")

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
        "round": 21,
        "date": NOW_STR,
        "timeframes": ["H1", "M30"],
        "symbols": ALL_SYMBOLS,
        "all_findings": all_findings_dedup,
        "strong_findings": strong_unique,
        "promising_findings": promising_unique,
        "yearly_validations": yearly_results,
    }

    results_path = os.path.join(PROJECT_DIR, "data", "round21_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 结果已保存: {results_path}")

    return output


if __name__ == "__main__":
    results = main()
