#!/usr/bin/env python3
"""
Round 10 — gen_004:
早盘30分钟量比>3 + 振幅<2% + 主力净流入 → 盘中拉升

Data constraints:
- stk_factor_pro (volume_ratio, OHLC) only non-zero from 2026-04-24
- moneyflow (net_mf_amount) available from 2020-01-02
"""

import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grid_engine import run_grid, get_research_range

# ─── Test A: Full hypothesis (limited window due to stk_factor_pro) ──────────
# Condition: volume_ratio > 3 AND amplitude < 2% (daily) AND net main fund inflow > 0
# Amplitude computed as (high - low) / pre_close * 100

config_a = {
    "entry_sql": (
        "f.volume_ratio > 3 "
        "AND (f.high - f.low) / f.pre_close * 100 < 2 "
        "AND m.net_mf_amount > 0"
    ),
    "tables": {
        "f": "tushare_stk_factor_pro",
        "m": "tushare_moneyflow"
    },
    "hold_periods": [1, 2, 3, 5],
    "direction": "long",
    "max_signals": 50000
}

# ─── Test B: Baseline — amplitude < 2% + net_mf_amount > 0 (full range) ─────
# Using stock_daily for amplitude calc + moneyflow for fund flow
config_b = {
    "entry_sql": (
        "(s.high - s.low) / s.pre_close * 100 < 2 "
        "AND m.net_mf_amount > 0"
    ),
    "tables": {
        "s": "tushare_stock_daily",
        "m": "tushare_moneyflow"
    },
    "hold_periods": [1, 2, 3, 5],
    "direction": "long",
    "max_signals": 50000
}

# ─── Test C: volume_ratio > 3 + amplitude < 2% (no moneyflow, limited window)
config_c = {
    "entry_sql": (
        "f.volume_ratio > 3 "
        "AND (f.high - f.low) / f.pre_close * 100 < 2"
    ),
    "tables": {
        "f": "tushare_stk_factor_pro"
    },
    "hold_periods": [1, 2, 3, 5],
    "direction": "long",
    "max_signals": 50000
}

# ─── Test D: volume_ratio > 3 + net_mf_amount > 0 (no amplitude constraint)
config_d = {
    "entry_sql": (
        "f.volume_ratio > 3 "
        "AND m.net_mf_amount > 0"
    ),
    "tables": {
        "f": "tushare_stk_factor_pro",
        "m": "tushare_moneyflow"
    },
    "hold_periods": [1, 2, 3, 5],
    "direction": "long",
    "max_signals": 50000
}

tests = [
    ("A", "量比>3 + 振幅<2% + 主力净流入>0 (完整条件)", config_a),
    ("B", "振幅<2% + 主力净流入>0 (无量比, 全范围基线)", config_b),
    ("C", "量比>3 + 振幅<2% (无资金流)", config_c),
    ("D", "量比>3 + 主力净流入>0 (无振幅约束)", config_d),
]

results = {}
for test_id, desc, cfg in tests:
    print(f"\n{'='*60}")
    print(f"Test {test_id}: {desc}")
    print(f"{'='*60}")
    try:
        r = run_grid(cfg)
        results[test_id] = {"description": desc, "config": cfg, "results": r}
        print(json.dumps(r, ensure_ascii=False, indent=2))
    except Exception as e:
        results[test_id] = {"description": desc, "config": cfg, "error": str(e)}
        print(f"ERROR: {e}")

# Save results
out = {
    "hypothesis_id": "gen_004",
    "hypothesis": "早盘30分钟量比>3+振幅<2%+主力净流入 → 盘中拉升",
    "direction": "long",
    "source": "Candle_R5",
    "data_note": (
        "stk_factor_pro 的 volume_ratio 和 OHLC 字段在 2026-04-24 前为零填充, "
        "所以涉及 volume_ratio 的测试 (A/C/D) 仅覆盖 2026-04-24 ~ 2026-05-11 共5个交易日。"
        "Test B 使用 stock_daily + moneyflow, 覆盖 2020-01-02 ~ 2026-05-11 全范围。"
    ),
    "tests": results
}

out_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs", f"round_010", "00_findings.json"
)
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"\nResults saved to {out_path}")
