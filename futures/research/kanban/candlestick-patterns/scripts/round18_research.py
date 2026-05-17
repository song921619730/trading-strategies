#!/usr/bin/env python3
"""
Round 18 — H1/M30 K线形态研究循环

本轮聚焦:
1. M30 复合做多全品种扫描 (engulfing_bull OR hammer OR pin_bar) + RSI<40 + EU/US
2. M30 复合做空全品种扫描 (engulfing_bear OR evening_star OR shooting_star) + RSI>60 + US
3. Inside Bar + RSI 极端值 = 反转策略 (H1全品种)
4. Doji + RSI极端值 → 反转 (H1全品种)
5. Three Black Crows + RSI>65 (阈值优化) → 做空 (H1全品种)
"""

import sys
import os
import json
from datetime import datetime
from typing import Any, Dict, List

# ── Paths ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "futures-intraday", "scripts"
))

from run_candlestick import run_pattern_test, list_available_symbols
from candlestick_features import list_available_patterns

# ─── Config ───
ALL_SYMBOLS = list_available_symbols("H1")
HOLD_PERIODS = [1, 2, 3, 5, 7, 10, 12, 15, 20, 30]

def run_hypothesis(
    entry_condition: str,
    direction: str,
    timeframe: str,
    symbols: list = None,
    label: str = "",
) -> List[Dict[str, Any]]:
    """Run a hypothesis and return structured findings."""
    print(f"\n{'='*80}")
    print(f"  🔬 {label}")
    print(f"  Condition: {entry_condition}")
    print(f"  Direction: {direction} | TF: {timeframe}")
    print(f"  Symbols: {len(symbols or ALL_SYMBOLS)}")
    print(f"{'='*80}")

    if symbols is None:
        symbols = ALL_SYMBOLS

    results = run_pattern_test(
        entry_condition=entry_condition,
        direction=direction,
        timeframe=timeframe,
        symbols=symbols,
        hold_periods=HOLD_PERIODS,
        verbose=False,
    )

    # Extract findings
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

    # Print summary table
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

    results["_meta"] = meta
    return findings, strong, promising


def main():
    print("=" * 80)
    print("  🕯️  第18轮 K线形态研究 — H1/M30 K线形态研究循环")
    print(f"  日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  品种: {len(ALL_SYMBOLS)}个")
    print("=" * 80)

    all_findings = []
    all_strong = []
    all_promising = []

    # ──────────────────────────────────────────
    # 假设 1: M30 复合做多全品种扫描
    # ──────────────────────────────────────────
    findings, strong, promising = run_hypothesis(
        entry_condition="(engulfing_bull or hammer or pin_bar) and rsi14 < 40 and ((session == 'europe') or (session == 'us'))",
        direction="long",
        timeframe="M30",
        label="H1: M30 复合做多 (engulfing_bull/hammer/pin_bar) + RSI<40 + EU/US → 做多",
    )
    all_findings.extend(findings)
    all_strong.extend(strong)
    all_promising.extend(promising)

    # ──────────────────────────────────────────
    # 假设 2: M30 复合做空全品种扫描
    # ──────────────────────────────────────────
    findings, strong, promising = run_hypothesis(
        entry_condition="(engulfing_bear or evening_star or shooting_star) and rsi14 > 60 and session == 'us'",
        direction="short",
        timeframe="M30",
        label="H2: M30 复合做空 (engulfing_bear/evening_star/shooting_star) + RSI>60 + US → 做空",
    )
    all_findings.extend(findings)
    all_strong.extend(strong)
    all_promising.extend(promising)

    # ──────────────────────────────────────────
    # 假设 3: Inside Bar + RSI<25 → 做多 (H1)
    # ──────────────────────────────────────────
    findings, strong, promising = run_hypothesis(
        entry_condition="inside_bar and rsi14 < 25",
        direction="long",
        timeframe="H1",
        label="H3: Inside Bar + RSI<25 → 做多 (H1 超卖反转)",
    )
    all_findings.extend(findings)
    all_strong.extend(strong)
    all_promising.extend(promising)

    # ──────────────────────────────────────────
    # 假设 4: Inside Bar + RSI>75 → 做空 (H1)
    # ──────────────────────────────────────────
    findings, strong, promising = run_hypothesis(
        entry_condition="inside_bar and rsi14 > 75",
        direction="short",
        timeframe="H1",
        label="H4: Inside Bar + RSI>75 → 做空 (H1 超买反转)",
    )
    all_findings.extend(findings)
    all_strong.extend(strong)
    all_promising.extend(promising)

    # ──────────────────────────────────────────
    # 假设 5: Doji + RSI<25 → 做多 (H1)
    # ──────────────────────────────────────────
    findings, strong, promising = run_hypothesis(
        entry_condition="doji and rsi14 < 25",
        direction="long",
        timeframe="H1",
        label="H5: Doji + RSI<25 → 做多 (H1 超卖Doji反转)",
    )
    all_findings.extend(findings)
    all_strong.extend(strong)
    all_promising.extend(promising)

    # ──────────────────────────────────────────
    # 假设 6: Doji + RSI>75 → 做空 (H1)
    # ──────────────────────────────────────────
    findings, strong, promising = run_hypothesis(
        entry_condition="doji and rsi14 > 75",
        direction="short",
        timeframe="H1",
        label="H6: Doji + RSI>75 → 做空 (H1 超买Doji反转)",
    )
    all_findings.extend(findings)
    all_strong.extend(strong)
    all_promising.extend(promising)

    # ──────────────────────────────────────────
    # 假设 7: Three Black Crows + RSI>65 → 做空 (H1)
    # ──────────────────────────────────────────
    findings, strong, promising = run_hypothesis(
        entry_condition="three_black_crows and rsi14 > 65",
        direction="short",
        timeframe="H1",
        label="H7: Three Black Crows + RSI>65 → 做空 (H1 三只乌鸦+超买)",
    )
    all_findings.extend(findings)
    all_strong.extend(strong)
    all_promising.extend(promising)

    # ─── Summary ───
    print(f"\n\n{'='*80}")
    print(f"  📊 ROUND 18 SUMMARY — ALL FINDINGS (n>=30)")
    print(f"{'='*80}")
    print(f"\n| {'品种':<10} | {'TF':<4} | {'方向':<4} | {'持有':<5} | {'胜率':<7} | {'n':<6} | {'Sharpe':<8} | {'条件'}")
    print(f"|{'':->10}|{'':->4}|{'':->4}|{'':->5}|{'':->7}|{'':->6}|{'':->8}|{'':->50}")

    for f in sorted(all_findings, key=lambda x: -x["win_rate"]):
        wr = f["win_rate"]
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        label = "⭐" if wr >= 60.0 else ("💡" if wr >= 55.0 else "")
        if wr >= 55.0:
            cond_short = f["entry_condition"][:50]
            print(f"| {label} {f['symbol']:<7} | {f['timeframe']:<4} | {dir_cn:<4} | {f['hold_period']:<5} | {wr:>5.1f}% | {f['signal_count']:<6} | {f['sharpe_ratio']:<8.2f} | {cond_short}")

    print(f"\n{'='*80}")
    print(f"  强信号 (WR>=60%, n>=30): {len(all_strong)}")
    for f in sorted(all_strong, key=lambda x: -x["win_rate"]):
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        print(f"    ⭐ {f['symbol']:10s} {f['timeframe']:4s} {dir_cn:4s} "
              f"hold={f['hold_period']:3d}  WR={f['win_rate']:5.1f}%  "
              f"n={f['signal_count']:5d}  Sharpe={f['sharpe_ratio']:7.2f}")

    print(f"\n  潜力信号 (55%<=WR<60%, n>=30): {len(all_promising)}")
    for f in sorted(all_promising, key=lambda x: -x["win_rate"]):
        dir_cn = "做多" if f["direction"] == "long" else "做空"
        print(f"    💡 {f['symbol']:10s} {f['timeframe']:4s} {dir_cn:4s} "
              f"hold={f['hold_period']:3d}  WR={f['win_rate']:5.1f}%  "
              f"n={f['signal_count']:5d}  Sharpe={f['sharpe_ratio']:7.2f}")

    # ─── Save results ───
    output = {
        "round": 18,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "timeframes": ["H1", "M30"],
        "symbols": ALL_SYMBOLS,
        "all_findings": all_findings,
        "strong_findings": all_strong,
        "promising_findings": all_promising,
    }

    results_path = os.path.join(SCRIPT_DIR, "..", "data", "round18_results.json")
    with open(results_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 结果已保存: {results_path}")

    return all_findings, all_strong, all_promising


if __name__ == "__main__":
    findings, strong, promising = main()
