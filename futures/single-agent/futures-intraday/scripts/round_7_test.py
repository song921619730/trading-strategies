#!/usr/bin/env python3
"""
round_7_test.py — 第7轮研究测试（超短线M1/M5聚焦）

测试项目（优先级排列）:
1. H31: M5 marubozu_bear + 美盘 → XAUUSD 做多 
2. H32: M1 marubozu_bear + 美盘 → XAUUSD 做多
3. H33: M5 marubozu_bear + 美盘 → XAGUSD, US500, US30, JP225 做多（多品种扩展）
4. H34: M5 harami_bear + 美盘 → XAUUSD 做多（孕阴线反向做多）
5. H35: M5 RSI<40 + 美盘 → XAGUSD, US500 持60期做多（RSI超卖策略优化）
6. H36: M5 three_black_crows + 美盘 → XAGUSD, XAUUSD, US30 做多（三黑兵降TF）
"""
import os, sys, json
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

from run_candlestick import run_pattern_test, run_pattern_test_enhanced

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
                lines.append(f"| 持有期 | 胜率 | n | 平均回报% | Sharpe |")
                lines.append(f"|:-----:|:----:|:--:|:--------:|:-----:|")
                for h, m in rows:
                    mr = "✅" if m['win_rate'] >= 60 and m['n'] >= 20 else "⭐" if m['win_rate'] >= 57 else "⚠️" if m['win_rate'] >= 50 else "❌"
                    lines.append(f"| {h} | {m['win_rate']:.1f}%{mr} | {m['n']} | {m['avg_return']:+.3f} | {m['sharpe']:.2f} |")
    
    return "\n".join(lines)

# =====================
# 1. H31: M5 marubozu_bear + 美盘 → XAUUSD 做多（复现验证）
# =====================
print("=" * 70)
print("📊 测试 H31: M5 marubozu_bear + 美盘 → XAUUSD 做多")
print("=" * 70)
res_h31 = run_pattern_test(
    entry_condition="session == 'us' and marubozu_bear == True",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
)
RESULTS["H31"] = res_h31

# =====================
# 2. H32: M1 marubozu_bear + 美盘 → XAUUSD 做多（复现验证）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H32: M1 marubozu_bear + 美盘 → XAUUSD 做多")
print("=" * 70)
res_h32 = run_pattern_test(
    entry_condition="session == 'us' and marubozu_bear == True",
    direction="long",
    timeframe="M1",
    symbols=["XAUUSD"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
)
RESULTS["H32"] = res_h32

# =====================
# 3. H33: M5 marubozu_bear + 美盘 → 多品种扩展
# =====================
print("\n" + "=" * 70)
print("📊 测试 H33: M5 marubozu_bear + 美盘 → XAGUSD, US500, US30, JP225 做多")
print("=" * 70)
res_h33 = run_pattern_test(
    entry_condition="session == 'us' and marubozu_bear == True",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD", "US500", "US30", "JP225"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
)
RESULTS["H33"] = res_h33

# =====================
# 4. H34: M5 harami_bear + 美盘 → XAUUSD 做多
# =====================
print("\n" + "=" * 70)
print("📊 测试 H34: M5 harami_bear + 美盘 → XAUUSD 做多")
print("=" * 70)
res_h34 = run_pattern_test(
    entry_condition="session == 'us' and harami_bear == True",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
)
RESULTS["H34"] = res_h34

# =====================
# 5. H35: M5 RSI<40 + 美盘 → XAGUSD, US500 持60期做多（优化持有期）
# =====================
print("\n" + "=" * 70)
print("📊 测试 H35: M5 RSI<40 + 美盘 → XAGUSD, US500 做多（长持有期优化）")
print("=" * 70)
res_h35 = run_pattern_test(
    entry_condition="rsi14 < 40 and session == 'us'",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD", "US500", "XAUUSD", "JP225"],
    hold_periods=[30, 40, 50, 60, 70, 80, 90, 120],
)
RESULTS["H35"] = res_h35

# =====================
# 6. H36: M5 three_black_crows + 美盘 → XAGUSD, XAUUSD, US30 做多
# =====================
print("\n" + "=" * 70)
print("📊 测试 H36: M5 three_black_crows + 美盘 → XAGUSD, XAUUSD, US30 做多")
print("=" * 70)
res_h36 = run_pattern_test(
    entry_condition="session == 'us' and three_black_crows == True",
    direction="long",
    timeframe="M5",
    symbols=["XAGUSD", "XAUUSD", "US30"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
)
RESULTS["H36"] = res_h36

# =====================
# 7. M1 美盘方向性偏差验证（baseline）
# =====================
print("\n" + "=" * 70)
print("📊 Baseline: M1/M5 美盘方向性偏差（纯美盘做多基准）")
print("=" * 70)
res_base_m5 = run_pattern_test(
    entry_condition="session == 'us'",
    direction="long",
    timeframe="M5",
    symbols=["XAUUSD", "XAGUSD", "US500", "US30", "JP225"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
)
RESULTS["BASELINE_M5"] = res_base_m5

res_base_m1 = run_pattern_test(
    entry_condition="session == 'us'",
    direction="long",
    timeframe="M1",
    symbols=["XAUUSD", "XAGUSD", "US500", "US30", "JP225"],
    hold_periods=[1, 2, 3, 5, 7, 10, 15, 20],
)
RESULTS["BASELINE_M1"] = res_base_m1

# =====================
# 保存结果
# =====================
out_dir = os.path.join(BASE, "logs", "research")
os.makedirs(out_dir, exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
out_path = os.path.join(out_dir, f"round7_{ts}.json")
with open(out_path, "w") as f:
    json.dump(RESULTS, f, ensure_ascii=False, indent=2, default=str)
print(f"\n✅ 第7轮测试结果已保存到: {out_path}")
print("=" * 70)
