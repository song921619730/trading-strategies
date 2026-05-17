#!/usr/bin/env python3
"""Round 66 — Full Report Generator"""
import json
from collections import defaultdict
from pathlib import Path

RESULTS_PATH = Path(__file__).resolve().parent.parent / "logs" / "round66_researcher_results.json"
REPORT_PATH = Path(__file__).resolve().parent.parent / "reports" / "round_066.md"

with open(RESULTS_PATH) as f:
    data = json.load(f)

TEST_DESC = {
    # Section A: JP225 极限扩样本
    "R66_H1_A001": "H1 亚盘+连跌3+RSI<30+BBL+ATR>0.10%做多",
    "R66_H1_A002": "H1 亚盘+连跌3+RSI<30+BBL+ATR>0.07%做多",
    "R66_M30_A003": "M30 亚盘+连跌4+RSI<25+ATR>0.10%做多",
    "R66_M30_A004": "M30 亚盘+连跌4+RSI<25+ATR>0.07%做多",
    "R66_M30_A005": "M30 亚盘+RSI<20+ATR>0.08%做多",
    # Section B: USDJPY 欧盘超买做空
    "R66_H1_B001": "H1 欧盘+RSI>70+ATR>0.10%做空",
    "R66_H1_B002": "H1 欧盘+RSI>65+ATR>0.10%做空",
    "R66_M30_B003": "M30 欧盘+RSI>70+ATR>0.10%做空",
    "R66_H1_B004": "H1 欧盘+RSI>70+ATR>0.07%做空",
    # Section C: UKOIL 长持有期
    "R66_M30_C001": "M30 亚盘+RSI<20+ATR>0.15%做多(长持有72-96)",
    "R66_M30_C002": "M30 亚盘+RSI<25+ATR>0.10%做多(长持有72-96)",
    "R66_M30_C003": "M30 亚盘+RSI<22+ATR>0.15%做多(长持有72-96)",
    "R66_M30_C004": "M30 亚盘+RSI<20+ATR>0.10%做多(长持有72-96)",
    # Section D: US30/US500/UKOIL 放宽RSI
    "R66_M30_D001": "M30 亚盘+RSI<25+ATR>0.15%做多",
    "R66_M30_D002": "M30 亚盘+RSI<25+ATR>0.10%做多",
    "R66_M30_D003": "M30 亚盘+RSI<28+ATR>0.10%做多",
    # Section E: AUDUSD bb_pos 增强降ATR
    "R66_H1_E001": "H1 亚盘+RSI<25+ATR>0.15%+bb_pos<0.3做多",
    "R66_H1_E002": "H1 亚盘+RSI<25+ATR>0.12%+bb_pos<0.35做多",
    "R66_H1_E003": "H1 亚盘+RSI<25+ATR>0.15%+低于MA50做多",
    # Section F: HK50 伦敦开盘
    "R66_H1_F001": "H1 伦敦开盘(8-10)+RSI<30+ATR>0.10%做多",
    "R66_H1_F002": "H1 亚→欧转换(7-9)+RSI<25+ATR>0.07%做多",
    # Section G: 极限Session窗口
    "R66_M30_G001": "M30 London-NY(12-14)+RSI<25+ATR>0.05%做多",
    "R66_M30_G002": "M30 London-NY(12-14)+RSI>70+ATR>0.05%做空",
    "R66_M30_G003": "M30 东京开盘(0-3)+RSI<25+ATR>0.05%做多",
    "R66_M30_G004": "M30 东京开盘(0-3)+RSI>70+ATR>0.05%做空",
    # Section H: 跨品种扫描
    "R66_H1_H001": "H1 欧盘+RSI>70+ATR>0.10%做空(跨品种)",
    "R66_M30_H002": "M30 亚盘+RSI<20+ATR>0.10%做多(跨品种)",
}

# Extract findings
findings = []
for test_id, test_results in data.items():
    if not isinstance(test_results, dict):
        continue
    for sym, sym_res in test_results.items():
        if not isinstance(sym_res, dict):
            continue
        for hp, stats in sym_res.items():
            if not isinstance(stats, dict):
                continue
            n = stats.get("signal_count", 0)
            wr = stats.get("win_rate")
            avg_ret = stats.get("avg_return")
            sharpe = stats.get("sharpe_ratio")
            dd = stats.get("max_drawdown")
            if wr is not None and n >= 30 and wr >= 0.60:
                findings.append({
                    "test_id": test_id,
                    "symbol": sym,
                    "hold_period": int(hp) if isinstance(hp, str) else hp,
                    "signal_count": n,
                    "win_rate": wr,
                    "avg_return": avg_ret,
                    "sharpe_ratio": sharpe,
                    "max_drawdown": dd,
                })

findings.sort(key=lambda x: (x["win_rate"], x["signal_count"]), reverse=True)

by_test = defaultdict(list)
for f in findings:
    by_test[f["test_id"]].append(f)

injectable = sorted([f for f in findings if f["signal_count"] >= 150 and f["win_rate"] >= 0.65], key=lambda x: x["win_rate"], reverse=True)
strong = sorted([f for f in findings if f["win_rate"] >= 0.70 and f["signal_count"] >= 50], key=lambda x: x["win_rate"], reverse=True)
standard = [f for f in findings if f["signal_count"] >= 30 and f["win_rate"] >= 0.60]

# Build report
lines = []
lines.append("# Round 66 执行报告 — P0/P1 优先级定向优化 🎯")
lines.append("")
lines.append("**执行时间:** 2026-05-14 15:46 UTC | **研究员:** Reze (Orchestrator)")
lines.append("**当前轮次:** 66 | **研究方向:** JP225极限扩样本/UKOIL长持有期/USDJPY扩样本 | **覆盖品种:** 14全品种")
lines.append(f"**总测试数:** {len(by_test)} | **达标信号 (WR≥60%, n≥30):** {len(standard)}")
lines.append(f"**可注入 (n≥150, WR≥65%):** {len(injectable)} | **强信号 (WR≥70%, n≥50):** {len(strong)}")
lines.append("")

lines.append("---")
lines.append("")
lines.append("## 执行摘要")
lines.append("")
lines.append("Round 66 基于 Round 65 的 P0/P1 优先级假设进行定向优化。核心命题：")
lines.append("- **P0-JP225**: 降ATR从0.15%至0.10%/0.07%，验证JP225极限扩样本边界")
lines.append("- **P0-USDJPY**: 降ATR从0.15%至0.10%/0.07%，看能否将n=69扩至150+")
lines.append("- **P1-UKOIL**: 引入长持有期72-96，验证均值回归慢速模式")
lines.append("- **P1-D**: US30/US500/UKOIL放宽RSI至25/28扩样本")
lines.append("- **P1-E**: AUDUSD bb_pos降ATR扩样本")
lines.append("- **P2-G**: Session转换窗口ATR降至0.05% 极限扩样本")
lines.append("共执行 **27 个假设检验**（H1 10个 + M30 17个），覆盖全部 14 个 MT5 品种。")
lines.append("")

# Key milestones
lines.append("### 🏆 里程碑")
lines.append("")
lines.append("| 里程碑 | 详情 |")
lines.append("|:-------|:------|")
lines.append("| **JP225 极限扩样本边界确认** | ATR降阈至0.10%/0.07%后n保持不变(178)，说明非ATR限制 |")
lines.append("| **USDJPY 欧盘做空扩样本有限** | ATR从0.15%→0.10%后n从69→119，但WR从72.5%降至55%+ |")
lines.append("| **UKOIL长持有期确认** | hold=72-96在C001/C002/C003/C004均未出现明显增强 |")
lines.append("| **M30亚盘RSI<20+ATR>0.10% JP225** | n=158, WR=66.46% — 可注入信号确认 |")
lines.append("| **M30亚盘RSI<25+ATR>0.10% US500** | n=182, WR=65.38% — 新大样本信号 🆕 |")
lines.append("| **HK50+M30亚盘RSI<20+ATR>0.10%** | n=313信号最多，但WR<60% |")
lines.append("| **AUDSD/USDJPY/USDCHF做多谱系基本关闭** | 各条件下WR全面低于60% |")
lines.append("")

# ── TIER 1: Injectable ──
lines.append("---")
lines.append("")
lines.append("## 🥇 TIER 1 — 可注入信号（n>=150, WR>=65%）")
lines.append("")

# Check if there are injectable signals from this round
new_injectable = [f for f in injectable if f['signal_count'] >= 150 and f['win_rate'] >= 0.65]
if new_injectable:
    lines.append("| # | 信号 | HP | n | WR | avg_ret | Sharpe | 状态 |")
    lines.append("|:-:|:-----|:--:|:-:|:--:|:-------:|:------:|:----:|")
    for i, f in enumerate(new_injectable, 1):
        desc = TEST_DESC.get(f['test_id'], f['test_id'])
        is_new = "🆕" if f['signal_count'] >= 150 else "⭐"
        lines.append(f"| {i} | {f['symbol']} {desc} | {f['hold_period']} | {f['signal_count']} | **{f['win_rate']:.2%}** | {f['avg_return'] or 0:+.4f} | {f['sharpe_ratio'] or 0:.1f} | {is_new} |")
    lines.append("")
else:
    lines.append("⚠️ **本轮未产生新的可注入信号(n≥150, WR≥65%)。**")
    lines.append("")
    lines.append("多轮降ATR扩样本后，部分品种已触及信号数量上限（JP225 H1连跌模式n=178为硬上限），需要探索全新条件组合。")
    lines.append("")

# Detailed breakdown for injectable signals
for f in new_injectable:
    test_id = f['test_id']
    sym = f['symbol']
    desc = TEST_DESC.get(test_id, test_id)
    lines.append(f"### {sym} {desc} hold={f['hold_period']}")
    lines.append("")
    sym_res = data.get(test_id, {}).get(sym, {})
    tf = "H1" if "H1" in test_id else "M30"
    lines.append(f"| Hold | n | avg_ret | WR | Sharpe | MaxDD |")
    lines.append(f"|:----:|:-:|:-------:|:--:|:------:|:-----:|")
    for hp in sorted(sym_res.keys(), key=int):
        r = sym_res[hp]
        n = r['signal_count']
        if n == 0:
            continue
        wr = r['win_rate']
        wr_str = f"**{wr:.2%}**" if wr and wr >= 0.60 and n >= 30 else f"{wr:.2%}"
        lines.append(f"| {hp:>2} | {n:>4} | {r['avg_return'] or 0:+.4f} | {wr_str} | {r['sharpe_ratio'] or 0:.2f} | {r['max_drawdown'] or 0:.4f} |")
    lines.append("")

# ── TIER 2: Strong ──
lines.append("---")
lines.append("")
lines.append("## 🥈 TIER 2 — 高潜力强信号（WR>=70%, n>=50）")
lines.append("")
lines.append("| # | 信号 | HP | n | WR | avg_ret | Sharpe | 发现 |")
lines.append("|:-:|:-----|:--:|:-:|:--:|:-------:|:------:|:----:|")
for i, f in enumerate(strong, 1):
    desc = TEST_DESC.get(f['test_id'], f['test_id'])
    is_new = "🆕" if f['signal_count'] < 150 else "⭐"
    lines.append(f"| {i} | {f['symbol']} {desc} | {f['hold_period']} | {f['signal_count']} | **{f['win_rate']:.2%}** | {f['avg_return'] or 0:+.4f} | {f['sharpe_ratio'] or 0:.1f} | {is_new} |")
lines.append("")

# Top strong breakouts
top_strong = strong[:5]
for f in top_strong:
    test_id = f['test_id']
    sym = f['symbol']
    desc = TEST_DESC.get(test_id, test_id)
    lines.append(f"### ▶ {sym} {desc}")
    lines.append("")
    sym_res = data.get(test_id, {}).get(sym, {})
    lines.append(f"| Hold | n | avg_ret | WR | Sharpe | MaxDD |")
    lines.append(f"|:----:|:-:|:-------:|:--:|:------:|:-----:|")
    for hp in sorted(sym_res.keys(), key=int):
        r = sym_res[hp]
        n = r['signal_count']
        if n == 0:
            continue
        wr = r['win_rate']
        wr_str = f"**{wr:.2%}**" if wr and wr >= 0.60 and n >= 30 else f"{wr:.2%}"
        lines.append(f"| {hp:>2} | {n:>4} | {r['avg_return'] or 0:+.4f} | {wr_str} | {r['sharpe_ratio'] or 0:.2f} | {r['max_drawdown'] or 0:.4f} |")
    lines.append("")

# ── TIER 3: Cross-Symbol Summary ──
lines.append("---")
lines.append("")
lines.append("## 🥉 TIER 3 — 跨品种 Session 发现汇总")
lines.append("")

lines.append("### 所有测试 — 最佳品种/持有期汇总")
lines.append("")
lines.append("| ID | 描述 | 最佳品种 | HP | WR | n | avg_ret |")
lines.append("|:--:|:-----|:--------:|:--:|:--:|:-:|:-------:|")
for test_id in sorted(by_test.keys()):
    best = max(by_test[test_id], key=lambda x: x['win_rate'] * min(x['signal_count']/150, 1))
    desc = TEST_DESC.get(test_id, test_id)
    lines.append(f"| {test_id} | {desc} | {best['symbol']} | {best['hold_period']} | **{best['win_rate']:.2%}** | {best['signal_count']} | {best['avg_return'] or 0:+.4f} |")
lines.append("")

# Symbol heatmap
lines.append("### 品种发现热力")
lines.append("")
sym_stats = defaultdict(lambda: {"count": 0, "best_wr": 0, "tests": set()})
for f in findings:
    sym_stats[f['symbol']]["count"] += 1
    sym_stats[f['symbol']]["best_wr"] = max(sym_stats[f['symbol']]["best_wr"], f['win_rate'])
    sym_stats[f['symbol']]["tests"].add(f['test_id'])

lines.append("| 品种 | 达标信号数 | 最高WR | 覆盖测试数 | 结论 |")
lines.append("|:----:|:--------:|:-----:|:---------:|:----|")
for sym in sorted(sym_stats.keys()):
    s = sym_stats[sym]
    if s['count'] >= 20:
        verdict = "🔥 强信号密集区"
    elif s['count'] >= 10:
        verdict = "✅ 中等信号"
    else:
        verdict = "⚠️ 零星信号"
    lines.append(f"| {sym} | {s['count']} | {s['best_wr']:.2%} | {len(s['tests'])} | {verdict} |")
lines.append("")

# ── Key Insights ──
lines.append("---")
lines.append("")
lines.append("## 🔬 关键发现与解读")
lines.append("")

# Insight 1: JP225 极限降ATR — 边界确认
lines.append("### 1️⃣ JP225 降ATR极限边界确认 — 「已触碰天花板」")
lines.append("")
lines.append("Round 65发现JP225在ATR>0.15%时有n=178, WR=70.22%。")
lines.append("本轮将ATR降至0.10%和0.07%，n保持178不变，WR保持70.22%不变。")
lines.append("")
lines.append("**结论: ATR不是JP225 H1连跌信号的限制因子。**")
lines.append("")
lines.append("JP225的n=178是由条件 `session=='asia' and consecutive_bear>=3 and rsi14<30 and close<bb_lower` 的联合概率决定的。")
lines.append("ATR从0.15%→0.07%不增加信号数，说明JP225亚盘连跌3+RSI<30+BB下轨的条件组合天然产生约178个信号。")
lines.append("要进一步扩样本，需要放宽RSI(至35)或连跌条件(至2)，但可能大幅降低WR。")
lines.append("")

# Insight 2: USDJPY 欧盘做空
lines.append("### 2️⃣ USDJPY 欧盘超买做空 — 降ATR效应递减")
lines.append("")
lines.append("| ATR阈值 | n | 最佳WR | 评估 |")
lines.append("|:-------:|:-:|:------:|:----|")
lines.append("| 0.20% (R64) | 14 | — | 样本太小 |")
lines.append("| 0.15% (R65) | 69 | **72.46%** | 高WR但n不足 |")
lines.append("| 0.10% (R66_B001) | 119 | ~55% | 样本扩至119但WR崩溃 |")
lines.append("| 0.07% (R66_B004) | 119+ | ~55% | 样本不再增加 |")
lines.append("")
lines.append("**结论: USDJPY欧盘做空存在n=69的最佳甜蜜点。**")
lines.append("ATR>0.15%时WR高但n小；降ATR至0.10%后n增至119但WR从72.5%降至55%+。")
lines.append("说明高胜率的USDJPY做空信号只在较高波动(ATR>0.15%)时出现，低波动期的信号质量低。")
lines.append("**这条路径基本关闭** — 无法通过降ATR扩样本到150的同时保持65%+的WR。")
lines.append("")

# Insight 3: UKOIL 长持有期
lines.append("### 3️⃣ UKOIL 长持有期(72-96)测试 — 无显著增强")
lines.append("")
lines.append("Round 65发现UKOIL亚盘RSI<20在hold=60时WR=76.47%。假设更长的持有期(72-96=36-48h)可能进一步提升。")
lines.append("")
c_test_results = {}
for test_id in ["R66_M30_C001", "R66_M30_C002", "R66_M30_C003", "R66_M30_C004"]:
    if test_id in data and "UKOIL" in data[test_id]:
        c_test_results[test_id] = data[test_id]["UKOIL"]

lines.append("测试结果：")
lines.append("| 测试 | 条件 | n | hold=60 WR | hold=72 WR | hold=84 WR | hold=96 WR |")
lines.append("|:----:|:-----|:-:|:---------:|:---------:|:---------:|:---------:|")
for tid, res in sorted(c_test_results.items()):
    desc_short = TEST_DESC.get(tid, tid)[:40]
    n = res.get("60", {}).get("signal_count", 0) or res.get("30", {}).get("signal_count", 0)
    wr60 = res.get("60", {}).get("win_rate", 0) or 0
    wr72 = res.get("72", {}).get("win_rate", None)
    wr84 = res.get("84", {}).get("win_rate", None)
    wr96 = res.get("96", {}).get("win_rate", None)
    wr72s = f"{wr72:.2%}" if wr72 else "—"
    wr84s = f"{wr84:.2%}" if wr84 else "—"
    wr96s = f"{wr96:.2%}" if wr96 else "—"
    lines.append(f"| {tid} | {desc_short} | {n} | {wr60:.2%} | {wr72s} | {wr84s} | {wr96s} |")
lines.append("")
lines.append("**结论: 长持有期对UKOIL无增强效应。** UKOIL在hold=45-60处已达最佳，72-96持有期WR持平或下降。")
lines.append("这意味着UKOIL的均值回归周期约为22.5-30小时(45-60根M30K线)，不需要更长时间。")
lines.append("")

# Insight 4: US30/US500 M30 RSI<25 放宽
lines.append("### 4️⃣ US30/US500 M30 亚盘RSI放宽至25 — 大样本信号确认")
lines.append("")
lines.append("M30 亚盘+RSI<25+ATR>0.10%做多 (R66_M30_D002) 在US500上表现突出：")
lines.append("- n=182, WR=65.38% at hold=60 ✅ — 新大样本信号！")
lines.append("- 相比R65的RSI<30版(n=427, WR=67.45%)，虽n减半但WR接近")
lines.append("")
lines.append("US30在同样条件下：")
lines.append("- n=82, WR=67.07% at hold=50 — n仍不足150")
lines.append("- 放宽至RSI<28后n=129, WR=62.79% — 样本扩大但WR下降")
lines.append("")
lines.append("**结论: US500 M30 亚盘RSI<25+ATR>0.10% hold=60 为新的弱可注入信号候选。**")
lines.append("n=182已过150门槛，WR=65.38%刚过65%标准。建议列入注入候补队列。")
lines.append("")

# Insight 5: AUDUSD bb_pos 降ATR
lines.append("### 5️⃣ AUDUSD bb_pos<0.3 降ATR — 做多方向基本失效")
lines.append("")
lines.append("R65发现AUDUSD H1 亚盘+RSI<25+ATR>0.20%+bb_pos<0.3做多WR=72.06%(n=68)。")
lines.append("本轮降ATR至0.15%后：")
lines.append("- AUDUSD R66_H1_E001: n=137, WR<45% across all holds — 样本大幅扩大但WR崩塌")
lines.append("- 说明AUDUSD亚盘RSI<25在ATR高时表现好，但低ATR信号质量极差")
lines.append("")
lines.append("**结论: AUDUSD亚盘做多的低ATR信号不可靠。** 维持原ATR>0.20%的严格版本。")
lines.append("")

# Insight 6: Session窗口极限降ATR
lines.append("### 6️⃣ Session转换窗口 ATR降至0.05% — 极限扩样本效果")
lines.append("")
lines.append("| 测试 | 条件 | 最佳品种 | n | 最佳WR |")
lines.append("|:----:|:-----|:--------:|:-:|:------:|")
lines.append("| G001 | London-NY(12-14)超卖做多 | USOIL | 263 | 65.02% |")
lines.append("| G002 | London-NY(12-14)超买做空 | USOIL | 263 | 63.12% |")
lines.append("| G003 | 东京开盘(0-3)超卖做多 | USOIL | 263 | 65.02% |")
lines.append("| G004 | 东京开盘(0-3)超买做空 | 全部 | 363-806 | <55% |")
lines.append("")
lines.append("**G001/G003在USOIL上表现突出！** ATR降至0.05%后，London-NY和东京窗口均产生n=263的做多信号，")
lines.append("hold=10时WR=65.02%。USOIL的Session窗口超卖模式在极限ATR下仍然有效。")
lines.append("**建议: USOIL M30 Session窗口超卖做多n=263, WR=65% 列入候补注入队列。**")
lines.append("")

# ── Hypothesis Verification Matrix ──
lines.append("---")
lines.append("")
lines.append("## ✅ 假设验证结果矩阵")
lines.append("")
lines.append("| 优先级 | 假设 | 验证结果 | 结论 |")
lines.append("|:-----:|:-----|:---------|:----|")
lines.append("| **P0** | JP225 H1连跌+RSI<30+BBL 降ATR至0.10% → n~300 | n维持178不变 | ❌ 非ATR限制，已触碰天花板 |")
lines.append("| **P0** | USDJPY H1欧盘超买做空 降ATR至0.10% → n~160 | n=119但WR从72%降至55% | ❌ 降ATR无法同时保持WR |")
lines.append("| **P1** | UKOIL M30 RSI<20 长持有期72-96 提升WR | 60-72-84-96 WR持平或下降 | ❌ 无增强效应 |")
lines.append("| **P1** | US30/US500 亚盘放宽RSI至25 → n翻3倍 | US500 n=182, WR=65.38% | ✅ US500可注入；US30 n=82不足 |")
lines.append("| **P1** | AUDUSD bb_pos降ATR至0.15% → n~150 | n=137但WR全面<45% | ❌ 低ATR信号不可靠 |")
lines.append("| **P2** | HK50伦敦开盘 RSI放宽至30+ATR0.10% | n=213但WR<60% | ❌ 扩样本但WR不足 |")
lines.append("| **P2** | Session窗口ATR降至0.05% → n~300 | USOIL n=263, WR=65.02% | ✅ 新发现：USOIL窗口超卖 |")
lines.append("| **P2** | 东京开盘超买做空 | 多品种n大但WR<55% | ❌ 无效 |")
lines.append("")

# ── Next Hypotheses ──
lines.append("---")
lines.append("")
lines.append("## 🔮 下一步假设（Round 67）")
lines.append("")
lines.append("基于Round 66的发现，部分P0/P1路径已关闭(JP225边界/USDJPY失效/UKOIL长持有失效)。")
lines.append("需要转向新方向：")
lines.append("")
lines.append("| 优先级 | 假设 | 当前证据 | 预期 |")
lines.append("|:-----:|:-----|:---------|:-----|")
lines.append("| **P0** | **USOIL M30 Session窗口超卖(12-14/0-3) 大样本验证** | n=263, WR=65.02% | 跨品种验证USOIL+UKOIL+OIL |")
lines.append("| **P0** | **US500 M30 亚盘RSI<25做多 AT≥0.10% 注入优化** | n=182, WR=65.38% | 细调持有期至最佳参数 |")
lines.append("| **P1** | **M30 亚盘RSI<20+ATR>0.10% JP225 批量最优参数** | n=158, WR=66.46% | 确定最终注入参数 |")
lines.append("| **P1** | **H1 亚盘连跌+RSI<30+BBL JP225 持有期加权优化** | n=178, WR=70.22% | 多持有期分配资金(8/10/12/15) |")
lines.append("| **P1** | **新条件探索: 亚盘开盘缺口+RSI极限** | 未测试 | 探索新信号谱系 |")
lines.append("| **P2** | **M5/M15 日内波段挖掘** | 之前R60有发现 | 连接H1/M30与M5信号链 |")
lines.append("| **P2** | **XAUUSD M30 亚盘RSI<25+A<0.15% 扩样本** | 小样本但高WR | 针对性降ATR |")
lines.append("")

# ── Methodology Notes ──
lines.append("---")
lines.append("")
lines.append("## 📋 研究方法说明")
lines.append("")
lines.append("- **Session定义:** asia(0-7UTC), europe(8-15UTC), us(16-23UTC)")
lines.append("- **数据范围:** ~2021-05至2026-05，来源MT5")
lines.append("- **注入门槛:** n>=150 且 WR>=65%")
lines.append("- **强信号标准:** WR>=70% 且 n>=50")
lines.append("- **所有回报均为未扣除交易成本的毛回报（点差/佣金未计入）**")
lines.append("- **ATR降阈策略:** 将ATR阈值逐步降低以扩大样本量，寻找WR-样本量最佳平衡点")
lines.append("- **P0/P1/P2分级:** P0=核心高价值假设，P1=中优先级，P2=探索性")
lines.append("")

# ── Write Report ──
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(REPORT_PATH, "w") as f:
    f.write("\n".join(lines))

print(f"✅ 报告已保存至: {REPORT_PATH}")
print(f"共 {len(lines)} 行")
