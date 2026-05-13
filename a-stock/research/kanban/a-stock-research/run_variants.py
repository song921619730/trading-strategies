#!/usr/bin/env python3
"""运行所有 6 个变体回测"""
import json
import sys
sys.path.insert(0, '/mnt/f/AIcoding_space/Hermes/strategies/a-stock/research/kanban/a-stock-research/scripts')
from grid_engine import run_grid

VARIANTS = {
    "V1_非一字+未开板": 'ld.first_time IS NOT NULL AND ld.last_time IS NOT NULL AND ld.first_time != ld.last_time AND ld.open_times = 0',
    "V2_非一字+早封<10点": 'ld.first_time IS NOT NULL AND ld.last_time IS NOT NULL AND ld.first_time != ld.last_time AND ld.first_time < \'10:00\'',
    "V3_非一字+午前<11:30": 'ld.first_time IS NOT NULL AND ld.last_time IS NOT NULL AND ld.first_time != ld.last_time AND ld.first_time < \'11:30\'',
    "V4_非一字+有封单": 'ld.first_time IS NOT NULL AND ld.last_time IS NOT NULL AND ld.first_time != ld.last_time AND ld.fd_amount > 0',
    "V5_纯非一字首板": 'ld.first_time IS NOT NULL AND ld.last_time IS NOT NULL AND ld.first_time != ld.last_time',
    "V6_非一字+未开板+早封": 'ld.first_time IS NOT NULL AND ld.last_time IS NOT NULL AND ld.first_time != ld.last_time AND ld.open_times = 0 AND ld.first_time < \'10:00\'',
}

results = {}
for name, entry_sql in VARIANTS.items():
    print(f"\n{'='*70}")
    print(f"回测: {name}")
    print(f"{'='*70}")
    config = {
        "entry_sql": entry_sql,
        "tables": {"ld": "tushare_limit_list_d"},
        "hold_periods": [1, 3, 5],
        "direction": "long",
        "max_signals": 100000  # 不限量
    }
    try:
        result = run_grid(config)
        results[name] = result
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"错误: {e}")
        results[name] = {"error": str(e)}

# 汇总输出
print("\n\n")
print("="*70)
print("最终汇总")
print("="*70)
print(f"{'变体':<30} {'n_1d':<8} {'WR_1d':<10} {'avg_1d':<12} {'CI_low_1d':<10} {'n_3d':<8} {'WR_3d':<10} {'avg_3d':<12} {'CI_low_3d':<10}")
print("-"*110)
for name in VARIANTS:
    r = results.get(name, {})
    if "error" in r:
        print(f"{name:<30} ERROR: {r['error']}")
        continue
    h1 = r.get("hold_1", {})
    h3 = r.get("hold_3", {})
    h5 = r.get("hold_5", {})
    print(f"{name:<30} "
          f"{h1.get('signal_count', 0):<8} {h1.get('win_rate', 0)*100:<10.2f} {h1.get('avg_return', 0)*100:<12.4f} {h1.get('ci_95_lower', 0)*100:<10.2f} "
          f"{h3.get('signal_count', 0):<8} {h3.get('win_rate', 0)*100:<10.2f} {h3.get('avg_return', 0)*100:<12.4f} {h3.get('ci_95_lower', 0)*100:<10.2f}")

print("-"*110)
print("注: WR=胜率, avg_ret=平均收益率(%), CI_low=Wilson置信区间下限(%)")
