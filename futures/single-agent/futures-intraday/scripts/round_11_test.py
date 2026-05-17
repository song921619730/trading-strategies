#!/usr/bin/env python3
"""
round_11_test.py — 第11轮研究测试（ATR>0.8%极限、做空方向验证、XAUUSD ATR扩展、仓位管理、持有期精调、H1 TF提升）

测试项目（优先级排列）:
1. H52: M5 RSI<40+ATR>0.8%+美盘→XAGUSD 持75-85期做多（ATR阈值极限测试）
2. H53: M5 RSI<40+ATR>0.5%+美盘→XAGUSD 做空方向验证
3. H54: M5 RSI<40+ATR>0.3%+美盘→XAUUSD 持75-85期做多（ATR增强跨品种至黄金）
4. H55: M5 harami_bear+RSI<40+美盘→XAUUSD+XAGUSD@15 双品种仓位管理研究
5. H56: M5 RSI<40+ATR>0.5%+美盘→XAGUSD 68-88期精调
6. H57: H1 RSI<40+ATR>0.5%+美盘→XAGUSD 持1-7期做多（TF提升至H1）
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
# 1. H52: M5 RSI<40+ATR>0.8%+美盘→XAGUSD 持75-85期做多（ATR阈值极限测试）
# =====================
print("=" * 70)
print("📊 测试 H52: M5 RSI<40+ATR>0.8%+美盘→XAGUSD 持75-85期做多")
print("  F25 WR 70.3% @ATR>0.5%。继续提高阈值至0.8%测试能否突破72%+")
print("=" * 70)
res_h52 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.8",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD"],
    hold_periods=[70, 75, 80, 85, 90],
)
RESULTS["H52"] = res_h52

# =====================
# 2. H53: M5 RSI<40+ATR>0.5%+美盘→XAGUSD 做空方向验证
# =====================
print("\n" + "=" * 70)
print("📊 测试 H53: M5 RSI<40+ATR>0.5%+美盘→XAGUSD 做空方向验证")
print("  F25做多WR 70.3%，验证做空是否同向无效确认方向特异性")
print("=" * 70)
res_h53 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.5",
    direction="short",
    timeframe="M5",
    symbols=["XAGUSD"],
    hold_periods=[75, 80, 85],
)
RESULTS["H53"] = res_h53

# =====================
# 3. H54: M5 RSI<40+ATR>0.3%+美盘→XAUUSD 持75-85期做多（ATR增强跨品种至黄金）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H54: M5 RSI<40+ATR>0.3%+美盘→XAUUSD 持70-90期做多")
print("  F25在XAGUSD WR 70.3%。黄金波动率稍低，尝试ATR>0.3%扩展至XAUUSD")
print("=" * 70)
res_h54 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.3",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD"],
    hold_periods=[70, 75, 80, 85, 90],
)
RESULTS["H54"] = res_h54

# =====================
# 4. H55: M5 harami_bear+RSI<40+美盘→XAUUSD+XAGUSD@15 双品种仓位管理研究
# =====================
print("\n" + "=" * 70)
print("📊 测试 H55: M5 harami_bear+RSI<40+美盘→XAUUSD+XAGUSD 双品种仓位管理")
print("  F17(74.6%)+F22(64.8%)双品种独立信号，研究同时持仓绩效")
print("=" * 70)
res_h55 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and harami_bear == True",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD", "XAUUSD"],
    hold_periods=[15],
)
RESULTS["H55"] = res_h55

# =====================
# 5. H56: M5 RSI<40+ATR>0.5%+美盘→XAGUSD 68-88期精调（ATR>0.5%持有期精调）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H56: M5 RSI<40+ATR>0.5%+美盘→XAGUSD 68-88期精调")
print("  F25最优80期(70.3%)。精调68-88期确认是否为全局最优")
print("=" * 70)
res_h56 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.5",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD"],
    hold_periods=[68, 72, 75, 78, 80, 82, 85, 88],
)
RESULTS["H56"] = res_h56

# =====================
# 6. H57: H1 RSI<40+ATR>0.5%+美盘→XAGUSD 持1-7期做多（TF提升至H1）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H57: H1 RSI<40+ATR>0.5%+美盘→XAGUSD 持1-7期做多（TF提升至H1）")
print("  M5成功(WR 70.3%@80期≈6.67h)。H1上持2-5期≈2-5h更高效")
print("=" * 70)
res_h57 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.5",
    direction="long",
    timeframe="H1",
    symbols=["XAGUSD"],
    hold_periods=[1, 2, 3, 5, 7],
)
RESULTS["H57"] = res_h57

# =====================
# 保存结果
# =====================
out_dir = os.path.join(BASE, "logs", "research")
os.makedirs(out_dir, exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
out_path = os.path.join(out_dir, f"round11_{ts}.json")
with open(out_path, "w") as f:
    json.dump(RESULTS, f, ensure_ascii=False, indent=2, default=str)
print(f"\n✅ 第11轮测试结果已保存到: {out_path}")
print("=" * 70)
