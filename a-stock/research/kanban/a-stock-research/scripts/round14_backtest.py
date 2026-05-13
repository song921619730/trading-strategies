#!/usr/bin/env python3
"""
Round 14 Backtest — long_001a: 跳空高开 1.5-3% + 2024年后 → 持有1日做多（跨周期验证）

直连 ClickHouse 高效回测：用 SQL 一次性计算各持有期的收益。
"""
import json
import subprocess
import sys
from datetime import date, timedelta

CH_SCRIPT = "/mnt/f/AIcoding_space/skills/tushare-clickhouse-direct/scripts/ch_query.py"

def ch_query(sql: str) -> list[dict]:
    r = subprocess.run(
        ["python3", CH_SCRIPT, "sql", sql],
        capture_output=True, text=True, timeout=120
    )
    idx = r.stdout.find('[')
    if idx >= 0:
        return json.loads(r.stdout[idx:])
    print(f"CH ERROR: {r.stderr[:500]}", file=sys.stderr)
    print(f"STDOUT: {r.stdout[:500]}", file=sys.stderr)
    return []

# ─── 1. 交易日历 ───────────────────────────────────────────────
print("📅 Loading trade calendar...")
cal_rows = ch_query(
    "SELECT cal_date FROM tushare.tushare_trade_cal FINAL "
    "WHERE exchange='SSE' AND is_open=1 ORDER BY cal_date"
)
trade_dates = [r["cal_date"] for r in cal_rows]
trade_set = set(trade_dates)
print(f"   {len(trade_dates)} trading days loaded")

def next_n_trade_day(start_date: str, n: int) -> str:
    """Return the Nth trading day after start_date"""
    if start_date not in trade_set:
        for d in trade_dates:
            if d >= start_date:
                start_date = d
                break
    idx = trade_dates.index(start_date)
    target = idx + n
    if target < len(trade_dates):
        return trade_dates[target]
    return None

# ─── 2. 获取所有 entry signals（2024+）───────────────────────────
print("🔍 Getting entry signals (2024+)...")

# Use window function to get future close prices directly
# This avoids the slow batch-by-batch exit price lookup
sql = """
SELECT 
    ts_code,
    trade_date,
    open,
    pre_close,
    close as entry_close,
    pct_chg as entry_pct,
    open / pre_close as gap_ratio,
    LEAD(close, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) AS exit_1d,
    LEAD(close, 3) OVER (PARTITION BY ts_code ORDER BY trade_date) AS exit_3d,
    LEAD(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) AS exit_5d,
    LEAD(close, 10) OVER (PARTITION BY ts_code ORDER BY trade_date) AS exit_10d
FROM (
    SELECT * FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2024-01-01'
      AND trade_date <= '2026-05-11'
)
WHERE open / pre_close BETWEEN 1.015 AND 1.03
  AND close > 0
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('2026-05-11', INTERVAL 1 YEAR))
ORDER BY ts_code, trade_date
"""

signals = ch_query(sql)
print(f"   Got {len(signals)} signals")

if not signals:
    print("No signals found!")
    sys.exit(1)

# ─── 3. 计算各持有期收益 ───────────────────────────────────────
def calc_stats(signals, hold_key, label):
    """Calculate win rate and avg return for a given hold period"""
    results = []
    for s in signals:
        exit_price = s.get(hold_key)
        entry = s["entry_close"]
        if exit_price is None or exit_price == 0:
            continue
        ret = (exit_price - entry) / entry * 100
        results.append(ret)
    
    n = len(results)
    if n == 0:
        return {"hold": label, "n": 0, "wr": 0, "avg_ret": 0}
    
    wins = sum(1 for r in results if r > 0)
    wr = wins / n * 100
    avg_ret = sum(results) / n
    
    # 95% CI for WR using normal approximation
    import math
    se = math.sqrt(wr/100 * (1-wr/100) / n) if n > 0 else 0
    ci_lower = (wr/100 - 1.96 * se) * 100
    
    return {
        "hold": label,
        "n": n,
        "wr": round(wr, 2),
        "avg_ret": round(avg_ret, 4),
        "ci_lower": round(ci_lower, 2),
        "total_return": round(sum(results), 2),
        "max_return": round(max(results), 2),
        "min_return": round(min(results), 2),
    }

stats = {}
for hold_key, label in [("exit_1d", 1), ("exit_3d", 3), ("exit_5d", 5), ("exit_10d", 10)]:
    stats[label] = calc_stats(signals, hold_key, label)

print("\n" + "="*60)
print("📊 回测结果：跳空高开 1.5-3%（2024+）")
print("="*60)
print(f"{'持有':>6} | {'信号数':>8} | {'胜率%':>8} | {'平均收益%':>10} | {'CI 下限%':>8}")
print("-"*60)
for hp in [1, 3, 5, 10]:
    s = stats[hp]
    print(f"{s['hold']:>6} | {s['n']:>8} | {s['wr']:>8.2f} | {s['avg_ret']:>10.4f} | {s['ci_lower']:>8.2f}")
print("="*60)

# ─── 4. 跨周期对比（2020-2023）─────────────────────────────────
print("\n📊 跨周期对比：跳空高开 1.5-3%（2020-2023 vs 2024+）")

sql_old = """
SELECT 
    ts_code,
    trade_date,
    open,
    pre_close,
    close as entry_close,
    pct_chg as entry_pct,
    open / pre_close as gap_ratio,
    LEAD(close, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) AS exit_1d,
    LEAD(close, 5) OVER (PARTITION BY ts_code ORDER BY trade_date) AS exit_5d
FROM (
    SELECT * FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2020-01-02'
      AND trade_date <= '2023-12-31'
)
WHERE open / pre_close BETWEEN 1.015 AND 1.03
  AND close > 0
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('2023-12-31', INTERVAL 1 YEAR))
ORDER BY ts_code, trade_date
"""

signals_old = ch_query(sql_old)
print(f"   2020-2023: {len(signals_old)} signals")

stats_old = {}
for hold_key, label in [("exit_1d", 1), ("exit_5d", 5)]:
    stats_old[label] = calc_stats(signals_old, hold_key, label)

print(f"\n{'时期':>12} | {'持有':>6} | {'信号数':>8} | {'胜率%':>8} | {'平均收益%':>10} | {'CI 下限%':>8}")
print("-"*65)
for period, st, signame in [("2020-2023", stats_old, "old"), ("2024+", stats, "new")]:
    for hp in [1, 5]:
        s = st[hp]
        print(f"{period:>12} | {s['hold']:>6} | {s['n']:>8} | {s['wr']:>8.2f} | {s['avg_ret']:>10.4f} | {s['ci_lower']:>8.2f}")

# ─── 5. 涨跌幅过滤（排除一字板）───────────────────────────────
print("\n📊 涨跌幅过滤（排除 pct_chg 异常值）")

sql_filtered = """
SELECT 
    ts_code,
    trade_date,
    open,
    pre_close,
    close as entry_close,
    pct_chg as entry_pct,
    LEAD(close, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) AS exit_1d
FROM (
    SELECT * FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2024-01-01'
      AND trade_date <= '2026-05-11'
)
WHERE open / pre_close BETWEEN 1.015 AND 1.03
  AND close > 0
  AND pct_chg BETWEEN -9.5 AND 10  -- 排除一字涨停/跌停
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_st FINAL WHERE st_type IS NOT NULL AND st_type != '')
  AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_new_share FINAL WHERE ipo_date >= DATE_SUB('2026-05-11', INTERVAL 1 YEAR))
ORDER BY ts_code, trade_date
"""

signals_filtered = ch_query(sql_filtered)
print(f"   Filtered signals: {len(signals_filtered)}")

st_f = calc_stats(signals_filtered, "exit_1d", 1)
print(f"   Hold 1: WR={st_f['wr']}%, avg_ret={st_f['avg_ret']}%, n={st_f['n']}")

# ─── 6. 按缺口幅度细分 ────────────────────────────────────────
print("\n📊 按缺口幅度细分")
# 1.5-2%, 2-2.5%, 2.5-3%
for lo, hi, label in [(1.015, 1.02, "1.5-2%"), (1.02, 1.025, "2-2.5%"), (1.025, 1.03, "2.5-3%")]:
    sql_sub = f"""
    SELECT 
        ts_code, trade_date, open, pre_close, close as entry_close, pct_chg as entry_pct,
        LEAD(close, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) AS exit_1d
    FROM (
        SELECT * FROM tushare.tushare_stock_daily FINAL
        WHERE trade_date >= '2024-01-01' AND trade_date <= '2026-05-11'
    )
    WHERE open / pre_close BETWEEN {lo} AND {hi}
      AND close > 0
    ORDER BY ts_code, trade_date
    """
    sub_signals = ch_query(sql_sub)
    sub_stat = calc_stats(sub_signals, "exit_1d", 1)
    print(f"   {label}: n={sub_stat['n']}, WR={sub_stat['wr']}%, avg_ret={sub_stat['avg_ret']}%")

print("\n✅ Round 14 backtest complete!")
