#!/usr/bin/env python3
"""
round_9_test.py — 第9轮研究测试（F17跨品种扩展、ATR复合过滤、持有期精调）

测试项目（优先级排列）:
1. H42: M5 harami_bear+RSI<40+美盘→XAGUSD, JP225 持5-20期做多（F17跨品种扩展）
2. H43: M5 RSI<40+美盘+ATR>0.3%→XAGUSD 持75-95期做多（ATR波动率增强过滤）
3. H44: M5 three_black_crows+RSI<40+美盘→XAUUSD 持7-12期精调
4. H45: M5 RSI<40+美盘→XAUUSD, JP225, US30 持75-90期做多（多品种扩展）
5. H46: M5 bull_reversal+RSI<40+美盘→XAUUSD 持5-20期做多（综合反转形态测试）
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
                    if m['win_rate'] >= 60 and m['n'] >= 20:
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
# 1. H42: M5 harami_bear+RSI<40+美盘→XAGUSD, JP225 做多（F17跨品种扩展）
# =====================
print("=" * 70)
print("📊 测试 H42: M5 harami_bear+RSI<40+美盘→XAGUSD, JP225 做多（F17跨品种扩展）")
print("=" * 70)
res_h42 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and harami_bear == True",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD", "JP225"],
    hold_periods=[5, 7, 10, 15, 20],
)
RESULTS["H42"] = res_h42

# =====================
# 2. H43: M5 RSI<40+美盘+ATR>0.3%→XAGUSD 做多（ATR波动率增强过滤）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H43: M5 RSI<40+美盘+ATR>0.3%→XAGUSD@85 做多（ATR波动率增强）")
print("=" * 70)
res_h43 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and atr14_pct > 0.3",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD"],
    hold_periods=[75, 80, 85, 90, 95],
)
RESULTS["H43"] = res_h43

# =====================
# 3. H44: M5 three_black_crows+RSI<40+美盘→XAUUSD 持7-12期精调
# =====================
print("\n" + "=" * 70)
print("📊 测试 H44: M5 three_black_crows+RSI<40+美盘→XAUUSD 持7-12期精调")
print("=" * 70)
res_h44 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and three_black_crows == True",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD"],
    hold_periods=[7, 8, 9, 10, 11, 12],
)
RESULTS["H44"] = res_h44

# =====================
# 4. H45: M5 RSI<40+美盘→XAUUSD, JP225, US30 持75-90期做多（多品种扩展）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H45: M5 RSI<40+美盘→XAUUSD, JP225, US30 持75-90期做多（多品种扩展）")
print("=" * 70)
res_h45 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us'",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD", "JP225", "US30"],
    hold_periods=[75, 80, 85, 90],
)
RESULTS["H45"] = res_h45

# =====================
# 5. H46: M5 bull_reversal+RSI<40+美盘→XAUUSD 持5-20期做多（综合反转形态测试）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H46: M5 bull_reversal+RSI<40+美盘→XAUUSD 做多（综合反转形态）")
print("=" * 70)
res_h46 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and bull_reversal == True",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD"],
    hold_periods=[5, 7, 10, 15, 20],
)
RESULTS["H46"] = res_h46

# =====================
# 保存结果
# =====================
out_dir = os.path.join(BASE, "logs", "research")
os.makedirs(out_dir, exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
out_path = os.path.join(out_dir, f"round9_{ts}.json")
with open(out_path, "w") as f:
    json.dump(RESULTS, f, ensure_ascii=False, indent=2, default=str)
print(f"\n✅ 第9轮测试结果已保存到: {out_path}")
print("=" * 70)
