#!/usr/bin/env python3
"""Debug T5 — test data pipeline step by step"""
import json, subprocess, sys

CH_URL = "http://127.0.0.1:8123"
CH_DB = "tushare"
CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"

def ch_query(sql, fmt="JSON", timeout=60):
    with open('/tmp/ch_q.sql', 'w') as f:
        f.write(sql.rstrip().rstrip(";") + (f"\nFORMAT {fmt}" if fmt else ""))
    cmd = ["curl", "-s", "-X", "POST",
           f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&max_execution_time={timeout}&database={CH_DB}",
           "--data-binary", "@/tmp/ch_q.sql"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+10)
    return json.loads(r.stdout)

# 1. Check SPX data
print("=== SPX Check ===")
r = ch_query("SELECT ts_code, trade_date, pct_chg FROM tushare.tushare_index_global FINAL WHERE ts_code='SPX' AND trade_date >= '2024-01-01' ORDER BY trade_date DESC LIMIT 10")
for row in r.get('data', []):
    print(f"  {row['trade_date']}: {row.get('pct_chg')}")

# 2. Count Phase 1 candidate rows
print("\n=== Phase 1 Count ===")
r = ch_query("""
SELECT count() as cnt FROM (
    SELECT ts_code, trade_date, close, pct_chg, high, low, vol, amount
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2024-01-01' AND trade_date <= '2026-05-06'
      AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%'
      AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
)
""")
print(f"  Total daily rows (2024-2026): {r.get('data', [{}])[0].get('cnt')}")

# 3. Check a sample of daily_basic rows with dv_ratio, pb, pe
print("\n=== Daily Basic Sample ===")
r = ch_query("""
SELECT count() as cnt FROM tushare.tushare_daily_basic FINAL
WHERE trade_date >= '2024-06-01' AND trade_date <= '2026-05-06'
  AND dv_ratio IS NOT NULL AND dv_ratio > 0
  AND pe IS NOT NULL AND pe > 0
  AND pb IS NOT NULL AND pb > 0
  AND circ_mv IS NOT NULL AND circ_mv > 0
""")
print(f"  Basic rows with dv/pe/pb/circ_mv: {r.get('data', [{}])[0].get('cnt')}")

# 4. Count PB≤1 + dv≥2% + CM≤50亿
print("\n=== Sample: PB≤1 + dv≥2% + CM≤50亿 ===")
r = ch_query("""
SELECT count() as cnt FROM (
    SELECT ts_code, trade_date, pe, pb, dv_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date = toDate('2026-04-15')
      AND dv_ratio IS NOT NULL AND dv_ratio >= 2
      AND pb IS NOT NULL AND pb > 0 AND pb <= 1
      AND circ_mv IS NOT NULL AND circ_mv <= 500000
)
""")
print(f"  PB≤1 + dv≥2% + CM≤50亿 on 2026-04-15: {r.get('data', [{}])[0].get('cnt')}")

# 5. Try direct candidate query with sample
print("\n=== Sample: Candidate with amplitude >= 3 ===")
r = ch_query("""
SELECT ts_code, trade_date, close, pct_chg, amplitude, pos_20d, pos_60d, vol_ratio
FROM (
    SELECT *,
        round((high / low - 1) * 100, 2) AS amplitude,
        round((close - min(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)) / 
              NULLIF(max(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) - 
                     min(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 0.001) * 100, 2) AS pos_20d,
        round((close - min(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)) / 
              NULLIF(max(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) - 
                     min(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW), 0.001) * 100, 2) AS pos_60d,
        round(vol / NULLIF(AVG(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING), 0.001), 2) AS vol_ratio
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '2024-10-01' AND trade_date <= '2026-05-06'
      AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%'
      AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
)
WHERE amplitude >= 3
  AND pos_20d <= 30
  AND vol_ratio >= 1.0
ORDER BY ts_code, trade_date
LIMIT 5
""", timeout=120)
rows = r.get('data', [])
print(f"  Sample rows: {len(rows)}")
for row in rows[:5]:
    print(f"  {row['ts_code']} {row['trade_date']} close={row['close']} pct={row['pct_chg']} amp={row['amplitude']} pos20d={row['pos_20d']} pos60d={row['pos_60d']} vr={row['vol_ratio']}")

# 6. Try with small date range to verify
print("\n=== Small range test ===")
r = ch_query("""
SELECT ts_code, trade_date, pe, pb, dv_ratio, circ_mv 
FROM tushare.tushare_daily_basic FINAL
WHERE trade_date = toDate('2026-04-15')
  AND circ_mv IS NOT NULL AND circ_mv <= 500000
  AND pe > 0 AND pe <= 15
  AND pb > 0 AND pb <= 2
  AND dv_ratio >= 3
LIMIT 10
""")
print(f"  dv≥3+PE≤15+PB≤2+CM≤50亿 on 2026-04-15: {len(r.get('data', []))} rows")
for row in r.get('data', [])[:5]:
    print(f"  {row['ts_code']} pe={row['pe']} pb={row['pb']} dv={row['dv_ratio']} mv={row['circ_mv']}")

# 7. Check fina_indicator - netprofit_yoy and roe availability
print("\n=== Fina Indicator Sample ===")
r = ch_query("""
SELECT count() as cnt FROM tushare.tushare_fina_indicator FINAL
WHERE netprofit_yoy IS NOT NULL AND netprofit_yoy >= 10
  AND roe IS NOT NULL AND roe >= 10
""")
print(f"  fina_indicator with np_yoy≥10% + roe≥10%: {r.get('data', [{}])[0].get('cnt')}")

print("\n=== Latest fina_indicator records ===")
r = ch_query("SELECT count(DISTINCT ts_code) FROM tushare.tushare_fina_indicator FINAL")
print(f"  Distinct stocks: {r.get('data', [{}])[0].get('count(DISTINCT ts_code)')}")

r = ch_query("""
SELECT ts_code, end_date, netprofit_yoy, roe 
FROM tushare.tushare_fina_indicator FINAL
WHERE netprofit_yoy IS NOT NULL AND netprofit_yoy >= 10
ORDER BY end_date DESC LIMIT 5
""")
for row in r.get('data', []):
    print(f"  {row['ts_code']} end={row['end_date']} np_yoy={row['netprofit_yoy']} roe={row['roe']}")
