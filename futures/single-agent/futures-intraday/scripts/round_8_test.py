#!/usr/bin/env python3
"""
round_8_test.py — 第8轮研究测试（M5复合过滤与持有期精调）

测试项目（优先级排列）:
1. H37: M5 RSI<40 + 美盘 + harami_bear → XAUUSD 持5-15期做多
2. H38: M5 RSI<40 + 美盘 → XAGUSD 持75-110期做多（最优持有期精调）
3. H39: M5 RSI<40 + 美盘 → XAGUSD, US500 持80-100期做多（DXY不可用时的最佳替代）
4. H40: M5 RSI<40 + 美盘 + marubozu_bear → XAUUSD 持1-5期做多
5. H41: M5 three_black_crows + RSI<40 + 美盘 → XAGUSD, XAUUSD 持10-30期做多
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
# 1. H37: M5 RSI<40 + 美盘 + harami_bear → XAUUSD 做多
# =====================
print("=" * 70)
print("📊 测试 H37: M5 RSI<40 + 美盘 + harami_bear → XAUUSD 做多")
print("=" * 70)
res_h37 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and harami_bear == True",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD"],
    hold_periods=[5, 7, 10, 15, 20],
)
RESULTS["H37"] = res_h37

# =====================
# 2. H38: M5 RSI<40 + 美盘 → XAGUSD 持有期精调 (75-110期)
# =====================
print("\n" + "=" * 70)
print("📊 测试 H38: M5 RSI<40 + 美盘 → XAGUSD 持有期精调")
print("=" * 70)
res_h38 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us'",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD"],
    hold_periods=[75, 80, 85, 90, 95, 100, 105, 110],
)
RESULTS["H38"] = res_h38

# =====================
# 3. H39: M5 RSI<40 + 美盘 → XAGUSD, US500 持80-100期做多
# (原始假设包含DXY↓过滤，但因研究数据无DXY，测试基础版本)
# =====================
print("\n" + "=" * 70)
print("📊 测试 H39: M5 RSI<40 + 美盘 → XAGUSD, US500 做多（DXY过滤暂缺）")
print("=" * 70)
res_h39 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us'",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD", "US500"],
    hold_periods=[80, 85, 90, 95, 100],
)
RESULTS["H39"] = res_h39

# =====================
# 4. H40: M5 RSI<40 + 美盘 + marubozu_bear → XAUUSD 做多
# =====================
print("\n" + "=" * 70)
print("📊 测试 H40: M5 RSI<40 + 美盘 + marubozu_bear → XAUUSD 做多")
print("=" * 70)
res_h40 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and marubozu_bear == True",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD"],
    hold_periods=[1, 2, 3, 5, 7],
)
RESULTS["H40"] = res_h40

# =====================
# 5. H41: M5 three_black_crows + RSI<40 + 美盘 → XAGUSD, XAUUSD 做多
# =====================
print("\n" + "=" * 70)
print("📊 测试 H41: M5 three_black_crows + RSI<40 + 美盘 → XAGUSD, XAUUSD 做多")
print("=" * 70)
res_h41 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us' and three_black_crows == True",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD", "XAUUSD"],
    hold_periods=[10, 15, 20, 25, 30],
)
RESULTS["H41"] = res_h41

# =====================
# 保存结果
# =====================
out_dir = os.path.join(BASE, "logs", "research")
os.makedirs(out_dir, exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
out_path = os.path.join(out_dir, f"round8_{ts}.json")
with open(out_path, "w") as f:
    json.dump(RESULTS, f, ensure_ascii=False, indent=2, default=str)
print(f"\n✅ 第8轮测试结果已保存到: {out_path}")
print("=" * 70)
