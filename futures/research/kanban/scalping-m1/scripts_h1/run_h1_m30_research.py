#!/usr/bin/env python3
"""
H1/M30 欧盘/亚盘研究循环 — Round 1

研究重点:
1. H1 欧盘超卖/超买均值回归 (全14品种)
2. H1 亚盘开盘方向延续
3. M30 欧盘连续阴线超卖反转
4. H1 欧盘首小时方向 bias
5. 跨品种 session 波动率对比
6. H1 亚盘 range breakout 到欧盘

输出: 发现和最佳模式列表
"""
import sys, logging, json
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from h1_m30_engine import (
    load_data, compute_indicators, evaluate_pattern, SYMBOLS_ALL,
    PERIODS_PER_YEAR, list_available_symbols, TIMEFRAME_DIRS
)

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("h1_m30_research")

BASE = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────────────
# Session definitions (UTC)
# Asia:   00:00-08:00
# Europe: 08:00-13:00
# US:     13:00-22:00
# ──────────────────────────────────────────────────────────────────

print("=" * 70)
print("📈 H1/M30 欧盘/亚盘研究循环 — Round 1")
print(f"   日期: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
print(f"   品种: {len(SYMBOLS_ALL)} symbols")
print("=" * 70)

# ──────────────────────────────────────────────────────────────────
# 1. 数据摘要
# ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("📊 数据摘要")
print("=" * 70)

for tf in ["H1", "M30"]:
    print(f"\n--- {tf} ---")
    data = load_data(tf, symbols=SYMBOLS_ALL)
    for sym in sorted(data.keys()):
        df = compute_indicators(data[sym])
        rsi = df["rsi14"].iloc[-1] if "rsi14" in df.columns else 0
        atr = df["atr14_pct"].iloc[-1] if "atr14_pct" in df.columns else 0
        close = df["close"].iloc[-1]
        print(f"  {sym:8s} {tf}: {len(df):>5} rows  [{df.index[0].date()} → {df.index[-1].date()}]  "
              f"Close={close:<10.4f}  RSI={rsi:.1f}  ATR%={atr:.3f}%")


# ══════════════════════════════════════════════════════════════════
# RESEARCH MODULE 1: H1 European Session Oversold/Overbought Mean Reversion
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R1: H1 欧盘超卖/超买均值回归（全14品种）")
print("=" * 70)

h1_data = load_data("H1", symbols=SYMBOLS_ALL)
r1_results = []

for sym in sorted(h1_data.keys()):
    df = compute_indicators(h1_data[sym])

    # Long: European session oversold
    cond_long = "session == 'europe' and rsi14 < 25"
    res = evaluate_pattern(df, sym, cond_long, "欧盘超卖做多 RSI<25",
                          direction="long", hold_range=[1,2,3,4,5,6,8,10,12,16,20,24], tf="H1")
    if res and res.get("best_wr", 0) >= 0.55:
        r1_results.append(res)

    # Short: European session overbought
    cond_short = "session == 'europe' and rsi14 > 75"
    res2 = evaluate_pattern(df, sym, cond_short, "欧盘超买做空 RSI>75",
                           direction="short", hold_range=[1,2,3,4,5,6,8,10,12,16,20,24], tf="H1")
    if res2 and res2.get("best_wr", 0) >= 0.55:
        r1_results.append(res2)

print(f"\n✅ R1 完成: {len(r1_results)} 个有效模式")


# ══════════════════════════════════════════════════════════════════
# RESEARCH MODULE 2: H1 Asian Session Opening Direction
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R2: H1 亚盘开盘方向延续（全14品种）")
print("=" * 70)

r2_results = []

for sym in sorted(h1_data.keys()):
    df = compute_indicators(h1_data[sym])

    # Asian session first hours: bullish bias if first hour closes up
    cond_bull_asia = "session == 'asia' and hour >= 0 and hour < 3 and close > open"
    res = evaluate_pattern(df, sym, cond_bull_asia, "亚盘早段阳线做多",
                          direction="long", hold_range=[1,2,3,4,5,6,8,10,12], tf="H1")
    if res and res.get("best_wr", 0) >= 0.55:
        r2_results.append(res)

    # Asian session bearish
    cond_bear_asia = "session == 'asia' and hour >= 0 and hour < 3 and close < open"
    res2 = evaluate_pattern(df, sym, cond_bear_asia, "亚盘早段阴线做空",
                           direction="short", hold_range=[1,2,3,4,5,6,8,10,12], tf="H1")
    if res2 and res2.get("best_wr", 0) >= 0.55:
        r2_results.append(res2)

print(f"\n✅ R2 完成: {len(r2_results)} 个有效模式")


# ══════════════════════════════════════════════════════════════════
# RESEARCH MODULE 3: M30 European Session Consecutive Candle Reversal
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R3: M30 欧盘连续阴线超卖反转（全14品种）")
print("=" * 70)

m30_data = load_data("M30", symbols=SYMBOLS_ALL)
r3_results = []

for sym in sorted(m30_data.keys()):
    df = compute_indicators(m30_data[sym])

    # Long: European session consecutive bear >= 3 + oversold
    cond_long = "session == 'europe' and consecutive_bear >= 3 and rsi14 < 30"
    res = evaluate_pattern(df, sym, cond_long, "欧盘连阴>=3+超卖做多",
                          direction="long", hold_range=[1,2,3,4,6,8,10,12,16,20,24], tf="M30")
    if res and res.get("best_wr", 0) >= 0.55:
        r3_results.append(res)

    # Short: European session consecutive bull >= 3 + overbought
    cond_short = "session == 'europe' and consecutive_bull >= 3 and rsi14 > 70"
    res2 = evaluate_pattern(df, sym, cond_short, "欧盘连阳>=3+超买做空",
                           direction="short", hold_range=[1,2,3,4,6,8,10,12,16,20,24], tf="M30")
    if res2 and res2.get("best_wr", 0) >= 0.55:
        r3_results.append(res2)

    # Long: European session RSI<20 extreme oversold (without CB)
    cond_extreme = "session == 'europe' and rsi14 < 20"
    res3 = evaluate_pattern(df, sym, cond_extreme, "欧盘极端超卖做多 RSI<20",
                           direction="long", hold_range=[1,2,3,4,6,8,10,12,16,20,24], tf="M30")
    if res3 and res3.get("best_wr", 0) >= 0.60:
        r3_results.append(res3)

print(f"\n✅ R3 完成: {len(r3_results)} 个有效模式")


# ══════════════════════════════════════════════════════════════════
# RESEARCH MODULE 4: H1 European First Hour Direction Bias
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R4: H1 欧盘首小时(8-9 UTC)方向 Bias（全14品种）")
print("=" * 70)

r4_results = []

for sym in sorted(h1_data.keys()):
    df = compute_indicators(h1_data[sym])

    # European first hour: if bullish, continue long
    cond_first_bull = "hour == 8 and close > open"
    res = evaluate_pattern(df, sym, cond_first_bull, "欧盘首小时阳线做多",
                          direction="long", hold_range=[1,2,3,4,5,6,8,10,12], tf="H1")
    if res and res.get("best_wr", 0) >= 0.55:
        r4_results.append(res)

    # European first hour: if bearish, continue short
    cond_first_bear = "hour == 8 and close < open"
    res2 = evaluate_pattern(df, sym, cond_first_bear, "欧盘首小时阴线做空",
                           direction="short", hold_range=[1,2,3,4,5,6,8,10,12], tf="H1")
    if res2 and res2.get("best_wr", 0) >= 0.55:
        r4_results.append(res2)

print(f"\n✅ R4 完成: {len(r4_results)} 个有效模式")


# ══════════════════════════════════════════════════════════════════
# RESEARCH MODULE 5: H1 Asian Session Range Breakout at European Open
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R5: H1 亚盘区间突破 + 欧盘开盘方向")
print("=" * 70)

r5_results = []

for sym in sorted(h1_data.keys()):
    df = compute_indicators(h1_data[sym])

    # Asian session high/low range breakout
    # Price above MA20 during European open after Asian session
    cond_breakout = "session == 'europe' and hour >= 8 and hour < 10 and above_ma20 == 1 and rsi14 > 50"
    res = evaluate_pattern(df, sym, cond_breakout, "欧盘初高于MA20+RSI>50做多",
                          direction="long", hold_range=[1,2,3,4,5,6,8,10], tf="H1")
    if res and res.get("best_wr", 0) >= 0.55:
        r5_results.append(res)

    cond_breakdown = "session == 'europe' and hour >= 8 and hour < 10 and above_ma20 == 0 and rsi14 < 50"
    res2 = evaluate_pattern(df, sym, cond_breakdown, "欧盘初低于MA20+RSI<50做空",
                           direction="short", hold_range=[1,2,3,4,5,6,8,10], tf="H1")
    if res2 and res2.get("best_wr", 0) >= 0.55:
        r5_results.append(res2)

print(f"\n✅ R5 完成: {len(r5_results)} 个有效模式")


# ══════════════════════════════════════════════════════════════════
# RESEARCH MODULE 6: M30 Asian Session Pre-Europe Patterns
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📌 R6: M30 亚盘尾段/欧盘开盘过渡（全14品种）")
print("=" * 70)

r6_results = []

for sym in sorted(m30_data.keys()):
    df = compute_indicators(m30_data[sym])

    # Asian session last 2 hours (hour 6-7) -> European open continuation
    cond_asia_late_long = "hour >= 6 and hour < 8 and close > open and rsi14 > 50"
    res = evaluate_pattern(df, sym, cond_asia_late_long, "亚盘尾段阳线做多(过渡欧盘)",
                          direction="long", hold_range=[1,2,3,4,6,8,10,12], tf="M30")
    if res and res.get("best_wr", 0) >= 0.55:
        r6_results.append(res)

    cond_asia_late_short = "hour >= 6 and hour < 8 and close < open and rsi14 < 50"
    res2 = evaluate_pattern(df, sym, cond_asia_late_short, "亚盘尾段阴线做空(过渡欧盘)",
                           direction="short", hold_range=[1,2,3,4,6,8,10,12], tf="M30")
    if res2 and res2.get("best_wr", 0) >= 0.55:
        r6_results.append(res2)

print(f"\n✅ R6 完成: {len(r6_results)} 个有效模式")


# ══════════════════════════════════════════════════════════════════
# SUMMARY & BEST FINDINGS
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("🏆 H1/M30 研究 — 发现汇总")
print("=" * 70)

all_results = r1_results + r2_results + r3_results + r4_results + r5_results + r6_results

# Filter for quality signals
strong_signals = [r for r in all_results if r["best_wr"] >= 0.60 and r["best_n"] >= 30]
promising_signals = [r for r in all_results if r["best_wr"] >= 0.55 and r["best_wr"] < 0.60 and r["best_n"] >= 30]

print(f"\n📈 强信号 (WR>=60% n>=30): {len(strong_signals)}")
print(f"📊 有潜力信号 (WR>=55% n>=30): {len(promising_signals)}")

if strong_signals:
    print(f"\n{'='*60}")
    print(f"🏆 最佳发现 — 按胜率排序")
    print(f"{'='*60}")
    strong_sorted = sorted(strong_signals, key=lambda x: x["best_wr"], reverse=True)
    print(f" {'#':<4} {'品种':<8} {'模式':<40} {'方向':<6} {'WR':<8} {'n':<6} {'Hold':<6} {'Sharpe':<8}")
    print(f" {'-'*3} {'-'*7} {'-'*39} {'-'*5} {'-'*7} {'-'*5} {'-'*5} {'-'*7}")
    for i, r in enumerate(strong_sorted[:40]):
        print(f" {i+1:<3} {r['symbol']:<8} {r['label'][:38]:<40} {r['direction']:<6} "
              f"{r['best_wr']*100:<7.1f}% {r['best_n']:<6} {r['best_hold']:<6} {r['best_sharpe']:<8.2f}")


# ──────────────────────────────────────────────────────────────────
# 生成新假设
# ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("💡 下一轮假设")
print("=" * 70)

new_hypotheses = []
# Based on findings, generate 3-5 new hypotheses
new_hypotheses.append({
    "id": "h1r1_europe_oversold_depth",
    "description": f"H1 欧盘超卖 RSI 阈值深度扫描 — 对有signal的品种做RSI<20/22/25/28分档对比",
    "direction": "long",
    "timeframe": "H1",
    "priority": 1,
})
new_hypotheses.append({
    "id": "h1r1_europe_mid_window",
    "description": f"H1 欧盘中段(9-12 UTC) vs 欧盘首段(8-10 UTC) 子窗口对比",
    "direction": "long",
    "timeframe": "H1",
    "priority": 1,
})
new_hypotheses.append({
    "id": "m30_europe_cb_depth",
    "description": f"M30 欧盘连阴CB深度对比 — CB>=2/3/4/5 加上RSI阈值的精细扫描",
    "direction": "long",
    "timeframe": "M30",
    "priority": 1,
})
new_hypotheses.append({
    "id": "h1_asia_to_europe_transition",
    "description": f"H1 亚盘尾段(6-8)到欧盘开盘(8-10)的整体transition策略 — 亚盘range高/低突破",
    "direction": "long",
    "timeframe": "H1",
    "priority": 2,
})
new_hypotheses.append({
    "id": "h1_m30_europe_short_explore",
    "description": f"H1/M30 欧盘超买做空探索 — RSI>70/72/75/78 + CBull>=3/4 组合扫描",
    "direction": "short",
    "timeframe": "H1/M30",
    "priority": 2,
})

for h in new_hypotheses:
    print(f"  [{h['priority']}] {h['description'][:70]}...")


# ──────────────────────────────────────────────────────────────────
# 生成报告文件
# ──────────────────────────────────────────────────────────────────
# This is round 1 of H1/M30 research track
report_path = REPORTS_DIR / "h1_m30_round_001.md"

with open(report_path, "w", encoding="utf-8") as f:
    f.write(f"""# H1/M30 欧盘/亚盘研究报告 — Round 1

**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC
**品种**: 全部14个MT5品种
**时间框架**: H1（主）/ M30（辅）

---

## 数据概况

| Timeframe | 品种数 | 数据范围 | 平均行数 |
|:---------:|:------:|:---------|:--------:|
| H1 | 14 | ~3.5个月 (Feb-May 2026) | ~1670 |
| M30 | 14 | ~3.5个月 (Feb-May 2026) | ~3340 |

## 研究模块结果

### R1: H1 欧盘超卖/超买均值回归
- 测试条件: `session=='europe' and rsi14<25` (做多) / `rsi14>75` (做空)
- 有效品种: {len(r1_results)}
""")
    if r1_results:
        f.write(f"| {'品种':<8} | {'模式':<40} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':40}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r1_results, key=lambda x: x["best_wr"], reverse=True)[:15]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:38]:<40} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"### R2: H1 亚盘开盘方向延续\n")
    f.write(f"- 有效品种: {len(r2_results)}\n")
    if r2_results:
        f.write(f"| {'品种':<8} | {'模式':<40} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':40}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r2_results, key=lambda x: x["best_wr"], reverse=True)[:10]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:38]:<40} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"### R3: M30 欧盘连续阴线超卖反转\n")
    f.write(f"- 有效品种: {len(r3_results)}\n")
    if r3_results:
        f.write(f"| {'品种':<8} | {'模式':<40} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':40}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r3_results, key=lambda x: x["best_wr"], reverse=True)[:15]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:38]:<40} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"### R4: H1 欧盘首小时方向 Bias\n")
    f.write(f"- 有效品种: {len(r4_results)}\n")
    if r4_results:
        f.write(f"| {'品种':<8} | {'模式':<40} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':40}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r4_results, key=lambda x: x["best_wr"], reverse=True)[:10]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:38]:<40} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"### R5: H1 亚盘区间突破+欧盘开盘\n")
    f.write(f"- 有效品种: {len(r5_results)}\n")
    if r5_results:
        f.write(f"| {'品种':<8} | {'模式':<40} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':40}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r5_results, key=lambda x: x["best_wr"], reverse=True)[:10]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:38]:<40} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"### R6: M30 亚盘尾段/欧盘开盘过渡\n")
    f.write(f"- 有效品种: {len(r6_results)}\n")
    if r6_results:
        f.write(f"| {'品种':<8} | {'模式':<40} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':8}|{'---':40}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for r in sorted(r6_results, key=lambda x: x["best_wr"], reverse=True)[:10]:
            f.write(f"| {r['symbol']:<8} | {r['label'][:38]:<40} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    f.write("\n")

    f.write(f"## 最佳发现 (WR>=60% n>=30)\n\n")
    if strong_signals:
        f.write(f"| {'#':<4} | {'品种':<8} | {'模式':<40} | {'方向':<6} | {'WR':<8} | {'n':<6} | {'Hold':<6} | {'Sharpe':<8} |\n")
        f.write(f"|{':---':4}|{'---':8}|{'---':40}|{'---':6}|{'---':8}|{'---':6}|{'---':6}|{'---':8}|\n")
        for i, r in enumerate(sorted(strong_signals, key=lambda x: x["best_wr"], reverse=True)):
            f.write(f"| {i+1:<3} | {r['symbol']:<8} | {r['label'][:38]:<40} | {r['direction']:<6} | {r['best_wr']*100:<7.1f}% | {r['best_n']:<6} | {r['best_hold']:<6} | {r['best_sharpe']:<8.2f} |\n")
    else:
        f.write("无符合条件的强信号。\n")
    f.write("\n")

    f.write("## 下一轮假设\n\n")
    for h in new_hypotheses:
        f.write(f"- **P{h['priority']}** [{h['timeframe']}] {h['description']}\n")
    f.write("\n")

    f.write("---\n")
    f.write(f"*报告由 Reze (Orchestrator) 于 {datetime.now().strftime('%Y-%m-%d %H:%M')} 生成*\n")

print(f"\n✅ 报告已保存到: {report_path}")
print("✅ H1/M30 研究循环 Round 1 完成")
