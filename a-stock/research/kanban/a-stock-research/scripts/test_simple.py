#!/usr/bin/env python3
"""Round 9 — Simple direct tests using run_grid"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from grid_engine import run_grid, ch_query

EXCLUDE = """
  AND s.ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
  AND s.ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('2026-05-11', INTERVAL 1 YEAR))
  AND s.ts_code NOT IN (SELECT ts_code FROM tushare.tushare_suspend_d FINAL WHERE trade_date >= DATE_SUB('2026-05-11', INTERVAL 10 DAY))
"""

def run_test(label, entry_sql, tables, direction="short", hold_periods=[1,2,3,5], max_signals=10000):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"SQL: {entry_sql[:80]}...")
    print('='*60)
    t0 = time.time()
    config = {
        "entry_sql": entry_sql,
        "tables": tables,
        "hold_periods": hold_periods,
        "direction": direction,
        "max_signals": max_signals,
    }
    result = run_grid(config)
    elapsed = time.time() - t0
    print(f"Time: {elapsed:.1f}s")
    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        for hp, s in result.items():
            print(f"  {hp}: n={s['signal_count']}, WR={s['win_rate']:.2%}, avg_ret={s['avg_return']:.4f}, CI=[{s['ci_95_lower']:.2%},{s['ci_95_upper']:.2%}], Sharpe={s['sharpe_ratio']:.2f}, PF={s['profit_factor']:.2f}")
    return result


# Quick test to validate the approach
print("=== Testing grid_engine with a simple condition ===")
test = run_test("Quick check", "s.pct_chg > 3 AND d.volume_ratio > 3", 
                {"s": "tushare_stock_daily", "d": "tushare_daily_basic"},
                direction="short", max_signals=5000)

print("\n\nTest completed. Checking output...")
print(json.dumps(test, indent=2))
