#!/usr/bin/env python3
"""
round25_a02: US30 H1 美盘+RSI<40+ATR阈值梯度扫描尝试突破60%

Phase 1: ATR阈值梯度(0.25%/0.30%/0.35%/0.40%) × 持有期(3,5,7,10,12,15,20) = 28组
Phase 2: 最优参数跨14品种验证
"""
import json
import logging
import sys
from pathlib import Path
from pprint import pformat

import numpy as np

from grid_engine import run_grid

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("round25_a02")

# ==========================================================================
# Phase 1: ATR梯度扫描 (US30 only)
# ==========================================================================
ATR_THRESHOLDS = [0.0025, 0.0030, 0.0035, 0.0040]
HOLD_PERIODS = [3, 5, 7, 10, 12, 15, 20]
SYMBOLS = ["US30"]

print("=" * 80)
print("  Phase 1: ATR Threshold Gradient Scan on US30 H1")
print("  Entry: session == 'us' and rsi14 < 40 and atr14/close > [threshold]")
print("  Direction: long")
print(f"  ATR Thresholds: {ATR_THRESHOLDS}")
print(f"  Hold Periods:   {HOLD_PERIODS}")
print("=" * 80)

all_phase1_results = {}

for atr_t in ATR_THRESHOLDS:
    entry_cond = f"session == 'us' and rsi14 < 40 and atr14 / close > {atr_t}"
    config = {
        "timeframe": "H1",
        "symbols": SYMBOLS.copy(),
        "entry_condition": entry_cond,
        "direction": "long",
        "hold_periods": HOLD_PERIODS.copy(),
        "exit_at_close": True,
    }
    results = run_grid(config)
    meta = results.pop("_meta", {})
    all_phase1_results[atr_t] = results

    print(f"\n{'─'*80}")
    print(f"  ATR > {atr_t}  (={atr_t*100:.2f}%)")
    print(f"{'─'*80}")
    print(f"  {'Symbol':<8} {'Hold':>5} {'n':>6} {'WinRate':>8} {'AvgRet':>10} {'Sharpe':>8} {'MaxDD':>8}")
    print(f"  {'─'*8} {'─'*5} {'─'*6} {'─'*8} {'─'*10} {'─'*8} {'─'*8}")
    for sym, sym_res in sorted(results.items()):
        for hp in sorted(sym_res.keys(), key=int):
            s = sym_res[hp]
            cnt = s.get("signal_count", 0)
            if cnt == 0:
                continue
            wr = s.get("win_rate", 0) or 0
            avg = s.get("avg_return", 0) or 0
            sharpe = s.get("sharpe_ratio", 0) or 0
            dd = s.get("max_drawdown", 0) or 0
            print(f"  {sym:<8} {hp:>5} {cnt:>6} {wr:>7.2%} {avg:>+9.5f} {sharpe:>7.2f} {dd:>7.4f}")

# ==========================================================================
# Find best parameter
# ==========================================================================
print("\n\n" + "=" * 80)
print("  Identifying Optimal Parameters...")
print("=" * 80)

best_wr = 0
best_params = None
best_stats = None

for atr_t, results in all_phase1_results.items():
    for sym, sym_res in results.items():
        for hp in sorted(sym_res.keys(), key=int):
            s = sym_res[hp]
            cnt = s.get("signal_count", 0)
            wr = s.get("win_rate", 0) or 0
            if cnt >= 50 and wr > best_wr:
                best_wr = wr
                best_params = (atr_t, hp)
                best_stats = s
                best_stats["atr_threshold"] = atr_t
                best_stats["hold_period"] = hp

if best_params:
    atr_opt, hp_opt = best_params
    print(f"\n  >>> Optimal: ATR > {atr_opt} (={atr_opt*100:.2f}%), hold={hp_opt}")
    print(f"      Win Rate: {best_wr:.2%}")
    print(f"      Signal Count: {best_stats.get('signal_count', 0)}")
    print(f"      Avg Return: {best_stats.get('avg_return', 0):+.5f}")
    print(f"      Sharpe: {best_stats.get('sharpe_ratio', 0):.2f}")
    print(f"      Max DD: {best_stats.get('max_drawdown', 0):.4f}")
else:
    print("  No optimal parameters found!")
    sys.exit(1)

# ==========================================================================
# Phase 2: Cross-symbol validation with optimal params
# ==========================================================================
ALL_SYMBOLS = [
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
    "USOIL", "UKOIL", "USTEC", "US30", "US500", "JP225", "HK50",
]

print(f"\n\n{'='*80}")
print(f"  Phase 2: Cross-Symbol Validation")
print(f"  Optimal Params: ATR > {atr_opt} (={atr_opt*100:.2f}%), hold={hp_opt}")
print(f"  14 Symbols: {ALL_SYMBOLS}")
print("=" * 80)

entry_cond_opt = f"session == 'us' and rsi14 < 40 and atr14 / close > {atr_opt}"
config_opt = {
    "timeframe": "H1",
    "symbols": ALL_SYMBOLS,
    "entry_condition": entry_cond_opt,
    "direction": "long",
    "hold_periods": [hp_opt],
    "exit_at_close": True,
}
cross_results = run_grid(config_opt)
cross_meta = cross_results.pop("_meta", {})

print(f"\n{'─'*80}")
print(f"  Cross-Symbol Results (ATR > {atr_opt} = {atr_opt*100:.2f}%, hold={hp_opt})")
print(f"{'─'*80}")
print(f"  {'Symbol':<8} {'n':>6} {'WinRate':>8} {'AvgRet':>10} {'Sharpe':>8} {'MaxDD':>8}")
print(f"  {'─'*8} {'─'*6} {'─'*8} {'─'*10} {'─'*8} {'─'*8}")

cross_table = []
for sym in ALL_SYMBOLS:
    sym_res = cross_results.get(sym, {})
    if not sym_res:
        print(f"  {sym:<8}  No data")
        continue
    s = sym_res.get(hp_opt, {})
    cnt = s.get("signal_count", 0)
    wr = s.get("win_rate", 0) or 0
    avg = s.get("avg_return", 0) or 0
    sharpe = s.get("sharpe_ratio", 0) or 0
    dd = s.get("max_drawdown", 0) or 0
    cross_table.append({
        "symbol": sym, "n": cnt, "wr": wr, "avg": avg, "sharpe": sharpe, "dd": dd,
    })
    print(f"  {sym:<8} {cnt:>6} {wr:>7.2%} {avg:>+9.5f} {sharpe:>7.2f} {dd:>7.4f}")

# Sort by win rate
cross_table.sort(key=lambda x: x["wr"], reverse=True)
print(f"\n{'─'*80}")
print(f"  Ranked by Win Rate:")
print(f"{'─'*80}")
for i, item in enumerate(cross_table, 1):
    print(f"  {i:>2}. {item['symbol']:<8} n={item['n']:>5}  wr={item['wr']:>6.2%}  "
          f"avg={item['avg']:>+9.5f}  sharpe={item['sharpe']:>6.2f}  dd={item['dd']:>7.4f}")

# ==========================================================================
# Summary
# ==========================================================================
print(f"\n\n{'='*80}")
print(f"  ROUND25_a02 — COMPLETE SUMMARY")
print(f"{'='*80}")

best_sym = cross_table[0] if cross_table else None

print(f"\n  Phase 1 (US30 Gradient Scan):")
print(f"  ┌──────────┬──────┬───────┬──────────┬──────────────┬──────────┬──────────┐")
print(f"  │ ATR Thr  │ Hold │   n   │ WinRate  │   AvgRet     │ Sharpe   │  MaxDD   │")
print(f"  ├──────────┼──────┼───────┼──────────┼──────────────┼──────────┼──────────┤")
for atr_t in ATR_THRESHOLDS:
    results = all_phase1_results.get(atr_t, {})
    sym_res = results.get("US30", {})
    for hp in HOLD_PERIODS:
        s = sym_res.get(hp, {})
        cnt = s.get("signal_count", 0)
        if cnt == 0:
            continue
        wr = s.get("win_rate", 0) or 0
        avg = s.get("avg_return", 0) or 0
        sharpe = s.get("sharpe_ratio", 0) or 0
        dd = s.get("max_drawdown", 0) or 0
        marker = " ★" if (cnt >= 50 and wr >= 0.60) else ""
        print(f"  │ {atr_t*100:>5.2f}%  │ {hp:>4} │ {cnt:>5} │ {wr:>7.2%} │ {avg:>+11.5f} │ {sharpe:>6.2f} │ {dd:>6.4f} │{marker}")
print(f"  └──────────┴──────┴───────┴──────────┴──────────────┴──────────┴──────────┘")

print(f"\n  Phase 2 (Cross-Symbol, optimal ATR={atr_opt*100:.2f}%, hold={hp_opt}):")
print(f"  ┌──────────┬───────┬──────────┬──────────────┬──────────┬──────────┐")
print(f"  │ Symbol   │   n   │ WinRate  │   AvgRet     │ Sharpe   │  MaxDD   │")
print(f"  ├──────────┼───────┼──────────┼──────────────┼──────────┼──────────┤")
for item in cross_table:
    marker = " ★" if (item["n"] >= 30 and item["wr"] >= 0.60) else ""
    print(f"  │ {item['symbol']:<8} │ {item['n']:>5} │ {item['wr']:>7.2%} │ {item['avg']:>+11.5f} │ {item['sharpe']:>6.2f} │ {item['dd']:>6.4f} │{marker}")
print(f"  └──────────┴───────┴──────────┴──────────────┴──────────┴──────────┘")

# Verdict
print(f"\n\n  VERDICT:")
us30_wr = None
for item in cross_table:
    if item["symbol"] == "US30":
        us30_wr = item["wr"]
        break

print(f"  US30最优胜率: {best_wr:.2%} (ATR>{atr_opt*100:.2f}%, hold={hp_opt}, n={best_stats.get('signal_count',0)})")
print(f"  Round21基线: 59.17% (ATR>0.25%, hold=7, n=1,036)")
print(f"  Round23基线: 59.38% (ATR>0.35%, hold=10, n=517)")

if best_wr >= 0.60:
    print(f"  >>> 突破60%! 达到 {best_wr:.2%} <<<")
    verdict = "STRONG"
elif best_wr >= 0.57:
    print(f"  >>> 接近60%! ({best_wr:.2%}) <<<")
    verdict = "PROMISING"
elif best_wr >= 0.55:
    print(f"  >>> 超过55%阈值 ({best_wr:.2%}) <<<")
    verdict = "PROMISING"
else:
    verdict = "INCONCLUSIVE"

print(f"  >>> VERDICT: {verdict}")

# Save raw results
output = {
    "phase1": all_phase1_results,
    "phase2": {
        "config": config_opt,
        "results": {sym: cross_results.get(sym, {}) for sym in ALL_SYMBOLS},
    },
    "best_params": {
        "atr_threshold": atr_opt,
        "hold_period": hp_opt,
        "win_rate": best_wr,
        "signal_count": best_stats.get("signal_count", 0),
        "avg_return": best_stats.get("avg_return", 0),
        "sharpe_ratio": best_stats.get("sharpe_ratio", 0),
        "max_drawdown": best_stats.get("max_drawdown", 0),
    },
    "cross_table": cross_table,
    "verdict": verdict,
}

outpath = Path(__file__).resolve().parent.parent / "reports" / "round25_a02_results.json"
outpath.parent.mkdir(parents=True, exist_ok=True)
with open(outpath, "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"\n  Results saved to: {outpath}")

# Generate new hypotheses based on findings
print(f"\n\n{'='*80}")
print(f"  NEW HYPOTHESES GENERATION")
print(f"{'='*80}")

hypotheses = []

# Check which symbols performed well
promising_symbols = [item for item in cross_table if item["n"] >= 50 and item["wr"] >= 0.55]
strong_symbols = [item for item in cross_table if item["n"] >= 30 and item["wr"] >= 0.60]

if strong_symbols:
    for item in strong_symbols:
        print(f"\n  >>> STRONG信号: {item['symbol']} wr={item['wr']:.2%} n={item['n']}")
        if item['symbol'] != 'US30':
            h = {
                "id": f"round27_a0{len(hypotheses)+1}",
                "hypothesis": f"{item['symbol']} H1 美盘+RSI<40+ATR>{atr_opt*100:.2f}%做多 hold={hp_opt} 强信号验证",
                "entry_condition": f"session == 'us' and rsi14 < 40 and atr14 / close > {atr_opt}",
                "direction": "long",
                "timeframe": "H1",
                "hold_period": hp_opt,
                "source": f"round25_a02跨品种发现{item['symbol']}达{item['wr']:.2%}",
            }
            hypotheses.append(h)

# Generate hypothesis about adjusting ATR threshold
if best_wr >= 0.57:
    finer_atr_low = round(atr_opt - 0.0003, 4)
    finer_atr_high = round(atr_opt + 0.0003, 4)
    h = {
        "id": f"round27_a0{len(hypotheses)+1}",
        "hypothesis": f"US30 H1 美盘+RSI<40+ATR>{finer_atr_low*100:.2f}%~{finer_atr_high*100:.2f}%精细扫描试图突破{best_wr*100:.0f}%",
        "entry_condition": f"session == 'us' and rsi14 < 40 and atr14 / close > {finer_atr_low} and atr14 / close < {finer_atr_high}",
        "direction": "long",
        "timeframe": "H1",
        "source": f"round25_a02在ATR>{atr_opt*100:.2f}%达{best_wr:.2%}，精细扫描阈值范围寻找最优",
    }
    hypotheses.append(h)

# Generate hypothesis about specific session hour
h = {
    "id": f"round27_a0{len(hypotheses)+1}",
    "hypothesis": f"US30 H1 RSI<40+ATR>{atr_opt*100:.2f}%做多 hold={hp_opt} 小时级别精细分析（分小时US session）",
    "entry_condition": f"rsi14 < 40 and atr14 / close > {atr_opt}",
    "direction": "long",
    "timeframe": "H1",
    "source": f"round25_a02发现美盘+RSI<40+ATR>{atr_opt*100:.2f}%信号，进一步细化US session内各小时表现",
}
hypotheses.append(h)

# If cross-validation shows patterns in specific groups
if len(promising_symbols) >= 3:
    promising_syms = [item["symbol"] for item in promising_symbols]
    h = {
        "id": f"round27_a0{len(hypotheses)+1}",
        "hypothesis": f"H1 美盘+RSI<40+ATR>{atr_opt*100:.2f}%做多 跨品种信号一致性验证 ({', '.join(promising_syms[:3])})",
        "entry_condition": f"session == 'us' and rsi14 < 40 and atr14 / close > {atr_opt}",
        "direction": "long",
        "timeframe": "H1",
        "hold_period": hp_opt,
        "source": f"round25_a02跨品种发现{len(promising_symbols)}个品种超过55%",
    }
    hypotheses.append(h)

for i, h in enumerate(hypotheses, 1):
    print(f"\n  Round27_a0{i}: {h['hypothesis']}")
    print(f"    Entry: {h['entry_condition']}")
    print(f"    Hold: {h.get('hold_period', 'TBD')}")
    print(f"    Source: {h['source']}")

print(f"\n{'='*80}")
print(f"  TEST COMPLETE — Round25_a02: {verdict}")
print(f"{'='*80}")
