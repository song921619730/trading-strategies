#!/usr/bin/env python3
"""Test ch_helper.py with large queries"""
import subprocess, sys

queries = [
    ("stock_daily count", "SELECT count(*) AS cnt FROM tushare.tushare_stock_daily FINAL WHERE trade_date >= '2020-01-01' AND trade_date <= '2026-05-12' AND ts_code NOT LIKE '30%' AND ts_code NOT LIKE '688%' AND ts_code NOT LIKE '920%' AND ts_code NOT LIKE '%ST%' AND close > 0"),
    ("daily_basic count", "SELECT count(*) AS cnt FROM tushare.tushare_daily_basic FINAL WHERE trade_date >= '2020-01-01'"),
    ("moneyflow count", "SELECT count(*) AS cnt FROM tushare.tushare_moneyflow FINAL WHERE trade_date >= '2020-01-01'"),
]

for label, sql in queries:
    r = subprocess.run(["python3", "ch_helper.py", sql, "300"], capture_output=True, text=True, timeout=310)
    status = "OK" if r.returncode == 0 else f"FAIL(rc={r.returncode})"
    out_preview = r.stdout[:80] if r.stdout else ""
    err_preview = r.stderr[:80] if r.stderr else ""
    print(f"{label}: {status} | {out_preview} | stderr: {err_preview}")
