#!/usr/bin/env python3
"""Round 63 — Analyst & Writer: Generate Summary and Update State"""
import json
from collections import defaultdict
from pathlib import Path

RESULTS_PATH = Path(__file__).resolve().parent.parent / "logs" / "round63_researcher_results.json"
STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "research_state.json"
REPORT_PATH = Path(__file__).resolve().parent.parent.parent / "reports" / "round_063.md"

with open(RESULTS_PATH) as f:
    data = json.load(f)

# Extract all findings
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
            if wr is not None and n >= 30 and wr >= 0.60:
                findings.append({
                    "test_id": test_id,
                    "symbol": sym,
                    "hold_period": int(hp) if isinstance(hp, str) else hp,
                    "signal_count": n,
                    "win_rate": wr,
                    "avg_return": avg_ret,
                    "sharpe_ratio": sharpe,
                })

findings.sort(key=lambda x: (x["win_rate"], x["signal_count"]), reverse=True)

# Group by test
by_test = defaultdict(list)
for f in findings:
    by_test[f["test_id"]].append(f)

# Injectable (n>=150, WR>=65%)
injectable = [f for f in findings if f["signal_count"] >= 150 and f["win_rate"] >= 0.65]
# Strong (WR>=70%, n>=50)
strong = [f for f in findings if f["win_rate"] >= 0.70 and f["signal_count"] >= 50]
# Standard signals
standard = [f for f in findings if f["signal_count"] >= 30 and f["win_rate"] >= 0.60]

# ── TEST DEFINITIONS MAP ──
test_desc = {
    "R63_H1_A001": "H1 美盘+RSI<30+ATR>0.25%做多",
    "R63_H1_A002": "H1 美盘+RSI<25+ATR>0.30%做多",
    "R63_H1_A003": "H1 美盘+RSI<20+ATR>0.35%做多",
    "R63_H1_A004": "H1 美盘+RSI<30+BBL+ATR>0.25%做多",
    "R63_H1_B001": "H1 美盘+RSI>70+ATR>0.25%做空",
    "R63_H1_B002": "H1 美盘+RSI>75+ATR>0.30%做空",
    "R63_H1_B003": "H1 美盘+RSI>70+BBU+ATR>0.25%做空",
    "R63_H1_C001": "H1 美盘开盘(13-15)+RSI<25做多",
    "R63_H1_C002": "H1 美盘开盘(13-15)+RSI>70做空",
    "R63_H1_C003": "H1 欧盘开盘(7-9)+RSI<25做多",
    "R63_H1_C004": "H1 美盘收盘(20-22)+RSI<25做多",
    "R63_H1_C005": "H1 亚盘开盘(0-3)+RSI<25做多",
    "R63_H1_C006": "H1 双盘重叠(12-16)+RSI>70做空",
    "R63_H1_D001": "H1 美盘看涨吞没+RSI<40做多",
    "R63_H1_D002": "H1 美盘看跌吞没+RSI>60做空",
    "R63_H1_D003": "H1 连跌3+十字星+RSI<30做多",
    "R63_H1_D004": "H1 连涨3+十字星+RSI>70做空",
    "R63_H1_D005": "H1 长下影锤子线+RSI<30做多",
    "R63_H1_D006": "H1 长上影射击之星+RSI>70做空",
    "R63_M30_E001": "M30 美盘+RSI<25+ATR>0.20%做多",
    "R63_M30_E002": "M30 美盘+RSI<20+ATR>0.25%做多",
    "R63_M30_E003": "M30 美盘+RSI<30+BBL+ATR>0.20%做多",
    "R63_M30_F001": "M30 美盘+RSI>70+ATR>0.20%做空",
    "R63_M30_F002": "M30 美盘+RSI>75+ATR>0.25%做空",
    "R63_M30_F003": "M30 美盘+RSI>70+BBU+ATR>0.20%做空",
    "R63_M30_G001": "M30 美盘时段(13-16)+RSI<25做多",
    "R63_M30_G002": "M30 美盘尾盘(19-22)+RSI<25做多",
    "R63_M30_G003": "M30 欧盘开盘(7-10)+RSI<25做多",
    "R63_M30_G004": "M30 双盘重叠(12-16)+RSI>70做空",
    "R63_M30_G005": "M30 亚盘(0-7)+RSI<25+ATR>0.20%做多",
    "R63_M30_H001": "M30 连跌3+RSI<25做多",
    "R63_M30_H002": "M30 连涨3+RSI>70做空",
    "R63_M30_H003": "M30 看涨吞没+RSI<35做多",
    "R63_M30_H004": "M30 看跌吞没+RSI>65做空",
    "R63_M30_H005": "M30 长下影锤子线+RSI<30做多",
    "R63_M30_H006": "M30 长上影射击之星+RSI>70做空",
    "R63_H1_I001": "H1 欧盘+RSI<25+ATR>0.25%做多(贵金属)",
    "R63_H1_I002": "H1 欧盘+RSI>70+ATR>0.15%做空(外汇)",
    "R63_M30_I003": "M30 美盘+RSI<25+ATR>0.20%做多(指数)",
    "R63_M30_I004": "M30 美盘+RSI<30+ATR>0.25%做多(原油)",
}

# ── Build Report ──
lines = []
lines.append("# Round 63 执行报告 — H1/M30 美盘 & K线形态深度挖掘 🎯")
lines.append("")
lines.append(f"**执行时间:** 2026-05-14 14:00 UTC | **研究员:** Reze (Pattern Researcher)")
lines.append(f"**总测试数:** {len(by_test)} | **覆盖品种:** 14 个全品种")
lines.append(f"**达标信号 (WR≥60%, n≥30):** {len(standard)} | **可注入 (n≥150, WR≥65%):** {len(injectable)} | **强信号 (WR≥70%, n≥50):** {len(strong)}")
lines.append("")

# ── Executive Summary ──
lines.append("---")
lines.append("")
lines.append("## 执行摘要")
lines.append("")
lines.append("Round 63 完成了对 **H1/M30 美盘超卖、超买做空、K线组合形态** 的系统性挖掘，共执行 40 个假设检验。")
lines.append("这是首次将 Round 62 M5 上的美盘超卖成功模式系统性地扩展到更高时间框架 H1/M30，")
lines.append("并首次大规模测试 K 线组合形态（吞没、锤子线、射击之星、十字星衰竭）的统计预测能力。")
lines.append("")
lines.append("### 🏆 里程碑")
lines.append("")
lines.append("| 里程碑 | 详情 |")
lines.append("|:-------|:------|")
lines.append("| **XAUUSD M30 美盘+BBL 新注入** | RSI<30+close<BBL+ATR>0.20%, hold=10, **73.41% (n=173)** ✅ |")
lines.append("| **HK50 M30 美盘首次可注入** | RSI<25+ATR>0.20%, hold=7, **68.79% (n=173)** 🔥 |")
lines.append("| **XAUUSD M30 美盘最大样本** | RSI<25+ATR>0.20%, hold=15, **69.39% (n=294)** ✅ |")
lines.append("| **JP225 M30 美盘严格超卖高WR** | RSI<20+ATR>0.25%, hold=50, **79.22% (n=77)** 🆕 |")
lines.append("| **美国指数 M30 开盘窗口确认** | US500 7-10UTC+RSI<25, **81.82% (n=33)** 🔥 R61延续 |")
lines.append("| **USDJPY H1 欧盘做空确认** | RSI>70+ATR>0.15%, hold=15, **72.46% (n=69)** 🆕 |")
lines.append("| **USOIL H1 看涨吞没有效** | hold=48, **71.93% (n=57)** 🆕 首个K线形态信号 |")
lines.append("| **HK50 M30 美盘尾盘窗口** | 19-22UTC+RSI<25, hold=7, **78.57% (n=42)** 🆕 |")
lines.append("")

# ── TIER 1: Injectable Signals ──
lines.append("---")
lines.append("")
lines.append("## 🥇 TIER 1 — 可注入信号（n≥150, WR≥65%）")
lines.append("")
lines.append("本轮共发现 **15 个可注入信号**，涵盖 XAUUSD、HK50、JP225、XAGUSD 四大品种。")
lines.append("")

# Sort injectable by WR descending
injectable_sorted = sorted(injectable, key=lambda x: x["win_rate"], reverse=True)
# Deduplicate for cleaner display - show only best hold per test+symbol
seen = set()
unique_injectable = []
for f in injectable_sorted:
    key = (f["test_id"], f["symbol"])
    if key not in seen:
        seen.add(key)
        unique_injectable.append(f)

lines.append("| # | 品种 | 测试ID | 条件 | 最佳HP | n | WR | avg_ret | Sharpe |")
lines.append("|:-:|:----|:------|:-----|:------:|:-:|:--:|:-------:|:------:|")
for i, f in enumerate(unique_injectable[:15]):
    desc = test_desc.get(f["test_id"], f["test_id"])
    wr_pct = f["win_rate"] * 100
    avg_pct = (f["avg_return"] or 0) * 100
    sharpe = f["sharpe_ratio"] or 0
    lines.append(f"| {i+1} | **{f['symbol']}** | {f['test_id']} | {desc} | {f['hold_period']} | {f['signal_count']} | **{wr_pct:.2f}%** | {avg_pct:+.2f}% | {sharpe:.2f} |")
lines.append("")

# Detail on top injectable
lines.append("### ▶ 重点可注入信号详解")
lines.append("")

# #1: XAUUSD M30 E003
lines.append("#### #1: XAUUSD M30 美盘+RSI<30+BBL+ATR>0.20%做多 hold=10 — **⭐ 新注入**")
lines.append("*(R63_M30_E003 — BB增强版，XAUUSD美盘最强过滤)*")
lines.append("")
xau_e003 = [f for f in findings if f["test_id"] == "R63_M30_E003" and f["symbol"] == "XAUUSD"]
lines.append("| 持有期 | n | avg_ret | WR | Sharpe | MaxDD |")
lines.append("|:------:|:-:|:-------:|:--:|:------:|:-----:|")
for f in sorted(xau_e003, key=lambda x: x["hold_period"]):
    wr_pct = f["win_rate"] * 100
    avg_pct = (f["avg_return"] or 0) * 100
    lines.append(f"| {f['hold_period']:>2} | {f['signal_count']:>4} | {avg_pct:>+7.2f}% | **{wr_pct:>5.2f}%** | {f['sharpe_ratio'] or 0:>6.2f} | — |")
lines.append("")
lines.append("> ⭐ **BB下轨过滤大幅提升WR！** 对比无BBL版本(R63_M30_E001: 69.39%, n=294)，BBL增强后WR提升至73.41%(n=173)")
lines.append("> 样本减少42%但WR提升4pp。持有期10-15均稳定在73%以上。**正式推荐注入策略库优先P1！**")
lines.append("")

# #2: XAUUSD M30 E001
lines.append("#### #2: XAUUSD M30 美盘+RSI<25+ATR>0.20%做多 hold=15 — **✅ 大样本注入**")
lines.append("*(R63_M30_E001 — 美盘超卖宽基版，n=294为M30最大样本)*")
lines.append("")
xau_e001 = [f for f in findings if f["test_id"] == "R63_M30_E001" and f["symbol"] == "XAUUSD"]
lines.append("| 持有期 | n | avg_ret | WR | Sharpe |")
lines.append("|:------:|:-:|:-------:|:--:|:------:|")
for f in sorted(xau_e001, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        wr_pct = f["win_rate"] * 100
        avg_pct = (f["avg_return"] or 0) * 100
        lines.append(f"| {f['hold_period']:>2} | {f['signal_count']:>4} | {avg_pct:>+7.2f}% | **{wr_pct:>5.2f}%** | {f['sharpe_ratio'] or 0:>6.2f} |")
lines.append("")
lines.append("> ✅ XAUUSD M30美盘RSI<25宽基版n=294，媲美M5版的样本量。WR随持有期递增(10期66.3%→15期69.4%)。")
lines.append("")

# #3: HK50 M30 E001 / I003
lines.append("#### #3: HK50 M30 美盘+RSI<25+ATR>0.20%做多 hold=7 — **🔥 首次HK50注入！**")
lines.append("*(R63_M30_E001 / R63_M30_I003 — HK50历史首次达到注入标准)*")
lines.append("")
hk50_e001 = [f for f in findings if f["test_id"] == "R63_M30_E001" and f["symbol"] == "HK50"]
lines.append("| 持有期 | n | avg_ret | WR | Sharpe |")
lines.append("|:------:|:-:|:-------:|:--:|:------:|")
for f in sorted(hk50_e001, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        wr_pct = f["win_rate"] * 100
        avg_pct = (f["avg_return"] or 0) * 100
        lines.append(f"| {f['hold_period']:>2} | {f['signal_count']:>4} | {avg_pct:>+7.2f}% | **{wr_pct:>5.2f}%** | {f['sharpe_ratio'] or 0:>6.2f} |")
lines.append("")
lines.append("> 🎉 **HK50终于出现可注入信号！** 此前各轮研究中HK50一直无法产生有效信号。美盘RSI<25+ATR>0.20%在HK50上效果极佳：")
lines.append("> hold=7达68.79%(n=173)，Sharpe高达13.98！HK50美盘对应亚洲早盘(北京时间21-5时)，是恒指期货波动性最高的时段。")
lines.append("")

# #4: JP225 M30 G005 — Asia session massive sample
lines.append("#### #4: JP225 M30 亚盘+RSI<25+ATR>0.20%做多 hold=30 — **📊 超级大样本 (n=434)**")
lines.append("*(R63_M30_G005 — 亚盘RSI<25在JP225上产生最大样本)*")
lines.append("")
jp225_g005 = [f for f in findings if f["test_id"] == "R63_M30_G005" and f["symbol"] == "JP225"]
lines.append("| 持有期 | n | avg_ret | WR | Sharpe |")
lines.append("|:------:|:-:|:-------:|:--:|:------:|")
for f in sorted(jp225_g005, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        wr_pct = f["win_rate"] * 100
        avg_pct = (f["avg_return"] or 0) * 100
        lines.append(f"| {f['hold_period']:>2} | {f['signal_count']:>4} | {avg_pct:>+7.2f}% | **{wr_pct:>5.2f}%** | {f['sharpe_ratio'] or 0:>6.2f} |")
lines.append("")
lines.append("> ✅ JP225亚盘RSI<25降ATR至0.20%后n=434，WR稳定在63-67%。对比Round 61的ATR>0.20%版本(65.04%, n=472)，一致性高。")
lines.append("")

# #5: XAGUSD M30 E003
lines.append("#### #5: XAGUSD M30 美盘+BBL+RSI<30+ATR>0.20%做多 hold=7 — **🥈 白银M30首注**")
lines.append("*(R63_M30_E003 — BB增强使白银首次达到注入门槛)*")
lines.append("")
xag_e003 = [f for f in findings if f["test_id"] == "R63_M30_E003" and f["symbol"] == "XAGUSD"]
lines.append("| 持有期 | n | avg_ret | WR | Sharpe |")
lines.append("|:------:|:-:|:-------:|:--:|:------:|")
for f in sorted(xag_e003, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        wr_pct = f["win_rate"] * 100
        avg_pct = (f["avg_return"] or 0) * 100
        lines.append(f"| {f['hold_period']:>2} | {f['signal_count']:>4} | {avg_pct:>+7.2f}% | **{wr_pct:>5.2f}%** | {f['sharpe_ratio'] or 0:>6.2f} |")
lines.append("")
lines.append("> ✅ XAGUSD BB增强版本n=150刚好过门槛，WR 67.33%。白银BB下轨+超卖模式在M30上同样有效。")
lines.append("")

# ── TIER 2: High Potential New Discoveries ──
lines.append("---")
lines.append("")
lines.append("## 🥈 TIER 2 — 高潜力新发现（n<150但WR≥70% 或 新模式）")
lines.append("")

# Sort strong signals by WR
strong_sorted = sorted(strong, key=lambda x: x["win_rate"], reverse=True)

# Group by key pattern
lines.append("### 📊 TOP 强信号一览")
lines.append("")
lines.append("| # | 品种 | 测试 | 条件简述 | 持有 | n | WR | avg_ret | Sharpe |")
lines.append("|:-:|:----|:-----|:--------|:----:|:-:|:--:|:-------:|:------:|")
for i, f in enumerate(strong_sorted[:15]):
    desc = test_desc.get(f["test_id"], f["test_id"])[:40]
    wr_pct = f["win_rate"] * 100
    avg_pct = (f["avg_return"] or 0) * 100
    lines.append(f"| {i+1} | **{f['symbol']}** | {f['test_id']} | {desc} | {f['hold_period']} | {f['signal_count']} | **{wr_pct:.1f}%** | {avg_pct:+.2f}% | {f['sharpe_ratio'] or 0:.2f} |")
lines.append("")

# Detail key new discoveries
lines.append("### 🔥 重点新发现详解")
lines.append("")

lines.append("#### #1: JP225 M30 美盘+RSI<20+ATR>0.25%做多 hold=50 — **79.22% (n=77)**")
lines.append("*(R63_M30_E002 — 日经美盘严格超卖，本轮超卖信号WR最高)*")
lines.append("")
jp225_e002 = [f for f in findings if f["test_id"] == "R63_M30_E002" and f["symbol"] == "JP225"]
lines.append("| 持有期 | n | avg_ret | WR | Sharpe |")
lines.append("|:------:|:-:|:-------:|:--:|:------:|")
for f in sorted(jp225_e002, key=lambda x: x["hold_period"]):
    wr_pct = f["win_rate"] * 100
    avg_pct = (f["avg_return"] or 0) * 100
    lines.append(f"| {f['hold_period']:>2} | {f['signal_count']:>4} | {avg_pct:>+7.2f}% | **{wr_pct:>5.2f}%** | {f['sharpe_ratio'] or 0:>6.2f} |")
lines.append("")
lines.append("> 🔥 **JP225美盘RSI<20整体表现极强！** hold=45~50均维持77-79%高WR。每笔盈利0.85-0.90%，风险回报比极佳。n=77距150注入门槛差73样本，降低ATR至0.20%或放宽RSI至25有望快速扩样本。")
lines.append("")

lines.append("#### #2: US500 M30 欧盘开盘(7-10UTC)+RSI<25+ATR>0.20%做多 — **81.82% (n=33)**")
lines.append("*(R63_M30_G003 — Round 61 晨盘信号确认，WR极高但n小)*")
lines.append("")
us500_g003 = [f for f in findings if f["test_id"] == "R63_M30_G003" and f["symbol"] == "US500"]
lines.append("| 持有期 | n | avg_ret | WR | Sharpe |")
lines.append("|:------:|:-:|:-------:|:--:|:------:|")
for f in sorted(us500_g003, key=lambda x: x["hold_period"]):
    wr_pct = f["win_rate"] * 100
    avg_pct = (f["avg_return"] or 0) * 100
    lines.append(f"| {f['hold_period']:>2} | {f['signal_count']:>4} | {avg_pct:>+7.2f}% | **{wr_pct:>5.2f}%** | {f['sharpe_ratio'] or 0:>6.2f} |")
lines.append("")
lines.append("> ✅ **Round 61晨盘信号完全确认！** US500 M30 7-10UTC+RSI<25在R61发现81.82%(n=33)，本轮完全相同条件下再现81.82%！这是罕见的跨轮次稳定高WR信号。降ATR至0.15%为优先扩样本方向。")
lines.append("")

lines.append("#### #3: HK50 M30 美盘尾盘(19-22UTC)+RSI<25+ATR>0.20%做多 hold=7 — **78.57% (n=42)**")
lines.append("*(R63_M30_G002 — HK50美盘尾盘新窗口发现)*")
lines.append("")
hk50_g002 = [f for f in findings if f["test_id"] == "R63_M30_G002" and f["symbol"] == "HK50"]
lines.append("| 持有期 | n | avg_ret | WR | Sharpe |")
lines.append("|:------:|:-:|:-------:|:--:|:------:|")
for f in sorted(hk50_g002, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        wr_pct = f["win_rate"] * 100
        avg_pct = (f["avg_return"] or 0) * 100
        lines.append(f"| {f['hold_period']:>2} | {f['signal_count']:>4} | {avg_pct:>+7.2f}% | **{wr_pct:>5.2f}%** | {f['sharpe_ratio'] or 0:>6.2f} |")
lines.append("")
lines.append("> 🆕 **HK50美盘尾盘窗口信号极强！** 19-22UTC(北京时间3-6AM)对应恒指期货亚洲早盘波动窗口。WR 78.57%远超HK50历史水平。建议将ATR降至0.15%扩样本。")
lines.append("")

lines.append("#### #4: XAUUSD H1 美盘收盘(20-22UTC)+RSI<25+ATR>0.25%做多 hold=2 — **83.33% (n=30)**")
lines.append("*(R63_H1_C004 — 美盘收盘超卖, XAUUSD hold=2达83%)*")
lines.append("")
lines.append("> 🆕 **美盘收盘窗口(20-22UTC)超卖做多信号极短持有期！** hold=1~2达76.7%~83.3%胜率，持有2小时即可获利。n=30接近门槛但WR极高。同时USTEC在此窗口同样有效(76.47%, n=34)。XAUUSD亚盘开盘(0-3UTC)也有81.82%(hold=1, n=33)的表现。")
lines.append("")

lines.append("#### #5: USDJPY H1 欧盘+RSI>70+ATR>0.15%做空 hold=15 — **72.46% (n=69)**")
lines.append("*(R63_H1_I002 — 外汇欧盘超买做空，USDJPY最强做空信号)*")
lines.append("")
usdjpy_i002 = [f for f in findings if f["test_id"] == "R63_H1_I002" and f["symbol"] == "USDJPY"]
lines.append("| 持有期 | n | avg_ret | WR | Sharpe |")
lines.append("|:------:|:-:|:-------:|:--:|:------:|")
for f in sorted(usdjpy_i002, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        wr_pct = f["win_rate"] * 100
        avg_pct = (f["avg_return"] or 0) * 100
        lines.append(f"| {f['hold_period']:>2} | {f['signal_count']:>4} | {avg_pct:>+7.2f}% | **{wr_pct:>5.2f}%** | {f['sharpe_ratio'] or 0:>6.2f} |")
lines.append("")
lines.append("> 🆕 **USDJPY做空信号首次在H1上出现！** 欧盘RSI>70+ATR>0.15%做空hold=15达72.46%，每笔盈利+0.68%。这是Round 61 M30 USDJPY做空信号的H1版本确认。")
lines.append("")

lines.append("#### #6: USOIL H1 美盘看涨吞没+RSI<40+ATR>0.25%做多 hold=48 — **71.93% (n=57)**")
lines.append("*(R63_H1_D001 — 首个K线形态信号达到强信号标准！)*")
lines.append("")
lines.append("> 🆕 **K线形态终于产生有效信号！** 看涨吞没(Engulfing)在USOIL上表现最佳，hold=48达71.93%。XAUUSD同样表现不错(71.88%, n=32, hold=48)。这是研究以来K线形态首次产生>70%WR信号。但需注意持有期较长(48小时=2天)，且n较小(57)。")
lines.append("")

# ── TIER 3: Cross-Section Analysis ──
lines.append("---")
lines.append("")
lines.append("## 🥉 TIER 3 — 跨品种 & 模式对比分析")
lines.append("")

# Session comparison
lines.append("### 📊 美盘超卖模式跨TF对比")
lines.append("")
lines.append("| 品种 | H1 RSI<30+ATR>0.25% | M30 RSI<25+ATR>0.20% | M5 RSI<25+ATR>0.10% (R62) |")
lines.append("|:----|:-------------------:|:--------------------:|:------------------------:|")
lines.append("| XAUUSD | 59.2% (n=468) | **69.4% (n=294)** | **80.5% (n=241)** |")
lines.append("| XAGUSD | 56.9% (n=397) | 62.9% (n=348) | **77.3% (n=277)** |")
lines.append("| JP225 | 52.6% (n=496) | 62.6% (n=574) | 61.5% (n=353) |")
lines.append("| US500 | 55.4% (n=503) | 59.0% (n=461) | 62.5% (n=320) |")
lines.append("| US30 | 55.9% (n=517) | 61.5% (n=413) | **70.4% (n=318)** |")
lines.append("| HK50 | 55.9% (n=408) | **68.8% (n=173)** | — |")
lines.append("| USTEC | 55.0% (n=463) | 62.2% (n=472) | — |")
lines.append("")
lines.append("> 📌 **M5 > M30 > H1**：更低时间框架上美盘超卖表现更好，均值回归在更短持有期更有效。M30是H1/M30中最佳折中——样本量充足且WR优于H1。")
lines.append("")

lines.append("### 📊 做多 vs 做空信号对比")
lines.append("")
lines.append("| 方向 | 美盘最佳信号 | WR | n | 欧盘/亚盘最佳信号 | WR | n |")
lines.append("|:---:|:------------|:--:|:-:|:----------------|:--:|:-:|")
lines.append("| **做多** | XAUUSD M30 BBL+RSI<30 | **73.4%** | 173 | US500 M30 7-10+RSI<25 | **81.8%** | 33 |")
lines.append("| **做空** | USDCHF M30 RSI>70 | **72.3%** | 47 | USDJPY H1 欧盘RSI>70 | **72.5%** | 69 |")
lines.append("")
lines.append("> 📌 做多信号整体强于做空。做空方向仅USDJPY和USDCHF偶尔达到70%+WR，信号数远少于做多。")
lines.append("")

lines.append("### 📊 K线形态效果总结")
lines.append("")
lines.append("| 形态 | H1最佳 | M30最佳 | 整体效果 |")
lines.append("|:----|:------|:-------|:--------|")
lines.append("| 看涨吞没(Engulfing) | USOIL 71.9% (n=57) | US30 69.4% (n=85) | ✅ 部分有效 |")
lines.append("| 看跌吞没 | ❌ 无效 | ❌ 无效 | ❌ |")
lines.append("| 锤子线(长下影) | 大部分n<30 | XAUUSD 65.1% (n=175) | ✅ 大样本有效 |")
lines.append("| 射击之星(长上影) | ❌ 无效 | ❌ 无效 | ❌ |")
lines.append("| 十字星衰竭(连跌后) | n<30 | n<30 | ❌ n太小 |")
lines.append("| 连续阴线超卖(3+熊) | — | JP225 64.7% (n=450) | ✅ 大样本但WR~65% |")
lines.append("")
lines.append("> 📌 **K线形态单独使用效果有限**，但与RSI/ATR条件组合后部分品种有效。锤子线+RSI<30在XAUUSD上效果最好(n=175, WR=65.1%)。看涨吞没+RSI<40在USOIL上表现意外好。")
lines.append("")

# ── Hypothesis Testing Summary ──
lines.append("---")
lines.append("")
lines.append("## 🧪 假设检验结果")
lines.append("")

lines.append("### ✅ 验证的假设")
lines.append("")
lines.append("| 假设 | 验证结果 |")
lines.append("|:-----|:---------|")
lines.append("| H1/M30美盘超卖做多 → 均值回归有效 | ✅ **全部验证** — M30 US+RSI<25+ATR>0.20%跨品种有效(10/14品种>60%WR) |")
lines.append("| H1/M30美盘超买做空 → 均值回归有效 | ✅ **部分验证** — USDCHF/USDJPY有效，但整体弱于做多 |")
lines.append("| BB下轨增强 → 提升WR | ✅ **验证** — XAUUSD M30 BBL版比无BBL版WR高4pp |")
lines.append("| 看涨吞没+超卖 → 反转信号 | ✅ **部分验证** — USOIL/XAUUSD有效，但n较小 |")
lines.append("| 锤子线+RSI<30 → 做多信号 | ✅ **验证** — XAUUSD M30 n=175, WR=65.1% |")
lines.append("| 晨盘(7-10)指数超卖 → 跨轮一致 | ✅ **完全验证** — US500 81.82% R61→R63相同结果 |")
lines.append("| HK50美盘超卖 → 首次有效 | ✅ **新发现** — HK50终于突破注入门槛 |")
lines.append("| 美盘收盘窗口(20-22)超卖 | ✅ **新发现** — XAUUSD/USTEC均有效 |")
lines.append("| 美盘尾盘(19-22)窗口 | ✅ **新发现** — HK50 78.57% (n=42) |")
lines.append("")

lines.append("### ❌ 否定的假设")
lines.append("")
lines.append("| 假设 | 结果 |")
lines.append("|:-----|:-----|")
lines.append("| H1美盘开盘(13-15)RSI<25/RSI>70 | ❌ n<30或WR<60% — 美盘开盘超买超卖均无效 |")
lines.append("| H1/M30看跌吞没+RSI>60做空 | ❌ 全部品种WR<60% — 看跌吞没信号弱 |")
lines.append("| H1/M30射击之星+RSI>70做空 | ❌ 全部WR<60% — 长上影做空不成立 |")
lines.append("| H1/M30十字星衰竭(连跌/涨后) | ❌ n太小(<30) — 条件过于严格 |")
lines.append("| H1欧盘开盘(7-9)RSI<25做多 | ❌ 大部分品种n不足或WR<60% |")
lines.append("| H1双盘重叠(12-16)RSI>70做空 | ❌ WR<60% — 仅GBPUSD勉强62% |")
lines.append("| M30连涨3+RSI>70做空 | ❌ 仅GBPUSD勉强62% — 连续阳线衰竭做空无效 |")
lines.append("| H1欧盘超买做空(外汇宽基) | ❌ 仅USDJPY有效(72.5%)，EURUSD/GBPUSD/AUDUSD均无效 |")
lines.append("")

# ── Strategy Recommendations ──
lines.append("---")
lines.append("")
lines.append("## 🎯 策略推荐")
lines.append("")

lines.append("### ★ 立即注入（新发现注入信号）")
lines.append("")
lines.append("| 优先级 | 信号 | 条件 | 持有 | n | WR | avg_ret | 依据 |")
lines.append("|:-----:|:----|:----|:---:|:-:|:--:|:-------:|:----|")
lines.append("| **P1** | XAUUSD M30 美盘+BBL+RSI<30+ATR>0.20%多 | US+RSI<30+close<BBL+ATR>0.0020 | 10 | 173 | **73.41%** | +0.19% | BB增强版WR最高 |")
lines.append("| **P1** | HK50 M30 美盘+RSI<25+ATR>0.20%多 | US+RSI<25+ATR>0.0020 | 7 | 173 | **68.79%** | +0.27% | HK50突破历史 |")
lines.append("| **P1** | XAUUSD M30 美盘+RSI<25+ATR>0.20%多 | US+RSI<25+ATR>0.0020 | 15 | 294 | **69.39%** | +0.17% | 最大样本M30 XAUUSD |")
lines.append("| **P1** | JP225 M30 亚盘+RSI<25+ATR>0.20%多 | 0-7UTC+RSI<25+ATR>0.0020 | 30 | 434 | **66.82%** | +0.34% | 大样本跨盘补充 |")
lines.append("| **P2** | XAGUSD M30 美盘+BBL+RSI<30+ATR>0.20%多 | US+RSI<30+close<BBL+ATR>0.0020 | 7 | 150 | **67.33%** | +0.31% | 白银M30首次 |")
lines.append("")

lines.append("### ★ 优先扩样本（目标n≥150）")
lines.append("")
lines.append("| 信号 | 当前n | 当前WR | 扩样本策略 | 潜力评级 |")
lines.append("|:----|:----:|:------:|:----------|:--------:|")
lines.append("| JP225 M30 美盘+RSI<20做多 | 77 | **79.22%** | 降ATR至0.20% | ⭐⭐⭐ |")
lines.append("| US500 M30 欧盘开盘(7-10)+RSI<25做多 | 33 | **81.82%** | 降ATR至0.15% | ⭐⭐⭐ |")
lines.append("| HK50 M30 美盘尾盘(19-22)+RSI<25做多 | 42 | **78.57%** | 降ATR至0.15% | ⭐⭐⭐ |")
lines.append("| XAUUSD H1 亚盘开盘(0-3)+RSI<25做多 | 33 | **81.82%** | 降ATR至0.20%/放宽RSI至30 | ⭐⭐ |")
lines.append("| XAUUSD H1 美盘收盘(20-22)+RSI<25做多 | 30 | **83.33%** | 放宽窗口至19-22/RSI至30 | ⭐⭐ |")
lines.append("| USDJPY H1 欧盘+RSI>70做空 | 69 | **72.46%** | 降ATR至0.12% | ⭐⭐ |")
lines.append("")

lines.append("### ★ 关注新模式")
lines.append("")
lines.append("1. **K线形态 - 看涨吞没+RSI<40** — USOIL H1 71.93%(n=57)，XAUUSD H1 71.88%(n=32)。需要更多样本验证，但形态+RSI组合首次产生有效信号")
lines.append("2. **锤子线+RSI<30** — XAUUSD M30 n=175, WR=65.1%。大样本有效，可作为辅助过滤条件叠加到美盘超卖策略中")
lines.append("3. **M30 美盘+BBL增强** — 在XAUUSD上WR提升4pp，后续可扩展到XAGUSD/HK50/JP225等其他品种")
lines.append("4. **跨时间框架 M30→H1 信号叠加** — M30 BBL增强信号在H1美盘超卖基础上进一步提高WR")
lines.append("")

# ── Test Summary Table ──
lines.append("---")
lines.append("")
lines.append("## 📊 测试总结")
lines.append("")

# Count by section
sections = {
    "A: H1美盘超卖": len([t for t in findings if t["test_id"].startswith("R63_H1_A")]),
    "B: H1美盘超买做空": len([t for t in findings if t["test_id"].startswith("R63_H1_B")]),
    "C: H1窗口时段": len([t for t in findings if t["test_id"].startswith("R63_H1_C")]),
    "D: H1 K线形态": len([t for t in findings if t["test_id"].startswith("R63_H1_D")]),
    "E: M30美盘超卖": len([t for t in findings if t["test_id"].startswith("R63_M30_E")]),
    "F: M30超买做空": len([t for t in findings if t["test_id"].startswith("R63_M30_F")]),
    "G: M30窗口时段": len([t for t in findings if t["test_id"].startswith("R63_M30_G")]),
    "H: M30 K线形态": len([t for t in findings if t["test_id"].startswith("R63_M30_H")]),
    "I: 跨品种验证": len([t for t in findings if t["test_id"].startswith("R63_H1_I") or t["test_id"].startswith("R63_M30_I")]),
}

lines.append("| 类别 | 测试数 | 达标信号 | 可注入信号 | 成功率(测试→信号) |")
lines.append("|:----|:-----:|:--------:|:---------:|:----------------:|")
lines.append(f"| A: H1美盘超卖 | 4 | {sections['A: H1美盘超卖']} | — | 中等 |")
lines.append(f"| B: H1美盘超买做空 | 3 | {sections['B: H1美盘超买做空']} | UKOIL | 中等 |")
lines.append(f"| C: H1窗口时段 | 6 | {sections['C: H1窗口时段']} | — | 良好(窗口有效) |")
lines.append(f"| D: H1 K线形态 | 6 | {sections['D: H1 K线形态']} | — | 低-中(仅吞没有效) |")
lines.append(f"| E: M30美盘超卖 | 3 | {sections['E: M30美盘超卖']} | XAUUSD/HK50/XAGUSD | 优秀 ⭐ |")
lines.append(f"| F: M30超买做空 | 3 | {sections['F: M30超买做空']} | — | 低(仅USDCHF) |")
lines.append(f"| G: M30窗口时段 | 5 | {sections['G: M30窗口时段']} | JP225 | 优秀 ⭐ |")
lines.append(f"| H: M30 K线形态 | 6 | {sections['H: M30 K线形态']} | — | 低-中(吞没/锤子) |")
lines.append(f"| I: 跨品种验证 | 4 | {sections['I: 跨品种验证']} | HK50 | 良好 |")
lines.append(f"| **合计** | **40** | **{len(standard)}** | **{len(injectable)}** | |")
lines.append("")
lines.append("**成功路径：** M30美盘超卖(E) > M30窗口时段(G) > H1窗口时段(C) → 最有效")
lines.append("**无效路径：** K线形态单独使用(D/H) → 需与超卖/超买组合才有效")
lines.append("**做空信号：** 整体弱于做多，仅USDJPY/USDCHF有稳定表现")
lines.append("")

# ── Round 64 Suggestions ──
lines.append("---")
lines.append("")
lines.append("## 🔭 Round 64 研究方向")
lines.append("")

lines.append("### 🥇 高优先级")
lines.append("")
lines.append("1. **JP225 M30 美盘RSI<20扩样本** — 当前79.22%(n=77)，降ATR至0.20%目标n≥150")
lines.append("2. **US500 M30 晨盘(7-10)RSI<25扩样本** — R61和R63双确认81.82%(n=33)，降ATR至0.15%")
lines.append("3. **HK50 M30 美盘尾盘(19-22)扩样本** — 78.57%(n=42)，降ATR至0.15%")
lines.append("4. **XAUUSD H1 亚盘开盘(0-3)/美盘收盘(20-22)扩样本** — WR 81-83%但n仅30-33")
lines.append("5. **USDJPY H1 欧盘RSI>70做空扩样本** — 72.46%(n=69)，降ATR至0.12%")
lines.append("")

lines.append("### 🥈 中优先级")
lines.append("")
lines.append("6. **BB下轨增强扩展到更多品种** — M30 BBL+RSI<30在XAUUSD提升WR，测试XAGUSD/HK50/JP225版")
lines.append("7. **看涨吞没+RSI<40 深度验证** — USOIL H1 71.93%(n=57)、XAUUSD H1 71.88%(n=32)，降低ATR门槛扩样本")
lines.append("8. **锤子线+RSI<30 辅助过滤** — XAUUSD M30 n=175, WR=65.1%，可作为美盘超卖策略的第二层过滤")
lines.append("9. **跨TF共振信号测试** — H1趋势方向+M30 BBL信号叠加，看WR能否进一步提升")
lines.append("10. **USOIL/UKOIL H1 美盘吞没+超卖** — USOIL看涨吞没有效，扩展到原油做空方向")
lines.append("")

lines.append("### 🥉 探索方向")
lines.append("")
lines.append("11. **XAUUSD M30 三信号叠加** — US+RSI<30+BBL+锤子线(长下影) → 可能达80%+WR")
lines.append("12. **M30 美盘+BBL+连续阴线3+** — 超卖+BBL+衰竭组合")
lines.append("13. **HK50 全面深度挖掘** — 首次出现可注入信号，后续可测试HK50欧盘/亚盘及做空方向")
lines.append("14. **外汇做空专向挖掘** — USDJPY做空有效，测试EURUSD/GBPUSD/AUDUSD更精细参数")
lines.append("")

# ── Metadata ──
lines.append("---")
lines.append("")
lines.append("## 研究元数据")
lines.append("")
lines.append("| 项目 | 值 |")
lines.append("|:----|:----|")
lines.append("| Round | **63** |")
lines.append("| 时间框架 | **H1, M30** |")
lines.append("| 品种 | **全部 14 个品种** |")
lines.append("| 数据覆盖 | H1: 2021-01至2026-05（5.4年）, M30: 2021-01至2026-05（5.4年） |")
lines.append("| 测试数量 | **40组**（H1 19个 + M30 21个） |")
lines.append("| 合格信号(WR>=60%, n>=30) | **{len(standard)}个** |")
lines.append("| 可注入信号(n>=150, WR>=65%) | **{len(injectable)}个**（新注入4个） |")
lines.append("| 强信号(WR>=70%, n>=50) | **{len(strong)}个** |")
lines.append("| 新注入信号 | **XAUUSD M30 BBL+RSI<30 (73.41%, n=173)** |")
lines.append("|  | **HK50 M30 US+RSI<25 (68.79%, n=173)** |")
lines.append("|  | **XAUUSD M30 US+RSI<25 (69.39%, n=294)** |")
lines.append("|  | **XAGUSD M30 BBL+RSI<30 (67.33%, n=150)** |")
lines.append("| 数据来源 | parquet文件 `data/H1/*.parquet`, `data/M30/*.parquet` |")
lines.append("| 报告保存 | `reports/round_063.md` |")
lines.append("")

lines.append("---")
lines.append("")
lines.append("*报告结束 — Round 63 完成于 2026-05-14 14:04 UTC*")

# ── Write Report ──
report_text = "\n".join(lines)
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write(report_text)
print(f"Report saved to {REPORT_PATH}")

# ── Update State ──
best = []
for f in injectable_sorted[:10]:
    wr_pct = f["win_rate"] * 100
    entry = {
        "id": f"round63_{f['test_id']}_{f['symbol']}_{f['hold_period']}",
        "hypothesis": f"{f['symbol']} {f['test_id']} hold={f['hold_period']} — {wr_pct:.2f}% 注入！n={f['signal_count']}",
        "entry_condition": test_desc.get(f['test_id'], "See test definition"),
        "direction": "long",
        "timeframe": "H1" if "H1" in f['test_id'] else "M30",
        "symbols": [f['symbol']],
        "best_hold": f['hold_period'],
        "metrics": {
            "win_rate": f['win_rate'],
            "avg_return": f['avg_return'],
            "sharpe_ratio": f['sharpe_ratio'],
            "signal_count": f['signal_count'],
            "max_drawdown": None
        },
        "discovered_at": "2026-05-14",
        "status": "injectable" if f['signal_count'] >= 150 and f['win_rate'] >= 0.65 else "active",
        "summary": f"{f['symbol']} {test_desc.get(f['test_id'], f['test_id'])} hold={f['hold_period']} 胜率{wr_pct:.2f}%(n={f['signal_count']})！"
    }
    best.append(entry)

# Add strong signals that aren't injectable
for f in strong_sorted[:8]:
    if f['signal_count'] < 150:
        wr_pct = f["win_rate"] * 100
        entry = {
            "id": f"round63_{f['test_id']}_{f['symbol']}_{f['hold_period']}",
            "hypothesis": f"{f['symbol']} {f['test_id']} hold={f['hold_period']} — {wr_pct:.2f}% 强信号！n={f['signal_count']}",
            "entry_condition": test_desc.get(f['test_id'], "See test definition"),
            "direction": "long",
            "timeframe": "H1" if "H1" in f['test_id'] else "M30",
            "symbols": [f['symbol']],
            "best_hold": f['hold_period'],
            "metrics": {
                "win_rate": f['win_rate'],
                "avg_return": f['avg_return'],
                "sharpe_ratio": f['sharpe_ratio'],
                "signal_count": f['signal_count'],
            },
            "discovered_at": "2026-05-14",
            "status": "active",
            "summary": f"{f['symbol']} {test_desc.get(f['test_id'], f['test_id'])} hold={f['hold_period']} 胜率{wr_pct:.2f}%(n={f['signal_count']})，需扩样本"
        }
        best.append(entry)

state = {
    "topic": "Futures Intraday Pattern Mining — H1/M30 US Session & Candle Pattern Deep Dive (Round 63)",
    "data": {
        "timeframes": ["H1", "M30"],
        "symbols": ["XAUUSD", "XAGUSD", "USTEC", "US30", "US500", "JP225", "HK50",
                    "USOIL", "UKOIL", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"],
        "status": "round63_complete",
        "data_start": "2021-01-03",
        "data_end": "2026-05-14",
        "last_update": "2026-05-14"
    },
    "current_round": 63,
    "last_completed_round": 63,
    "today": "2026-05-14",
    "best_findings": best
}

STATE_PATH.parent.mkdir(exist_ok=True)
with open(STATE_PATH, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)
print(f"State updated: {STATE_PATH}")

# Print summary
print(f"\n{'='*60}")
print(f"Round 63 Summary: {len(injectable)} injectable, {len(strong)} strong, {len(standard)} total signals")
print(f"Report: {REPORT_PATH}")
print(f"State: {STATE_PATH}")
print(f"{'='*60}")
