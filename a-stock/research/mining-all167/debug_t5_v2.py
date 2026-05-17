#!/usr/bin/env python3
"""
T5 Iter23 — Simplified test: just run C3 (the most viable combo)
to debug the zero-signal issue, then add remaining combos.
"""
import json, hashlib, math, subprocess, sys, os
from datetime import datetime

CH_USER = "ai_reader"
CH_PASS = "OqywPPt0uQsWRz8yMfXili1FAaTJiuxG4KdTOaqBPqQ"
CH_URL = "http://127.0.0.1:8123"
CH_DB = "tushare"
START_DATE = "2024-01-01"  # shortened for debugging
END_DATE = "2026-05-12"
SIGNAL_END = "2026-05-06"

def ch_query(sql, fmt="JSON", timeout=180):
    with open('/tmp/ch_q_t5.sql', 'w') as f:
        f.write(sql.rstrip().rstrip(";") + (f"\nFORMAT {fmt}" if fmt else ""))
    cmd = ["curl", "-s", "-X", "POST",
           f"{CH_URL}/?user={CH_USER}&password={CH_PASS}&max_execution_time={timeout}&database={CH_DB}",
           "--data-binary", "@/tmp/ch_q_t5.sql"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+10)
        return json.loads(r.stdout)
    except Exception as e:
        print(f"  CH QUERY ERROR: {e}")
        return {"data": []}

def compute_stats(results):
    n = len(results)
    if n == 0:
        return {"signal_count": 0, "wr_5d": 0, "wr_10d": 0, "wr_20d": 0,
                "ret_5d": 0, "ret_10d": 0, "ret_20d": 0, "sharpe_5d": 0}
    def avg(lst): return sum(lst) / len(lst) if lst else 0
    def std(lst):
        if len(lst) < 2: return 0
        m = avg(lst)
        return math.sqrt(sum((x-m)**2 for x in lst) / len(lst))
    stats = {"signal_count": n}
    for k in ["ret_5d", "ret_10d", "ret_20d"]:
        vals = [r[k] for r in results if r[k] is not None]
        stats[f"wr_{k.replace('ret_', '')}"] = round(sum(1 for v in vals if v > 0) / len(vals) * 100, 2) if vals else 0
        stats[k] = round(avg(vals) * 100, 4) if vals else 0
    ret5_vals = [r["ret_5d"] for r in results if r["ret_5d"] is not None]
    if len(ret5_vals) > 1:
        sd = std(ret5_vals)
        stats["sharpe_5d"] = round((avg(ret5_vals) / sd) * math.sqrt(252/5), 4) if sd > 0 else 0
    else:
        stats["sharpe_5d"] = 0
    return stats

t0 = datetime.now()

# ===== STEP 1: max date =====
r = ch_query("SELECT max(trade_date) FROM tushare.tushare_stock_daily FINAL")
max_date = r.get('data', [{}])[0].get('max(trade_date)', '?')
print(f"Max trade_date: {max_date}")

# ===== STEP 2: Build candidates =====
print(f"\n--- Phase 1: Building candidates (2024-{SIGNAL_END}) ---")
sql = f"""
SELECT ts_code, trade_date, close, pct_chg, high, low, vol, amount,
    round((high / low - 1) * 100, 2) AS amplitude,
    round((close - min_low_20d) / NULLIF(max_high_20d - min_low_20d, 0.001) * 100, 2) AS pos_20d,
    round((close - min_low_60d) / NULLIF(max_high_60d - min_low_60d, 0.001) * 100, 2) AS pos_60d,
    round(vol / NULLIF(avg_vol_20d, 0.001), 2) AS vol_ratio
FROM (
    SELECT ts_code, trade_date, close, high, low, vol, amount, pct_chg,
        MIN(low) OVER w20 AS min_low_20d,
        MAX(high) OVER w20 AS max_high_20d,
        MIN(low) OVER w60 AS min_low_60d,
        MAX(high) OVER w60 AS max_high_60d,
        AVG(vol) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avg_vol_20d
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{START_DATE}' AND trade_date <= '{SIGNAL_END}'
      AND ts_code NOT LIKE '30%%' AND ts_code NOT LIKE '688%%'
      AND ts_code NOT LIKE '920%%' AND ts_code NOT LIKE '%%ST%%'
    WINDOW w20 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
           w60 AS (PARTITION BY ts_code ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
)
WHERE amplitude >= 3
ORDER BY ts_code, trade_date
"""

r = ch_query(sql, timeout=600)
data = r.get('data', [])
print(f"  Rows: {len(data)}")
if len(data) > 0:
    print(f"  Sample: {data[0]['ts_code']} {data[0]['trade_date']}")
else:
    print("  ERROR: No candidates! Check SQL or data availability.")
    print(f"  Response keys: {list(r.keys())}")
    if 'error' in r:
        print(f"  Error: {r['error']}")
    sys.exit(1)

candidates = {}
for row in data:
    key = (row['ts_code'], str(row['trade_date'])[:10])
    candidates[key] = row

ts_codes = set(row['ts_code'] for row in data)
print(f"  Unique stocks: {len(ts_codes)}")

# ===== STEP 3: Fetch daily_basic =====
print(f"\n--- Phase 2: daily_basic ---")
code_list = list(ts_codes)
batch_size = 500
db_data = {}
for i in range(0, len(code_list), batch_size):
    batch = code_list[i:i+batch_size]
    codes_str = ",".join(f"'{c}'" for c in batch)
    sql = f"""
    SELECT ts_code, trade_date, pe, pb, dv_ratio, circ_mv
    FROM tushare.tushare_daily_basic FINAL
    WHERE trade_date >= '{START_DATE}' AND trade_date <= '{SIGNAL_END}'
      AND ts_code IN ({codes_str})
    ORDER BY ts_code, trade_date
    """
    r = ch_query(sql, timeout=300)
    rows = r.get('data', [])
    for row in rows:
        key = (row['ts_code'], str(row['trade_date'])[:10])
        db_data[key] = row
    if i % 1000 == 0 or i + batch_size >= len(code_list):
        print(f"  batch {i//batch_size}: db_rows={len(rows)}, total_db={len(db_data)}")  # <-- FIXED f-string

print(f"  Total db_data: {len(db_data)}")

# ===== STEP 4: SPX =====
print(f"\n--- Phase 3: SPX ---")
r = ch_query(f"""
SELECT trade_date, pct_chg FROM tushare.tushare_index_global FINAL
WHERE ts_code='SPX' AND trade_date >= '{START_DATE}'
ORDER BY trade_date
""")
spx_data = {}
for row in r.get('data', []):
    spx_data[str(row['trade_date'])[:10]] = row.get('pct_chg', 0) or 0
print(f"  SPX rows: {len(spx_data)}")

# ===== STEP 5: Forward prices =====
print(f"\n--- Phase 4: Forward prices ---")
all_prices = {}
for i in range(0, len(code_list), batch_size):
    batch = code_list[i:i+batch_size]
    codes_str = ",".join(f"'{c}'" for c in batch)
    sql = f"""
    SELECT ts_code, trade_date, close
    FROM tushare.tushare_stock_daily FINAL
    WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}'
      AND ts_code IN ({codes_str})
    ORDER BY ts_code, trade_date
    """
    r = ch_query(sql, timeout=300)
    rows = r.get('data', [])
    for row in rows:
        key = (row['ts_code'], str(row['trade_date'])[:10])
        all_prices[key] = row['close']
    if i % 1000 == 0 or i + batch_size >= len(code_list):
        print(f"  batch {i//batch_size}: price_rows={len(rows)}, total_prices={len(all_prices)}")  # <-- FIXED f-string

print(f"  Total prices: {len(all_prices)}")

# ===== DEBUG: Simple filter (no SPX) =====
print(f"\n--- DEBUG FILTER: dv≥3 + PE≤15 + PB≤2 + CM≤50亿 + VR≥1.0 (no pos, no amp) ---")
debug_signals = []
for (code, date), row in candidates.items():
    k = (code, date)
    db_row = db_data.get(k, {})
    if not db_row:
        continue
    vr = row.get('vol_ratio', 0) or 0
    pe = db_row.get('pe')
    pb = db_row.get('pb')
    dv = db_row.get('dv_ratio')
    cm = db_row.get('circ_mv')
    
    if vr < 1.0: continue
    if not pe or pe <= 0 or pe > 15: continue
    if not pb or pb <= 0 or pb > 2: continue
    if not dv or dv < 3: continue
    if not cm or cm > 500000: continue
    
    debug_signals.append({
        'ts_code': code, 'trade_date': date, 'close': row['close'],
        'pe': pe, 'pb': pb, 'dv_ratio': dv, 'circ_mv': cm, 'vol_ratio': vr
    })
print(f"  Debug signals (no pos/amp filter): {len(debug_signals)}")
if debug_signals:
    for s in debug_signals[:5]:
        print(f"  {s['ts_code']} {s['trade_date']} pe={s['pe']} pb={s['pb']} dv={s['dv_ratio']} cm={s['circ_mv']}")

# ===== COMBO C3: Pure test =====
print(f"\n--- COMBO C3: dv≥3 + PE≤15 + PB≤2 + CM≤50亿 + VR≥1.3 + 振幅≥6% ---")
c3_signals = []
for (code, date), row in candidates.items():
    k = (code, date)
    db_row = db_data.get(k, {})
    if not db_row:
        continue
    vr = row.get('vol_ratio', 0) or 0
    amp = row.get('amplitude', 0) or 0
    pe = db_row.get('pe')
    pb = db_row.get('pb')
    dv = db_row.get('dv_ratio')
    cm = db_row.get('circ_mv')
    
    if amp < 6: continue
    if vr < 1.3: continue
    if not pe or pe <= 0 or pe > 15: continue
    if not pb or pb <= 0 or pb > 2: continue
    if not dv or dv < 3: continue
    if not cm or cm > 500000: continue
    
    c3_signals.append({
        'ts_code': code, 'trade_date': date, 'close': row['close'], 'pct_chg': row.get('pct_chg'),
        'amplitude': amp, 'vol_ratio': vr, 'pe': pe, 'pb': pb, 'dv_ratio': dv, 'circ_mv': cm
    })
print(f"  C3 signals: {len(c3_signals)}")
if c3_signals:
    for s in c3_signals[:5]:
        print(f"  {s['ts_code']} {s['trade_date']} pct={s['pct_chg']} amp={s['amplitude']} vr={s['vol_ratio']} pe={s['pe']} dv={s['dv_ratio']}")

# ===== Compute returns =====
if len(c3_signals) >= 200:
    print(f"\n--- Computing C3 returns ---")
    results = []
    for s in c3_signals:
        code = s['ts_code']
        entry_date = s['trade_date']
        stock_dates = sorted([d for (c, d), v in all_prices.items() if c == code and d >= entry_date])
        if entry_date not in stock_dates: continue
        idx = stock_dates.index(entry_date)
        rets = {'ts_code': code, 'trade_date': entry_date, 'entry_close': s['close']}
        for offset, key in [(5, 'ret_5d'), (10, 'ret_10d'), (20, 'ret_20d')]:
            if idx + offset < len(stock_dates):
                fd = stock_dates[idx + offset]
                fc = all_prices.get((code, fd))
                if fc and s['close'] and s['close'] > 0:
                    rets[key] = (fc - s['close']) / s['close']
                else:
                    rets[key] = None
            else:
                rets[key] = None
        results.append(rets)
    stats = compute_stats(results)
    print(f"  N={stats['signal_count']}, WR5d={stats['wr_5d']}%, R5={stats['ret_5d']}%, "
          f"R10={stats['ret_10d']}%, R20={stats['ret_20d']}%, Sharpe={stats['sharpe_5d']}")
else:
    print(f"  C3 signals too few ({len(c3_signals)}), skipping return computation")

elapsed = datetime.now() - t0
print(f"\nTotal time: {elapsed}")
print("DONE")
