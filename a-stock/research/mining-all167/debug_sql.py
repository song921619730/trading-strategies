#!/usr/bin/env python3
"""Debug combo SQL response"""
import json, subprocess

sql = """SELECT d.ts_code, d.trade_date
FROM (SELECT ts_code, trade_date, pct_chg, close,
  (close - MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS 19 PRECEDING)) /
  GREATEST(MAX(high) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS 19 PRECEDING)
         - MIN(low) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS 19 PRECEDING), 1e-10) AS pos_20d,
  (high - low) / GREATEST(close, 1e-10) * 100 AS amp_pct,
  lagInFrame(pct_chg, 1) OVER (PARTITION BY ts_code ORDER BY trade_date) AS prev_pct
FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
WHERE s.trade_date >= '2020-01-01' AND s.trade_date <= '2026-05-12'
  AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%'
  AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%' AND s.close > 0) AS d
INNER JOIN (SELECT * FROM tushare.tushare_daily_basic FINAL) AS b
  ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
WHERE d.pos_20d <= 0.20 AND d.pct_chg <= -5 AND d.amp_pct >= 5
  AND b.volume_ratio >= 1.2 AND b.circ_mv <= 300000 AND b.circ_mv > 0
LIMIT 5"""

r = subprocess.run(["python3", "ch_helper.py", sql, "300"], capture_output=True, text=True, timeout=310)
data = json.loads(r.stdout)
print(f"Type: {type(data).__name__}")
if isinstance(data, list):
    print(f"Len: {len(data)}")
    if data:
        print(f"Keys: {list(data[0].keys())}")
        print(f"Sample: {data[0]}")
elif isinstance(data, dict):
    print(f"Dict keys: {list(data.keys())}")
print(f"stderr: {r.stderr[:200]}")
