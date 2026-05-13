#!/usr/bin/env python3
"""
Compute T8-C5 baseline with 底20% filter for comparison.
"""
import json, math, sys, os, subprocess
from datetime import datetime

CH_QUERY = "/home/gjtmux/.hermes/skills/tushare-clickhouse-direct/scripts/ch_query.py"

def sql(query):
    r = subprocess.run(["python3", CH_QUERY, "sql", query], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"SQL ERROR: {r.stderr[:200]}")
        return []
    if not r.stdout.strip():
        return []
    try:
        return json.loads(r.stdout)
    except:
        return []

def compute_metrics(results, label):
    n = len(results)
    ret5 = [r.get("r5", 0) or 0 for r in results]
    a5 = sum(ret5) / n * 100 if n else 0
    w5 = sum(1 for r in ret5 if r > 0) / n * 100 if n else 0
    std5 = math.sqrt(sum((x - a5/100)**2 for x in ret5) / n) if n > 1 else 1
    sp5 = (a5 / 100) / std5 * math.sqrt(252 / 5) if std5 > 0 else 0
    return {"N": n, "WR5": round(w5,2), "R5": round(a5,4), "Sharpe5": round(sp5,3)}

dt_start = "2020-01-01"
dt_end = "2026-05-12"
dt_end_ext = "2026-08-01"

# Get signals
q = f"""
SELECT ts_code, trade_date, close
FROM (
    SELECT s.ts_code, s.trade_date, s.close,
           MIN(s.close) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS min20,
           MAX(s.close) OVER (PARTITION BY s.ts_code ORDER BY s.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS max20
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL) AS s
    JOIN (SELECT ts_code, trade_date, volume_ratio, circ_mv, turnover_rate FROM (SELECT * FROM tushare.tushare_daily_basic FINAL)) AS db
      ON s.ts_code = db.ts_code AND s.trade_date = db.trade_date
    WHERE s.trade_date >= '{dt_start}' AND s.trade_date <= '{dt_end}'
      AND s.close > 0 AND s.pre_close > 0
      AND s.open / s.pre_close < 1.0
      AND s.close / s.high >= 0.95
      AND db.volume_ratio >= 1.3
      AND (s.high - s.low) / s.pre_close * 100 >= 5.0
      AND db.circ_mv <= 500000
      AND s.pct_chg >= 2.0
      AND s.ts_code NOT LIKE '30%' AND s.ts_code NOT LIKE '688%' AND s.ts_code NOT LIKE '920%' AND s.ts_code NOT LIKE '%ST%'
)
WHERE (close - min20) / nullIf((max20 - min20), 0) < 0.20
ORDER BY trade_date
"""
signals = sql(q)
print(f"T8-C5 baseline (with 底20%): {len(signals)} signals")

# Forward returns
codes = list(set(s['ts_code'] for s in signals))
results = []
for cb in [codes[i:i+100] for i in range(0, len(codes), 100)]:
    cq = ",".join(f"'{c}'" for c in cb)
    q_px = f"""
    SELECT ts_code, trade_date, close,
           leadInFrame(close, 5) OVER w AS c5,
           leadInFrame(close, 10) OVER w AS c10,
           leadInFrame(close, 20) OVER w AS c20
    FROM (SELECT * FROM tushare.tushare_stock_daily FINAL)
    WHERE ts_code IN ({cq})
      AND trade_date >= '{dt_start}' AND trade_date <= '{dt_end_ext}'
    WINDOW w AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
    ORDER BY ts_code, trade_date
    """
    px_rows = sql(q_px)
    px_map = {(r['ts_code'], r['trade_date']): r for r in px_rows}
    for s in signals:
        key = (s['ts_code'], s['trade_date'])
        if key in px_map:
            px = px_map[key]
            if px.get('close') and px['close'] > 0:
                r5 = (px['c5'] / px['close'] - 1) if px.get('c5') and px['c5'] > 0 else None
                r10 = (px['c10'] / px['close'] - 1) if px.get('c10') and px['c10'] > 0 else None
                r20 = (px['c20'] / px['close'] - 1) if px.get('c20') and px['c20'] > 0 else None
                if r5 is not None:
                    results.append({'code': s['ts_code'], 'date': s['trade_date'], 'r5': r5, 'r10': r10, 'r20': r20})

print(f"Signals with forward returns: {len(results)}")
m = compute_metrics(results, "T8-C5-baseline")
print(f"T8-C5 baseline: N={m['N']}, WR5={m['WR5']}%, R5={m['R5']}%, Sharpe5={m['Sharpe5']}")
