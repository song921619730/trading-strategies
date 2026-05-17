#!/usr/bin/env python3
"""
round_10_test.py — 第10轮研究测试（ATR阈值优化、反向验证、三策略统一测试、US500扩展）

测试项目（优先级排列）:
1. H47: M5 RSI<40+ATR>0.3%+美盘→XAGUSD@75 做空方向反向验证（确认信号方向性）
2. H48: M5 RSI<40+ATR>0.5%+美盘→XAGUSD@75 做多（更高ATR阈值测试）
3. H49: M5 RSI<40+harami_bear+美盘→XAGUSD+XAUUSD@15 做多（F17+F22合并测试）
4. H50: M5 RSI<40+ATR>0.3%+美盘→US500 持85-100期做多（ATR增强跨品种扩展）
5. H51: M5 RSI<40+美盘→XAGUSD 三持有期统一对比（60 vs 75 vs 85期）
"""
import os, sys, json
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

from run_candlestick import run_pattern_test

RESULTS = {}
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def fmt_result(name, res):
    """Format test result for report"""
    best = res.get("best_overall", {})
    lines = []
    lines.append(f"### {name}")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 条件 | {res.get('entry_condition', 'N/A')} |")
    lines.append(f"| 最佳品种 | {best.get('symbol', 'N/A')} |")
    lines.append(f"| 最佳持有期 | {best.get('hold', 'N/A')} |")
    lines.append(f"| 胜率 | {best.get('win_rate', 0):.1f}% |")
    lines.append(f"| 信号数 | {best.get('n', 0)} |")
    lines.append(f"| Sharpe | {best.get('sharpe', 0):.2f} |")
    lines.append(f"| 平均回报 | {best.get('avg_return', 0):.3f}% |")

    details = res.get("details", {})
    for sym, sdata in details.items():
        if isinstance(sdata, dict) and "error" not in sdata:
            hp = sdata.get("hold_periods", {})
            rows = [(h, hp[h]) for h in sorted(hp.keys()) if hp[h].get("n", 0) >= 5]
            if rows:
                lines.append(f"\n#### {sym} (n={sdata.get('signal_count', '?')})")
                lines.append(f"| 持有期 | 胜率 | n | 平均回报% | Sharpe | 判定 |")
                lines.append(f"|:-----:|:----:|:--:|:--------:|:-----:|:----:|")
                for h, m in rows:
                    if m['win_rate'] >= 65 and m['n'] >= 50:
                        mr = "✅✅✅"
                    elif m['win_rate'] >= 60 and m['n'] >= 20:
                        mr = "✅✅"
                    elif m['win_rate'] >= 57:
                        mr = "⭐"
                    elif m['win_rate'] >= 50:
                        mr = "⚠️"
                    else:
                        mr = "❌"
                    lines.append(f"| {h} | {m['win_rate']:.1f}% | {m['n']} | {m['avg_return']:+.3f} | {m['sharpe']:.2f} | {mr} |")

    return "\n".join(lines)

# =====================
# 1. H47: M5 RSI<40+ATR>0.3%+美盘→XAGUSD@75 做空反向验证
# =====================
print("=" * 70)
print("📊 测试 H47: M5 RSI<40+ATR>0.3%+美盘→XAGUSD@75 做空方向反向验证")
print("  验证：F21做多WR 66.6%，做空方向是否同向无效，确认信号方向特异性")
print("=" * 70)
res_h47 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.3",
    direction="short",
    timeframe="M5",
    symbols=["XAGUSD"],
    hold_periods=[65, 70, 75, 80, 85],
)
RESULTS["H47"] = res_h47

# =====================
# 2. H48: M5 RSI<40+ATR>0.5%+美盘→XAGUSD@75 做多（更高ATR阈值）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H48: M5 RSI<40+ATR>0.5%+美盘→XAGUSD@75 做多（更高ATR阈值测试）")
print("  目标：ATR>0.5% → 能否突破68%+")
print("=" * 70)
res_h48 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.5",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD"],
    hold_periods=[60, 65, 70, 75, 80, 85],
)
RESULTS["H48"] = res_h48

# =====================
# 3. H49: M5 RSI<40+harami_bear+美盘→XAGUSD+XAUUSD@15 做多（F17+F22合并）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H49: M5 RSI<40+harami_bear+美盘→XAGUSD+XAUUSD 持10-20期做多")
print("  F17(XAUUSD WR 74.6%) + F22(XAGUSD WR 64.8%) 同步测试双品种")
print("=" * 70)
res_h49 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and harami_bear == True",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD", "XAUUSD"],
    hold_periods=[5, 7, 10, 12, 15, 20],
)
RESULTS["H49"] = res_h49

# =====================
# 4. H50: M5 RSI<40+ATR>0.3%+美盘→US500 持85-100期做多（ATR增强跨品种扩展）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H50: M5 RSI<40+ATR>0.3%+美盘→US500 持85-100期做多（ATR增强跨品种）")
print("  F21在XAGUSD大获成功(WR 66.6%)，扩展至US500")
print("=" * 70)
res_h50 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.3",
    direction="long",
    timeframe="M5",
    symbols=["US500"],
    hold_periods=[75, 80, 85, 90, 95, 100],
)
RESULTS["H50"] = res_h50

# =====================
# 5. H51: M5 RSI<40+美盘→XAGUSD 三持有期统一对比（60 vs 75 vs 85期）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H51: M5 RSI<40+美盘→XAGUSD 三持有期统一对比")
print("  F15(60期)→F18(85期)→F21(75期) 统一回测确定最终最优解")
print("=" * 70)
res_h51 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us'",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD"],
    hold_periods=[55, 60, 65, 70, 75, 80, 85, 90],
)
RESULTS["H51"] = res_h51

# =====================
# 保存结果
# =====================
out_dir = os.path.join(BASE, "logs", "research")
os.makedirs(out_dir, exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
out_path = os.path.join(out_dir, f"round10_{ts}.json")
with open(out_path, "w") as f:
    json.dump(RESULTS, f, ensure_ascii=False, indent=2, default=str)
print(f"\n✅ 第10轮测试结果已保存到: {out_path}")
print("=" * 70)
