#!/usr/bin/env python3
"""Round 9 — Quick focused tests"""
import json, sys, time, subprocess, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from grid_engine import run_grid, ch_query, compute_stats, load_trade_cal

def run_one(label, entry_sql, direction="short", hold_periods=[1,2,3,5], max_n=5000):
    print(f"\n{'='*55}")
    print(f"{label}")
    print(f"SQL: {entry_sql[:90]}")
    t0 = time.time()
    r = run_grid({
        "entry_sql": entry_sql,
        "tables": {"s": "tushare_stock_daily", "d": "tushare_daily_basic"},
        "hold_periods": hold_periods,
        "direction": direction,
        "max_signals": max_n,
    })
    print(f"⏱ {time.time()-t0:.0f}s")
    if "error" in r:
        print(f"  ❌ {r['error']}")
    else:
        for hp, s in r.items():
            wr, n = s['win_rate']*100, s['signal_count']
            ci = f"[{s['ci_95_lower']*100:.1f},{s['ci_95_upper']*100:.1f}]"
            ar = s['avg_return']*100
            print(f"  hold={hp}: n={n}, WR={wr:.1f}% CI={ci}, avg_ret={ar:.2f}%")
    return r

results = {}

# T1: Baseline (量比>3+涨幅>3% => 做空) — already done in round 8, small replication
results["baseline"] = run_one("T1: 量比>3+涨幅>3% => 做空 (baseline)", 
    "s.pct_chg > 3 AND d.volume_ratio > 3", max_n=5000)

# T2: gen_010 — 天量下跌+低开确认
results["gen010_gap1"] = run_one("T2: 量比>5+跌幅<-3%+低开>1% => 做空",
    "s.pct_chg < -3 AND d.volume_ratio > 5 AND s.open < s.pre_close * 0.99", max_n=5000)

# T3: gen_010 v2 — 天量下跌+大幅低开
results["gen010_gap2"] = run_one("T3: 量比>5+跌幅<-3%+低开>2% => 做空",
    "s.pct_chg < -3 AND d.volume_ratio > 5 AND s.open < s.pre_close * 0.98", max_n=3000)

# T4: gen_009 proxy — 放量暴涨 (extreme) => 做空
results["gen009_extreme"] = run_one("T4: 量比>4+涨幅>5% => 做空 (extreme)",
    "s.pct_chg > 5 AND d.volume_ratio > 4", max_n=3000)

# T5: 量比>3+涨幅>3%+close<20 (小市值偏好?) => 做空
results["small_cap"] = run_one("T5: 量比>3+涨幅>3%+小市值(circ_mv<50亿) => 做空",
    "s.pct_chg > 3 AND d.volume_ratio > 3 AND d.circ_mv < 5000000000", max_n=3000)

# T6: 量比>3+涨幅>3%+大市值 => 做空
results["large_cap"] = run_one("T6: 量比>3+涨幅>3%+大市值(circ_mv>100亿) => 做空",
    "s.pct_chg > 3 AND d.volume_ratio > 3 AND d.circ_mv > 10000000000", max_n=3000)

print("\n\n" + "="*55)
print("SUMMARY")
print("="*55)
print(json.dumps(results, ensure_ascii=False, indent=2))

with open("/tmp/round9_done.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
