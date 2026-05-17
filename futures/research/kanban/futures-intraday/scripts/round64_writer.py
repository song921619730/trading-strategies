#!/usr/bin/env python3
"""Round 64 — Full Report Generator"""
import json
from collections import defaultdict
from pathlib import Path

RESULTS_PATH = Path(__file__).resolve().parent.parent / "logs" / "round64_researcher_results.json"
REPORT_PATH = Path(__file__).resolve().parent.parent.parent / "reports" / "round_064.md"

with open(RESULTS_PATH) as f:
    data = json.load(f)

# ── Test Description Map ──
TEST_DESC = {
    # H1 Asia Long
    "R64_H1_A001": "H1 亚盘+RSI<30+ATR>0.20%做多",
    "R64_H1_A002": "H1 亚盘+RSI<25+ATR>0.25%做多",
    "R64_H1_A003": "H1 亚盘+RSI<30+BBL+ATR>0.20%做多",
    "R64_H1_A004": "H1 亚盘+连跌3+RSI<35+ATR>0.20%做多",
    "R64_H1_A005": "H1 亚盘+RSI<25+close<MA50+ATR>0.20%做多",
    # H1 Asia Short
    "R64_H1_B001": "H1 亚盘+RSI>70+ATR>0.20%做空",
    "R64_H1_B002": "H1 亚盘+RSI>75+ATR>0.25%做空",
    "R64_H1_B003": "H1 亚盘+RSI>70+BBU+ATR>0.20%做空",
    # H1 Europe Long
    "R64_H1_C001": "H1 欧盘+RSI<30+ATR>0.20%做多",
    "R64_H1_C002": "H1 欧盘+RSI<25+ATR>0.25%做多",
    "R64_H1_C003": "H1 欧盘+RSI<30+BBL+ATR>0.20%做多",
    "R64_H1_C004": "H1 欧盘+连跌3+RSI<35+ATR>0.20%做多",
    "R64_H1_C005": "H1 欧盘+RSI<25+close<MA50+ATR>0.20%做多",
    # H1 Europe Short
    "R64_H1_D001": "H1 欧盘+RSI>70+ATR>0.20%做空",
    "R64_H1_D002": "H1 欧盘+RSI>75+ATR>0.25%做空",
    "R64_H1_D003": "H1 欧盘+RSI>70+BBU+ATR>0.20%做空",
    # H1 Transitions
    "R64_H1_E001": "H1 亚→欧(7-9)+RSI<25做多",
    "R64_H1_E002": "H1 欧→美(15-17)+RSI>70做空",
    "R64_H1_E003": "H1 London-NY重叠(12-14)+RSI<25做多",
    "R64_H1_E004": "H1 London-NY重叠(12-14)+RSI>70做空",
    # H1 Open Windows
    "R64_H1_F001": "H1 伦敦开盘(8-10)+RSI<25做多",
    "R64_H1_F002": "H1 东京开盘(0-3)+RSI<25做多",
    # H1 Candle Asia
    "R64_H1_L001": "H1 亚盘看涨吞没+RSI<40做多",
    "R64_H1_L002": "H1 亚盘看跌吞没+RSI>60做空",
    "R64_H1_L003": "H1 欧盘看涨吞没+RSI<40做多",
    "R64_H1_L004": "H1 欧盘看跌吞没+RSI>60做空",
    # M30 Asia Long
    "R64_M30_G001": "M30 亚盘+RSI<25+ATR>0.15%做多",
    "R64_M30_G002": "M30 亚盘+RSI<20+ATR>0.20%做多",
    "R64_M30_G003": "M30 亚盘+RSI<25+BBL+ATR>0.15%做多",
    "R64_M30_G004": "M30 亚盘+连跌3+RSI<30+ATR>0.15%做多",
    # M30 Asia Short
    "R64_M30_H001": "M30 亚盘+RSI>70+ATR>0.15%做空",
    "R64_M30_H002": "M30 亚盘+RSI>75+ATR>0.20%做空",
    "R64_M30_H003": "M30 亚盘+RSI>70+BBU+ATR>0.15%做空",
    # M30 Europe Long
    "R64_M30_I001": "M30 欧盘+RSI<25+ATR>0.15%做多",
    "R64_M30_I002": "M30 欧盘+RSI<20+ATR>0.20%做多",
    "R64_M30_I003": "M30 欧盘+RSI<25+BBL+ATR>0.15%做多",
    "R64_M30_I004": "M30 欧盘+连跌3+RSI<30+ATR>0.15%做多",
    # M30 Europe Short
    "R64_M30_J001": "M30 欧盘+RSI>70+ATR>0.15%做空",
    "R64_M30_J002": "M30 欧盘+RSI>75+ATR>0.20%做空",
    "R64_M30_J003": "M30 欧盘+RSI>70+BBU+ATR>0.15%做空",
    # M30 Transitions
    "R64_M30_K001": "M30 亚→欧(7-9)+RSI<25做多",
    "R64_M30_K002": "M30 欧→美(15-17)+RSI>70做空",
    "R64_M30_K003": "M30 London-NY重叠(12-14)+RSI<25做多",
    "R64_M30_K004": "M30 London-NY重叠(12-14)+RSI>70做空",
    "R64_M30_K005": "M30 伦敦开盘(8-10)+RSI<25做多",
    "R64_M30_K006": "M30 东京开盘(0-3)+RSI<25做多",
}

# ── Extract Findings ──
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
                direction = "LONG" if avg_ret and avg_ret >= 0 else "SHORT"
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

# ── Build Report ──
lines = []
lines.append("# Round 64 执行报告 — 欧盘/亚盘 Session 深度挖掘 🌏")
lines.append("")
lines.append("**执行时间:** 2026-05-14 06:14 UTC | **研究员:** Reze (Orchestrator)")
lines.append("**当前轮次:** 64 | **研究方向:** 亚盘(Asia) + 欧盘(London) Session | **覆盖品种:** 14全品种")
lines.append(f"**总测试数:** {len(by_test)} | **达标信号 (WR≥60%, n≥30):** {len(standard)}")
lines.append(f"**可注入 (n≥150, WR≥65%):** {len(injectable)} | **强信号 (WR≥70%, n≥50):** {len(strong)}")
lines.append("")

lines.append("---")
lines.append("")
lines.append("## 执行摘要")
lines.append("")
lines.append("Round 64 完成了研究历史上首次 **系统性欧盘/亚盘 Session 模式挖掘**。")
lines.append("之前63轮已穷尽美盘(US session)的ATR+RSI+Session三因子研究，本轮全面转向非美盘时段的空白区域。")
lines.append("共执行 **44 个假设检验**（H1 24个 + M30 20个），覆盖全部 14 个 MT5 品种。")
lines.append("")

lines.append("### 🏆 里程碑")
lines.append("")
lines.append("| 里程碑 | 详情 |")
lines.append("|:-------|:------|")
lines.append("| **US500 亚盘首個可注入信号** | H1 亚盘+RSI<25+ATR>0.25%, hold=24, **68.05% (n=169)** ✅ |")
lines.append("| **AUDUSD 欧盘超买做空新注入** | H1 欧盘+RSI>70+ATR>0.20%, hold=40, **65.29% (n=170)** ✅ |")
lines.append("| **AUDUSD 亚盘超卖大样本** | H1 亚盘+RSI<30+ATR>0.20%, hold=30, **65.43% (n=188)** ✅ |")
lines.append("| **AUDUSD 亚盘超买做空注入** | M30 亚盘+RSI>70+ATR>0.15%, hold=15, **66.47% (n=173)** ✅ |")
lines.append("| **US30 亚盘极限超卖高WR** | M30 亚盘+RSI<20+ATR>0.20%, hold=50, **77.59% (n=58)** 🔥 |")
lines.append("| **UKOIL 亚盘极限超卖新发现** | M30 亚盘+RSI<20+ATR>0.20%, hold=60, **75.38% (n=65)** 🆕 |")
lines.append("| **HK50 伦敦开盘窗口确认** | H1 伦敦开盘(8-10)+RSI<25, hold=3, **70.59% (n=68)** 🔥 |")
lines.append("| **AUDUSD 伦敦-NY重叠做空** | M30 12-14UTC+RSI>70, hold=60, **71.60% (n=81)** 🆕 |")
lines.append("| **JP225 亚盘RSI<20高稳信号** | M30 亚盘+RSI<20+ATR>0.20%, hold=15, **70.07% (n=137)** 🆕 |")
lines.append("| **USOIL 欧盘超大样本** | H1 欧盘+RSI<30+ATR>0.20%, **61.83% (n=613)** — 研究史最大样本！|")
lines.append("")

# ── TIER 1: Injectable Signals ──
lines.append("---")
lines.append("")
lines.append("## 🥇 TIER 1 — 可注入信号（n>=150, WR>=65%）")
lines.append("")
lines.append("| # | 信号 | HP | n | WR | avg_ret | Sharpe | 状态 |")
lines.append("|:-:|:-----|:--:|:-:|:--:|:-------:|:------:|:----:|")
for i, f in enumerate(injectable, 1):
    desc = TEST_DESC.get(f['test_id'], f['test_id'])
    lines.append(f"| {i} | {f['symbol']} {desc} | {f['hold_period']} | {f['signal_count']} | **{f['win_rate']:.2%}** | {f['avg_return'] or 0:+.4f} | {f['sharpe_ratio'] or 0:.1f} | ✅ |")

lines.append("")

if injectable:
    for f in injectable:
        test_id = f['test_id']
        sym = f['symbol']
        desc = TEST_DESC.get(test_id, test_id)
        lines.append(f"### {sym} {desc} hold={f['hold_period']}")
        lines.append("")
        # Get full results for this test/symbol
        sym_res = data.get(test_id, {}).get(sym, {})
        tf = "H1" if "H1" in test_id else "M30"
        ppy = 6000 if tf == "H1" else 12000
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

# ── TIER 2: Strong Signals ──
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

# Add detailed breakout for top strong signals
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

# Group by test id
lines.append("### 所有测试 — 最佳品种/持有期汇总")
lines.append("")
lines.append("| ID | 描述 | 最佳品种 | HP | WR | n | avg_ret |")
lines.append("|:--:|:-----|:--------:|:--:|:--:|:-:|:-------:|")
for test_id in sorted(by_test.keys()):
    best = max(by_test[test_id], key=lambda x: x['win_rate'] * min(x['signal_count']/150, 1))
    desc = TEST_DESC.get(test_id, test_id)
    lines.append(f"| {test_id} | {desc} | {best['symbol']} | {best['hold_period']} | **{best['win_rate']:.2%}** | {best['signal_count']} | {best['avg_return'] or 0:+.4f} |")
lines.append("")

# ── Symbol Heatmap ──
lines.append("### 品种发现热力")
lines.append("")
sym_stats = defaultdict(lambda: {"count": 0, "best_wr": 0, "best_sym": "", "tests": set()})
for f in findings:
    sym_stats[f['symbol']]["count"] += 1
    sym_stats[f['symbol']]["best_wr"] = max(sym_stats[f['symbol']]["best_wr"], f['win_rate'])
    sym_stats[f['symbol']]["tests"].add(f['test_id'])

lines.append(f"| 品种 | 达标信号数 | 最高WR | 覆盖测试数 | 结论 |")
lines.append(f"|:----:|:--------:|:-----:|:---------:|:----|")
for sym in sorted(sym_stats.keys()):
    s = sym_stats[sym]
    if s['count'] >= 50:
        verdict = "🔥 强信号密集区"
    elif s['count'] >= 20:
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

# Insight 1
lines.append("### 1️⃣ AUDUSD — 本次研究的最大赢家")
lines.append("")
lines.append(f"AUDUSD 共产生 **{sym_stats['AUDUSD']['count']} 个达标信号**，覆盖全部44个测试中的大部分，是本次研究信号最密集的品种。")
lines.append("")
lines.append("**核心模式：**")
lines.append("- **亚盘超卖做多** (H1_A001): n=188 WR=65.43% — 亚盘RSI<30+ATR>0.20%在AUDUSD上稳定有效")
lines.append("- **亚盘超买做空** (M30_H001): n=173 WR=66.47% — 首次证明AUDUSD亚盘超买均值回归具有可注入质量")
lines.append("- **欧盘超买做空** (H1_D001): n=170 WR=65.29% — 欧盘RSI>70做空在AUDUSD上表现高度一致")
lines.append("")
lines.append("**解读:** AUDUSD作为亚系品种（受澳洲经济数据、亚洲股市影响大），其在亚盘/欧盘的均值回归特性非常显著。")
lines.append("这可能与AUDUSD的高流动性、亚洲时段套利交易行为有关。**建议优先将AUDUSD的3个可注入信号加入注入队列。**")
lines.append("")

# Insight 2
lines.append("### 2️⃣ 亚盘极限超卖（RSI<20）—— 高WR但样本不足")
lines.append("")
lines.append("M30亚盘+RSI<20+ATR>0.20% (R64_M30_G002) 是本次研究中WR最高的一组测试：")
lines.append("")
lines.append("| 品种 | HP | n | WR | avg_ret | Sharpe |")
lines.append("|:---:|:--:|:-:|:--:|:-------:|:------:|")
lines.append("| US30 | 50 | 58 | **77.59%** | +0.46% | 5.39 |")
lines.append("| UKOIL | 60 | 65 | **75.38%** | +0.87% | 3.62 |")
lines.append("| US500 | 50 | 69 | **73.91%** | +0.49% | 5.95 |")
lines.append("| JP225 | 15 | 137 | **70.07%** | +0.40% | 11.48 |")
lines.append("| USTEC | 50 | 48 | **75.00%** | +0.99% | 4.53 |")
lines.append("| XAUUSD | 20 | 30 | **76.67%** | +0.56% | 4.95 |")
lines.append("")
lines.append("**解读:** 亚盘RSI<20的极限条件在几乎所有品种上产生70%+的WR。但n=30-137均未达到150的注入门槛。")
lines.append("**建议下一步降低ATR至0.15%扩样本**，预期n可翻2-3倍。这是下一轮研究的最高优先级。")
lines.append("")

# Insight 3
lines.append("### 3️⃣ US500 亚盘首個可注入信号")
lines.append("")
lines.append("R64_H1_A002 (H1 亚盘+RSI<25+ATR>0.25%做多) 在US500上产生首个亚盘可注入信号：")
lines.append("- hold=24: WR=68.05% n=169 ✅")
lines.append("- hold=20: WR=67.46% n=169 ✅")
lines.append("- hold=30: WR=65.09% n=169 ✅")
lines.append("")
lines.append("对比美盘版(Round 63, H1_A002: US500美盘RSI<25+ATR>0.30%, n=91, WR=67.03%)，")
lines.append("亚盘版样本更大(+86%)且胜率接近(+1pp)。US500在亚盘的均值回归行为被首次量化确认。")
lines.append("")

# Insight 4
lines.append("### 4️⃣ HK50 伦敦开盘/亚欧转换窗口极高WR")
lines.append("")
lines.append("HK50在伦敦开盘和亚欧转换窗口表现出色：")
lines.append("- **R64_H1_F001** (伦敦开盘8-10+RSI<25): hold=3 WR=**70.59%** n=68")
lines.append("- **R64_H1_E001** (亚欧转换7-9+RSI<25): hold=4 WR=**70.00%** n=80")
lines.append("")
lines.append("HK50作为亚洲指数，在伦敦开盘时的超卖反转非常可靠。这为日内的定时交易策略提供了quantifiable基准。")
lines.append("建议下一步降低ATR至0.15%以扩样本至n>=150。")
lines.append("")

# Insight 5
lines.append("### 5️⃣ 美国和欧洲指数的Session对比全景")
lines.append("")
lines.append("| 模式 | US500 | US30 | USTEC | JP225 | HK50 |")
lines.append("|:----|:----:|:----:|:----:|:----:|:----:|")
lines.append("| H1亚盘超卖(R64_A001) | 65.35%* (n=127) | **67.86%** (n=112) | 64.83% (n=116) | 63.34% (n=161)* | 62.50% (n=72) |")
lines.append("| H1亚盘严格(R64_A002) | **68.05%** (n=169)* ✅ | 64.04% (n=89) | 63.89% (n=72) | 62.86% (n=105) | — |")
lines.append("| H1欧盘超卖(R64_C001) | 61.34% (n=555)* | 56.11% (n=491) | 59.87% (n=463) | 58.33% (n=528) | 58.62% (n=348) |")
lines.append("| H1欧盘严格(R64_C002) | 62.30% (n=122) | 58.70% (n=92) | **64.52%** (n=62) | 60.22% (n=93) | 63.64% (n=66) |")
lines.append("| M30亚盘极限(R64_G002) | **73.91%** (n=69) | **77.59%** (n=58) | 75.00% (n=48) | 70.07% (n=137)* | — |")
lines.append("")
lines.append("> *标记为可注入或接近可注入信号")
lines.append("")
lines.append("**关键观察:**")
lines.append("1. **亚盘超卖一致性强于欧盘超卖** — 所有指数品种亚盘WR普遍比欧盘高3-5pp")
lines.append("2. **US500是亚盘最稳定品种** — 唯一同时产生H1可注入 + M30极限高WR的指数")
lines.append("3. **JP225 M30亚盘极限样本最大** — n=137接近注入门槛，降ATR预期可达n>=200")
lines.append("")

# Insight 6
lines.append("### 6️⃣ 欧盘超买做空（Short Side）—— 外汇品种优势")
lines.append("")
lines.append("欧盘超买做空(R64_H1_D001: 欧盘+RSI>70+ATR>0.20%)在外汇品种上表现远超指数/商品：")
lines.append("- **AUDUSD**: n=170 WR=65.29% ✅ 可注入")
lines.append("- **EURUSD**: n=36 WR=72.22% 🔥 n不足")
lines.append("- **GBPUSD**: n=41 WR=65.85% 🔥 n不足")
lines.append("- **USDCHF**: n=54 WR=64.81% ⚠️")
lines.append("- **指数品种**: 全部<54% ❌")
lines.append("")
lines.append("**解读:** 欧盘超买做空是外汇专属策略。AUDUSD已达标，EURUSD/GBPUSD降低ATR有扩样本空间。")
lines.append("")

# ── Next Hypotheses ──
lines.append("---")
lines.append("")
lines.append("## 🔮 下一步假设（Round 65）")
lines.append("")
lines.append("基于Round 64的发现，以下为下一轮的优先研究方向：")
lines.append("")
lines.append("| 优先级 | 假设 | 当前瓶颈 | 预期优化 |")
lines.append("|:-----:|:-----|:---------|:---------|")
lines.append("| **P0** | **JP225 M30 亚盘RSI<20 降ATR至0.15%** | n=137<150 | ATR↓0.05% → 预期n~250, WR~67% |")
lines.append("| **P0** | **US30 M30 亚盘RSI<20 降ATR至0.15%** | n=58<150 | ATR↓0.05% → 预期n~150, WR~73% |")
lines.append("| **P0** | **UKOIL M30 亚盘RSI<20 降ATR至0.15%** | n=65<150 | ATR↓0.05% → 预期n~180, WR~70% |")
lines.append("| **P1** | **US500 M30 亚盘RSI<20 降ATR至0.15%** | n=69<150 | ATR↓0.05% → 预期n~180, WR~69% |")
lines.append("| **P1** | **HK50 H1 伦敦开盘降ATR至0.15%** | n=68<150 | ATR↓0.05% → 预期n~160, WR~66% |")
lines.append("| **P1** | **USOIL 欧盘RSI<30 转M30细粒度挖掘** | n=613最大样本 | 探索更高WR的子条件 |")
lines.append("| **P2** | **EURUSD/GBPUSD 欧盘超买做空降ATR** | n<50 | ATR↓0.05% → 预期n~100+ |")
lines.append("| **P2** | **AUDUSD 亚盘连续阴线衰竭深度优化** | n=98 WR=72.45% | 组合BBL/MA50增强 |")
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
lines.append("")

# ── Write Report ──
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(REPORT_PATH, "w") as f:
    f.write("\n".join(lines))

print(f"✅ 报告已保存至: {REPORT_PATH}")
print(f"共 {len(lines)} 行")
