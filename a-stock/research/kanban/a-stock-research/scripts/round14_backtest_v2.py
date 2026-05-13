#!/usr/bin/env python3
"""
Round 14 Backtest v2 — long_001a: 跳空高开 1.5-3% + 2024年后
使用 ClickHouse 兼容的窗口函数语法
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
    }

# ─── Get trade dates ───────────────────────────────────────────
print("📅 Loading trade calendar...")
cal = ch_query("SELECT cal_date FROM tushare.tushare_trade_cal FINAL WHERE exchange='SSE' AND is_open=1 ORDER BY cal_date")
trade_dates = [r["cal_date"] for r in cal]
trade_set = set(trade_dates)
print(f"   {len(trade_dates)} trading days")

def nth_trade_day(start, n):
    if start not in trade_set:
        for d in trade_dates:
            if d >= start:
                start = d
                break
    idx = trade_dates.index(start)
    if idx + n < len(trade_dates):
        return trade_dates[idx + n]
    return None

# ─── Approach: Get entry signals, then batch query exit prices ─
print("🔍 Getting entry signals...")

# Step 1: Get all entry signals (stock_daily only has ~750万 rows, should be fast)
entry_sql = """
SELECT 
    ts_code,
    trade_date,
    open,
    pre_close,
    close AS entry_close,
    pct_chg AS entry_pct,
    open / pre_close AS gap_ratio
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

entries = ch_query(entry_sql)
print(f"   Got {len(entries)} entry signals")

if len(entries) == 0:
    print("No signals found. Exiting.")
    sys.exit(1)

# Limit to 50000 for performance
if len(entries) > 50000:
    print(f"   Truncating to 50000 signals for performance")
    entries = entries[:50000]

# Step 2: Batch query exit prices
# For each hold period, collect all (ts_code, exit_date) pairs and query in batches
print("📊 Querying exit prices...")

for hp in [1, 3, 5, 10]:
    print(f"   hold={hp}...")
    exit_prices = {}
    batch_lookup = {}  # exit_date -> [ts_codes]
    
    for sig in entries:
        exit_date = nth_trade_day(sig["trade_date"], hp)
        if exit_date:
            key = (sig["ts_code"], sig["trade_date"])
            exit_prices[key] = {"exit_date": exit_date, "price": None}
            batch_lookup.setdefault(exit_date, []).append(sig["ts_code"])
    
    # Batch query by exit_date
    for exit_date, codes in batch_lookup.items():
        # Query in chunks to avoid too long IN clause
        chunk_size = 500
        for i in range(0, len(codes), chunk_size):
            chunk = codes[i:i+chunk_size]
            codes_str = ", ".join(f"'{c}'" for c in chunk)
            sql = f"""
            SELECT ts_code, close FROM (
                SELECT * FROM tushare.tushare_stock_daily FINAL
                WHERE trade_date = '{exit_date}'
            )
            WHERE ts_code IN ({codes_str})
            """
            rows = ch_query(sql)
            price_map = {r["ts_code"]: r["close"] for r in rows}
            for code in chunk:
                key = (code, None)  # we don't know which entry date
                # Find matching entry
                for ek in exit_prices:
                    if ek[0] == code:
                        exit_prices[ek]["price"] = price_map.get(code, 0)
    
    # Calculate returns
    returns = []
    for (tc, ed), data in exit_prices.items():
        if data["price"] and data["price"] > 0:
            # Find entry close for this signal
            entry_close = None
            for e in entries:
                if e["ts_code"] == tc and e["trade_date"] == ed:
                    entry_close = e["entry_close"]
                    break
            if entry_close:
                ret = (data["price"] - entry_close) / entry_close * 100
                returns.append(ret)
    
    st = calc_stats(returns, hp)
    print(f"      n={st['n']}, WR={st['wr']}%, avg_ret={st['avg_ret']}%, CI_low={st['ci_lower']}%")

print("\n✅ Done")
