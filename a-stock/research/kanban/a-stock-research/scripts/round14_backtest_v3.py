#!/usr/bin/env python3
"""
Round 14 Backtest v3 — long_001a: 跳空高开 1.5-3% + 2024年后
使用 ClickHouse leadInFrame 窗口函数一次性计算收益
"""
import json
import math
import subprocess
import sys

CH_SCRIPT = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"

def ch_query(sql: str) -> list[dict]:
    r = subprocess.run(
        ["python3", CH_SCRIPT, "sql", sql],
        capture_output=True, text=True, timeout=300
    )
    idx = r.stdout.find('[')
    if idx >= 0:
        return json.loads(r.stdout[idx:])
    print(f"CH ERROR: {r.stderr[:500]}", file=sys.stderr)
    print(f"STDOUT: {r.stdout[:500]}", file=sys.stderr)
    return []

def calc_stats(results, label):
    n = len(results)
    if n == 0:
        return {"hold": label, "n": 0, "wr": 0, "avg_ret": 0, "ci_lower": 0}
    wins = sum(1 for r in results if r > 0)
    wr = wins / n * 100
    avg_ret = sum(results) / n
    se = math.sqrt(wr/100 * (1-wr/100) / n) if n > 0 else 0
    ci_lower = (wr/100 - 1.96 * se) * 100
    return {
        "hold": label, "n": n, "wr": round(wr, 2),
        "avg_ret": round(avg_ret, 4), "ci_lower": round(ci_lower, 2),
        "total_return": round(sum(results), 2),
        "positive_sum": round(sum(r for r in results if r > 0), 2),
        "negative_sum": round(sum(r for r in results if r < 0), 2),
    }

# ─── 1. 主回测：2024+ 跳空高开 1.5-3% ──────────────────────────
print("="*60)
print("📊 回测 1: 跳空高开 1.5-3%（2024-01-01 ~ 2026-05-11）")
print("="*60)

sql_main = """
SELECT 
    ts_code,
    trade_date,
    open,
    pre_close,
    close AS entry_close,
    pct_chg AS entry_pct,
    open / pre_close AS gap_ratio,
    leadInFrame(close, 1) OVER (PARTITION BY ts_code ORDER BY trade_date ASC ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS exit_1d,
    leadInFrame(close, 3) OVER (PARTITION BY ts_code ORDER BY trade_date ASC ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS exit_3d,
    leadInFrame(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date ASC ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS exit_5d,
    leadInFrame(close, 10) OVER (PARTITION BY ts_code ORDER BY trade_date ASC ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS exit_10d
FROM (
    SELECT * FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2024-01-01' AND trade_date <= '2026-05-11'
)
WHERE open / pre_close BETWEEN 1.015 AND 1.03
  AND close > 0
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('2026-05-11', INTERVAL 1 YEAR))
ORDER BY ts_code, trade_date
"""

signals = ch_query(sql_main)
n_total = len(signals)
print(f"   总信号数: {n_total}")

if n_total == 0:
    print("No signals found!")
    sys.exit(1)

for hold_key, label in [("exit_1d", 1), ("exit_3d", 3), ("exit_5d", 5), ("exit_10d", 10)]:
    returns = []
    for s in signals:
        exit_price = s.get(hold_key)
        if exit_price is not None and exit_price > 0:
            ret = (exit_price - s["entry_close"]) / s["entry_close"] * 100
            returns.append(ret)
    st = calc_stats(returns, label)
    print(f"   持有 {label}日: n={st['n']}, WR={st['wr']}%, avg_ret={st['avg_ret']}%, CI_lower={st['ci_lower']}%, pos_sum={st['positive_sum']}, neg_sum={st['negative_sum']}")

# ─── 2. 跨周期对比：2020-2023 ──────────────────────────────────
print()
print("="*60)
print("📊 回测 2: 跨周期对比（2020-2023）")
print("="*60)

sql_old = """
SELECT 
    ts_code,
    trade_date,
    open,
    pre_close,
    close AS entry_close,
    pct_chg AS entry_pct,
    open / pre_close AS gap_ratio,
    leadInFrame(close, 1) OVER (PARTITION BY ts_code ORDER BY trade_date ASC ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS exit_1d,
    leadInFrame(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date ASC ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS exit_5d
FROM (
    SELECT * FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2020-01-02' AND trade_date <= '2023-12-31'
)
WHERE open / pre_close BETWEEN 1.015 AND 1.03
  AND close > 0
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('2023-12-31', INTERVAL 1 YEAR))
ORDER BY ts_code, trade_date
"""

signals_old = ch_query(sql_old)
n_old = len(signals_old)
print(f"   总信号数 (2020-2023): {n_old}")

for hold_key, label in [("exit_1d", 1), ("exit_5d", 5)]:
    returns = []
    for s in signals_old:
        exit_price = s.get(hold_key)
        if exit_price is not None and exit_price > 0:
            ret = (exit_price - s["entry_close"]) / s["entry_close"] * 100
            returns.append(ret)
    st = calc_stats(returns, label)
    print(f"   持有 {label}日: n={st['n']}, WR={st['wr']}%, avg_ret={st['avg_ret']}%, CI_lower={st['ci_lower']}%")

# ─── 3. 对比表 ────────────────────────────────────────────────
print()
print("="*60)
print("📊 跨周期对比总结")
print("="*60)
print(f"{'时期':>12} | {'持有':>6} | {'信号数':>8} | {'胜率%':>8} | {'平均收益%':>10} | {'CI下限%':>8}")
print("-"*65)

# Recalculate for display
for hold_key, label in [("exit_1d", 1), ("exit_5d", 5)]:
    ret_new = [(s.get(hold_key) - s["entry_close"]) / s["entry_close"] * 100 
               for s in signals if s.get(hold_key) is not None and s.get(hold_key) > 0]
    st_new = calc_stats(ret_new, label)
    ret_old = [(s.get(hold_key) - s["entry_close"]) / s["entry_close"] * 100 
               for s in signals_old if s.get(hold_key) is not None and s.get(hold_key) > 0]
    st_old = calc_stats(ret_old, label)
    
    print(f"{'2020-2023':>12} | {st_old['hold']:>6} | {st_old['n']:>8} | {st_old['wr']:>8.2f} | {st_old['avg_ret']:>10.4f} | {st_old['ci_lower']:>8.2f}")
    print(f"{'2024+':>12} | {st_new['hold']:>6} | {st_new['n']:>8} | {st_new['wr']:>8.2f} | {st_new['avg_ret']:>10.4f} | {st_new['ci_lower']:>8.2f}")
    print("-"*65)

# ─── 4. 缺口幅度细分 ──────────────────────────────────────────
print()
print("="*60)
print("📊 缺口幅度细分 (2024+, Hold 1日)")
print("="*60)

for lo, hi, label in [(1.015, 1.02, "1.5-2%"), (1.02, 1.025, "2-2.5%"), (1.025, 1.03, "2.5-3%")]:
    sub_returns = []
    for s in signals:
        if lo <= s["gap_ratio"] < hi:
            if s["exit_1d"] is not None and s["exit_1d"] > 0:
                ret = (s["exit_1d"] - s["entry_close"]) / s["entry_close"] * 100
                sub_returns.append(ret)
    st = calc_stats(sub_returns, 1)
    print(f"   {label}: n={st['n']}, WR={st['wr']}%, avg_ret={st['avg_ret']}%, CI_lower={st['ci_lower']}%")

# ─── 5. 涨跌幅过滤 ────────────────────────────────────────────
print()
print("="*60)
print("📊 排除 pct_chg 异常值后 (2024+, Hold 1日)")
print("="*60)

filtered_returns = []
for s in signals:
    if -9.5 <= s["entry_pct"] <= 10:  # 可正常买入
        if s["exit_1d"] is not None and s["exit_1d"] > 0:
            ret = (s["exit_1d"] - s["entry_close"]) / s["entry_close"] * 100
            filtered_returns.append(ret)
st_f = calc_stats(filtered_returns, 1)
print(f"   过滤后: n={st_f['n']}, WR={st_f['wr']}%, avg_ret={st_f['avg_ret']}%, CI_lower={st_f['ci_lower']}%")
print(f"   过滤掉了 {n_total - st_f['n']} 个信号")

# ─── 6. 每月胜率趋势 ──────────────────────────────────────────
print()
print("="*60)
print("📊 月度胜率趋势 (2024+, Hold 1日)")
print("="*60)

from collections import defaultdict
monthly = defaultdict(list)
for s in signals:
    if s["exit_1d"] is not None and s["exit_1d"] > 0:
        ret = (s["exit_1d"] - s["entry_close"]) / s["entry_close"] * 100
        month = s["trade_date"][:7]  # YYYY-MM
        monthly[month].append(ret)

for month in sorted(monthly.keys()):
    rets = monthly[month]
    wins = sum(1 for r in rets if r > 0)
    wr = wins / len(rets) * 100
    avg_r = sum(rets) / len(rets)
    print(f"   {month}: n={len(rets):>6}, WR={wr:>5.1f}%, avg_ret={avg_r:>+.4f}%")

# ─── 7. 按年度细分 ────────────────────────────────────────────
print()
print("="*60)
print("📊 按年度细分 (Hold 1日)")
print("="*60)

yearly = defaultdict(list)
for s in signals:
    if s["exit_1d"] is not None and s["exit_1d"] > 0:
        ret = (s["exit_1d"] - s["entry_close"]) / s["entry_close"] * 100
        year = s["trade_date"][:4]
        yearly[year].append(ret)
yearly_old = defaultdict(list)
for s in signals_old:
    if s["exit_1d"] is not None and s["exit_1d"] > 0:
        ret = (s["exit_1d"] - s["entry_close"]) / s["entry_close"] * 100
        year = s["trade_date"][:4]
        yearly_old[year].append(ret)

for year in sorted(set(list(yearly.keys()) + list(yearly_old.keys()))):
    rets = yearly.get(year, []) + yearly_old.get(year, [])
    if not rets:
        continue
    wins = sum(1 for r in rets if r > 0)
    wr = wins / len(rets) * 100
    avg_r = sum(rets) / len(rets)
    print(f"   {year}: n={len(rets):>7}, WR={wr:>5.1f}%, avg_ret={avg_r:>+.4f}%")

print()
print("✅ Round 14 回测完成!")
