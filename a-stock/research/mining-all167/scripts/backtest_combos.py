#!/usr/bin/env python3
"""
Backtest 5 parameter combinations against ClickHouse.
Data baseline: 2026-05-08.
Pattern: compute window functions on stock_daily alone, then JOIN for filtering.
"""

import json, hashlib, math, subprocess

CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_URL = "http://127.0.0.1:8123"
CH_DB = "tushare"

def ch_query(sql, fmt="JSON", timeout=120):
    with open('/tmp/ch_query.sql', 'w') as f:
        f.write(sql.rstrip().rstrip(";") + (f"\nFORMAT {fmt}" if fmt else ""))
    cmd = ["curl", "-s", "-X", "POST",
           f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&max_execution_time={timeout}&database={CH_DB}",
           "--data-binary", "@/tmp/ch_query.sql"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+10)
        data = result.stdout
        if fmt == "JSON":
            return json.loads(data)
        return data.strip()
    except json.JSONDecodeError:
        return {"error": data.strip()[:500]}
    except subprocess.TimeoutExpired:
        return {"error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}

def compute_stats(results):
    n = len(results)
    if n == 0:
        return {"signal_count": 0, "wr_1d": 0, "wr_3d": 0, "wr_5d": 0, "wr_10d": 0, "wr_20d": 0,
                "ret_1d": 0, "ret_3d": 0, "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0}
    def avg(lst): return sum(lst) / len(lst) if lst else 0
    def std(lst):
        if len(lst) < 2: return 0
        m = avg(lst)
        return math.sqrt(sum((x-m)**2 for x in lst) / len(lst))
    stats = {"signal_count": n}
    for k in ["ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d"]:
        vals = [r[k] for r in results if r[k] is not None]
        stats[f"wr_{k.replace('ret_', '')}"] = round(sum(1 for v in vals if v > 0) / len(vals) * 100, 2) if vals else 0
        stats[k] = round(avg(vals) * 100, 4) if vals else 0
    ret5_vals = [r["ret_5d"] for r in results if r["ret_5d"] is not None]
    if len(ret5_vals) > 1:
        m5, s5 = avg(ret5_vals), std(ret5_vals)
        stats["sharpe_5d"] = round(m5 / s5 * math.sqrt(252/5), 4) if s5 > 0 else 0
    else:
        stats["sharpe_5d"] = 0
    return stats

ST_FILTER = "AND ts_code NOT IN (SELECT ts_code FROM tushare.tushare_stock_basic FINAL WHERE name LIKE '%ST%')"

# ═══════════════════════════════════════════
# Combo 1: 放量突破+资金认可
# n_day_high=20, volume_ratio>=1.5, buy_elg_ratio>=0.05, turnover_rate>=1%
# ═══════════════════════════════════════════
SQL_COMBO1 = f"""
SELECT ts_code, trade_date, sig_close, fc[1] AS c1d, fc[3] AS c3d, fc[5] AS c5d, fc[10] AS c10d, fc[20] AS c20d
FROM (
    SELECT ts_code, trade_date, close AS sig_close, pct_chg AS d_pct_chg, vol AS d_vol,
        max(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max_close_20d,
        groupArray(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING) AS fc
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101' AND trade_date <= '20260508'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'
      {ST_FILTER}
) dw
INNER JOIN (SELECT ts_code, trade_date, volume_ratio, turnover_rate FROM tushare.tushare_daily_basic FINAL) b USING (ts_code, trade_date)
INNER JOIN (SELECT ts_code, trade_date, buy_elg_vol, sell_elg_vol FROM tushare.tushare_moneyflow FINAL) m USING (ts_code, trade_date)
WHERE sig_close = max_close_20d
  AND volume_ratio >= 1.5
  AND turnover_rate >= 1.0
  AND (buy_elg_vol / nullIf(buy_elg_vol + sell_elg_vol, 0)) >= 0.05
LIMIT 50000
"""

# ═══════════════════════════════════════════
# Combo 2: 低估值+中大盘
# pe<=30, pb<=3, circ_mv 100-500亿
# ═══════════════════════════════════════════
SQL_COMBO2 = f"""
SELECT ts_code, trade_date, sig_close, fc[1] AS c1d, fc[3] AS c3d, fc[5] AS c5d, fc[10] AS c10d, fc[20] AS c20d
FROM (
    SELECT ts_code, trade_date, close AS sig_close,
        groupArray(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING) AS fc
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101' AND trade_date <= '20260508'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'
      {ST_FILTER}
) dw
INNER JOIN (SELECT ts_code, trade_date, pe, pb, circ_mv FROM tushare.tushare_daily_basic FINAL) b USING (ts_code, trade_date)
WHERE pe > 0 AND pe <= 30
  AND pb > 0 AND pb <= 3
  AND circ_mv >= 1000000 AND circ_mv <= 5000000
LIMIT 50000
"""

# ═══════════════════════════════════════════
# Combo 3: 涨停+趋势跟随
# limit_times>=1, close>MA20, pct_chg>=0
# ═══════════════════════════════════════════
SQL_COMBO3 = f"""
SELECT ts_code, trade_date, sig_close, fc[1] AS c1d, fc[3] AS c3d, fc[5] AS c5d, fc[10] AS c10d, fc[20] AS c20d
FROM (
    SELECT ts_code, trade_date, close AS sig_close, pct_chg, vol,
        avg(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20,
        groupArray(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING) AS fc
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101' AND trade_date <= '20260508'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'
      {ST_FILTER}
) dw
INNER JOIN (SELECT ts_code, trade_date, limit_times FROM tushare.tushare_limit_list_d FINAL) ld USING (ts_code, trade_date)
WHERE limit_times >= 1 AND sig_close > ma20 AND pct_chg >= 0
LIMIT 50000
"""

# ═══════════════════════════════════════════
# Combo 4: 主力净流入+低PB
# net_mf_vol>=50000, pb<=5, pct_chg>=0
# ═══════════════════════════════════════════
SQL_COMBO4 = f"""
SELECT ts_code, trade_date, sig_close, fc[1] AS c1d, fc[3] AS c3d, fc[5] AS c5d, fc[10] AS c10d, fc[20] AS c20d
FROM (
    SELECT ts_code, trade_date, close AS sig_close, pct_chg,
        groupArray(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING) AS fc
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '20200101' AND trade_date <= '20260508'
      AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'
      {ST_FILTER}
) dw
INNER JOIN (SELECT ts_code, trade_date, pb FROM tushare.tushare_daily_basic FINAL) b USING (ts_code, trade_date)
INNER JOIN (SELECT ts_code, trade_date, buy_lg_vol, sell_lg_vol, buy_elg_vol, sell_elg_vol FROM tushare.tushare_moneyflow FINAL) m USING (ts_code, trade_date)
WHERE pb > 0 AND pb <= 5
  AND (buy_lg_vol + buy_elg_vol - sell_lg_vol - sell_elg_vol) >= 50000
  AND pct_chg >= 0
LIMIT 50000
"""

# ═══════════════════════════════════════════
# Combo 5: 低位+放量
# close in bottom 40% of 60d range, vol>MA5_vol*1.5, pct_chg>=0
# ═══════════════════════════════════════════
SQL_COMBO5 = f"""
SELECT ts_code, trade_date, sig_close, fc[1] AS c1d, fc[3] AS c3d, fc[5] AS c5d, fc[10] AS c10d, fc[20] AS c20d
FROM (
    SELECT ts_code, trade_date, sig_close, pct_chg, position_ratio, vol_ratio, fc
    FROM (
        SELECT ts_code, trade_date, close AS sig_close, pct_chg, vol,
            (close - min60) / nullIf(max60 - min60, 0) AS position_ratio,
            vol / nullIf(ma5_vol, 0) AS vol_ratio,
            groupArray(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING) AS fc
        FROM (
            SELECT ts_code, trade_date, close, pct_chg, vol,
                min(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS min60,
                max(close) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS max60,
                avg(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5_vol
            FROM tushare.tushare_stock_daily FINAL
            WHERE trade_date >= '20200101' AND trade_date <= '20260508'
              AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%'
              {ST_FILTER}
        )
    )
)
WHERE position_ratio <= 0.40
  AND vol_ratio >= 1.5
  AND pct_chg >= 0
LIMIT 50000
"""

combos_sql = [
    {"name": "放量突破+资金认可", "sql": SQL_COMBO1,
     "params": "n_day_high=20, volume_ratio_min=1.5, buy_elg_ratio_min=0.05, turnover_rate_min=0.01"},
    {"name": "低估值+中大盘", "sql": SQL_COMBO2,
     "params": "pe_max=30, pb_max=3, market_cap_bucket=中大盘(100-500亿)"},
    {"name": "涨停+趋势跟随", "sql": SQL_COMBO3,
     "params": "limit_times_min=1, ma_arrangement=close>MA20, pct_chg_min=0"},
    {"name": "主力净流入+低PB", "sql": SQL_COMBO4,
     "params": "net_mf_vol_min=50000, pb_max=5, pct_chg_min=0"},
    {"name": "低位+放量", "sql": SQL_COMBO5,
     "params": "close_position=底40%, vol>MA5_vol*1.5, pct_chg_min=0"},
]

for c in combos_sql:
    c["hash"] = hashlib.md5(c["params"].encode()).hexdigest()[:12]

results_all = []
for combo in combos_sql:
    print(f"\n{'='*60}")
    print(f"Running: {combo['name']}")
    print(f"Hash: {combo['hash']}")
    
    data = ch_query(combo["sql"], fmt="JSON")
    
    if "error" in data:
        print(f"  ERROR: {data['error'][:300]}")
        results_all.append({"name": combo["name"], "params": combo["params"], "hash": combo["hash"],
                          "error": data["error"], "stats": None, "sql": combo["sql"]})
        continue
    
    rows = data.get("data", [])
    print(f"  Rows: {len(rows)}")
    
    if len(rows) == 0:
        results_all.append({"name": combo["name"], "params": combo["params"], "hash": combo["hash"],
                          "stats": {"signal_count": 0}, "sql": combo["sql"], "row_count": 0})
        continue
    
    ret_results = []
    for row in rows:
        sig_close = float(row.get("sig_close", 0) or 0)
        if sig_close <= 0:
            continue
        def calc_ret(key):
            c = row.get(key)
            if c is not None:
                cv = float(c)
                if cv > 0 and sig_close > 0:
                    return cv / sig_close - 1
            return None
        ret_results.append({
            "ret_1d": calc_ret("c1d"), "ret_3d": calc_ret("c3d"),
            "ret_5d": calc_ret("c5d"), "ret_10d": calc_ret("c10d"), "ret_20d": calc_ret("c20d"),
        })
    
    stats = compute_stats(ret_results)
    stats["rows_returned"] = len(rows)
    print(f"  signals={stats['signal_count']}, WR1d={stats['wr_1d']}%, WR5d={stats['wr_5d']}%, ret5d={stats['ret_5d']}%, ret10d={stats['ret_10d']}%, sharpe5d={stats['sharpe_5d']}")
    
    results_all.append({"name": combo["name"], "params": combo["params"], "hash": combo["hash"],
                       "stats": stats, "sql": combo["sql"], "row_count": len(rows)})

with open("/tmp/backtest_results.json", "w") as f:
    json.dump(results_all, f, ensure_ascii=False, indent=2)

print("\n" + "="*60)
print("BACKTEST SUMMARY")
print("="*60)
for r in results_all:
    if r.get("stats") and r["stats"].get("signal_count", 0) > 0:
        s = r["stats"]
        ok = "PASS" if s["wr_5d"] >= 52 and s["ret_5d"] >= 3 and s["signal_count"] >= 200 else "FAIL"
        print(f"[{ok}] {r['name']}: signals={s['signal_count']}, WR1d={s['wr_1d']}%, WR5d={s['wr_5d']}%, WR10d={s['wr_10d']}%, ret5d={s['ret_5d']}%, ret10d={s['ret_10d']}%, sharpe5d={s['sharpe_5d']}")
    elif r.get("error"):
        print(f"[ERR] {r['name']}: {r['error'][:120]}")
    else:
        print(f"[N/A] {r['name']}: No signals")
