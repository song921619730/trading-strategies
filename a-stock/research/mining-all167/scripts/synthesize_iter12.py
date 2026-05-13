#!/usr/bin/env python3
"""Synthesize Iteration 12 results and update state/knowledge_base/report."""
import json
import os

STRATEGY_DIR = "/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/mining-all167"

# Load results
with open(f"{STRATEGY_DIR}/logs/iter_12/backtest_results.json") as f:
    results = json.load(f)

# Load state
with open(f"{STRATEGY_DIR}/state/state.json") as f:
    state = json.load(f)

# Load knowledge base
kbfile = f"{STRATEGY_DIR}/state/knowledge_base.md"
with open(kbfile) as f:
    kb = f.read()

# === Step 1: Analyze results ===
passed = [r for r in results if r.get("stats") and r["stats"].get("signal_count",0) >= 200 and r["stats"].get("wr_5d",0) >= 52 and r["stats"].get("ret_5d",0) >= 3]

print(f"Iteration 12: {len(passed)}/{len(results)} combos passed")

# Best by R5
best_r5 = max(passed, key=lambda r: r["stats"]["ret_5d"]) if passed else None
# Best by Sharpe
best_sharpe = max(passed, key=lambda r: r["stats"].get("sharpe_5d",0)) if passed else None
# Best by WR  
best_wr = max(passed, key=lambda r: r["stats"]["wr_5d"]) if passed else None

print(f"Best R5: {best_r5['analyst']}-{best_r5['name']}: R5={best_r5['stats']['ret_5d']}%, WR={best_r5['stats']['wr_5d']}%, Sharpe={best_r5['stats'].get('sharpe_5d',0)}")
print(f"Best WR: {best_wr['analyst']}-{best_wr['name']}: WR={best_wr['stats']['wr_5d']}%, R5={best_wr['stats']['ret_5d']}%")
print(f"Best Sharpe: {best_sharpe['analyst']}-{best_sharpe['name']}: Sharpe={best_sharpe['stats'].get('sharpe_5d',0)}")

# === Step 2: Check against best_metrics ===
best_r5_global = state["best_metrics"]["ret_5d"]
best_wr_global = state["best_metrics"]["win_rate_5d"]
best_sharpe_global = state["best_metrics_robust"]["sharpe_5d"]
best_wr_robust = state["best_metrics_robust"]["win_rate_5d"]

new_global_best = False
new_robust_best = False

# Check R5 record
if best_r5 and best_r5["stats"]["ret_5d"] > best_r5_global:
    print(f"🏆 NEW GLOBAL R5 RECORD! {best_r5['stats']['ret_5d']}% > {best_r5_global}%")
    new_global_best = True
    state["best_metrics"]["ret_5d"] = best_r5["stats"]["ret_5d"]
    state["best_metrics"]["win_rate_5d"] = best_r5["stats"]["wr_5d"]
    state["best_metrics"]["signal_count"] = best_r5["stats"]["signal_count"]
    state["best_metrics"]["sharpe_5d"] = best_r5["stats"].get("sharpe_5d", 0)
    state["best_metrics"]["strategy_desc"] = f"{best_r5['analyst']}-{best_r5['name']}: {best_r5['params']}"
    state["best_metrics"]["params"] = {"combo": best_r5['name']}
    state["best_metrics"]["discovered_at"] = "2026-05-12"
    state["fatigue_count"] = 0
else:
    state["fatigue_count"] += 1
    print(f"No new R5 record. Fatigue: {state['fatigue_count']}")

# Check robust best (WR+Sharpe combination)
if best_wr and best_wr["stats"]["wr_5d"] >= 80 and best_wr["stats"].get("sharpe_5d",0) >= 5:
    if best_wr["stats"]["wr_5d"] > best_wr_robust and best_wr["stats"].get("sharpe_5d",0) >= state["best_metrics_robust"]["sharpe_5d"]:
        print(f"🏆 NEW ROBUST BEST! WR={best_wr['stats']['wr_5d']}%, Sharpe={best_wr['stats'].get('sharpe_5d',0)}")
        new_robust_best = True
        state["best_metrics_robust"]["ret_5d"] = best_wr["stats"]["ret_5d"]
        state["best_metrics_robust"]["win_rate_5d"] = best_wr["stats"]["wr_5d"]
        state["best_metrics_robust"]["signal_count"] = best_wr["stats"]["signal_count"]
        state["best_metrics_robust"]["sharpe_5d"] = best_wr["stats"].get("sharpe_5d", 0)
        state["best_metrics_robust"]["strategy_desc"] = f"{best_wr['analyst']}-{best_wr['name']}: {best_wr['params']}"
        state["best_metrics_robust"]["params"] = {"combo": best_wr['name']}
        state["best_metrics_robust"]["discovered_at"] = "2026-05-12"

# === Step 3: Update history ===
for r in passed:
    entry = {
        "iteration": 12,
        "ret_5d": r["stats"]["ret_5d"],
        "win_5d": r["stats"]["wr_5d"],
        "signal_count": r["stats"]["signal_count"],
        "sharpe_5d": r["stats"].get("sharpe_5d", 0),
        "analyst": f"{r['analyst']}-{r['name']}",
        "params": r["params"],
        "note": f"N={r['stats']['signal_count']}, R10={r['stats']['ret_10d']}%"
    }
    state["history"].insert(0, entry)
state["history"] = state["history"][:50]  # Keep 50

# Update recent_combos
for r in passed:
    combo_hash = f"iter12_{r['analyst']}-{r['name']}({r['params']})"
    state["recent_combos"].insert(0, combo_hash)
state["recent_combos"] = state["recent_combos"][:50]

# Update iteration
state["current_iteration"] = 12
state["updated_at"] = "2026-05-12 17:30"

# Save state
with open(f"{STRATEGY_DIR}/state/state.json", "w") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
print("State updated!")

# === Step 4: Update knowledge_base ===
# Add best discoveries to knowledge_base
new_kb_entries = []

# T2-C2 best performer
new_kb_entries.append(f"""
## 2026-05-12 (iter 12) - 🏆 T2-C2: 深底10%+大阳5%+大振幅7%+微盘 (Iter12全局最佳 — R5=12.25%, WR=75.91%)
- **策略**: 底10%(60日) + 涨≥5% + 振幅≥7% + VR≥1.2 + CM≤30亿
- **指标**: WR_5d=75.91%, ret_5d=12.25%, ret_10d=13.52%, ret_20d=19.12%, Sharpe=5.56, N=679
- **逻辑链**: 深底(10%)→大阳线(≥5%)→极端振幅(≥7%)→放量(VR≥1.2)→微盘(≤30亿)→高确定性暴涨
- **超越Iter3 T2-C9h**: R5+121%(5.53%→12.25%), WR-4pp(79.9%→75.91%), 信号-75%(2692→679)
- **核心因子排序**: 振幅≥7%(最强质变) > 涨幅≥5%(方向确认) > 底10%(深底位置) > VR≥1.2(放量确认)
- **状态**: ✅ Iter12最优, 已加入state.history
""")

# T5-C2 high dividend
new_kb_entries.append(f"""
## 2026-05-12 (iter 12) - T5-C2: 高股息+大振幅+中小盘 (T5流派达标)
- **策略**: 底30%(60日) + dv≥3% + PE≤15 + PB≤2 + VR≥1.2 + 振幅≥6% + CM≤50亿
- **指标**: WR_5d=73.67%, ret_5d=5.91%, ret_10d=8.41%, ret_20d=11.13%, Sharpe=4.49, N=1,075
- **状态**: ✅ T5流派Iter12最佳
""")

# T3-C4 panic micro cap
new_kb_entries.append(f"""
## 2026-05-12 (iter 12) - T3-C4: 恐慌放量微盘 (T3流派Iter12最佳)
- **策略**: 恐慌≤-7% + 底15% + 振幅≥7% + VR≥1.5 + CM≤30亿
- **指标**: WR_5d=71.98%, ret_5d=5.94%, ret_10d=9.73%, ret_20d=15.07%, Sharpe=3.33, N=2,168
- **状态**: ✅ T3流派Iter12最佳
""")

# T8-C3 deep amplitude micro cap
new_kb_entries.append(f"""
## 2026-05-12 (iter 12) - T8-C3: 深底大振幅微盘 (T8流派Iter12最佳)
- **策略**: 底10%(60日) + 涨≥3% + 振幅≥6% + VR≥1.3 + CM≤30亿
- **指标**: WR_5d=63.69%, ret_5d=6.05%, ret_10d=6.51%, Sharpe=3.06, N=1,446
- **状态**: ✅ T8流派Iter12最佳
""")

with open(kbfile, "a") as f:
    for entry in new_kb_entries:
        f.write(entry)
print(f"Knowledge base updated with {len(new_kb_entries)} entries!")

# === Step 5: Generate report ===
report = f"""# 策略挖掘报告 — Iteration 12

> **报告生成时间**: 2026-05-12 17:30 UTC+8
> **迭代编号**: 12
> **数据基准**: 2026-05-11

## 📊 本轮概述

**测试规模**: 7个流派 × 共30组组合测试
**达标**: 15/30 (50.0%)
**全局R5纪录**: {state['best_metrics']['ret_5d']}% (未破Iter7 T9-X17的25.76%)
**疲劳计数**: {state['fatigue_count']}/10
"""

# Per-school table
analysts = {}
for r in results:
    a = r['analyst']
    if a not in analysts: analysts[a] = {'total':0,'pass':0,'best':None}
    analysts[a]['total'] += 1
    if r.get('stats') and r['stats'].get('signal_count',0)>=200 and r['stats'].get('wr_5d',0)>=52 and r['stats'].get('ret_5d',0)>=3:
        analysts[a]['pass'] += 1
        if not analysts[a]['best'] or r['stats']['ret_5d'] > analysts[a]['best']['stats']['ret_5d']:
            analysts[a]['best'] = r

report += """
| 流派 | 结果 | 达标率 | 最佳R5 | 最佳WR |
|------|------|--------|--------|--------|
"""
for a_name in ['T2','T3','T5','T6','T7','T8']:
    a = analysts.get(a_name, {'total':0,'pass':0})
    best = a.get('best')
    best_r5 = f"{best['stats']['ret_5d']}%" if best else "—"
    best_wr = f"{best['stats']['wr_5d']}%" if best else "—"
    report += f"| {a_name} | {a['pass']}/{a['total']} ✅ | {a['pass']/a['total']*100:.0f}% | {best_r5} | {best_wr} |\n"

report += f"\n**本轮总达标**: {len(passed)}/30 组 (50.0%)\n"
report += f"**全局纪录 (R5={state['best_metrics']['ret_5d']}%) 未破** — 疲劳计数增至 **{state['fatigue_count']}**\n"

# Top 5
sorted_passed = sorted(passed, key=lambda r: r['stats']['ret_5d'], reverse=True)
report += """
---

## 🏆 Top 5 策略排名

"""
for i, r in enumerate(sorted_passed[:5], 1):
    s = r['stats']
    report += f"""
### {'🥇🥈🥉🏅🎖️'[i-1]} {r['analyst']}-{r['name']}

| 指标 | 值 |
|------|-----|
| 策略 | {r['params']} |
| N | {s['signal_count']} |
| WR_5d | {s['wr_5d']}% |
| R5 | {s['ret_5d']}% |
| R10 | {s['ret_10d']}% |
| R20 | {s['ret_20d']}% |
| Sharpe | {s.get('sharpe_5d',0)} |
"""

# All passed combos
report += """
---

## 全部达标组合

| 流派 | 组合 | N | WR5d | R5d | R10d | R20d | SR5d | 状态 |
|------|------|-----|------|-----|------|------|------|------|
"""
for r in sorted_passed:
    s = r['stats']
    report += f"| {r['analyst']} | {r['name']} | {s['signal_count']} | {s['wr_5d']}% | {s['ret_5d']}% | {s['ret_10d']}% | {s['ret_20d']}% | {s.get('sharpe_5d',0)} | ✅ |\n"

# Key findings
report += """
---

## 关键发现

### ✅ 新验证的有效因子
1. **振幅≥7% + 涨幅≥5% 是最强因子对** — T2-C2 (R5=12.25%, WR=75.91%) 证明深底+大振幅+大阳线+微盘的组合可产生极高确定性暴涨
2. **微盘(CM≤30亿)持续验证为质变因子** — T2-C2(CM≤30亿)的R5比Iter11 X04扩展版(CM≤50亿)高+9.76pp
3. **高股息+大振幅(≥6%)组合有效** — T5-C2 (WR=73.67%, R5=5.91%) 确认dv≥3%是基本面最强激活因子
4. **恐慌放量微盘持续有效** — T3-C4 (R5=5.94%, WR=71.98%, N=2,168) 在Iter11接近达标后成功突破

### ❌ 确认的无效方向
- **底部企稳中大盘(30-100亿)收益不足** — T7-C3 R5=1.89%, T8-C4 R5=1.44%
- **缩量后放量模式R5不足** — T2-C3 (R5=1.76%), 条件放松后收益反而下降

### 疲劳警告
- 全局R5=25.76%纪录(T9-X17, iter7)连续**6轮**未破
- 但本轮T2-C2 (R5=12.25%, WR=75.91%, Sharpe=5.56) 是Iter12最强发现
- WR×Sharpe维度:T2-C2的WR=75.91%+Sharpe=5.56, 稳健最佳仍是T9-X04(WR=82.29%, Sharpe=6.021)

---

## 下一轮建议方向

### 🔴 高优先级
1. **T2-C2扩容**: CM从≤30亿→≤50亿, 或VR从1.2→1.0, 验证容量弹性
2. **T2-C2+T7宏观**: 加入SPX前日上涨或Shibor宽松宏观过滤, 验证WR能否突破80%
3. **T5-C2扩容**: CM从≤50亿→≤100亿, 提升信号量

### 🟡 中优先级
4. **T3-C4扩容**: CM从≤30亿→≤50亿, 验证恐慌策略的容量弹性
5. **T8-C3深度验证**: 底10%+涨≥3%+振幅≥6%+VR≥1.3的最佳参数组合

---

*报告由 Orchestrator 自动生成 — Iteration 12 | 基准日期 2026-05-11 | 2026-05-12 17:30 UTC+8*
"""

# Write report
report_path = f"{STRATEGY_DIR}/reports/mining-all167-iter12-20260512.md"
with open(report_path, "w") as f:
    f.write(report)
print(f"Report written to {report_path}")
print("\nDone! Iteration 12 complete.")
"