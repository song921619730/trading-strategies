#!/usr/bin/env python3
"""
TechnicalAnalyst: long_005 回测验证
涨停首板(非一字) + 封板率>70% → 次日溢价做多

Using up_stat field from tushare_limit_list_d for封板率:
  up_stat format: 'success/total' → 封板率 = success/total
  E.g., '1/1' = 100%, '2/3' = 66.7%, '1/2' = 50%

Note: limit_times field is only populated from 2026-04-24 onwards.
For 2020-2025, limit_times=0 for all entries, so首板 filter is approximated.
"""

import json
import subprocess
import sys
from datetime import date, timedelta

sys.path.insert(0, '.')
from grid_engine import run_grid, ch_query

# ─── Helper ──────────────────────────────────────────
def print_result(label: str, result: dict):
    """格式化打印回测结果"""
    if "error" in result:
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
        print(f"  ❌ ERROR: {result['error']}")
        return

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    for hp_key in sorted(result.keys()):
        s = result[hp_key]
        print(f"\n  📊 {hp_key}:")
        print(f"     信号数量:   {s['signal_count']}")
        print(f"     胜率:       {s['win_rate']:.2%}  [{s['ci_95_lower']:.1%}, {s['ci_95_upper']:.1%}]")
        print(f"     平均收益:   {s['avg_return']:.4f} ({s['avg_return']*100:.2f}%)")
        print(f"     平均盈利:   {s['avg_win']:.4f}")
        print(f"     平均亏损:   {s['avg_loss']:.4f}")
        print(f"     盈亏比:     {s['profit_factor']:.2f}")
        print(f"     夏普比率:   {s['sharpe_ratio']:.2f}")
        print(f"     最大回撤:   {s['max_drawdown']:.2%}")


def build_seal_rate_condition(min_rate: float) -> str:
    """构建封板率条件SQL: up_stat格式'success/total', 计算 success/total >= min_rate"""
    return (
        f"toFloat64OrZero(substring(limit_list.up_stat, 1, "
        f"position(limit_list.up_stat, '/')-1)) / "
        f"toFloat64OrZero(substring(limit_list.up_stat, "
        f"position(limit_list.up_stat, '/')+1)) >= {min_rate}"
    )


# ─── Common base conditions ──────────────────────────
# Non-一字首板: first_time IS NOT NULL, last_time IS NOT NULL, first_time != last_time
# Also exclude stocks that never hit limit-up (first_time='0')
NON_YI_ZHI = (
    "limit_list.first_time IS NOT NULL "
    "AND limit_list.first_time != '0' "
    "AND limit_list.last_time IS NOT NULL "
    "AND limit_list.first_time != limit_list.last_time"
)

# For 2026 data: add limit_times=1 for首板 filter
LIMIT_TIMES_1 = (
    "(limit_list.limit_times = 1 OR limit_list.trade_date < '2026-01-01')"
)

# For strict首板 (only 2026 where limit_times is populated)
STRICT_SHOU_BAN = "limit_list.limit_times = 1"


# ─── Variant Definitions ─────────────────────────────

def run_variant(name: str, entry_cond: str, hold_periods=None):
    """Run a single backtest variant using grid_engine"""
    if hold_periods is None:
        hold_periods = [1, 3, 5, 10]

    config = {
        "entry_sql": entry_cond,
        "tables": {"limit_list": "tushare_limit_list_d"},
        "hold_periods": hold_periods,
        "direction": "long",
        "max_signals": 50000,
    }

    return run_grid(config)


# ═══════════════════════════════════════════════════════
# DATA OVERVIEW
# ═══════════════════════════════════════════════════════
print("=" * 70)
print("  🔍 long_005 回测: 涨停首板(非一字) + 封板率>70%")
print("  Technical Analysts — A股技术面模式挖掘")
print("=" * 70)
print()

# Check data ranges
print("── 数据概况 ──")
ranges = ch_query("""
    SELECT 
        min(trade_date) as min_d,
        max(trade_date) as max_d,
        count() as cnt,
        countIf(up_stat IS NOT NULL AND substring(up_stat,1,1) != '0') as has_limit,
        countIf(first_time IS NOT NULL AND first_time != '0' 
                AND last_time IS NOT NULL 
                AND first_time != last_time) as fei_yi_zhi_cnt
    FROM tushare.tushare_limit_list_d FINAL
""")
for r in ranges:
    if r:
        print(f"  数据范围: {r['min_d']} ~ {r['max_d']}")
        print(f"  总行数: {r['cnt']:,}")
        print(f"  有涨停记录: {r['has_limit']:,}")
        print(f"  非一字板: {r['fei_yi_zhi_cnt']:,}")
    else:
        print("  No data returned")
    print()

# For direct queries, don't use alias prefix
NON_YI_ZHI_DIRECT = (
    "first_time IS NOT NULL "
    "AND first_time != '0' "
    "AND last_time IS NOT NULL "
    "AND first_time != last_time"
)

def build_seal_rate_cond_direct(min_rate: float) -> str:
    return (
        f"toFloat64OrZero(substring(up_stat, 1, "
        f"position(up_stat, '/')-1)) / "
        f"toFloat64OrZero(substring(up_stat, "
        f"position(up_stat, '/')+1)) >= {min_rate}"
    )

# Check sample signals for each variant
print("── 样本信号量预览 (2026年) ──")
sql_non_yi_zhi = f"""
    SELECT count() as cnt
    FROM tushare.tushare_limit_list_d FINAL
    WHERE trade_date >= '2026-01-01'
      AND {NON_YI_ZHI_DIRECT}
"""
rows = ch_query(sql_non_yi_zhi)
print(f"  非一字板 (2026): {rows[0]['cnt'] if rows else 'ERROR'}")

for rate_name, min_rate in [("≥70%", 0.7), ("≥80%", 0.8), ("≥60%", 0.6)]:
    seal_cond = build_seal_rate_cond_direct(min_rate)
    sql = f"""
        SELECT count() as cnt
        FROM tushare.tushare_limit_list_d FINAL
        WHERE trade_date >= '2026-01-01'
          AND {NON_YI_ZHI_DIRECT}
          AND {seal_cond}
    """
    rows = ch_query(sql)
    print(f"  非一字板 + 封板率{rate_name} (2026): {rows[0]['cnt'] if rows else 'ERROR'}")

# Early seal (first_time before 14:00)
seal_cond_70_direct = build_seal_rate_cond_direct(0.7)
sql_early = f"""
    SELECT count() as cnt
    FROM tushare.tushare_limit_list_d FINAL
    WHERE trade_date >= '2026-01-01'
      AND {NON_YI_ZHI_DIRECT}
      AND {seal_cond_70_direct}
      AND toUInt32(first_time) < 140000
"""
rows = ch_query(sql_early)
print(f"  非一字板 + 封板率≥70% + 首封<14:00 (2026): {rows[0]['cnt'] if rows else 'ERROR'}")

# With limit_times=1 (首板)
sql_shouban = f"""
    SELECT count() as cnt
    FROM tushare.tushare_limit_list_d FINAL
    WHERE trade_date >= '2026-04-24'
      AND {NON_YI_ZHI_DIRECT}
      AND limit_times = 1
      AND {seal_cond_70_direct}
"""
rows = ch_query(sql_shouban)
print(f"  首板(limit_times=1) + 非一字 + 封板率≥70% (2026): {rows[0]['cnt'] if rows else 'ERROR'}")
print()

# ═══════════════════════════════════════════════════════
# FULL PERIOD BACKTESTS (2020-2026)
# ═══════════════════════════════════════════════════════
print("=" * 70)
print("  📈 FULL PERIOD BACKTESTS (2020-2026)")
print("  Using: non-一字板 condition (all available years)")
print("  Note: limit_times field only available from 2026-04")
print("=" * 70)

all_results = {}

# ─── Variant a: 基础版 非一字首板 + 封板率>=70% ───
label_a = "Variant A: 非一字板 + 封板率≥70% (基础版)"
cond_a = f"""
    {NON_YI_ZHI}
    AND {LIMIT_TIMES_1}
    AND {build_seal_rate_condition(0.7)}
"""
result_a = run_variant(label_a, cond_a)
all_results["a_基础版_70"] = result_a
print_result(label_a, result_a)

# ─── Variant b: 严格版 非一字首板 + 封板率>=80% ───
label_b = "Variant B: 非一字板 + 封板率≥80% (严格版)"
cond_b = f"""
    {NON_YI_ZHI}
    AND {LIMIT_TIMES_1}
    AND {build_seal_rate_condition(0.8)}
"""
result_b = run_variant(label_b, cond_b)
all_results["b_严格版_80"] = result_b
print_result(label_b, result_b)

# ─── Variant c: 宽松版 非一字首板 + 封板率>=60% ───
label_c = "Variant C: 非一字板 + 封板率≥60% (宽松版)"
cond_c = f"""
    {NON_YI_ZHI}
    AND {LIMIT_TIMES_1}
    AND {build_seal_rate_condition(0.6)}
"""
result_c = run_variant(label_c, cond_c)
all_results["c_宽松版_60"] = result_c
print_result(label_c, result_c)

# ─── Variant d: 时间过滤版 首封时间<14:00 + 封板率>=70% ───
label_d = "Variant D: 非一字板 + 封板率≥70% + 首封<14:00 (时间过滤版)"
cond_d = f"""
    {NON_YI_ZHI}
    AND {LIMIT_TIMES_1}
    AND {build_seal_rate_condition(0.7)}
    AND toUInt32(limit_list.first_time) < 140000
"""
result_d = run_variant(label_d, cond_d)
all_results["d_时间过滤版_early"] = result_d
print_result(label_d, result_d)

# ═══════════════════════════════════════════════════════
# 2026-ONLY BACKTEST (with strict limit_times=1)
# ═══════════════════════════════════════════════════════
print()
print("=" * 70)
print("  📈 2026-ONLY BACKTEST (strict 首板 with limit_times=1)")
print("  Only available from 2026-04-24 to 2026-05-11")
print("=" * 70)

strict_results = {}

# ─── Variant a-strict: 首板 + 封板率>=70% ───
label_a2 = "Variant A-strict: 首板(limit_times=1) + 非一字 + 封板率≥70%"
cond_a2 = f"""
    {NON_YI_ZHI}
    AND {STRICT_SHOU_BAN}
    AND {build_seal_rate_condition(0.7)}
    AND limit_list.trade_date >= '2026-04-24'
"""
result_a2 = run_variant(label_a2, cond_a2)
strict_results["a_strict_70"] = result_a2
print_result(label_a2, result_a2)

# ─── Variant b-strict: 首板 + 封板率>=80% ───
label_b2 = "Variant B-strict: 首板(limit_times=1) + 非一字 + 封板率≥80%"
cond_b2 = f"""
    {NON_YI_ZHI}
    AND {STRICT_SHOU_BAN}
    AND {build_seal_rate_condition(0.8)}
    AND limit_list.trade_date >= '2026-04-24'
"""
result_b2 = run_variant(label_b2, cond_b2)
strict_results["b_strict_80"] = result_b2
print_result(label_b2, result_b2)

# ─── Variant c-strict: 首板 + 封板率>=60% ───
label_c2 = "Variant C-strict: 首板(limit_times=1) + 非一字 + 封板率≥60%"
cond_c2 = f"""
    {NON_YI_ZHI}
    AND {STRICT_SHOU_BAN}
    AND {build_seal_rate_condition(0.6)}
    AND limit_list.trade_date >= '2026-04-24'
"""
result_c2 = run_variant(label_c2, cond_c2)
strict_results["c_strict_60"] = result_c2
print_result(label_c2, result_c2)

# ─── Variant d-strict: 首板 + 封板率>=70% + 首封<14:00 ───
label_d2 = "Variant D-strict: 首板(limit_times=1) + 非一字 + 封板率≥70% + 首封<14:00"
cond_d2 = f"""
    {NON_YI_ZHI}
    AND {STRICT_SHOU_BAN}
    AND {build_seal_rate_condition(0.7)}
    AND toUInt32(limit_list.first_time) < 140000
    AND limit_list.trade_date >= '2026-04-24'
"""
result_d2 = run_variant(label_d2, cond_d2)
strict_results["d_strict_early"] = result_d2
print_result(label_d2, result_d2)


# ═══════════════════════════════════════════════════════
# SUMMARY COMPARISON
# ═══════════════════════════════════════════════════════
print()
print("=" * 70)
print("  📊 SUMMARY COMPARISON")
print("=" * 70)
print()

# Full period summary table
print(f"{'Variant':<40} {'HP':<5} {'Signals':<8} {'WinRate':<10} {'AvgRet':<10} {'Sharpe':<8} {'ProfitFactor':<10}")
print("-" * 95)

for var_key in ["a_基础版_70", "b_严格版_80", "c_宽松版_60", "d_时间过滤版_early"]:
    var_names = {
        "a_基础版_70": "A:≥70%",
        "b_严格版_80": "B:≥80%",
        "c_宽松版_60": "C:≥60%",
        "d_时间过滤版_early": "D:early<14:00",
    }
    result = all_results.get(var_key, {})
    if "error" in result:
        continue
    for hp_key in sorted(result.keys()):
        s = result[hp_key]
        label = var_names[var_key]
        print(f"{label:<40} {hp_key:<5} {s['signal_count']:<8} {s['win_rate']:<10.2%} {s['avg_return']:<10.4f} {s['sharpe_ratio']:<8.2f} {s['profit_factor']:<10.2f}")

# Generate comparison dict for log output
comparison = {
    "full_period": {},
    "strict_2026": {}
}

for var_key, result in all_results.items():
    comparison["full_period"][var_key] = {}
    for hp_key in sorted(result.keys()):
        s = result[hp_key]
        comparison["full_period"][var_key][hp_key] = {
            "signal_count": s["signal_count"],
            "win_rate": s["win_rate"],
            "avg_return": s["avg_return"],
            "profit_factor": s["profit_factor"],
            "sharpe_ratio": s["sharpe_ratio"],
            "max_drawdown": s["max_drawdown"],
        }

for var_key, result in strict_results.items():
    comparison["strict_2026"][var_key] = {}
    for hp_key in sorted(result.keys()):
        s = result[hp_key]
        comparison["strict_2026"][var_key][hp_key] = {
            "signal_count": s["signal_count"],
            "win_rate": s["win_rate"],
            "avg_return": s["avg_return"],
            "profit_factor": s["profit_factor"],
            "sharpe_ratio": s["sharpe_ratio"],
            "max_drawdown": s["max_drawdown"],
        }

print()
print("JSON summary for logging:")
print(json.dumps(comparison, ensure_ascii=False, indent=2))
