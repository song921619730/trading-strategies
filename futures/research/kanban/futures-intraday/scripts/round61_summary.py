#!/usr/bin/env python3
"""Round 61 — Summary Report Generator (Chinese)"""
import json
from collections import defaultdict

with open("../logs/round61_researcher_results.json") as f:
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

# By test
by_test = defaultdict(list)
for f in findings:
    by_test[f["test_id"]].append(f)

# Injectable (n>=150)
injectable = [f for f in findings if f["signal_count"] >= 150]

# Strong (WR>=70%, n>=50)
strong = [f for f in findings if f["win_rate"] >= 0.70 and f["signal_count"] >= 50]

lines = []
lines.append("=" * 70)
lines.append("  Round 61 欧亚盘 H1/M30 模式挖掘 — 最终推荐信号")
lines.append("=" * 70)
lines.append("")
lines.append(f"共执行测试: 40 个")
lines.append(f"符合标准 (WR≥60%, n≥30) 信号: {len(findings)} 个")
lines.append(f"可注入信号 (n≥150): {len(injectable)} 个")
lines.append(f"强信号 (WR≥70%, n≥50): {len(strong)} 个")
lines.append("")

lines.append("─" * 70)
lines.append("【一级推荐 — 可注入信号 Top 10】(n≥150)")
lines.append("─" * 70)
lines.append(f"{'排名':>4} {'品种':>10} {'测试':>35} {'持有':>4} {'信号数':>6} {'胜率':>8} {'平均回报':>10} {'Sharpe':>8}")
lines.append("─" * 70)
for i, f in enumerate(injectable[:10]):
    wr_pct = f["win_rate"] * 100
    avg_pct = (f["avg_return"] or 0) * 100
    lines.append(f"{i+1:>4} {f['symbol']:>10} {f['test_id']:>35} {f['hold_period']:>4} {f['signal_count']:>6} {wr_pct:>7.1f}% {avg_pct:>+9.2f}% {f['sharpe_ratio'] or 0:>8.2f}")
lines.append("")

lines.append("─" * 70)
lines.append("【二级推荐 — 高胜率强信号】(WR≥70%, n≥50)")
lines.append("─" * 70)
lines.append(f"{'品种':>10} {'测试':>35} {'持有':>4} {'信号数':>6} {'胜率':>8} {'平均回报':>10}")
lines.append("─" * 70)
for f in sorted(strong, key=lambda x: (x["win_rate"], x["signal_count"]), reverse=True):
    wr_pct = f["win_rate"] * 100
    avg_pct = (f["avg_return"] or 0) * 100
    lines.append(f"{f['symbol']:>10} {f['test_id']:>35} {f['hold_period']:>4} {f['signal_count']:>6} {wr_pct:>7.1f}% {avg_pct:>+9.2f}%")
lines.append("")

lines.append("─" * 70)
lines.append("【重点信号详解】")
lines.append("─" * 70)
lines.append("")

# Key signal 1: XAUUSD H1 美盘
lines.append("▶ 信号1: XAUUSD H1 美盘+RSI<30+ATR>0.35%做多")
lines.append("  条件: session=='us' and rsi14<30 and atr14/close>0.0035")
lines.append("  信号数: 235 | 最佳持有: hold=7")
sig1 = [f for f in findings if f["test_id"] == "h1_xau_us_rsi30_atr035" and f["symbol"] == "XAUUSD"]
for f in sorted(sig1, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        w = f["win_rate"] * 100
        a = (f["avg_return"] or 0) * 100
        lines.append(f"    hold={f['hold_period']:>2}: n={f['signal_count']:>4} | WR={w:>5.1f}% | avg={a:>+6.2f}% | Sharpe={f['sharpe_ratio'] or 0:>5.2f}")
lines.append("")

# Key signal 2: XAUUSD H1 亚盘
lines.append("▶ 信号2: XAUUSD H1 亚盘+RSI<30+ATR>0.30%做多")
lines.append("  条件: session=='asia' and rsi14<30 and atr14/close>0.0030")
sig2 = [f for f in findings if f["test_id"] == "h1_xau_asia_rsi30_atr030" and f["symbol"] == "XAUUSD"]
for f in sorted(sig2, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        w = f["win_rate"] * 100
        a = (f["avg_return"] or 0) * 100
        lines.append(f"    hold={f['hold_period']:>2}: n={f['signal_count']:>4} | WR={w:>5.1f}% | avg={a:>+6.2f}% | Sharpe={f['sharpe_ratio'] or 0:>5.2f}")
lines.append("")

# Key signal 3: JP225 M30 欧盘
lines.append("▶ 信号3: JP225 M30 欧盘+RSI<25+ATR>0.35%做多")
lines.append("  条件: session=='europe' and rsi14<25 and atr14/close>0.0035")
sig3 = [f for f in findings if f["test_id"] == "m30_jp225_europe_rsi25_atr035" and f["symbol"] == "JP225"]
for f in sorted(sig3, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        w = f["win_rate"] * 100
        a = (f["avg_return"] or 0) * 100
        lines.append(f"    hold={f['hold_period']:>2}: n={f['signal_count']:>4} | WR={w:>5.1f}% | avg={a:>+6.2f}% | Sharpe={f['sharpe_ratio'] or 0:>5.2f}")
lines.append("")

# Key signal 4: US500 M30 亚盘连续阴+RSI<30
lines.append("▶ 信号4: US500 M30 亚盘连续3阴+RSI<30+ATR>0.20%做多")
lines.append("  条件: consecutive_bear_count>=3 and rsi14<30 and session=='asia' and atr14/close>0.0020")
sig4 = [f for f in findings if f["test_id"] == "m30_bear3_asia_rsi30" and f["symbol"] == "US500"]
for f in sorted(sig4, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        w = f["win_rate"] * 100
        a = (f["avg_return"] or 0) * 100
        lines.append(f"    hold={f['hold_period']:>2}: n={f['signal_count']:>4} | WR={w:>5.1f}% | avg={a:>+6.2f}% | Sharpe={f['sharpe_ratio'] or 0:>5.2f}")
lines.append("")

# Key signal 5: USDJPY M30 欧盘下午做空
lines.append("▶ 信号5: USDJPY M30 欧盘下午(12-16UTC)+RSI>70+ATR>0.20%做空")
lines.append("  条件: hour>=12 and hour<16 and rsi14>70 and atr14/close>0.0020")
sig5 = [f for f in findings if f["test_id"] == "m30_hour_12_16_rsi70_short" and f["symbol"] == "USDJPY"]
for f in sorted(sig5, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        w = f["win_rate"] * 100
        a = (f["avg_return"] or 0) * 100
        lines.append(f"    hold={f['hold_period']:>2}: n={f['signal_count']:>4} | WR={w:>5.1f}% | avg={a:>+6.2f}% | Sharpe={f['sharpe_ratio'] or 0:>5.2f}")
lines.append("")

# Key signal 6: US500 M30 欧盘8-12UTC
lines.append("▶ 信号6: US500 M30 欧盘开盘(8-12UTC)+RSI<25+ATR>0.20%做多")
lines.append("  条件: hour>=8 and hour<12 and rsi14<25 and atr14/close>0.0020")
sig6 = [f for f in findings if f["test_id"] == "m30_hour_8_12_rsi25" and f["symbol"] == "US500"]
for f in sorted(sig6, key=lambda x: x["hold_period"]):
    if f["signal_count"] >= 30:
        w = f["win_rate"] * 100
        a = (f["avg_return"] or 0) * 100
        lines.append(f"    hold={f['hold_period']:>2}: n={f['signal_count']:>4} | WR={w:>5.1f}% | avg={a:>+6.2f}% | Sharpe={f['sharpe_ratio'] or 0:>5.2f}")
lines.append("")

lines.append("─" * 70)
lines.append("【测试总结与建议】")
lines.append("─" * 70)
lines.append("")
lines.append("本次 Round 61 共执行 40 个假设检验（H1 20个 + M30 20个），覆盖 14 个品种。")
lines.append("主要发现如下：")
lines.append("")
lines.append("1. XAUUSD H1 美盘信号成功注入")
lines.append("   - 将 ATR 阈值从 0.40% 降至 0.35% 后，信号数从 ~143 增至 235")
lines.append("   - hold=7 仍保持 71.5% 胜率，达到可注入标准")
lines.append("   - 强烈推荐将此信号加入实盘策略")
lines.append("")
lines.append("2. XAUUSD H1 亚盘 ATR 降低同样有效")
lines.append("   - ATR 从 0.40% 降至 0.30% 后，信号数从 ~62 增至 153")
lines.append("   - hold=48 达到 66.0% 胜率，但持有期过长需注意")
lines.append("")
lines.append("3. JP225 M30 欧盘信号验证成功")
lines.append("   - RSI<25+ATR>0.35% 在欧盘产生 69 个信号")
lines.append("   - hold=45 达到 72.5% 胜率，但 n 未达 150 注入门槛")
lines.append("   - 建议进一步降低 ATR 阈值尝试扩样本")
lines.append("")
lines.append("4. US500 M30 亚盘连续阴线衰竭信号最强")
lines.append("   - 连续3阴+RSI<30 在亚盘 hold=50 达 71.7% 胜率 (n=99)")
lines.append("   - 欧盘连续阴线也有不错表现，适合跨盘部署")
lines.append("")
lines.append("5. USDJPY M30 欧盘下午做空是新的发现")
lines.append("   - 12-16UTC+RSI>70 做空 hold=50 达 73.5% 胜率 (n=68)")
lines.append("   - 此信号需要进一步扩样本验证")
lines.append("")
lines.append("6. US500 M30 晨盘(7-10UTC)/欧盘开盘(8-12UTC)信号质量极高")
lines.append("   - WR 高达 81.8%，但 n 仅 33-44")
lines.append("   - 建议进一步降低门槛扩样本")
lines.append("")
lines.append("7. EURUSD H1 亚盘 RSI<30+ATR>0.20% 胜率最高(82.9%)但 n 仅 35")
lines.append("   - 需大幅降低 ATR 门槛才能达到注入标准")
lines.append("")
lines.append("【最终推荐】")
lines.append("  ★ 立即注入: XAUUSD H1 美盘+RSI<30+ATR>0.35%做多 hold=7 (n=235, WR=71.5%)")
lines.append("  ★ 优先扩样本: JP225 M30 欧盘+RSI<25+ATR>0.35%做多 → 降ATR至0.30%")
lines.append("  ★ 优先扩样本: US500 M30 亚盘连续阴+RSI<30 → 降ATR至0.15%")
lines.append("  ★ 关注: USDJPY M30 欧盘下午(12-16)+RSI>70做空 → 降ATR至0.15%")
lines.append("  ★ 关注: XAUUSD H1 亚盘+RSI<30+ATR>0.30% hold=48 → 降ATR至0.25%")
lines.append("")

print("\n".join(lines))

# Save to file
with open("../logs/round61_summary_finding.txt", "w") as f:
    f.write("\n".join(lines))

print(f"\nSummary saved to ../logs/round61_summary_finding.txt")
