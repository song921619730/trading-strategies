#!/usr/bin/env python3
"""
round_12_test.py — 第12轮研究测试（H1 ATR>0.3%降阈值、harami+ATR复合、US500 H1尝试）

测试项目（优先级排列）:
1. H58: H1 RSI<40+ATR>0.3%+美盘→XAGUSD持3-7期做多（H1 ATR>0.3%版本）
2. H59: M5 harami_bear+RSI<40+ATR>0.3%+美盘→XAGUSD持15-20期做多（harami+ATR复合过滤）
3. H60: M5 RSI<40+ATR>0.3%+美盘→XAGUSD+US500 双品种仓位管理
4. H61: M5 three_black_crows+RSI<40+ATR>0.3%+美盘→XAUUSD持11期做多
5. H62: H1 RSI<40+ATR>0.3%+美盘→US500持5-10期做多（H1上US500 ATR版本）
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
# 1. H58: H1 RSI<40+ATR>0.3%+美盘→XAGUSD持3-7期做多（H1 ATR>0.3%版本）
# =====================
print("=" * 70)
print("📊 测试 H58: H1 RSI<40+ATR>0.3%+美盘→XAGUSD 持3-7期做多")
print("  H57中ATR>0.5% WR=66.4%。降阈值至0.3%在H1上信号更多，WR可能提升至68%+")
print("=" * 70)
res_h58 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.3",
    direction="long",
    timeframe="H1",
    symbols=["XAGUSD"],
    hold_periods=[3, 5, 7, 10],
)
RESULTS["H58"] = res_h58

# =====================
# 2. H59: M5 harami_bear+RSI<40+ATR>0.3%+美盘→XAGUSD持15-20期做多
# =====================
print("\n" + "=" * 70)
print("📊 测试 H59: M5 harami_bear+RSI<40+ATR>0.3%+美盘→XAGUSD 持10-25期做多")
print("  F22(64.8%)+F21(66.6%)的组合能否叠加到68%+？")
print("=" * 70)
res_h59 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and harami_bear == True and atr14_pct > 0.3",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD"],
    hold_periods=[10, 15, 20, 25],
)
RESULTS["H59"] = res_h59

# =====================
# 3. H60: M5 RSI<40+ATR>0.3%+美盘→XAGUSD+US500 双品种仓位管理
# =====================
print("\n" + "=" * 70)
print("📊 测试 H60: M5 RSI<40+ATR>0.3%+美盘→XAGUSD+US500 双品种仓位管理")
print("  F21(XAGUSD@75 WR=66.6%)+F16(US500@95 WR=60.9%)双品种相关性研究")
print("=" * 70)
res_h60 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.3",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD", "US500"],
    hold_periods=[75, 85],
)
RESULTS["H60"] = res_h60

# =====================
# 4. H61: M5 three_black_crows+RSI<40+ATR>0.3%+美盘→XAUUSD持11期做多
# =====================
print("\n" + "=" * 70)
print("📊 测试 H61: M5 three_black_crows+RSI<40+ATR>0.3%+美盘→XAUUSD 持8-20期做多")
print("  F20(61.1%)加ATR>0.3%过滤能否提升至63%+？三黑兵+高波动环境反转力度更强")
print("=" * 70)
res_h61 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and three_black_crows == True and atr14_pct > 0.3",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD"],
    hold_periods=[8, 11, 15, 20],
)
RESULTS["H61"] = res_h61

# =====================
# 5. H62: H1 RSI<40+ATR>0.3%+美盘→US500持5-10期做多
# =====================
print("\n" + "=" * 70)
print("📊 测试 H62: H1 RSI<40+ATR>0.3%+美盘→US500 持3-10期做多")
print("  F16中US500 WR=60.9%(M5@95期)。H1+ATR尝试能否提升")
print("=" * 70)
res_h62 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.3",
    direction="long",
    timeframe="H1",
    symbols=["US500"],
    hold_periods=[3, 5, 7, 10],
)
RESULTS["H62"] = res_h62

# =====================
# 保存结果
# =====================
out_dir = os.path.join(BASE, "logs", "research")
os.makedirs(out_dir, exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
out_path = os.path.join(out_dir, f"round12_{ts}.json")
with open(out_path, "w") as f:
    json.dump(RESULTS, f, ensure_ascii=False, indent=2, default=str)
print(f"\n✅ 第12轮测试结果已保存到: {out_path}")
print("=" * 70)
