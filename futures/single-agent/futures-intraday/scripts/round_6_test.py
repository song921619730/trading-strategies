#!/usr/bin/env python3
"""
round_6_test.py — 第6轮研究测试

测试项目:
1. H28: H1 three_black_crows + RSI<60 + 美盘 → XAUUSD, US30 做多（反向）
2. H29: H1 bear_continuation + RSI>60 + 美盘 → XAUUSD 做多（反向）
3. H30: H1 shooting_star + RSI>50 + 美盘 → US30 做多（降低RSI门槛）
4. M1/M5 超短线模式扫描（探索性质）
"""
import os, sys, json
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

from run_candlestick import run_pattern_test, run_pattern_test_enhanced

RESULTS = {}
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def fmt_result(name, res):
    """Format test result for report"""
    best = res.get("best_overall", {})
    lines = []
    lines.append(f"\n### {name}")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 最佳品种 | {best.get('symbol', 'N/A')} |")
    lines.append(f"| 最佳持有期 | {best.get('hold', 'N/A')} |")
    lines.append(f"| 胜率 | {best.get('win_rate', 0):.1f}% |")
    lines.append(f"| 信号数 | {best.get('n', 0)} |")
    lines.append(f"| Sharpe | {best.get('sharpe', 0):.2f} |")
    lines.append(f"| 平均回报 | {best.get('avg_return', 0):.3f}% |")
    
    # Per-symbol details
    details = res.get("details", {})
    for sym, sdata in details.items():
        if isinstance(sdata, dict) and "error" not in sdata:
            hp = sdata.get("hold_periods", {})
            rows = [(h, hp[h]) for h in sorted(hp.keys()) if hp[h].get("n", 0) >= 5]
            if rows:
                lines.append(f"\n#### {sym} (n={sdata.get('signal_count', '?')})")
                lines.append(f"| 持有期 | 胜率 | n | 平均回报% | Sharpe |")
                lines.append(f"|:-----:|:----:|:--:|:--------:|:-----:|")
                for h, m in rows:
                    mr = "✅" if m['win_rate'] >= 60 and m['n'] >= 15 else "⚠️" if m['win_rate'] >= 50 else "❌"
                    lines.append(f"| {h} | {m['win_rate']:.1f}%{mr} | {m['n']} | {m['avg_return']:+.3f} | {m['sharpe']:.2f} |")
    
    return "\n".join(lines)

# =====================
# 1. 测试 H28: three_black_crows 反向做多
# =====================
print("=" * 70)
print("📊 测试 H28: H1 three_black_crows + RSI<60 + 美盘 → XAUUSD, US30 做多")
print("=" * 70)
res_h28 = run_pattern_test(
    entry_condition="rsi14 < 60 and session == 'us' and three_black_crows == True",
    direction="long",
    timeframe="H1",
    symbols=["XAUUSD", "US30"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15],
)
RESULTS["H28"] = res_h28

# =====================
# 2. 测试 H29: bear_continuation 反向做多
# =====================
print("=" * 70)
print("📊 测试 H29: H1 bear_continuation + RSI>60 + 美盘 → XAUUSD 做多")
print("=" * 70)
res_h29 = run_pattern_test(
    entry_condition="rsi14 > 60 and session == 'us' and bear_continuation == True",
    direction="long",
    timeframe="H1",
    symbols=["XAUUSD"],
    hold_periods=[1, 2, 3, 5, 7, 10],
)
RESULTS["H29"] = res_h29

# =====================
# 3. 测试 H30: shooting_star RSI>50 做多
# =====================
print("=" * 70)
print("📊 测试 H30: H1 shooting_star + RSI>50 + 美盘 → US30 做多")
print("=" * 70)
res_h30 = run_pattern_test(
    entry_condition="rsi14 > 50 and session == 'us' and shooting_star == True",
    direction="long",
    timeframe="H1",
    symbols=["US30"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15],
)
RESULTS["H30"] = res_h30

# =====================
# 4. M1 超短线模式扫描（增强分析）
# =====================
print("\n" + "=" * 70)
print("🔥 M1 超短线模式扫描 — 探索所有K线形态在M1上的表现")
print("=" * 70)
res_m1_scan = run_pattern_test_enhanced(
    entry_condition="session == 'us'",
    direction="long",
    timeframe="M1",
    symbols=["XAUUSD", "XAGUSD", "US30", "US500", "JP225"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
)
RESULTS["M1_SCAN"] = res_m1_scan

# =====================
# 5. M5 超短线模式扫描
# =====================
print("\n" + "=" * 70)
print("🔥 M5 超短线模式扫描 — 探索所有K线形态在M5上的表现")
print("=" * 70)
res_m5_scan = run_pattern_test_enhanced(
    entry_condition="session == 'us'",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD", "XAGUSD", "US30", "US500", "JP225"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
)
RESULTS["M5_SCAN"] = res_m5_scan

# =====================
# 6. M1 RSI<40 + 美盘 基础策略测试
# =====================
print("\n" + "=" * 70)
print("🔥 M1 美盘+RSI<40 基础策略 — 各品种做多测试")
print("=" * 70)
res_m1_rsi = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us'",
    direction="long",
    timeframe="M1",
    symbols=["XAUUSD", "XAGUSD", "US30", "US500", "JP225"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20, 30, 60],
)
RESULTS["M1_RSI"] = res_m1_rsi

# =====================
# 7. M5 RSI<40 + 美盘 基础策略测试
# =====================
print("\n" + "=" * 70)
print("🔥 M5 美盘+RSI<40 基础策略 — 各品种做多测试")
print("=" * 70)
res_m5_rsi = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us'",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD", "XAGUSD", "US30", "US500", "JP225"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20, 30, 60],
)
RESULTS["M5_RSI"] = res_m5_rsi

# =====================
# 8. M1 RSI>60 + 美盘 做空测试
# =====================
print("\n" + "=" * 70)
print("🔥 M1 美盘+RSI>60 做空 — 各品种测试")
print("=" * 70)
res_m1_rsi_short = run_pattern_test(
    entry_condition="rsi14 > 60 and session == 'us'",
    direction="short",
    timeframe="M1",
    symbols=["XAUUSD", "XAGUSD", "US30", "US500", "JP225"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20, 30, 60],
)
RESULTS["M1_RSI_SHORT"] = res_m1_rsi_short

# =====================
# 9. M5 RSI>60 + 美盘 做空测试
# =====================
print("\n" + "=" * 70)
print("🔥 M5 美盘+RSI>60 做空 — 各品种测试")
print("=" * 70)
res_m5_rsi_short = run_pattern_test(
    entry_condition="rsi14 > 60 and session == 'us'",
    direction="short",
    timeframe="M5",
    symbols=["XAUUSD", "XAGUSD", "US30", "US500", "JP225"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20, 30, 60],
)
RESULTS["M5_RSI_SHORT"] = res_m5_rsi_short

# =====================
# 保存结果
# =====================
out_dir = os.path.join(BASE, "logs", "research")
os.makedirs(out_dir, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
result_path = os.path.join(out_dir, f"round6_{ts}.json")
with open(result_path, "w") as f:
    json.dump(RESULTS, f, ensure_ascii=False, indent=2, default=str)
print(f"\n✅ 原始结果已保存: {result_path}")

# =====================
# 生成分析报告
# =====================
report = []
report.append(f"# 第6轮研究报告 — Round 6（M1/M5 超短线首轮探索）")
report.append(f"")
report.append(f"**时间**: {TIMESTAMP}")
report.append(f"**研究焦点**: M1/M5 超短线模式发现 + H28-H30 验证")
report.append(f"")
report.append(f"---")
report.append(f"")

# H28 Results
report.append(f"## H28: three_black_crows 反向做多验证")
report.append(f"")
report.append(f"**假设**: H1 three_black_crows + RSI<60 + 美盘 → XAUUSD, US30 做多")
report.append(f"**前情**: H24发现三黑兵做空WR仅32-44%，反向做多胜率56-68%。验证反向效应是否成立。")
report.append(f"")
h28_best = RESULTS["H28"].get("best_overall", {})
report.append(f"**结果**: 最佳 WR={h28_best.get('win_rate', 0):.1f}% ({h28_best.get('symbol', 'N/A')}@{h28_best.get('hold', 'N/A')}期, n={h28_best.get('n', 0)})")
report.append(f"")

h28_details = RESULTS["H28"].get("details", {})
for sym in ["XAUUSD", "US30"]:
    if sym in h28_details and isinstance(h28_details[sym], dict) and "error" not in h28_details[sym]:
        hp = h28_details[sym].get("hold_periods", {})
        report.append(f"### {sym} (信号数: {h28_details[sym].get('signal_count', 0)})")
        report.append(f"| 持有期 | 胜率 | n | 平均回报% | Sharpe |")
        report.append(f"|:-----:|:----:|:--:|:--------:|:-----:|")
        for h in sorted(hp.keys()):
            m = hp[h]
            if m['n'] >= 5:
                emoji = "✅" if m['win_rate'] >= 60 and m['n'] >= 15 else "⚠️" if m['win_rate'] >= 50 else "❌"
                report.append(f"| {h} | {m['win_rate']:.1f}%{emoji} | {m['n']} | {m['avg_return']:+.3f} | {m['sharpe']:.2f} |")

report.append(f"")

# H29 Results
report.append(f"## H29: bear_continuation 反向做多验证")
report.append(f"")
report.append(f"**假设**: H1 bear_continuation + RSI>60 + 美盘 → XAUUSD 做多")
report.append(f"**前情**: H11做空WR 68.2%(n=22)；H20做多WR仅45.5%(n=22)。复测确认方向。")
report.append(f"")
h29_best = RESULTS["H29"].get("best_overall", {})
report.append(f"**结果**: 最佳 WR={h29_best.get('win_rate', 0):.1f}% ({h29_best.get('symbol', 'N/A')}@{h29_best.get('hold', 'N/A')}期, n={h29_best.get('n', 0)})")
report.append(f"")

h29_details = RESULTS["H29"].get("details", {})
for sym in ["XAUUSD"]:
    if sym in h29_details and isinstance(h29_details[sym], dict) and "error" not in h29_details[sym]:
        hp = h29_details[sym].get("hold_periods", {})
        report.append(f"### {sym} (信号数: {h29_details[sym].get('signal_count', 0)})")
        report.append(f"| 持有期 | 胜率 | n | 平均回报% | Sharpe |")
        report.append(f"|:-----:|:----:|:--:|:--------:|:-----:|")
        for h in sorted(hp.keys()):
            m = hp[h]
            if m['n'] >= 5:
                emoji = "✅" if m['win_rate'] >= 60 and m['n'] >= 15 else "⚠️" if m['win_rate'] >= 50 else "❌"
                report.append(f"| {h} | {m['win_rate']:.1f}%{emoji} | {m['n']} | {m['avg_return']:+.3f} | {m['sharpe']:.2f} |")

report.append(f"")

# H30 Results
report.append(f"## H30: shooting_star RSI>50 做多（降低RSI门槛）")
report.append(f"")
report.append(f"**假设**: H1 shooting_star + RSI>50 + 美盘 → US30 做多")
report.append(f"**前情**: H19中RSI>60版本WR 84.6%但n仅13。降低RSI至>50以增加信号量。")
report.append(f"")
h30_best = RESULTS["H30"].get("best_overall", {})
report.append(f"**结果**: 最佳 WR={h30_best.get('win_rate', 0):.1f}% ({h30_best.get('symbol', 'N/A')}@{h30_best.get('hold', 'N/A')}期, n={h30_best.get('n', 0)})")
report.append(f"")

h30_details = RESULTS["H30"].get("details", {})
for sym in ["US30"]:
    if sym in h30_details and isinstance(h30_details[sym], dict) and "error" not in h30_details[sym]:
        hp = h30_details[sym].get("hold_periods", {})
        report.append(f"### {sym} (信号数: {h30_details[sym].get('signal_count', 0)})")
        report.append(f"| 持有期 | 胜率 | n | 平均回报% | Sharpe |")
        report.append(f"|:-----:|:----:|:--:|:--------:|:-----:|")
        for h in sorted(hp.keys()):
            m = hp[h]
            if m['n'] >= 5:
                emoji = "✅" if m['win_rate'] >= 60 and m['n'] >= 15 else "⚠️" if m['win_rate'] >= 50 else "❌"
                report.append(f"| {h} | {m['win_rate']:.1f}%{emoji} | {m['n']} | {m['avg_return']:+.3f} | {m['sharpe']:.2f} |")

report.append(f"")

# M1/M5 RSI Baseline
report.append(f"## M1/M5 超短线基础策略测试")
report.append(f"")

for test_name, label in [("M1_RSI", "M1 美盘+RSI<40 做多"), ("M5_RSI", "M5 美盘+RSI<40 做多"),
                          ("M1_RSI_SHORT", "M1 美盘+RSI>60 做空"), ("M5_RSI_SHORT", "M5 美盘+RSI>60 做空")]:
    res = RESULTS[test_name]
    best = res.get("best_overall", {})
    report.append(f"### {label}")
    report.append(f"| 指标 | 值 |")
    report.append(f"|------|-----|")
    report.append(f"| 最佳品种 | {best.get('symbol', 'N/A')} |")
    report.append(f"| 最佳持有期 | {best.get('hold', 'N/A')} |")
    report.append(f"| 胜率 | {best.get('win_rate', 0):.1f}% |")
    report.append(f"| 信号数 | {best.get('n', 0)} |")
    report.append(f"| Sharpe | {best.get('sharpe', 0):.2f} |")
    report.append(f"")
    
    details = res.get("details", {})
    for sym in ["XAUUSD", "XAGUSD", "US30", "US500", "JP225"]:
        if sym in details and isinstance(details[sym], dict) and "error" not in details[sym]:
            hp = details[sym].get("hold_periods", {})
            sc = details[sym].get("signal_count", 0)
            # Find best hold for this symbol
            best_hold = max(hp.keys(), key=lambda h: hp[h].get("win_rate", 0) if hp[h].get("n", 0) >= 15 else -1) if hp else None
            if best_hold and hp[best_hold]["n"] >= 15:
                best_m = hp[best_hold]
                emoji = "✅" if best_m["win_rate"] >= 60 else "⭐" if best_m["win_rate"] >= 55 else ""
                report.append(f"- {sym} {emoji}: WR {best_m['win_rate']:.1f}% @ {best_hold}期 (n={best_m['n']}, Sharpe={best_m['sharpe']:.2f}, 信号总数={sc})")

report.append(f"")

# M1/M5 Pattern Scan Summary
report.append(f"## M1 形态扫描 — 美盘时段")
report.append(f"")

m1_scan = RESULTS["M1_SCAN"].get("pattern_summary", {})
# Sort by best WR
sorted_m1 = sorted(m1_scan.items(), key=lambda x: x[1]["best_wr"], reverse=True)
report.append(f"| 形态 | 最佳WR | 最佳品种@持有期 | 总信号数 | 平均WR |")
report.append(f"|------|:-----:|:--------------:|:--------:|:-----:|")
for pname, pdata in sorted_m1:
    if pdata["total_n"] >= 30:
        marker = "⭐" if pdata["best_wr"] > 60 else "  "
        report.append(f"| {marker} {pname} | {pdata['best_wr']:.1f}% | {pdata['best_symbol']}@{pdata['best_hold']} | {pdata['total_n']} | {pdata['avg_wr']:.1f}% |")
report.append(f"")

report.append(f"## M5 形态扫描 — 美盘时段")
report.append(f"")

m5_scan = RESULTS["M5_SCAN"].get("pattern_summary", {})
sorted_m5 = sorted(m5_scan.items(), key=lambda x: x[1]["best_wr"], reverse=True)
report.append(f"| 形态 | 最佳WR | 最佳品种@持有期 | 总信号数 | 平均WR |")
report.append(f"|------|:-----:|:--------------:|:--------:|:-----:|")
for pname, pdata in sorted_m5:
    if pdata["total_n"] >= 30:
        marker = "⭐" if pdata["best_wr"] > 60 else "  "
        report.append(f"| {marker} {pname} | {pdata['best_wr']:.1f}% | {pdata['best_symbol']}@{pdata['best_hold']} | {pdata['total_n']} | {pdata['avg_wr']:.1f}% |")
report.append(f"")

# =====================
# 结论与生成新假设
# =====================
report.append(f"## 结论与下一步")
report.append(f"")

report.append(f"### H28-H30 验证结论")
report.append(f"")
report.append(f"- **H28 (three_black_crows 反向做多)**: ")
report.append(f"- **H29 (bear_continuation 反向做多)**: ")
report.append(f"- **H30 (shooting_star RSI>50做多)**: ")
report.append(f"")

report.append(f"### M1/M5 初步发现")
report.append(f"")
report.append(f"- **M1 RSI<40 做多**: ")
report.append(f"- **M5 RSI<40 做多**: ")
report.append(f"- **M1/M5 形态扫描**: ")
report.append(f"")

report.append(f"---")
report.append(f"*报告自动生成于 {TIMESTAMP}*")

report_text = "\n".join(report)

# Save report
report_path = os.path.join(BASE, "reports", f"round_6_report.md")
with open(report_path, "w") as f:
    f.write(report_text)
print(f"\n✅ 报告已保存: {report_path}")

# Also print key findings for stdout
print("\n" + "=" * 70)
print("📋 H28 结果摘要:")
h28_best = RESULTS["H28"].get("best_overall", {})
print(f"   Best: {h28_best.get('symbol', 'N/A')}@{h28_best.get('hold', 'N/A')} WR={h28_best.get('win_rate', 0):.1f}% n={h28_best.get('n', 0)}")
print("📋 H29 结果摘要:")
h29_best = RESULTS["H29"].get("best_overall", {})
print(f"   Best: {h29_best.get('symbol', 'N/A')}@{h29_best.get('hold', 'N/A')} WR={h29_best.get('win_rate', 0):.1f}% n={h29_best.get('n', 0)}")
print("📋 H30 结果摘要:")
h30_best = RESULTS["H30"].get("best_overall", {})
print(f"   Best: {h30_best.get('symbol', 'N/A')}@{h30_best.get('hold', 'N/A')} WR={h30_best.get('win_rate', 0):.1f}% n={h30_best.get('n', 0)}")

print("\n📋 M1 RSI<40 做多:")
m1_best = RESULTS["M1_RSI"].get("best_overall", {})
print(f"   Best: {m1_best.get('symbol', 'N/A')}@{m1_best.get('hold', 'N/A')} WR={m1_best.get('win_rate', 0):.1f}% n={m1_best.get('n', 0)}")

print("\n📋 M5 RSI<40 做多:")
m5_best = RESULTS["M5_RSI"].get("best_overall", {})
print(f"   Best: {m5_best.get('symbol', 'N/A')}@{m5_best.get('hold', 'N/A')} WR={m5_best.get('win_rate', 0):.1f}% n={m5_best.get('n', 0)}")

print("\n📋 M1 形态扫描 Top 5:")
m1_sorted = sorted(m1_scan.items(), key=lambda x: x[1]["best_wr"], reverse=True)
for pname, pdata in m1_sorted[:5]:
    if pdata["total_n"] >= 30:
        print(f"   {pname:25s} WR={pdata['best_wr']:5.1f}% n={pdata['total_n']:4d} {pdata['best_symbol']}@{pdata['best_hold']}")

print("\n📋 M5 形态扫描 Top 5:")
m5_sorted = sorted(m5_scan.items(), key=lambda x: x[1]["best_wr"], reverse=True)
for pname, pdata in m5_sorted[:5]:
    if pdata["total_n"] >= 30:
        print(f"   {pname:25s} WR={pdata['best_wr']:5.1f}% n={pdata['total_n']:4d} {pdata['best_symbol']}@{pdata['best_hold']}")

print(f"\nDone! Report: {report_path}")
